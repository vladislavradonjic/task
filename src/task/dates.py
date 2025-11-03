"""Date parsing funcitons"""

from datetime import date, timedelta
from dateutil import parser
import calendar


WEEKDAY_MAP = {
    'mon': 0, 'monday': 0,
    'tue': 1, 'tuesday': 1,
    'wed': 2, 'wednesday': 2,
    'thu': 3, 'thursday': 3,
    'fri': 4, 'friday': 4,
    'sat': 5, 'saturday': 5,
    'sun': 6, 'sunday': 6,
}

MONTH_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

def eom(dat: date) -> date:
    return date(dat.year, dat.month, calendar.monthrange(dat.year, dat.month)[1])

def parse_date_string(value: str, base_date: date | None = None) -> date | None:
    """Parse natural language date string.

    Supports:
    - "today", "tomorrow", "eom"
    - Weekdays: "friday", "monday"
    - Months: "sep", "october"
    - Month-day: "nov6", "feb5"
    - ISO format: "2025-08-21"

    Returns None if unparseable.
    """
    if not value:
        return None

    today = base_date or date.today()
    value_lower = value.lower().strip()
    # today
    if value_lower == "today":
        return today
    # tomorrow
    if value_lower == "tomorrow":
        return today + timedelta(days=1)
    # eom
    if value_lower == "eom":
        return eom(today)
    # weekday
    if value_lower in WEEKDAY_MAP:
        weekday = WEEKDAY_MAP[value_lower]
        days_ahead = (weekday - today.weekday())
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)
    # month
    if value_lower in MONTH_MAP:
        month = MONTH_MAP[value_lower]
        year = today.year
        if month < today.month:
            year += 1
        return eom(date(year, month, 1))
    # month-day, ISO, etc.
    try:
        parsed_date = parser.parse(value_lower, default=today)
        # if in past, push to next year
        if parsed_date < today:
            parsed_date = parsed_date.replace(year=today.year + 1)
        return parsed_date
    except ValueError:
        print(f"Date {value} not parsable; using None")
        return None