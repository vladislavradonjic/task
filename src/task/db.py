"""Database and configuration operations"""
import os
import json
from datetime import date
import polars as pl
from .models import Config, Task, Filter

CONFIG_FILE = "config.json"
ENCODING = "utf-8"

def get_config_path() -> str:
    """Get the path to the configuration file"""
    # Windows
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata is None:
            appdata = os.path.expanduser("~")
        config_dir = os.path.join(appdata, "task")
        return os.path.join(config_dir, CONFIG_FILE)

    # Unix-like
    home = os.path.expanduser("~")
    config_dir = os.path.join(home, ".task")
    return os.path.join(config_dir, CONFIG_FILE)

def expand_path(path: str) -> str:
    """Expand ~ and environment variables in path"""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))

def write_config(config: Config | None = None) -> None:
    """Write the configuration to the file"""
    config_path = expand_path(get_config_path())
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)

    if config is None:
        config = Config(db_path=os.path.join(config_dir, "db", "default.json"))

    data = config.model_dump()

    with open(config_path, "w", encoding=ENCODING) as file:
        json.dump(data, file, indent=2, default=str)

def read_config() -> Config:
    """Read the configuration from the file"""
    config_path = expand_path(get_config_path())
    if not os.path.exists(config_path):
        # create default config if none exists
        print(f"Configuration file not found at {config_path}. Creating default config.")
        write_config(None)
        # Read the config we just created
        config_path = expand_path(get_config_path())

    with open(config_path, "r", encoding=ENCODING) as file:
        data = json.load(file)

    return Config(**data)

def init_db(db_path: str) -> None:
    """Initialize the database"""
    if os.path.exists(db_path):
        force = input(f"Database already exists at {db_path}. Overwrite? (y/n): ")
        if force.lower() != "y":
            print("Database initialization cancelled.")
            return

    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)

    with open(db_path, "w", encoding=ENCODING) as file:
        json.dump([], file, indent=2, default=str)

def write_db(tasks: pl.DataFrame) -> None:
    """Write the tasks to the database"""
    config = read_config()
    tasks_dict = tasks.to_dicts()

    if not os.path.exists(config.db_path):
        init_db(config.db_path)

    with open(config.db_path, "w", encoding=ENCODING) as file:
        json.dump(tasks_dict, file, indent=2, default=str)

def read_db() -> pl.DataFrame | None:
    """Read the tasks from the database"""
    config = read_config()

    if not os.path.exists(config.db_path):
        return None

    return pl.read_json(config.db_path)

def get_next_id(tasks: pl.DataFrame | None) -> int:
    """Get the next available ID"""
    if tasks is None or tasks.height == 0:
        return 1

    max_id = tasks["id"].max()

    if max_id is None:
        return 1

    return int(max_id) + 1

def add_task(tasks: pl.DataFrame, task: Task) -> pl.DataFrame:
    """Add a task to the database"""
    # Use mode='json' to ensure UUIDs are serialized as strings
    # This matches how they're stored when reading from JSON
    task_dict = task.model_dump(mode='json')
    
    if tasks is None:
        return pl.DataFrame([task_dict])

    return tasks.vstack(pl.DataFrame([task_dict])).sort("id", nulls_last=True)

def filter_tasks(tasks: pl.DataFrame, filter_obj: Filter) -> pl.DataFrame:
    """Filter the tasks based on the filter"""
    if tasks is None or tasks.height == 0:
        return pl.DataFrame()

    filtered = tasks

    for field, value in filter_obj:
        if not value:
            continue

        if field == "ids":
            filtered = filtered.filter(pl.col("id").is_in(value))
        elif field == "title":
            filtered = filtered.filter(
                pl.col("title").str.to_lowercase().str.contains(value.lower(), literal=False)
            )
        elif field in ["project", "priority", "due", "scheduled"]:
            filtered = filtered.filter(pl.col(field) == value)
        elif field == "tags":
            for tag in value:
                if tag.startswith("+"):
                    filtered = filtered.filter(pl.col("tags").str.contains(tag.lstrip("+")))
                elif tag.startswith("-"):
                    filtered = filtered.filter(~pl.col("tags").str.contains(tag.lstrip("-")))
    
    return filtered

