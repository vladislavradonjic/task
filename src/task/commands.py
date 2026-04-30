"""Command implementations."""

import json
import re
import shutil
import sys
from datetime import date as _date, datetime, timedelta as _timedelta
from pathlib import Path
from uuid import UUID

import polars as pl

import networkx as nx
from rich.console import Console
from rich.table import Table
from task.models import CreatedEvent, DeletedEvent, DoneEvent, FieldChange, ParsedFilter, ParsedModification, Event, Task, UpdatedEvent, UndoneEvent
from task.storage import active_context, append_event, assign_display_ids, data_dir as get_data_dir, effective_events, load_events, rebuild_tasks, save_snapshot
from task.dates import parse_date
from task.urgency import compute_urgency


def command_names() -> set[str]:
    return {
        name[:-1]
        for name, obj in globals().items()
        if name.endswith("_") and not name.startswith("_") and callable(obj)
    }


def _read_state(d: Path) -> dict:
    return json.loads((d / "state.json").read_text())


def _init_context_dir(ctx: Path) -> None:
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / "meta.json").write_text(json.dumps({"version": 1}, indent=2))
    (ctx / "events.jsonl").touch()
    (ctx / "tasks.json").write_text("[]")
    (ctx / "recaps").mkdir(exist_ok=True)


def _match_ids(tasks: list[Task], filter_args: ParsedFilter, verb: str) -> tuple[list[Task], str]:
    if not filter_args.ids:
        return [], f"No filter given; nothing {verb}."
    matched = [t for t in tasks if t.id in set(filter_args.ids)]
    if not matched:
        return [], "No matching tasks."
    return matched, ""


def _parse_dep_ids(text: str) -> tuple[list[int], list[int]]:
    """Parse signed/unsigned IDs from a depends description. Returns (to_add, to_remove)."""
    to_add, to_remove = [], []
    for part in re.split(r'[\s,]+', text.strip()):
        if not part:
            continue
        if part.startswith('-') and part[1:].isdigit():
            to_remove.append(int(part[1:]))
        elif part.startswith('+') and part[1:].isdigit():
            to_add.append(int(part[1:]))
        elif part.isdigit():
            to_add.append(int(part))
    return to_add, to_remove


def _build_graph(tasks: list[Task]) -> nx.DiGraph:
    """DiGraph where edge X→Y means Y depends on X (X blocks Y)."""
    g = nx.DiGraph()
    g.add_nodes_from(t.uuid for t in tasks)
    for task in tasks:
        for dep_uuid in task.depends:
            g.add_edge(dep_uuid, task.uuid)
    return g


def _apply_dep_changes(
    current: list[UUID],
    to_add: list[UUID],
    to_remove: set[UUID],
    self_uuid: UUID,
) -> list[UUID]:
    """Return new depends list: removes then adds, deduplicating, excluding self."""
    result = [u for u in current if u not in to_remove]
    for u in to_add:
        if u not in result and u != self_uuid:
            result.append(u)
    return result


def add_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Add a new task.

    Usage: task add <description> [+tag] [-tag] [property:value]
    """
    tags = [t.lstrip("+") for t in modify_args.tags if t.startswith("+")]

    raw = dict(modify_args.properties)
    due: datetime | None = None
    wait: datetime | None = None

    if due_str := raw.pop("due", None):
        try:
            due = parse_date(due_str)
        except ValueError as e:
            return [], f"Invalid due date: {e}"

    if wait_str := raw.pop("wait", None):
        try:
            wait = parse_date(wait_str)
        except ValueError as e:
            return [], f"Invalid wait date: {e}"

    status = "waiting" if (wait is not None and wait > datetime.now()) else "pending"
    task = Task(
        description=modify_args.description,
        status=status,
        tags=tags,
        due=due,
        wait=wait,
        properties={k: v for k, v in raw.items() if v is not None},
    )
    event = CreatedEvent(task_id=task.uuid, snapshot=task)
    return [event], f"Created task {task.uuid}"


def _render_task_table(visible: list[Task], all_tasks: list[Task]) -> None:
    urgency_scores = compute_urgency(all_tasks)
    visible = sorted(visible, key=lambda t: (-urgency_scores.get(t.uuid, 0.0), t.entry))

    show_tags = any(t.tags for t in visible)
    show_project = any("project" in t.properties for t in visible)
    show_urgency = any(urgency_scores.get(t.uuid, 0.0) != 0.0 for t in visible)
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
    if show_urgency:
        table.add_column("Urgency", overflow="ellipsis")

    for task in visible:
        id_str = str(task.id) if task.id is not None else "-"
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
            id_cell = f"{id_str}{list_flag}{active_flag}"
        else:
            id_cell = id_str
        row = [id_cell, task.description]
        if show_tags:
            row.append(" ".join(f"+{t}" for t in task.tags))
        if show_project:
            row.append(task.properties.get("project", ""))
        if show_urgency:
            row.append(f"{urgency_scores.get(task.uuid, 0.0):.1f}")
        table.add_row(*row)

    Console().print(table)


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

    _render_task_table(visible, tasks)
    return [], ""


def query_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Filter tasks with a polars expression.

    Usage: task query "<expression>"

    Example: task query "col('priority') == 'H'"
    Use & and | (not 'and'/'or') for boolean logic.
    Available columns: uuid, id, description, status, tags, entry, due, wait, end, start,
    plus any property names such as priority and project.
    """
    expr_str = modify_args.description.strip()
    if not expr_str:
        return [], 'No expression given. Usage: task query "<polars-expression>"'

    all_prop_keys: set[str] = set()
    for t in tasks:
        all_prop_keys.update(t.properties.keys())

    records: list[dict] = []
    for task in tasks:
        row: dict = {
            "uuid": str(task.uuid),
            "id": task.id,
            "description": task.description,
            "status": task.status,
            "tags": task.tags,
            "entry": task.entry,
            "due": task.due,
            "wait": task.wait,
            "end": task.end,
            "start": task.start,
        }
        for k in all_prop_keys:
            row[k] = task.properties.get(k)
        records.append(row)

    if not records:
        return [], "No tasks."

    try:
        df = pl.from_dicts(records, infer_schema_length=None)
    except Exception as e:
        return [], f"Error building query table: {e}"

    try:
        polars_expr = eval(
            expr_str,
            {"col": pl.col, "pl": pl, "date": _date, "datetime": datetime, "timedelta": _timedelta},
        )
        result = df.filter(polars_expr)
    except SyntaxError as e:
        return [], f"Syntax error in expression: {e}"
    except Exception as e:
        return [], f"Query error: {e}"

    if result.is_empty():
        return [], "No matching tasks."

    matched_uuids = {UUID(u) for u in result["uuid"].to_list()}
    matched = [t for t in tasks if t.uuid in matched_uuids]
    _render_task_table(matched, tasks)
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
    matched, err = _match_ids(tasks, filter_args, "done")
    if err:
        return [], err
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
    matched, err = _match_ids(tasks, filter_args, "deleted")
    if err:
        return [], err
    events = [DeletedEvent(task_id=t.uuid) for t in matched]
    return events, f"Deleted {_fmt(matched)}."


def _compute_changes(
    task: Task,
    modify_args: ParsedModification,
    all_tasks: list[Task],
) -> tuple[dict[str, FieldChange], str]:
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

    other_props = {k: v for k, v in modify_args.properties.items() if k not in ("depends", "due", "wait")}
    if other_props:
        new_props = dict(task.properties)
        for k, v in other_props.items():
            if v is None:
                new_props.pop(k, None)
            else:
                new_props[k] = v
        if new_props != task.properties:
            changes["properties"] = FieldChange(before=dict(task.properties), after=new_props)

    if "depends" in modify_args.properties:
        dep_value = modify_args.properties["depends"]
        if dep_value is None:
            new_deps: list[UUID] = []
        else:
            to_add_ids, to_remove_ids = _parse_dep_ids(dep_value)
            id_map = {t.id: t.uuid for t in all_tasks if t.id is not None}
            missing = [i for i in to_add_ids + to_remove_ids if i not in id_map]
            if missing:
                return {}, f"Unknown task ID(s): {', '.join(str(i) for i in missing)}"
            to_add_uuids = [id_map[i] for i in to_add_ids]
            to_remove_uuids = {id_map[i] for i in to_remove_ids}
            new_deps = _apply_dep_changes(task.depends, to_add_uuids, to_remove_uuids, task.uuid)
            if to_add_uuids:
                g = _build_graph(all_tasks)
                for u in to_add_uuids:
                    if u != task.uuid:
                        g.add_edge(u, task.uuid)
                if not nx.is_directed_acyclic_graph(g):
                    return {}, "Adding dependency would create a cycle."
        if new_deps != list(task.depends):
            changes["depends"] = FieldChange(before=list(task.depends), after=new_deps)

    if "due" in modify_args.properties:
        raw_due = modify_args.properties["due"]
        if raw_due is None:
            new_due: datetime | None = None
        else:
            try:
                new_due = parse_date(raw_due)
            except ValueError as e:
                return {}, str(e)
        if new_due != task.due:
            changes["due"] = FieldChange(before=task.due, after=new_due)

    if "wait" in modify_args.properties:
        raw_wait = modify_args.properties["wait"]
        if raw_wait is None:
            new_wait: datetime | None = None
        else:
            try:
                new_wait = parse_date(raw_wait)
            except ValueError as e:
                return {}, str(e)
        if new_wait != task.wait:
            changes["wait"] = FieldChange(before=task.wait, after=new_wait)
        if new_wait is not None and new_wait > datetime.now() and task.status == "pending":
            changes["status"] = FieldChange(before=task.status, after="waiting")
        elif new_wait is None and task.status == "waiting":
            changes["status"] = FieldChange(before=task.status, after="pending")

    return changes, ""


def modify_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Modify task fields.

    Usage: task <id> modify [description] [+tag] [-tag] [property:value] [property:]

    Use property: (empty value) to clear a field.
    """
    matched, err = _match_ids(tasks, filter_args, "modified")
    if err:
        return [], err
    events = []
    for task in matched:
        changes, err = _compute_changes(task, modify_args, tasks)
        if err:
            return [], err
        if changes:
            events.append(UpdatedEvent(task_id=task.uuid, changes=changes))
    if not events:
        return [], "Nothing to change."
    return events, f"Modified {_fmt(matched)}."


def depends_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Add or remove task dependencies.

    Usage: task <id> depends <id>[,<id>...] | -<id>

    Unsigned or +-prefixed IDs are added; --prefixed IDs are removed.
    Adding a duplicate or self-reference is a no-op. Cycles are rejected.
    """
    matched, err = _match_ids(tasks, filter_args, "modified")
    if err:
        return [], err

    if not modify_args.description.strip():
        return [], "No dependency IDs given."

    to_add_ids, to_remove_ids = _parse_dep_ids(modify_args.description)
    id_map = {t.id: t.uuid for t in tasks if t.id is not None}

    missing = [i for i in to_add_ids + to_remove_ids if i not in id_map]
    if missing:
        return [], f"Unknown task ID(s): {', '.join(str(i) for i in missing)}"

    to_add_uuids = [id_map[i] for i in to_add_ids]
    to_remove_uuids = {id_map[i] for i in to_remove_ids}

    if to_add_uuids:
        g = _build_graph(tasks)
        for task in matched:
            for u in to_add_uuids:
                if u != task.uuid:
                    g.add_edge(u, task.uuid)
        if not nx.is_directed_acyclic_graph(g):
            return [], "Adding dependency would create a cycle."

    events = []
    for task in matched:
        new_deps = _apply_dep_changes(task.depends, to_add_uuids, to_remove_uuids, task.uuid)
        if new_deps != list(task.depends):
            events.append(UpdatedEvent(task_id=task.uuid, changes={
                "depends": FieldChange(before=list(task.depends), after=new_deps),
            }))

    if not events:
        return [], "Nothing to change."
    return events, f"Updated dependencies on {_fmt(matched)}."


def blocks_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Add or remove blocking relationships.

    Usage: task <id> blocks <id>[,<id>...]

    'task A blocks B' means B depends on A. Prefix IDs with - to remove.
    """
    matched, err = _match_ids(tasks, filter_args, "modified")
    if err:
        return [], err

    if not modify_args.description.strip():
        return [], "No target IDs given."

    to_add_ids, to_remove_ids = _parse_dep_ids(modify_args.description)
    id_map = {t.id: t.uuid for t in tasks if t.id is not None}
    uuid_to_task = {t.uuid: t for t in tasks}

    missing = [i for i in to_add_ids + to_remove_ids if i not in id_map]
    if missing:
        return [], f"Unknown task ID(s): {', '.join(str(i) for i in missing)}"

    blocker_uuids = [t.uuid for t in matched]
    blocker_set = set(blocker_uuids)
    add_targets = [id_map[i] for i in to_add_ids]
    remove_targets = {id_map[i] for i in to_remove_ids}

    if add_targets:
        g = _build_graph(tasks)
        for target_uuid in add_targets:
            target_task = uuid_to_task[target_uuid]
            for u in blocker_uuids:
                if u not in target_task.depends and u != target_uuid:
                    g.add_edge(u, target_uuid)
        if not nx.is_directed_acyclic_graph(g):
            return [], "Adding blocking relationship would create a cycle."

    events = []
    for target_uuid in set(add_targets) | remove_targets:
        target_task = uuid_to_task[target_uuid]
        new_deps = _apply_dep_changes(
            target_task.depends,
            blocker_uuids if target_uuid in set(add_targets) else [],
            blocker_set if target_uuid in remove_targets else set(),
            target_uuid,
        )
        if new_deps != list(target_task.depends):
            events.append(UpdatedEvent(task_id=target_uuid, changes={
                "depends": FieldChange(before=list(target_task.depends), after=new_deps),
            }))

    if not events:
        return [], "Nothing to change."
    return events, "Updated blocking relationships."


def undo_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Undo the last action.

    Usage: task undo

    Walks the event log backward and reverses the most recent change.
    """
    d = get_data_dir()
    ctx = active_context(d)
    all_events = load_events(ctx)

    target = next(reversed(effective_events(all_events)), None)

    if target is None:
        return [], "Nothing to undo."

    desc = next(
        (e.snapshot.description for e in all_events if isinstance(e, CreatedEvent) and e.task_id == target.task_id),
        str(target.task_id),
    )

    append_event(ctx, UndoneEvent(task_id=target.task_id, undid_ts=target.ts, undid_type=target.type))
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    return [], f'Undid {target.type} on "{desc}".'


def _ctx_show(d: Path) -> str:
    return _read_state(d)["active"]


def _ctx_list(d: Path) -> str:
    active = _read_state(d)["active"]
    contexts = sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "meta.json").exists())
    return "\n".join(f"{'*' if c == active else ' '} {c}" for c in contexts)


def _ctx_use(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: task context use <name>"
    if not (d / name / "meta.json").exists():
        return f"Context '{name}' does not exist. Run `task context list`."
    state_file = d / "state.json"
    state = _read_state(d)
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
    _init_context_dir(ctx)
    return f"Created context '{name}'."


def _ctx_delete(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: task context delete <name>"
    active = _read_state(d)["active"]
    if name == active:
        return f"Cannot delete the active context '{name}'. Switch first with `task context use <other>`."
    ctx = d / name
    if not (ctx / "meta.json").exists():
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
    target = modify_args.description.strip() if modify_args.description else None

    if target:
        fn = globals().get(f"{target}_")
        if fn is None or not callable(fn):
            return [], f"Unknown command: {target!r}"
        return [], (fn.__doc__ or "(no description)").strip()

    lines = []
    for name in sorted(command_names()):
        fn = globals()[f"{name}_"]
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
    _init_context_dir(d / "default")
    return [], f"Initialized at {d}"