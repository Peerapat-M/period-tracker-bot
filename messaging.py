from datetime import datetime
from urllib.parse import quote

from linebot.v3.messaging import (
    ApiClient,
    DatetimePickerAction,
    FlexContainer,
    FlexMessage,
    MessageAction,
    MessagingApi,
    PostbackAction,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)

import db
from config import LINE_OA_ID, configuration


def build_pair_deep_link(user_id):
    prefilled_text = quote(f"pair {user_id}", safe="")
    return f"https://line.me/R/oaMessage/{LINE_OA_ID}/?{prefilled_text}"


# ----------------------------------------------------
# LINE API send helpers
# ----------------------------------------------------
def send_push(to, messages):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(PushMessageRequest(to=to, messages=messages))


def send_reply(reply_token, messages):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


# ----------------------------------------------------
# Quick Replies
# ----------------------------------------------------
def get_calendar_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=DatetimePickerAction(
                    label="📅 เลือกวันแรก",
                    data="action=select_date",
                    mode="date",
                    initial=datetime.now().strftime("%Y-%m-%d"),
                    max=datetime.now().strftime("%Y-%m-%d"),
                )
            ),
            QuickReplyItem(action=MessageAction(label="ดูประวัติ", text="ดูประวัติ")),
            QuickReplyItem(action=MessageAction(label="แชร์ให้แฟน", text="แชร์ให้แฟน")),
            QuickReplyItem(action=MessageAction(label="แจ้งเตือน", text="แจ้งเตือน")),
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
            QuickReplyItem(action=PostbackAction(label="❌ ยกเลิก", data="action=cancel_reset")),
        ]
    )


# ----------------------------------------------------
# Flex Messages
# ----------------------------------------------------
def _info_row(icon, label, value, value_color=None):
    value_text = {"type": "text", "text": value, "size": "sm", "weight": "bold", "align": "end", "flex": 3, "wrap": True}
    if value_color:
        value_text["color"] = value_color
    return {
        "type": "box", "layout": "horizontal", "margin": "md", "spacing": "sm",
        "contents": [
            {"type": "text", "text": icon, "size": "sm", "flex": 0},
            {"type": "text", "text": label, "size": "sm", "color": "#555555", "flex": 4, "wrap": True},
            value_text,
        ],
    }


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
                {"type": "text", "text": next_period.strftime("%d/%m/%Y"), "weight": "bold", "size": "xxl", "color": "#C71585", "margin": "sm"},
            ],
            "backgroundColor": "#FFF0F5",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                _info_row("🩸", "บันทึกวันแรกไว้ว่า", latest_date.strftime("%d/%m/%Y"), value_color="#C75B7A"),
                _info_row("🥚", "วันไข่ตกโดยประมาณ", ovulation.strftime("%d/%m/%Y"), value_color="#7E60BF"),
                _info_row(
                    "👶", "ช่วงมีโอกาสตั้งครรภ์",
                    f"{fertile_start.strftime('%d/%m')} - {fertile_end.strftime('%d/%m/%Y')}",
                    value_color="#D6336C",
                ),
                _info_row("🧪", "เริ่มตรวจครรภ์ได้ตั้งแต่", test_date.strftime("%d/%m/%Y"), value_color="#5E35B1"),
                {"type": "separator", "margin": "lg"},
                {"type": "text", "text": f"ℹ️ รอบเดือนเฉลี่ย {avg_cycle} วัน | เตือนล่วงหน้า {remind_days} วัน", "size": "xs", "color": "#888888", "wrap": True, "align": "center", "margin": "md"},
                {"type": "text", "text": "⚠️ เป็นเพียงการคาดการณ์ ควรใช้วิธีอื่นร่วมด้วยในการคุมกำเนิด", "size": "xs", "color": "#A8467A", "wrap": True, "align": "center", "margin": "xs"},
            ],
        },
    }
    return FlexMessage(
        alt_text="พยากรณ์รอบเดือน",
        contents=FlexContainer.from_dict(bubble_json),
        quick_reply=get_calendar_quick_reply(),
    )


def create_history_flex(user_id):
    logs = db.get_user_logs(user_id, limit=5)
    if not logs:
        return None

    avg_cycle = db.calculate_avg_cycle(user_id)

    history_contents = []
    for log in logs:
        dt = datetime.strptime(log["start_date"], "%Y-%m-%d")
        history_contents.append(_info_row("🩸", "ประจำเดือนมาวันแรก", dt.strftime("%d/%m/%Y"), value_color="#C75B7A"))

    bubble_json = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📋 ประวัติการบันทึกรอบเดือน", "weight": "bold", "color": "#D87093", "size": "md"},
                {"type": "text", "text": f"รอบเดือนเฉลี่ยปัจจุบัน: {avg_cycle} วัน", "size": "xs", "color": "#888888", "wrap": True, "margin": "xs"},
            ],
            "backgroundColor": "#FFF0F5",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": history_contents,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "💡 กดปุ่ม 'ลบรายการล่าสุด' บน Rich Menu เพื่อลบข้อมูลล่าสุด", "size": "xs", "color": "#888888", "wrap": True, "align": "center"},
            ],
        },
    }
    return FlexMessage(
        alt_text="ประวัติรอบเดือน",
        contents=FlexContainer.from_dict(bubble_json),
        quick_reply=get_calendar_quick_reply(),
    )


# ----------------------------------------------------
# Notifications
# ----------------------------------------------------
def send_period_reminder(user_id, next_period_str, days_before):
    user_msg = TextMessage(
        text=f"🔔 แจ้งเตือนล่วงหน้า\n\n"
             f"อีก {days_before} วันจะถึงกำหนดรอบเดือนถัดไปของคุณแล้วนะคะ! ({next_period_str})\n"
             f"อย่าลืมเตรียมพกผ้าอนามัยไว้ล่วงหน้านะคะ 🌸",
        quick_reply=get_calendar_quick_reply(),
    )
    try:
        send_push(user_id, [user_msg])
    except Exception as e:
        print(f"❌ ส่งแจ้งเตือนล้มเหลว: {e}")

    partner_id = db.get_partner_id(user_id)
    if not partner_id:
        return

    partner_msg = TextMessage(
        text=f"🌸 Care Mode แจ้งเตือนคนรัก\n\n"
             f"อีก {days_before} วันจะถึงกำหนดรอบเดือนของแฟนคุณแล้วนะคะ ({next_period_str})\n\n"
             f"💡 คำแนะนำในการดูแล:\n"
             f"• เตรียมกระเป๋าน้ำร้อนหรือเครื่องดื่มอุ่นๆ ไว้ให้\n"
             f"• ช่วยซัพพอร์ตและคอยเอาใจใส่เป็นพิเศษในช่วงนี้นะคะ 💕"
    )
    try:
        send_push(partner_id, [partner_msg])
    except Exception as e:
        print(f"❌ ส่ง Care Mode หาแฟนล้มเหลว: {e}")


def send_late_period_alert(user_id, next_period_str):
    msg = TextMessage(
        text=f"❓ ติดตามรอบเดือน\n\n"
             f"รอบเดือนของคุณคาดว่าจะมาตั้งแต่วันที่ {next_period_str} (เลทมา 2 วันแล้ว)\n"
             f"ประจำเดือนมาหรือยังคะ? สามารถกดบันทึกวันแรกผ่านปฏิทินได้เลยนะคะ 🌸",
        quick_reply=get_calendar_quick_reply(),
    )
    try:
        send_push(user_id, [msg])
    except Exception as e:
        print(f"❌ ส่งแจ้งเตือนรอบเดือนเลทล้มเหลว: {e}")
