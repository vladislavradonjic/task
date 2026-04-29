import json

from task.commands import add_, context_, delete_, done_, init_, list_, modify_, undo_
from task.models import CreatedEvent, DeletedEvent, DoneEvent, ParsedFilter, ParsedModification, Task, UpdatedEvent
from task.storage import assign_display_ids


# ---------------------------------------------------------------------------
# add_
# ---------------------------------------------------------------------------

def test_add_returns_created_event():
    events, message = add_([], ParsedFilter(), ParsedModification(description="buy milk"))
    assert len(events) == 1
    assert isinstance(events[0], CreatedEvent)
    assert events[0].snapshot.description == "buy milk"
    assert str(events[0].task_id) in message


def test_add_task_id_matches_snapshot():
    events, _ = add_([], ParsedFilter(), ParsedModification(description="test"))
    assert events[0].task_id == events[0].snapshot.uuid


def test_add_applies_positive_tags():
    events, _ = add_([], ParsedFilter(), ParsedModification(description="test", tags=["+bug", "+urgent"]))
    assert events[0].snapshot.tags == ["bug", "urgent"]


def test_add_ignores_negative_tags():
    events, _ = add_([], ParsedFilter(), ParsedModification(description="test", tags=["-stale"]))
    assert events[0].snapshot.tags == []


def test_add_applies_properties():
    events, _ = add_([], ParsedFilter(), ParsedModification(description="test", properties={"project": "work", "priority": "H"}))
    assert events[0].snapshot.properties == {"project": "work", "priority": "H"}


def test_add_drops_none_properties():
    # None value means "remove" in modify context — meaningless on create
    events, _ = add_([], ParsedFilter(), ParsedModification(description="test", properties={"due": None}))
    assert "due" not in events[0].snapshot.properties


# ---------------------------------------------------------------------------
# list_
# ---------------------------------------------------------------------------

def test_list_no_tasks(capsys):
    _, message = list_([], ParsedFilter(), ParsedModification())
    assert message == "No tasks."


def test_list_shows_pending(capsys):
    tasks = [Task(description="buy milk"), Task(description="fix parser")]
    assign_display_ids(tasks)
    _, message = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "buy milk" in captured.out
    assert "fix parser" in captured.out


def test_list_hides_waiting_when_10_or_more_pending(capsys):
    pending = [Task(description=f"task {i}") for i in range(10)]
    waiting = [Task(description="waiting task", status="waiting")]
    tasks = pending + waiting
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "waiting task" not in captured.out


def test_list_shows_waiting_when_fewer_than_10_pending(capsys):
    pending = [Task(description=f"task {i}") for i in range(3)]
    waiting = [Task(description="waiting task", status="waiting")]
    tasks = pending + waiting
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "waiting task" in captured.out


def test_list_shows_tags_column_only_when_present(capsys):
    tasks = [Task(description="tagged", tags=["bug"]), Task(description="plain")]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "Tags" in captured.out
    assert "+bug" in captured.out


def test_list_omits_tags_column_when_absent(capsys):
    tasks = [Task(description="plain")]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "Tags" not in captured.out


def test_list_shows_project_column_only_when_present(capsys):
    tasks = [Task(description="work task", properties={"project": "work"})]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "Project" in captured.out
    assert "work" in captured.out


def test_list_ids_from_full_active_set(capsys):
    # waiting gets a display ID even when not shown (≥10 pending suppresses it)
    pending = [Task(description=f"task {i}") for i in range(10)]
    waiting = [Task(description="wait task", status="waiting")]
    tasks = pending + waiting
    assign_display_ids(tasks)
    assert waiting[0].id is not None
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "wait task" not in captured.out


def test_list_status_filter_waiting_overrides_threshold(capsys):
    pending = [Task(description=f"task {i}") for i in range(10)]
    waiting = [Task(description="wait task", status="waiting")]
    tasks = pending + waiting
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(properties={"status": "waiting"}), ParsedModification())
    captured = capsys.readouterr()
    assert "wait task" in captured.out
    assert "task 0" not in captured.out


def test_list_status_filter_pending_shows_only_pending(capsys):
    pending = [Task(description="pending task")]
    waiting = [Task(description="wait task", status="waiting")]
    tasks = pending + waiting
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(properties={"status": "pending"}), ParsedModification())
    captured = capsys.readouterr()
    assert "pending task" in captured.out
    assert "wait task" not in captured.out


def test_list_flag_today(capsys):
    tasks = [Task(description="today task", tags=["today"])]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "1d " in captured.out


def test_list_flag_week(capsys):
    tasks = [Task(description="week task", tags=["week"])]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "1w " in captured.out


def test_list_flag_both_today_and_week(capsys):
    tasks = [Task(description="both", tags=["today", "week"])]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "1* " in captured.out


def test_list_flag_active(capsys):
    from datetime import datetime
    tasks = [Task(description="active", start=datetime.now())]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    assert "1 >" in captured.out


def test_list_flag_omitted_when_no_task_has_flag(capsys):
    tasks = [Task(description="plain a"), Task(description="plain b")]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    # IDs should be bare numbers with no flag chars
    assert "1 " in captured.out or "1\n" in captured.out or "1│" in captured.out
    assert "d" not in captured.out
    assert "w" not in captured.out
    assert ">" not in captured.out


def test_list_flag_unflagged_task_gets_spaces_when_others_have_flags(capsys):
    from datetime import datetime
    tasks = [
        Task(description="active", start=datetime.now()),
        Task(description="plain"),
    ]
    assign_display_ids(tasks)
    _, _ = list_(tasks, ParsedFilter(), ParsedModification())
    captured = capsys.readouterr()
    # unflagged task gets two-space suffix for alignment
    assert "2  " in captured.out


# ---------------------------------------------------------------------------
# done_
# ---------------------------------------------------------------------------

def test_done_empty_filter_is_noop():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = done_(tasks, ParsedFilter(), ParsedModification())
    assert events == []
    assert "No filter" in message


def test_done_no_matching_id():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = done_(tasks, ParsedFilter(ids=[99]), ParsedModification())
    assert events == []
    assert "No matching" in message


def test_done_returns_done_event():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = done_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)
    assert events[0].task_id == tasks[0].uuid
    assert "buy milk" in message


def test_done_sets_end_timestamp():
    from task.events import apply_event
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, _ = done_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    result = apply_event(tasks, events[0])
    assert result[0].status == "done"
    assert result[0].end is not None


def test_done_refuses_waiting_task():
    tasks = [Task(description="waiting task", status="waiting")]
    assign_display_ids(tasks)
    events, message = done_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert events == []
    assert "waiting" in message.lower()


def test_done_refuses_entire_batch_if_any_waiting():
    tasks = [
        Task(description="pending task"),
        Task(description="waiting task", status="waiting"),
    ]
    assign_display_ids(tasks)
    events, message = done_(tasks, ParsedFilter(ids=[1, 2]), ParsedModification())
    assert events == []
    assert "waiting" in message.lower()


def test_done_multiple_tasks():
    tasks = [Task(description=f"task {i}") for i in range(3)]
    assign_display_ids(tasks)
    events, message = done_(tasks, ParsedFilter(ids=[1, 3]), ParsedModification())
    assert len(events) == 2
    assert "2 tasks" in message


# ---------------------------------------------------------------------------
# delete_
# ---------------------------------------------------------------------------

def test_delete_empty_filter_is_noop():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = delete_(tasks, ParsedFilter(), ParsedModification())
    assert events == []
    assert "No filter" in message


def test_delete_no_matching_id():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = delete_(tasks, ParsedFilter(ids=[99]), ParsedModification())
    assert events == []
    assert "No matching" in message


def test_delete_returns_deleted_event():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = delete_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], DeletedEvent)
    assert events[0].task_id == tasks[0].uuid
    assert "buy milk" in message


def test_delete_sets_status_deleted():
    from task.events import apply_event
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, _ = delete_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    result = apply_event(tasks, events[0])
    assert result[0].status == "deleted"


def test_delete_multiple_tasks():
    tasks = [Task(description=f"task {i}") for i in range(3)]
    assign_display_ids(tasks)
    events, message = delete_(tasks, ParsedFilter(ids=[1, 2]), ParsedModification())
    assert len(events) == 2
    assert "2 tasks" in message


def test_delete_waiting_task_allowed():
    tasks = [Task(description="waiting task", status="waiting")]
    assign_display_ids(tasks)
    events, _ = delete_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert len(events) == 1
    assert isinstance(events[0], DeletedEvent)


# ---------------------------------------------------------------------------
# modify_
# ---------------------------------------------------------------------------

def test_modify_empty_filter_is_noop():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = modify_(tasks, ParsedFilter(), ParsedModification(description="new desc"))
    assert events == []
    assert "No filter" in message


def test_modify_no_matching_id():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = modify_(tasks, ParsedFilter(ids=[99]), ParsedModification(description="new desc"))
    assert events == []
    assert "No matching" in message


def test_modify_nothing_to_change():
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    assert events == []
    assert "Nothing to change" in message


def test_modify_description():
    from task.events import apply_event
    tasks = [Task(description="buy milk")]
    assign_display_ids(tasks)
    events, message = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="buy oat milk"))
    assert len(events) == 1
    assert isinstance(events[0], UpdatedEvent)
    assert "description" in events[0].changes
    result = apply_event(tasks, events[0])
    assert result[0].description == "buy oat milk"
    assert "buy milk" in message or "buy oat milk" in message


def test_modify_add_tag():
    from task.events import apply_event
    tasks = [Task(description="task", tags=["existing"])]
    assign_display_ids(tasks)
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(tags=["+urgent"]))
    result = apply_event(tasks, events[0])
    assert "urgent" in result[0].tags
    assert "existing" in result[0].tags


def test_modify_remove_tag():
    from task.events import apply_event
    tasks = [Task(description="task", tags=["bug", "urgent"])]
    assign_display_ids(tasks)
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(tags=["-bug"]))
    result = apply_event(tasks, events[0])
    assert "bug" not in result[0].tags
    assert "urgent" in result[0].tags


def test_modify_add_tag_idempotent():
    tasks = [Task(description="task", tags=["bug"])]
    assign_display_ids(tasks)
    events, message = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(tags=["+bug"]))
    assert events == []
    assert "Nothing to change" in message


def test_modify_set_property():
    from task.events import apply_event
    tasks = [Task(description="task")]
    assign_display_ids(tasks)
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"project": "work"}))
    result = apply_event(tasks, events[0])
    assert result[0].properties["project"] == "work"


def test_modify_clear_property():
    from task.events import apply_event
    tasks = [Task(description="task", properties={"project": "work"})]
    assign_display_ids(tasks)
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"project": None}))
    result = apply_event(tasks, events[0])
    assert "project" not in result[0].properties


def test_modify_records_before_after():
    tasks = [Task(description="old desc")]
    assign_display_ids(tasks)
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="new desc"))
    change = events[0].changes["description"]
    assert change.before == "old desc"
    assert change.after == "new desc"


def test_modify_multiple_tasks():
    tasks = [Task(description=f"task {i}") for i in range(3)]
    assign_display_ids(tasks)
    events, message = modify_(tasks, ParsedFilter(ids=[1, 2]), ParsedModification(properties={"project": "work"}))
    assert len(events) == 2
    assert "2 tasks" in message


# ---------------------------------------------------------------------------
# context_
# ---------------------------------------------------------------------------

def test_context_bare_shows_active(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification())
    assert message == "default"


def test_context_list_marks_active(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="list"))
    assert "* default" in message


def test_context_list_shows_all_contexts(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    context_(ParsedFilter(), ParsedModification(description="create work"))
    _, message = context_(ParsedFilter(), ParsedModification(description="list"))
    assert "* default" in message
    assert "  work" in message


def test_context_create_makes_dir(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="create work"))
    assert "work" in message
    assert (tmp_data_dir / "work" / "meta.json").exists()
    assert (tmp_data_dir / "work" / "events.jsonl").exists()
    assert (tmp_data_dir / "work" / "tasks.json").exists()
    assert (tmp_data_dir / "work" / "recaps").is_dir()


def test_context_create_invalid_name(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="create 1bad"))
    assert "Invalid" in message
    assert not (tmp_data_dir / "1bad").exists()


def test_context_create_duplicate(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    context_(ParsedFilter(), ParsedModification(description="create work"))
    _, message = context_(ParsedFilter(), ParsedModification(description="create work"))
    assert "already exists" in message


def test_context_create_does_not_switch(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    context_(ParsedFilter(), ParsedModification(description="create work"))
    _, message = context_(ParsedFilter(), ParsedModification())
    assert message == "default"


def test_context_use_switches_active(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    context_(ParsedFilter(), ParsedModification(description="create work"))
    _, message = context_(ParsedFilter(), ParsedModification(description="use work"))
    assert "work" in message
    state = json.loads((tmp_data_dir / "state.json").read_text())
    assert state["active"] == "work"


def test_context_use_nonexistent(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="use nonexistent"))
    assert "does not exist" in message


def test_context_delete_refuses_active(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="delete default"))
    assert "active" in message.lower()
    assert (tmp_data_dir / "default").exists()


def test_context_delete_refuses_non_tty(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    context_(ParsedFilter(), ParsedModification(description="create work"))
    _, message = context_(ParsedFilter(), ParsedModification(description="delete work"))
    assert "TTY" in message
    assert (tmp_data_dir / "work").exists()


def test_context_delete_nonexistent(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="delete nonexistent"))
    assert "does not exist" in message


def test_context_unknown_subcommand(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = context_(ParsedFilter(), ParsedModification(description="frobnicate"))
    assert "Unknown" in message


# ---------------------------------------------------------------------------
# init_
# ---------------------------------------------------------------------------

def test_init_creates_structure(tmp_data_dir):
    _, message = init_(ParsedFilter(), ParsedModification())
    assert (tmp_data_dir / "state.json").exists()
    assert (tmp_data_dir / "default" / "meta.json").exists()
    state = json.loads((tmp_data_dir / "state.json").read_text())
    assert state == {"version": 1, "active": "default"}
    assert "Initialized" in message


def test_init_already_initialized(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    _, message = init_(ParsedFilter(), ParsedModification())
    assert "Already initialized" in message


# ---------------------------------------------------------------------------
# undo_
# ---------------------------------------------------------------------------

def _setup(tmp_data_dir):
    init_(ParsedFilter(), ParsedModification())
    return tmp_data_dir / "default"


def test_undo_nothing_to_undo(tmp_data_dir):
    _setup(tmp_data_dir)
    _, message = undo_(ParsedFilter(), ParsedModification())
    assert message == "Nothing to undo."


def test_undo_created_removes_task(tmp_data_dir):
    from task.storage import append_event, rebuild_tasks, assign_display_ids, save_snapshot
    ctx = _setup(tmp_data_dir)

    events, _ = add_([], ParsedFilter(), ParsedModification(description="buy milk"))
    for e in events:
        append_event(ctx, e)
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    _, message = undo_(ParsedFilter(), ParsedModification())
    assert "created" in message
    assert "buy milk" in message
    assert rebuild_tasks(ctx) == []


def test_undo_done_reverts_to_pending(tmp_data_dir):
    from task.storage import append_event, rebuild_tasks, assign_display_ids, save_snapshot
    ctx = _setup(tmp_data_dir)

    events, _ = add_([], ParsedFilter(), ParsedModification(description="fix parser"))
    for e in events:
        append_event(ctx, e)
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    events, _ = done_(tasks, ParsedFilter(ids=[1]), ParsedModification())
    for e in events:
        append_event(ctx, e)
    tasks = rebuild_tasks(ctx)
    save_snapshot(ctx, tasks)

    _, message = undo_(ParsedFilter(), ParsedModification())
    assert "done" in message
    assert "fix parser" in message
    remaining = rebuild_tasks(ctx)
    assert len(remaining) == 1
    assert remaining[0].status == "pending"
    assert remaining[0].end is None


def test_undo_twice_walks_back(tmp_data_dir):
    from task.storage import append_event, rebuild_tasks, assign_display_ids, save_snapshot
    ctx = _setup(tmp_data_dir)

    events, _ = add_([], ParsedFilter(), ParsedModification(description="task a"))
    for e in events:
        append_event(ctx, e)
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    events, _ = add_([], ParsedFilter(), ParsedModification(description="task b"))
    for e in events:
        append_event(ctx, e)
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    undo_(ParsedFilter(), ParsedModification())
    undo_(ParsedFilter(), ParsedModification())
    assert rebuild_tasks(ctx) == []


def test_undo_repeated_beyond_log_is_safe(tmp_data_dir):
    from task.storage import append_event, rebuild_tasks, assign_display_ids, save_snapshot
    ctx = _setup(tmp_data_dir)

    events, _ = add_([], ParsedFilter(), ParsedModification(description="only task"))
    for e in events:
        append_event(ctx, e)
    tasks = rebuild_tasks(ctx)
    assign_display_ids(tasks)
    save_snapshot(ctx, tasks)

    undo_(ParsedFilter(), ParsedModification())
    _, message = undo_(ParsedFilter(), ParsedModification())
    assert message == "Nothing to undo."
