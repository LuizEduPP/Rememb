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
    build_handoff_package,
    build_workstream_switch_package,
    clear_entries,
    compare_sessions,
    compare_workstreams,
    close_session,
    close_session_with_handoff,
    diff_entry_versions,
    delete_entries,
    edit_entries,
    format_entries,
    _generate_handoff,
    get_review_session,
    get_review_workstream,
    get_stats,
    get_workstream_state,
    init,
    list_entry_versions,
    list_review_queue,
    list_workstream_queue,
    list_workstreams,
    open_workstream,
    parse_handoff_restore_context,
    read_structured_handoff,
    read_entries,
    read_entries_page,
    resume_workstream,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    start_session,
    update_config,
    update_review_status,
    update_workstream_state,
    write_entries,
    write_entry,
    write_structured_handoff,
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


def test_write_entry_accepts_optional_operational_metadata(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    entry = write_entry(
        root,
        "project",
        "Operational state for an active workstream.",
        ["ops"],
        workstream_id="ws_alpha",
        session_id="sess_001",
        entry_kind="state",
        entry_role="essential",
        actor_type="agent",
        actor_id="copilot",
        related_entry_ids=["abcd1234"],
        structured={"goal": "ship", "current_state": ["done"]},
    )

    assert entry["workstream_id"] == "ws_alpha"
    assert entry["session_id"] == "sess_001"
    assert entry["entry_kind"] == "state"
    assert entry["entry_role"] == "essential"
    assert entry["actor_type"] == "agent"
    assert entry["actor_id"] == "copilot"
    assert entry["related_entry_ids"] == ["abcd1234"]
    assert entry["structured"]["goal"] == "ship"


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


def test_edit_entries_updates_operational_metadata_and_history(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    entry = write_entry(root, "project", "Base memory.", entry_kind="memory")

    updated = edit_entries(
        root,
        [{
            "entry_id": entry["id"],
            "entry_kind": "decision",
            "workstream_id": "ws_beta",
            "structured": {"decision": "Use MCP", "status": "active"},
        }],
    )[0]

    assert updated is not None
    assert updated["entry_kind"] == "decision"
    assert updated["workstream_id"] == "ws_beta"
    assert updated["structured"]["decision"] == "Use MCP"
    assert updated["version"] == 2
    assert updated["history"][0]["entry_kind"] == "memory"


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


def test__generate_handoff_formats_content_and_parses_restore_context():
    payload = _generate_handoff(
        "Ship handoff MVP",
        summary="Focus on the smallest useful store slice.",
        current_state=["Store already supports versions."],
        open_loops=["Add public handoff helpers."],
        next_steps=["Write tests.", "Expose MCP later."],
        related_entries=["abcd1234", "deadbeef@v2"],
        restore_section="actions",
        restore_query="handoff mvp",
        include_deleted=True,
        tags=["resume"],
    )

    parsed = parse_handoff_restore_context(payload["content"])

    assert payload["section"] == "actions"
    assert "handoff" in payload["tags"]
    assert "goal:ship-handoff-mvp" in payload["tags"]
    assert payload["entry_kind"] == "handoff"
    assert payload["structured"]["goal"] == "Ship handoff MVP"
    assert parsed["goal"] == "Ship handoff MVP"
    assert parsed["summary"] == "Focus on the smallest useful store slice."
    assert parsed["current_state"] == ["Store already supports versions."]
    assert parsed["open_loops"] == ["Add public handoff helpers."]
    assert parsed["next_steps"] == ["Write tests.", "Expose MCP later."]
    assert parsed["related_entries"][0]["entry_id"] == "abcd1234"
    assert parsed["related_entries"][0]["version"] is None
    assert parsed["related_entries"][1]["entry_id"] == "deadbeef"
    assert parsed["related_entries"][1]["version"] == 2
    assert parsed["restore_context"] == {
        "section": "actions",
        "query": "handoff mvp",
        "include_deleted": True,
    }




def test_workstream_state_and_resume_aggregate_sessions(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    first_state = write_entry(
        root,
        "project",
        "Initial workstream snapshot.",
        workstream_id="ws_agent",
        session_id="sess_a",
        entry_kind="state",
        structured={
            "goal": "Ship workstream resume",
            "current_state": ["metadata stored"],
        },
    )
    handoff_payload = _generate_handoff(
        "Ship workstream resume",
        summary="Use the latest handoff when resuming.",
        current_state=["metadata stored", "MCP pending"],
        open_loops=["Expose tools"],
        next_steps=["Add MCP handlers"],
        related_entries=[first_state["id"]],
        restore_query="workstream ws_agent",
    )
    handoff = write_entry(
        root,
        handoff_payload["section"],
        handoff_payload["content"],
        handoff_payload["tags"],
        workstream_id="ws_agent",
        session_id="sess_b",
        entry_kind="handoff",
        structured=handoff_payload["structured"],
        related_entry_ids=[first_state["id"]],
    )
    write_entry(
        root,
        "actions",
        "Another workstream entry.",
        workstream_id="ws_other",
        session_id="sess_z",
        entry_kind="state",
    )

    state = get_workstream_state(root, "ws_agent")
    filtered_state = get_workstream_state(root, "ws_agent", session_id="sess_a")
    resume = resume_workstream(root, "ws_agent")

    assert state is not None
    assert state["entry_count"] == 2
    assert state["session_count"] == 2
    assert state["latest_handoff"]["id"] == handoff["id"]
    assert state["latest_state"]["id"] == first_state["id"]
    assert state["sessions"][0]["session_id"] == "sess_b"
    assert filtered_state is not None
    assert filtered_state["entry_count"] == 1
    assert filtered_state["session_count"] == 1
    assert filtered_state["latest_entry"]["id"] == first_state["id"]
    assert resume is not None
    assert resume["goal"] == "Ship workstream resume"
    assert resume["summary"] == "Use the latest handoff when resuming."
    assert resume["current_state"] == ["metadata stored", "MCP pending"]
    assert resume["open_loops"] == ["Expose tools"]
    assert resume["next_steps"] == ["Add MCP handlers"]
    assert resume["related_entry_ids"] == [first_state["id"]]
    assert resume["focus_entry_ids"] == [handoff["id"], first_state["id"]]




def test_resume_workstream_falls_back_to_state_context_without_handoff(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    state_entry = write_entry(
        root,
        "actions",
        "Current operational state.",
        workstream_id="ws_state_only",
        session_id="sess_state",
        entry_kind="state",
        structured={
            "goal": "Ship state-only resume",
            "summary": "No handoff written yet.",
            "current_state": ["state exists"],
        },
    )

    resume = resume_workstream(root, "ws_state_only")

    assert resume is not None
    assert resume["goal"] == "Ship state-only resume"
    assert resume["summary"] == "No handoff written yet."
    assert resume["focus_entry_ids"] == [state_entry["id"]]
    assert resume["restore_context"] == {
        "section": "actions",
        "query": "Ship state-only resume",
        "include_deleted": False,
    }


def test_workstream_open_list_and_session_lifecycle(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    opened = open_workstream(root, "Ship the workstream-first UI", workstream_id="ws_ui", summary="Primary operational surface")
    session = start_session(root, "ws_ui", summary="Iteration 1", session_id="sess_ui")
    updated = update_workstream_state(
        root,
        "ws_ui",
        session_id="sess_ui",
        current_state=["spa view ready"],
        open_loops=["add browser validation"],
        next_steps=["wire tests"],
    )
    review = close_session(
        root,
        "ws_ui",
        session_id="sess_ui",
        outcome="Implemented workstream-first navigation.",
        next_steps=["validate browser"],
    )
    items = list_workstreams(root)

    assert opened["created"] is True
    assert opened["workstream_id"] == "ws_ui"
    assert session is not None
    assert session["session_id"] == "sess_ui"
    assert updated is not None
    assert updated["structured"]["current_state"] == ["spa view ready"]
    assert review is not None
    assert review["entry_kind"] == "review"
    assert items[0]["workstream_id"] == "ws_ui"
    assert items[0]["session_count"] == 1


def test_structured_handoff_roundtrip_for_workstream(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    open_workstream(root, "Ship MCP parity", workstream_id="ws_mcp")
    start_session(root, "ws_mcp", session_id="sess_mcp")
    handoff = write_structured_handoff(
        root,
        "ws_mcp",
        session_id="sess_mcp",
        goal="Ship MCP parity",
        summary="Store, MCP and Web aligned.",
        current_state=["store done"],
        decisions=["keep entry-first storage"],
        open_loops=["finish browser validation"],
        next_steps=["run focused tests"],
        essential_context=["public API must stay compatible"],
        optional_context=["web polish can follow"],
        related_entries=["deadbeef@v2"],
        risk_flags=["server restart may be blocked"],
    )

    payload = read_structured_handoff(root, workstream_id="ws_mcp")

    assert handoff["entry_kind"] == "handoff"
    assert payload is not None
    assert payload["entry_id"] == handoff["id"]
    assert payload["goal"] == "Ship MCP parity"
    assert payload["decisions"] == ["keep entry-first storage"]
    assert payload["related_entries"][0]["entry_id"] == "deadbeef"


def test_resume_workstream_exposes_compressed_context_and_changes(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    open_workstream(root, "Ship anti context switch", workstream_id="ws_focus")
    start_session(root, "ws_focus", session_id="sess_focus")
    state_entry = update_workstream_state(
        root,
        "ws_focus",
        session_id="sess_focus",
        current_state=["review mode drafted"],
        essential_context=["preserve local-first store"],
        optional_context=["UI polish can wait"],
        archived_context=["old modal flow"],
        risk_flags=["timeline can drift if not anchored"],
        obsolete_context=["legacy modal-only detail"],
    )
    write_entry(
        root,
        "actions",
        "Added review route.",
        workstream_id="ws_focus",
        session_id="sess_focus",
        entry_kind="decision",
        actor_type="agent",
        related_entry_ids=[state_entry["id"]],
    )

    resume = resume_workstream(root, "ws_focus")

    assert resume is not None
    assert resume["compressed_context"] == {
        "essential": ["preserve local-first store"],
        "optional": ["UI polish can wait"],
        "archived": ["old modal flow"],
        "risky": ["timeline can drift if not anchored"],
        "obsolete": ["legacy modal-only detail"],
    }
    assert len(resume["what_changed"]) == 1
    assert resume["what_changed"][0]["entry_kind"] == "decision"


def test_build_handoff_package_and_close_session_with_handoff(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    open_workstream(root, "Ship anti context switch", workstream_id="ws_pkg")
    start_session(root, "ws_pkg", session_id="sess_pkg")
    update_workstream_state(
        root,
        "ws_pkg",
        session_id="sess_pkg",
        summary="Review mode is wired.",
        current_state=["store ready"],
        open_loops=["expose MCP"],
        next_steps=["wire web route"],
        essential_context=["keep workstream-first flow"],
        optional_context=["docs can follow"],
        archived_context=["old entry-first shortcut"],
        risk_flags=["UI needs diff previews"],
    )

    package = build_handoff_package(root, "ws_pkg", next_goal="Ship review mode")
    result = close_session_with_handoff(
        root,
        "ws_pkg",
        session_id="sess_pkg",
        outcome="Prepared the new operational layer.",
        next_goal="Ship review mode",
        audience="human",
    )
    payload = read_structured_handoff(root, workstream_id="ws_pkg")

    assert package is not None
    assert package["next_goal"] == "Ship review mode"
    assert package["handoff_schema"] == "agent-first-operational-v1"
    assert package["execution_history_count"] == 1
    assert package["next_execution"]["goal"] == "Ship review mode"
    assert package["next_execution"]["resume_mode"] == "goal_oriented"
    assert package["operational_handoff"]["goal"] == "Ship review mode"
    assert package["operational_handoff"]["restore_hint"] == package["restore_context"]
    assert package["agent_handoff"]["essential_context"] == ["keep workstream-first flow"]
    assert package["human_handoff"]["watchouts"] == ["UI needs diff previews"]
    assert result is not None
    assert result["review_entry"]["entry_kind"] == "review"
    assert result["handoff_entry"]["entry_kind"] == "handoff"
    assert payload is not None
    assert payload["handoff_schema"] == "agent-first-operational-v1"
    assert payload["goal"] == "Ship review mode"
    assert payload["audience"] == "agent"
    assert payload["requested_audience"] == "human"
    assert payload["restore_hint"] == payload["restore_context"]
    assert payload["archived_context"] == ["old entry-first shortcut"]
    assert payload["next_execution"]["goal"] == "Ship review mode"


def test_review_queue_and_status_updates(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    created = write_entry(
        root,
        "actions",
        "Draft review queue.",
        workstream_id="ws_review",
        session_id="sess_review",
        entry_kind="decision",
        actor_type="agent",
        structured={"risk_flags": ["needs approval"]},
    )
    edited = edit_entries(root, [{"entry_id": created["id"], "content": "Draft review queue v2."}])[0]

    queue = list_review_queue(root, workstream_id="ws_review")
    updated = update_review_status(root, edited["id"], "approved", review_notes="Reviewed by human.")
    pending_after = list_review_queue(root, workstream_id="ws_review")
    all_items = list_review_queue(root, workstream_id="ws_review", pending_only=False)

    assert queue[0]["entry_id"] == edited["id"]
    assert queue[0]["review_reasons"] == ["agent_generated", "versioned", "kind:decision", "risk_flags"]
    assert queue[0]["agent_review"]["decision"] == "escalate_for_validation"
    assert queue[0]["agent_review"]["risk_level"] == "critical"
    assert queue[0]["provenance"]["current_version"] == 2
    assert "+++" in (queue[0]["diff"] or "")
    assert updated is not None
    assert updated["structured"]["review_status"] == "approved"
    assert updated["structured"]["human_validation"]["status"] == "approved"
    assert pending_after == []
    assert all_items[0]["review_status"] == "approved"
    assert all_items[0]["human_validation"]["status"] == "approved"


def test_review_aggregations_and_operational_queue(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    open_workstream(root, "Ship review supervisor", workstream_id="ws_supervisor")
    start_session(root, "ws_supervisor", session_id="sess_supervisor")
    anchor = write_entry(
        root,
        "project",
        "Original context snapshot.",
        workstream_id="ws_supervisor",
        session_id="sess_supervisor",
        actor_type="human",
        actor_id="luiz",
    )
    first_decision = write_entry(
        root,
        "actions",
        "Draft the first review policy.",
        workstream_id="ws_supervisor",
        session_id="sess_supervisor",
        entry_kind="decision",
        actor_type="agent",
        actor_id="copilot",
        related_entry_ids=[anchor["id"]],
        structured={"risk_flags": ["needs supervision"], "source_context_entry_ids": [anchor["id"]]},
    )
    second_decision = write_entry(
        root,
        "actions",
        "Replace the first review policy with a tighter one.",
        workstream_id="ws_supervisor",
        session_id="sess_supervisor",
        entry_kind="decision",
        actor_type="agent",
        actor_id="copilot",
        supersedes_entry_id=first_decision["id"],
        related_entry_ids=[first_decision["id"], anchor["id"]],
        structured={"risk_flags": ["needs human approval"], "source_context_entry_ids": [anchor["id"]]},
    )

    filtered_queue = list_review_queue(
        root,
        workstream_id="ws_supervisor",
        actor_type="agent",
        actor_id="copilot",
        entry_kind="decision",
        pending_only=False,
    )
    review_session = get_review_session(root, "ws_supervisor", "sess_supervisor")
    review_workstream = get_review_workstream(root, "ws_supervisor")
    queue = list_workstream_queue(root, status="awaiting_review")

    assert [item["entry_id"] for item in filtered_queue] == [second_decision["id"], first_decision["id"]]
    assert filtered_queue[0]["actor_id"] == "copilot"
    assert filtered_queue[0]["supersedes_entry_id"] == first_decision["id"]
    assert filtered_queue[0]["source_context_entry_ids"] == [first_decision["id"], anchor["id"]]
    assert filtered_queue[0]["agent_review"]["risk_level"] == "critical"
    assert filtered_queue[0]["supervision_status"] == "awaiting_human_validation"
    assert review_session is not None
    assert review_session["operational_status"] == "awaiting_review"
    assert review_session["pending_review_count"] == 2
    assert review_session["active_decision_ids"] == [second_decision["id"]]
    assert review_session["resume"]["next_execution"]["goal"] == "Ship review supervisor"
    assert review_session["execution_snapshot"]["inputs"]["source_context_entry_ids"] == [anchor["id"], first_decision["id"]]
    assert review_session["execution_snapshot"]["review_result"]["pending_human_validation"] == 2
    assert review_workstream is not None
    assert review_workstream["operational_status"] == "awaiting_review"
    assert review_workstream["sessions"][0]["session_id"] == "sess_supervisor"
    assert review_workstream["resume"]["next_execution"]["goal"] == "Ship review supervisor"
    assert review_workstream["review_policy_summary"]["escalate_for_validation"] == 2
    assert queue[0]["workstream_id"] == "ws_supervisor"
    assert queue[0]["operational_status"] == "awaiting_review"


def test_compare_sessions_and_workstreams(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)

    open_workstream(root, "Ship queue", workstream_id="ws_compare")
    start_session(root, "ws_compare", session_id="sess_a")
    update_workstream_state(
        root,
        "ws_compare",
        session_id="sess_a",
        summary="First session ready.",
        current_state=["review queue drafted"],
        open_loops=["wire filters"],
        next_steps=["ship state route"],
    )
    close_session(root, "ws_compare", session_id="sess_a", outcome="Paused after drafting.", next_goal="Finish filters")

    start_session(root, "ws_compare", session_id="sess_b", goal="Finish filters")
    update_workstream_state(
        root,
        "ws_compare",
        session_id="sess_b",
        summary="Second session advanced.",
        current_state=["review queue shipped"],
        open_loops=["ship comparison UI"],
        next_steps=["wire workstream compare"],
    )
    write_entry(
        root,
        "actions",
        "Agent changed review policy.",
        workstream_id="ws_compare",
        session_id="sess_b",
        entry_kind="decision",
        actor_type="agent",
        structured={"risk_flags": ["needs human approval"]},
    )

    open_workstream(root, "Ship handoff dashboard", workstream_id="ws_other")
    start_session(root, "ws_other", session_id="sess_other")
    update_workstream_state(
        root,
        "ws_other",
        session_id="sess_other",
        summary="Other workstream.",
        current_state=["handoff dashboard drafted"],
        open_loops=["connect review queue"],
        next_steps=["ship handoff compare"],
    )

    session_compare = compare_sessions(root, "ws_compare", "sess_a", "sess_b")
    workstream_compare = compare_workstreams(root, "ws_compare", "ws_other")
    switch_package = build_workstream_switch_package(root, "ws_compare", "ws_other")

    assert session_compare is not None
    assert session_compare["delta"]["new_open_loops"] == ["ship comparison UI"]
    assert session_compare["delta"]["resolved_open_loops"] == ["wire filters"]
    assert session_compare["delta"]["new_next_steps"] == ["wire workstream compare"]
    assert session_compare["delta"]["risk_shift"]["target_pending_human_validation"] == 1
    assert session_compare["delta"]["new_decision_entry_ids"]
    assert workstream_compare is not None
    assert workstream_compare["left"]["workstream_id"] == "ws_compare"
    assert workstream_compare["right"]["workstream_id"] == "ws_other"
    assert workstream_compare["delta"]["left_operational_status"] == "awaiting_review"
    assert workstream_compare["switch_package"]["target_workstream_id"] == "ws_other"
    assert workstream_compare["open_loops_diff"]
    assert switch_package is not None
    assert switch_package["switch_mode"] == "anti_context_switch"
    assert switch_package["state_gap"]["needed_now_but_not_open"]