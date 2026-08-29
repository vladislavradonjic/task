from task.models import CreatedEvent, DeletedEvent, DoneEvent, Event, Task, UpdatedEvent


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
        case UpdatedEvent():
            return [
                Task.model_validate({
                    **t.model_dump(mode="python"),
                    **{f: c.after for f, c in event.changes.items()},
                })
                if t.uuid == event.task_id else t
                for t in tasks
            ]
    return tasks
