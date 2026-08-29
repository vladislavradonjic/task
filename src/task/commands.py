"""Command implementations."""

import calendar as _calendar
import json
import re
import shutil
import sys
from datetime import date as _date, datetime, timedelta as _timedelta
from pathlib import Path
from uuid import UUID

from rich.console import Console
from rich.table import Table
from task.models import CreatedEvent, DeletedEvent, DoneEvent, Entry, EntryDeletedEvent, EntryUpdatedEvent, FieldChange, LoggedEvent, ParsedFilter, ParsedModification, Event, Task, UpdatedEvent, UndoneEvent
from task.storage import active_context, append_event, assign_display_ids, assign_display_letters, data_dir as get_data_dir, effective_events, load_events, rebuild_entries, rebuild_tasks, save_entries_snapshot, save_snapshot
from task.dates import parse_date, parse_duration_seconds
from task.urgency import compute_urgency


def command_names() -> set[str]:
    return {
        name[:-1]
        for name, obj in globals().items()
        if name.endswith("_") and not name.startswith("_") and callable(obj)
    }


def _read_state(d: Path) -> dict:
    return json.loads((d / "state.json").read_text(encoding="utf-8"))


def _init_context_dir(ctx: Path) -> None:
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / "meta.json").write_text(json.dumps({"version": 1}, indent=2), encoding="utf-8", newline="\n")
    (ctx / "events.jsonl").touch()
    (ctx / "tasks.json").write_text("[]", encoding="utf-8", newline="\n")
    (ctx / "recaps").mkdir(exist_ok=True)
    (ctx / ".gitattributes").write_text("events.jsonl merge=union\n", encoding="utf-8", newline="\n")
    (ctx / ".gitignore").write_text("tasks.json\nentries.json\n", encoding="utf-8", newline="\n")


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


def _is_acyclic(g) -> bool:
    import networkx as nx

    return nx.is_directed_acyclic_graph(g)


def _build_graph(tasks: list[Task]):
    """DiGraph where edge X→Y means Y depends on X (X blocks Y)."""
    import networkx as nx

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

    Usage: tsk add <description> [+tag] [-tag] [property:value]
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


def _fmt_interval(seconds: float, past: bool = False) -> str:
    if seconds < 60:
        s = f"{int(seconds)}s"
    elif seconds < 3600:
        s = f"{int(seconds // 60)}m"
    elif seconds < 86400:
        s = f"{int(seconds // 3600)}h"
    elif seconds < 365 * 86400:
        s = f"{int(seconds // 86400)}d"
    else:
        s = f"{int(seconds // (365 * 86400))}y"
    return f"{s} ago" if past else s


def _render_task_table(visible: list[Task], all_tasks: list[Task]) -> None:
    from rich import box as _box
    now = datetime.now()
    urgency_scores = compute_urgency(all_tasks)
    visible = sorted(visible, key=lambda t: (-urgency_scores.get(t.uuid, 0.0), t.entry))

    _RESERVED_TAGS = {"today", "week"}
    show_tags = any(tag for t in visible for tag in t.tags if tag not in _RESERVED_TAGS)
    show_priority = any("priority" in t.properties for t in visible)
    show_due = any(t.due is not None for t in visible)
    show_project = any("project" in t.properties for t in visible)
    show_urgency = any(urgency_scores.get(t.uuid, 0.0) != 0.0 for t in visible)
    has_flags = any(
        "today" in t.tags or "week" in t.tags
        for t in visible
    )

    table = Table(show_header=True, box=_box.SIMPLE_HEAD)
    table.add_column("ID", style="bold", overflow="ellipsis")
    table.add_column("Description", overflow="fold")
    if show_tags:
        table.add_column("Tags", overflow="ellipsis")
    if show_priority:
        table.add_column("Pri", overflow="ellipsis")
    if show_due:
        table.add_column("Due", overflow="ellipsis")
    if show_project:
        table.add_column("Project", overflow="ellipsis")
    if show_urgency:
        table.add_column("Urgency", overflow="ellipsis")
    table.add_column("Age", overflow="ellipsis")

    active_uuids = {t.uuid for t in all_tasks if t.status in ("pending", "waiting")}
    blocked_uuids = {t.uuid for t in visible if any(dep in active_uuids for dep in t.depends)}

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
            id_cell = f"{id_str}{list_flag}"
        else:
            id_cell = id_str
        row = [id_cell, task.description]
        if show_tags:
            row.append(" ".join(f"+{t}" for t in task.tags if t not in _RESERVED_TAGS))
        if show_priority:
            pri = task.properties.get("priority", "")
            if pri == "H":
                row.append("[red]H[/red]")
            elif pri == "M":
                row.append("[yellow]M[/yellow]")
            else:
                row.append(pri)
        if show_due:
            if task.due is not None:
                diff = (task.due.replace(tzinfo=None) - now).total_seconds()
                due_str = _fmt_interval(-diff, past=True) if diff < 0 else _fmt_interval(diff)
                row.append(f"[red]{due_str}[/red]" if diff < 0 else due_str)
            else:
                row.append("")
        if show_project:
            row.append(task.properties.get("project", ""))
        if show_urgency:
            row.append(f"{urgency_scores.get(task.uuid, 0.0):.1f}")
        age_s = max(0.0, (now - task.entry.replace(tzinfo=None)).total_seconds())
        row.append(_fmt_interval(age_s, past=True))
        if task.uuid in blocked_uuids or task.status == "waiting":
            row_style = "dim"
        else:
            row_style = None
        table.add_row(*row, style=row_style)

    Console().print(table)


def _project_match(task_project: str | None, prefix: str) -> bool:
    if task_project is None:
        return False
    return task_project == prefix or task_project.startswith(prefix + ".")


def list_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """List tasks.

    Usage: tsk [filter] list [status:pending|waiting|done] [project:<prefix>]

    Shows pending always; waiting only when fewer than 10 pending exist.
    project:work matches work and any work.* subtree.
    """
    status_filter = filter_args.properties.get("status")
    if status_filter:
        visible = [t for t in tasks if t.status == status_filter]
    else:
        pending = [t for t in tasks if t.status == "pending"]
        waiting = [t for t in tasks if t.status == "waiting"]
        visible = pending + (waiting if len(pending) < 10 else [])

    project_filter = filter_args.properties.get("project")
    if project_filter:
        visible = [t for t in visible if _project_match(t.properties.get("project"), project_filter)]

    if not visible:
        return [], "No tasks."

    _render_task_table(visible, tasks)
    return [], ""


def query_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Filter tasks with a polars expression.

    Usage: tsk query "<expression>"

    Example: task query "col('priority') == 'H'"
    Use & and | (not 'and'/'or') for boolean logic.
    Available columns: uuid, id, description, status, tags, entry, due, wait, end,
    plus any property names such as priority and project.
    """
    expr_str = modify_args.description.strip()
    if not expr_str:
        return [], 'No expression given. Usage: tsk query "<polars-expression>"'

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
        }
        for k in all_prop_keys:
            row[k] = task.properties.get(k)
        records.append(row)

    if not records:
        return [], "No tasks."

    import polars as pl

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

    Usage: tsk <id> done

    Refuses on waiting tasks — clear wait: first.
    """
    matched, err = _match_ids(tasks, filter_args, "done")
    if err:
        return [], err
    waiting = [t for t in matched if t.status == "waiting"]
    if waiting:
        desc = ", ".join(f'"{t.description}"' for t in waiting)
        return [], f"Task is waiting; clear wait: first: {desc}"
    events: list[Event] = []
    for t in matched:
        events.append(DoneEvent(task_id=t.uuid))
    return events, f"Marked {_fmt(matched)} done."


def delete_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Delete tasks.

    Usage: tsk <id> delete
    """
    matched, err = _match_ids(tasks, filter_args, "deleted")
    if err:
        return [], err
    events: list[Event] = []
    for t in matched:
        events.append(DeletedEvent(task_id=t.uuid))
    return events, f"Deleted {_fmt(matched)}."


def _parse_date_prop(raw: str | None) -> tuple[datetime | None, str]:
    if raw is None:
        return None, ""
    try:
        return parse_date(raw), ""
    except ValueError as e:
        return None, str(e)


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
                if not _is_acyclic(g):
                    return {}, "Adding dependency would create a cycle."
        if new_deps != list(task.depends):
            changes["depends"] = FieldChange(before=list(task.depends), after=new_deps)

    if "due" in modify_args.properties:
        new_due, err = _parse_date_prop(modify_args.properties["due"])
        if err:
            return {}, err
        if new_due != task.due:
            changes["due"] = FieldChange(before=task.due, after=new_due)

    if "wait" in modify_args.properties:
        new_wait, err = _parse_date_prop(modify_args.properties["wait"])
        if err:
            return {}, err
        if new_wait != task.wait:
            changes["wait"] = FieldChange(before=task.wait, after=new_wait)
        if new_wait is not None and new_wait > datetime.now() and task.status == "pending":
            changes["status"] = FieldChange(before=task.status, after="waiting")
        elif new_wait is None and task.status == "waiting":
            changes["status"] = FieldChange(before=task.status, after="pending")

    return changes, ""


def modify_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Modify task fields.

    Usage: tsk <id> modify [description] [+tag] [-tag] [property:value] [property:]

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

    Usage: tsk <id> depends <id>[,<id>...] | -<id>

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
        if not _is_acyclic(g):
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

    Usage: tsk <id> blocks <id>[,<id>...]

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
        if not _is_acyclic(g):
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

    Usage: tsk undo

    Walks the event log backward and reverses the most recent change.
    """
    d = get_data_dir()
    ctx = active_context(d)
    all_events = load_events(ctx)

    target = next(reversed(effective_events(all_events)), None)

    if target is None:
        return [], "Nothing to undo."

    # Task and timesheet events name their subject differently.
    entry_id = getattr(target, "entry_id", None)
    task_id = getattr(target, "task_id", None)
    if entry_id is not None:
        desc = next(
            (e.snapshot.description or e.snapshot.kind
             for e in all_events if isinstance(e, LoggedEvent) and e.entry_id == entry_id),
            str(entry_id),
        )
    else:
        desc = next(
            (e.snapshot.description for e in all_events if isinstance(e, CreatedEvent) and e.task_id == task_id),
            str(task_id),
        )

    append_event(ctx, UndoneEvent(
        task_id=task_id, entry_id=entry_id, undid_ts=target.ts, undid_type=target.type,
    ))
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)
    save_entries_snapshot(ctx, rebuild_entries(ctx))

    return [], f'Undid {target.type} on "{desc}".'


def _ctx_show(d: Path) -> str:
    return _read_state(d)["active"]


def _ctx_list(d: Path) -> str:
    active = _read_state(d)["active"]
    contexts = sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "meta.json").exists())
    return "\n".join(f"{'*' if c == active else ' '} {c}" for c in contexts)


def _ctx_use(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: tsk context use <name>"
    if not (d / name / "meta.json").exists():
        return f"Context '{name}' does not exist. Run `tsk context list`."
    state_file = d / "state.json"
    state = _read_state(d)
    state["active"] = name
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8", newline="\n")
    return f"Active context: {name}"


def _ctx_create(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: tsk context create <name>"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        return f"Invalid context name: {name!r}. Must start with a letter; letters, digits, underscores, hyphens only."
    ctx = d / name
    if ctx.exists():
        return f"Context '{name}' already exists."
    _init_context_dir(ctx)
    return f"Created context '{name}'."


def _ctx_delete(d: Path, name: str | None) -> str:
    if name is None:
        return "Usage: tsk context delete <name>"
    active = _read_state(d)["active"]
    if name == active:
        return f"Cannot delete the active context '{name}'. Switch first with `tsk context use <other>`."
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

    Usage: tsk help [command]

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

    Usage: tsk context [list|use <name>|create <name>|delete <name>]

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


def _tag_list_cmd(
    tag: str,
    tasks: list[Task],
    filter_args: ParsedFilter,
    modify_args: ParsedModification,
) -> tuple[list[Event], str]:
    subcmd = modify_args.description.strip().lower()

    if subcmd == "clear":
        targets = [t for t in tasks if tag in t.tags and t.status in ("pending", "waiting")]
        if not targets:
            return [], f"No tasks tagged +{tag}."
        events = [
            UpdatedEvent(
                task_id=t.uuid,
                changes={"tags": FieldChange(before=list(t.tags), after=[x for x in t.tags if x != tag])},
            )
            for t in targets
        ]
        return events, f"Cleared +{tag} from {_fmt(targets)}."

    if filter_args.ids:
        matched, err = _match_ids(tasks, filter_args, f"added to +{tag}")
        if err:
            return [], err
        events = []
        changed = []
        for t in matched:
            if tag not in t.tags:
                events.append(
                    UpdatedEvent(
                        task_id=t.uuid,
                        changes={"tags": FieldChange(before=list(t.tags), after=list(t.tags) + [tag])},
                    )
                )
                changed.append(t)
        if not events:
            return [], f"All matched tasks already tagged +{tag}."
        return events, f"Added +{tag} to {_fmt(changed)}."

    visible = [t for t in tasks if tag in t.tags and t.status in ("pending", "waiting")]
    if not visible:
        return [], f"No tasks tagged +{tag}."
    _render_task_table(visible, tasks)
    return [], ""


def today_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Manage the daily list.

    Usage: tsk [<ids>] today [clear]

    Bare: list tasks tagged +today. With IDs: add +today. 'clear': remove +today from all.
    """
    return _tag_list_cmd("today", tasks, filter_args, modify_args)


def week_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Manage the weekly list.

    Usage: tsk [<ids>] week [clear]

    Bare: list tasks tagged +week. With IDs: add +week. 'clear': remove +week from all.
    """
    return _tag_list_cmd("week", tasks, filter_args, modify_args)


def _in_period(dt: datetime | None, start: datetime, end: datetime) -> bool:
    if dt is None:
        return False
    return start <= dt.replace(tzinfo=None) <= end


def _load_template(period: str, cfg) -> str:
    if cfg.recap.template_dir:
        override = Path(cfg.recap.template_dir).expanduser() / f"{period}.md.j2"
        if override.exists():
            return override.read_text(encoding="utf-8")
    from importlib.resources import files as _res_files
    return (_res_files("task") / "templates" / f"{period}.md.j2").read_text(encoding="utf-8")


def _hm(seconds) -> str:
    """Jinja filter: seconds (or a timedelta) as H:MM, so templates stay readable."""
    if hasattr(seconds, "total_seconds"):
        seconds = seconds.total_seconds()
    total = int(seconds or 0)
    return f"{total // 3600}:{(total % 3600) // 60:02d}"


def _timesheet_for_period(context: Path, first_day, last_day, cfg):
    """Timesheet rows whose logical day falls in the period, plus the two rollups.

    Rows are flattened to dicts rather than passed as ResolvedEntry, so templates say
    `row.kind` instead of `row.entry.kind`.
    """
    from task.storage import load_entries
    from task.timesheet import resolve, rollup

    day_starts_at = cfg.timesheet.day_starts_at
    resolved = [
        r for r in resolve(load_entries(context), day_starts_at)
        if r.day is not None and first_day <= r.day <= last_day
    ]
    rows = [
        {
            "day": r.day,
            "start": r.start,
            "end": r.end,
            "duration_s": r.duration.total_seconds() if r.duration else 0.0,
            "kind": r.entry.kind,
            "project": r.entry.project,
            "description": r.entry.description,
            "open": r.is_open,
        }
        for r in resolved
    ]
    by_kind = {k: v.total_seconds() for k, v in rollup(resolved, "kind").items()}
    by_project = {p: v.total_seconds() for p, v in rollup(resolved, "project").items()}
    return rows, by_kind, by_project, sum(by_kind.values())


def recap_(
    tasks: list[Task],
    filter_args: ParsedFilter,
    modify_args: ParsedModification,
    *,
    context: Path,
    cfg,
) -> tuple[list[Event], str]:
    """Generate a recap document.

    Usage: tsk recap day|week|month

    Writes a markdown summary of what was planned and what got done.
    Prompts before overwriting an existing file (default: No).
    """
    period = modify_args.description.strip().lower()
    if period not in ("day", "week", "month"):
        return [], "Usage: tsk recap day|week|month"

    now = datetime.now()
    today = now.date()

    if period == "day":
        period_start = datetime(today.year, today.month, today.day)
        period_end = datetime(today.year, today.month, today.day, 23, 59, 59, 999999)
        period_date: _date = today
    elif period == "week":
        monday = today - _timedelta(days=today.weekday())
        period_start = datetime(monday.year, monday.month, monday.day)
        period_end = period_start + _timedelta(days=7) - _timedelta(microseconds=1)
        period_date = monday
    else:
        period_start = datetime(today.year, today.month, 1)
        last_day = _calendar.monthrange(today.year, today.month)[1]
        period_end = datetime(today.year, today.month, last_day, 23, 59, 59, 999999)
        period_date = _date(today.year, today.month, 1)

    done_in_period = [t for t in tasks if t.status == "done" and _in_period(t.end, period_start, period_end)]
    due_in_period = [t for t in tasks if _in_period(t.due, period_start, period_end)]
    overdue_in_period = [t for t in due_in_period if t.status != "done"]
    today_list = [t for t in tasks if "today" in t.tags and t.status in ("pending", "waiting")] if period == "day" else []
    week_list = [t for t in tasks if "week" in t.tags and t.status in ("pending", "waiting")] if period == "week" else []

    rows, by_kind, by_project, total_s = _timesheet_for_period(
        context, period_start.date(), period_end.date(), cfg
    )

    template_text = _load_template(period, cfg)

    from jinja2 import Environment
    env = Environment(trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters["hm"] = _hm
    content = env.from_string(template_text).render(
        date=period_date,
        period=period,
        today_list=today_list,
        week_list=week_list,
        due_in_period=due_in_period,
        overdue_in_period=overdue_in_period,
        done_in_period=done_in_period,
        rows_in_period=rows,
        time_by_kind=by_kind,
        time_by_project=by_project,
        total_tracked_in_period=total_s,
    )

    out_dir = Path(cfg.recap.output_dir).expanduser() if cfg.recap.output_dir else context / "recaps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"recap-{period}-{period_date.strftime('%Y-%m-%d')}.md"

    if out_path.exists():
        if not sys.stdin.isatty():
            return [], f"File already exists: {out_path}; run interactively to overwrite."
        answer = input(f"Overwrite {out_path}? [y/N] ")
        if answer.strip().lower() != "y":
            return [], "Recap not written."

    out_path.write_text(content, encoding="utf-8", newline="\n")
    return [], f"Wrote {out_path}"


def _render_count_table(counts: dict[str, int], col_name: str) -> None:
    table = Table(show_header=True)
    table.add_column(col_name)
    table.add_column("Count", justify="right")
    for key, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        table.add_row(key, str(count))
    Console().print(table)


def tags_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """List tags in use.

    Usage: tsk tags

    Shows each tag and how many pending/waiting tasks carry it, sorted by count.
    """
    active = [t for t in tasks if t.status in ("pending", "waiting")]
    counts: dict[str, int] = {}
    for task in active:
        for tag in task.tags:
            counts[f"+{tag}"] = counts.get(f"+{tag}", 0) + 1

    if not counts:
        return [], "No tags in use."

    _render_count_table(counts, "Tag")
    return [], ""


def projects_(tasks: list[Task], filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """List projects in use.

    Usage: tsk projects

    Shows each project and how many pending/waiting tasks are assigned to it, sorted by count.
    """
    active = [t for t in tasks if t.status in ("pending", "waiting")]
    counts: dict[str, int] = {}
    for task in active:
        if proj := task.properties.get("project"):
            counts[proj] = counts.get(proj, 0) + 1

    if not counts:
        return [], "No projects in use."

    _render_count_table(counts, "Project")
    return [], ""


def init_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Initialize the task store.

    Usage: tsk init

    Creates the data directory and default context.
    """
    d = get_data_dir()
    state_file = d / "state.json"
    if state_file.exists():
        return [], f"Already initialized at {d}"
    d.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"version": 1, "active": "default"}, indent=2), encoding="utf-8", newline="\n")
    _init_context_dir(d / "default")
    return [], f"Initialized at {d}"


# --- timesheet ---------------------------------------------------------------
#
# Entry commands take (entries, tasks, filter, modify): entries are the subject, tasks
# are needed to resolve `task:<id>` and to render the link. See docs/timesheet.md.

_ENTRY_PROPS = {"kind", "project", "task", "from", "til", "for"}


def _resolve_moment(raw: str, now: datetime, day_starts_at) -> datetime:
    """A bare clock time lands inside the current logical day; anything else is a date."""
    from task.timesheet import resolve_clock

    try:
        clock = datetime.strptime(raw.strip(), "%H:%M").time()
    except ValueError:
        return parse_date(raw).replace(tzinfo=None)
    return resolve_clock(clock, now, day_starts_at)


def _day_end(now: datetime, day_starts_at) -> datetime:
    """The instant the current logical day ends — the ceiling for any `til:`."""
    from task.timesheet import day_window, logical_day

    return day_window(logical_day(now, day_starts_at), day_starts_at)[1]


def _fmt_day(day) -> str:
    """`Saturday 29 Aug`, without the day-of-month zero padding.

    `%-d` is a glibc extension: Windows' strftime rejects it with "Invalid format
    string", and `%#d` is the MSVC spelling. Interpolating the integer avoids both.
    """
    return f"{day:%A} {day.day} {day:%b}"


def _fmt_delta(delta) -> str:
    total = int(delta.total_seconds())
    return f"{total // 3600}:{(total % 3600) // 60:02d}"


def log_(
    entries: list[Entry],
    tasks: list[Task],
    filter_args: ParsedFilter,
    modify_args: ParsedModification,
    cfg,
) -> tuple[list[Event], str]:
    """Add a timesheet row.

    Usage: tsk log [description...] kind:<k> [project:<p>] [task:<id>] [from:<t>] [til:<t>] [for:<d>]

    The end defaults to now; the start is read from the previous row unless from: says
    otherwise. Times may be bare clock values (9:15) and resolve inside the current day.
    """
    from task.timesheet import logical_day, resolve

    day_starts_at = cfg.timesheet.day_starts_at
    now = datetime.now().replace(microsecond=0)

    if modify_args.tags:
        return [], "Tags are not valid on log; use kind: and project:."
    unknown = set(modify_args.properties) - _ENTRY_PROPS
    if unknown:
        return [], f"Unknown propert{'y' if len(unknown) == 1 else 'ies'} on log: {', '.join(sorted(unknown))}."

    description = modify_args.description.strip()
    kind = modify_args.properties.get("kind")
    project = modify_args.properties.get("project")

    # A shortcut is recognised only as the first description token, and only supplies
    # defaults — anything given explicitly wins.
    words = description.split()
    if words and words[0] in cfg.timesheet.shortcuts:
        shortcut = cfg.timesheet.shortcuts[words[0]]
        rest = " ".join(words[1:])
        description = rest or (shortcut.description or "")
        kind = kind or shortcut.kind
        project = project or shortcut.project

    if not kind:
        return [], "No kind given. Usage: tsk log <description> kind:<kind>"
    if kind not in cfg.timesheet.kinds:
        return [], f"Unknown kind {kind!r}. Valid kinds: {', '.join(cfg.timesheet.kinds)}."

    task_uuid = None
    raw_task = modify_args.properties.get("task")
    if raw_task:
        if not raw_task.isdigit():
            return [], f"task: expects a task id, got {raw_task!r}."
        match = next((t for t in tasks if t.id == int(raw_task)), None)
        if match is None:
            return [], f"No task with id {raw_task}."
        task_uuid = match.uuid

    try:
        explicit_from = (
            _resolve_moment(modify_args.properties["from"], now, day_starts_at)
            if modify_args.properties.get("from") else None
        )
        explicit_til = (
            _resolve_moment(modify_args.properties["til"], now, day_starts_at)
            if modify_args.properties.get("til") else None
        )
    except ValueError as e:
        return [], str(e)

    duration = None
    if modify_args.properties.get("for"):
        if explicit_from and explicit_til:
            return [], "Give at most two of from:, til: and for:."
        try:
            duration = _timedelta(seconds=parse_duration_seconds(modify_args.properties["for"]))
        except ValueError as e:
            return [], f"Invalid duration: {e}"
        if duration <= _timedelta(0):
            return [], "Duration must be positive."

    # `til:` with no value opens the row; an absent til: just defaults to now.
    leave_open = "til" in modify_args.properties and modify_args.properties["til"] is None

    til = explicit_til
    if til is None and not leave_open:
        til = explicit_from + duration if (explicit_from and duration) else now
    # A scheduled end may legitimately be ahead of the clock — you know a meeting runs
    # to 15:00 and correct it later if it overruns. Beyond today is still a typo.
    if til is not None and til >= _day_end(now, day_starts_at):
        return [], "Cannot log a row ending after today."

    _today_rows(entries, day_starts_at)  # assigns letters, so a refusal can name the row
    resolved = resolve(entries, day_starts_at)
    last = resolved[-1] if resolved else None

    from_ = explicit_from
    if from_ is None and duration is not None and til is not None:
        from_ = til - duration
    if from_ is None:
        # Derive from the previous row, but never across a logical day boundary —
        # otherwise the first row of a morning would swallow the night.
        reference = til or now
        if last is None:
            return [], "No earlier row today to continue from. Give from: or for:."
        if last.end is None:
            return [], (
                f"Row {last.entry.id or 'above'} is still open. Close it with "
                f"`<letter> modify til:<time>`, or give from:."
            )
        if logical_day(last.end, day_starts_at) != logical_day(reference, day_starts_at):
            return [], "No earlier row today to continue from. Give from: or for:."

    if leave_open and last is not None and last.end is None:
        return [], "A row is already open; close it before opening another."

    start = from_ if from_ is not None else (last.end if last is not None else None)
    if start is not None and til is not None and til <= start:
        return [], f"Row would end at or before it starts ({start:%H:%M})."

    entry = Entry(
        from_=from_,
        til=til,
        kind=kind,
        project=project,
        description=description,
        task=task_uuid,
    )
    label = entry.description or f"{kind}{' on ' + entry.project if entry.project else ''}"
    return [LoggedEvent(entry_id=entry.uuid, snapshot=entry)], f'Logged "{label}".'


def _today_rows(entries: list[Entry], day_starts_at):
    """Rows of the current logical day, lettered. Letters only address today."""
    from task.timesheet import logical_day, resolve_day

    day = logical_day(datetime.now(), day_starts_at)
    rows = resolve_day(entries, day, day_starts_at)
    assign_display_letters([r.entry for r in rows])
    return rows


def _match_letters(rows: list, filter_args: ParsedFilter, verb: str) -> tuple[list, str]:
    if not filter_args.letters:
        return [], f"No row given; nothing {verb}."
    wanted = set(filter_args.letters)
    matched = [r for r in rows if r.entry.id in wanted]
    if not matched:
        return [], f"No row {', '.join(sorted(wanted))} in today's timesheet."
    return matched, ""


def _entry_modify(
    entries: list[Entry],
    tasks: list[Task],
    filter_args: ParsedFilter,
    modify_args: ParsedModification,
    cfg,
) -> tuple[list[Event], str]:
    """Change a timesheet row. Reached as `tsk <letter> modify ...`.

    An empty value clears a field, matching `modify wait:` on tasks — `til:` reopens a
    row, `from:` hands it back to the derivation chain.
    """
    day_starts_at = cfg.timesheet.day_starts_at
    now = datetime.now().replace(microsecond=0)

    if modify_args.tags:
        return [], "Tags are not valid on a timesheet row; use kind: and project:."
    unknown = set(modify_args.properties) - _ENTRY_PROPS - {"for"}
    if unknown:
        return [], f"Unknown propert{'y' if len(unknown) == 1 else 'ies'}: {', '.join(sorted(unknown))}."

    rows = _today_rows(entries, day_starts_at)
    matched, err = _match_letters(rows, filter_args, "modified")
    if err:
        return [], err
    if len(matched) > 1:
        return [], "Can only modify one row at a time."
    row = matched[0]
    entry = row.entry

    changes: dict[str, FieldChange] = {}

    if modify_args.description.strip():
        changes["description"] = FieldChange(before=entry.description, after=modify_args.description.strip())

    for prop, field in (("kind", "kind"), ("project", "project")):
        if prop in modify_args.properties:
            after = modify_args.properties[prop] or None
            if field == "kind":
                if not after:
                    return [], "kind cannot be cleared; every row needs one."
                if after not in cfg.timesheet.kinds:
                    return [], f"Unknown kind {after!r}. Valid kinds: {', '.join(cfg.timesheet.kinds)}."
            if after != getattr(entry, field):
                changes[field] = FieldChange(before=getattr(entry, field), after=after)

    if "task" in modify_args.properties:
        raw = modify_args.properties["task"]
        if not raw:
            after = None
        elif not raw.isdigit():
            return [], f"task: expects a task id, got {raw!r}."
        else:
            match = next((t for t in tasks if t.id == int(raw)), None)
            if match is None:
                return [], f"No task with id {raw}."
            after = match.uuid
        if after != entry.task:
            changes["task"] = FieldChange(before=entry.task, after=after)

    for prop, field in (("from", "from_"), ("til", "til")):
        if prop not in modify_args.properties:
            continue
        raw = modify_args.properties[prop]
        if not raw:
            after = None
        else:
            try:
                after = _resolve_moment(raw, now, day_starts_at)
            except ValueError as e:
                return [], str(e)
        if after != getattr(entry, field):
            changes[field] = FieldChange(before=getattr(entry, field), after=after)

    if not changes:
        return [], "Nothing to change."

    til = changes["til"].after if "til" in changes else entry.til
    if til is not None and til >= _day_end(now, day_starts_at):
        return [], "Cannot set a row to end after today."
    start = changes["from_"].after if "from_" in changes else entry.from_
    if start is None:
        start = row.start
    if start is not None and til is not None and til <= start:
        return [], f"Row would end at or before it starts ({start:%H:%M})."

    label = entry.description or entry.kind
    return [EntryUpdatedEvent(entry_id=entry.uuid, changes=changes)], f'Updated "{label}".'


def _entry_delete(
    entries: list[Entry],
    tasks: list[Task],
    filter_args: ParsedFilter,
    modify_args: ParsedModification,
    cfg,
) -> tuple[list[Event], str]:
    """Remove timesheet rows. Reached as `tsk <letter> delete`.

    Deleting a row lets the next one absorb its slot, which happens for free mid-chain
    because starts are derived. The day's *first* row has no predecessor to derive from,
    so its successor is promoted to an anchor at the deleted row's start.
    """
    rows = _today_rows(entries, cfg.timesheet.day_starts_at)
    matched, err = _match_letters(rows, filter_args, "deleted")
    if err:
        return [], err

    events: list[Event] = []
    doomed = {r.entry.uuid for r in matched}
    for i, row in enumerate(rows):
        if row.entry.uuid not in doomed:
            continue
        successor = rows[i + 1] if i + 1 < len(rows) else None
        first_of_day = i == 0
        if (
            first_of_day
            and successor is not None
            and successor.entry.uuid not in doomed
            and successor.entry.from_ is None
            and row.start is not None
        ):
            events.append(EntryUpdatedEvent(
                entry_id=successor.entry.uuid,
                changes={"from_": FieldChange(before=None, after=row.start)},
            ))
        events.append(EntryDeletedEvent(entry_id=row.entry.uuid))

    labels = ", ".join(f'"{r.entry.description or r.entry.kind}"' for r in matched)
    return events, f"Deleted {labels}."


def _render_day_table(rows: list, tasks: list[Task], day) -> None:
    from rich import box as _box

    from task.timesheet import rollup, total_tracked

    by_uuid = {t.uuid: t for t in tasks}
    show_project = any(r.entry.project for r in rows)
    show_task = any(r.entry.task for r in rows)

    table = Table(
        show_header=True,
        box=_box.SIMPLE_HEAD,
        title=f"{_fmt_day(day)}   {_fmt_delta(total_tracked(rows))} tracked",
        title_justify="left",
        title_style="bold",
    )
    columns = ["", "Time", "Dur", "Kind"]
    if show_project:
        columns.append("Project")
    columns.append("Description")
    if show_task:
        columns.append("Task")
    for name in columns:
        table.add_column(
            name,
            style="bold" if name == "" else None,
            justify="right" if name == "Dur" else "left",
            overflow="fold" if name == "Description" else "ellipsis",
        )

    for r in rows:
        if r.gap_before and r.start is not None:
            gap = dict.fromkeys(columns, "")
            gap["Time"] = f"[dim]{r.start - r.gap_before:%H:%M}–{r.start:%H:%M}[/dim]"
            gap["Dur"] = f"[dim]{_fmt_delta(r.gap_before)}[/dim]"
            gap["Description"] = "[dim]untracked[/dim]"
            table.add_row(*(gap[c] for c in columns))

        start = f"{r.start:%H:%M}" if r.start else "?"
        end = f"{r.end:%H:%M}" if r.end else "  ?  "
        row = [
            r.entry.id or "-",
            f"{start}–{end}",
            _fmt_delta(r.duration) if r.duration else "open",
            r.entry.kind,
        ]
        if show_project:
            row.append(r.entry.project or "")
        row.append(r.entry.description)
        if show_task:
            linked = by_uuid.get(r.entry.task) if r.entry.task else None
            row.append(f"→{linked.id}" if linked and linked.id else "")
        table.add_row(*row, style="dim" if r.entry.kind == "junk" else None)

    console = Console()
    console.print(table)
    if rows:
        kinds = "  ".join(f"{k} {_fmt_delta(v)}" for k, v in rollup(rows, "kind").items())
        projects = "  ".join(
            f"{p or '—'} {_fmt_delta(v)}" for p, v in rollup(rows, "project").items()
        )
        console.print(f"  [dim]{kinds}[/dim]", highlight=False)
        console.print(f"  [dim]{projects}[/dim]", highlight=False)


def day_(
    entries: list[Entry],
    tasks: list[Task],
    filter_args: ParsedFilter,
    modify_args: ParsedModification,
    cfg,
) -> tuple[list[Event], str]:
    """Show the timesheet for a logical day.

    Usage: tsk day [<date>]

    Bare form shows today. A day runs from 04:00 to 04:00, so work past midnight stays
    with the evening it belongs to.
    """
    from task.timesheet import logical_day, resolve_day

    day_starts_at = cfg.timesheet.day_starts_at
    raw = modify_args.description.strip()
    if raw:
        # An explicit argument names a calendar date, and we show that date's logical day.
        # (Bare dates parse to midnight, which logical_day would push to the day before.)
        try:
            day = parse_date(raw).replace(tzinfo=None).date()
        except ValueError as e:
            return [], str(e)
    else:
        day = logical_day(datetime.now(), day_starts_at)

    rows = resolve_day(entries, day, day_starts_at)
    if not rows:
        return [], f"Nothing logged for {_fmt_day(day)}."
    assign_display_letters([r.entry for r in rows])
    _render_day_table(rows, tasks, day)
    return [], ""


def rebuild_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Rebuild the caches from the event log.

    Usage: tsk rebuild

    events.jsonl is canonical; tasks.json and entries.json are only caches. Use this
    if either is stale or was damaged; nothing is lost by running it.
    """
    d = get_data_dir()
    ctx = active_context(d)
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)
    entries = rebuild_entries(ctx)
    save_entries_snapshot(ctx, entries)
    return [], (
        f"Rebuilt {len(tasks)} task(s) and {len(entries)} timesheet row(s) "
        f"from {ctx / 'events.jsonl'}."
    )


def run_(filter_args: ParsedFilter, modify_args: ParsedModification) -> tuple[list[Event], str]:
    """Start the interactive REPL.

    Usage: tsk run

    Enters an interactive session. Type commands without the leading 'tsk'.
    Shows the task list with today's timesheet beneath it, re-rendered after each
    change. Type 'exit' or 'quit', or press Ctrl+D, to leave; Ctrl+C cancels the
    current input line.
    """
    return [], ""