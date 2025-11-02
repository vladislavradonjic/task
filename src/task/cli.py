"Command line interface orchestration"
import sys
from . import command
from .parse import separate_sections

def get_commands() -> set[str]:
    """Get all available commands"""
    return {name for name in dir(command) if callable(getattr(command, name)) and not name.startswith("_")}

def main() -> None:
    """Main entry point"""
    commands = get_commands()
    arglist = sys.argv[1:]

    if not arglist:
        print("Usage task [filter] <command> [modification]")
        print("Commands: ", ", ".join(commands))
        return

    cmd_string, filter_section, modification_section = separate_sections(arglist, commands)

    if cmd_string is None:
        print("Unknown command. Available commands: ", ", ".join(commands))
        return

    func = getattr(command, cmd_string)
    if func is None:
        print("Unknown command. Available commands: ", ", ".join(commands))
        return

    func(filter_section, modification_section)



