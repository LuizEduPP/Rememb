from __future__ import annotations

import json
import multiprocessing
import queue
from pathlib import Path

import pytest

from rememb.helpers import _file_lock
from rememb.config import DEFAULT_SECTIONS
from rememb.exceptions import RemembNotInitializedError, RemembValidationError
from rememb.store import (
    clear_entries,
    diff_entry_versions,
    delete_entries,
    edit_entries,
    format_entries,
    get_stats,
    init,
    list_entry_versions,
    read_entries,
    read_entries_page,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    update_config,
    write_entries,
    write_entry,
)


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
    assert entry["version"] == 1
    assert entry["history"] == []
    assert entries == [entry]
    assert stats["total"] == 1
    assert stats["by_section"]["project"] == 1


def test_write_entries_creates_multiple_entries_atomically(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    entries = write_entries(
        root,
        [
            {"section": "project", "content": "First batch memory.", "tags": ["one"]},
            {"section": "actions", "content": "Second batch memory.", "tags": ["two"]},
        ],
    )

    stored = read_entries(root)

    assert len(entries) == 2
    assert [entry["content"] for entry in stored] == ["First batch memory.", "Second batch memory."]
    assert {entry["section"] for entry in entries} == {"project", "actions"}


def test_edit_entries_updates_multiple_entries_in_order(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    first = write_entry(root, "project", "Original first.", ["a"])
    second = write_entry(root, "project", "Original second.", ["b"])

    results = edit_entries(
        root,
        [
            {"entry_id": first["id"], "content": "Updated first.", "tags": ["x"]},
            {"entry_id": second["id"], "section": "actions"},
            {"entry_id": "deadbeef", "content": "Missing"},
        ],
    )

    stored = read_entries(root)
    by_id = {entry["id"]: entry for entry in stored}

    assert results[0]["content"] == "Updated first."
    assert results[1]["section"] == "actions"
    assert results[2] is None
    assert by_id[first["id"]]["tags"] == ["x"]
    assert by_id[second["id"]]["section"] == "actions"
    assert by_id[first["id"]]["version"] == 2
    assert by_id[first["id"]]["history"][0]["version"] == 1
    assert by_id[first["id"]]["history"][0]["content"] == "Original first."
    assert by_id[second["id"]]["version"] == 2
    assert by_id[second["id"]]["history"][0]["section"] == "project"


def test_edit_entry_upgrades_legacy_entry_to_versioned_history(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    entry = write_entry(root, "project", "Legacy memory.", ["old"])
    entries_path = root / ".rememb" / "entries.json"
    stored_entries = json.loads(entries_path.read_text(encoding="utf-8"))
    stored_entries[0].pop("version", None)
    stored_entries[0].pop("history", None)
    entries_path.write_text(json.dumps(stored_entries, indent=2), encoding="utf-8")

    updated = edit_entries(root, [{"entry_id": entry["id"], "content": "Legacy memory updated."}])[0]

    assert updated is not None
    assert updated["version"] == 2
    assert len(updated["history"]) == 1
    assert updated["history"][0]["version"] == 1
    assert updated["history"][0]["content"] == "Legacy memory."


def test_delete_entries_removes_only_found_ids(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    first = write_entry(root, "project", "Delete first.")
    second = write_entry(root, "project", "Delete second.")

    deleted_ids = delete_entries(root, [first["id"], "deadbeef"])
    remaining = read_entries(root)
    all_entries = read_entries(root, include_deleted=True)
    deleted_entry = next(entry for entry in all_entries if entry["id"] == first["id"])

    assert deleted_ids == [first["id"]]
    assert [entry["id"] for entry in remaining] == [second["id"]]
    assert deleted_entry["deleted_at"]
    assert deleted_entry["version"] == 2
    assert deleted_entry["history"][0]["version"] == 1


def test_read_page_and_search_hide_deleted_by_default(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    deleted = write_entry(root, "project", "Deleted alpha memory", ["alpha"])
    live = write_entry(root, "project", "Live alpha memory", ["alpha"])
    delete_entries(root, [deleted["id"]])

    class AlphaModel:
        def encode(self, texts, show_progress_bar=False, batch_size=32):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("rememb.store._store_context.get_model", lambda _root=None: AlphaModel())
    monkeypatch.setattr("rememb.store._store_context.schedule_model_release", lambda _root=None: None)

    page = read_entries_page(root)
    hidden_results = search_entries(root, "alpha")
    visible_results = search_entries(root, "alpha", include_deleted=True)

    assert [entry["id"] for entry in page["items"]] == [live["id"]]
    assert [entry["id"] for entry in hidden_results] == [live["id"]]
    assert {entry["id"] for entry in visible_results} == {deleted["id"], live["id"]}


def test_versions_restore_and_diff_cover_deleted_entries(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    entry = write_entry(root, "project", "first line\nsecond line", ["draft"])
    updated = edit_entries(root, [{"entry_id": entry["id"], "content": "first line\nthird line", "tags": ["released"]}])[0]
    deleted_ids = delete_entries(root, [entry["id"]])

    versions = list_entry_versions(root, entry["id"])
    diff = diff_entry_versions(root, entry["id"], 1, 2)
    restored_deleted = restore_deleted_entry(root, entry["id"])
    restored_version = restore_entry_version(root, entry["id"], 1)
    final_versions = list_entry_versions(root, entry["id"])

    assert deleted_ids == [entry["id"]]
    assert updated is not None
    assert [revision["version"] for revision in versions] == [1, 2, 3]
    assert versions[-1]["deleted_at"]
    assert diff is not None
    assert "--- " in diff["diff"]
    assert "+second line" in diff["diff"] or "-second line" in diff["diff"]
    assert restored_deleted is not None
    assert restored_deleted["version"] == 4
    assert "deleted_at" not in restored_deleted
    assert restored_version is not None
    assert restored_version["version"] == 5
    assert restored_version["content"] == "first line\nsecond line"
    assert [revision["version"] for revision in final_versions] == [1, 2, 3, 4, 5]
    assert final_versions[2]["deleted_at"]
    assert not final_versions[-1].get("deleted_at")


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
    stored = read_entries(root)
    stored_by_id = {entry["id"]: entry for entry in stored}

    assert results[0]["score"] >= results[1]["score"]
    assert "score" in results[0]
    assert all(stored_by_id[result["id"]]["access_count"] == 1 for result in results)
    assert all(stored_by_id[result["id"]]["last_accessed"] for result in results)


def test_search_entries_boosts_exact_tokens_and_tags(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    write_entry(root, "project", "Completely generic note.", ["release"])
    write_entry(root, "project", "Roadmap and timeline details.", ["alpha", "launch"])

    class FlatModel:
        def encode(self, texts, show_progress_bar=False, batch_size=32):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("rememb.store._store_context.get_model", lambda _root=None: FlatModel())
    monkeypatch.setattr("rememb.store._store_context.schedule_model_release", lambda _root=None: None)

    results = search_entries(root, "alpha launch")

    assert results[0]["tags"] == ["alpha", "launch"]
    assert results[0]["score"] > results[1]["score"]


def test_get_stats_excludes_deleted_from_totals(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    first = write_entry(root, "project", "Keep me hidden after delete.")
    write_entry(root, "actions", "Still active.")
    delete_entries(root, [first["id"]])

    stats = get_stats(root)

    assert stats["total"] == 1
    assert stats["deleted_total"] == 1
    assert stats["by_section"]["project"] == 0
    assert stats["by_section"]["actions"] == 1


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