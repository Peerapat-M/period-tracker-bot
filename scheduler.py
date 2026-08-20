from datetime import datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

import db
from config import BANGKOK_TZ, DATABASE_URL
from messaging import (
    send_fertile_window_alert,
    send_late_period_alert,
    send_period_reminder,
    send_test_date_alert,
)

scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=DATABASE_URL)},
    timezone=BANGKOK_TZ,
)
scheduler.start()


def _reminder_job_id(user_id):
    return f"reminder_{user_id}"


def _late_job_id(user_id):
    return f"late_{user_id}"


def _fertile_job_id(user_id):
    return f"fertile_{user_id}"


def _test_date_job_id(user_id):
    return f"test_date_{user_id}"


def _resolve_run_date(naive_datetime):
    # A short cycle combined with a large remind_days (or a start date logged
    # several days after it began) can push this into the past; APScheduler
    # silently drops jobs whose run_date has already passed, so clamp instead.
    aware = naive_datetime.replace(tzinfo=BANGKOK_TZ)
    now = datetime.now(BANGKOK_TZ)
    return aware if aware > now else now + timedelta(seconds=5)


def schedule_user_reminders(user_id, next_period, fertile_start, fertile_end, test_date):
    remind_days = db.get_user_remind_days(user_id)
    remind_hour = db.get_user_remind_hour(user_id)
    next_period_str = next_period.strftime("%d/%m/%Y")

    reminder_date = next_period - timedelta(days=remind_days)
    reminder_datetime = datetime.combine(reminder_date, datetime.min.time()).replace(hour=remind_hour, minute=0)

    scheduler.add_job(
        send_period_reminder,
        "date",
        run_date=_resolve_run_date(reminder_datetime),
        args=[user_id, next_period_str, remind_days],
        id=_reminder_job_id(user_id),
        replace_existing=True,
    )

    late_date = next_period + timedelta(days=2)
    late_datetime = datetime.combine(late_date, datetime.min.time()).replace(hour=remind_hour, minute=0)

    scheduler.add_job(
        send_late_period_alert,
        "date",
        run_date=_resolve_run_date(late_datetime),
        args=[user_id, next_period_str],
        id=_late_job_id(user_id),
        replace_existing=True,
    )

    fertile_datetime = datetime.combine(fertile_start, datetime.min.time()).replace(hour=remind_hour, minute=0)

    scheduler.add_job(
        send_fertile_window_alert,
        "date",
        run_date=_resolve_run_date(fertile_datetime),
        args=[user_id, fertile_start.strftime("%d/%m/%Y"), fertile_end.strftime("%d/%m/%Y")],
        id=_fertile_job_id(user_id),
        replace_existing=True,
    )

    test_date_datetime = datetime.combine(test_date, datetime.min.time()).replace(hour=remind_hour, minute=0)

    scheduler.add_job(
        send_test_date_alert,
        "date",
        run_date=_resolve_run_date(test_date_datetime),
        args=[user_id, test_date.strftime("%d/%m/%Y")],
        id=_test_date_job_id(user_id),
        replace_existing=True,
    )

    return remind_days


def remove_user_reminders(user_id):
    job_ids = (
        _reminder_job_id(user_id),
        _late_job_id(user_id),
        _fertile_job_id(user_id),
        _test_date_job_id(user_id),
    )
    for job_id in job_ids:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass
