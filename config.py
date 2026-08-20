import os
from zoneinfo import ZoneInfo

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# The bot's LINE Official Account basic ID (the "@..." handle), used to build
# oaMessage deep links that open a chat with this bot with text pre-filled.
LINE_OA_ID = os.getenv("LINE_OA_ID", "@569bwxwh")

# SQLAlchemy (used by the scheduler jobstore) requires the postgresql:// scheme.
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
