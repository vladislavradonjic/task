from datetime import time
from pathlib import Path

from pydantic import BaseModel

from task.timesheet import DEFAULT_DAY_STARTS_AT


class ListConfig(BaseModel):
    sort: str = "urgency,-entry"


class RecapConfig(BaseModel):
    output_dir: str | None = None
    template_dir: str | None = None


class Shortcut(BaseModel):
    """Field defaults for a recurring timesheet row. Explicit arguments always win."""
    description: str | None = None
    kind: str | None = None
    project: str | None = None


class TimesheetConfig(BaseModel):
    # `kind` is meant to be exhaustive, so the vocabulary is closed and typos are refused.
    kinds: list[str] = ["solo", "chat", "meeting", "call", "junk"]
    # A logical day runs from here to here, so work past midnight stays with its evening.
    day_starts_at: time = DEFAULT_DAY_STARTS_AT
    shortcuts: dict[str, Shortcut] = {}


class ProjectsConfig(BaseModel):
    # How far back `tsk projects` looks, and the pool the REPL suggests projects from.
    window: str = "3m"


class SuggestConfig(BaseModel):
    """REPL ghost-text completion for `project:` and `kind:` — see docs/projects.md."""
    # Below this similarity the REPL offers nothing rather than guessing.
    threshold: float = 0.6
    # False gives back a plain input line with no ghost text.
    enabled: bool = True


class Config(BaseModel):
    list: ListConfig = ListConfig()
    recap: RecapConfig = RecapConfig()
    timesheet: TimesheetConfig = TimesheetConfig()
    projects: ProjectsConfig = ProjectsConfig()
    suggest: SuggestConfig = SuggestConfig()


_LIST_KEYS = {"sort"}
_RECAP_KEYS = {"output_dir", "template_dir"}
_TIMESHEET_KEYS = {"kinds", "day_starts_at", "shortcuts"}
_SHORTCUT_KEYS = {"description", "kind", "project"}
_PROJECTS_KEYS = {"window"}
_SUGGEST_KEYS = {"threshold", "enabled"}


def load_config(data_dir: Path) -> Config:
    import tomllib

    config_file = data_dir / "config.toml"
    if not config_file.exists():
        return Config()

    data = tomllib.loads(config_file.read_text(encoding="utf-8"))
    kwargs: dict = {}

    if "list" in data:
        kwargs["list"] = ListConfig(**{k: v for k, v in data["list"].items() if k in _LIST_KEYS})
    if "recap" in data:
        kwargs["recap"] = RecapConfig(**{k: v for k, v in data["recap"].items() if k in _RECAP_KEYS})
    if "timesheet" in data:
        section = {k: v for k, v in data["timesheet"].items() if k in _TIMESHEET_KEYS}
        if isinstance(section.get("shortcuts"), dict):
            section["shortcuts"] = {
                name: Shortcut(**{k: v for k, v in fields.items() if k in _SHORTCUT_KEYS})
                for name, fields in section["shortcuts"].items()
                if isinstance(fields, dict)
            }
        kwargs["timesheet"] = TimesheetConfig(**section)
    if "projects" in data:
        kwargs["projects"] = ProjectsConfig(
            **{k: v for k, v in data["projects"].items() if k in _PROJECTS_KEYS})
    if "suggest" in data:
        kwargs["suggest"] = SuggestConfig(
            **{k: v for k, v in data["suggest"].items() if k in _SUGGEST_KEYS})
    return Config(**kwargs)
