import json
from datetime import datetime, timedelta

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
    event = CreatedEvent(task_id=task.uuid, snapshot=task)
    storage.append_event(tmp_data_dir, event)
    lines = (tmp_data_dir / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "created"


def test_append_event_accumulates(tmp_data_dir):
    task = Task(description="test")
    event = CreatedEvent(task_id=task.uuid, snapshot=task)
    storage.append_event(tmp_data_dir, event)
    storage.append_event(tmp_data_dir, event)
    lines = (tmp_data_dir / "events.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_active_context_env_override(tmp_data_dir, monkeypatch):
    monkeypatch.setenv("TASK_CONTEXT", "work")
    assert storage.active_context(tmp_data_dir) == tmp_data_dir / "work"


def test_load_tasks_rebuilds_from_events_when_cache_missing(tmp_data_dir):
    context = tmp_data_dir / "default"
    context.mkdir()
    task = Task(description="buy milk")
    event = CreatedEvent(task_id=task.uuid, snapshot=task)
    storage.append_event(context, event)
    loaded = storage.load_tasks(context)
    assert len(loaded) == 1
    assert loaded[0].description == "buy milk"
    assert loaded[0].uuid == task.uuid


def test_assign_display_ids_ordered_by_entry():
    now = datetime.now()
    t1 = Task(description="older", entry=now - timedelta(hours=1))
    t2 = Task(description="newer", entry=now)
    storage.assign_display_ids([t2, t1])  # deliberately reversed
    assert t1.id == 1
    assert t2.id == 2


def test_assign_display_ids_skips_done_and_deleted():
    t_pending = Task(description="pending")
    t_done = Task(description="done", status="done")
    t_deleted = Task(description="deleted", status="deleted")
    storage.assign_display_ids([t_pending, t_done, t_deleted])
    assert t_pending.id == 1
    assert t_done.id is None
    assert t_deleted.id is None


def test_assign_display_ids_includes_waiting():
    now = datetime.now()
    t_pending = Task(description="pending", entry=now - timedelta(minutes=1))
    t_waiting = Task(description="waiting", status="waiting", entry=now)
    storage.assign_display_ids([t_waiting, t_pending])  # deliberately reversed
    assert t_pending.id == 1
    assert t_waiting.id == 2
