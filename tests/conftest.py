import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DATA_DIR", str(tmp_path))
    return tmp_path
