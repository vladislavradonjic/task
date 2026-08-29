import json, os
from datetime import datetime
from pathlib import Path
from pydantic import TypeAdapter
from task.models import Entry, Event, FieldChange, Task, UpdatedEvent, UndoneEvent
from task.events import apply_entry_event, apply_event

CURRENT_STATE_VERSION = 1
CURRENT_CONTEXT_VERSION = 1

_event_adapter = TypeAdapter(Event)


def data_dir() -> Path:
    override = os.environ.get("TASK_DATA_DIR")
    if override:
        return Path(override)
    from platformdirs import user_data_dir
    return Path(user_data_dir("task", appauthor=False))


def active_context(data_dir: Path) -> Path:
    override = os.environ.get("TASK_CONTEXT")
    if override:
        return data_dir / override
    
    state = data_dir / "state.json"
    if state.exists():
        active = json.loads(state.read_text(encoding="utf-8"))["active"]
    else:
        active = "default"
    return data_dir / active


def load_events(context: Path) -> list[Event]:
    events_file = context / "events.jsonl"
    if not events_file.exists():
        return []
    return [
        _event_adapter.validate_json(line)
        for line in events_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def effective_events(events: list[Event]) -> list[Event]:
    undone_ts = {e.undid_ts for e in events if isinstance(e, UndoneEvent)}
    return [e for e in events if not isinstance(e, UndoneEvent) and e.ts not in undone_ts]


def rebuild_tasks(context: Path) -> list[Task]:
    tasks: list[Task] = []
    for event in effective_events(load_events(context)):
        tasks = apply_event(tasks, event)
    return tasks


def load_tasks(context: Path) -> list[Task]:
    cache = context / "tasks.json"
    if cache.exists():
        try:
            return [
                Task.model_validate(task)
                for task in json.loads(cache.read_text(encoding="utf-8"))
            ]
        except (ValueError, OSError):
            pass  # unreadable or corrupt cache; events.jsonl is canonical, so rebuild
    tasks = rebuild_tasks(context)
    if tasks:
        save_snapshot(context, tasks)
    return tasks


def append_event(context: Path, event: Event) -> None:
    context.mkdir(parents=True, exist_ok=True)
    with open(context / "events.jsonl", "a", encoding="utf-8", newline="\n") as file:
        file.write(event.model_dump_json() + "\n")


def save_snapshot(context: Path, tasks: list[Task]) -> None:
    payload = json.dumps([task.model_dump(mode="json") for task in tasks], indent=2)
    tmp = context / "tasks.json.tmp"
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, context / "tasks.json")


def lazy_wait_transitions(tasks: list[Task], now: datetime | None = None) -> list[UpdatedEvent]:
    if now is None:
        now = datetime.now()
    events = []
    for task in tasks:
        if task.status == "waiting" and task.wait is not None and task.wait <= now:
            events.append(UpdatedEvent(
                task_id=task.uuid,
                changes={
                    "status": FieldChange(before="waiting", after="pending"),
                    "wait": FieldChange(before=task.wait, after=None),
                },
            ))
    return events


def assign_display_ids(tasks: list[Task]) -> None:
    active = sorted(
        (task for task in tasks if task.status in {"pending", "waiting"}),
        key=lambda t: t.entry,
    )

    for i, task in enumerate(active, 1):
        task.id = i


# --- timesheet entries: a parallel track over the same event log ---------------


def rebuild_entries(context: Path) -> list[Entry]:
    entries: list[Entry] = []
    for event in effective_events(load_events(context)):
        entries = apply_entry_event(entries, event)
    return entries


def load_entries(context: Path) -> list[Entry]:
    cache = context / "entries.json"
    if cache.exists():
        try:
            return [
                Entry.model_validate(entry)
                for entry in json.loads(cache.read_text(encoding="utf-8"))
            ]
        except (ValueError, OSError):
            pass  # unreadable or corrupt cache; events.jsonl is canonical, so rebuild
    entries = rebuild_entries(context)
    if entries:
        save_entries_snapshot(context, entries)
    return entries


def save_entries_snapshot(context: Path, entries: list[Entry]) -> None:
    payload = json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2)
    tmp = context / "entries.json.tmp"
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, context / "entries.json")


def _letters():
    """a..z, then aa, ab, ... — so a long day never runs out of addresses."""
    width = 1
    while True:
        for i in range(26 ** width):
            label, n = "", i
            for _ in range(width):
                label = chr(ord("a") + n % 26) + label
                n //= 26
            yield label
        width += 1


def assign_display_letters(entries: list[Entry]) -> None:
    """Label entries in the order given. Ordering and day-scoping are the caller's job."""
    letters = _letters()
    for entry in entries:
        entry.id = next(letters)
