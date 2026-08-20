import re
from datetime import datetime, timedelta

from linebot.v3.webhooks import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    TextMessageContent,
)

import ai_chat
import db
import messaging
import scheduler as scheduler_module
from config import BANGKOK_TZ, MAX_PERIOD_LOG_BACKDATE_DAYS, handler

MIN_PARTNER_ID_LENGTH = 10


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


def calculate_cycle_prediction(user_id, start_date, custom_cycle=None):
    if custom_cycle and 20 <= custom_cycle <= 45:
        avg_cycle = custom_cycle
    else:
        avg_cycle = db.calculate_avg_cycle(user_id)

    next_period = start_date + timedelta(days=avg_cycle)
    ovulation = next_period - timedelta(days=14)
    fertile_start = ovulation - timedelta(days=5)
    fertile_end = ovulation + timedelta(days=1)
    test_date = ovulation + timedelta(days=12)

    return avg_cycle, next_period, ovulation, fertile_start, fertile_end, test_date


def process_and_reply(user_id, start_date, custom_cycle=None):
    now = datetime.now(BANGKOK_TZ)
    if start_date.date() > now.date():
        return messaging.TextMessage(
            text="❌ ไม่สามารถบันทึกวันที่ในอนาคตได้ค่ะ กรุณาเลือกวันแรกของรอบเดือนที่ผ่านมาแล้วนะคะ",
            quick_reply=messaging.get_calendar_quick_reply(),
        )

    if start_date.date() < (now - timedelta(days=MAX_PERIOD_LOG_BACKDATE_DAYS)).date():
        return messaging.TextMessage(
            text="❌ ย้อนหลังได้ไม่เกิน 6 เดือนนะคะ กรุณาเลือกวันแรกของรอบเดือนที่ผ่านมาไม่นานนี้",
            quick_reply=messaging.get_calendar_quick_reply(),
        )

    db.save_period_log(user_id, start_date.strftime("%Y-%m-%d"))

    avg_cycle, next_period, ovulation, fertile_start, fertile_end, test_date = calculate_cycle_prediction(
        user_id, start_date, custom_cycle
    )

    remind_days = scheduler_module.schedule_user_reminders(
        user_id, next_period, fertile_start, fertile_end, test_date
    )

    return messaging.create_prediction_flex(
        start_date, next_period, ovulation, fertile_start, fertile_end, test_date, avg_cycle, remind_days
    )


def _reschedule_reminders(user_id):
    """Recompute predictions from the user's latest log and reschedule reminders.

    Returns True if a log existed to reschedule from, False otherwise.
    """
    logs = db.get_user_logs(user_id, limit=1)
    if not logs:
        return False

    latest_date = datetime.strptime(logs[0]["start_date"], "%Y-%m-%d")
    _, next_period, _, fertile_start, fertile_end, test_date = calculate_cycle_prediction(
        user_id, latest_date
    )
    scheduler_module.schedule_user_reminders(
        user_id, next_period, fertile_start, fertile_end, test_date
    )
    return True


def _reschedule_or_clear_reminders(user_id):
    if not _reschedule_reminders(user_id):
        scheduler_module.remove_user_reminders(user_id)


def _parse_postback_params(postback_data):
    return dict(p.split("=", 1) for p in postback_data.split("&"))


def show_latest_prediction(user_id):
    logs = db.get_user_logs(user_id, limit=1)
    if not logs:
        return messaging.TextMessage(
            text="ยังไม่พบประวัติการบันทึกค่ะ เลือกกด 'บันทึกรอบเดือน' เพื่อเริ่มบันทึกได้เลยนะคะ 😊",
            quick_reply=messaging.get_calendar_quick_reply(),
        )

    start_date = datetime.strptime(logs[0]["start_date"], "%Y-%m-%d")
    avg_cycle, next_period, ovulation, fertile_start, fertile_end, test_date = calculate_cycle_prediction(
        user_id, start_date
    )
    remind_days = db.get_user_remind_days(user_id)

    return messaging.create_prediction_flex(
        start_date, next_period, ovulation, fertile_start, fertile_end, test_date, avg_cycle, remind_days
    )


@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = (
        "สวัสดีค่ะ! ยินดีต้อนรับสู่ระบบบันทึกรอบเดือน 🌸\n\n"
        "คุณสามารถกดปุ่มเมนูด้านล่างเพื่อเริ่มใช้งานได้เลยนะคะ 😊"
    )
    messaging.send_reply(
        event.reply_token,
        [messaging.TextMessage(text=welcome_text, quick_reply=messaging.get_calendar_quick_reply())],
    )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    user_text_lower = user_text.lower()

    if user_text_lower in ["บันทึกรอบเดือน", "บันทึก", "เลือกวันจากปฏิทิน"]:
        reply_msg = messaging.TextMessage(
            text="🗓️ เลือกวันแรกของรอบเดือนล่าสุดผ่านปฏิทินด้านล่าง หรือพิมพ์ระบุวันที่ เช่น 01/08/2026 ได้เลยค่ะ",
            quick_reply=messaging.get_calendar_quick_reply(),
        )

    elif user_text_lower in ["พยากรณ์ล่าสุด", "ดูพยากรณ์", "พยากรณ์", "การ์ดล่าสุด"]:
        reply_msg = show_latest_prediction(user_id)

    elif user_text_lower in ["ดูประวัติ", "ประวัติ", "history", "เช็คประวัติ"]:
        history_flex = messaging.create_history_flex(user_id)
        if history_flex:
            reply_msg = history_flex
        else:
            reply_msg = messaging.TextMessage(
                text="ยังไม่พบประวัติการบันทึกค่ะ เลือกกด 'บันทึกรอบเดือน' เพื่อเริ่มบันทึกได้เลยนะคะ 😊",
                quick_reply=messaging.get_calendar_quick_reply(),
            )

    elif user_text_lower in ["แชร์ให้แฟน", "ผูกบัญชีแฟน", "partner", "care mode"]:
        partner_id = db.get_partner_id(user_id)
        if partner_id:
            reply_msg = messaging.TextMessage(
                text=f"💕 บัญชีของคุณผูกกับคนรักเรียบร้อยแล้ว!\n"
                     f"เมื่อถึงกำหนดเตือนล่วงหน้า น้องบอทจะส่งข้อความ Care Mode ไปหาแฟนให้อัตโนมัตินะคะ 😊\n\n"
                     f"หากต้องการยกเลิก ให้พิมพ์ว่า: 'ยกเลิกผูกแฟน'",
                quick_reply=messaging.get_calendar_quick_reply(),
            )
        else:
            pair_link = messaging.build_pair_deep_link(user_id)
            reply_msg = messaging.TextMessage(
                text=f"👩‍❤️‍👨 Care Mode แชร์ข้อมูลให้คนรัก\n\n"
                     f"กดส่งต่อ (Forward) ข้อความนี้ หรือแชร์ลิงก์ด้านล่างให้แฟนได้เลยนะคะ พอแฟนกดลิงก์ แชทกับน้องบอทจะเปิดขึ้นมาพร้อมข้อความผูกบัญชีให้พร้อมกดส่งเลยค่ะ:\n\n"
                     f"{pair_link}\n\n"
                     f"📌 หรือหากคุณได้ ID จากแฟนมาแล้ว ให้พิมพ์ตอบกลับมาในรูปแบบ: pair USER_ID",
                quick_reply=messaging.get_calendar_quick_reply(),
            )

    elif user_text_lower in ["แจ้งเตือน", "ตั้งค่าแจ้งเตือน", "ตั้งค่า", "settings"]:
        current_days = db.get_user_remind_days(user_id)
        current_hour = db.get_user_remind_hour(user_id)
        reply_msg = messaging.TextMessage(
            text=f"⚙️ ตั้งค่าการแจ้งเตือน\n\n"
                 f"ปัจจุบันน้องบอทจะเตือนล่วงหน้า {current_days} วัน (เวลา {current_hour:02d}:00 น.)\n"
                 f"ต้องการเปลี่ยนเป็นเตือนล่วงหน้ากี่วัน หรือปรับเวลาแจ้งเตือน เลือกด้านล่างได้เลยนะคะ:",
            quick_reply=messaging.get_settings_quick_reply(),
        )

    elif user_text_lower in ["ลบรายการล่าสุด", "ลบข้อมูล", "ลบ", "delete"]:
        latest_logs = db.get_user_logs(user_id, limit=1)
        if not latest_logs:
            reply_msg = messaging.TextMessage(text="ไม่พบข้อมูลให้ลบค่ะ 😊", quick_reply=messaging.get_calendar_quick_reply())
        else:
            latest_date_str = datetime.strptime(latest_logs[0]["start_date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            reply_msg = messaging.TextMessage(
                text=f"⚠️ คุณแน่ใจหรือไม่ว่าต้องการลบรายการล่าสุด (วันที่ {latest_date_str})?\n"
                     "การดำเนินการนี้ไม่สามารถย้อนกลับได้ค่ะ",
                quick_reply=messaging.get_confirm_delete_quick_reply(),
            )

    elif user_text_lower in ["รีเซ็ตประวัติ", "รีเซ็ต", "reset", "ล้างข้อมูล"]:
        reply_msg = messaging.TextMessage(
            text="⚠️ คุณแน่ใจหรือไม่ว่าต้องการล้างประวัติรอบเดือนทั้งหมด?\n"
                 "การดำเนินการนี้ไม่สามารถย้อนกลับได้ค่ะ",
            quick_reply=messaging.get_confirm_reset_quick_reply(),
        )

    elif user_text_lower.startswith("pair "):
        target_partner_id = user_text[5:].strip()
        if target_partner_id == user_id:
            reply_msg = messaging.TextMessage(text="❌ ไม่สามารถผูกบัญชีกับตัวเองได้ค่ะ กรุณาส่ง ID ของแฟนมาแทนนะคะ")
        elif target_partner_id and len(target_partner_id) > MIN_PARTNER_ID_LENGTH:
            # target_partner_id is the person being tracked (who shared their ID);
            # user_id (whoever sent this "pair" message) becomes their notified partner.
            db.link_partner(target_partner_id, user_id)
            reply_msg = messaging.TextMessage(
                text="🎉 ผูกบัญชีกับคนรักเรียบร้อยแล้วค่ะ!\n"
                     "เมื่อถึงกำหนดเตือนรอบเดือนของแฟนคุณ น้องบอทจะส่งข้อความ Care Mode มาสะกิดให้อัตโนมัตินะคะ 💕",
                quick_reply=messaging.get_calendar_quick_reply(),
            )
        else:
            reply_msg = messaging.TextMessage(text="❌ รูปแบบ ID ไม่ถูกต้อง กรุณาเช็ก ID ของแฟนใหม่อีกครั้งนะคะ")

    elif user_text_lower in ["ยกเลิกผูกแฟน", "unpair"]:
        db.unlink_partner(user_id)
        reply_msg = messaging.TextMessage(
            text="🗑️ ยกเลิกการผูกบัญชีกับแฟนเรียบร้อยแล้วค่ะ",
            quick_reply=messaging.get_calendar_quick_reply(),
        )

    else:
        parsed_date, custom_cycle = parse_date_input(user_text)
        if parsed_date:
            reply_msg = process_and_reply(user_id, parsed_date, custom_cycle)
        else:
            ai_reply = ai_chat.get_ai_reply(user_id, user_text)
            if ai_reply:
                reply_msg = messaging.TextMessage(
                    text=ai_reply,
                    quick_reply=messaging.get_calendar_quick_reply(),
                )
            else:
                reply_msg = messaging.TextMessage(
                    text="ขออภัยค่ะ น้องบอทไม่เข้าใจคำสั่ง 🙏\n\n"
                         "📌 สามารถใช้งานได้ง่ายๆ โดยกดเลือกเมนูบน Rich Menu ด้านล่างได้เลยค่ะ",
                    quick_reply=messaging.get_calendar_quick_reply(),
                )

    messaging.send_reply(event.reply_token, [reply_msg])


@handler.add(MessageEvent)
def handle_unsupported_message(event):
    reply_msg = messaging.TextMessage(
        text="ขออภัยค่ะ ตอนนี้น้องบอทยังไม่รองรับข้อความประเภทนี้ 🙏\n\n"
             "📌 สามารถใช้งานได้ง่ายๆ โดยกดเลือกเมนูบน Rich Menu ด้านล่างได้เลยค่ะ",
        quick_reply=messaging.get_calendar_quick_reply(),
    )
    messaging.send_reply(event.reply_token, [reply_msg])


@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    postback_data = event.postback.data

    if postback_data == "action=select_date":
        selected_date_str = event.postback.params.get("date")
        if not selected_date_str:
            return
        start_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
        flex_message = process_and_reply(user_id, start_date)
        messaging.send_reply(event.reply_token, [flex_message])

    elif postback_data == "action=set_remind_hour":
        selected_time_str = event.postback.params.get("time")
        if not selected_time_str:
            return
        hour = int(selected_time_str.split(":")[0])
        db.set_user_remind_hour(user_id, hour)
        _reschedule_reminders(user_id)

        reply_msg = messaging.TextMessage(
            text=f"✅ ตั้งค่าเรียบร้อย! น้องบอทจะแจ้งเตือนเวลา {hour:02d}:00 น. นะคะ 🌸",
            quick_reply=messaging.get_calendar_quick_reply(),
        )
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data.startswith("action=set_remind"):
        days = int(postback_data.split("days=")[1])
        db.set_user_remind_days(user_id, days)
        _reschedule_reminders(user_id)

        reply_msg = messaging.TextMessage(
            text=f"✅ ตั้งค่าเรียบร้อย! น้องบอทจะแจ้งเตือนล่วงหน้า {days} วัน ก่อนรอบเดือนถัดไปนะคะ 🌸",
            quick_reply=messaging.get_calendar_quick_reply(),
        )
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data == "action=confirm_delete_last":
        if db.delete_last_log(user_id):
            _reschedule_or_clear_reminders(user_id)
            reply_msg = messaging.TextMessage(
                text="ลบรายการล่าสุดเรียบร้อยแล้วค่ะ 🗑️\nกดปุ่ม 'ดูประวัติ' เพื่อดูรายการที่เหลือได้เลยนะคะ",
                quick_reply=messaging.get_calendar_quick_reply(),
            )
        else:
            reply_msg = messaging.TextMessage(text="ไม่พบข้อมูลให้ลบค่ะ 😊", quick_reply=messaging.get_calendar_quick_reply())
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data == "action=cancel_delete_last":
        reply_msg = messaging.TextMessage(
            text="❌ ยกเลิกการลบข้อมูลเรียบร้อยแล้ว ข้อมูลของคุณยังปลอดภัยอยู่ค่ะ 🌸",
            quick_reply=messaging.get_calendar_quick_reply(),
        )
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data.startswith("action=select_delete"):
        params = _parse_postback_params(postback_data)
        display_date = datetime.strptime(params["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
        reply_msg = messaging.TextMessage(
            text=f"⚠️ คุณแน่ใจหรือไม่ว่าต้องการลบรายการวันที่ {display_date}?\n"
                 "การดำเนินการนี้ไม่สามารถย้อนกลับได้ค่ะ",
            quick_reply=messaging.get_confirm_delete_specific_quick_reply(params["id"]),
        )
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data.startswith("action=confirm_delete_specific"):
        params = _parse_postback_params(postback_data)
        if db.delete_log_by_id(user_id, int(params["id"])):
            _reschedule_or_clear_reminders(user_id)
            reply_msg = messaging.TextMessage(
                text="ลบรายการเรียบร้อยแล้วค่ะ 🗑️\nกดปุ่ม 'ดูประวัติ' เพื่อดูรายการที่เหลือได้เลยนะคะ",
                quick_reply=messaging.get_calendar_quick_reply(),
            )
        else:
            reply_msg = messaging.TextMessage(
                text="ไม่พบข้อมูลรายการนี้ค่ะ อาจถูกลบไปแล้ว",
                quick_reply=messaging.get_calendar_quick_reply(),
            )
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data == "action=confirm_reset":
        db.reset_user_logs(user_id)
        scheduler_module.remove_user_reminders(user_id)

        reply_msg = messaging.TextMessage(
            text="🧹 ล้างประวัติทั้งหมดเรียบร้อยแล้วค่ะ!\nคุณสามารถเริ่มบันทึกรอบเดือนใหม่ได้ทันทีนะคะ 😊",
            quick_reply=messaging.get_calendar_quick_reply(),
        )
        messaging.send_reply(event.reply_token, [reply_msg])

    elif postback_data == "action=cancel_reset":
        reply_msg = messaging.TextMessage(
            text="❌ ยกเลิกการล้างข้อมูลเรียบร้อยแล้ว ข้อมูลของคุณยังปลอดภัยอยู่ค่ะ 🌸",
            quick_reply=messaging.get_calendar_quick_reply(),
        )
        messaging.send_reply(event.reply_token, [reply_msg])
