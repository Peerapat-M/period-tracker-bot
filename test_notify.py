import os

from linebot.v3.messaging import TextMessage

from config import CHANNEL_ACCESS_TOKEN
from messaging import send_push

TARGET_USER_ID = os.getenv("TEST_USER_ID")


def send_test_notification():
    if not CHANNEL_ACCESS_TOKEN or not TARGET_USER_ID:
        raise SystemExit(
            "Set LINE_CHANNEL_ACCESS_TOKEN and TEST_USER_ID environment variables before running this script."
        )

    msg = TextMessage(text="🔔 [ทดสอบการแจ้งเตือน]\nประจำเดือนของคุณคาดว่าจะมาในอีก 3 วันข้างหน้านะครับ! 🌸")
    send_push(TARGET_USER_ID, [msg])
    print("✅ ส่งข้อความแจ้งเตือนสำเร็จแล้ว!")


if __name__ == "__main__":
    send_test_notification()
