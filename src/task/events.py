from task.models import CreatedEvent, Event, Task


def apply_event(tasks: list[Task], event: Event) -> list[Task]:
    match event:
        case CreatedEvent():
            return [*tasks, event.snapshot]
    return tasks
