import pytest
from pydantic import ValidationError
from datetime import date, datetime
from uuid import UUID, uuid4

from task.models import Task, Filter, Modification, ParsedCommand, Config


class TestTask:
    """Tests for the Task model."""
    
    def test_task_creation_with_minimal_fields(self):
        """Test creating a task with only required fields."""
        task = Task(title="Test task", id=None)
        assert task.title == "Test task"
        assert isinstance(task.uuid, UUID)
        assert task.id is None
        assert task.project is None
        assert task.priority is None
        assert task.status == "pending"
        assert task.rank_score == 0.0
        assert isinstance(task.created_at, datetime)
        assert isinstance(task.updated_at, datetime)
        assert task.depends == []
        assert task.blocks == []
        assert task.tags == []
    
    def test_task_creation_with_all_fields(self):
        """Test creating a task with all fields."""
        test_uuid = uuid4()
        test_date = date(2024, 1, 15)
        test_datetime = datetime(2024, 1, 15, 10, 30)
        dep_uuid = uuid4()
        block_uuid = uuid4()
        
        task = Task(
            uuid=test_uuid,
            id=1,
            title="Complete project",
            project="work",
            priority="H",
            due=test_date,
            scheduled=test_date,
            depends=[dep_uuid],
            blocks=[block_uuid],
            started_at=test_datetime,
            tags=["urgent", "important"],
            status="active",
            rank_score=42.5,
            created_at=test_datetime,
            updated_at=test_datetime,
            deleted_at=None,
        )
        
        assert task.uuid == test_uuid
        assert task.id == 1
        assert task.title == "Complete project"
        assert task.priority == "H"
        assert len(task.tags) == 2
        assert task.depends == [dep_uuid]
        assert task.blocks == [block_uuid]
    
    def test_task_priority_valid_values(self):
        """Test that valid priority values are accepted."""
        for priority in ["H", "M", "L"]:
            task = Task(title="Test", id=None, priority=priority)
            assert task.priority == priority
        
        # None should also work
        task = Task(title="Test", id=None, priority=None)
        assert task.priority is None
    
    def test_task_priority_invalid_value(self):
        """Test that invalid priority values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Task(title="Test", id=None, priority="X")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("priority",) for error in errors)
        assert any("literal" in str(error["type"]).lower() or "input" in str(error["type"]).lower() 
                   for error in errors if error["loc"] == ("priority",))
    
    def test_task_priority_empty_string(self):
        """Test that empty string for priority raises ValidationError."""
        with pytest.raises(ValidationError):
            Task(title="Test", id=None, priority="")
    
    def test_task_defaults_separate_instances(self):
        """Test that default factory values create separate instances."""
        task1 = Task(title="Task 1", id=None)
        task2 = Task(title="Task 2", id=None)
        
        # UUIDs should be different
        assert task1.uuid != task2.uuid
        
        # Lists should be separate instances
        dep_uuid = uuid4()
        task1.depends.append(dep_uuid)
        assert len(task1.depends) == 1
        assert len(task2.depends) == 0
        assert dep_uuid in task1.depends
        assert dep_uuid not in task2.depends
        
        # Tags should be separate instances
        task1.tags.append("tag1")
        assert "tag1" in task1.tags
        assert "tag1" not in task2.tags
    
    def test_task_is_frozen(self):
        """Test that Task model is immutable (frozen)."""
        task = Task(title="Test task", id=None)
        
        with pytest.raises(ValidationError) as exc_info:
            task.title = "New title"
        
        errors = exc_info.value.errors()
        assert any("frozen" in str(error["type"]).lower() for error in errors)
    
    def test_task_missing_required_field(self):
        """Test that missing required field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Task()
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("title",) for error in errors)
    
    def test_task_status_default(self):
        """Test that status defaults to 'pending'."""
        task = Task(title="Test", id=None)
        assert task.status == "pending"
    
    def test_task_datetime_defaults(self):
        """Test that datetime fields use default_factory."""
        task1 = Task(title="Task 1", id=None)
        task2 = Task(title="Task 2", id=None)
        
        # They should be different timestamps (with small tolerance for execution speed)
        assert isinstance(task1.created_at, datetime)
        assert isinstance(task2.created_at, datetime)
        assert isinstance(task1.updated_at, datetime)
        assert isinstance(task2.updated_at, datetime)


class TestFilter:
    """Tests for the Filter model."""
    
    def test_filter_empty_creation(self):
        """Test creating an empty filter."""
        filter_obj = Filter()
        assert filter_obj.ids == []
        assert filter_obj.title is None
        assert filter_obj.project is None
        assert filter_obj.priority is None
        assert filter_obj.tags == []
        assert filter_obj.due is None
        assert filter_obj.scheduled is None
        assert filter_obj.depends is None
        assert filter_obj.blocks is None
        assert filter_obj.status is None
    
    def test_filter_with_criteria(self):
        """Test creating a filter with criteria."""
        test_date = date(2024, 1, 15)
        filter_obj = Filter(
            ids=[1, 2, 3],
            title="test",
            project="work",
            priority="H",
            due=test_date,
            scheduled=test_date,
            depends=5,
            blocks=10,
            tags=["urgent"],
            status="active",
        )
        
        assert filter_obj.ids == [1, 2, 3]
        assert filter_obj.title == "test"
        assert filter_obj.priority == "H"
        assert filter_obj.due == test_date
        assert filter_obj.depends == 5
        assert filter_obj.blocks == 10
        assert "urgent" in filter_obj.tags
        assert filter_obj.status == "active"
    
    def test_filter_priority_valid_values(self):
        """Test that valid priority values are accepted."""
        for priority in ["H", "M", "L"]:
            filter_obj = Filter(priority=priority)
            assert filter_obj.priority == priority
        
        filter_obj = Filter(priority=None)
        assert filter_obj.priority is None
    
    def test_filter_priority_invalid_value(self):
        """Test that invalid priority values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Filter(priority="X")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("priority",) for error in errors)
    
    def test_filter_defaults_separate_instances(self):
        """Test that default factory values create separate instances."""
        filter1 = Filter()
        filter2 = Filter()
        
        filter1.ids.append(1)
        assert len(filter1.ids) == 1
        assert len(filter2.ids) == 0
        
        filter1.tags.append("tag1")
        assert "tag1" in filter1.tags
        assert "tag1" not in filter2.tags


class TestModification:
    """Tests for the Modification model."""
    
    def test_modification_empty_creation(self):
        """Test creating an empty modification."""
        mod = Modification()
        assert all(getattr(mod, field) is None for field in [
            "title", "project", "priority", "due", "scheduled",
            "depends", "blocks", "tags"
        ])
    
    def test_modification_with_changes(self):
        """Test creating a modification with changes."""
        test_date = date(2024, 1, 15)
        mod = Modification(
            title="New title",
            project="new_project",
            priority="M",
            due=test_date,
            scheduled=test_date,
            depends=[1, -2],  # Add 1, remove 2
            blocks=[3, -4],   # Add 3, remove 4
            tags=["+tag1", "-tag2"],
        )
        
        assert mod.title == "New title"
        assert mod.project == "new_project"
        assert mod.priority == "M"
        assert mod.due == test_date
        assert mod.scheduled == test_date
        assert mod.depends == [1, -2]
        assert mod.blocks == [3, -4]
        assert mod.tags == ["+tag1", "-tag2"]
    
    def test_modification_priority_valid_values(self):
        """Test that valid priority values are accepted."""
        for priority in ["H", "M", "L"]:
            mod = Modification(priority=priority)
            assert mod.priority == priority
        
        mod = Modification(priority=None)
        assert mod.priority is None
    
    def test_modification_priority_invalid_value(self):
        """Test that invalid priority values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Modification(priority="X")
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("priority",) for error in errors)
    
    def test_modification_partial_fields(self):
        """Test that modification can have only some fields set."""
        mod = Modification(title="Only title")
        assert mod.title == "Only title"
        assert mod.priority is None
        assert mod.depends is None


class TestParsedCommand:
    """Tests for the ParsedCommand model."""
    
    def test_parsed_command_minimal(self):
        """Test creating a parsed command with just command."""
        cmd = ParsedCommand(command="list")
        assert cmd.command == "list"
        assert cmd.filter is None
        assert cmd.modification is None
    
    def test_parsed_command_with_filter(self):
        """Test creating a parsed command with filter."""
        filter_obj = Filter(ids=[1, 2], priority="H")
        cmd = ParsedCommand(command="list", filter=filter_obj)
        assert cmd.command == "list"
        assert cmd.filter is not None
        assert cmd.filter.ids == [1, 2]
        assert cmd.filter.priority == "H"
        assert cmd.modification is None
    
    def test_parsed_command_with_modification(self):
        """Test creating a parsed command with modification."""
        mod = Modification(title="New title", priority="L")
        cmd = ParsedCommand(command="modify", modification=mod)
        assert cmd.command == "modify"
        assert cmd.modification is not None
        assert cmd.modification.title == "New title"
        assert cmd.modification.priority == "L"
        assert cmd.filter is None
    
    def test_parsed_command_with_both_filter_and_modification(self):
        """Test creating a parsed command with both filter and modification."""
        filter_obj = Filter(ids=[1])
        mod = Modification(priority="H")
        cmd = ParsedCommand(command="modify", filter=filter_obj, modification=mod)
        assert cmd.command == "modify"
        assert cmd.filter is not None
        assert cmd.modification is not None
        assert cmd.filter.ids == [1]
        assert cmd.modification.priority == "H"
    
    def test_parsed_command_missing_command(self):
        """Test that missing command raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ParsedCommand()
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("command",) for error in errors)


class TestConfig:
    """Tests for the Config model."""
    
    def test_config_creation_minimal(self):
        """Test creating config with only required field."""
        config = Config(db_path="/path/to/db")
        assert config.db_path == "/path/to/db"
        assert config.current_context == "default"
        assert isinstance(config.urgency_coefficients, dict)
        assert isinstance(config.contexts, dict)
    
    def test_config_urgency_coefficients_default(self):
        """Test that urgency_coefficients has expected default values."""
        config = Config(db_path="/path/to/db")
        
        assert config.urgency_coefficients["next_tag"] == 15.0
        assert config.urgency_coefficients["due"] == 12.0
        assert config.urgency_coefficients["blocking"] == 8.0
        assert config.urgency_coefficients["priority_h"] == 6.0
        assert config.urgency_coefficients["priority_m"] == 3.9
        assert config.urgency_coefficients["priority_l"] == 1.8
        assert config.urgency_coefficients["scheduled"] == 5.0
        assert config.urgency_coefficients["active"] == 4.0
        assert config.urgency_coefficients["age"] == 2.0
        assert config.urgency_coefficients["annotations"] == 1.0
        assert config.urgency_coefficients["tags"] == 1.0
        assert config.urgency_coefficients["project"] == 1.0
        assert config.urgency_coefficients["waiting"] == -3.0
        assert config.urgency_coefficients["blocked"] == -5.0
    
    def test_config_urgency_coefficients_all_keys(self):
        """Test that all expected keys are present in default urgency_coefficients."""
        config = Config(db_path="/path/to/db")
        expected_keys = {
            "next_tag", "due", "blocking", "priority_h", "priority_m", "priority_l",
            "scheduled", "active", "age", "annotations", "tags", "project",
            "waiting", "blocked"
        }
        assert set(config.urgency_coefficients.keys()) == expected_keys
    
    def test_config_with_custom_values(self):
        """Test creating config with custom values."""
        custom_coeffs = {"priority_h": 10.0, "due": 20.0}
        config = Config(
            db_path="/custom/path",
            current_context="work",
            urgency_coefficients=custom_coeffs,
            contexts={"work": "/work/db", "home": "/home/db"}
        )
        
        assert config.db_path == "/custom/path"
        assert config.current_context == "work"
        assert config.urgency_coefficients == custom_coeffs
        assert config.contexts == {"work": "/work/db", "home": "/home/db"}
    
    def test_config_defaults_separate_instances(self):
        """Test that default factory values create separate instances."""
        config1 = Config(db_path="/path1")
        config2 = Config(db_path="/path2")
        
        config1.contexts["ctx1"] = "path1"
        assert "ctx1" in config1.contexts
        assert "ctx1" not in config2.contexts
        
        config1.urgency_coefficients["custom"] = 10.0
        assert "custom" in config1.urgency_coefficients
        assert "custom" not in config2.urgency_coefficients
    
    def test_config_missing_db_path(self):
        """Test that missing db_path raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Config()
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("db_path",) for error in errors)

