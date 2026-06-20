"""Entry storage backends for rememb."""

from __future__ import annotations

from pathlib import Path

from rememb.storage.base import EntryStorageBackend
from rememb.storage.json_backend import JsonEntryStorage
from rememb.storage.sqlite_backend import SqliteEntryStorage

_BACKENDS: dict[str, EntryStorageBackend] = {
    "json": JsonEntryStorage(),
    "sqlite": SqliteEntryStorage(),
}

_DEFAULT_BACKEND = "json"


def normalize_storage_backend(value: object) -> str:
    backend = str(value or _DEFAULT_BACKEND).strip().lower()
    if backend not in _BACKENDS:
        raise ValueError(f"Unsupported storage_backend '{value}'. Use 'json' or 'sqlite'.")
    return backend


def _effective_storage_backend(root: Path, configured: str) -> str:
    """Resolve the backend whose store file is actually present on disk."""
    from rememb.utils import _entries_db_path, _entries_path

    configured = normalize_storage_backend(configured)
    if configured == "sqlite":
        return "sqlite"

    if _entries_path(root).exists():
        return "json"
    if _entries_db_path(root).exists():
        return "sqlite"
    return "json"


def get_storage_backend(root: Path | None = None, *, backend: str | None = None) -> EntryStorageBackend:
    """Resolve the configured storage backend for a rememb root."""
    if backend is not None:
        return _BACKENDS[normalize_storage_backend(backend)]

    if root is None:
        return _BACKENDS[_DEFAULT_BACKEND]

    from rememb.helpers import _store_context

    config = _store_context.get_config(root)
    configured = normalize_storage_backend(config.get("storage_backend", _DEFAULT_BACKEND))
    selected = _effective_storage_backend(root, configured)
    return _BACKENDS[selected]


def migrate_json_to_sqlite(root: Path) -> int:
    """Migrate legacy JSON entries into SQLite storage."""
    return SqliteEntryStorage.migrate_from_json(root)


__all__ = [
    "EntryStorageBackend",
    "JsonEntryStorage",
    "SqliteEntryStorage",
    "get_storage_backend",
    "migrate_json_to_sqlite",
    "normalize_storage_backend",
]
