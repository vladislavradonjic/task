from task.events import apply_event
from task.models import CreatedEvent, Task


def test_apply_created_to_empty():
    task = Task(description="buy milk")
    result = apply_event([], CreatedEvent(task_id=task.id, snapshot=task))
    assert result == [task]


def test_apply_created_appends():
    existing = Task(description="existing")
    new = Task(description="new")
    result = apply_event([existing], CreatedEvent(task_id=new.id, snapshot=new))
    assert result == [existing, new]
