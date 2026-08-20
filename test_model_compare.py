import os
import time

from google.genai import Client, errors, types

# Copied from ai_chat.py's SYSTEM_PROMPT — kept standalone here so this script
# only needs GEMINI_API_KEY, not the full app config (LINE/DB credentials).
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

API_KEY = os.getenv("GEMINI_API_KEY")
MODELS = ["gemini-3.6-flash", "gemini-3.1-flash-lite"]

TEST_PROMPTS = [
    "ปวดท้องประจำเดือนควรกินอะไรดี",
    "รอบเดือนหน้าจะมาวันไหน",
    "แนะนำร้านอาหารในกรุงเทพหน่อย",
    "ปวดท้องประจำเดือนมากๆ ควรกินยาอะไร",
]


def main():
    if not API_KEY:
        raise SystemExit("Set the GEMINI_API_KEY environment variable before running this script.")

    client = Client(api_key=API_KEY)

    for prompt in TEST_PROMPTS:
        print("=" * 70)
        print(f"คำถาม: {prompt}")
        print("=" * 70)
        for model in MODELS:
            start = time.monotonic()
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                )
                elapsed = time.monotonic() - start
                print(f"\n[{model}] ({elapsed:.2f}s)")
                print(response.text)
            except errors.APIError as e:
                elapsed = time.monotonic() - start
                print(f"\n[{model}] ({elapsed:.2f}s) ERROR code={e.code}: {e.message}")
        print()


if __name__ == "__main__":
    main()
