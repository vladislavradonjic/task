from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from task.commands import start_, stop_, log_
from task.dates import parse_duration_seconds
from task.events import apply_event
from task.models import ParsedFilter, ParsedModification, StartedEvent, StoppedEvent, Task
from task.storage import assign_display_ids


def _now():
    return datetime(2026, 4, 15, 10, 0, 0)


def _tasks(*specs):
    tasks = [Task(**s) for s in specs]
    assign_display_ids(tasks)
    return tasks


# ---------------------------------------------------------------------------
# parse_duration_seconds
# ---------------------------------------------------------------------------

def test_duration_hours_only():
    assert parse_duration_seconds("2h") == 7200


def test_duration_minutes_min():
    assert parse_duration_seconds("30min") == 1800


def test_duration_minutes_m():
    assert parse_duration_seconds("45m") == 2700


def test_duration_combined():
    assert parse_duration_seconds("1h30m") == 5400


def test_duration_combined_min():
    assert parse_duration_seconds("1h30min") == 5400


def test_duration_invalid():
    with pytest.raises(ValueError, match="unrecognized duration"):
        parse_duration_seconds("notaduration")


def test_duration_negative_not_supported():
    with pytest.raises(ValueError):
        parse_duration_seconds("-1h")


# ---------------------------------------------------------------------------
# start_
# ---------------------------------------------------------------------------

def test_start_pending_task():
    tasks = _tasks({"description": "fix parser"})
    events, message = start_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], StartedEvent)
    assert events[0].task_id == tasks[0].uuid
    assert "fix parser" in message


def test_start_sets_active():
    tasks = _tasks({"description": "fix parser"})
    events, _ = start_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    result = apply_event(tasks, events[0])
    assert result[0].start is not None


def test_start_captures_note():
    tasks = _tasks({"description": "fix parser"})
    events, _ = start_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="debugging the crash"))
    assert events[0].note == "debugging the crash"


def test_start_waiting_refused():
    tasks = _tasks({"description": "waiting task", "status": "waiting"})
    events, message = start_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert events == []
    assert "waiting" in message.lower()


def test_start_done_refused():
    # done tasks have no display ID in normal use; force an ID so _match_ids can find it
    task = Task(description="done task", status="done")
    task.id = 1
    events, message = start_([task], ParsedFilter(ids=[1]), ParsedModification())
    assert events == []
    assert "done" in message.lower()


def test_start_already_active_errors():
    start_time = _now()
    tasks = _tasks({"description": "active task", "start": start_time})
    events, message = start_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert events == []
    assert "already active" in message.lower()


def test_start_auto_stops_other_active():
    start_time = _now() - timedelta(hours=1)
    tasks = _tasks(
        {"description": "currently active", "start": start_time},
        {"description": "new task"},
    )
    events, _ = start_(tasks, ParsedFilter(ids=[2]), ParsedModification())
    assert len(events) == 2
    assert isinstance(events[0], StoppedEvent)
    assert events[0].task_id == tasks[0].uuid
    assert isinstance(events[1], StartedEvent)
    assert events[1].task_id == tasks[1].uuid


def test_start_auto_stop_has_correct_duration():
    start_time = _now() - timedelta(hours=2)
    tasks = _tasks(
        {"description": "active", "start": start_time},
        {"description": "new"},
    )
    with patch("task.commands.datetime") as mock_dt:
        mock_dt.now.return_value = _now()
        events, _ = start_(tasks, ParsedFilter(ids=[2]), ParsedModification())
    stop_ev = events[0]
    assert isinstance(stop_ev, StoppedEvent)
    assert stop_ev.duration_s == pytest.approx(7200, abs=1)


def test_start_tags_refused():
    tasks = _tasks({"description": "task"})
    events, message = start_(tasks, ParsedFilter(ids=[1]), ParsedModification(tags=["+bug"]))
    assert events == []
    assert "not valid" in message.lower()


def test_start_properties_refused():
    tasks = _tasks({"description": "task"})
    events, message = start_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"project": "x"}))
    assert events == []
    assert "not valid" in message.lower()


def test_start_empty_filter_errors():
    tasks = _tasks({"description": "task"})
    events, message = start_(tasks, ParsedFilter(), ParsedModification())
    assert events == []
    assert "No filter" in message


# ---------------------------------------------------------------------------
# stop_
# ---------------------------------------------------------------------------

def test_stop_bare_targets_active():
    tasks = _tasks({"description": "active task", "start": _now() - timedelta(minutes=30)})
    events, message = stop_(tasks, ParsedFilter(), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], StoppedEvent)
    assert events[0].task_id == tasks[0].uuid
    assert "active task" in message


def test_stop_bare_clears_start():
    tasks = _tasks({"description": "active task", "start": _now() - timedelta(minutes=30)})
    events, _ = stop_(tasks, ParsedFilter(), ParsedModification())
    result = apply_event(tasks, events[0])
    assert result[0].start is None


def test_stop_bare_no_active():
    tasks = _tasks({"description": "task"})
    events, message = stop_(tasks, ParsedFilter(), ParsedModification())
    assert events == []
    assert "No task" in message


def test_stop_captures_note():
    tasks = _tasks({"description": "active", "start": _now() - timedelta(minutes=10)})
    events, _ = stop_(tasks, ParsedFilter(), ParsedModification(description="found the bug"))
    assert events[0].note == "found the bug"


def test_stop_records_duration():
    elapsed = timedelta(minutes=45)
    tasks = _tasks({"description": "active", "start": _now() - elapsed})
    with patch("task.commands.datetime") as mock_dt:
        mock_dt.now.return_value = _now()
        events, _ = stop_(tasks, ParsedFilter(), ParsedModification())
    assert events[0].duration_s == pytest.approx(elapsed.total_seconds(), abs=1)


def test_stop_with_id():
    tasks = _tasks({"description": "active task", "start": _now() - timedelta(minutes=30)})
    events, message = stop_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], StoppedEvent)


def test_stop_with_wrong_id_errors():
    tasks = _tasks(
        {"description": "active", "start": _now() - timedelta(minutes=5)},
        {"description": "not active"},
    )
    events, message = stop_(tasks, ParsedFilter(ids=[2]), ParsedModification())
    assert events == []
    assert "not active" in message.lower()


def test_stop_task_not_active_errors():
    tasks = _tasks({"description": "task"})
    events, message = stop_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert events == []
    assert "not active" in message.lower()


# ---------------------------------------------------------------------------
# log_
# ---------------------------------------------------------------------------

def test_log_basic():
    tasks = _tasks({"description": "task"})
    events, message = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2h"))
    assert len(events) == 2
    assert isinstance(events[0], StartedEvent)
    assert isinstance(events[1], StoppedEvent)
    assert "task" in message


def test_log_does_not_affect_active():
    tasks = _tasks({"description": "task"})
    events, _ = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="1h"))
    assert events[0].affects_active is False
    assert events[1].affects_active is False
    # applying them leaves start unchanged
    result = tasks
    for e in events:
        result = apply_event(result, e)
    assert result[0].start is None


def test_log_correct_duration():
    tasks = _tasks({"description": "task"})
    events, _ = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="90m"))
    assert events[1].duration_s == pytest.approx(5400, abs=1)


def test_log_start_is_end_minus_duration():
    tasks = _tasks({"description": "task"})
    events, _ = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="1h"))
    gap = (events[1].ts - events[0].ts).total_seconds()
    assert gap == pytest.approx(3600, abs=1)


def test_log_with_at():
    tasks = _tasks({"description": "task"})
    events, _ = log_(
        tasks, ParsedFilter(ids=[1]),
        ParsedModification(description="30min", properties={"at": "2026-04-15T12:00"}),
    )
    assert events[1].ts == datetime(2026, 4, 15, 12, 0, 0)
    assert events[0].ts == datetime(2026, 4, 15, 11, 30, 0)


def test_log_captures_note():
    tasks = _tasks({"description": "task"})
    events, _ = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="1h working on tests"))
    assert events[0].note == "working on tests"
    assert events[1].note == "working on tests"


def test_log_no_duration_errors():
    tasks = _tasks({"description": "task"})
    events, message = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description=""))
    assert events == []
    assert "duration" in message.lower()


def test_log_invalid_duration_errors():
    tasks = _tasks({"description": "task"})
    events, message = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="notaduration"))
    assert events == []
    assert "duration" in message.lower()


def test_log_tags_refused():
    tasks = _tasks({"description": "task"})
    events, message = log_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="1h", tags=["+bug"]))
    assert events == []
    assert "not allowed" in message.lower()


# ---------------------------------------------------------------------------
# Auto-stop on done and delete
# ---------------------------------------------------------------------------

def test_done_auto_stops_active():
    tasks = _tasks({"description": "active task", "start": _now() - timedelta(minutes=30)})
    from task.commands import done_
    from task.models import DoneEvent
    events, _ = done_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 2
    assert isinstance(events[0], StoppedEvent)
    assert isinstance(events[1], DoneEvent)


def test_done_non_active_no_stop_event():
    tasks = _tasks({"description": "task"})
    from task.commands import done_
    from task.models import DoneEvent
    events, _ = done_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)


def test_delete_auto_stops_active():
    tasks = _tasks({"description": "active task", "start": _now() - timedelta(minutes=30)})
    from task.commands import delete_
    from task.models import DeletedEvent
    events, _ = delete_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 2
    assert isinstance(events[0], StoppedEvent)
    assert isinstance(events[1], DeletedEvent)
