import json, os
from datetime import datetime
from pathlib import Path
from pydantic import TypeAdapter
from task.models import Event, FieldChange, Task, UpdatedEvent, UndoneEvent
from task.events import apply_event

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
        active = json.loads(state.read_text())["active"]
    else:
        active = "default"
    return data_dir / active


def load_events(context: Path) -> list[Event]:
    events_file = context / "events.jsonl"
    if not events_file.exists():
        return []
    return [
        _event_adapter.validate_json(line)
        for line in events_file.read_text().splitlines()
        if line.strip()
    ]


def rebuild_tasks(context: Path) -> list[Task]:
    events = load_events(context)
    undone_ts = {e.undid_ts for e in events if isinstance(e, UndoneEvent)}
    tasks: list[Task] = []
    for event in events:
        if isinstance(event, UndoneEvent) or event.ts in undone_ts:
            continue
        tasks = apply_event(tasks, event)
    return tasks


def load_tasks(context: Path) -> list[Task]:
    cache = context / "tasks.json"
    if not cache.exists():
        tasks = rebuild_tasks(context)
        if tasks:
            save_snapshot(context, tasks)
        return tasks
    return [Task.model_validate(task) for task in json.loads(cache.read_text())]


def append_event(context: Path, event: Event) -> None:
    context.mkdir(parents=True, exist_ok=True)
    with open(context / "events.jsonl", "a") as file:
        file.write(event.model_dump_json() + "\n")


def save_snapshot(context: Path, tasks: list[Task]) -> None:
    (context / "tasks.json").write_text(
        json.dumps([task.model_dump(mode="json") for task in tasks], indent=2)
    )


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

