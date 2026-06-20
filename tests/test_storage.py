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


def test_sqlite_reads_after_external_backend_switch(tmp_path: Path) -> None:
    """Simulate Web UI switching backend while MCP keeps a stale config cache."""
    import json

    from rememb.helpers import _store_context
    from rememb.storage import migrate_json_to_sqlite
    from rememb.utils import _config_path, _entries_path

    root = tmp_path / "project"
    root.mkdir()
    init(root)
    write_entry(root, "project", "survives migration")

    _store_context.get_config(root)

    config = json.loads(_config_path(root).read_text(encoding="utf-8"))
    config["storage_backend"] = "sqlite"
    _config_path(root).write_text(json.dumps(config, indent=2), encoding="utf-8")
    migrate_json_to_sqlite(root)

    assert not _entries_path(root).exists()
    entries = read_entries(root)
    assert len(entries) == 1
    assert entries[0]["content"] == "survives migration"
    assert _store_context.get_config(root)["storage_backend"] == "sqlite"


def test_json_backend_remains_default(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    init(root)

    write_entry(root, "context", "json default")
    entries = read_entries(root)

    assert len(entries) == 1
    assert (root / ".rememb" / "entries.json").exists()
