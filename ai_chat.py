import logging
import time
from collections import deque

from google.genai import Client, errors, types

import db
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

FAST_MODEL = "gemini-3.1-flash-lite"
CAREFUL_MODEL = "gemini-3.6-flash"

# Topics where a wrong or careless answer matters most (found by testing:
# the fast model named specific drugs before the disclaimer) — route these
# to the slower but more reliable model instead of the fast default.
SENSITIVE_KEYWORDS = ["ยา", "รุนแรง", "หนัก", "ผิดปกติ", "อันตราย", "เสี่ยง"]

SYSTEM_PROMPT = (
    "คุณคือน้องบอท ผู้ช่วยตอบคำถามเกี่ยวกับประจำเดือน สุขภาพผู้หญิง และการตั้งครรภ์ในไลน์บอทติดตามรอบเดือน "
    "รวมถึงหัวข้อที่เกี่ยวข้อง เช่น การคุมกำเนิด/วางแผนครอบครัว อาหารที่ควรกินหรือควรหลีกเลี่ยง "
    "และการออกกำลังกายที่เหมาะสมในแต่ละช่วงของรอบเดือน/ตั้งครรภ์\n"
    "ตอบเป็นภาษาไทย ลงท้ายด้วยค่ะ/นะคะ น้ำเสียงอบอุ่นเป็นกันเอง กระชับ ไม่เกิน 4-5 บรรทัด\n\n"
    "ถ้าคำถามไม่เกี่ยวกับประจำเดือนหรือสุขภาพผู้หญิง ให้ตอบสุภาพว่าไม่สามารถช่วยเรื่องนี้ได้ "
    "และแนะนำให้กดเมนูของบอทแทน\n\n"
    "คุณไม่ใช่แพทย์ ห้ามวินิจฉัยโรค และห้ามเอ่ยชื่อยา ชื่อสารออกฤทธิ์ ยี่ห้อยา หรือกลุ่มยาใดๆ โดยเด็ดขาด "
    "(เช่น พาราเซตามอล, NSAIDs, ไอบูโพรเฟน) แม้จะบอกว่าให้ปรึกษาแพทย์ก่อนใช้ก็ตาม "
    "ให้แนะนำวิธีที่ไม่ใช่ยาแทน (เช่น การประคบอุ่น การพักผ่อน) "
    "หากจำเป็นต้องใช้ยาให้บอกว่าควรปรึกษาเภสัชกรหรือแพทย์เท่านั้น "
    "หากอาการรุนแรงหรือน่ากังวลให้แนะนำให้ไปพบแพทย์เสมอ\n\n"
    "ห้ามคำนวณหรือทำนายวันที่ของรอบเดือนถัดไป วันตกไข่ หรือวันไข่ตกเอง ถ้าผู้ใช้ถามเรื่องนี้ "
    "ให้แนะนำให้กดปุ่ม 'พยากรณ์ล่าสุด' ด้านล่าง หรือพิมพ์คำว่า 'พยากรณ์ล่าสุด' เพื่อดูวันที่คำนวณจากระบบแทน เพราะแม่นยำกว่า"
)

REQUEST_TIMEOUT_MS = 12000
DAILY_LIMIT_PER_USER = 20
GLOBAL_LIMIT_PER_MINUTE = 10

QUOTA_REACHED_MESSAGE = "วันนี้ถามน้องบอทครบโควตาแล้วนะคะ ลองใหม่พรุ่งนี้ได้เลยค่ะ 🌸"
BUSY_MESSAGE = "ขออภัยค่ะ ตอนนี้มีคนถามน้องบอทพร้อมกันเยอะ รบกวนลองพิมพ์คำถามใหม่อีกครั้งในอีกสักครู่นะคะ 🙏"

_client = (
    Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    if GEMINI_API_KEY
    else None
)

_recent_call_times = {FAST_MODEL: deque(), CAREFUL_MODEL: deque()}


def _is_sensitive_topic(user_text):
    return any(keyword in user_text for keyword in SENSITIVE_KEYWORDS)


def _global_limit_reached(model):
    now = time.monotonic()
    bucket = _recent_call_times[model]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    return len(bucket) >= GLOBAL_LIMIT_PER_MINUTE


def _try_model(model, user_text, system_instruction):
    if _global_limit_reached(model):
        return None

    _recent_call_times[model].append(time.monotonic())

    try:
        response = _client.models.generate_content(
            model=model,
            contents=user_text,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        return response.text
    except errors.APIError as e:
        logger.warning("Gemini API error on %s (code=%s): %s", model, e.code, e.message)
        return None
    except Exception:
        logger.exception("Unexpected error calling Gemini API on %s", model)
        return None


def get_ai_reply(user_id, user_text):
    if _client is None:
        return None

    if db.count_ai_requests_today(user_id) >= DAILY_LIMIT_PER_USER:
        return QUOTA_REACHED_MESSAGE

    logs = db.get_user_logs(user_id, limit=1)
    if logs:
        avg_cycle = db.calculate_avg_cycle(user_id)
        user_context = f"รอบเดือนล่าสุดของผู้ใช้เริ่มวันที่ {logs[0]['start_date']} รอบเฉลี่ย {avg_cycle} วัน"
    else:
        user_context = "ผู้ใช้ยังไม่มีประวัติการบันทึกรอบเดือน"

    system_instruction = f"{SYSTEM_PROMPT}\n\nข้อมูลผู้ใช้: {user_context}"

    if _is_sensitive_topic(user_text):
        model_order = (CAREFUL_MODEL, FAST_MODEL)
    else:
        model_order = (FAST_MODEL, CAREFUL_MODEL)

    for model in model_order:
        text = _try_model(model, user_text, system_instruction)
        if text:
            db.log_ai_request(user_id)
            return text

    return BUSY_MESSAGE
