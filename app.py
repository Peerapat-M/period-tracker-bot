import os

from flask import Flask, abort, request
from linebot.v3.exceptions import InvalidSignatureError

import db
import handlers  # noqa: F401  (registers webhook event handlers on import)
from config import handler

app = Flask(__name__)

try:
    db.init_db()
except Exception as e:
    print(f"Database Init Exception: {e}")


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
