"""Command implementations."""

import json
from rich.console import Console
from rich.table import Table
from task.models import CreatedEvent, DeletedEvent, DoneEvent, ParsedFilter, ParsedModification, Event, Task
from task.storage import data_dir as get_data_dir


def add_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    tags = [t.lstrip("+") for t in modify_args.tags if t.startswith("+")]
    task = Task(
        description=modify_args.description,
        tags=tags,
        properties={k: v for k, v in modify_args.properties.items() if v is not None},
    )
    event = CreatedEvent(task_id=task.uuid, snapshot=task)
    return [event], f"Created task {task.uuid}"


def list_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    pending = [t for t in tasks if t.status == "pending"]
    waiting = [t for t in tasks if t.status == "waiting"]
    visible = pending + (waiting if len(pending) < 10 else [])

    if not visible:
        return [], "No tasks."

    show_tags = any(t.tags for t in visible)
    show_project = any("project" in t.properties for t in visible)

    table = Table(show_header=True)
    table.add_column("ID", style="bold")
    table.add_column("Description", overflow="fold")
    if show_tags:
        table.add_column("Tags")
    if show_project:
        table.add_column("Project")

    for task in visible:
        row = [str(task.id), task.description]
        if show_tags:
            row.append(" ".join(f"+{t}" for t in task.tags))
        if show_project:
            row.append(task.properties.get("project", ""))
        table.add_row(*row)

    Console().print(table)
    return [], ""


def _fmt(tasks: list[Task]) -> str:
    if len(tasks) == 1:
        return f'"{tasks[0].description}"'
    return f"{len(tasks)} tasks"


def done_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    if not filter_args.ids:
        return [], "No filter given; nothing done."
    matched = [t for t in tasks if t.id in set(filter_args.ids)]
    if not matched:
        return [], "No matching tasks."
    waiting = [t for t in matched if t.status == "waiting"]
    if waiting:
        desc = ", ".join(f'"{t.description}"' for t in waiting)
        return [], f"Task is waiting; clear wait: first: {desc}"
    events = [DoneEvent(task_id=t.uuid) for t in matched]
    return events, f"Marked {_fmt(matched)} done."


def delete_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    if not filter_args.ids:
        return [], "No filter given; nothing deleted."
    matched = [t for t in tasks if t.id in set(filter_args.ids)]
    if not matched:
        return [], "No matching tasks."
    events = [DeletedEvent(task_id=t.uuid) for t in matched]
    return events, f"Deleted {_fmt(matched)}."


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