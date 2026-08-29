"""Timeline resolution — docs/timesheet.md.

The rules under test: starts derive from the previous row's end, an anchor breaks the
chain, editing an end cascades, and a logical day runs from 04:00 so work past midnight
stays with the evening it belongs to.
"""

from datetime import date, datetime, time, timedelta

import pytest

from task import commands
from task.commands import _entry_delete, _entry_modify, day_, log_
from task.config import Config, Shortcut, TimesheetConfig
from task.models import (
    Entry,
    EntryDeletedEvent,
    EntryUpdatedEvent,
    LoggedEvent,
    ParsedFilter,
    ParsedModification,
    Task,
)
from task.storage import assign_display_ids
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


# ---------------------------------------------------------------------------
# log_ / day_ — the commands (docs/timesheet.md)
# ---------------------------------------------------------------------------

@pytest.fixture
def at_1100(monkeypatch):
    """Pin the clock so `til:` defaulting and future-checks are deterministic."""
    def _pin(moment):
        real = datetime

        class Fake(datetime):
            @classmethod
            def now(cls, tz=None):
                return real(moment.year, moment.month, moment.day, moment.hour, moment.minute)

        monkeypatch.setattr(commands, "datetime", Fake)
    _pin(_at(11, 0))
    return _at(11, 0)


def _cfg(**timesheet):
    return Config(timesheet=TimesheetConfig(**timesheet))


def _mod(description="", **props):
    return ParsedModification(description=description, properties=props)


def _log(entries, tasks=None, description="", cfg=None, **props):
    return log_(entries, tasks or [], ParsedFilter(), _mod(description, **props), cfg or _cfg())


def test_log_emits_one_logged_event(at_1100):
    events, message = _log([], description="standup", kind="meeting", **{"from": "9:00", "til": "9:30"})
    assert len(events) == 1 and isinstance(events[0], LoggedEvent)
    assert "standup" in message


def test_log_stores_the_anchor_and_end(at_1100):
    events, _ = _log([], description="standup", kind="meeting", **{"from": "9:00", "til": "9:30"})
    entry = events[0].snapshot
    assert entry.from_ == _at(9) and entry.til == _at(9, 30)


def test_log_til_defaults_to_now(at_1100):
    events, _ = _log([], description="x", kind="solo", **{"from": "9:00"})
    assert events[0].snapshot.til == _at(11, 0)


def test_log_leaves_from_unset_so_it_derives(at_1100):
    previous = _e(from_=_at(9), til=_at(9, 30))
    events, _ = _log([previous], description="next", kind="solo", til="10:00")
    assert events[0].snapshot.from_ is None


def test_logged_row_chains_onto_the_previous_one(at_1100):
    previous = _e(from_=_at(9), til=_at(9, 30))
    events, _ = _log([previous], description="next", kind="solo", til="10:00")
    rows = resolve([previous, events[0].snapshot])
    assert rows[1].start == _at(9, 30) and rows[1].duration == timedelta(minutes=30)


def test_log_for_computes_the_end_from_the_anchor(at_1100):
    events, _ = _log([], description="x", kind="solo", **{"from": "9:00", "for": "90min"})
    assert events[0].snapshot.til == _at(10, 30)


def test_log_for_computes_the_anchor_from_the_end(at_1100):
    events, _ = _log([], description="x", kind="solo", til="10:00", **{"for": "1h"})
    assert events[0].snapshot.from_ == _at(9, 0)


def test_log_refuses_all_three_of_from_til_and_for(at_1100):
    events, message = _log([], kind="solo", **{"from": "9:00", "til": "10:00", "for": "1h"})
    assert events == [] and "at most two" in message


def test_log_refuses_a_future_end(at_1100):
    events, message = _log([], description="x", kind="solo", til="23:00")
    assert events == [] and "future" in message


def test_log_requires_a_kind(at_1100):
    events, message = _log([], description="x")
    assert events == [] and "kind" in message


def test_log_refuses_tags(at_1100):
    events, message = log_([], [], ParsedFilter(), ParsedModification(description="x", tags=["+bug"]), _cfg())
    assert events == [] and "Tags are not valid" in message


def test_log_refuses_unknown_properties(at_1100):
    events, message = _log([], kind="solo", bogus="1")
    assert events == [] and "bogus" in message


def test_log_without_an_earlier_row_today_asks_for_an_anchor(at_1100):
    events, message = _log([], description="x", kind="solo", til="10:00")
    assert events == [] and "from:" in message


def test_log_will_not_chain_across_a_day_boundary(at_1100):
    """Last night's last row must not become this morning's start."""
    last_night = _e(from_=_at(22, day=28), til=_at(23, day=28))
    events, message = _log([last_night], description="morning", kind="solo", til="10:00")
    assert events == [] and "from:" in message


def test_log_links_a_task_by_display_id(at_1100):
    task = Task(description="write the parser")
    assign_display_ids([task])
    events, _ = _log([], [task], description="x", kind="solo", task="1", **{"from": "9:00"})
    assert events[0].snapshot.task == task.uuid


def test_log_refuses_an_unknown_task_id(at_1100):
    events, message = _log([], [], kind="solo", task="99", **{"from": "9:00"})
    assert events == [] and "No task with id 99" in message


def test_log_refuses_a_non_numeric_task(at_1100):
    events, message = _log([], [], kind="solo", task="abc", **{"from": "9:00"})
    assert events == [] and "task id" in message


def test_log_keeps_description_optional_when_kind_and_project_say_enough(at_1100):
    events, message = _log([], kind="meeting", project="acme", **{"from": "9:00"})
    assert events[0].snapshot.description == ""
    assert "meeting on acme" in message


def test_log_resolves_a_clock_time_across_midnight(monkeypatch):
    real = datetime

    class Fake(datetime):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 8, 30, 0, 50)

    monkeypatch.setattr(commands, "datetime", Fake)
    events, _ = _log([], description="late deploy", kind="solo", **{"from": "23:30"})
    entry = events[0].snapshot
    assert entry.from_ == datetime(2026, 8, 29, 23, 30)
    assert entry.til == datetime(2026, 8, 30, 0, 50)
    assert resolve([entry])[0].duration == timedelta(hours=1, minutes=20)
    assert resolve([entry])[0].day == date(2026, 8, 29)


# --- day_ ---

def test_day_reports_an_empty_day(at_1100):
    events, message = day_([], [], ParsedFilter(), _mod(), _cfg())
    assert events == [] and "Nothing logged" in message


def test_day_renders_rows_with_times_kinds_and_totals(at_1100, capsys):
    day_(_a_day(), [], ParsedFilter(), _mod(), _cfg())
    out = capsys.readouterr().out
    assert "09:00" in out and "09:30" in out
    assert "meeting" in out and "junk" in out
    assert "4:30 tracked" in out          # sums the day, excluding the 45m gap
    assert "untracked" in out             # and shows the gap explicitly


def test_day_assigns_letters_in_timeline_order(at_1100):
    entries = _a_day()
    day_(entries, [], ParsedFilter(), _mod(), _cfg())
    assert [e.id for e in entries] == ["a", "b", "c", "d", "e"]


def test_day_accepts_an_explicit_date(at_1100, capsys):
    day_(_a_day(), [], ParsedFilter(), _mod("2026-08-29"), _cfg())
    assert "Saturday 29 Aug" in capsys.readouterr().out


def test_day_with_an_explicit_date_that_has_no_rows(at_1100):
    events, message = day_(_a_day(), [], ParsedFilter(), _mod("2026-08-27"), _cfg())
    assert events == [] and "Thursday 27 Aug" in message


def test_day_shows_the_task_link(at_1100, capsys):
    task = Task(description="write the parser")
    assign_display_ids([task])
    entries = [_e(from_=_at(9), til=_at(9, 30), task=task.uuid)]
    day_(entries, [task], ParsedFilter(), _mod(), _cfg())
    assert "→1" in capsys.readouterr().out


def test_day_rejects_an_unparseable_date(at_1100):
    events, message = day_([], [], ParsedFilter(), _mod("notadate"), _cfg())
    assert events == [] and "notadate" in message


# ---------------------------------------------------------------------------
# editing: _entry_modify / _entry_delete, reached via `tsk <letter> modify|delete`
# ---------------------------------------------------------------------------

def _rows(*entries):
    """Entries as they would be after a day render, so letters are assigned."""
    from task.storage import assign_display_letters

    listed = list(entries)
    assign_display_letters([r.entry for r in resolve_day(listed, date(2026, 8, 29))])
    return listed


def _edit(entries, letters, tasks=None, description="", cfg=None, **props):
    return _entry_modify(
        entries, tasks or [],
        ParsedFilter(letters=letters if isinstance(letters, list) else [letters]),
        _mod(description, **props),
        cfg or _cfg(),
    )


def _rm(entries, letters, tasks=None):
    return _entry_delete(
        entries, tasks or [],
        ParsedFilter(letters=letters if isinstance(letters, list) else [letters]),
        _mod(), _cfg(),
    )


def test_modify_changes_the_end(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)))
    events, message = _edit(entries, "a", til="10:00")
    assert isinstance(events[0], EntryUpdatedEvent)
    assert events[0].changes["til"].after == _at(10)
    assert "Updated" in message


def test_modifying_an_end_cascades_into_the_next_row(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)))
    events, _ = _edit(entries, "a", til="10:00")
    from task.events import apply_entry_event
    updated = apply_entry_event(entries, events[0])
    rows = resolve(updated)
    assert rows[1].start == _at(10) and rows[1].duration == timedelta(hours=1)


def test_modify_changes_kind_project_and_description(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30), description="rough"))
    events, _ = _edit(entries, "a", description="client sync", kind="call", project="acme")
    changes = events[0].changes
    assert changes["kind"].after == "call"
    assert changes["project"].after == "acme"
    assert changes["description"].after == "client sync"


def test_modify_can_clear_til_to_reopen_a_row(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, _ = _edit(entries, "a", til=None)
    assert events[0].changes["til"].after is None


def test_modify_can_clear_from_to_rejoin_the_chain(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(from_=_at(10), til=_at(11)))
    events, _ = _edit(entries, "b", **{"from": None})
    assert events[0].changes["from_"].after is None


def test_modify_links_and_unlinks_a_task(at_1100):
    task = Task(description="write the parser")
    assign_display_ids([task])
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, _ = _edit(entries, "a", [task], task="1")
    assert events[0].changes["task"].after == task.uuid


def test_modify_refuses_to_clear_kind(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, message = _edit(entries, "a", kind=None)
    assert events == [] and "cannot be cleared" in message


def test_modify_refuses_a_future_end(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, message = _edit(entries, "a", til="23:00")
    assert events == [] and "future" in message


def test_modify_refuses_an_end_at_or_before_the_start(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, message = _edit(entries, "a", til="8:00")
    assert events == [] and "before it starts" in message


def test_modify_reports_when_nothing_would_change(at_1100):
    entries = _rows(_e(kind="solo", from_=_at(9), til=_at(9, 30)))
    events, message = _edit(entries, "a", kind="solo")
    assert events == [] and "Nothing to change" in message


def test_modify_needs_a_row(at_1100):
    events, message = _edit(_rows(_e(from_=_at(9), til=_at(9, 30))), [])
    assert events == [] and "No row given" in message


def test_modify_reports_an_unknown_letter(at_1100):
    events, message = _edit(_rows(_e(from_=_at(9), til=_at(9, 30))), "z", til="9:45")
    assert events == [] and "No row z" in message


def test_modify_refuses_more_than_one_row(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)))
    events, message = _edit(entries, ["a", "b"], til="9:45")
    assert events == [] and "one row at a time" in message


def test_modify_refuses_tags(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, message = _entry_modify(
        entries, [], ParsedFilter(letters=["a"]), ParsedModification(tags=["+x"]), _cfg())
    assert events == [] and "Tags are not valid" in message


# --- delete ---

def test_delete_removes_the_row(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)))
    events, message = _rm(entries, "b")
    assert [type(e) for e in events] == [EntryDeletedEvent]
    assert "Deleted" in message


def test_deleting_mid_chain_lets_the_next_row_absorb_the_slot(at_1100):
    from task.events import apply_entry_event

    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)), _e(til=_at(12)))
    events, _ = _rm(entries, "b")
    remaining = entries
    for event in events:
        remaining = apply_entry_event(remaining, event)
    rows = resolve(remaining)
    assert rows[1].start == _at(9, 30) and rows[1].end == _at(12)


def test_deleting_the_days_first_row_promotes_its_successor_to_an_anchor(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)))
    events, _ = _rm(entries, "a")
    promotion = next(e for e in events if isinstance(e, EntryUpdatedEvent))
    assert promotion.changes["from_"].after == _at(9)


def test_promotion_keeps_the_rest_of_the_day_resolvable(at_1100):
    from task.events import apply_entry_event

    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(til=_at(11)))
    events, _ = _rm(entries, "a")
    remaining = entries
    for event in events:
        remaining = apply_entry_event(remaining, event)
    rows = resolve(remaining)
    assert rows[0].start == _at(9) and rows[0].end == _at(11)


def test_no_promotion_when_the_successor_is_already_anchored(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(from_=_at(10), til=_at(11)))
    events, _ = _rm(entries, "a")
    assert all(isinstance(e, EntryDeletedEvent) for e in events)


def test_delete_needs_a_row(at_1100):
    events, message = _rm(_rows(_e(from_=_at(9), til=_at(9, 30))), [])
    assert events == [] and "No row given" in message


# --- open rows on log ---

def test_log_can_leave_a_row_open(at_1100):
    previous = _e(from_=_at(9), til=_at(9, 30))
    events, _ = _log([previous], description="writing docs", kind="solo", til=None)
    assert events[0].snapshot.til is None


def test_log_refuses_to_chain_off_an_open_row(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(description="open one"))
    events, message = _log(entries, description="next", kind="solo", til="10:00")
    assert events == [] and "still open" in message


def test_log_refuses_a_second_open_row(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)), _e(description="open one"))
    events, message = _log(entries, description="another", kind="solo", til=None, **{"from": "10:00"})
    assert events == [] and "already open" in message


# ---------------------------------------------------------------------------
# config: kinds vocabulary, shortcuts, day boundary (docs/config.md)
# ---------------------------------------------------------------------------

def test_unknown_kind_is_refused_with_the_valid_list(at_1100):
    events, message = _log([], description="x", kind="meting", **{"from": "9:00"})
    assert events == []
    assert "meting" in message and "solo, chat, meeting, call, junk" in message


def test_kinds_vocabulary_is_configurable(at_1100):
    cfg = _cfg(kinds=["solo", "admin"])
    events, _ = _log([], description="x", kind="admin", cfg=cfg, **{"from": "9:00"})
    assert events[0].snapshot.kind == "admin"


def test_a_kind_outside_the_configured_list_is_refused(at_1100):
    cfg = _cfg(kinds=["solo", "admin"])
    events, message = _log([], description="x", kind="meeting", cfg=cfg, **{"from": "9:00"})
    assert events == [] and "Valid kinds: solo, admin" in message


def test_modify_also_validates_the_kind(at_1100):
    entries = _rows(_e(from_=_at(9), til=_at(9, 30)))
    events, message = _edit(entries, "a", kind="nonsense")
    assert events == [] and "Unknown kind" in message


# --- shortcuts ---

def _with_shortcuts():
    return _cfg(shortcuts={
        "standup": Shortcut(description="team standup", kind="meeting", project="internal"),
        "mtg": Shortcut(kind="meeting"),
    })


def test_shortcut_supplies_every_field(at_1100):
    events, _ = _log([], description="standup", cfg=_with_shortcuts(), **{"from": "9:00"})
    entry = events[0].snapshot
    assert (entry.description, entry.kind, entry.project) == ("team standup", "meeting", "internal")


def test_shortcut_can_supply_only_a_kind(at_1100):
    events, _ = _log([], description="mtg", project="acme", cfg=_with_shortcuts(), **{"from": "9:00"})
    entry = events[0].snapshot
    assert entry.kind == "meeting" and entry.project == "acme" and entry.description == ""


def test_explicit_fields_beat_the_shortcut(at_1100):
    events, _ = _log(
        [], description="standup", kind="call", project="elsewhere",
        cfg=_with_shortcuts(), **{"from": "9:00"},
    )
    entry = events[0].snapshot
    assert entry.kind == "call" and entry.project == "elsewhere"


def test_trailing_words_replace_the_shortcut_description(at_1100):
    events, _ = _log([], description="standup about the parser",
                     cfg=_with_shortcuts(), **{"from": "9:00"})
    assert events[0].snapshot.description == "about the parser"


def test_shortcut_is_only_recognised_as_the_first_word(at_1100):
    events, message = _log([], description="about standup", cfg=_with_shortcuts(), **{"from": "9:00"})
    assert events == [] and "No kind given" in message


def test_an_unconfigured_word_is_not_a_shortcut(at_1100):
    events, message = _log([], description="whatever", cfg=_with_shortcuts(), **{"from": "9:00"})
    assert events == [] and "No kind given" in message


# --- day boundary ---

def test_day_boundary_is_honoured_by_log(at_1100):
    """With a noon boundary, a 09:00 row belongs to the previous logical day."""
    cfg = _cfg(day_starts_at=time(12, 0))
    events, _ = _log([], description="x", kind="solo", cfg=cfg, **{"from": "9:00", "til": "9:30"})
    rows = resolve([events[0].snapshot], day_starts_at=time(12, 0))
    assert rows[0].day == date(2026, 8, 28)


def test_day_boundary_is_honoured_by_the_day_view(at_1100, capsys):
    cfg = _cfg(day_starts_at=time(12, 0))
    day_(_a_day(), [], ParsedFilter(), _mod(), cfg)
    assert "Friday 28 Aug" in capsys.readouterr().out
