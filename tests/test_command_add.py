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
        assert "Add task with id 1" in message or "task 1" in message.lower()
        
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
        """Test adding task with empty modification section."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        
        config = Config(db_path=str(db_file))
        db.write_config(config)
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        message = command.add([], [])
        
        tasks = db.read_db()
        assert tasks["title"][0] == ""
        assert "task" in message.lower()
    
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

