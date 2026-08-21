from handlers import _round_to_ten_minutes


def test_already_on_a_ten_minute_mark_is_unchanged():
    assert _round_to_ten_minutes(8, 0) == (8, 0)
    assert _round_to_ten_minutes(8, 30) == (8, 30)


def test_rounds_down_below_the_halfway_point():
    assert _round_to_ten_minutes(8, 4) == (8, 0)
    assert _round_to_ten_minutes(8, 24) == (8, 20)


def test_ties_round_up():
    assert _round_to_ten_minutes(8, 5) == (8, 10)
    assert _round_to_ten_minutes(8, 15) == (8, 20)


def test_rounds_up_above_the_halfway_point():
    assert _round_to_ten_minutes(8, 6) == (8, 10)
    assert _round_to_ten_minutes(8, 59) == (9, 0)


def test_rounding_up_past_the_hour_wraps_to_the_next_hour():
    assert _round_to_ten_minutes(23, 55) == (0, 0)
