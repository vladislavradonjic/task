import json

from task.commands import add_, init_
from task.models import CreatedEvent, ParsedFilter, ParsedModification


def test_add_returns_created_event():
    events, message = add_(ParsedFilter(), ParsedModification(description="buy milk"))
    assert len(events) == 1
    assert isinstance(events[0], CreatedEvent)
    assert events[0].snapshot.description == "buy milk"
    assert str(events[0].task_id) in message


def test_add_task_id_matches_snapshot():
    events, _ = add_(ParsedFilter(), ParsedModification(description="test"))
    assert events[0].task_id == events[0].snapshot.id


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
