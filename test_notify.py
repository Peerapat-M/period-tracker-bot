import os
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "JsgwYXflC6+dfFYEjJeFhNO82OyMl92RyP8Ci4/GqATRbL8ARe9avr9jRCpow/E+gyTuyBDKA9cBkUBAObiMezQp2veQeuBHs2NZ1/LVbjsOVjJfFnfem6btIO0ty+EQMngegAdMQpoWhdkijDoyHwdB04t89/1O/w1cDnyilFU=")
TARGET_USER_ID = "Ue1997aea6e3cea510c0f5f2a93084ffb"  # นำ User ID ของคุณมาใส่ตรงนี้

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

def send_test_notification():
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