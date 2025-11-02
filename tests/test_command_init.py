"""Tests for the init command."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, call

from task import command, db
from task.models import Config


class TestInitCommand:
    """Tests for the init command function."""
    
    def test_init_creates_config_and_db(self, tmp_path, monkeypatch):
        """Test that init creates both config and database files."""
        config_file = tmp_path / "config.json"
        db_dir = tmp_path / "db"
        db_file = db_dir / "default.json"
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Mock input to confirm database creation
        with patch("builtins.input", return_value="y"):
            message = command.init([], [])
        
        # Check return message
        assert isinstance(message, str)
        assert "Database initialized" in message
        assert "default.json" in message or str(db_file) in message
        
        # Check config was created
        assert config_file.exists()
        with open(config_file) as f:
            config_data = json.load(f)
        
        assert "db_path" in config_data
        assert "default.json" in config_data["db_path"]
        
        # Check database was created
        assert db_file.exists()
        with open(db_file) as f:
            db_data = json.load(f)
        
        assert db_data == []
    
    def test_init_adds_current_context(self, tmp_path, monkeypatch):
        """Test that init adds current_context to contexts dict."""
        config_file = tmp_path / "config.json"
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        with patch("builtins.input", return_value="y"):
            message = command.init([], [])
        
        assert isinstance(message, str)
        assert "Database initialized" in message
        
        config = db.read_config()
        
        assert config.current_context in config.contexts
        assert config.contexts[config.current_context] == config.db_path
    
    def test_init_does_not_duplicate_context(self, tmp_path, monkeypatch):
        """Test that init doesn't duplicate context if already exists."""
        config_file = tmp_path / "config.json"
        
        # Create config with context already set
        existing_config = Config(
            db_path=str(tmp_path / "db" / "default.json"),
            current_context="work",
            contexts={"work": str(tmp_path / "db" / "default.json")}
        )
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        # Write the existing config
        db.write_config(existing_config)
        
        initial_contexts = existing_config.contexts.copy()
        
        with patch("builtins.input", return_value="y"):
            message = command.init([], [])
        
        assert isinstance(message, str)
        
        config = db.read_config()
        
        # Should not have duplicated the context
        assert len(config.contexts) == len(initial_contexts)
        assert config.contexts["work"] == initial_contexts["work"]
    
    def test_init_empty_filter_and_modification(self, tmp_path, monkeypatch):
        """Test init with empty filter and modification sections."""
        config_file = tmp_path / "config.json"
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        with patch("builtins.input", return_value="y"):
            message = command.init([], [])
        
        assert isinstance(message, str)
        assert config_file.exists()
    
    def test_init_with_filter_section(self, tmp_path, monkeypatch):
        """Test init with filter section (should be ignored for init)."""
        config_file = tmp_path / "config.json"
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        with patch("builtins.input", return_value="y"):
            message = command.init(["some", "filter", "args"], [])
        
        assert isinstance(message, str)
        assert config_file.exists()
    
    def test_init_with_modification_section(self, tmp_path, monkeypatch):
        """Test init with modification section (should be ignored for init)."""
        config_file = tmp_path / "config.json"
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        with patch("builtins.input", return_value="y"):
            message = command.init([], ["some", "modification", "args"])
        
        assert isinstance(message, str)
        assert config_file.exists()
    
    def test_init_database_exists_user_cancels(self, tmp_path, monkeypatch):
        """Test init when database exists and user cancels."""
        config_file = tmp_path / "config.json"
        db_file = tmp_path / "db" / "default.json"
        db_file.parent.mkdir()
        
        # Create existing database
        db_file.write_text('[{"uuid": "test"}]')
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        with patch("builtins.input", return_value="n"):
            message = command.init([], [])
        
        assert isinstance(message, str)
        assert "Database initialized" in message
        
        # Database should remain unchanged (user cancelled, but init still returns message)
        with open(db_file) as f:
            data = json.load(f)
        
        assert data == [{"uuid": "test"}]
    
    def test_init_config_has_default_values(self, tmp_path, monkeypatch):
        """Test that created config has all default values."""
        config_file = tmp_path / "config.json"
        
        monkeypatch.setattr(db, "get_config_path", lambda: str(config_file))
        monkeypatch.setattr(db, "expand_path", lambda p: str(Path(p).resolve()))
        
        with patch("builtins.input", return_value="y"):
            message = command.init([], [])
        
        assert isinstance(message, str)
        assert "Database initialized" in message
        
        config = db.read_config()
        
        # Check default urgency coefficients are present
        assert "priority_h" in config.urgency_coefficients
        assert "due" in config.urgency_coefficients
        assert config.urgency_coefficients["priority_h"] == 6.0
        assert config.current_context == "default"
        assert isinstance(config.contexts, dict)
