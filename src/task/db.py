"""Database and configuration operations"""
import os
import json
from .models import Config

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
