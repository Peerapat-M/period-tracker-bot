import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from statistics import median

import psycopg2
from psycopg2.extras import RealDictCursor

from config import BANGKOK_TZ, DATABASE_URL

logger = logging.getLogger(__name__)

# calculate_avg_cycle only ever looks at this many recent cycles, so there's
# no point keeping more than that in storage per user.
MAX_PERIOD_LOGS_PER_USER = 6


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


@contextmanager
def _cursor(commit=False):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


def ping():
    """Trivial round-trip used by the /health endpoint to keep both the app
    and a free-tier Postgres instance from being treated as idle."""
    with _cursor() as cur:
        cur.execute("SELECT 1")


def _init_period_logs(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS period_logs (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Supabase auto-exposes every public-schema table over its REST API;
    # without RLS enabled, anyone with the project's anon key can read or
    # write these rows directly, bypassing this app entirely. The app
    # itself connects as the `postgres` role (or `postgres.<ref>` via
    # the Supavisor pooler), which bypasses RLS, so this has no effect
    # on the app's own access -- it only locks out the public API.
    cur.execute("ALTER TABLE period_logs ENABLE ROW LEVEL SECURITY")
    # A retried webhook delivery (see handlers._dedupe_webhook_event) can
    # re-run save_period_log for a cycle it already recorded. Collapse
    # any duplicates already on disk before adding the constraint below
    # (which would otherwise fail to create if any still exist), then
    # rely on it going forward so the retry's INSERT becomes a no-op.
    # Once the index exists it's the only thing checked on every later
    # cold start, so this one-time cleanup doesn't rescan the table.
    cur.execute("SELECT to_regclass('period_logs_user_start_date_idx') IS NULL AS needs_migration")
    if cur.fetchone()["needs_migration"]:
        cur.execute(
            """
            DELETE FROM period_logs a
            USING period_logs b
            WHERE a.user_id = b.user_id
            AND a.start_date = b.start_date
            AND a.id > b.id
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS period_logs_user_start_date_idx
            ON period_logs (user_id, start_date)
            """
        )


def _init_user_settings(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            remind_days_before INTEGER DEFAULT 3,
            remind_hour INTEGER DEFAULT 8
        )
        """
    )
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS remind_hour INTEGER DEFAULT 8")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS remind_minute INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY")


def _init_partners(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS partners (
            user_id TEXT PRIMARY KEY,
            partner_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("ALTER TABLE partners ENABLE ROW LEVEL SECURITY")


def _init_ai_usage_log(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage_log (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("ALTER TABLE ai_usage_log ENABLE ROW LEVEL SECURITY")


def _harden_apscheduler_jobs_rls(cur):
    # Owned by APScheduler's SQLAlchemyJobStore (scheduler.py), not this
    # module -- guarded with IF EXISTS since it's only guaranteed to
    # exist because scheduler.py runs before init_db() in app.py's
    # import order, not by anything db.py controls itself.
    cur.execute("ALTER TABLE IF EXISTS apscheduler_jobs ENABLE ROW LEVEL SECURITY")


def init_db():
    # Each step commits in its own transaction and a failure in one is
    # caught and logged here rather than propagating -- otherwise a single
    # failing statement (e.g. one ALTER TABLE) would, in one shared
    # transaction, roll back every CREATE TABLE that ran before it, and
    # app.py's own try/except around init_db() would swallow that with just
    # a log line, leaving the app serving requests against a schema-less DB.
    for description, step in (
        ("period_logs", _init_period_logs),
        ("user_settings", _init_user_settings),
        ("partners", _init_partners),
        ("ai_usage_log", _init_ai_usage_log),
        ("apscheduler_jobs RLS", _harden_apscheduler_jobs_rls),
    ):
        try:
            with _cursor(commit=True) as cur:
                step(cur)
        except Exception:
            logger.exception("DB init step failed, continuing with the rest: %s", description)


# ----------------------------------------------------
# Period Logs
# ----------------------------------------------------
def save_period_log(user_id, start_date_str):
    with _cursor(commit=True) as cur:
        # ON CONFLICT DO NOTHING makes this idempotent: a webhook retry of an
        # already-saved cycle (e.g. after send_reply's fallback push also
        # failed, see messaging.send_reply) re-runs this call but must not
        # insert a second row for the same cycle.
        cur.execute(
            """
            INSERT INTO period_logs (user_id, start_date) VALUES (%s, %s)
            ON CONFLICT (user_id, start_date) DO NOTHING
            """,
            (user_id, start_date_str),
        )
        cur.execute(
            """
            DELETE FROM period_logs
            WHERE user_id = %s
            AND id NOT IN (
                SELECT id FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT %s
            )
            """,
            (user_id, user_id, MAX_PERIOD_LOGS_PER_USER),
        )


def get_user_logs(user_id, limit=5):
    with _cursor() as cur:
        cur.execute(
            "SELECT id, start_date FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT %s",
            (user_id, limit),
        )
        return cur.fetchall()


def delete_last_log(user_id):
    with _cursor(commit=True) as cur:
        cur.execute(
            "SELECT id FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("DELETE FROM period_logs WHERE id = %s", (row["id"],))
    return True


def delete_log_by_id(user_id, log_id):
    with _cursor(commit=True) as cur:
        cur.execute("DELETE FROM period_logs WHERE id = %s AND user_id = %s", (log_id, user_id))
        deleted = cur.rowcount > 0
    return deleted


def reset_user_logs(user_id):
    with _cursor(commit=True) as cur:
        cur.execute("DELETE FROM period_logs WHERE user_id = %s", (user_id,))


# ----------------------------------------------------
# User Settings
# ----------------------------------------------------
def _get_user_setting(user_id, column, default):
    # column is always one of this module's own hardcoded literals below,
    # never external input, so interpolating it into the SQL is safe.
    with _cursor() as cur:
        cur.execute(f"SELECT {column} FROM user_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    value = row[column] if row else None
    return value if value is not None else default


def _set_user_setting(user_id, column, value):
    with _cursor(commit=True) as cur:
        cur.execute(
            f"""
            INSERT INTO user_settings (user_id, {column}) VALUES (%s, %s)
            ON CONFLICT(user_id) DO UPDATE SET {column} = EXCLUDED.{column}
            """,
            (user_id, value),
        )


def get_user_remind_days(user_id):
    return _get_user_setting(user_id, "remind_days_before", 3)


def set_user_remind_days(user_id, days):
    _set_user_setting(user_id, "remind_days_before", days)


def get_user_remind_hour(user_id):
    return _get_user_setting(user_id, "remind_hour", 8)


def set_user_remind_hour(user_id, hour):
    _set_user_setting(user_id, "remind_hour", hour)


def get_user_remind_minute(user_id):
    return _get_user_setting(user_id, "remind_minute", 0)


def set_user_remind_minute(user_id, minute):
    _set_user_setting(user_id, "remind_minute", minute)


def get_user_reminder_settings(user_id):
    """Fetch remind_days_before, remind_hour, and remind_minute in one
    round trip, for callers (scheduler.schedule_user_reminders, the
    settings menu) that always need all three together."""
    with _cursor() as cur:
        cur.execute(
            "SELECT remind_days_before, remind_hour, remind_minute FROM user_settings WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    remind_days = row["remind_days_before"] if row and row["remind_days_before"] is not None else 3
    remind_hour = row["remind_hour"] if row and row["remind_hour"] is not None else 8
    remind_minute = row["remind_minute"] if row and row["remind_minute"] is not None else 0
    return remind_days, remind_hour, remind_minute


# ----------------------------------------------------
# Partner Sync
# ----------------------------------------------------
def link_partner(user_id, partner_id):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO partners (user_id, partner_id) VALUES (%s, %s)
            ON CONFLICT(user_id) DO UPDATE SET partner_id = EXCLUDED.partner_id
            """,
            (user_id, partner_id),
        )


def get_partner_id(user_id):
    with _cursor() as cur:
        cur.execute("SELECT partner_id FROM partners WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    return row["partner_id"] if row else None


def unlink_partner(user_id):
    with _cursor(commit=True) as cur:
        cur.execute("DELETE FROM partners WHERE user_id = %s", (user_id,))


# ----------------------------------------------------
# AI Usage
# ----------------------------------------------------
def _bangkok_day_boundary_utc():
    # ai_usage_log.created_at is a naive TIMESTAMP written by Postgres's
    # CURRENT_TIMESTAMP (server/session tz, effectively UTC here since
    # nothing sets a session timezone) -- comparing it against bare
    # CURRENT_DATE would key the daily quota to the UTC day instead of the
    # Bangkok day every other date boundary in this app uses.
    now_bkk = datetime.now(BANGKOK_TZ)
    midnight_bkk = now_bkk.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_bkk.astimezone(timezone.utc).replace(tzinfo=None)


def count_ai_requests_today(user_id):
    with _cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS count FROM ai_usage_log WHERE user_id = %s AND created_at >= %s",
            (user_id, _bangkok_day_boundary_utc()),
        )
        return cur.fetchone()["count"]


def log_ai_request(user_id):
    with _cursor(commit=True) as cur:
        # The quota check only ever looks at today's (Bangkok) rows, so
        # anything older is dead weight — clear it out here instead of a
        # separate job.
        cur.execute("DELETE FROM ai_usage_log WHERE created_at < %s", (_bangkok_day_boundary_utc(),))
        cur.execute("INSERT INTO ai_usage_log (user_id) VALUES (%s)", (user_id,))


# ----------------------------------------------------
# Calculations
# ----------------------------------------------------
def calculate_avg_cycle(user_id, logs=None):
    if logs is None:
        logs = get_user_logs(user_id, limit=MAX_PERIOD_LOGS_PER_USER)
    if len(logs) < 2:
        return 28

    dates = sorted(datetime.strptime(log["start_date"], "%Y-%m-%d") for log in logs)

    gaps = [
        (dates[i] - dates[i - 1]).days
        for i in range(1, len(dates))
        if 20 <= (dates[i] - dates[i - 1]).days <= 45
    ]

    if not gaps:
        return 28

    return int(round(median(gaps)))
