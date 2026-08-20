from datetime import datetime

import pytest

from handlers import parse_date_input


@pytest.mark.parametrize("separator", ["/", "-", ".", " "])
def test_parses_gregorian_date_with_any_separator(separator):
    text = separator.join(["01", "08", "2026"])
    parsed_date, custom_cycle = parse_date_input(text)
    assert parsed_date == datetime(2026, 8, 1)
    assert custom_cycle is None


def test_parses_single_digit_day_and_month():
    parsed_date, _ = parse_date_input("1/8/2026")
    assert parsed_date == datetime(2026, 8, 1)


def test_converts_buddhist_era_year_to_gregorian():
    parsed_date, _ = parse_date_input("01/08/2569")
    assert parsed_date == datetime(2026, 8, 1)


def test_parses_trailing_custom_cycle_length():
    parsed_date, custom_cycle = parse_date_input("01/08/2026 30")
    assert parsed_date == datetime(2026, 8, 1)
    assert custom_cycle == 30


def test_rejects_invalid_calendar_date():
    parsed_date, custom_cycle = parse_date_input("31/02/2026")
    assert parsed_date is None
    assert custom_cycle is None


def test_rejects_out_of_range_month():
    parsed_date, custom_cycle = parse_date_input("01/13/2026")
    assert parsed_date is None
    assert custom_cycle is None


def test_rejects_text_that_is_not_a_date():
    parsed_date, custom_cycle = parse_date_input("บันทึกรอบเดือน")
    assert parsed_date is None
    assert custom_cycle is None


def test_strips_surrounding_whitespace():
    parsed_date, _ = parse_date_input("  01/08/2026  ")
    assert parsed_date == datetime(2026, 8, 1)
