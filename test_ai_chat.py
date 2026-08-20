import os

from google.genai import Client, errors, types

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"


def main():
    if not API_KEY:
        raise SystemExit("Set the GEMINI_API_KEY environment variable before running this script.")

    client = Client(api_key=API_KEY)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents="สวัสดีค่ะ ทดสอบระบบ",
            config=types.GenerateContentConfig(
                system_instruction="ตอบสั้นๆ เป็นภาษาไทยว่าได้ยินแล้ว",
            ),
        )
        print("✅ Gemini ตอบกลับสำเร็จ:")
        print(response.text)
    except errors.APIError as e:
        raise SystemExit(f"❌ Gemini API error (code={e.code}): {e.message}")


if __name__ == "__main__":
    main()
