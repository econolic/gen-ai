import pytest

from app.config import get_settings
from mcp_servers.excel_server.server import _sandbox_path


def test_excel_mcp_allows_data_dir_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    inside = tmp_path / "uploads" / "file.xlsx"
    inside.parent.mkdir()
    inside.touch()

    assert _sandbox_path(str(inside)) == str(inside.resolve())


def test_excel_mcp_rejects_outside_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    with pytest.raises(ValueError):
        _sandbox_path(str(tmp_path / "outside.xlsx"))
