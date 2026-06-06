import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def offline_demo_seed(monkeypatch):
    monkeypatch.setenv("OFFLINE_DEMO_SEED_FIRST", "true")
    from app.config import get_settings

    get_settings.cache_clear()
