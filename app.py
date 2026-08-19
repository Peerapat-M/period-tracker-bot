import os
import re
from datetime import datetime, timedelta
from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    FlexContainer,
    FlexMessage,
    MessagingApi,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    DatetimePickerAction,
    MessageAction,
    PostbackAction,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    TextMessageContent,
)
import psycopg2
from psycopg2.extras import RealDictCursor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

app = Flask(__name__)

CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ปรับแก้ URI ให้ใช้ psycopg2
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ----------------------------------------------------
# ⏰ Persistent Scheduler Setup (PostgreSQL)
# ----------------------------------------------------
jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}
scheduler = BackgroundScheduler(jobstores=jobstores)
scheduler.start()

# ----------------------------------------------------
# 🗄️ Database Setup & Helper Functions
# ----------------------------------------------------
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS period_logs (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                start_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                remind_days_before INTEGER DEFAULT 3
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS partners (
                user_id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Database Init Exception: {e}")

# Operations for Period Logs
def save_period_log(user_id, start_date_str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO period_logs (user_id, start_date) VALUES (%s, %s)",
            (user_id, start_date_str),
        )
        conn.commit()
    conn.close()

def get_user_logs(user_id, limit=5):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, start_date FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT %s",
            (user_id, limit),
        )
        rows = cur.fetchall()
    conn.close()
    return rows

def delete_last_log(user_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM period_logs WHERE id = %s", (row["id"],))
            conn.commit()
            conn.close()
            return True
    conn.close()
    return False

def reset_user_logs(user_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM period_logs WHERE user_id = %s", (user_id,))
        conn.commit()
    conn.close()

# Operations for User Settings
def get_user_remind_days(user_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT remind_days_before FROM user_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    conn.close()
    return row["remind_days_before"] if row else 3

def set_user_remind_days(user_id, days):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, remind_days_before) VALUES (%s, %s)
            ON CONFLICT(user_id) DO UPDATE SET remind_days_before = EXCLUDED.remind_days_before
            """,
            (user_id, days)
        )
        conn.commit()
    conn.close()

# Operations for Partner Sync
def link_partner(user_id, partner_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO partners (user_id, partner_id) VALUES (%s, %s)
            ON CONFLICT(user_id) DO UPDATE SET partner_id = EXCLUDED.partner_id
            """,
            (user_id, partner_id)
        )
        conn.commit()
    conn.close()

def get_partner_id(user_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT partner_id FROM partners WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    conn.close()
    return row["partner_id"] if row else None

def unlink_partner(user_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM partners WHERE user_id = %s", (user_id,))
        conn.commit()
    conn.close()

# Calculations
def calculate_avg_cycle(user_id):
    logs = get_user_logs(user_id, limit=5)
    if len(logs) < 2:
        return 28

    dates = [datetime.strptime(log["start_date"], "%Y-%m-%d") for log in logs]
    dates.sort()

    gaps = []
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if 20 <= gap <= 45:
            gaps.append(gap)

    if not gaps:
        return 28

    return int(round(sum(gaps) / len(gaps)))

# ----------------------------------------------------
# 🔔 Notification Functions
# ----------------------------------------------------
def send_period_reminder(user_id, next_period_str, days_before):
    user_msg = TextMessage(
        text=f"🔔 [แจ้งเตือนล่วงหน้า]\n\n"
             f"อีก {days_before} วันจะถึงกำหนดรอบเดือนถัดไปของคุณแล้วนะคะ! ({next_period_str})\n"
             f"อย่าลืมเตรียมพกผ้าอนามัยไว้ล่วงหน้านะคะ 🌸",
        quick_reply=get_calendar_quick_reply()
    )
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(PushMessageRequest(to=user_id, messages=[user_msg]))
    except Exception as e:
        print(f"❌ ส่งแจ้งเตือนล้มเหลว: {e}")

    partner_id = get_partner_id(user_id)
    if partner_id:
        partner_msg = TextMessage(
            text=f"🌸 [Care Mode - แจ้งเตือนคนรัก]\n\n"
                 f"อีก {days_before} วันจะถึงกำหนดรอบเดือนของแฟนคุณแล้วนะคะ ({next_period_str})\n\n"
                 f"💡 คำแนะนำในการดูแล:\n"
                 f"• เตรียมกระเป๋าน้ำร้อนหรือเครื่องดื่มอุ่นๆ ไว้ให้\n"
                 f"• ช่วยซัพพอร์ตและคอยเอาใจใส่เป็นพิเศษในช่วงนี้นะคะ 💕"
        )
        try:
            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).push_message(PushMessageRequest(to=partner_id, messages=[partner_msg]))
        except Exception as e:
            print(f"❌ ส่ง Care Mode หาแฟนล้มเหลว: {e}")

def send_late_period_alert(user_id, next_period_str):
    msg = TextMessage(
        text=f"❓ [ติดตามรอบเดือน]\n\n"
             f"รอบเดือนของคุณคาดว่าจะมาตั้งแต่วันที่ {next_period_str} (เลทมา 2 วันแล้ว)\n"
             f"ประจำเดือนมาหรือยังคะ? สามารถกดบันทึกวันแรกผ่านปฏิทินได้เลยนะคะ 🌸",
        quick_reply=get_calendar_quick_reply()
    )
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(PushMessageRequest(to=user_id, messages=[msg]))
    except Exception as e:
        print(f"❌ ส่งแจ้งเตือนรอบเดือนเลทล้มเหลว: {e}")

# ----------------------------------------------------
# 📱 Quick Replies & Flex Messages
# ----------------------------------------------------
def get_calendar_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=DatetimePickerAction(
                    label="📅 เลือกวันแรก",
                    data="action=select_date",
                    mode="date",
                )
            ),
            QuickReplyItem(action=MessageAction(label="ดูประวัติ", text="ดูประวัติ")),
            QuickReplyItem(action=MessageAction(label="แชร์ให้แฟน", text="แชร์ให้แฟน")),
            QuickReplyItem(action=MessageAction(label="แจ้งเตือน", text="แจ้งเตือน"))
        ]
    )

def get_settings_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(action=PostbackAction(label="เตือนล่วงหน้า 1 วัน", data="action=set_remind&days=1")),
            QuickReplyItem(action=PostbackAction(label="เตือนล่วงหน้า 3 วัน", data="action=set_remind&days=3")),
            QuickReplyItem(action=PostbackAction(label="เตือนล่วงหน้า 5 วัน", data="action=set_remind&days=5")),
        ]
    )

def get_confirm_reset_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(action=PostbackAction(label="⚠️ ยืนยันล้างข้อมูล", data="action=confirm_reset")),
            QuickReplyItem(action=PostbackAction(label="❌ ยกเลิก", data="action=cancel_reset"))
        ]
    )

def create_prediction_flex(latest_date, next_period, ovulation, fertile_start, fertile_end, test_date, avg_cycle, remind_days):
    bubble_json = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "🌸 พยากรณ์รอบเดือนของคุณ", "weight": "bold", "color": "#D87093", "size": "md"},
                {"type": "text", "text": "ประจำเดือนรอบถัดไป", "size": "xs", "color": "#888888", "margin": "xs"},
                {"type": "text", "text": next_period.strftime("%d/%m/%Y"), "weight": "bold", "size": "xxl", "color": "#C71585", "margin": "sm"}
            ],
            "backgroundColor": "#FFF0F5"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box", "layout": "horizontal", "margin": "md",
                    "contents": [
                        {"type": "text", "text": "🥚 วันไข่ตกโดยประมาณ", "size": "sm", "color": "#555555", "flex": 3},
                        {"type": "text", "text": ovulation.strftime("%d/%m/%Y"), "size": "sm", "weight": "bold", "align": "end", "flex": 2}
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "margin": "md",
                    "contents": [
                        {"type": "text", "text": "👶 ช่วงมีโอกาสตั้งครรภ์", "size": "sm", "color": "#555555", "flex": 3},
                        {"type": "text", "text": f"{fertile_start.strftime('%d/%m')} - {fertile_end.strftime('%d/%m/%Y')}", "size": "sm", "weight": "bold", "color": "#2E8B57", "align": "end", "flex": 3}
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "margin": "md",
                    "contents": [
                        {"type": "text", "text": "🧪 เริ่มตรวจครรภ์ได้ตั้งแต่", "size": "sm", "color": "#555555", "flex": 3},
                        {"type": "text", "text": test_date.strftime("%d/%m/%Y"), "size": "sm", "weight": "bold", "color": "#4169E1", "align": "end", "flex": 2}
                    ]
                },
                {"type": "separator", "margin": "lg"},
                {"type": "text", "text": f"ℹ️ รอบเดือนเฉลี่ย {avg_cycle} วัน | เตือนล่วงหน้า {remind_days} วัน", "size": "xs", "color": "#888888", "align": "center", "margin": "md"},
                {"type": "text", "text": "⚠️ เป็นเพียงการคาดการณ์ ควรใช้วิธีอื่นร่วมด้วยในการคุมกำเนิด", "size": "xs", "color": "#DC143C", "wrap": True, "align": "center", "margin": "xs"}
            ]
        }
    }
    return FlexMessage(alt_text="พยากรณ์รอบเดือน", contents=FlexContainer.from_dict(bubble_json))

def create_history_flex(user_id):
    logs = get_user_logs(user_id, limit=5)
    avg_cycle = calculate_avg_cycle(user_id)

    if not logs:
        return None

    history_contents = []
    for log in logs:
        dt = datetime.strptime(log["start_date"], "%Y-%m-%d")
        history_contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "sm",
            "contents": [
                {"type": "text", "text": "🩸 ประจำเดือนมาวันแรก", "size": "sm", "color": "#555555"},
                {"type": "text", "text": dt.strftime("%d/%m/%Y"), "size": "sm", "weight": "bold", "align": "end"}
            ]
        })

    bubble_json = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📋 ประวัติการบันทึกรอบเดือน", "weight": "bold", "color": "#D87093", "size": "md"},
                {"type": "text", "text": f"รอบเดือนเฉลี่ยปัจจุบัน: {avg_cycle} วัน", "size": "xs", "color": "#888888", "margin": "xs"}
            ],
            "backgroundColor": "#FFF0F5"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": history_contents
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "💡 กดปุ่ม 'ลบรายการล่าสุด' บน Rich Menu เพื่อลบข้อมูลล่าสุด", "size": "xs", "color": "#888888", "align": "center"}
            ]
        }
    }
    return FlexMessage(alt_text="ประวัติรอบเดือน", contents=FlexContainer.from_dict(bubble_json))

# ----------------------------------------------------
# ⚙️ Business Logic Helpers
# ----------------------------------------------------
def parse_date_input(text):
    text = text.strip()
    match = re.match(r"^(\d{1,2})[/\-\. ](\d{1,2})[/\-\. ](\d{4})(?:\s+(\d{1,2}))?$", text)
    if not match:
        return None, None

    day, month, year, custom_cycle = match.groups()
    day, month, year = int(day), int(month), int(year)
    custom_cycle = int(custom_cycle) if custom_cycle else None

    if year > 2500:
        year -= 543

    try:
        parsed_date = datetime(year, month, day)
        return parsed_date, custom_cycle
    except ValueError:
        return None, None

def schedule_user_reminders(user_id, next_period):
    remind_days = get_user_remind_days(user_id)
    next_period_str = next_period.strftime("%d/%m/%Y")

    reminder_date = next_period - timedelta(days=remind_days)
    reminder_datetime = datetime.combine(reminder_date, datetime.min.time()).replace(hour=9, minute=0)

    job_id = f"reminder_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        send_period_reminder,
        'date',
        run_date=reminder_datetime,
        args=[user_id, next_period_str, remind_days],
        id=job_id,
        replace_existing=True
    )

    late_date = next_period + timedelta(days=2)
    late_datetime = datetime.combine(late_date, datetime.min.time()).replace(hour=10, minute=0)

    late_job_id = f"late_{user_id}"
    if scheduler.get_job(late_job_id):
        scheduler.remove_job(late_job_id)

    scheduler.add_job(
        send_late_period_alert,
        'date',
        run_date=late_datetime,
        args=[user_id, next_period_str],
        id=late_job_id,
        replace_existing=True
    )

def process_and_reply(user_id, start_date, custom_cycle=None):
    save_period_log(user_id, start_date.strftime("%Y-%m-%d"))

    if custom_cycle and 20 <= custom_cycle <= 45:
        avg_cycle = custom_cycle
    else:
        avg_cycle = calculate_avg_cycle(user_id)

    next_period = start_date + timedelta(days=avg_cycle)
    ovulation = next_period - timedelta(days=14)
    fertile_start = ovulation - timedelta(days=5)
    fertile_end = ovulation + timedelta(days=1)
    test_date = ovulation + timedelta(days=12)

    schedule_user_reminders(user_id, next_period)
    remind_days = get_user_remind_days(user_id)

    return create_prediction_flex(start_date, next_period, ovulation, fertile_start, fertile_end, test_date, avg_cycle, remind_days)

# ----------------------------------------------------
# 📩 Webhook Handlers
# ----------------------------------------------------
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = (
        "สวัสดีค่ะ! ยินดีต้อนรับสู่ระบบบันทึกรอบเดือน 🌸\n\n"
        "คุณสามารถกดปุ่มเมนูด้านล่างเพื่อเริ่มใช้งานได้เลยนะคะ 😊"
    )
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=welcome_text, quick_reply=get_calendar_quick_reply())],
            )
        )

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    user_text_lower = user_text.lower()

    if user_text in ["บันทึกรอบเดือน", "บันทึก", "เลือกวันจากปฏิทิน"]:
        reply_msg = TextMessage(
            text="🗓️ เลือกวันแรกของรอบเดือนล่าสุดผ่านปฏิทินด้านล่าง หรือพิมพ์ระบุวันที่ เช่น 01/08/2026 ได้เลยค่ะ",
            quick_reply=get_calendar_quick_reply()
        )

    elif user_text in ["ดูประวัติ", "ประวัติ", "history", "เช็คประวัติ"]:
        history_flex = create_history_flex(user_id)
        if history_flex:
            reply_msg = history_flex
        else:
            reply_msg = TextMessage(
                text="ยังไม่พบประวัติการบันทึกค่ะ เลือกกด 'บันทึกรอบเดือน' เพื่อเริ่มบันทึกได้เลยนะคะ 😊",
                quick_reply=get_calendar_quick_reply()
            )

    elif user_text in ["แชร์ให้แฟน", "ผูกบัญชีแฟน", "partner", "care mode"]:
        partner_id = get_partner_id(user_id)
        if partner_id:
            reply_msg = TextMessage(
                text=f"💕 บัญชีของคุณผูกกับคนรักเรียบร้อยแล้ว!\n"
                     f"เมื่อถึงกำหนดเตือนล่วงหน้า บอทจะส่งข้อความ Care Mode ไปหาแฟนให้อัตโนมัตินะคะ 😊\n\n"
                     f"หากต้องการยกเลิก ให้พิมพ์ว่า: 'ยกเลิกผูกแฟน'",
                quick_reply=get_calendar_quick_reply()
            )
        else:
            reply_msg = TextMessage(
                text=f"👩‍❤️‍👨 [Care Mode - แชร์ข้อมูลให้คนรัก]\n\n"
                     f"ส่งข้อความคำสั่งด้านล่างนี้ไปให้แฟนนำมาพิมพ์ใส่บอทได้เลยนะคะ:\n\n"
                     f"pair {user_id}\n\n"
                     f"📌 หรือหากคุณได้ ID จากแฟนมาแล้ว ให้พิมพ์ตอบกลับมาในรูปแบบ: pair USER_ID",
                quick_reply=get_calendar_quick_reply()
            )

    elif user_text in ["แจ้งเตือน", "ตั้งค่าแจ้งเตือน", "ตั้งค่า", "settings"]:
        current_days = get_user_remind_days(user_id)
        reply_msg = TextMessage(
            text=f"⚙️ [ตั้งค่าการแจ้งเตือน]\n\n"
                 f"ปัจจุบันระบบจะเตือนล่วงหน้า {current_days} วัน (เวลา 09:00 น.)\n"
                 f"ต้องการเปลี่ยนเป็นเตือนล่วงหน้ากี่วัน เลือกด้านล่างได้เลยนะคะ:",
            quick_reply=get_settings_quick_reply()
        )

    elif user_text in ["ลบรายการล่าสุด", "ลบข้อมูล", "ลบ", "delete"]:
        if delete_last_log(user_id):
            reply_msg = TextMessage(
                text="ลบรายการล่าสุดเรียบร้อยแล้วค่ะ 🗑️\nกดปุ่ม 'ดูประวัติ' เพื่อดูรายการที่เหลือได้เลยนะคะ",
                quick_reply=get_calendar_quick_reply()
            )
        else:
            reply_msg = TextMessage(text="ไม่พบข้อมูลให้ลบค่ะ 😊", quick_reply=get_calendar_quick_reply())

    elif user_text in ["รีเซ็ตประวัติ", "รีเซ็ต", "reset", "ล้างข้อมูล"]:
        reply_msg = TextMessage(
            text="⚠️ คุณแน่ใจหรือไม่ว่าต้องการล้างประวัติรอบเดือนทั้งหมด?\n"
                 "การดำเนินการนี้ไม่สามารถย้อนกลับได้ค่ะ",
            quick_reply=get_confirm_reset_quick_reply()
        )

    elif user_text_lower.startswith("pair "):
        target_partner_id = user_text[5:].strip()
        if target_partner_id and len(target_partner_id) > 10:
            link_partner(user_id, target_partner_id)
            reply_msg = TextMessage(
                text="🎉 ผูกบัญชีกับคนรักเรียบร้อยแล้วค่ะ!\n"
                     "เมื่อถึงกำหนดเตือนรอบเดือน ระบบจะยิงข้อความ Care Mode ไปสะกิดแฟนคุณให้อัตโนมัตินะคะ 💕",
                quick_reply=get_calendar_quick_reply()
            )
        else:
            reply_msg = TextMessage(text="❌ รูปแบบ ID ไม่ถูกต้อง กรุณาเช็ก ID ของแฟนใหม่อีกครั้งนะคะ")

    elif user_text in ["ยกเลิกผูกแฟน", "unpair"]:
        unlink_partner(user_id)
        reply_msg = TextMessage(
            text="🗑️ ยกเลิกการผูกบัญชีกับแฟนเรียบร้อยแล้วค่ะ",
            quick_reply=get_calendar_quick_reply()
        )

    else:
        parsed_date, custom_cycle = parse_date_input(user_text)
        if parsed_date:
            reply_msg = process_and_reply(user_id, parsed_date, custom_cycle)
        else:
            reply_msg = TextMessage(
                text="ขออภัยค่ะ ระบบไม่เข้าใจคำสั่ง 🙏\n\n"
                     "📌 สามารถใช้งานได้ง่ายๆ โดยกดเลือกเมนูบน Rich Menu ด้านล่างได้เลยค่ะ",
                quick_reply=get_calendar_quick_reply()
            )

    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply_msg],
            )
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    postback_data = event.postback.data

    if postback_data == "action=select_date":
        selected_date_str = event.postback.params.get("date")
        if selected_date_str:
            start_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
            flex_message = process_and_reply(user_id, start_date)

            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message],
                    )
                )

    elif postback_data.startswith("action=set_remind"):
        days = int(postback_data.split("days=")[1])
        set_user_remind_days(user_id, days)

        logs = get_user_logs(user_id, limit=1)
        if logs:
            latest_date = datetime.strptime(logs[0]["start_date"], "%Y-%m-%d")
            avg_cycle = calculate_avg_cycle(user_id)
            next_period = latest_date + timedelta(days=avg_cycle)
            schedule_user_reminders(user_id, next_period)

        reply_msg = TextMessage(
            text=f"✅ ตั้งค่าเรียบร้อย! ระบบจะแจ้งเตือนล่วงหน้า {days} วัน ก่อนรอบเดือนถัดไปนะคะ 🌸",
            quick_reply=get_calendar_quick_reply()
        )
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply_msg],
                )
            )

    elif postback_data == "action=confirm_reset":
        reset_user_logs(user_id)
        for job_prefix in ["reminder_", "late_"]:
            job_id = f"{job_prefix}{user_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

        reply_msg = TextMessage(
            text="🧹 ล้างประวัติทั้งหมดเรียบร้อยแล้วค่ะ!\nคุณสามารถเริ่มบันทึกรอบเดือนใหม่ได้ทันทีนะคะ 😊",
            quick_reply=get_calendar_quick_reply()
        )
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply_msg],
                )
            )

    elif postback_data == "action=cancel_reset":
        reply_msg = TextMessage(
            text="❌ ยกเลิกการล้างข้อมูลเรียบร้อยแล้ว ข้อมูลของคุณยังปลอดภัยอยู่ค่ะ 🌸",
            quick_reply=get_calendar_quick_reply()
        )
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply_msg],
                )
            )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)