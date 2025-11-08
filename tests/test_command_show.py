"""Tests for the show command."""
import polars as pl
import pytest

from task import command, db
from task.models import Filter


@pytest.fixture
def sample_tasks_df():
    """Fixture providing a sample tasks DataFrame."""
    return pl.DataFrame(
        {
            "id": [1, 2],
            "title": ["Buy milk", "Plan project"],
            "project": ["home", "work"],
            "priority": ["H", "M"],
            "due": ["2025-01-10", "2025-02-01"],
            "scheduled": [None, "2025-01-20"],
            "tags": [
                ["errand", "home"],
                ["work"],
            ],
            "status": ["pending", "active"],
        }
    )


def test_show_no_tasks_returns_message(monkeypatch):
    """Show should return message when no tasks found."""
    filter_obj = Filter()
    monkeypatch.setattr(command, "parse_filter", lambda _: filter_obj)
    monkeypatch.setattr(db, "read_db", lambda: None)
    monkeypatch.setattr(db, "filter_tasks", lambda tasks, f: pl.DataFrame())

    result = command.show([], [])
    assert result == "No tasks found"


def test_show_returns_filtered_dataframe(monkeypatch, sample_tasks_df):
    """Show should return filtered DataFrame when tasks exist."""
    filter_obj = Filter(ids=[2])

    monkeypatch.setattr(command, "parse_filter", lambda _: filter_obj)
    monkeypatch.setattr(db, "read_db", lambda: sample_tasks_df)

    result = command.show([], [])
    assert isinstance(result, pl.DataFrame)
    assert result["id"].to_list() == [2]

