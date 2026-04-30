import calendar
import re
from datetime import datetime, timedelta

from dateutil import parser as _du_parser
from dateutil.relativedelta import relativedelta

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_OFFSET = re.compile(r'^([+-]?)(\d+)(min|h|d|w|m|y)$')
_DURATION = re.compile(r'^(?:(\d+)h)?(\d+)(?:min|m)$|^(\d+)h$')


def parse_duration_seconds(s: str) -> float:
    """Parse a duration string like '2h', '30min', '1h30m' into seconds."""
    m = _DURATION.match(s.strip())
    if not m:
        raise ValueError(f"unrecognized duration {s!r}; expected forms: 2h, 30min, 1h30m")
    if m.group(3) is not None:
        # matched (\d+)h only
        return int(m.group(3)) * 3600
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    return hours * 3600 + minutes * 60


def parse_date(value: str, now: datetime | None = None) -> datetime:
    """Parse a date string per parsing.md. Raises ValueError on unrecognized input."""
    if now is None:
        now = datetime.now()

    v = value.strip().lower()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    match v:
        case "now":
            return now
        case "today":
            return today
        case "tomorrow":
            return today + timedelta(days=1)
        case "yesterday":
            return today - timedelta(days=1)
        case "eod":
            return today.replace(hour=23, minute=59, second=59)
        case "eow":
            days_to_sunday = (6 - today.weekday()) % 7
            return (today + timedelta(days=days_to_sunday)).replace(hour=23, minute=59, second=59)
        case "eom":
            last_day = calendar.monthrange(today.year, today.month)[1]
            return today.replace(day=last_day, hour=23, minute=59, second=59)
        case "eoy":
            return today.replace(month=12, day=31, hour=23, minute=59, second=59)

    if v in _WEEKDAYS:
        target_dow = _WEEKDAYS[v]
        days_ahead = (target_dow - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)

    if v in _MONTHS:
        target_month = _MONTHS[v]
        year = now.year + 1 if now.month >= target_month else now.year
        return datetime(year, target_month, 1, 0, 0, 0)

    m = _OFFSET.match(v)
    if m:
        sign_str, qty_str, unit = m.groups()
        n = int(qty_str) * (-1 if sign_str == "-" else 1)
        match unit:
            case "min": return now + timedelta(minutes=n)
            case "h":   return now + timedelta(hours=n)
            case "d":   return now + timedelta(days=n)
            case "w":   return now + timedelta(weeks=n)
            case "m":   return now + relativedelta(months=n)
            case "y":   return now + relativedelta(years=n)

    try:
        return _du_parser.parse(value.strip(), dayfirst=False)
    except (ValueError, OverflowError):
        pass

    raise ValueError(f"unrecognized date: {value!r}")
