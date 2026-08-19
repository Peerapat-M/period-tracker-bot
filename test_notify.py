import os
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
TARGET_USER_ID = os.getenv("TEST_USER_ID")

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

def send_test_notification():
    if not CHANNEL_ACCESS_TOKEN or not TARGET_USER_ID:
        raise SystemExit(
            "Set LINE_CHANNEL_ACCESS_TOKEN and TEST_USER_ID environment variables before running this script."
        )

    msg = TextMessage(text="🔔 [ทดสอบการแจ้งเตือน]\nประจำเดือนของคุณคาดว่าจะมาในอีก 3 วันข้างหน้านะครับ! 🌸")
    
    with ApiClient(configuration) as api_client:
        api_instance = MessagingApi(api_client)
        push_message_request = PushMessageRequest(
            to=TARGET_USER_ID,
            messages=[msg]
        )
        api_instance.push_message(push_message_request)
        print("✅ ส่งข้อความแจ้งเตือนสำเร็จแล้ว!")

if __name__ == "__main__":
    send_test_notification()