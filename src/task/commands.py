"""Command implementations."""

import json
import re
import shutil
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from task.models import CreatedEvent, DeletedEvent, DoneEvent, FieldChange, ParsedFilter, ParsedModification, Event, Task, UpdatedEvent, UndoneEvent
from task.storage import active_context, append_event, assign_display_ids, data_dir as get_data_dir, load_events, rebuild_tasks, save_snapshot


def add_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Add a new task.

    Usage: task add <description> [+tag] [-tag] [property:value]
    """
    tags = [t.lstrip("+") for t in modify_args.tags if t.startswith("+")]
    task = Task(
        description=modify_args.description,
        tags=tags,
        properties={k: v for k, v in modify_args.properties.items() if v is not None},
    )
    event = CreatedEvent(task_id=task.uuid, snapshot=task)
    return [event], f"Created task {task.uuid}"


def list_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """List tasks.

    Usage: task [filter] list [status:pending|waiting|done]

    Shows pending always; waiting only when fewer than 10 pending exist.
    """
    status_filter = filter_args.properties.get("status")
    if status_filter:
        visible = [t for t in tasks if t.status == status_filter]
    else:
        pending = [t for t in tasks if t.status == "pending"]
        waiting = [t for t in tasks if t.status == "waiting"]
        visible = pending + (waiting if len(pending) < 10 else [])

    if not visible:
        return [], "No tasks."

    show_tags = any(t.tags for t in visible)
    show_project = any("project" in t.properties for t in visible)
    has_flags = any(
        "today" in t.tags or "week" in t.tags or t.start is not None
        for t in visible
    )

    table = Table(show_header=True)
    table.add_column("ID", style="bold", overflow="ellipsis")
    table.add_column("Description", overflow="fold")
    if show_tags:
        table.add_column("Tags", overflow="ellipsis")
    if show_project:
        table.add_column("Project", overflow="ellipsis")

    for task in visible:
        if has_flags:
            if "today" in task.tags and "week" in task.tags:
                list_flag = "*"
            elif "today" in task.tags:
                list_flag = "d"
            elif "week" in task.tags:
                list_flag = "w"
            else:
                list_flag = " "
            active_flag = ">" if task.start is not None else " "
            id_cell = f"{task.id}{list_flag}{active_flag}"
        else:
            id_cell = str(task.id)
        row = [id_cell, task.description]
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
    """Mark tasks done.

    Usage: task <id> done

    Refuses on waiting tasks — clear wait: first.
    """
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
    """Delete tasks.

    Usage: task <id> delete
    """
    if not filter_args.ids:
        return [], "No filter given; nothing deleted."
    matched = [t for t in tasks if t.id in set(filter_args.ids)]
    if not matched:
        return [], "No matching tasks."
    events = [DeletedEvent(task_id=t.uuid) for t in matched]
    return events, f"Deleted {_fmt(matched)}."


def _compute_changes(task: Task, modify_args: ParsedModification) -> dict[str, FieldChange]:
    changes: dict[str, FieldChange] = {}

    if modify_args.description and modify_args.description != task.description:
        changes["description"] = FieldChange(before=task.description, after=modify_args.description)

    if modify_args.tags:
        new_tags = list(task.tags)
        for tag in modify_args.tags:
            if tag.startswith("+"):
                name = tag[1:]
                if name not in new_tags:
                    new_tags.append(name)
            else:
                name = tag[1:]
                new_tags = [t for t in new_tags if t != name]
        if new_tags != task.tags:
            changes["tags"] = FieldChange(before=list(task.tags), after=new_tags)

    if modify_args.properties:
        new_props = dict(task.properties)
        for k, v in modify_args.properties.items():
            if v is None:
                new_props.pop(k, None)
            else:
                new_props[k] = v
        if new_props != task.properties:
            changes["properties"] = FieldChange(before=dict(task.properties), after=new_props)

    return changes


def modify_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Modify task fields.

    Usage: task <id> modify [description] [+tag] [-tag] [property:value] [property:]

    Use property: (empty value) to clear a field.
    """
    if not filter_args.ids:
        return [], "No filter given; nothing modified."
    matched = [t for t in tasks if t.id in set(filter_args.ids)]
    if not matched:
        return [], "No matching tasks."
    events = []
    for task in matched:
        changes = _compute_changes(task, modify_args)
        if changes:
            events.append(UpdatedEvent(task_id=task.uuid, changes=changes))
    if not events:
        return [], "Nothing to change."
    return events, f"Modified {_fmt(matched)}."


def undo_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Undo the last action.

    Usage: task undo

    Walks the event log backward and reverses the most recent change.
    """
    d = get_data_dir()
    ctx = active_context(d)
    events = load_events(ctx)

    undone_ts = {e.undid_ts for e in events if isinstance(e, UndoneEvent)}

    target = None
    for event in reversed(events):
        if isinstance(event, UndoneEvent) or event.ts in undone_ts:
            continue
        target = event
        break

    if target is None:
        return [], "Nothing to undo."

    desc = next(
        (e.snapshot.description for e in events if isinstance(e, CreatedEvent) and e.task_id == target.task_id),
        str(target.task_id),
    )

    append_event(ctx, UndoneEvent(task_id=target.task_id, undid_ts=target.ts, undid_type=target.type))
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    return [], f'Undid {target.type} on "{desc}".'


def _ctx_show(d: Path) -> str:
    return json.loads((d / "state.json").read_text())["active"]


def _ctx_list(d: Path) -> str:
    active = json.loads((d / "state.json").read_text())["active"]
    contexts = sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "meta.json").exists())
    return "\n".join(f"{'*' if c == active else ' '} {c}" for c in contexts)


def _ctx_use(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: task context use <name>"
    if not (d / name / "meta.json").exists():
        return f"Context '{name}' does not exist. Run `task context list`."
    state_file = d / "state.json"
    state = json.loads(state_file.read_text())
    state["active"] = name
    state_file.write_text(json.dumps(state, indent=2))
    return f"Active context: {name}"


def _ctx_create(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: task context create <name>"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        return f"Invalid context name: {name!r}. Must start with a letter; letters, digits, underscores, hyphens only."
    ctx = d / name
    if ctx.exists():
        return f"Context '{name}' already exists."
    ctx.mkdir(parents=True)
    (ctx / "meta.json").write_text(json.dumps({"version": 1}, indent=2))
    (ctx / "events.jsonl").touch()
    (ctx / "tasks.json").write_text("[]")
    (ctx / "recaps").mkdir()
    return f"Created context '{name}'."


def _ctx_delete(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: task context delete <name>"
    active = json.loads((d / "state.json").read_text())["active"]
    if name == active:
        return f"Cannot delete the active context '{name}'. Switch first with `task context use <other>`."
    ctx = d / name
    if not ctx.exists():
        return f"Context '{name}' does not exist."
    if not sys.stdin.isatty():
        return "Cannot confirm deletion non-interactively; run in a TTY."
    answer = input(f"Delete context '{name}' and all its tasks? [y/N] ")
    if answer.strip().lower() != "y":
        return "Deletion cancelled."
    shutil.rmtree(ctx)
    return f"Deleted context '{name}'."


def help_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Show help.

    Usage: task help [command]

    Bare form lists all commands. With a command name, shows its full description.
    """
    import task.commands as _mod

    target = modify_args.description.strip() if modify_args.description else None

    if target:
        fn = getattr(_mod, f"{target}_", None)
        if fn is None or not callable(fn):
            return [], f"Unknown command: {target!r}"
        return [], (fn.__doc__ or "(no description)").strip()

    names = sorted(
        name[:-1]
        for name in dir(_mod)
        if name.endswith("_") and not name.startswith("_") and callable(getattr(_mod, name))
    )
    lines = []
    for name in names:
        fn = getattr(_mod, f"{name}_")
        doc = (fn.__doc__ or "").strip()
        first_line = doc.splitlines()[0] if doc else "(no description)"
        lines.append(f"  {name:<12}{first_line}")
    return [], "\n".join(lines)


def context_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Manage contexts.

    Usage: task context [list|use <name>|create <name>|delete <name>]

    Bare form shows the active context.
    """
    d = get_data_dir()
    parts = modify_args.description.split() if modify_args.description else []
    subcmd = parts[0] if parts else None
    name = parts[1] if len(parts) > 1 else None

    match subcmd:
        case None:
            return [], _ctx_show(d)
        case "list":
            return [], _ctx_list(d)
        case "use":
            return [], _ctx_use(d, name)
        case "create":
            return [], _ctx_create(d, name)
        case "delete":
            return [], _ctx_delete(d, name)
        case _:
            return [], f"Unknown context subcommand: {subcmd!r}"


def init_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Initialize the task store.

    Usage: task init

    Creates the data directory and default context.
    """
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