"Command implementations"
from pathlib import Path
from .models import Config, Task
from . import db
from .parse import parse_modification, parse_filter

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
    if not modification_section or len(modification_section) == 0:
        return "Modification section is empty; Task not created."
    modification = parse_modification(modification_section)
    tasks = db.read_db()
    next_id = db.get_next_id(tasks)
    # ignore tags starting with "-", as there is nothing to remove
    tags = []
    if modification.tags:
        tags = [tag.lstrip("+") for tag in modification.tags if tag.startswith("+")]
    
    task = Task(
        id=next_id, 
        title=modification.title,
        project=modification.project,
        priority=modification.priority,
        tags=tags,
        due=modification.due,
        scheduled=modification.scheduled,
        # TODO: add depends and blocks
    )
    tasks = db.add_task(tasks, task)
    db.write_db(tasks)

    return f"Added task with id {next_id}"

def show(filter_section: list[str], modification_section: list[str]):
    """Show the tasks"""
    filter_obj = parse_filter(filter_section)
    tasks = db.read_db()
    filtered_tasks = db.filter_tasks(tasks, filter_obj)

    if filtered_tasks is None or filtered_tasks.height == 0:
        return "No tasks found"

    # TODO: format using rich
    return filtered_tasks

def modify(filter_section: list[str], modification_section: list[str]):
    """Modify a task"""
    pass

def done(filter_section: list[str], modification_section: list[str]):
    """Mark a task as done"""
    pass
