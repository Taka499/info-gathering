from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Item

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    url TEXT,
    category TEXT,
    first_seen_utc TEXT,
    posted_utc TEXT
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    """SQLite-backed seen-items store.

    Items are recorded at filter time, not post time, so a crash between
    fetch and post errs on the side of never re-posting.
    """

    def __init__(self, db_path: str = "state/seen.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def filter_new(self, items: list[Item]) -> list[Item]:
        new: list[Item] = []
        now = _now()
        for item in items:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO items"
                " (id, source, title, url, category, first_seen_utc)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (item.id, item.source, item.title, item.url, item.category, now),
            )
            if cur.rowcount:
                new.append(item)
        self._conn.commit()
        return new

    def mark_posted(self, items: list[Item]) -> None:
        now = _now()
        self._conn.executemany(
            "UPDATE items SET posted_utc = ? WHERE id = ?",
            [(now, item.id) for item in items],
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
