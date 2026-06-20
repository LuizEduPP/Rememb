from __future__ import annotations

from pathlib import Path

import pytest

from rememb.store import init, read_entries, update_config, write_entry


def test_sqlite_backend_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    init(root)
    update_config(root, {"storage_backend": "sqlite"})

    write_entry(root, "project", "SQLite-backed memory entry", tags=["storage"])
    entries = read_entries(root)

    assert len(entries) == 1
    assert entries[0]["content"] == "SQLite-backed memory entry"
    assert (root / ".rememb" / "entries.db").exists()
    assert not (root / ".rememb" / "entries.json").exists()


def test_sqlite_migrates_existing_json_store(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    init(root)
    write_entry(root, "actions", "legacy json entry")

    update_config(root, {"storage_backend": "sqlite"})
    entries = read_entries(root)

    assert len(entries) == 1
    assert entries[0]["content"] == "legacy json entry"
    assert (root / ".rememb" / "entries.json.migrated").exists()


def test_json_backend_remains_default(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    init(root)

    write_entry(root, "context", "json default")
    entries = read_entries(root)

    assert len(entries) == 1
    assert (root / ".rememb" / "entries.json").exists()
