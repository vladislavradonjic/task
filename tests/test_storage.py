import json

from task import storage
from task.models import CreatedEvent, Task


def test_active_context_reads_state_json(tmp_data_dir):
    (tmp_data_dir / "state.json").write_text(json.dumps({"version": 1, "active": "work"}))
    assert storage.active_context(tmp_data_dir) == tmp_data_dir / "work"


def test_active_context_defaults_to_default(tmp_data_dir):
    assert storage.active_context(tmp_data_dir) == tmp_data_dir / "default"


def test_load_tasks_empty_when_no_cache(tmp_data_dir):
    assert storage.load_tasks(tmp_data_dir) == []


def test_save_and_load_tasks_roundtrip(tmp_data_dir):
    tasks = [Task(description="buy milk"), Task(description="fix parser")]
    storage.save_snapshot(tmp_data_dir, tasks)
    loaded = storage.load_tasks(tmp_data_dir)
    assert loaded == tasks


def test_append_event_creates_jsonl(tmp_data_dir):
    task = Task(description="test")
    event = CreatedEvent(task_id=task.id, snapshot=task)
    storage.append_event(tmp_data_dir, event)
    lines = (tmp_data_dir / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "created"


def test_append_event_accumulates(tmp_data_dir):
    task = Task(description="test")
    event = CreatedEvent(task_id=task.id, snapshot=task)
    storage.append_event(tmp_data_dir, event)
    storage.append_event(tmp_data_dir, event)
    lines = (tmp_data_dir / "events.jsonl").read_text().splitlines()
    assert len(lines) == 2
