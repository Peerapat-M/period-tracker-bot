import logging
import time
from collections import deque

from google.genai import Client, errors, types

import db
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = (
    "คุณคือน้องบอท ผู้ช่วยตอบคำถามเกี่ยวกับประจำเดือน สุขภาพผู้หญิง การตั้งครรภ์ "
    "และการคุมกำเนิด/วางแผนครอบครัวในไลน์บอทติดตามรอบเดือน\n"
    "ตอบเป็นภาษาไทย ลงท้ายด้วยค่ะ/นะคะ น้ำเสียงอบอุ่นเป็นกันเอง กระชับ ไม่เกิน 4-5 บรรทัด\n\n"
    "ถ้าคำถามไม่เกี่ยวกับประจำเดือนหรือสุขภาพผู้หญิง ให้ตอบสุภาพว่าไม่สามารถช่วยเรื่องนี้ได้ "
    "และแนะนำให้กดเมนูของบอทแทน\n\n"
    "คุณไม่ใช่แพทย์ ห้ามวินิจฉัยโรคหรือแนะนำยา หากอาการรุนแรงหรือน่ากังวลให้แนะนำให้ไปพบแพทย์เสมอ\n\n"
    "ห้ามคำนวณหรือทำนายวันที่ของรอบเดือนถัดไป วันตกไข่ หรือวันไข่ตกเอง ถ้าผู้ใช้ถามเรื่องนี้ "
    "ให้แนะนำให้กดปุ่ม 'ดูประวัติ' เพื่อดูวันที่คำนวณจากระบบแทน เพราะแม่นยำกว่า"
)

REQUEST_TIMEOUT_MS = 8000
DAILY_LIMIT_PER_USER = 10
GLOBAL_LIMIT_PER_MINUTE = 5

QUOTA_REACHED_MESSAGE = "วันนี้ถามน้องบอทครบโควตาแล้วนะคะ ลองใหม่พรุ่งนี้ได้เลยค่ะ 🌸"

_client = (
    Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    if GEMINI_API_KEY
    else None
)

_recent_call_times = deque()


def _global_limit_reached():
    now = time.monotonic()
    while _recent_call_times and now - _recent_call_times[0] > 60:
        _recent_call_times.popleft()
    return len(_recent_call_times) >= GLOBAL_LIMIT_PER_MINUTE


def get_ai_reply(user_id, user_text):
    if _client is None:
        return None

    if db.count_ai_requests_today(user_id) >= DAILY_LIMIT_PER_USER:
        return QUOTA_REACHED_MESSAGE

    if _global_limit_reached():
        return None

    logs = db.get_user_logs(user_id, limit=1)
    if logs:
        avg_cycle = db.calculate_avg_cycle(user_id)
        user_context = f"รอบเดือนล่าสุดของผู้ใช้เริ่มวันที่ {logs[0]['start_date']} รอบเฉลี่ย {avg_cycle} วัน"
    else:
        user_context = "ผู้ใช้ยังไม่มีประวัติการบันทึกรอบเดือน"

    _recent_call_times.append(time.monotonic())

    try:
        response = _client.models.generate_content(
            model=MODEL,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=f"{SYSTEM_PROMPT}\n\nข้อมูลผู้ใช้: {user_context}",
            ),
        )
        db.log_ai_request(user_id)
        return response.text
    except errors.APIError as e:
        logger.warning("Gemini API error (code=%s): %s", e.code, e.message)
        return None
    except Exception:
        logger.exception("Unexpected error calling Gemini API")
        return None
