from task.models import CreatedEvent, DeletedEvent, DoneEvent, Event, Task


def apply_event(tasks: list[Task], event: Event) -> list[Task]:
    match event:
        case CreatedEvent():
            return [*tasks, event.snapshot]
        case DoneEvent():
            return [
                t.model_copy(update={"status": "done", "end": event.ts})
                if t.uuid == event.task_id else t
                for t in tasks
            ]
        case DeletedEvent():
            return [
                t.model_copy(update={"status": "deleted"})
                if t.uuid == event.task_id else t
                for t in tasks
            ]
    return tasks
