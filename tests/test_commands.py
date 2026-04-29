import json

from task.commands import add_, init_, list_
from task.models import CreatedEvent, ParsedFilter, ParsedModification, Task
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
