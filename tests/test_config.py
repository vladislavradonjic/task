from task.config import Config, load_config


def test_load_config_returns_defaults_when_absent(tmp_data_dir):
    cfg = load_config(tmp_data_dir)
    assert cfg.list.sort == "urgency,-entry"
    assert cfg.time_tracking.stale_threshold_hours == 8
    assert cfg.recap.output_dir is None


def test_load_config_reads_list_sort(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text('[list]\nsort = "entry"\n')
    cfg = load_config(tmp_data_dir)
    assert cfg.list.sort == "entry"


def test_load_config_reads_time_tracking(tmp_data_dir):
    (tmp_data_dir / "config.toml").write_text("[time_tracking]\nstale_threshold_hours = 12\n")
    cfg = load_config(tmp_data_dir)
    assert cfg.time_tracking.stale_threshold_hours == 12


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
    assert cfg.time_tracking.stale_threshold_hours == 8
    assert cfg.recap.output_dir is None
