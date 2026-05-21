from __future__ import annotations

import json
import multiprocessing
import queue
from pathlib import Path

import pytest

from rememb.helpers import _file_lock
from rememb.config import DEFAULT_SECTIONS
from rememb.exceptions import RemembNotInitializedError, RemembValidationError
from rememb.store import clear_entries, format_entries, get_stats, init, read_entries, search_entries, update_config, write_entry


def _hold_file_lock(path_str: str, mode: str, entered_conn, release_conn) -> None:
    with _file_lock(Path(path_str), mode=mode):
        entered_conn.send("entered")
        release_conn.recv()
    entered_conn.close()
    release_conn.close()


def test_init_creates_expected_files_and_gitignore(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    rememb_path = init(root, project_name="demo-project")

    assert rememb_path == root / ".rememb"
    assert (rememb_path / "entries.json").exists()
    assert (rememb_path / "config.json").exists()
    assert (rememb_path / "meta.json").exists()

    meta = json.loads((rememb_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["project"] == "demo-project"
    assert meta["sections"] == DEFAULT_SECTIONS

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".rememb/embeddings.npy" in gitignore
    assert ".rememb/embeddings.hash" in gitignore


def test_write_entry_roundtrip_and_stats(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    entry = write_entry(root, "project", "Use pytest for runtime validation.", ["testing", "runtime"])
    entries = read_entries(root, "project")
    stats = get_stats(root)

    assert entry["id"]
    assert len(entry["id"]) == 8
    assert entries == [entry]
    assert stats["total"] == 1
    assert stats["by_section"]["project"] == 1


def test_update_config_migrates_entries_from_removed_section(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    write_entry(root, "project", "Keep this memory during section migration.")

    updated = update_config(root, {"sections": ["actions", "systems", "requests", "user", "context"]})
    entries = read_entries(root)
    meta = json.loads((root / ".rememb" / "meta.json").read_text(encoding="utf-8"))

    assert "project" not in updated["sections"]
    assert "uncategorized" in updated["sections"]
    assert entries[0]["section"] == "uncategorized"
    assert meta["sections"] == updated["sections"]


def test_clear_entries_requires_explicit_confirmation(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    write_entry(root, "project", "Memory that should be cleared only with confirmation.")

    with pytest.raises(RemembValidationError, match="confirm=True"):
        clear_entries(root)

    cleared = clear_entries(root, confirm=True)

    assert cleared == 1
    assert read_entries(root) == []


def test_file_lock_uses_exclusive_lock_for_r_plus_mode(tmp_path):
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

    first_entered_parent.close()
    first_release_parent.close()
    second_entered_parent.close()
    second_release_parent.close()


def test_file_lock_read_mode_does_not_create_missing_file(tmp_path):
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        with _file_lock(missing_path, mode="r"):
            pass

    assert not missing_path.exists()


def test_search_and_stats_require_initialization(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(RemembNotInitializedError):
        search_entries(root, "query")

    with pytest.raises(RemembNotInitializedError):
        get_stats(root)

    assert not (root / ".rememb").exists()


def test_search_entries_returns_scores(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    write_entry(root, "project", "alpha match")
    write_entry(root, "project", "beta mismatch")

    class FakeModel:
        def encode(self, texts, show_progress_bar=False, batch_size=32):
            vectors = []
            for text in texts:
                lowered = text.lower()
                vectors.append([1.0, 0.0] if "alpha" in lowered else [0.0, 1.0])
            return vectors

    monkeypatch.setattr("rememb.store._store_context.get_model", lambda _root=None: FakeModel())
    monkeypatch.setattr("rememb.store._store_context.schedule_model_release", lambda _root=None: None)

    results = search_entries(root, "alpha")

    assert results[0]["score"] >= results[1]["score"]
    assert "score" in results[0]


def test_format_entries_supports_summary_and_truncation():
    entries = [
        {
            "id": "abcd1234",
            "section": "project",
            "content": "a" * 20,
            "tags": ["tag1"],
            "score": 0.98765,
        }
    ]

    text = format_entries(entries, include_id=True, include_score=True, max_chars=8, summary_only=True)

    assert "abcd1234" in text
    assert "score: 0.988" in text
    assert "aaaaa..." in text