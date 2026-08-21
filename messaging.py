import logging
from datetime import datetime, timedelta
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
from config import BANGKOK_TZ, LINE_OA_ID, MAX_PERIOD_LOG_BACKDATE_DAYS, configuration

logger = logging.getLogger(__name__)


def build_pair_deep_link(user_id):
    prefilled_text = quote(f"pair {user_id}", safe="")
    return f"https://line.me/R/oaMessage/{LINE_OA_ID}/?{prefilled_text}"


def format_thai_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")


# ----------------------------------------------------
# LINE API send helpers
# ----------------------------------------------------
def send_push(to, messages):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(PushMessageRequest(to=to, messages=messages))


def send_reply(reply_token, messages, fallback_to=None):
    """Reply via the reply token, falling back to a push message if it fails
    (e.g. the token expired while the server was cold-starting) so a slow
    first response still reaches the user instead of going out silently.

    Deliberately lets a failure of BOTH the reply and the fallback push
    propagate -- the caller is a webhook event handler, and an exception
    here is what keeps _dedupe_webhook_event from marking a totally failed
    delivery as done and stops it from being silently swallowed with no
    retry. (_safe_push below never raises itself, but its send_* callers
    do when a push fails, for the same reason -- run_due_jobs() relies on
    that to retry at the next poll instead of dropping the job.)
    """
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=messages)
            )
    except Exception:
        logger.exception("ตอบกลับด้วย reply token ล้มเหลว")
        if not fallback_to:
            raise
        send_push(fallback_to, messages)


def _safe_push(to, messages, failure_label):
    """Never raises -- callers decide what a failed push means for them (the
    send_* notification functions below raise so run_due_jobs() retries at
    the next poll instead of the job being dropped after a transient error).
    """
    try:
        send_push(to, messages)
        return True
    except Exception:
        logger.exception("ส่ง%sล้มเหลว", failure_label)
        return False


# ----------------------------------------------------
# Quick Replies
# ----------------------------------------------------
def get_calendar_quick_reply():
    now = datetime.now(BANGKOK_TZ)
    return QuickReply(
        items=[
            QuickReplyItem(
                action=DatetimePickerAction(
                    label="📅 เลือกวันแรก",
                    data="action=select_date",
                    mode="date",
                    initial=now.strftime("%Y-%m-%d"),
                    min=(now - timedelta(days=MAX_PERIOD_LOG_BACKDATE_DAYS)).strftime("%Y-%m-%d"),
                    max=now.strftime("%Y-%m-%d"),
                )
            ),
            QuickReplyItem(action=MessageAction(label="พยากรณ์ล่าสุด", text="พยากรณ์ล่าสุด")),
            QuickReplyItem(action=MessageAction(label="แชร์ให้แฟน", text="แชร์ให้แฟน")),
            QuickReplyItem(action=MessageAction(label="ตั้งค่าแจ้งเตือน", text="ตั้งค่าแจ้งเตือน")),
        ]
    )


def get_settings_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=DatetimePickerAction(
                    label="⏰ ตั้งเวลาแจ้งเตือน",
                    data="action=set_remind_hour",
                    mode="time",
                    initial="08:00",
                )
            ),
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


def get_confirm_delete_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(action=PostbackAction(label="⚠️ ยืนยันลบ", data="action=confirm_delete_last")),
            QuickReplyItem(action=PostbackAction(label="❌ ยกเลิก", data="action=cancel_delete_last")),
        ]
    )


def get_confirm_delete_specific_quick_reply(log_id):
    return QuickReply(
        items=[
            QuickReplyItem(action=PostbackAction(label="⚠️ ยืนยันลบ", data=f"action=confirm_delete_specific&id={log_id}")),
            QuickReplyItem(action=PostbackAction(label="❌ ยกเลิก", data="action=cancel_delete_last")),
        ]
    )


# ----------------------------------------------------
# Flex Messages
# ----------------------------------------------------
def _info_row(icon, label, value, value_color=None, action=None):
    value_text = {"type": "text", "text": value, "size": "sm", "weight": "bold", "align": "end", "flex": 3, "wrap": True}
    if value_color:
        value_text["color"] = value_color
    row = {
        "type": "box", "layout": "horizontal", "margin": "md", "spacing": "sm",
        "contents": [
            {"type": "text", "text": icon, "size": "sm", "flex": 0},
            {"type": "text", "text": label, "size": "sm", "color": "#555555", "flex": 4, "wrap": True},
            value_text,
        ],
    }
    if action:
        row["action"] = action
    return row


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
    logs = db.get_user_logs(user_id, limit=db.MAX_PERIOD_LOGS_PER_USER)
    if not logs:
        return None

    avg_cycle = db.calculate_avg_cycle(user_id, logs=logs)

    history_contents = []
    for log in logs:
        display_date = format_thai_date(log["start_date"])
        history_contents.append(
            _info_row(
                "🩸", "ประจำเดือนมาวันแรก", display_date, value_color="#C75B7A",
                action={
                    "type": "postback",
                    "label": "ลบรายการนี้",
                    "data": f"action=select_delete&id={log['id']}&date={log['start_date']}",
                    "displayText": f"เลือกลบรายการวันที่ {display_date}",
                },
            )
        )

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
                {"type": "text", "text": "💡 กดที่รายการด้านบนเพื่อลบรายการนั้นได้เลยค่ะ", "size": "xs", "color": "#888888", "wrap": True, "align": "center"},
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
    delivered = _safe_push(user_id, [user_msg], "แจ้งเตือน")

    partner_id = db.get_partner_id(user_id)
    if partner_id:
        partner_msg = TextMessage(
            text=f"🌸 Care Mode แจ้งเตือนคนรัก\n\n"
                 f"อีก {days_before} วันจะถึงกำหนดรอบเดือนของแฟนคุณแล้วนะคะ ({next_period_str})\n\n"
                 f"💡 คำแนะนำในการดูแล:\n"
                 f"• เตรียมกระเป๋าน้ำร้อนหรือเครื่องดื่มอุ่นๆ ไว้ให้\n"
                 f"• ช่วยซัพพอร์ตและคอยเอาใจใส่เป็นพิเศษในช่วงนี้นะคะ 💕"
        )
        delivered = _safe_push(partner_id, [partner_msg], "Care Mode หาแฟน") and delivered

    if not delivered:
        # Raising (instead of swallowing) is what makes run_due_jobs() leave
        # this job in place for a retry on the next poll rather than
        # dropping it as done -- see messaging.py's _safe_push.
        raise RuntimeError(f"send_period_reminder to {user_id} was not fully delivered")


def send_late_period_alert(user_id, next_period_str):
    msg = TextMessage(
        text=f"❓ ติดตามรอบเดือน\n\n"
             f"รอบเดือนของคุณคาดว่าจะมาตั้งแต่วันที่ {next_period_str} (เลทมา 2 วันแล้ว)\n"
             f"ประจำเดือนมาหรือยังคะ? สามารถกดบันทึกวันแรกผ่านปฏิทินได้เลยนะคะ 🌸",
        quick_reply=get_calendar_quick_reply(),
    )
    if not _safe_push(user_id, [msg], "แจ้งเตือนรอบเดือนเลท"):
        raise RuntimeError(f"send_late_period_alert to {user_id} was not delivered")


def send_fertile_window_alert(user_id, fertile_start_str, fertile_end_str):
    msg = TextMessage(
        text=f"🥚 ช่วงมีโอกาสตั้งครรภ์สูง\n\n"
             f"คาดว่าวันที่ {fertile_start_str} - {fertile_end_str} เป็นช่วงที่มีโอกาสตั้งครรภ์สูงนะคะ\n"
             f"หากกำลังวางแผนมีบุตรหรือคุมกำเนิด ควรวางแผนล่วงหน้าในช่วงนี้ค่ะ 🌸",
        quick_reply=get_calendar_quick_reply(),
    )
    if not _safe_push(user_id, [msg], "แจ้งเตือนช่วงไข่ตก"):
        raise RuntimeError(f"send_fertile_window_alert to {user_id} was not delivered")


def send_test_date_alert(user_id, test_date_str):
    msg = TextMessage(
        text=f"🧪 วันแนะนำเริ่มตรวจครรภ์\n\n"
             f"วันนี้ ({test_date_str}) เป็นวันที่แนะนำให้เริ่มตรวจครรภ์ได้แล้วนะคะ\n"
             f"หากผลตรวจไม่ชัดเจน ลองตรวจซ้ำอีกครั้งในอีกไม่กี่วันได้ค่ะ 🌸",
        quick_reply=get_calendar_quick_reply(),
    )
    if not _safe_push(user_id, [msg], "แจ้งเตือนวันตรวจครรภ์"):
        raise RuntimeError(f"send_test_date_alert to {user_id} was not delivered")
