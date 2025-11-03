"""Tests for command parsing functions."""
import pytest

from task.parse import parse_modification, separate_sections, extract_tags, extract_properties, extract_ids, parse_filter
from task.models import Modification, Filter


class TestExtractTags:
    """Tests for extract_tags function."""
    
    def test_extract_tags_single_plus(self):
        """Test extracting single tag with +."""
        tags, remaining = extract_tags(["Buy", "+urgent"])
        
        assert tags == ["+urgent"]
        assert remaining == ["Buy"]
    
    def test_extract_tags_single_minus(self):
        """Test extracting single tag with -."""
        tags, remaining = extract_tags(["Task", "-deprecated"])
        
        assert tags == ["-deprecated"]
        assert remaining == ["Task"]
    
    def test_extract_tags_multiple(self):
        """Test extracting multiple tags."""
        tags, remaining = extract_tags(["Buy", "groceries", "+shopping", "+urgent", "-old"])
        
        assert tags == ["+shopping", "+urgent", "-old"]
        assert remaining == ["Buy", "groceries"]
    
    def test_extract_tags_no_tags(self):
        """Test with no tags present."""
        tags, remaining = extract_tags(["Buy", "groceries"])
        
        assert tags == []
        assert remaining == ["Buy", "groceries"]
    
    def test_extract_tags_all_tags(self):
        """Test when all arguments are tags."""
        tags, remaining = extract_tags(["+tag1", "+tag2"])
        
        assert tags == ["+tag1", "+tag2"]
        assert remaining == []
    
    def test_extract_tags_empty(self):
        """Test with empty list."""
        tags, remaining = extract_tags([])
        
        assert tags == []
        assert remaining == []


class TestExtractProperties:
    """Tests for extract_properties function."""
    
    def test_extract_properties_project(self):
        """Test extracting project property."""
        props, remaining = extract_properties(["Buy", "project:home"])
        
        assert props == {"project": "home"}
        assert remaining == ["Buy"]
    
    def test_extract_properties_priority(self):
        """Test extracting priority property."""
        props, remaining = extract_properties(["Task", "priority:H"])
        
        assert props == {"priority": "H"}
        assert remaining == ["Task"]
    
    def test_extract_properties_multiple(self):
        """Test extracting multiple properties."""
        props, remaining = extract_properties(["Task", "project:work", "priority:M"])
        
        assert props == {"project": "work", "priority": "M"}
        assert remaining == ["Task"]
    
    def test_extract_properties_with_spaces(self):
        """Test properties with spaces in values."""
        props, remaining = extract_properties(["Task", "project:my project"])
        
        assert props == {"project": "my project"}
        assert remaining == ["Task"]
    
    def test_extract_properties_quoted_value(self):
        """Test properties with quoted values (strips quotes)."""
        props, remaining = extract_properties(["Task", "project:'work project'"])
        
        assert props == {"project": "work project"}
        assert remaining == ["Task"]
    
    def test_extract_properties_no_properties(self):
        """Test with no properties."""
        props, remaining = extract_properties(["Buy", "groceries"])
        
        assert props == {}
        assert remaining == ["Buy", "groceries"]
    
    def test_extract_properties_trailing_colon(self):
        """Test that trailing colon is not treated as property."""
        props, remaining = extract_properties(["Task", "project:"])
        
        assert props == {}
        assert remaining == ["Task", "project:"]
    
    def test_extract_properties_empty(self):
        """Test with empty list."""
        props, remaining = extract_properties([])
        
        assert props == {}
        assert remaining == []
    
    def test_extract_properties_priority_case_insensitive(self):
        """Test that priority is normalized to uppercase."""
        props, remaining = extract_properties(["Task", "priority:h"])
        
        assert props == {"priority": "H"}
        assert remaining == ["Task"]
    
    def test_extract_properties_priority_lowercase_m(self):
        """Test that lowercase 'm' is normalized to 'M'."""
        props, remaining = extract_properties(["Task", "priority:m"])
        
        assert props == {"priority": "M"}
        assert remaining == ["Task"]
    
    def test_extract_properties_priority_lowercase_l(self):
        """Test that lowercase 'l' is normalized to 'L'."""
        props, remaining = extract_properties(["Task", "priority:l"])
        
        assert props == {"priority": "L"}
        assert remaining == ["Task"]
    
    def test_extract_properties_priority_invalid_ignored(self):
        """Test that invalid priority values are ignored."""
        props, remaining = extract_properties(["Task", "priority:invalid"])
        
        assert props == {}
        assert remaining == ["Task"]
    
    def test_extract_properties_priority_mixed_case_ignored(self):
        """Test that invalid mixed-case priority is ignored."""
        props, remaining = extract_properties(["Task", "priority:Hi"])
        
        assert props == {}
        assert remaining == ["Task"]
    
    def test_extract_properties_due_date(self):
        """Test extracting due date property."""
        props, remaining = extract_properties(["Task", "due:tomorrow"])
        
        # Should parse "tomorrow" as a date
        from datetime import date
        assert isinstance(props["due"], date)
        assert props["due"] >= date.today()
        assert remaining == ["Task"]
    
    def test_extract_properties_scheduled_date(self):
        """Test extracting scheduled date property."""
        props, remaining = extract_properties(["Task", "scheduled:2025-12-25"])
        
        # Should parse as a date
        from datetime import date
        assert isinstance(props["scheduled"], date)
        assert props["scheduled"] == date(2025, 12, 25)
        assert remaining == ["Task"]
    
    def test_extract_properties_both_dates(self):
        """Test extracting both due and scheduled dates."""
        props, remaining = extract_properties([
            "Task", "due:tomorrow", "scheduled:2025-12-01"
        ])
        
        from datetime import date
        assert isinstance(props["due"], date)
        assert isinstance(props["scheduled"], date)
        assert props["scheduled"] == date(2025, 12, 1)
        assert remaining == ["Task"]
    
    def test_extract_properties_invalid_date_ignored(self):
        """Test that invalid date values are ignored."""
        props, remaining = extract_properties(["Task", "due:not-a-date"])
        
        # Invalid date should be ignored (not in props)
        assert "due" not in props
        assert remaining == ["Task"]


class TestParseModification:
    """Tests for parse_modification function."""
    
    def test_parse_modification_single_word(self):
        """Test parsing modification with single word title."""
        modification = parse_modification(["Buy"])
        
        assert isinstance(modification, Modification)
        assert modification.title == "Buy"
        assert modification.project is None
        assert modification.priority is None
        assert modification.tags is None or modification.tags == []
    
    def test_parse_modification_multiple_words(self):
        """Test parsing modification with multiple words."""
        modification = parse_modification(["Buy", "groceries", "today"])
        
        assert modification.title == "Buy groceries today"
    
    def test_parse_modification_empty(self):
        """Test parsing empty modification section returns Modification with empty title."""
        modification = parse_modification([])
        
        assert isinstance(modification, Modification)
        assert modification.title == ""  # Empty string from " ".join([])
        assert modification.project is None
        assert modification.priority is None
        assert modification.tags is None or modification.tags == []
    
    def test_parse_modification_preserves_spacing(self):
        """Test that spacing is preserved when joining words."""
        modification = parse_modification(["Complete", "the", "project"])
        
        assert modification.title == "Complete the project"
    
    def test_parse_modification_with_project(self):
        """Test parsing with project property."""
        modification = parse_modification(["Buy", "groceries", "project:home"])
        
        assert modification.title == "Buy groceries"
        assert modification.project == "home"
    
    def test_parse_modification_with_priority(self):
        """Test parsing with priority property."""
        modification = parse_modification(["Complete", "task", "priority:H"])
        
        assert modification.title == "Complete task"
        assert modification.priority == "H"
    
    def test_parse_modification_with_tags(self):
        """Test parsing with tags."""
        modification = parse_modification(["Task", "+urgent", "+shopping"])
        
        assert modification.title == "Task"
        assert modification.tags == ["+urgent", "+shopping"]
    
    def test_parse_modification_all_properties(self):
        """Test parsing with project, priority, and tags."""
        modification = parse_modification([
            "Complete", "project", "project:work", "priority:M", "+urgent"
        ])
        
        assert modification.title == "Complete project"
        assert modification.project == "work"
        assert modification.priority == "M"
        assert modification.tags == ["+urgent"]
    
    def test_parse_modification_minus_tag(self):
        """Test parsing with minus tag (should still be included in tags list)."""
        modification = parse_modification(["Task", "-old"])
        
        assert modification.title == "Task"
        assert modification.tags == ["-old"]
    
    def test_parse_modification_lowercase_priority_normalized(self):
        """Test that lowercase priority is normalized to uppercase."""
        modification = parse_modification(["Task", "priority:h"])
        
        assert modification.priority == "H"  # Should be normalized to uppercase
    
    def test_parse_modification_with_due_date(self):
        """Test parsing with due date property."""
        modification = parse_modification(["Task", "due:tomorrow"])
        
        from datetime import date
        assert modification.title == "Task"
        assert isinstance(modification.due, date)
        assert modification.due >= date.today()
    
    def test_parse_modification_with_scheduled_date(self):
        """Test parsing with scheduled date property."""
        modification = parse_modification(["Task", "scheduled:monday"])
        
        from datetime import date
        assert modification.title == "Task"
        assert isinstance(modification.scheduled, date)
        assert modification.scheduled >= date.today()
    
    def test_parse_modification_with_both_dates(self):
        """Test parsing with both due and scheduled dates."""
        modification = parse_modification([
            "Complete", "project", "due:2025-12-25", "scheduled:2025-12-01"
        ])
        
        from datetime import date
        assert modification.title == "Complete project"
        assert modification.due == date(2025, 12, 25)
        assert modification.scheduled == date(2025, 12, 1)
    
    def test_parse_modification_with_all_properties_including_dates(self):
        """Test parsing with all properties including dates."""
        modification = parse_modification([
            "Complete", "project", 
            "project:work", 
            "priority:M", 
            "due:tomorrow",
            "scheduled:monday",
            "+urgent"
        ])
        
        from datetime import date
        assert modification.title == "Complete project"
        assert modification.project == "work"
        assert modification.priority == "M"
        assert isinstance(modification.due, date)
        assert isinstance(modification.scheduled, date)
        assert modification.tags == ["+urgent"]


class TestSeparateSections:
    """Tests for separate_sections function."""
    
    def test_separate_sections_command_in_middle(self):
        """Test separating sections when command is in middle."""
        commands = {"add", "show", "done"}
        args = ["filter", "add", "Buy", "groceries"]
        
        cmd, filter_section, mod_section = separate_sections(args, commands)
        
        assert cmd == "add"
        assert filter_section == ["filter"]
        assert mod_section == ["Buy", "groceries"]
    
    def test_separate_sections_command_at_start(self):
        """Test separating sections when command is at start."""
        commands = {"add", "show", "done"}
        args = ["add", "Buy", "groceries"]
        
        cmd, filter_section, mod_section = separate_sections(args, commands)
        
        assert cmd == "add"
        assert filter_section == []
        assert mod_section == ["Buy", "groceries"]
    
    def test_separate_sections_no_command(self):
        """Test when no command is found."""
        commands = {"add", "show", "done"}
        args = ["Buy", "groceries"]
        
        cmd, filter_section, mod_section = separate_sections(args, commands)
        
        assert cmd is None
        assert filter_section is None
        assert mod_section is None
    
    def test_separate_sections_case_insensitive(self):
        """Test that command matching is case insensitive."""
        commands = {"add", "show", "done"}
        args = ["ADD", "Task"]
        
        cmd, filter_section, mod_section = separate_sections(args, commands)
        
        assert cmd == "add"
        assert mod_section == ["Task"]
    
    def test_separate_sections_multiple_commands_takes_first(self):
        """Test that first matching command is used."""
        commands = {"add", "show", "done"}
        args = ["show", "add", "Task"]
        
        cmd, filter_section, mod_section = separate_sections(args, commands)
        
        assert cmd == "show"
        assert filter_section == []
        assert mod_section == ["add", "Task"]


class TestExtractIds:
    """Tests for extract_ids function."""
    
    def test_extract_ids_single_id(self):
        """Test extracting single ID."""
        ids, remaining = extract_ids(["1", "task"])
        
        assert ids == [1]
        assert remaining == ["task"]
    
    def test_extract_ids_multiple_ids(self):
        """Test extracting multiple IDs."""
        ids, remaining = extract_ids(["1", "2", "3", "task"])
        
        assert ids == [1, 2, 3]
        assert remaining == ["task"]
    
    def test_extract_ids_only_ids(self):
        """Test extracting when all arguments are IDs."""
        ids, remaining = extract_ids(["1", "2", "3"])
        
        assert ids == [1, 2, 3]
        assert remaining == []
    
    def test_extract_ids_no_ids(self):
        """Test extracting when no IDs are present."""
        ids, remaining = extract_ids(["task", "project:work"])
        
        assert ids == []
        assert remaining == ["task", "project:work"]
    
    def test_extract_ids_mixed_order(self):
        """Test extracting IDs in mixed order with other arguments."""
        ids, remaining = extract_ids(["task", "1", "project:work", "2", "priority:H"])
        
        assert ids == [1, 2]
        assert remaining == ["task", "project:work", "priority:H"]
    
    def test_extract_ids_empty_list(self):
        """Test extracting from empty list."""
        ids, remaining = extract_ids([])
        
        assert ids == []
        assert remaining == []
    
    def test_extract_ids_numeric_strings_only(self):
        """Test that only purely numeric strings are extracted."""
        ids, remaining = extract_ids(["1", "123", "abc", "1a", "-5", "0"])
        
        assert ids == [1, 123, 0]  # Only pure digits
        assert remaining == ["abc", "1a", "-5"]  # Non-digit strings kept


class TestParseFilter:
    """Tests for parse_filter function."""
    
    def test_parse_filter_empty(self):
        """Test parsing empty filter section."""
        filter_obj = parse_filter([])
        
        assert isinstance(filter_obj, Filter)
        assert filter_obj.ids == []
        assert filter_obj.title == ""
        assert filter_obj.project is None
        assert filter_obj.priority is None
        assert filter_obj.tags == []
    
    def test_parse_filter_ids_only(self):
        """Test parsing filter with only IDs."""
        filter_obj = parse_filter(["1", "2", "3"])
        
        assert filter_obj.ids == [1, 2, 3]
        assert filter_obj.title == ""
        assert filter_obj.project is None
    
    def test_parse_filter_title_only(self):
        """Test parsing filter with only title text."""
        filter_obj = parse_filter(["Buy", "groceries"])
        
        assert filter_obj.ids == []
        assert filter_obj.title == "Buy groceries"
        assert filter_obj.project is None
    
    def test_parse_filter_with_project(self):
        """Test parsing filter with project property."""
        filter_obj = parse_filter(["project:work"])
        
        assert filter_obj.ids == []
        assert filter_obj.title == ""
        assert filter_obj.project == "work"
    
    def test_parse_filter_with_priority(self):
        """Test parsing filter with priority property."""
        filter_obj = parse_filter(["priority:H"])
        
        assert filter_obj.ids == []
        assert filter_obj.title == ""
        assert filter_obj.priority == "H"
    
    def test_parse_filter_with_tags(self):
        """Test parsing filter with tags."""
        filter_obj = parse_filter(["+urgent", "+shopping"])
        
        assert filter_obj.ids == []
        assert filter_obj.title == ""
        assert filter_obj.tags == ["+urgent", "+shopping"]
    
    def test_parse_filter_with_ids_and_project(self):
        """Test parsing filter with IDs and project."""
        filter_obj = parse_filter(["1", "2", "project:work"])
        
        assert filter_obj.ids == [1, 2]
        assert filter_obj.project == "work"
        assert filter_obj.title == ""
    
    def test_parse_filter_with_ids_and_title(self):
        """Test parsing filter with IDs and title."""
        filter_obj = parse_filter(["1", "Buy", "groceries"])
        
        assert filter_obj.ids == [1]
        assert filter_obj.title == "Buy groceries"
    
    def test_parse_filter_with_all_properties(self):
        """Test parsing filter with all types of properties."""
        filter_obj = parse_filter([
            "1", "2",
            "project:work",
            "priority:M",
            "+urgent",
            "Buy", "groceries"
        ])
        
        assert filter_obj.ids == [1, 2]
        assert filter_obj.project == "work"
        assert filter_obj.priority == "M"
        assert filter_obj.tags == ["+urgent"]
        assert filter_obj.title == "Buy groceries"
    
    def test_parse_filter_with_status(self):
        """Test parsing filter with status property."""
        filter_obj = parse_filter(["status:pending"])
        
        assert filter_obj.ids == []
        assert filter_obj.status == "pending"
    
    def test_parse_filter_with_due_date(self):
        """Test parsing filter with due date."""
        filter_obj = parse_filter(["due:tomorrow"])
        
        from datetime import date
        assert filter_obj.ids == []
        assert isinstance(filter_obj.due, date)
        assert filter_obj.due >= date.today()
    
    def test_parse_filter_with_scheduled_date(self):
        """Test parsing filter with scheduled date."""
        filter_obj = parse_filter(["scheduled:2025-12-25"])
        
        from datetime import date
        assert filter_obj.ids == []
        assert filter_obj.scheduled == date(2025, 12, 25)
    
    def test_parse_filter_with_depends(self):
        """Test parsing filter with depends property."""
        filter_obj = parse_filter(["depends:5"])
        
        assert filter_obj.ids == []
        assert filter_obj.depends == 5
    
    def test_parse_filter_with_blocks(self):
        """Test parsing filter with blocks property."""
        filter_obj = parse_filter(["blocks:3"])
        
        assert filter_obj.ids == []
        assert filter_obj.blocks == 3
    
    def test_parse_filter_priority_case_insensitive(self):
        """Test that priority is normalized to uppercase."""
        filter_obj = parse_filter(["priority:h"])
        
        assert filter_obj.priority == "H"
    
    def test_parse_filter_invalid_priority_ignored(self):
        """Test that invalid priority is ignored."""
        filter_obj = parse_filter(["priority:invalid"])
        
        assert filter_obj.priority is None
    
    def test_parse_filter_invalid_date_ignored(self):
        """Test that invalid date is ignored."""
        filter_obj = parse_filter(["due:not-a-date"])
        
        assert filter_obj.due is None
    
    def test_parse_filter_complex_example(self):
        """Test a complex real-world filter example."""
        filter_obj = parse_filter([
            "1", "2", "3",
            "project:home",
            "priority:H",
            "status:active",
            "+urgent",
            "-old",
            "Buy", "groceries", "today"
        ])
        
        from datetime import date
        assert filter_obj.ids == [1, 2, 3]
        assert filter_obj.project == "home"
        assert filter_obj.priority == "H"
        assert filter_obj.status == "active"
        assert filter_obj.tags == ["+urgent", "-old"]
        assert filter_obj.title == "Buy groceries today"

