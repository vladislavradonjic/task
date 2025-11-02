"""Tests for command parsing functions."""
import pytest

from task.parse import parse_modification, separate_sections
from task.models import Modification


class TestParseModification:
    """Tests for parse_modification function."""
    
    def test_parse_modification_single_word(self):
        """Test parsing modification with single word title."""
        modification = parse_modification(["Buy"])
        
        assert isinstance(modification, Modification)
        assert modification.title == "Buy"
        assert modification.project is None
        assert modification.priority is None
    
    def test_parse_modification_multiple_words(self):
        """Test parsing modification with multiple words."""
        modification = parse_modification(["Buy", "groceries", "today"])
        
        assert modification.title == "Buy groceries today"
    
    def test_parse_modification_empty(self):
        """Test parsing empty modification section."""
        modification = parse_modification([])
        
        assert isinstance(modification, Modification)
        assert modification.title == ""
    
    def test_parse_modification_preserves_spacing(self):
        """Test that spacing is preserved when joining words."""
        modification = parse_modification(["Complete", "the", "project"])
        
        assert modification.title == "Complete the project"


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

