from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import get_settings


class SQLiteStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._initialized_paths: set[Path] = set()

    @property
    def path(self) -> Path:
        return get_settings().app_db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            should_init = not path.exists() or path not in self._initialized_paths
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            if should_init:
                self._init(connection)
                self._initialized_paths.add(path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fact_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()


sqlite_store = SQLiteStore()


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
