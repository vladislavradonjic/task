"""Tests for database and configuration operations."""
import os
import json
from datetime import date
import polars as pl
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from task import db
from task.models import Config, Filter


class TestGetConfigPath:
    """Tests for get_config_path function."""
    
    def test_get_config_path_windows(self, monkeypatch):
        """Test config path on Windows."""
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")
        
        path = db.get_config_path()
        assert path == "C:\\Users\\Test\\AppData\\Roaming\\task\\config.json"
    
    def test_get_config_path_unix(self, monkeypatch):
        """Test config path on Unix-like systems."""
        monkeypatch.setattr(os, "name", "posix")
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.path.expanduser", return_value="/home/test"):
                path = db.get_config_path()
                # Use os.path.join to normalize path separators
                expected = os.path.join("/home/test", ".task", "config.json")
                assert path == expected
    
    def test_get_config_path_windows_no_appdata(self, monkeypatch):
        """Test config path on Windows when APPDATA is not set."""
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.delenv("APPDATA", raising=False)
        
        path = db.get_config_path()
        # Should still return a path, even if APPDATA is None
        assert "task" in path
        assert "config.json" in path


class TestExpandPath:
    """Tests for expand_path function."""
    
    def test_expand_path_absolute(self):
        """Test expanding an already absolute path."""
        path = "/absolute/path/to/file"
        result = db.expand_path(path)
        assert os.path.isabs(result)
        assert "absolute" in result
    
    def test_expand_path_with_tilde(self):
        """Test expanding path with ~."""
        with patch("os.path.expanduser", return_value="/home/test"):
            result = db.expand_path("~/test/path")
            assert os.path.isabs(result)
    
    def test_expand_path_with_env_var(self, monkeypatch):
        """Test expanding path with environment variable."""
        monkeypatch.setenv("TEST_VAR", "/test/value")
        result = db.expand_path("$TEST_VAR/file.json")
        # Should expand the env var
        assert result != "$TEST_VAR/file.json"


class TestWriteConfig:
    """Tests for write_config function."""
    
    def test_write_config_default(self, tmp_path):
        """Test writing default config when None is provided."""
        config_file = tmp_path / "config.json"
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            db.write_config(None)
        
        assert config_file.exists()
        
        with open(config_file) as f:
            data = json.load(f)
        
        assert "db_path" in data
        assert "default.json" in data["db_path"]
        assert data["current_context"] == "default"
        assert isinstance(data["urgency_coefficients"], dict)
        assert isinstance(data["contexts"], dict)
    
    def test_write_config_custom(self, tmp_path):
        """Test writing custom config."""
        config_file = tmp_path / "config.json"
        config = Config(
            db_path="/custom/db/path.json",
            current_context="work",
            contexts={"work": "/work/db.json"},
            urgency_coefficients={"priority_h": 10.0}
        )
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            db.write_config(config)
        
        assert config_file.exists()
        
        with open(config_file) as f:
            data = json.load(f)
        
        assert data["db_path"] == "/custom/db/path.json"
        assert data["current_context"] == "work"
        assert data["contexts"]["work"] == "/work/db.json"
        assert data["urgency_coefficients"]["priority_h"] == 10.0
    
    def test_write_config_creates_directory(self, tmp_path):
        """Test that write_config creates directory if it doesn't exist."""
        config_file = tmp_path / "nested" / "dir" / "config.json"
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            db.write_config(None)
        
        assert config_file.exists()
        assert config_file.parent.exists()


class TestReadConfig:
    """Tests for read_config function."""
    
    def test_read_config_nonexistent(self, tmp_path, capsys):
        """Test reading config when file doesn't exist (creates default)."""
        config_file = tmp_path / "config.json"
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            config = db.read_config()
        
        # Should create default config
        assert config_file.exists()
        captured = capsys.readouterr()
        assert "Configuration file not found" in captured.out or "not found" in captured.out.lower()
        
        assert isinstance(config, Config)
        assert "default.json" in config.db_path
    
    def test_read_config_existing(self, tmp_path):
        """Test reading existing config file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "db_path": "/test/db.json",
            "current_context": "work",
            "urgency_coefficients": {"priority_h": 5.0},
            "contexts": {"work": "/work/db.json"}
        }
        
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            config = db.read_config()
        
        assert config.db_path == "/test/db.json"
        assert config.current_context == "work"
        assert config.urgency_coefficients["priority_h"] == 5.0
        assert config.contexts["work"] == "/work/db.json"
    
    def test_read_config_invalid_json_raises_error(self, tmp_path):
        """Test reading config with invalid JSON raises JSONDecodeError."""
        config_file = tmp_path / "config.json"
        config_file.write_text("invalid json {")
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            # Should raise JSONDecodeError since we write valid JSON
            with pytest.raises(json.JSONDecodeError):
                db.read_config()
    
    def test_read_config_missing_fields(self, tmp_path):
        """Test reading config with missing fields (should use defaults)."""
        config_file = tmp_path / "config.json"
        config_data = {"db_path": "/test/db.json"}
        
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        with patch("task.db.get_config_path", return_value=str(config_file)):
            config = db.read_config()
        
        assert config.db_path == "/test/db.json"
        assert config.current_context == "default"  # Should use default
        assert isinstance(config.urgency_coefficients, dict)  # Should use default


@pytest.fixture
def sample_tasks_df():
    """Fixture providing a sample tasks DataFrame."""
    return pl.DataFrame(
        {
            "id": [1, 2, 3],
            "title": ["Buy milk", "Plan project", "Review notes"],
            "project": ["home", "work", "home"],
            "priority": ["H", "M", "L"],
            "due": [
                date(2025, 1, 10),
                date(2025, 2, 1),
                None,
            ],
            "scheduled": [
                None,
                date(2025, 1, 20),
                None,
            ],
            "tags": [
                "errand home",
                "work",
                "home reading",
            ],
            "status": ["pending", "active", "pending"],
        }
    )


class TestFilterTasks:
    """Tests for filter_tasks function."""

    def test_filter_tasks_none_returns_empty(self):
        """Should return empty DataFrame when tasks are None."""
        result = db.filter_tasks(None, Filter())
        assert isinstance(result, pl.DataFrame)
        assert result.height == 0

    def test_filter_tasks_empty_filter_returns_all(self, sample_tasks_df):
        """Empty filter should return all tasks."""
        result = db.filter_tasks(sample_tasks_df, Filter())
        assert result.height == sample_tasks_df.height
        assert result["id"].to_list() == [1, 2, 3]

    def test_filter_tasks_by_ids(self, sample_tasks_df):
        """Filtering by IDs should keep matching tasks only."""
        result = db.filter_tasks(sample_tasks_df, Filter(ids=[2]))
        assert result.height == 1
        assert result["id"].to_list() == [2]

    def test_filter_tasks_by_title_case_insensitive(self, sample_tasks_df):
        """Title filter should be case-insensitive."""
        result = db.filter_tasks(sample_tasks_df, Filter(title="PLAN"))
        assert result.height == 1
        assert result["title"].to_list() == ["Plan project"]

    def test_filter_tasks_by_project_and_priority(self, sample_tasks_df):
        """Project and priority filters should match exactly."""
        result = db.filter_tasks(sample_tasks_df, Filter(project="home", priority="H"))
        assert result.height == 1
        assert result["id"].to_list() == [1]

    def test_filter_tasks_by_due_date(self, sample_tasks_df):
        """Due date filter should match ISO-formatted dates."""
        result = db.filter_tasks(sample_tasks_df, Filter(due=date(2025, 1, 10)))
        assert result.height == 1
        assert result["id"].to_list() == [1]

    def test_filter_tasks_by_tags_include_and_exclude(self, sample_tasks_df):
        """Tag filters should handle inclusion and exclusion."""
        result = db.filter_tasks(sample_tasks_df, Filter(tags=["+home", "-errand"]))
        assert result.height == 1
        assert result["id"].to_list() == [3]


class TestInitDb:
    """Tests for init_db function."""
    
    def test_init_db_new(self, tmp_path):
        """Test initializing new database."""
        db_file = tmp_path / "db.json"
        
        db.init_db(str(db_file))
        
        assert db_file.exists()
        
        with open(db_file) as f:
            data = json.load(f)
        
        assert data == []  # Empty database is empty array
    
    def test_init_db_creates_directory(self, tmp_path):
        """Test that init_db creates directory if it doesn't exist."""
        db_file = tmp_path / "nested" / "path" / "db.json"
        
        db.init_db(str(db_file))
        
        assert db_file.exists()
        assert db_file.parent.exists()
    
    def test_init_db_existing_cancel(self, tmp_path):
        """Test initializing when database exists and user cancels."""
        db_file = tmp_path / "db.json"
        db_file.write_text('[{"test": "data"}]')
        
        with patch("builtins.input", return_value="n"):
            db.init_db(str(db_file))
        
        # Database should remain unchanged
        with open(db_file) as f:
            data = json.load(f)
        
        assert data == [{"test": "data"}]
    
    def test_init_db_existing_overwrite(self, tmp_path):
        """Test initializing when database exists and user confirms overwrite."""
        db_file = tmp_path / "db.json"
        db_file.write_text('[{"test": "old data"}]')
        
        with patch("builtins.input", return_value="y"):
            db.init_db(str(db_file))
        
        # Database should be overwritten (empty array)
        with open(db_file) as f:
            data = json.load(f)
        
        assert data == []
    
    def test_init_db_existing_overwrite_lowercase_y(self, tmp_path):
        """Test overwrite with lowercase 'y'."""
        db_file = tmp_path / "db.json"
        db_file.write_text('[{"test": "old"}]')
        
        with patch("builtins.input", return_value="y"):
            db.init_db(str(db_file))
        
        with open(db_file) as f:
            data = json.load(f)
        
        assert data == []
    
    def test_init_db_existing_cancel_uppercase_n(self, tmp_path):
        """Test cancel with uppercase 'N'."""
        db_file = tmp_path / "db.json"
        original_data = [{"test": "data"}]
        db_file.write_text(json.dumps(original_data))
        
        with patch("builtins.input", return_value="N"):
            db.init_db(str(db_file))
        
        # Should not overwrite (user cancelled)
        with open(db_file) as f:
            data = json.load(f)
        
        assert data == original_data
