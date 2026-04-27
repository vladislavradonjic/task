"""Command implementations. Dummy commands for now; real logic later."""

from task.models import CreatedEvent, ParsedFilter, ParsedModification, Event, Task


def add_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    task = Task(description=modify_args.description)
    event = CreatedEvent(task_id=task.id, snapshot=task)
    return [event], f"Created task {task.id}"


def list_(filter_args: ParsedFilter, modify_args: ParsedModification) -> None:
    """Dummy list command."""
    print("filter_args:", filter_args)
    print("modify_args:", modify_args)


def init_(filter_args: ParsedFilter, modify_args: ParsedModification) -> None:
    """Dummy init command."""
    print("filter_args:", filter_args)
    print("modify_args:", modify_args)
