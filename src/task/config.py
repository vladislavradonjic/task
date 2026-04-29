from pathlib import Path
from pydantic import BaseModel


class ListConfig(BaseModel):
    sort: str = "urgency,-entry"


class RecapConfig(BaseModel):
    output_dir: str | None = None
    template_dir: str | None = None


class TimeTrackingConfig(BaseModel):
    stale_threshold_hours: int = 8


class Config(BaseModel):
    list: ListConfig = ListConfig()
    recap: RecapConfig = RecapConfig()
    time_tracking: TimeTrackingConfig = TimeTrackingConfig()


_LIST_KEYS = {"sort"}
_RECAP_KEYS = {"output_dir", "template_dir"}
_TIME_TRACKING_KEYS = {"stale_threshold_hours"}


def load_config(data_dir: Path) -> Config:
    import tomllib

    config_file = data_dir / "config.toml"
    if not config_file.exists():
        return Config()

    data = tomllib.loads(config_file.read_text())
    kwargs: dict = {}

    if "list" in data:
        kwargs["list"] = ListConfig(**{k: v for k, v in data["list"].items() if k in _LIST_KEYS})
    if "recap" in data:
        kwargs["recap"] = RecapConfig(**{k: v for k, v in data["recap"].items() if k in _RECAP_KEYS})
    if "time_tracking" in data:
        kwargs["time_tracking"] = TimeTrackingConfig(
            **{k: v for k, v in data["time_tracking"].items() if k in _TIME_TRACKING_KEYS}
        )

    return Config(**kwargs)
