import os
from unittest.mock import patch

os.environ.setdefault("LINE_CHANNEL_SECRET", "test-secret")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

# scheduler.py starts a real APScheduler BackgroundScheduler backed by
# Postgres as soon as it's imported (module-level `scheduler.start()`), and
# handlers.py imports it too. Stub out .start() for this one warm-up import
# so the test suite never needs a live database; once cached in
# sys.modules, later `import scheduler` / `import handlers` in test files
# just reuse this same (never-actually-started) instance.
with patch("apscheduler.schedulers.background.BackgroundScheduler.start", lambda self, *a, **k: None):
    import scheduler  # noqa: F401
    import handlers  # noqa: F401
    import ai_chat  # noqa: F401
    import messaging  # noqa: F401
