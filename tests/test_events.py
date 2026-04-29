from task.events import apply_event
from task.models import CreatedEvent, DeletedEvent, DoneEvent, FieldChange, Task, UpdatedEvent


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
