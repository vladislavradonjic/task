"""Tests for the add command."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from task import command, db
from task.models import Task, Config


class TestAddCommand:
    """Tests for the add command function."""
    
    def test_add_task_creates_first_task(self, tmp_path, monkeypatch):
        """Test adding the first task to an empty database."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        # Setup config pointing to our test database
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Run add command
        message = command.add([], ["Buy", "groceries"])
        
        # Check message
        assert "Added task with id 1" in message or "task 1" in message.lower()
        
        # Check database was created and has task
        assert db_file.exists()
        tasks = db.read_db()
        assert tasks is not None
        assert tasks.height == 1
        assert tasks["title"][0] == "Buy groceries"
        assert tasks["id"][0] == 1
    
    def test_add_multiple_tasks_increments_id(self, tmp_path, monkeypatch):
        """Test that adding multiple tasks assigns sequential IDs."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Add first task
        command.add([], ["Task", "1"])
        tasks = db.read_db()
        assert tasks["id"][0] == 1
        
        # Add second task
        command.add([], ["Task", "2"])
        tasks = db.read_db()
        assert tasks.height == 2
        assert tasks["id"].to_list() == [1, 2]
    
    def test_add_task_with_single_word_title(self, tmp_path, monkeypatch):
        """Test adding task with single word title."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        message = command.add([], ["Code"])
        
        tasks = db.read_db()
        assert tasks["title"][0] == "Code"
        assert "task" in message.lower()
    
    def test_add_task_with_empty_title(self, tmp_path, monkeypatch):
        """Test adding task with empty modification section returns error message."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Empty modification section should return error message
        message = command.add([], [])
        assert message == "Modification section is empty; Task not created."
        
        # No task should be added
        tasks = db.read_db()
        assert tasks is None
    
    def test_add_task_persists_to_file(self, tmp_path, monkeypatch):
        """Test that added task is persisted to JSON file."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Persistent", "task"])
        
        # Read directly from file
        with open(db_file) as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]["title"] == "Persistent task"
        assert data[0]["id"] == 1
    
    def test_add_task_creates_default_values(self, tmp_path, monkeypatch):
        """Test that added task has correct default values."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Test", "task"])
        
        tasks = db.read_db()
        task_dict = tasks.to_dicts()[0]
        
        assert task_dict["status"] == "pending"
        assert task_dict["rank_score"] == 0.0
        assert task_dict["project"] is None
        assert task_dict["priority"] is None
        assert task_dict["tags"] == []
        assert task_dict["depends"] == []
        assert task_dict["blocks"] == []
        assert "uuid" in task_dict
        assert "created_at" in task_dict
        assert "updated_at" in task_dict
    
    def test_add_task_filter_section_ignored(self, tmp_path, monkeypatch):
        """Test that filter_section is ignored in add command."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Filter section should be ignored
        command.add(["some", "filter"], ["Actual", "task", "title"])
        
        tasks = db.read_db()
        assert tasks["title"][0] == "Actual task title"
    
    def test_add_task_multiple_times_preserves_existing(self, tmp_path, monkeypatch):
        """Test that adding multiple times preserves existing tasks."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Add three tasks
        command.add([], ["First"])
        command.add([], ["Second"])
        command.add([], ["Third"])
        
        tasks = db.read_db()
        assert tasks.height == 3
        assert tasks["title"].to_list() == ["First", "Second", "Third"]
        assert tasks["id"].to_list() == [1, 2, 3]
    
    def test_add_task_with_project(self, tmp_path, monkeypatch):
        """Test adding task with project property."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Buy", "groceries", "project:home"])
        
        tasks = db.read_db()
        assert tasks["title"][0] == "Buy groceries"
        assert tasks["project"][0] == "home"
    
    def test_add_task_with_priority(self, tmp_path, monkeypatch):
        """Test adding task with priority property."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Urgent", "task", "priority:H"])
        
        tasks = db.read_db()
        assert tasks["title"][0] == "Urgent task"
        assert tasks["priority"][0] == "H"
    
    def test_add_task_with_tags(self, tmp_path, monkeypatch):
        """Test adding task with tags."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Task", "+urgent", "+shopping"])
        
        tasks = db.read_db()
        assert tasks["title"][0] == "Task"
        # Tags should be stored without + prefix
        assert "urgent" in tasks["tags"][0]
        assert "shopping" in tasks["tags"][0]
        assert len(tasks["tags"][0]) == 2
    
    def test_add_task_with_minus_tag_ignored(self, tmp_path, monkeypatch):
        """Test that minus tags are ignored when adding (nothing to remove)."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Task", "+urgent", "-old"])
        
        tasks = db.read_db()
        # Only +urgent should be added (minus tag ignored)
        # Access tags from the first row
        task_dict = tasks.to_dicts()[0]
        assert task_dict["tags"] == ["urgent"]
    
    def test_add_task_with_all_properties(self, tmp_path, monkeypatch):
        """Test adding task with project, priority, and tags."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], [
            "Complete", "project", "documentation",
            "project:work",
            "priority:M",
            "+urgent",
            "+documentation"
        ])
        
        tasks = db.read_db()
        assert tasks["title"][0] == "Complete project documentation"
        assert tasks["project"][0] == "work"
        assert tasks["priority"][0] == "M"
        assert "urgent" in tasks["tags"][0]
        assert "documentation" in tasks["tags"][0]
    
    def test_add_task_with_due_date(self, tmp_path, monkeypatch):
        """Test adding task with due date."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Task", "due:tomorrow"])
        
        tasks = db.read_db()
        from datetime import date
        assert tasks["title"][0] == "Task"
        # Dates are stored as strings in JSON, so compare as string or parse
        due_str = tasks["due"][0]
        due_date = date.fromisoformat(due_str) if isinstance(due_str, str) else due_str
        assert isinstance(due_date, date)
        assert due_date >= date.today()
    
    def test_add_task_with_scheduled_date(self, tmp_path, monkeypatch):
        """Test adding task with scheduled date."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], ["Task", "scheduled:2025-12-25"])
        
        tasks = db.read_db()
        from datetime import date
        assert tasks["title"][0] == "Task"
        # Dates are stored as strings in JSON
        scheduled_str = tasks["scheduled"][0]
        scheduled_date = date.fromisoformat(scheduled_str) if isinstance(scheduled_str, str) else scheduled_str
        assert scheduled_date == date(2025, 12, 25)
    
    def test_add_task_with_both_dates(self, tmp_path, monkeypatch):
        """Test adding task with both due and scheduled dates."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], [
            "Complete", "project",
            "due:tomorrow",
            "scheduled:2025-12-01"
        ])
        
        tasks = db.read_db()
        from datetime import date
        assert tasks["title"][0] == "Complete project"
        # Dates are stored as strings in JSON
        due_str = tasks["due"][0]
        due_date = date.fromisoformat(due_str) if isinstance(due_str, str) else due_str
        assert isinstance(due_date, date)
        scheduled_str = tasks["scheduled"][0]
        scheduled_date = date.fromisoformat(scheduled_str) if isinstance(scheduled_str, str) else scheduled_str
        assert scheduled_date == date(2025, 12, 1)
    
    def test_add_task_with_all_fields_including_dates(self, tmp_path, monkeypatch):
        """Test adding task with all fields including dates."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        command.add([], [
            "Complete", "project", "documentation",
            "project:work",
            "priority:M",
            "due:2025-12-25",
            "scheduled:2025-12-01",
            "+urgent",
            "+documentation"
        ])
        
        tasks = db.read_db()
        from datetime import date
        task_dict = tasks.to_dicts()[0]
        
        assert task_dict["title"] == "Complete project documentation"
        assert task_dict["project"] == "work"
        assert task_dict["priority"] == "M"
        # Dates are stored as strings in JSON
        due_str = task_dict["due"]
        due_date = date.fromisoformat(due_str) if isinstance(due_str, str) else due_str
        assert due_date == date(2025, 12, 25)
        scheduled_str = task_dict["scheduled"]
        scheduled_date = date.fromisoformat(scheduled_str) if isinstance(scheduled_str, str) else scheduled_str
        assert scheduled_date == date(2025, 12, 1)
        assert "urgent" in task_dict["tags"]
        assert "documentation" in task_dict["tags"]

