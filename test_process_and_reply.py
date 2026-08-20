from datetime import datetime, timedelta
from unittest.mock import patch

from linebot.v3.messaging import FlexMessage, TextMessage

import handlers
from config import BANGKOK_TZ, MAX_PERIOD_LOG_BACKDATE_DAYS


def _today():
    return datetime.now(BANGKOK_TZ).replace(tzinfo=None)


def test_rejects_a_future_start_date():
    with patch.object(handlers.db, "save_period_log") as mock_save:
        result = handlers.process_and_reply("u1", _today() + timedelta(days=1))
    assert isinstance(result, TextMessage)
    assert "อนาคต" in result.text
    mock_save.assert_not_called()


def test_rejects_a_start_date_older_than_the_backdate_window():
    too_old = _today() - timedelta(days=MAX_PERIOD_LOG_BACKDATE_DAYS + 1)
    with patch.object(handlers.db, "save_period_log") as mock_save:
        result = handlers.process_and_reply("u1", too_old)
    assert isinstance(result, TextMessage)
    assert "6 เดือน" in result.text
    mock_save.assert_not_called()


def test_accepts_a_start_date_exactly_at_the_backdate_boundary():
    boundary = _today() - timedelta(days=MAX_PERIOD_LOG_BACKDATE_DAYS)
    with patch.object(handlers.db, "save_period_log") as mock_save, \
         patch.object(handlers.db, "calculate_avg_cycle", return_value=28), \
         patch.object(handlers.scheduler_module, "schedule_user_reminders", return_value=3):
        result = handlers.process_and_reply("u1", boundary)
    mock_save.assert_called_once_with("u1", boundary.strftime("%Y-%m-%d"))
    assert isinstance(result, FlexMessage)


def test_accepts_todays_date_and_saves_the_log():
    today = _today()
    with patch.object(handlers.db, "save_period_log") as mock_save, \
         patch.object(handlers.db, "calculate_avg_cycle", return_value=28), \
         patch.object(handlers.scheduler_module, "schedule_user_reminders", return_value=3) as mock_schedule:
        result = handlers.process_and_reply("u1", today)

    mock_save.assert_called_once_with("u1", today.strftime("%Y-%m-%d"))
    mock_schedule.assert_called_once()
    assert isinstance(result, FlexMessage)


def test_valid_custom_cycle_skips_the_calculated_average():
    today = _today()
    with patch.object(handlers.db, "save_period_log"), \
         patch.object(handlers.db, "calculate_avg_cycle") as mock_calc_avg, \
         patch.object(handlers.scheduler_module, "schedule_user_reminders", return_value=3):
        handlers.process_and_reply("u1", today, custom_cycle=30)
    mock_calc_avg.assert_not_called()


def test_out_of_range_custom_cycle_falls_back_to_calculated_average():
    today = _today()
    with patch.object(handlers.db, "save_period_log"), \
         patch.object(handlers.db, "calculate_avg_cycle", return_value=28) as mock_calc_avg, \
         patch.object(handlers.scheduler_module, "schedule_user_reminders", return_value=3):
        handlers.process_and_reply("u1", today, custom_cycle=99)
    mock_calc_avg.assert_called_once()
