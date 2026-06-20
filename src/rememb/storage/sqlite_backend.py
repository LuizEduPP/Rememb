"""SQLite storage backend for larger entry volumes."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from rememb.exceptions import RemembStorageError
from rememb.utils import _entries_path, _rememb_path

logger = logging.getLogger(__name__)

_ModifierResult = TypeVar("_ModifierResult")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    section TEXT NOT NULL,
    content TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_section ON entries(section);
CREATE INDEX IF NOT EXISTS idx_entries_updated_at ON entries(updated_at);
CREATE INDEX IF NOT EXISTS idx_entries_deleted_at ON entries(deleted_at);
"""


class SqliteEntryStorage:
    """Store entries in `.rememb/entries.db` with JSON payloads per row."""

    _connections: dict[str, sqlite3.Connection] = {}
    _lock = threading.Lock()

    def _db_path(self, root: Path) -> Path:
        return _rememb_path(root) / "entries.db"

    def _connect(self, root: Path) -> sqlite3.Connection:
        key = str(root.resolve())
        with self._lock:
            conn = self._connections.get(key)
            if conn is None:
                db_path = self._db_path(root)
                db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(db_path), check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.executescript(_SCHEMA)
                conn.commit()
                self._connections[key] = conn
            return conn

    def is_initialized(self, root: Path) -> bool:
        return self._db_path(root).exists()

    def ensure_initialized(self, root: Path) -> None:
        self._connect(root)

    def _row_to_entry(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"])
        if not isinstance(payload, dict):
            raise RemembStorageError("Invalid SQLite entry payload.")
        return payload

    def load_entries(self, root: Path) -> list[dict[str, Any]]:
        conn = self._connect(root)
        with self._lock:
            rows = conn.execute(
                "SELECT payload FROM entries ORDER BY updated_at ASC, created_at ASC, id ASC"
            ).fetchall()
        entries = [self._row_to_entry(row) for row in rows]
        logger.debug("Loaded %s entries from %s", len(entries), self._db_path(root))
        return entries

    def save_entries(self, root: Path, entries: list[dict[str, Any]]) -> None:
        conn = self._connect(root)
        with self._lock:
            conn.execute("DELETE FROM entries")
            for entry in entries:
                self._upsert_entry(conn, entry)
            conn.commit()
        logger.debug("Saved %s entries to %s", len(entries), self._db_path(root))

    @staticmethod
    def _upsert_entry(conn: sqlite3.Connection, entry: dict[str, Any]) -> None:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            raise RemembStorageError("Each entry must include an id for SQLite storage.")
        conn.execute(
            """
            INSERT INTO entries (id, section, content, payload, created_at, updated_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                section=excluded.section,
                content=excluded.content,
                payload=excluded.payload,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                deleted_at=excluded.deleted_at
            """,
            (
                entry_id,
                str(entry.get("section") or "context"),
                str(entry.get("content") or ""),
                json.dumps(entry, ensure_ascii=False),
                str(entry.get("created_at") or ""),
                str(entry.get("updated_at") or ""),
                str(entry.get("deleted_at") or "") or None,
            ),
        )

    def atomic_modify(
        self,
        root: Path,
        modifier: Callable[[list[dict[str, Any]]], _ModifierResult],
    ) -> _ModifierResult:
        conn = self._connect(root)
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute(
                    "SELECT payload FROM entries ORDER BY updated_at ASC, created_at ASC, id ASC"
                ).fetchall()
                entries = [self._row_to_entry(row) for row in rows]
                result = modifier(entries)
                conn.execute("DELETE FROM entries")
                for entry in entries:
                    self._upsert_entry(conn, entry)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def migrate_from_json(root: Path) -> int:
        """Import legacy `entries.json` into SQLite when switching backends."""
        json_path = _entries_path(root)
        if not json_path.exists():
            return 0
        try:
            raw_entries = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RemembStorageError(f"Cannot migrate corrupted JSON store: {exc}") from exc
        if not isinstance(raw_entries, list):
            raise RemembStorageError("Cannot migrate JSON store: expected a list of entries.")

        storage = SqliteEntryStorage()
        storage.save_entries(root, raw_entries)
        backup_path = json_path.with_suffix(".json.migrated")
        if not backup_path.exists():
            json_path.replace(backup_path)
        return len(raw_entries)
