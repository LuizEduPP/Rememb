from __future__ import annotations

import json
from pathlib import Path

import pytest

from rememb.config import DEFAULT_SECTIONS, DEFAULT_STORAGE_BACKEND
from rememb.exceptions import RemembNotInitializedError, RemembValidationError
from rememb.store import (
    agent_summarize_hint,
    clear_entries,
    consolidate_entries,
    delete_entries,
    diff_entry_versions,
    edit_entries,
    edit_entry,
    export_entries,
    format_entries,
    get_config,
    get_entry,
    get_stats,
    init,
    list_entry_tags,
    list_entry_versions,
    read_entries,
    read_entries_page,
    read_recent_entries,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    update_config,
    write_entries,
    write_entry,
)


def test_init_creates_expected_files_and_gitignore(tmp_path: Path):
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
    assert ".rememb/entries.db" in (root / ".gitignore").read_text(encoding="utf-8")
    assert get_config(root)["storage_backend"] == DEFAULT_STORAGE_BACKEND


def test_write_read_edit_and_stats(store: Path):
    entry = write_entry(store, "project", "Use pytest for runtime validation.", ["testing"])
    write_entry(store, "actions", "Still active.")

    assert len(entry["id"]) == 8
    assert entry["version"] == 1
    assert read_entries(store, "project") == [entry]
    assert get_entry(store, entry["id"])["content"] == entry["content"]

    updated = edit_entry(store, entry["id"], content="Updated validation note.")
    assert updated["version"] == 2
    assert updated["history"][0]["content"] == "Use pytest for runtime validation."

    delete_entries(store, [entry["id"]])
    stats = get_stats(store)
    assert get_entry(store, entry["id"]) is None
    assert get_entry(store, entry["id"], include_deleted=True) is not None
    assert stats["total"] == 1
    assert stats["deleted_total"] == 1
    assert stats["by_section"]["project"] == 0
    assert stats["by_section"]["actions"] == 1


def test_write_entries_batch_and_default_section(store: Path):
    created = write_entries(
        store,
        [
            {"content": "No section given."},
            {"section": "actions", "content": "Second batch memory.", "tags": ["two"]},
        ],
    )
    stored = read_entries(store)

    assert created[0]["section"] == "project"
    assert [entry["content"] for entry in stored] == ["No section given.", "Second batch memory."]
    with pytest.raises(RemembValidationError, match="Duplicate"):
        write_entry(store, "project", "No section given.")


def test_edit_and_delete_batches(store: Path):
    first = write_entry(store, "project", "Original first.", ["a"])
    second = write_entry(store, "project", "Original second.", ["b"])

    results = edit_entries(
        store,
        [
            {"entry_id": first["id"], "content": "Updated first.", "tags": ["x"]},
            {"entry_id": second["id"], "section": "actions"},
            {"entry_id": "deadbeef", "content": "Missing"},
        ],
    )
    deleted_ids = delete_entries(store, [first["id"], "deadbeef"])
    remaining = read_entries(store)
    hidden = get_entry(store, first["id"], include_deleted=True)

    assert results[0]["content"] == "Updated first."
    assert results[1]["section"] == "actions"
    assert results[2] is None
    assert deleted_ids == [first["id"]]
    assert [entry["id"] for entry in remaining] == [second["id"]]
    assert hidden["deleted_at"]
    assert hidden["version"] == 3


def test_edit_upgrades_legacy_entry_to_versioned_history(store: Path):
    entry = write_entry(store, "project", "Legacy memory.", ["old"])
    entries_path = store / ".rememb" / "entries.json"
    stored_entries = json.loads(entries_path.read_text(encoding="utf-8"))
    stored_entries[0].pop("version", None)
    stored_entries[0].pop("history", None)
    entries_path.write_text(json.dumps(stored_entries, indent=2), encoding="utf-8")

    updated = edit_entries(store, [{"entry_id": entry["id"], "content": "Legacy memory updated."}])[0]

    assert updated["version"] == 2
    assert updated["history"][0]["version"] == 1
    assert updated["history"][0]["content"] == "Legacy memory."


def test_recent_page_search_and_tags(store: Path):
    first = write_entry(store, "project", "Deleted alpha memory", ["alpha"])
    live = write_entry(store, "project", "Live alpha memory", ["alpha", "launch"])
    write_entry(store, "project", "Roadmap and timeline details.", ["release"])
    edit_entry(store, first["id"], "Deleted alpha memory updated")
    delete_entries(store, [first["id"]])

    recent = read_recent_entries(store, limit=2, include_deleted=True)
    page = read_entries_page(store, sort_by="recent", descending=True, limit=1)
    hidden = search_entries(store, "alpha")
    visible = search_entries(store, "alpha", include_deleted=True)
    tags = list_entry_tags(store)

    assert recent[0]["id"] == first["id"]
    assert page["items"][0]["id"] == live["id"]
    assert page["has_more"] is True
    assert [entry["id"] for entry in hidden] == [live["id"]]
    assert {entry["id"] for entry in visible} == {first["id"], live["id"]}
    assert {item["tag"] for item in tags} >= {"alpha", "launch", "release"}


def test_search_ranks_tokens_and_records_access(store: Path):
    write_entry(store, "project", "Generic alpha planning note.", ["release"])
    write_entry(store, "project", "Roadmap and timeline details.", ["alpha", "launch"])

    results = search_entries(store, "alpha launch")
    stored = {entry["id"]: entry for entry in read_entries(store)}

    assert results[0]["tags"] == ["alpha", "launch"]
    assert results[0]["score"] > results[1]["score"]
    assert all(stored[result["id"]]["access_count"] == 1 for result in results)


def test_versions_restore_diff_and_export(store: Path):
    entry = write_entry(store, "project", "first line\nsecond line", ["draft"])
    edit_entries(store, [{"entry_id": entry["id"], "content": "first line\nthird line", "tags": ["released"]}])
    other = write_entry(store, "user", "Other content", ["drop"])
    delete_entries(store, [entry["id"], other["id"]])

    versions = list_entry_versions(store, entry["id"])
    diff = diff_entry_versions(store, entry["id"], 1, 2)
    restored_deleted = restore_deleted_entry(store, entry["id"])
    restored_version = restore_entry_version(store, entry["id"], 1)
    exported = export_entries(store, entry_id=entry["id"], include_versions=True)

    assert [revision["version"] for revision in versions] == [1, 2, 3]
    assert versions[-1]["deleted_at"]
    assert "second line" in diff["diff"]
    assert restored_deleted["version"] == 4
    assert restored_version["content"] == "first line\nsecond line"
    assert exported["entry_count"] == 1
    assert exported["entries"][0]["history"]
    assert export_entries(store, entry_id="deadbeef") is None
    with pytest.raises(RemembValidationError):
        export_entries(store, entry_id="bad")


def test_consolidate_merges_exact_duplicates(store: Path):
    write_entry(store, "project", "Same text", ["a"], skip_duplicates=False)
    write_entry(store, "project", "Same text", ["b"], skip_duplicates=False)
    write_entry(store, "actions", "Same text", ["c"], skip_duplicates=False)

    result = consolidate_entries(store, "project")
    entries = read_entries(store)
    project = [entry for entry in entries if entry["section"] == "project"]

    assert result["removed_count"] == 1
    assert result["merged_groups"] == 1
    assert len(project) == 1
    assert set(project[0]["tags"]) == {"a", "b"}
    assert len(entries) == 2


def test_update_config_and_clear(store: Path):
    write_entry(store, "project", "Keep this memory during section migration.")

    updated = update_config(store, {"sections": ["actions", "systems", "requests", "user", "context"]})
    entries = read_entries(store)

    assert "project" not in updated["sections"]
    assert entries[0]["section"] == "uncategorized"
    with pytest.raises(RemembValidationError):
        update_config(store, {"unknown": 1})
    with pytest.raises(RemembValidationError):
        update_config(store, {"max_entries": 0})
    with pytest.raises(RemembValidationError, match="confirm=True"):
        clear_entries(store)
    assert clear_entries(store, confirm=True) == 1
    assert read_entries(store) == []


def test_search_and_stats_require_initialization(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(RemembNotInitializedError):
        search_entries(root, "query")
    with pytest.raises(RemembNotInitializedError):
        get_stats(root)
    assert not (root / ".rememb").exists()


def test_format_entries_and_summarize_hint():
    text = format_entries(
        [
            {
                "id": "abcd1234",
                "section": "project",
                "content": "a" * 20,
                "tags": ["tag1"],
                "score": 0.98765,
                "updated_at": "2026-06-23T12:00:00Z",
            }
        ],
        include_id=True,
        include_score=True,
        max_chars=8,
    )

    assert "abcd1234" in text
    assert "score: 0.988" in text
    assert "aaaaa..." in text
    assert "2026-06-23" in text
    assert agent_summarize_hint(80) == ""
    assert "More pages may remain" in agent_summarize_hint(3, has_more=True)
