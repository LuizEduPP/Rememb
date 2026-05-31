from __future__ import annotations

from fastapi.testclient import TestClient

import rememb.web as web
from rememb.web import deps
from rememb.exceptions import RemembValidationError
from rememb.store import edit_entry, init, write_entry


client = TestClient(web.app)


def test_index_exposes_deleted_and_history_controls():
    response = client.get("/")

    assert response.status_code == 200
    assert "Show deleted" in response.text
    assert "Workstreams" in response.text
    assert "/static/app.js" in response.text

    app_js = client.get("/static/app.js")
    assert app_js.status_code == 200
    script = app_js.text
    assert "Handoffs" in script
    assert "Version history" in script
    assert "Timeline" in script
    assert "Side-by-side diff" in script
    assert "current vs previous" in script
    assert "/api/entries/" in script
    assert "/api/workstreams/" in script
    assert "Workstream state" in script
    assert "Workstream resume" in script
    assert "workstream detail" in script
    assert "Review" in script
    assert "/api/review" in script
    assert "/api/review/workstreams/" in script
    assert "handoff-package" in script
    assert "/api/workstreams/queue" in script
    assert "/api/workstreams/compare" in script
    assert "/api/workstreams/switch-package" in script
    assert "Next execution" in script
    assert "Views" in response.text
    assert "System" in response.text
    assert "Overview" in response.text
    assert "Registry" in response.text
    assert "View all" in response.text
    assert "Storage backend" in response.text
    assert "Save settings" in script
    assert "rememb-skills" in response.text
    assert "Skills" in response.text


def test_index_is_offline_ready_without_external_cdns():
    response = client.get("/")

    assert response.status_code == 200
    assert "https://fonts.googleapis.com" not in response.text
    assert "https://fonts.gstatic.com" not in response.text
    assert "https://cdn.tailwindcss.com" not in response.text
    assert "https://cdn.jsdelivr.net/npm/markdown-it" not in response.text


def test_entries_endpoint_hides_deleted_by_default(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    first = write_entry(root, "project", "Hidden after delete", ["alpha"])
    second = write_entry(root, "project", "Still active", ["alpha"])

    delete_response = client.delete(f"/api/entries/{first['id']}")
    assert delete_response.status_code == 204

    visible = client.get("/api/entries")
    with_deleted = client.get("/api/entries", params={"include_deleted": True})
    search_visible = client.get("/api/search", params={"q": "alpha"})
    search_with_deleted = client.get("/api/search", params={"q": "alpha", "include_deleted": True})

    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == [second["id"]]
    assert {item["id"] for item in with_deleted.json()["items"]} == {first["id"], second["id"]}
    assert [item["id"] for item in search_visible.json()["results"]] == [second["id"]]
    assert {item["id"] for item in search_with_deleted.json()["results"]} == {first["id"], second["id"]}


def test_versions_diff_and_restore_endpoints(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    create_response = client.post(
        "/api/entries",
        json={"content": "line one\nline two", "section": "project", "tags": ["draft"]},
    )
    assert create_response.status_code == 201
    entry = create_response.json()["entry"]

    update_response = client.put(
        f"/api/entries/{entry['id']}",
        json={"content": "line one\nline three", "tags": ["released"]},
    )
    assert update_response.status_code == 200

    delete_response = client.delete(f"/api/entries/{entry['id']}")
    assert delete_response.status_code == 204

    versions_response = client.get(f"/api/entries/{entry['id']}/versions")
    assert versions_response.status_code == 200
    assert [version["version"] for version in versions_response.json()["versions"]] == [1, 2, 3]

    diff_response = client.get(
        f"/api/entries/{entry['id']}/diff",
        params={"from_version": 1, "to_version": 2},
    )
    assert diff_response.status_code == 200
    assert "--- " in diff_response.json()["diff"]

    restore_deleted_response = client.post(f"/api/entries/{entry['id']}/restore")
    assert restore_deleted_response.status_code == 200
    assert restore_deleted_response.json()["entry"]["version"] == 4

    restore_version_response = client.post(f"/api/entries/{entry['id']}/versions/1/restore")
    assert restore_version_response.status_code == 200
    restored = restore_version_response.json()["entry"]
    assert restored["version"] == 5
    assert restored["content"] == "line one\nline two"

    stats_response = client.get("/api/stats")
    assert stats_response.status_code == 200
    assert stats_response.json()["deleted_entries"] == 0






def test_workstream_crud_like_endpoints_and_structured_handoff(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    opened = client.post(
        "/api/workstreams/open",
        json={"goal": "Ship workstream-first UI", "workstream_id": "ws_ui", "summary": "Primary operating surface"},
    )
    assert opened.status_code == 201

    listed = client.get("/api/workstreams")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["workstream_id"] == "ws_ui"

    started = client.post(
        "/api/workstreams/ws_ui/executions/start",
        json={"session_id": "sess_ui", "summary": "first pass"},
    )
    assert started.status_code == 201

    state_update = client.post(
        "/api/workstreams/ws_ui/state",
        json={
            "session_id": "sess_ui",
            "current_state": ["view created"],
            "open_loops": ["validate browser"],
            "next_steps": ["run focused tests"],
        },
    )
    assert state_update.status_code == 200
    assert state_update.json()["entry"]["structured"]["current_state"] == ["view created"]

    structured_handoff = client.post(
        "/api/workstreams/ws_ui/handoff",
        json={
            "session_id": "sess_ui",
            "goal": "Ship workstream-first UI",
            "summary": "Ready for validation",
            "next_steps": ["check browser"],
            "related_entries": ["deadbeef@v2"],
            "archived_context": ["legacy modal flow"],
            "audience": "agent",
        },
    )
    assert structured_handoff.status_code == 201

    structured_read = client.get("/api/workstreams/ws_ui/handoff")
    assert structured_read.status_code == 200
    assert structured_read.json()["goal"] == "Ship workstream-first UI"
    assert structured_read.json()["related_entries"][0]["entry_id"] == "deadbeef"
    assert structured_read.json()["archived_context"] == ["legacy modal flow"]
    assert structured_read.json()["audience"] == "agent"

    state_response = client.get("/api/workstreams/ws_ui/state")
    assert state_response.status_code == 200
    timeline = state_response.json()["timeline"]
    assert len(timeline) >= 3
    assert timeline[0]["entry_kind"] in {"handoff", "state", "review"}
    assert any(item["entry_kind"] == "handoff" for item in timeline)
    assert any(item["session_id"] == "sess_ui" for item in timeline)

    closed = client.post(
        "/api/workstreams/ws_ui/executions/close",
        json={"session_id": "sess_ui", "outcome": "Implementation complete", "next_steps": ["restart web"]},
    )
    assert closed.status_code == 201
    assert closed.json()["entry"]["entry_kind"] == "review"


def test_handoff_package_close_and_handoff_and_review_endpoints(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    client.post(
        "/api/workstreams/open",
        json={"goal": "Ship review mode", "workstream_id": "ws_review", "summary": "Review surface"},
    )
    client.post(
        "/api/workstreams/ws_review/executions/start",
        json={"session_id": "sess_review", "summary": "first pass"},
    )
    client.post(
        "/api/workstreams/ws_review/state",
        json={
            "session_id": "sess_review",
            "summary": "Queue exists",
            "current_state": ["review queue rendered"],
            "open_loops": ["approve entries"],
            "next_steps": ["wire diff pane"],
            "essential_context": ["preserve workstream-first flow"],
            "archived_context": ["old modal close"],
            "risk_flags": ["human review still pending"],
        },
    )
    entry = write_entry(
        root,
        "actions",
        "Agent draft for review.",
        workstream_id="ws_review",
        session_id="sess_review",
        entry_kind="decision",
        actor_type="agent",
        structured={"risk_flags": ["needs human approval"]},
    )
    edit_entry(root, entry["id"], content="Agent draft for review with final diff.")

    handoff_package = client.get(
        "/api/workstreams/ws_review/handoff-package",
        params={"next_goal": "Approve review queue"},
    )
    switch_package = client.get(
        "/api/workstreams/switch-package",
        params={"current_workstream_id": "ws_review", "target_workstream_id": "ws_review"},
    )
    close_and_handoff = client.post(
        "/api/workstreams/ws_review/executions/close-and-handoff",
        json={
            "session_id": "sess_review",
            "outcome": "Review queue prepared",
            "next_goal": "Approve review queue",
            "audience": "human",
        },
    )
    review_list = client.get("/api/review", params={"workstream_id": "ws_review"})

    assert handoff_package.status_code == 200
    assert handoff_package.json()["next_goal"] == "Approve review queue"
    assert handoff_package.json()["next_execution"]["goal"] == "Approve review queue"
    assert handoff_package.json()["compressed_context"]["archived"] == ["old modal close"]
    assert switch_package.status_code == 200
    assert switch_package.json()["switch_mode"] == "anti_context_switch"
    assert switch_package.json()["resume_target"]["next_execution"]["goal"] == "Ship review mode"
    assert close_and_handoff.status_code == 201
    assert close_and_handoff.json()["handoff_entry"]["entry_kind"] == "handoff"
    assert review_list.status_code == 200
    assert review_list.json()["items"][0]["review_status"] == "pending"
    assert review_list.json()["items"][0]["agent_review"]["decision"] == "escalate_for_validation"

    review_update = client.post(
        f"/api/review/{review_list.json()['items'][0]['entry_id']}",
        json={"review_status": "approved", "review_notes": "Accepted."},
    )
    assert review_update.status_code == 200
    assert review_update.json()["entry"]["structured"]["review_status"] == "approved"
    assert review_update.json()["entry"]["structured"]["human_validation"]["status"] == "approved"


def test_review_endpoint_filters_by_session(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    write_entry(
        root,
        "actions",
        "Decision for first session.",
        workstream_id="ws_review_scope",
        session_id="sess_a",
        entry_kind="decision",
        actor_type="agent",
        structured={"risk_flags": ["session A"]},
    )
    write_entry(
        root,
        "actions",
        "Decision for second session.",
        workstream_id="ws_review_scope",
        session_id="sess_b",
        entry_kind="decision",
        actor_type="agent",
        structured={"risk_flags": ["session B"]},
    )

    filtered = client.get("/api/review", params={"workstream_id": "ws_review_scope", "session_id": "sess_b"})

    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 1
    assert filtered.json()["items"][0]["session_id"] == "sess_b"


def test_review_summary_queue_and_compare_endpoints(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    client.post(
        "/api/workstreams/open",
        json={"goal": "Ship supervisor", "workstream_id": "ws_supervisor", "summary": "Review flow"},
    )
    client.post(
        "/api/workstreams/ws_supervisor/executions/start",
        json={"session_id": "sess_a", "summary": "first"},
    )
    client.post(
        "/api/workstreams/ws_supervisor/state",
        json={
            "session_id": "sess_a",
            "summary": "Session A ready",
            "current_state": ["queue drafted"],
            "open_loops": ["wire compare UI"],
            "next_steps": ["ship review grouping"],
        },
    )
    first = write_entry(
        root,
        "actions",
        "Agent draft pending review.",
        workstream_id="ws_supervisor",
        session_id="sess_a",
        entry_kind="decision",
        actor_type="agent",
        actor_id="copilot",
        structured={"risk_flags": ["needs approval"]},
    )
    client.post(
        "/api/workstreams/ws_supervisor/executions/close",
        json={"session_id": "sess_a", "outcome": "paused", "next_goal": "continue"},
    )
    client.post(
        "/api/workstreams/ws_supervisor/executions/start",
        json={"session_id": "sess_b", "summary": "second", "goal": "continue"},
    )
    client.post(
        "/api/workstreams/ws_supervisor/state",
        json={
            "session_id": "sess_b",
            "summary": "Session B ready",
            "current_state": ["queue shipped"],
            "open_loops": ["wire dashboard compare"],
            "next_steps": ["ship workstream diff"],
        },
    )
    write_entry(
        root,
        "actions",
        "Second review decision introduces comparison workflow and dashboard changes.",
        workstream_id="ws_supervisor",
        session_id="sess_b",
        entry_kind="decision",
        actor_type="agent",
        actor_id="copilot",
        supersedes_entry_id=first["id"],
        structured={"risk_flags": ["needs approval"]},
    )

    client.post(
        "/api/workstreams/open",
        json={"goal": "Ship handoff board", "workstream_id": "ws_other", "summary": "Other"},
    )
    client.post(
        "/api/workstreams/ws_other/executions/start",
        json={"session_id": "sess_other", "summary": "other"},
    )
    client.post(
        "/api/workstreams/ws_other/state",
        json={
            "session_id": "sess_other",
            "summary": "Other ready",
            "current_state": ["handoff board drafted"],
            "open_loops": ["connect queue"],
            "next_steps": ["ship handoff compare"],
        },
    )

    filtered_review = client.get(
        "/api/review",
        params={"workstream_id": "ws_supervisor", "actor_type": "agent", "actor_id": "copilot", "entry_kind": "decision", "pending_only": False},
    )
    review_session = client.get("/api/review/workstreams/ws_supervisor/executions/sess_b")
    review_workstream = client.get("/api/review/workstreams/ws_supervisor")
    queue = client.get("/api/workstreams/queue", params={"status": "awaiting_review"})
    compare_sessions = client.get(
        "/api/workstreams/ws_supervisor/compare/executions",
        params={"base_execution_id": "sess_a", "target_execution_id": "sess_b"},
    )
    compare_workstreams = client.get(
        "/api/workstreams/compare",
        params={"left_workstream_id": "ws_supervisor", "right_workstream_id": "ws_other"},
    )
    review_update = client.post(
        f"/api/review/{filtered_review.json()['items'][0]['entry_id']}",
        json={
            "review_status": "needs_revision",
            "review_notes": "Refine causal trail.",
            "review_reason": "missing source links",
            "validation_notes": "Need a second pass.",
            "source_context_entry_ids": [first["id"]],
        },
    )

    assert filtered_review.status_code == 200
    assert len(filtered_review.json()["items"]) == 2
    assert filtered_review.json()["items"][0]["actor_id"] == "copilot"
    assert review_session.status_code == 200
    assert review_session.json()["session_id"] == "sess_b"
    assert review_session.json()["execution_id"] == "sess_b"
    assert review_session.json()["pending_review_count"] >= 1
    assert review_workstream.status_code == 200
    assert review_workstream.json()["operational_status"] == "awaiting_review"
    assert queue.status_code == 200
    assert queue.json()["items"][0]["workstream_id"] == "ws_supervisor"
    assert compare_sessions.status_code == 200
    assert compare_sessions.json()["base_execution_id"] == "sess_a"
    assert compare_sessions.json()["target_execution_id"] == "sess_b"
    assert compare_sessions.json()["delta"]["new_open_loops"] == ["wire dashboard compare"]
    assert compare_workstreams.status_code == 200
    assert "left_only_open_loops" in compare_workstreams.json()["delta"]
    assert review_update.status_code == 200
    assert review_update.json()["entry"]["structured"]["review_reason"] == "missing source links"


def test_entries_endpoint_accepts_workstream_and_session_metadata(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    created = client.post(
        "/api/entries",
        json={
            "content": "Operational note",
            "section": "actions",
            "tags": ["ops"],
            "workstream_id": "ws_meta",
            "session_id": "sess_meta",
        },
    )
    assert created.status_code == 201
    entry_id = created.json()["entry"]["id"]
    assert created.json()["entry"]["workstream_id"] == "ws_meta"

    updated = client.put(
        f"/api/entries/{entry_id}",
        json={"workstream_id": "ws_meta_2", "session_id": "sess_meta_2"},
    )
    assert updated.status_code == 200
    assert updated.json()["entry"]["workstream_id"] == "ws_meta_2"
    assert updated.json()["entry"]["session_id"] == "sess_meta_2"


def test_workstream_routes_normalize_domain_errors(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)
    monkeypatch.setattr(
        "rememb.web.routes.workstreams.get_workstream_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RemembValidationError("bad workstream")),
    )
    monkeypatch.setattr(
        "rememb.web.routes.workstreams.resume_workstream",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RemembValidationError("bad resume")),
    )

    state_response = client.get("/api/workstreams/ws_bad/state")
    resume_response = client.get("/api/workstreams/ws_bad/resume")

    assert state_response.status_code == 422
    assert state_response.json()["detail"] == "bad workstream"
    assert resume_response.status_code == 422
    assert resume_response.json()["detail"] == "bad resume"


