"Command implementations"
from pathlib import Path
from .models import Config
from . import db

def init(filter_section: list[str], modification_section: list[str]):
    """Initialize database"""
    # Read existing config or create default
    config = db.read_config()
    db.init_db(config.db_path)

    # add current context to config if not already present
    if config.current_context not in config.contexts:
        config.contexts[config.current_context] = config.db_path
        db.write_config(config)


def add(filter_section: list[str], modification_section: list[str]):
    """Add a new task"""
    pass

def show(filter_section: list[str], modification_section: list[str]):
    """Show the tasks"""
    pass

def done(filter_section: list[str], modification_section: list[str]):
    """Mark a task as done"""
    pass
