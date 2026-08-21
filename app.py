import logging
import os

from flask import Flask, abort, request
from linebot.v3.exceptions import InvalidSignatureError

# Nothing else in this codebase configures logging, so without a handler here
# every logger.info/.warning/.exception call (including APScheduler's own
# "job missed" / "error getting due jobs" warnings) has no reliable path to
# Render's captured output. Configure this before importing handlers, which
# imports scheduler and starts the background scheduler on import.
logging.basicConfig(level=logging.INFO)

import db
import handlers  # noqa: F401  (registers webhook event handlers on import)
import scheduler as scheduler_module
from config import handler

logger = logging.getLogger(__name__)

app = Flask(__name__)

try:
    db.init_db()
except Exception:
    logger.exception("Database Init Exception")


@app.route("/health", methods=["GET", "HEAD"])
def health():
    try:
        db.ping()
    except Exception:
        logger.exception("Health Check DB Ping Exception")
        return "DB unavailable", 503
    return "OK"


@app.route("/run-due-reminders", methods=["GET", "HEAD"])
def run_due_reminders():
    # BackgroundScheduler's own timer thread is paused (see scheduler.py) --
    # this is what actually fires due reminders now, meant to be hit every
    # few minutes by an external poller (e.g. UptimeRobot) instead.
    try:
        fired = scheduler_module.run_due_jobs()
    except Exception:
        logger.exception("run_due_jobs Exception")
        return "error", 503
    return f"fired {fired}", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
