"""Tests for database add operations."""
import pytest
import polars as pl
from uuid import UUID

from task import db
from task.models import Task, Config


class TestGetNextId:
    """Tests for get_next_id function."""
    
    def test_get_next_id_empty_database(self):
        """Test getting next ID when database is empty."""
        tasks = None
        next_id = db.get_next_id(tasks)
        assert next_id == 1
    
    def test_get_next_id_empty_dataframe(self):
        """Test getting next ID when DataFrame is empty."""
        tasks = pl.DataFrame()
        next_id = db.get_next_id(tasks)
        assert next_id == 1
    
    def test_get_next_id_first_task(self):
        """Test getting next ID when adding first task."""
        task = Task(id=1, title="First task")
        tasks = pl.DataFrame([task.model_dump(mode='json')])
        
        next_id = db.get_next_id(tasks)
        assert next_id == 2
    
    def test_get_next_id_multiple_tasks(self):
        """Test getting next ID with multiple existing tasks."""
        tasks_data = [
            Task(id=1, title="Task 1").model_dump(mode='json'),
            Task(id=2, title="Task 2").model_dump(mode='json'),
            Task(id=5, title="Task 5").model_dump(mode='json'),
        ]
        tasks = pl.DataFrame(tasks_data)
        
        next_id = db.get_next_id(tasks)
        assert next_id == 6
    
    def test_get_next_id_all_none_ids(self):
        """Test getting next ID when all tasks have None IDs."""
        task = Task(id=None, title="Task without ID")
        tasks = pl.DataFrame([task.model_dump(mode='json')])
        
        next_id = db.get_next_id(tasks)
        assert next_id == 1


class TestAddTask:
    """Tests for add_task function."""
    
    def test_add_task_to_empty_database(self):
        """Test adding task when database is None."""
        task = Task(id=1, title="First task")
        
        result = db.add_task(None, task)
        
        assert result is not None
        assert result.height == 1
        assert result["id"][0] == 1
        assert result["title"][0] == "First task"
        # UUID should be string when using mode='json'
        assert isinstance(result["uuid"][0], str)
    
    def test_add_task_to_existing_database(self):
        """Test adding task to existing DataFrame."""
        existing_task = Task(id=1, title="Existing task")
        tasks = pl.DataFrame([existing_task.model_dump(mode='json')])
        
        new_task = Task(id=2, title="New task")
        result = db.add_task(tasks, new_task)
        
        assert result.height == 2
        assert result["id"].to_list() == [1, 2]
        assert result["title"].to_list() == ["Existing task", "New task"]
    
    def test_add_task_immutability(self):
        """Test that add_task returns new DataFrame without mutating input."""
        existing_task = Task(id=1, title="Existing task")
        tasks = pl.DataFrame([existing_task.model_dump(mode='json')])
        original_height = tasks.height
        
        new_task = Task(id=2, title="New task")
        result = db.add_task(tasks, new_task)
        
        # Original DataFrame should be unchanged
        assert tasks.height == original_height
        # New DataFrame should have more rows
        assert result.height == original_height + 1
    
    def test_add_task_with_all_fields(self):
        """Test adding task with all fields populated."""
        task = Task(
            id=1,
            title="Complete project",
            project="work",
            priority="H",
            status="active"
        )
        
        result = db.add_task(None, task)
        
        assert result.height == 1
        assert result["project"][0] == "work"
        assert result["priority"][0] == "H"
        assert result["status"][0] == "active"
        # UUID is stored as string in dict, verify it's present
        uuid_value = result["uuid"][0]
        assert uuid_value is not None
        # Can be UUID object (if from dict) or string (if from JSON)
        if isinstance(uuid_value, str):
            # Verify it's a valid UUID string
            UUID(uuid_value)
        else:
            assert isinstance(uuid_value, UUID)
    
    def test_add_task_sorted_by_id(self):
        """Test that tasks are sorted by ID after adding."""
        tasks_data = [
            Task(id=3, title="Task 3").model_dump(mode='json'),
            Task(id=1, title="Task 1").model_dump(mode='json'),
        ]
        tasks = pl.DataFrame(tasks_data)
        
        new_task = Task(id=2, title="Task 2")
        result = db.add_task(tasks, new_task)
        
        assert result["id"].to_list() == [1, 2, 3]
        assert result["title"].to_list() == ["Task 1", "Task 2", "Task 3"]

