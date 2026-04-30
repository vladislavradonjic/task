from datetime import datetime

import pytest

from task.commands import query_
from task.models import ParsedFilter, ParsedModification, Task
from task.storage import assign_display_ids


def _tasks(*specs):
    """Build a list of tasks from dicts; assign display IDs."""
    tasks = [Task(**s) for s in specs]
    assign_display_ids(tasks)
    return tasks


# ---------------------------------------------------------------------------
# Basic filtering
# ---------------------------------------------------------------------------

def test_query_description_contains(capsys):
    tasks = _tasks(
        {"description": "buy milk"},
        {"description": "fix parser"},
    )
    events, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('description').str.contains('milk')"))
    assert events == []
    assert message == ""
    out = capsys.readouterr().out
    assert "buy milk" in out
    assert "fix parser" not in out


def test_query_status_done_included(capsys):
    tasks = _tasks(
        {"description": "done task", "status": "done"},
        {"description": "pending task"},
    )
    events, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('status') == 'done'"))
    assert message == ""
    out = capsys.readouterr().out
    assert "done task" in out
    assert "pending task" not in out


def test_query_property_priority(capsys):
    tasks = _tasks(
        {"description": "urgent", "properties": {"priority": "H"}},
        {"description": "low", "properties": {"priority": "L"}},
        {"description": "no priority"},
    )
    events, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('priority') == 'H'"))
    assert message == ""
    out = capsys.readouterr().out
    assert "urgent" in out
    assert "low" not in out
    assert "no priority" not in out


def test_query_compound_expression(capsys):
    tasks = _tasks(
        {"description": "high pending", "properties": {"priority": "H"}},
        {"description": "high done", "properties": {"priority": "H"}, "status": "done"},
        {"description": "low pending"},
    )
    _, message = query_(
        tasks,
        ParsedFilter(),
        ParsedModification(description="(col('priority') == 'H') & (col('status') == 'pending')"),
    )
    assert message == ""
    out = capsys.readouterr().out
    assert "high pending" in out
    assert "high done" not in out
    assert "low pending" not in out


def test_query_tags_filter(capsys):
    tasks = _tasks(
        {"description": "tagged", "tags": ["bug"]},
        {"description": "plain"},
    )
    _, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('tags').list.contains('bug')"))
    assert message == ""
    out = capsys.readouterr().out
    assert "tagged" in out
    assert "plain" not in out


# ---------------------------------------------------------------------------
# No match / empty
# ---------------------------------------------------------------------------

def test_query_no_match():
    tasks = _tasks({"description": "buy milk"})
    _, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('status') == 'done'"))
    assert message == "No matching tasks."


def test_query_no_tasks():
    _, message = query_([], ParsedFilter(), ParsedModification(description="col('status') == 'pending'"))
    assert message == "No tasks."


def test_query_empty_expression():
    tasks = _tasks({"description": "buy milk"})
    _, message = query_(tasks, ParsedFilter(), ParsedModification(description=""))
    assert "No expression" in message


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_query_syntax_error():
    tasks = _tasks({"description": "buy milk"})
    _, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('status' =="))
    assert "Syntax error" in message or "Query error" in message


def test_query_invalid_column():
    tasks = _tasks({"description": "buy milk"})
    _, message = query_(tasks, ParsedFilter(), ParsedModification(description="col('nonexistent_column') == 'x'"))
    assert "Query error" in message


def test_query_returns_no_events():
    tasks = _tasks({"description": "buy milk"})
    events, _ = query_(tasks, ParsedFilter(), ParsedModification(description="col('status') == 'pending'"))
    assert events == []
