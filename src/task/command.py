"Command implementations"
from pathlib import Path
from .models import Config, Task
from . import db
from .parse import parse_modification

def init(filter_section: list[str], modification_section: list[str]):
    """Initialize database"""
    # Read existing config or create default
    config = db.read_config()
    db.init_db(config.db_path)

    # add current context to config if not already present
    if config.current_context not in config.contexts:
        config.contexts[config.current_context] = config.db_path
        db.write_config(config)

    return f"Database initialized at {config.db_path}"

def add(filter_section: list[str], modification_section: list[str]):
    """Add a new task"""
    modification = parse_modification(modification_section)
    tasks = db.read_db()
    next_id = db.get_next_id(tasks)
    task = Task(id=next_id, title=modification.title)
    tasks = db.add_task(tasks, task)
    db.write_db(tasks)

    return f"Add task with id {next_id}"

def show(filter_section: list[str], modification_section: list[str]):
    """Show the tasks"""
    pass

def modify(filter_section: list[str], modification_section: list[str]):
    """Modify a task"""
    pass

def done(filter_section: list[str], modification_section: list[str]):
    """Mark a task as done"""
    pass
