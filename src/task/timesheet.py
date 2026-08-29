"""Timeline resolution for the timesheet — see docs/timesheet.md.

Pure functions over a list of `Entry`. Nothing here touches disk, config, or the
terminal; the day's shape is derived entirely from the stored rows.

The load-bearing rule is that start times are *derived*, not stored:

    effective start = `from_` if set, else the effective end of the previous row

which is the spreadsheet formula made explicit. Extending a row therefore cascades
into every row after it for free — there is no shifting code here, only derivation.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from task.models import Entry

DEFAULT_DAY_STARTS_AT = time(4, 0)


@dataclass
class ResolvedEntry:
    """A row placed on the timeline. A view object — never stored, never serialised."""

    entry: Entry
    start: datetime | None  # None when the row has no anchor and no predecessor
    end: datetime | None  # None while the row is still open
    day: date | None
    gap_before: timedelta | None  # untracked time between this row and the previous one

    @property
    def duration(self) -> timedelta | None:
        if self.start is None or self.end is None:
            return None
        return self.end - self.start

    @property
    def is_open(self) -> bool:
        return self.end is None


def logical_day(moment: datetime, day_starts_at: time = DEFAULT_DAY_STARTS_AT) -> date:
    """Which logical day a moment belongs to.

    With the default 04:00 boundary, 00:45 on the 29th belongs to the 28th — which is
    what makes work past midnight land in the evening it actually belongs to.
    """
    if moment.time() >= day_starts_at:
        return moment.date()
    return moment.date() - timedelta(days=1)


def day_window(day: date, day_starts_at: time = DEFAULT_DAY_STARTS_AT) -> tuple[datetime, datetime]:
    """Half-open [start, end) bounds of a logical day."""
    start = datetime.combine(day, day_starts_at)
    return start, start + timedelta(days=1)


def resolve_clock(
    clock: time,
    now: datetime,
    day_starts_at: time = DEFAULT_DAY_STARTS_AT,
) -> datetime:
    """Place a bare clock time inside the logical day containing `now`.

    `parse_date` would return *today* at that time, which is in the future when it is
    00:50 and the user types `from:23:30`. Resolving against the logical day instead
    puts 23:30 on the previous calendar date and 00:30 on the current one.
    """
    start, _ = day_window(logical_day(now, day_starts_at), day_starts_at)
    candidate = datetime.combine(start.date(), clock)
    if candidate < start:
        candidate += timedelta(days=1)
    return candidate


def resolve(
    entries: list[Entry],
    day_starts_at: time = DEFAULT_DAY_STARTS_AT,
) -> list[ResolvedEntry]:
    """Walk rows in log order, deriving each start from the previous row's end.

    An anchored row (`from_` set) breaks the chain — that is both the manual override
    and the way a gap is expressed. A row with neither an anchor nor a predecessor is
    unresolvable and comes back with `start=None` rather than raising; that only arises
    when the anchor of a day has been deleted, and the caller decides what to show.
    """
    resolved: list[ResolvedEntry] = []
    cursor: datetime | None = None  # effective end of the previous row

    for entry in entries:
        start = entry.from_ if entry.from_ is not None else cursor

        # A gap is an anchor that leaves a hole in the same logical day. Anchors that
        # start a new day are not gaps — last night's end is not this morning's business.
        gap_before = None
        if (
            entry.from_ is not None
            and cursor is not None
            and entry.from_ > cursor
            and logical_day(entry.from_, day_starts_at) == logical_day(cursor, day_starts_at)
        ):
            gap_before = entry.from_ - cursor

        resolved.append(
            ResolvedEntry(
                entry=entry,
                start=start,
                end=entry.til,
                day=logical_day(start, day_starts_at) if start is not None else None,
                gap_before=gap_before,
            )
        )
        # An open row ends the chain: nothing after it can derive a start.
        cursor = entry.til

    return resolved


def resolve_day(
    entries: list[Entry],
    day: date,
    day_starts_at: time = DEFAULT_DAY_STARTS_AT,
) -> list[ResolvedEntry]:
    """The rows belonging to one logical day, in timeline order."""
    return [r for r in resolve(entries, day_starts_at) if r.day == day]


def total_tracked(resolved: list[ResolvedEntry]) -> timedelta:
    """Summed duration of closed rows. Open rows contribute nothing."""
    return sum((r.duration for r in resolved if r.duration is not None), timedelta())


def rollup(resolved: list[ResolvedEntry], attribute: str) -> dict[str | None, timedelta]:
    """Tracked time grouped by an Entry attribute — `kind` or `project`.

    Ordered by descending total so the render layer does not have to sort.
    """
    totals: dict[str | None, timedelta] = {}
    for r in resolved:
        if r.duration is None:
            continue
        key = getattr(r.entry, attribute)
        totals[key] = totals.get(key, timedelta()) + r.duration
    return dict(sorted(totals.items(), key=lambda kv: (-kv[1], str(kv[0]))))
