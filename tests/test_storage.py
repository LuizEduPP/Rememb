from __future__ import annotations

import json
import multiprocessing
import queue
from pathlib import Path

import pytest

from rememb.config import DEFAULT_STORAGE_BACKEND, STORAGE_BACKEND_SQLITE
from rememb.helpers import _store_context
from rememb.storage import migrate_json_to_sqlite, normalize_storage_backend
from rememb.storage.locking import file_lock as _file_lock
from rememb.store import init, read_entries, update_config, write_entry
from rememb.utils import _config_path, _entries_path


def _hold_file_lock(path_str: str, mode: str, entered_conn, release_conn) -> None:
    with _file_lock(Path(path_str), mode=mode):
        entered_conn.send("entered")
        release_conn.recv()
    entered_conn.close()
    release_conn.close()


def test_normalize_storage_backend_defaults_and_rejects():
    assert normalize_storage_backend(None) == DEFAULT_STORAGE_BACKEND
    assert normalize_storage_backend(STORAGE_BACKEND_SQLITE) == STORAGE_BACKEND_SQLITE
    with pytest.raises(ValueError, match="Unsupported storage_backend"):
        normalize_storage_backend("redis")


def test_sqlite_roundtrip_and_json_migration(store: Path):
    write_entry(store, "actions", "legacy json entry")
    update_config(store, {"storage_backend": STORAGE_BACKEND_SQLITE})

    entries = read_entries(store)
    assert [entry["content"] for entry in entries] == ["legacy json entry"]
    assert (store / ".rememb" / "entries.db").exists()
    assert (store / ".rememb" / "entries.json.migrated").exists()

    write_entry(store, "project", "SQLite-backed memory entry", tags=["storage"])
    assert len(read_entries(store)) == 2


def test_sqlite_reads_after_external_backend_switch(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    write_entry(root, "project", "survives migration")
    _store_context.get_config(root)

    config = json.loads(_config_path(root).read_text(encoding="utf-8"))
    config["storage_backend"] = STORAGE_BACKEND_SQLITE
    _config_path(root).write_text(json.dumps(config, indent=2), encoding="utf-8")
    migrate_json_to_sqlite(root)

    assert not _entries_path(root).exists()
    assert [entry["content"] for entry in read_entries(root)] == ["survives migration"]
    assert _store_context.get_config(root)["storage_backend"] == STORAGE_BACKEND_SQLITE


def test_file_lock_uses_exclusive_lock_for_r_plus_mode(tmp_path: Path):
    entries_path = tmp_path / "entries.json"
    entries_path.write_text("[]", encoding="utf-8")

    ctx = multiprocessing.get_context("spawn")
    first_entered_parent, first_entered_child = ctx.Pipe(duplex=False)
    second_entered_parent, second_entered_child = ctx.Pipe(duplex=False)
    first_release_child, first_release_parent = ctx.Pipe(duplex=False)
    second_release_child, second_release_parent = ctx.Pipe(duplex=False)

    first = ctx.Process(target=_hold_file_lock, args=(str(entries_path), "r+", first_entered_child, first_release_child))
    second = ctx.Process(target=_hold_file_lock, args=(str(entries_path), "r+", second_entered_child, second_release_child))

    first.start()
    assert first_entered_parent.recv() == "entered"
    second.start()

    with pytest.raises(queue.Empty):
        if second_entered_parent.poll(0.3):
            raise AssertionError("second writer acquired r+ lock before first released it")
        raise queue.Empty()

    first_release_parent.send("release")
    first.join(timeout=5)
    assert first.exitcode == 0
    assert second_entered_parent.recv() == "entered"
    second_release_parent.send("release")
    second.join(timeout=5)
    assert second.exitcode == 0


def test_file_lock_read_mode_does_not_create_missing_file(tmp_path: Path):
    missing_path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        with _file_lock(missing_path, mode="r"):
            pass
    assert not missing_path.exists()
