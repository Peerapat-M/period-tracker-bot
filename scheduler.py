import logging
from datetime import datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
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

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    jobstores={
        # pool_pre_ping: reminders can be scheduled hours or days out, and
        # DATABASE_URL now points at Supabase's transaction-mode pooler,
        # which can drop an idle backend connection between two jobstore
        # calls that far apart. Without this, the next call reuses the dead
        # pooled connection and raises OperationalError, which APScheduler
        # doesn't retry -- pool_pre_ping tests and transparently replaces it
        # instead.
        #
        # keepalives: pool_pre_ping's own test query can itself hang instead
        # of failing fast when the pooler has dropped the connection as a
        # half-open TCP socket (no RST/FIN sent) -- the scheduler's background
        # thread is single-threaded, so one hung pre-ping call there freezes
        # every job, forever, with nothing logged. These make the OS notice
        # the dead peer and error out within ~50s instead of hanging.
        "default": SQLAlchemyJobStore(
            url=DATABASE_URL,
            engine_options={
                "pool_pre_ping": True,
                "connect_args": {
                    "keepalives": 1,
                    "keepalives_idle": 10,
                    "keepalives_interval": 10,
                    "keepalives_count": 3,
                },
            },
        ),
    },
    job_defaults={
        # APScheduler's default grace time is 1 second: if the run_date is
        # missed by more than that, the job is silently dropped instead of
        # run late. This process sleeps on Render's free tier between
        # requests, so a reminder due while asleep is often minutes to hours
        # overdue by the time a webhook or health check wakes it back up --
        # widen the window so it still fires (a bit late) instead of vanishing.
        "misfire_grace_time": 24 * 3600,
    },
    timezone=BANGKOK_TZ,
)


def _log_job_event(event):
    # A job that's due but doesn't run leaves no trace anywhere else -- this
    # is what would have surfaced today's misfire/cold-start issue immediately
    # instead of needing a live debugging session to notice.
    if event.code == EVENT_JOB_MISSED:
        logger.warning("Job %s missed its scheduled run at %s", event.job_id, event.scheduled_run_time)
    else:
        logger.error("Job %s raised an exception: %s", event.job_id, event.exception)


scheduler.add_listener(_log_job_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

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
    remind_days, remind_hour, remind_minute = db.get_user_reminder_settings(user_id)
    next_period_str = next_period.strftime("%d/%m/%Y")

    def _at(date_obj):
        return datetime.combine(date_obj, datetime.min.time()).replace(hour=remind_hour, minute=remind_minute)

    jobs = (
        (
            _reminder_job_id(user_id),
            send_period_reminder,
            _at(next_period - timedelta(days=remind_days)),
            [user_id, next_period_str, remind_days],
        ),
        (
            _late_job_id(user_id),
            send_late_period_alert,
            _at(next_period + timedelta(days=2)),
            [user_id, next_period_str],
        ),
        (
            _fertile_job_id(user_id),
            send_fertile_window_alert,
            _at(fertile_start),
            [user_id, fertile_start.strftime("%d/%m/%Y"), fertile_end.strftime("%d/%m/%Y")],
        ),
        (
            _test_date_job_id(user_id),
            send_test_date_alert,
            _at(test_date),
            [user_id, test_date.strftime("%d/%m/%Y")],
        ),
    )

    for job_id, func, run_datetime, args in jobs:
        scheduler.add_job(
            func,
            "date",
            run_date=_resolve_run_date(run_datetime),
            args=args,
            id=job_id,
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
