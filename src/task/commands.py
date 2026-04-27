"""Command implementations. Dummy commands for now; real logic later."""

import json
from task.models import CreatedEvent, ParsedFilter, ParsedModification, Event, Task
from task.storage import data_dir as get_data_dir


def add_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    task = Task(description=modify_args.description)
    event = CreatedEvent(task_id=task.id, snapshot=task)
    return [event], f"Created task {task.id}"


def list_(filter_args: ParsedFilter, modify_args: ParsedModification) -> None:
    """Dummy list command."""
    print("filter_args:", filter_args)
    print("modify_args:", modify_args)


def init_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    d = get_data_dir()
    state_file = d / "state.json"
    if state_file.exists():
        return [], f"Already initialized at {d}"
    d.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"version": 1, "active": "default"}, indent=2))
    default_context = d / "default"
    default_context.mkdir(parents=True, exist_ok=True)
    (default_context / "meta.json").write_text(json.dumps({"version": 1}, indent=2))
    return [], f"Initialized at {d}"