from unittest.mock import patch

import db


def _logs(*start_dates):
    return [{"id": i, "start_date": d} for i, d in enumerate(start_dates)]


def test_defaults_to_28_days_with_fewer_than_two_logs():
    with patch.object(db, "get_user_logs", return_value=_logs("2026-08-01")):
        assert db.calculate_avg_cycle("u1") == 28


def test_defaults_to_28_days_with_no_logs():
    with patch.object(db, "get_user_logs", return_value=[]):
        assert db.calculate_avg_cycle("u1") == 28


def test_returns_median_gap_between_consecutive_logs():
    # Gaps: 28 (Jun10->Jul08), 30 (Jul08->Aug07) -> median of [28, 30] = 29
    with patch.object(db, "get_user_logs", return_value=_logs("2026-08-07", "2026-07-08", "2026-06-10")):
        assert db.calculate_avg_cycle("u1") == 29


def test_median_resists_a_single_outlier_gap():
    # Gaps sorted: 26, 28, 44 -> median is the middle value, 28,
    # whereas a plain mean (26+28+44)/3 = 32.67 would be pulled toward the outlier.
    with patch.object(
        db, "get_user_logs",
        return_value=_logs("2026-08-20", "2026-07-07", "2026-06-09", "2026-05-14"),
    ):
        assert db.calculate_avg_cycle("u1") == 28


def test_ignores_gaps_outside_the_plausible_cycle_range():
    # Gap of 5 days is outside the 20-45 day physiological window and is dropped;
    # with no gaps left to average, falls back to the 28-day default.
    with patch.object(db, "get_user_logs", return_value=_logs("2026-08-06", "2026-08-01")):
        assert db.calculate_avg_cycle("u1") == 28


def test_calculation_window_matches_stored_history_limit():
    with patch.object(db, "get_user_logs") as mock_get_logs:
        mock_get_logs.return_value = _logs("2026-08-01", "2026-07-01")
        db.calculate_avg_cycle("u1")
        mock_get_logs.assert_called_once_with("u1", limit=db.MAX_PERIOD_LOGS_PER_USER)
