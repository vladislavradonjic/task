from datetime import time

from task.config import Config, load_config


def test_load_config_returns_defaults_when_absent(tmp_data_dir):
    cfg = load_config(tmp_data_dir)
    assert cfg.list.sort == "urgency,-entry"
    assert cfg.recap.output_dir is None


def test_load_config_reads_list_sort(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text('[list]\nsort = "entry"\n')
    cfg = load_config(tmp_data_dir)
    assert cfg.list.sort == "entry"


def test_load_config_reads_recap(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text('[recap]\noutput_dir = "~/recaps"\n')
    cfg = load_config(tmp_data_dir)
    assert cfg.recap.output_dir == "~/recaps"


def test_load_config_ignores_unknown_keys(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text('[list]\nsort = "entry"\nunknown_key = "ignored"\n')
    cfg = load_config(tmp_data_dir)
    assert cfg.list.sort == "entry"


def test_load_config_ignores_unknown_sections(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text("[future_section]\nsome_key = 42\n")
    cfg = load_config(tmp_data_dir)
    assert isinstance(cfg, Config)


def test_load_config_partial_overrides_keep_other_defaults(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text('[list]\nsort = "entry"\n')
    cfg = load_config(tmp_data_dir)
    assert cfg.recap.output_dir is None


# ---------------------------------------------------------------------------
# [timesheet] (docs/timesheet.md)
# ---------------------------------------------------------------------------

def test_timesheet_defaults(tmp_data_dir):
    cfg = load_config(tmp_data_dir)
    assert cfg.timesheet.kinds == ["solo", "chat", "meeting", "call", "junk"]
    assert cfg.timesheet.day_starts_at == time(4, 0)
    assert cfg.timesheet.shortcuts == {}


def test_timesheet_reads_kinds_and_boundary(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text(
        '[timesheet]\nkinds = ["solo", "admin"]\nday_starts_at = "05:30"\n', encoding="utf-8")
    cfg = load_config(tmp_data_dir)
    assert cfg.timesheet.kinds == ["solo", "admin"]
    assert cfg.timesheet.day_starts_at == time(5, 30)


def test_timesheet_reads_shortcuts(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text(
        '[timesheet.shortcuts]\n'
        'standup = { description = "team standup", kind = "meeting", project = "internal" }\n',
        encoding="utf-8")
    shortcut = load_config(tmp_data_dir).timesheet.shortcuts["standup"]
    assert (shortcut.description, shortcut.kind, shortcut.project) == (
        "team standup", "meeting", "internal")


def test_unknown_shortcut_keys_are_ignored(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text(
        '[timesheet.shortcuts]\nx = { kind = "solo", nonsense = "ignored" }\n', encoding="utf-8")
    assert load_config(tmp_data_dir).timesheet.shortcuts["x"].kind == "solo"


def test_unknown_timesheet_keys_are_ignored(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text(
        '[timesheet]\nkinds = ["solo"]\nnonsense = 1\n', encoding="utf-8")
    assert load_config(tmp_data_dir).timesheet.kinds == ["solo"]
