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


def test_lazy_wait_transitions_flips_expired_wait():
    past = datetime.now() - timedelta(hours=1)
    task = Task(description="deferred", status="waiting", wait=past)
    events = storage.lazy_wait_transitions([task])
    assert len(events) == 1
    assert events[0].changes["status"].before == "waiting"
    assert events[0].changes["status"].after == "pending"
    assert events[0].changes["wait"].after is None


def test_lazy_wait_transitions_no_event_for_future_wait():
    future = datetime.now() + timedelta(hours=1)
    task = Task(description="deferred", status="waiting", wait=future)
    assert storage.lazy_wait_transitions([task]) == []


def test_lazy_wait_transitions_no_event_when_wait_is_none():
    task = Task(description="waiting", status="waiting")
    assert storage.lazy_wait_transitions([task]) == []


def test_lazy_wait_transitions_skips_pending():
    task = Task(description="pending")
    assert storage.lazy_wait_transitions([task]) == []


def test_lazy_wait_transitions_apply_updates_task():
    from task.events import apply_event
    past = datetime.now() - timedelta(hours=1)
    task = Task(description="deferred", status="waiting", wait=past)
    transitions = storage.lazy_wait_transitions([task])
    result = apply_event([task], transitions[0])
    assert result[0].status == "pending"
    assert result[0].wait is None


def test_lazy_wait_transitions_accepts_now_override():
    fixed_now = datetime(2026, 1, 1, 12, 0)
    task_expired = Task(description="expired", status="waiting", wait=datetime(2026, 1, 1, 11, 0))
    task_future = Task(description="future", status="waiting", wait=datetime(2026, 1, 1, 13, 0))
    events = storage.lazy_wait_transitions([task_expired, task_future], now=fixed_now)
    assert len(events) == 1
    assert events[0].task_id == task_expired.uuid


def test_rebuild_tasks_skips_undone_event(tmp_data_dir):
    context = tmp_data_dir / "default"
    context.mkdir()
    task = Task(description="buy milk")
    created = CreatedEvent(task_id=task.uuid, snapshot=task)
    storage.append_event(context, created)
    from task.models import UndoneEvent
    undo = UndoneEvent(task_id=task.uuid, undid_ts=created.ts, undid_type="created")
    storage.append_event(context, undo)
    tasks = storage.rebuild_tasks(context)
    assert tasks == []


def test_rebuild_tasks_second_undo_skips_earlier_event(tmp_data_dir):
    from task.models import DoneEvent, UndoneEvent
    context = tmp_data_dir / "default"
    context.mkdir()
    task = Task(description="buy milk")
    created = CreatedEvent(task_id=task.uuid, snapshot=task)
    done = DoneEvent(task_id=task.uuid)
    storage.append_event(context, created)
    storage.append_event(context, done)
    undo_done = UndoneEvent(task_id=task.uuid, undid_ts=done.ts, undid_type="done")
    storage.append_event(context, undo_done)
    undo_created = UndoneEvent(task_id=task.uuid, undid_ts=created.ts, undid_type="created")
    storage.append_event(context, undo_created)
    tasks = storage.rebuild_tasks(context)
    assert tasks == []


def test_rebuild_tasks_partial_undo_leaves_earlier_events(tmp_data_dir):
    from task.models import DoneEvent, UndoneEvent
    context = tmp_data_dir / "default"
    context.mkdir()
    task = Task(description="buy milk")
    created = CreatedEvent(task_id=task.uuid, snapshot=task)
    done = DoneEvent(task_id=task.uuid)
    storage.append_event(context, created)
    storage.append_event(context, done)
    undo_done = UndoneEvent(task_id=task.uuid, undid_ts=done.ts, undid_type="done")
    storage.append_event(context, undo_done)
    tasks = storage.rebuild_tasks(context)
    assert len(tasks) == 1
    assert tasks[0].status == "pending"


def test_assign_display_ids_includes_waiting():
    now = datetime.now()
    t_pending = Task(description="pending", entry=now - timedelta(minutes=1))
    t_waiting = Task(description="waiting", status="waiting", entry=now)
    storage.assign_display_ids([t_waiting, t_pending])  # deliberately reversed
    assert t_pending.id == 1
    assert t_waiting.id == 2
