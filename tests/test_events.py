import json
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from task.events import apply_entry_event, apply_event
from task.models import (
    CreatedEvent, DeletedEvent, DoneEvent, Entry, EntryDeletedEvent, EntryUpdatedEvent,
    Event, FieldChange, LoggedEvent, Task, UpdatedEvent,
)

_event_adapter = TypeAdapter(Event)


def test_apply_created_to_empty():
    task = Task(description="buy milk")
    result = apply_event([], CreatedEvent(task_id=task.uuid, snapshot=task))
    assert result == [task]


def test_apply_created_appends():
    existing = Task(description="existing")
    new = Task(description="new")
    result = apply_event([existing], CreatedEvent(task_id=new.uuid, snapshot=new))
    assert result == [existing, new]


def test_apply_done_sets_status_and_end():
    task = Task(description="buy milk")
    event = DoneEvent(task_id=task.uuid)
    result = apply_event([task], event)
    assert result[0].status == "done"
    assert result[0].end == event.ts


def test_apply_done_leaves_other_tasks_unchanged():
    t1 = Task(description="first")
    t2 = Task(description="second")
    result = apply_event([t1, t2], DoneEvent(task_id=t1.uuid))
    assert result[1].status == "pending"


def test_apply_deleted_sets_status():
    task = Task(description="buy milk")
    result = apply_event([task], DeletedEvent(task_id=task.uuid))
    assert result[0].status == "deleted"


def test_apply_deleted_leaves_other_tasks_unchanged():
    t1 = Task(description="first")
    t2 = Task(description="second")
    result = apply_event([t1, t2], DeletedEvent(task_id=t1.uuid))
    assert result[1].status == "pending"


def test_apply_updated_patches_fields():
    task = Task(description="old", tags=["a"])
    event = UpdatedEvent(
        task_id=task.uuid,
        changes={
            "description": FieldChange(before="old", after="new"),
            "tags": FieldChange(before=["a"], after=["a", "b"]),
        },
    )
    result = apply_event([task], event)
    assert result[0].description == "new"
    assert result[0].tags == ["a", "b"]


def test_apply_updated_leaves_other_tasks_unchanged():
    t1 = Task(description="first")
    t2 = Task(description="second")
    event = UpdatedEvent(
        task_id=t1.uuid,
        changes={"description": FieldChange(before="first", after="updated")},
    )
    result = apply_event([t1, t2], event)
    assert result[1].description == "second"


def test_apply_updated_coerces_uuid_strings_in_depends():
    # Simulates replay from disk: FieldChange.after arrives as JSON strings, not UUID objects.
    dep_uuid = UUID("12345678-1234-5678-1234-567812345678")
    task = Task(description="test")
    event = UpdatedEvent(
        task_id=task.uuid,
        changes={"depends": FieldChange(before=[], after=[str(dep_uuid)])},
    )
    result = apply_event([task], event)
    assert result[0].depends == [dep_uuid]
    assert isinstance(result[0].depends[0], UUID)


# ---------------------------------------------------------------------------
# apply_entry_event — the timesheet reducer (docs/timesheet.md)
# ---------------------------------------------------------------------------

def _entry(**kw):
    return Entry(**{"kind": "solo", **kw})


def test_apply_logged_to_empty():
    entry = _entry(description="write the parser")
    assert apply_entry_event([], LoggedEvent(entry_id=entry.uuid, snapshot=entry)) == [entry]


def test_apply_logged_appends_in_order():
    first, second = _entry(description="a"), _entry(description="b")
    entries = apply_entry_event([], LoggedEvent(entry_id=first.uuid, snapshot=first))
    entries = apply_entry_event(entries, LoggedEvent(entry_id=second.uuid, snapshot=second))
    assert [e.description for e in entries] == ["a", "b"]


def test_apply_entry_updated_changes_only_the_target():
    target, other = _entry(description="target"), _entry(description="other")
    event = EntryUpdatedEvent(
        entry_id=target.uuid,
        changes={"til": FieldChange(before=None, after=datetime(2026, 8, 29, 11, 30))},
    )
    result = apply_entry_event([target, other], event)
    assert result[0].til == datetime(2026, 8, 29, 11, 30)
    assert result[1] == other


def test_apply_entry_updated_can_set_several_fields():
    entry = _entry(description="rough")
    event = EntryUpdatedEvent(
        entry_id=entry.uuid,
        changes={
            "kind": FieldChange(before="solo", after="meeting"),
            "project": FieldChange(before=None, after="acme"),
            "description": FieldChange(before="rough", after="client sync"),
        },
    )
    updated = apply_entry_event([entry], event)[0]
    assert (updated.kind, updated.project, updated.description) == ("meeting", "acme", "client sync")


def test_apply_entry_updated_can_clear_a_field():
    entry = _entry(til=datetime(2026, 8, 29, 11, 0))
    event = EntryUpdatedEvent(
        entry_id=entry.uuid,
        changes={"til": FieldChange(before=datetime(2026, 8, 29, 11, 0), after=None)},
    )
    assert apply_entry_event([entry], event)[0].til is None


def test_apply_entry_updated_preserves_uuid():
    entry = _entry(description="x")
    event = EntryUpdatedEvent(entry_id=entry.uuid, changes={"kind": FieldChange(before="solo", after="junk")})
    assert apply_entry_event([entry], event)[0].uuid == entry.uuid


def test_apply_entry_updated_is_a_no_op_for_unknown_id():
    entry = _entry(description="x")
    event = EntryUpdatedEvent(entry_id=uuid4(), changes={"kind": FieldChange(before="solo", after="junk")})
    assert apply_entry_event([entry], event) == [entry]


def test_apply_entry_deleted_removes_the_row_outright():
    doomed, kept = _entry(description="doomed"), _entry(description="kept")
    result = apply_entry_event([doomed, kept], EntryDeletedEvent(entry_id=doomed.uuid))
    assert result == [kept]


def test_apply_entry_deleted_is_a_no_op_for_unknown_id():
    entry = _entry(description="x")
    assert apply_entry_event([entry], EntryDeletedEvent(entry_id=uuid4())) == [entry]


# --- the two reducers must ignore each other's events ---

def test_apply_entry_event_ignores_task_events():
    entry = _entry(description="x")
    task = Task(description="a task")
    assert apply_entry_event([entry], CreatedEvent(task_id=task.uuid, snapshot=task)) == [entry]


def test_apply_event_ignores_entry_events():
    task = Task(description="a task")
    entry = _entry(description="x")
    assert apply_event([task], LoggedEvent(entry_id=entry.uuid, snapshot=entry)) == [task]


def test_entry_round_trips_through_json():
    entry = _entry(
        from_=datetime(2026, 8, 29, 9, 0),
        til=datetime(2026, 8, 29, 9, 30),
        project="acme.parse",
        description="počisti bazu",
        task=uuid4(),
    )
    event = LoggedEvent(entry_id=entry.uuid, snapshot=entry)
    revived = _event_adapter.validate_json(event.model_dump_json())
    assert revived.snapshot == entry


def test_open_row_has_no_til():
    assert _entry(from_=datetime(2026, 8, 29, 13, 15)).til is None


def test_display_letter_is_excluded_from_serialisation():
    entry = _entry(description="x")
    entry.id = "b"
    assert "id" not in json.loads(entry.model_dump_json())
