"""Timeline resolution — docs/timesheet.md.

The rules under test: starts derive from the previous row's end, an anchor breaks the
chain, editing an end cascades, and a logical day runs from 04:00 so work past midnight
stays with the evening it belongs to.
"""

from datetime import date, datetime, time, timedelta

from task.models import Entry
from task.timesheet import (
    day_window,
    logical_day,
    resolve,
    resolve_clock,
    resolve_day,
    rollup,
    total_tracked,
)


def _e(kind="solo", from_=None, til=None, **kw):
    return Entry(kind=kind, from_=from_, til=til, **kw)


def _at(h, m=0, day=29):
    return datetime(2026, 8, day, h, m)


# ---------------------------------------------------------------------------
# logical_day
# ---------------------------------------------------------------------------

def test_morning_belongs_to_its_own_date():
    assert logical_day(_at(9)) == date(2026, 8, 29)


def test_just_after_the_boundary_belongs_to_its_own_date():
    assert logical_day(_at(4, 0)) == date(2026, 8, 29)


def test_late_evening_belongs_to_its_own_date():
    assert logical_day(_at(23, 30)) == date(2026, 8, 29)


def test_after_midnight_belongs_to_the_previous_day():
    assert logical_day(_at(0, 45)) == date(2026, 8, 28)


def test_just_before_the_boundary_belongs_to_the_previous_day():
    assert logical_day(_at(3, 59)) == date(2026, 8, 28)


def test_boundary_is_configurable():
    assert logical_day(_at(5, 0), day_starts_at=time(6, 0)) == date(2026, 8, 28)


def test_day_window_is_twenty_four_hours():
    start, end = day_window(date(2026, 8, 29))
    assert start == datetime(2026, 8, 29, 4, 0)
    assert end - start == timedelta(days=1)


# ---------------------------------------------------------------------------
# resolve_clock — bare clock times land inside the current logical day
# ---------------------------------------------------------------------------

def test_clock_time_earlier_today_resolves_to_today():
    assert resolve_clock(time(9, 15), now=_at(10, 0)) == _at(9, 15)


def test_clock_time_before_midnight_resolves_to_yesterday_when_it_is_past_midnight():
    # 00:50 on the 29th is still the 28th's logical day, so 23:30 means last night.
    assert resolve_clock(time(23, 30), now=_at(0, 50)) == datetime(2026, 8, 28, 23, 30)


def test_clock_time_after_midnight_resolves_to_today_when_it_is_past_midnight():
    assert resolve_clock(time(0, 30), now=_at(0, 50)) == _at(0, 30)


def test_clock_time_in_the_small_hours_resolves_forward():
    # 03:00 is the tail of the logical day that began on the 29th at 04:00.
    assert resolve_clock(time(3, 0), now=_at(22, 0)) == datetime(2026, 8, 30, 3, 0)


# ---------------------------------------------------------------------------
# resolve — derivation, anchors, gaps
# ---------------------------------------------------------------------------

def test_first_row_uses_its_anchor():
    r = resolve([_e(from_=_at(9), til=_at(9, 30))])
    assert r[0].start == _at(9) and r[0].end == _at(9, 30)


def test_second_row_derives_its_start_from_the_first():
    rows = resolve([_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11, 20))])
    assert rows[1].start == _at(9, 30)
    assert rows[1].duration == timedelta(hours=1, minutes=50)


def test_chain_continues_across_several_rows():
    rows = resolve([
        _e(from_=_at(9), til=_at(9, 30)),
        _e(til=_at(11, 20)),
        _e(til=_at(11, 45)),
    ])
    assert [r.start for r in rows] == [_at(9), _at(9, 30), _at(11, 20)]


def test_editing_an_end_cascades_into_every_later_row():
    """A meeting that ran long shifts everything after it, with no other edit."""
    before = resolve([_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11, 20)), _e(til=_at(12, 0))])
    after = resolve([_e(from_=_at(9), til=_at(10, 0)), _e(til=_at(11, 20)), _e(til=_at(12, 0))])
    assert before[1].start == _at(9, 30)
    assert after[1].start == _at(10, 0)  # cascaded
    assert after[2].start == _at(11, 20)  # unchanged: it derives from row 2's own end


def test_anchor_breaks_the_chain():
    rows = resolve([_e(from_=_at(9), til=_at(9, 30)), _e(from_=_at(14), til=_at(15))])
    assert rows[1].start == _at(14)


def test_gap_is_reported_when_an_anchor_leaves_a_hole():
    rows = resolve([_e(from_=_at(9), til=_at(12, 30)), _e(from_=_at(13, 15), til=_at(14))])
    assert rows[1].gap_before == timedelta(minutes=45)


def test_no_gap_when_the_anchor_is_contiguous():
    rows = resolve([_e(from_=_at(9), til=_at(12, 30)), _e(from_=_at(12, 30), til=_at(14))])
    assert rows[1].gap_before is None


def test_no_gap_reported_for_a_derived_row():
    rows = resolve([_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11))])
    assert rows[1].gap_before is None


def test_gap_is_not_reported_across_a_day_boundary():
    """Last night's end and this morning's anchor are not a gap in one day."""
    rows = resolve([
        _e(from_=_at(22, day=28), til=_at(23, day=28)),
        _e(from_=_at(9), til=_at(10)),
    ])
    assert rows[1].gap_before is None


# --- open rows ---

def test_open_row_has_no_end_or_duration():
    rows = resolve([_e(from_=_at(13, 15))])
    assert rows[0].is_open and rows[0].end is None and rows[0].duration is None


def test_row_after_an_open_row_is_unresolvable_without_an_anchor():
    rows = resolve([_e(from_=_at(9)), _e(til=_at(11))])
    assert rows[1].start is None and rows[1].day is None


def test_row_after_an_open_row_resolves_when_anchored():
    rows = resolve([_e(from_=_at(9)), _e(from_=_at(11), til=_at(12))])
    assert rows[1].start == _at(11)


def test_unanchored_first_row_is_unresolvable_rather_than_raising():
    """Arises when a day's anchor is deleted; the caller decides what to render."""
    rows = resolve([_e(til=_at(9, 30))])
    assert rows[0].start is None and rows[0].day is None


def test_empty_input():
    assert resolve([]) == []


# --- past midnight ---

def test_row_spanning_midnight_measures_correctly():
    rows = resolve([_e(from_=_at(23, 30, day=28), til=_at(0, 45))])
    assert rows[0].duration == timedelta(hours=1, minutes=15)


def test_row_spanning_midnight_stays_in_the_evenings_logical_day():
    rows = resolve([_e(from_=_at(23, 30, day=28), til=_at(0, 45))])
    assert rows[0].day == date(2026, 8, 28)


def test_derived_row_after_midnight_stays_with_the_evening():
    rows = resolve([
        _e(from_=_at(22, day=28), til=_at(23, 30, day=28)),
        _e(til=_at(1, 0)),
    ])
    assert [r.day for r in rows] == [date(2026, 8, 28), date(2026, 8, 28)]


def test_a_new_days_anchor_starts_a_new_logical_day():
    rows = resolve([
        _e(from_=_at(22, day=28), til=_at(1, 0)),
        _e(from_=_at(9), til=_at(10)),
    ])
    assert [r.day for r in rows] == [date(2026, 8, 28), date(2026, 8, 29)]


# ---------------------------------------------------------------------------
# resolve_day, totals, rollups
# ---------------------------------------------------------------------------

def _a_day():
    return [
        _e(kind="meeting", project="internal", from_=_at(9), til=_at(9, 30)),
        _e(kind="solo", project="acme.parse", til=_at(11, 20)),
        _e(kind="junk", til=_at(11, 45)),
        _e(kind="call", project="acme", til=_at(12, 30)),
        _e(kind="solo", project="acme.parse", from_=_at(13, 15), til=_at(14, 15)),
    ]


def test_resolve_day_selects_only_that_day():
    entries = [_e(from_=_at(22, day=28), til=_at(23, day=28)), *_a_day()]
    assert len(resolve_day(entries, date(2026, 8, 29))) == 5


def test_resolve_day_is_empty_for_a_day_with_no_rows():
    assert resolve_day(_a_day(), date(2026, 8, 27)) == []


def test_total_tracked_excludes_gaps():
    rows = resolve_day(_a_day(), date(2026, 8, 29))
    assert total_tracked(rows) == timedelta(hours=4, minutes=30)


def test_total_tracked_ignores_open_rows():
    rows = resolve([_e(from_=_at(9), til=_at(10)), _e(from_=_at(11))])
    assert total_tracked(rows) == timedelta(hours=1)


def test_rollup_by_kind():
    rows = resolve_day(_a_day(), date(2026, 8, 29))
    assert rollup(rows, "kind") == {
        "solo": timedelta(hours=2, minutes=50),
        "call": timedelta(minutes=45),
        "meeting": timedelta(minutes=30),
        "junk": timedelta(minutes=25),
    }


def test_rollup_by_project_keeps_unassigned_time():
    rows = resolve_day(_a_day(), date(2026, 8, 29))
    totals = rollup(rows, "project")
    assert totals["acme.parse"] == timedelta(hours=2, minutes=50)
    assert totals[None] == timedelta(minutes=25)


def test_rollup_is_ordered_by_descending_total():
    rows = resolve_day(_a_day(), date(2026, 8, 29))
    assert list(rollup(rows, "kind")) == ["solo", "call", "meeting", "junk"]


def test_rollup_of_nothing_is_empty():
    assert rollup([], "kind") == {}
