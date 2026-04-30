import pytest
from datetime import datetime, timedelta

from task.dates import parse_date


# April 15 2026 is a Wednesday (weekday=2)
_NOW = datetime(2026, 4, 15, 10, 30, 0)


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

def test_now():
    assert parse_date("now", now=_NOW) == _NOW


def test_today():
    assert parse_date("today", now=_NOW) == datetime(2026, 4, 15, 0, 0, 0)


def test_tomorrow():
    assert parse_date("tomorrow", now=_NOW) == datetime(2026, 4, 16, 0, 0, 0)


def test_yesterday():
    assert parse_date("yesterday", now=_NOW) == datetime(2026, 4, 14, 0, 0, 0)


def test_eod():
    assert parse_date("eod", now=_NOW) == datetime(2026, 4, 15, 23, 59, 59)


def test_eow_midweek():
    # Wednesday → next Sunday
    assert parse_date("eow", now=_NOW) == datetime(2026, 4, 19, 23, 59, 59)


def test_eow_on_sunday():
    sunday = datetime(2026, 4, 19, 10, 0, 0)
    assert parse_date("eow", now=sunday) == datetime(2026, 4, 19, 23, 59, 59)


def test_eow_on_monday():
    monday = datetime(2026, 4, 20, 10, 0, 0)
    assert parse_date("eow", now=monday) == datetime(2026, 4, 26, 23, 59, 59)


def test_eom_april():
    assert parse_date("eom", now=_NOW) == datetime(2026, 4, 30, 23, 59, 59)


def test_eom_february_non_leap():
    feb = datetime(2026, 2, 10, 10, 0, 0)
    assert parse_date("eom", now=feb) == datetime(2026, 2, 28, 23, 59, 59)


def test_eoy():
    assert parse_date("eoy", now=_NOW) == datetime(2026, 12, 31, 23, 59, 59)


def test_keywords_case_insensitive():
    assert parse_date("TODAY", now=_NOW) == parse_date("today", now=_NOW)
    assert parse_date("EOD", now=_NOW) == parse_date("eod", now=_NOW)


# ---------------------------------------------------------------------------
# Weekday names
# ---------------------------------------------------------------------------

def test_weekday_future():
    # Wednesday → next Monday (5 days ahead)
    assert parse_date("monday", now=_NOW) == datetime(2026, 4, 20, 0, 0, 0)


def test_weekday_same_day_is_next_week():
    # Today is Wednesday; wednesday → next Wednesday (+7)
    assert parse_date("wednesday", now=_NOW) == datetime(2026, 4, 22, 0, 0, 0)


def test_weekday_short_form():
    assert parse_date("mon", now=_NOW) == parse_date("monday", now=_NOW)
    assert parse_date("fri", now=_NOW) == parse_date("friday", now=_NOW)


def test_weekday_case_insensitive():
    assert parse_date("MONDAY", now=_NOW) == parse_date("monday", now=_NOW)


def test_weekday_sunday_from_wednesday():
    # Wednesday → next Sunday (4 days)
    assert parse_date("sunday", now=_NOW) == datetime(2026, 4, 19, 0, 0, 0)


# ---------------------------------------------------------------------------
# Month names
# ---------------------------------------------------------------------------

def test_month_future_in_same_year():
    # April → June: June 1 this year
    assert parse_date("june", now=_NOW) == datetime(2026, 6, 1, 0, 0, 0)


def test_month_past_wraps_to_next_year():
    # April → February: Feb 1 next year
    assert parse_date("february", now=_NOW) == datetime(2027, 2, 1, 0, 0, 0)


def test_month_current_wraps_to_next_year():
    # Currently April → april: Apr 1 next year
    assert parse_date("april", now=_NOW) == datetime(2027, 4, 1, 0, 0, 0)


def test_month_short_form():
    assert parse_date("jun", now=_NOW) == parse_date("june", now=_NOW)
    assert parse_date("feb", now=_NOW) == parse_date("february", now=_NOW)


def test_month_case_insensitive():
    assert parse_date("JUNE", now=_NOW) == parse_date("june", now=_NOW)


# ---------------------------------------------------------------------------
# Offsets
# ---------------------------------------------------------------------------

def test_offset_days_positive():
    assert parse_date("+3d", now=_NOW) == _NOW + timedelta(days=3)


def test_offset_days_negative():
    assert parse_date("-2d", now=_NOW) == _NOW + timedelta(days=-2)


def test_offset_unsigned_means_positive():
    assert parse_date("1d", now=_NOW) == _NOW + timedelta(days=1)


def test_offset_hours():
    assert parse_date("+2h", now=_NOW) == _NOW + timedelta(hours=2)


def test_offset_minutes():
    assert parse_date("+30min", now=_NOW) == _NOW + timedelta(minutes=30)


def test_offset_weeks():
    assert parse_date("+1w", now=_NOW) == _NOW + timedelta(weeks=1)


def test_offset_months():
    result = parse_date("+2m", now=_NOW)
    assert result == datetime(2026, 6, 15, 10, 30, 0)


def test_offset_years():
    result = parse_date("+1y", now=_NOW)
    assert result == datetime(2027, 4, 15, 10, 30, 0)


# ---------------------------------------------------------------------------
# ISO-8601 absolute
# ---------------------------------------------------------------------------

def test_iso_date():
    result = parse_date("2026-09-03")
    assert result.year == 2026
    assert result.month == 9
    assert result.day == 3


def test_iso_datetime():
    result = parse_date("2026-09-03T14:00")
    assert result.hour == 14
    assert result.minute == 0


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------

def test_invalid_raises_value_error():
    with pytest.raises(ValueError, match="unrecognized date"):
        parse_date("notadate")


def test_empty_string_raises():
    with pytest.raises(ValueError):
        parse_date("")
