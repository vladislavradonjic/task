import json, os
from pathlib import Path
from task.models import Event, Task


def data_dir() -> Path:
    override = os.environ.get("TASK_DATA_DIR")
    if override:
        return Path(override)
    from platformdirs import user_data_dir
    return Path(user_data_dir("task", appauthor=False))


def active_context(data_dir: Path) -> Path:
    state = data_dir / "state.json"
    if state.exists():
        active = json.loads(state.read_text())["active"]
    else:
        active = "default"
    return data_dir / active


def load_tasks(context: Path) -> list[Task]:
    cache = context / "tasks.json"
    if not cache.exists():
        return []
    return [Task.model_validate(task) for task in json.loads(cache.read_text())]


def append_event(context: Path, event: Event) -> None:
    context.mkdir(parents=True, exist_ok=True)
    with open(context / "events.jsonl", "a") as file:
        file.write(event.model_dump_json() + "\n")


def save_snapshot(context: Path, tasks: list[Task]) -> None:
    (context / "tasks.json").write_text(
        json.dumps([task.model_dump(mode="json") for task in tasks], indent=2)
    )
