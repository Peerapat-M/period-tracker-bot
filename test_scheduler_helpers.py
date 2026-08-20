from datetime import datetime, timedelta

from config import BANGKOK_TZ
from scheduler import _resolve_run_date


def test_future_naive_datetime_keeps_its_value_with_bangkok_tz():
    future = datetime.now(BANGKOK_TZ).replace(tzinfo=None) + timedelta(days=1)
    resolved = _resolve_run_date(future)
    assert resolved.tzinfo == BANGKOK_TZ
    assert resolved.replace(tzinfo=None) == future


def test_past_naive_datetime_is_clamped_to_the_near_future():
    past = datetime.now(BANGKOK_TZ).replace(tzinfo=None) - timedelta(days=30)
    resolved = _resolve_run_date(past)
    now = datetime.now(BANGKOK_TZ)
    assert resolved > now
    assert (resolved - now).total_seconds() < 30
