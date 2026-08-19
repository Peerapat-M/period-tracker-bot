from datetime import datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

import db
from config import DATABASE_URL
from messaging import send_late_period_alert, send_period_reminder

scheduler = BackgroundScheduler(jobstores={"default": SQLAlchemyJobStore(url=DATABASE_URL)})
scheduler.start()


def _reminder_job_id(user_id):
    return f"reminder_{user_id}"


def _late_job_id(user_id):
    return f"late_{user_id}"


def schedule_user_reminders(user_id, next_period):
    remind_days = db.get_user_remind_days(user_id)
    next_period_str = next_period.strftime("%d/%m/%Y")

    reminder_date = next_period - timedelta(days=remind_days)
    reminder_datetime = datetime.combine(reminder_date, datetime.min.time()).replace(hour=9, minute=0)

    scheduler.add_job(
        send_period_reminder,
        "date",
        run_date=reminder_datetime,
        args=[user_id, next_period_str, remind_days],
        id=_reminder_job_id(user_id),
        replace_existing=True,
    )

    late_date = next_period + timedelta(days=2)
    late_datetime = datetime.combine(late_date, datetime.min.time()).replace(hour=10, minute=0)

    scheduler.add_job(
        send_late_period_alert,
        "date",
        run_date=late_datetime,
        args=[user_id, next_period_str],
        id=_late_job_id(user_id),
        replace_existing=True,
    )


def remove_user_reminders(user_id):
    for job_id in (_reminder_job_id(user_id), _late_job_id(user_id)):
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass
