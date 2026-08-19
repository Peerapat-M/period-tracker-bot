from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DATABASE_URL


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id TEXT PRIMARY KEY,
                    remind_days_before INTEGER DEFAULT 3
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS partners (
                    user_id TEXT PRIMARY KEY,
                    partner_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------
# Period Logs
# ----------------------------------------------------
def save_period_log(user_id, start_date_str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO period_logs (user_id, start_date) VALUES (%s, %s)",
                (user_id, start_date_str),
            )
            conn.commit()
    finally:
        conn.close()


def get_user_logs(user_id, limit=5):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, start_date FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT %s",
                (user_id, limit),
            )
            return cur.fetchall()
    finally:
        conn.close()


def delete_last_log(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM period_logs WHERE user_id = %s ORDER BY start_date DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return False
            cur.execute("DELETE FROM period_logs WHERE id = %s", (row["id"],))
            conn.commit()
        return True
    finally:
        conn.close()


def reset_user_logs(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM period_logs WHERE user_id = %s", (user_id,))
            conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------
# User Settings
# ----------------------------------------------------
def get_user_remind_days(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT remind_days_before FROM user_settings WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        return row["remind_days_before"] if row else 3
    finally:
        conn.close()


def set_user_remind_days(user_id, days):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_settings (user_id, remind_days_before) VALUES (%s, %s)
                ON CONFLICT(user_id) DO UPDATE SET remind_days_before = EXCLUDED.remind_days_before
                """,
                (user_id, days),
            )
            conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------
# Partner Sync
# ----------------------------------------------------
def link_partner(user_id, partner_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO partners (user_id, partner_id) VALUES (%s, %s)
                ON CONFLICT(user_id) DO UPDATE SET partner_id = EXCLUDED.partner_id
                """,
                (user_id, partner_id),
            )
            conn.commit()
    finally:
        conn.close()


def get_partner_id(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT partner_id FROM partners WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        return row["partner_id"] if row else None
    finally:
        conn.close()


def unlink_partner(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM partners WHERE user_id = %s", (user_id,))
            conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------
# Calculations
# ----------------------------------------------------
def calculate_avg_cycle(user_id):
    logs = get_user_logs(user_id, limit=5)
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

    return int(round(sum(gaps) / len(gaps)))
