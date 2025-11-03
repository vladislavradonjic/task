"""Tests for command parsing functions."""
import pytest

from task.parse import parse_modification, separate_sections, extract_tags, extract_properties
from task.models import Modification


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

