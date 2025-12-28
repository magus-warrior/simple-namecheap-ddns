"""SQLite-backed logging database for agent runs."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class UpdateRecord:
    target_id: str
    status: str
    message: str
    response_code: Optional[int]
    ip_address: Optional[str]


class LogDB:
    """Simple SQLite logger for DDNS updates."""

    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS update_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                response_code INTEGER,
                ip_address TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._connection.commit()

    def log_update(self, record: UpdateRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO update_history (target_id, status, message, response_code, ip_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.target_id,
                record.status,
                record.message,
                record.response_code,
                record.ip_address,
            ),
        )
        self._connection.commit()

    def get_cache(self, key: str) -> Optional[str]:
        row = self._connection.execute(
            "SELECT value FROM cache WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def set_cache(self, key: str, value: str) -> None:
        self._connection.execute(
            """
            INSERT INTO cache (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
