from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import rememb.mcp_server as mcp_server
from rememb.mcp_server import _build_tools
from rememb.utils import list_skill_definitions, load_skill_definition


@dataclass
class FakeTool:
    name: str
    description: str
    inputSchema: dict


@dataclass
class FakeTextContent:
    type: str
    text: str


def test_build_tools_exposes_expected_public_contract():
    tools = _build_tools(FakeTool)
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {
        "rememb_read",
        "rememb_read_page",
        "rememb_search",
        "rememb_versions",
        "rememb_restore",
        "rememb_diff",
        "rememb_handoff_generate",
        "rememb_handoff_package",
        "rememb_handoff_list",
        "rememb_handoff_restore_context",
        "rememb_handoff_write_structured",
        "rememb_handoff_read_structured",
        "rememb_workstream_switch_package",
        "rememb_workstream_list",
        "rememb_workstream_open",
        "rememb_workstream_state_get",
        "rememb_workstream_state_update",
        "rememb_workstream_resume",
        "rememb_execution_start",
        "rememb_execution_close",
        "rememb_execution_close_and_handoff",
        "rememb_review_queue",
        "rememb_review_execution_get",
        "rememb_review_workstream_get",
        "rememb_workstream_queue",
        "rememb_compare_executions",
        "rememb_compare_workstreams",
        "rememb_review_update",
        "rememb_write",
        "rememb_edit",
        "rememb_delete",
        "rememb_clear",
        "rememb_stats",
        "rememb_consolidate",
        "rememb_init",
        "rememb_list_skills",
        "rememb_use_skill",
    }
    assert by_name["rememb_search"].inputSchema["required"] == ["query"]
    assert by_name["rememb_write"].inputSchema["properties"]["semantic_scope"]["default"] == "global"
    assert "entries" in by_name["rememb_write"].inputSchema["properties"]
    assert "section" in by_name["rememb_read"].inputSchema["properties"]
    assert by_name["rememb_read"].inputSchema["properties"]["include_deleted"]["default"] is False
    assert "max_chars" in by_name["rememb_read"].inputSchema["properties"]
    assert by_name["rememb_read_page"].inputSchema["properties"]["offset"]["default"] == 0
    assert by_name["rememb_read_page"].inputSchema["properties"]["summary_only"]["default"] is True
    assert "section" in by_name["rememb_search"].inputSchema["properties"]
    assert by_name["rememb_search"].inputSchema["properties"]["include_deleted"]["default"] is False
    assert "summary_only" in by_name["rememb_search"].inputSchema["properties"]
    assert by_name["rememb_versions"].inputSchema["required"] == ["entry_id"]
    assert by_name["rememb_restore"].inputSchema["required"] == ["entry_id"]
    assert by_name["rememb_diff"].inputSchema["required"] == ["entry_id", "from_version", "to_version"]
    assert by_name["rememb_handoff_generate"].inputSchema["required"] == ["goal"]
    assert by_name["rememb_handoff_package"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_workstream_switch_package"].inputSchema["required"] == ["current_workstream_id", "target_workstream_id"]
    assert by_name["rememb_handoff_restore_context"].inputSchema["required"] == ["entry_id"]
    assert "workstream_id" in by_name["rememb_handoff_generate"].inputSchema["properties"]
    assert "session_id" in by_name["rememb_handoff_generate"].inputSchema["properties"]
    assert by_name["rememb_handoff_write_structured"].inputSchema["required"] == ["workstream_id", "goal"]
    assert "workstream_id" in by_name["rememb_handoff_read_structured"].inputSchema["properties"]
    assert "limit" in by_name["rememb_workstream_list"].inputSchema["properties"]
    assert by_name["rememb_workstream_open"].inputSchema["required"] == ["goal"]
    assert by_name["rememb_workstream_state_get"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_workstream_state_update"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_workstream_resume"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_execution_start"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_execution_close"].inputSchema["required"] == ["workstream_id", "outcome"]
    assert by_name["rememb_execution_close_and_handoff"].inputSchema["required"] == ["workstream_id", "outcome", "next_goal"]
    assert by_name["rememb_review_execution_get"].inputSchema["required"] == ["workstream_id", "execution_id"]
    assert by_name["rememb_review_workstream_get"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_compare_executions"].inputSchema["required"] == ["workstream_id", "base_execution_id", "target_execution_id"]
    assert by_name["rememb_compare_workstreams"].inputSchema["required"] == ["left_workstream_id", "right_workstream_id"]
    assert by_name["rememb_review_update"].inputSchema["required"] == ["entry_id", "review_status"]
    assert "actor_type" in by_name["rememb_review_queue"].inputSchema["properties"]
    assert "review_reason" in by_name["rememb_review_update"].inputSchema["properties"]
    assert "workstream_id" in by_name["rememb_write"].inputSchema["properties"]
    assert "entry_kind" in by_name["rememb_write"].inputSchema["properties"]
    assert "structured" in by_name["rememb_edit"].inputSchema["properties"]
    assert "updates" in by_name["rememb_edit"].inputSchema["properties"]
    assert "entry_ids" in by_name["rememb_delete"].inputSchema["properties"]
    assert by_name["rememb_use_skill"].inputSchema["required"] == ["skill"]


def test_handle_tool_supports_batch_write(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    captured = {}

    def fake_write_entries(root, entries, skip_duplicates, semantic_scope):
        captured["entries"] = entries
        captured["semantic_scope"] = semantic_scope
        return [
            {"id": "11111111", "section": entries[0]["section"]},
            {"id": "22222222", "section": entries[1]["section"]},
        ]

    monkeypatch.setattr(
        mcp_server,
        "write_entries",
        fake_write_entries,
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_write",
            {
                "entries": [
                    {"content": "First", "section": "project", "tags": ["a"], "workstream_id": "ws_1", "entry_kind": "state"},
                    {"content": "Second", "section": "actions"},
                ]
            },
            FakeTextContent,
        )
    )

    assert len(result) == 1
    assert "Saved 2 entries" in result[0].text
    assert "11111111" in result[0].text
    assert "22222222" in result[0].text
    assert captured["entries"][0]["workstream_id"] == "ws_1"
    assert captured["entries"][0]["entry_kind"] == "state"


def test_handle_tool_supports_batch_edit(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    captured = {}

    def fake_edit_entries(root, updates):
        captured["updates"] = updates
        return [
            {"id": updates[0]["entry_id"]},
            None,
        ]

    monkeypatch.setattr(
        mcp_server,
        "edit_entries",
        fake_edit_entries,
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_edit",
            {
                "updates": [
                    {"entry_id": "abcd1234", "content": "Updated", "structured": {"goal": "resume"}},
                    {"entry_id": "deadbeef", "section": "project"},
                ]
            },
            FakeTextContent,
        )
    )

    assert len(result) == 1
    assert "Processed 2 updates (1 updated)" in result[0].text
    assert "Updated abcd1234" in result[0].text
    assert "Entry deadbeef not found" in result[0].text
    assert captured["updates"][0]["structured"] == {"goal": "resume"}


def test_handle_tool_supports_batch_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "delete_entries",
        lambda root, entry_ids: [entry_ids[0]],
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_delete",
            {"entry_ids": ["abcd1234", "deadbeef"]},
            FakeTextContent,
        )
    )

    assert len(result) == 1
    assert "Processed 2 deletions (1 deleted)" in result[0].text
    assert "Deleted abcd1234" in result[0].text
    assert "Entry deadbeef not found" in result[0].text


def test_handle_tool_lists_versions(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "list_entry_versions",
        lambda root, entry_id, include_deleted=True: [
            {"version": 1, "section": "project", "tags": ["draft"], "updated_at": "2026-05-22T10:00:00"},
            {"version": 2, "section": "project", "tags": ["draft"], "updated_at": "2026-05-22T10:10:00", "deleted_at": "2026-05-22T10:11:00"},
        ],
    )

    result = asyncio.run(
        mcp_server._handle_tool("rememb_versions", {"entry_id": "abcd1234"}, FakeTextContent)
    )

    assert len(result) == 1
    assert "Versions for abcd1234" in result[0].text
    assert "v2" in result[0].text
    assert "[deleted]" in result[0].text


def test_handle_tool_restores_deleted_or_specific_version(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "restore_deleted_entry",
        lambda root, entry_id: {"id": entry_id, "version": 4},
    )
    monkeypatch.setattr(
        mcp_server,
        "restore_entry_version",
        lambda root, entry_id, version: {"id": entry_id, "version": 5},
    )

    deleted_result = asyncio.run(
        mcp_server._handle_tool("rememb_restore", {"entry_id": "abcd1234"}, FakeTextContent)
    )
    version_result = asyncio.run(
        mcp_server._handle_tool("rememb_restore", {"entry_id": "abcd1234", "version": 2}, FakeTextContent)
    )

    assert "Restored deleted entry abcd1234" in deleted_result[0].text
    assert "Restored abcd1234 to version 2" in version_result[0].text


def test_handle_tool_shows_diff(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "diff_entry_versions",
        lambda root, entry_id, from_version, to_version: {
            "diff": "--- abcd1234@v1\n+++ abcd1234@v2\n@@\n-old\n+new"
        },
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_diff",
            {"entry_id": "abcd1234", "from_version": 1, "to_version": 2},
            FakeTextContent,
        )
    )

    assert len(result) == 1
    assert "Diff abcd1234 v1 -> v2" in result[0].text
    assert "+new" in result[0].text


def test_handle_tool_generates_and_lists_handoffs(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    captured = {}

    def fake_write_handoff(root, goal, **kwargs):
        captured["goal"] = goal
        captured["kwargs"] = kwargs
        return {"id": "abcd1234", "section": "actions", "goal": goal}

    monkeypatch.setattr(
        mcp_server,
        "write_handoff",
        fake_write_handoff,
    )
    monkeypatch.setattr(
        mcp_server,
        "list_handoffs",
        lambda root, limit=None, include_deleted=False: [
            {"id": "abcd1234", "section": "actions", "content": "# Handoff\n\n## Goal\nShip MVP\n\n## Restore Context\nsection=actions\nquery=handoff\ninclude_deleted=false", "tags": ["handoff"]}
        ],
    )

    created = asyncio.run(
        mcp_server._handle_tool(
            "rememb_handoff_generate",
            {"goal": "Ship MVP", "next_steps": ["Write tests."], "workstream_id": "ws_agent", "session_id": "sess_a"},
            FakeTextContent,
        )
    )
    listed = asyncio.run(mcp_server._handle_tool("rememb_handoff_list", {}, FakeTextContent))

    assert "Saved handoff [actions] id=abcd1234" in created[0].text
    assert "Recent handoffs:" in listed[0].text
    assert "goal=Ship MVP" in listed[0].text
    assert captured["kwargs"]["workstream_id"] == "ws_agent"
    assert captured["kwargs"]["session_id"] == "sess_a"


def test_handle_tool_returns_handoff_restore_context(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "list_handoffs",
        lambda root, limit=None, include_deleted=True: [
            {"id": "abcd1234", "section": "actions", "content": "# Handoff\n\n## Goal\nShip MVP\n\n## Related Entries\n- deadbeef@v2\n\n## Restore Context\nsection=actions\nquery=handoff mvp\ninclude_deleted=true", "tags": ["handoff"]}
        ],
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_handoff_restore_context",
            {"entry_id": "abcd1234"},
            FakeTextContent,
        )
    )

    assert "Handoff abcd1234" in result[0].text
    assert "Query: handoff mvp" in result[0].text
    assert "Related entries: deadbeef@v2" in result[0].text


def test_handle_tool_reads_workstream_state(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "get_workstream_state",
        lambda root, workstream_id, session_id=None, include_deleted=False: {
            "workstream_id": workstream_id,
            "session_id": session_id,
            "entry_count": 3,
            "session_count": 2,
            "latest_entry": {"id": "cccc3333", "entry_kind": "decision", "session_id": "sess_b"},
            "latest_handoff": {"id": "bbbb2222", "session_id": "sess_b"},
            "latest_state": {"id": "aaaa1111", "session_id": "sess_a"},
            "sessions": [
                {"session_id": "sess_b", "entry_count": 2, "latest_entry_id": "cccc3333"},
                {"session_id": "sess_a", "entry_count": 1, "latest_entry_id": "aaaa1111"},
            ],
        },
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_workstream_state_get",
            {"workstream_id": "ws_agent"},
            FakeTextContent,
        )
    )

    assert len(result) == 1
    assert "Workstream: ws_agent" in result[0].text
    assert "Entries: 3" in result[0].text
    assert "Latest handoff: bbbb2222" in result[0].text
    assert "- sess_b entries=2 latest=cccc3333" in result[0].text


def test_handle_tool_builds_workstream_resume(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "resume_workstream",
        lambda root, workstream_id, session_id=None, include_deleted=False: {
            "workstream_id": workstream_id,
            "session_id": "sess_b",
            "goal": "Ship workstream tools",
            "summary": "Resume from latest handoff.",
            "latest_entry_id": "cccc3333",
            "latest_entry_kind": "handoff",
            "focus_entry_ids": ["bbbb2222", "aaaa1111", "cccc3333"],
            "current_state": ["store ready"],
            "open_loops": ["expose MCP"],
            "next_steps": ["wire tests"],
            "restore_context": {"section": "actions", "query": "ws_agent", "include_deleted": False},
            "related_entry_ids": ["aaaa1111"],
            "compressed_context": {"essential": ["store ready"], "optional": [], "archived": [], "risky": [], "obsolete": []},
            "what_changed": [{"summary": "Added tests"}],
        },
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_workstream_resume",
            {"workstream_id": "ws_agent"},
            FakeTextContent,
        )
    )

    assert len(result) == 1
    assert "Goal: Ship workstream tools" in result[0].text
    assert "Focus entries: bbbb2222, aaaa1111, cccc3333" in result[0].text
    assert "Current state: store ready" in result[0].text
    assert "Restore context: section=actions query=ws_agent include_deleted=False" in result[0].text
    assert "Compressed context: essential=1" in result[0].text
    assert "What changed: Added tests" in result[0].text


def test_handle_tool_reads_handoff_package_and_review_queue(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "build_handoff_package",
        lambda root, workstream_id, session_id=None, next_goal=None, include_deleted=False: {
            "workstream_id": workstream_id,
            "session_id": session_id,
            "current_goal": "Current goal",
            "next_goal": next_goal or "Next goal",
            "focus_entry_ids": ["aaaa1111"],
            "operational_handoff": {
                "essential_context": ["keep workflow short"],
                "open_loops": ["ship review mode"],
                "next_steps": ["wire queue"],
            },
            "what_changed": [{"summary": "Added review mode"}],
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "list_review_queue",
        lambda root, **kwargs: [
            {"entry_id": "abcd1234", "review_status": "pending", "entry_kind": "decision", "actor_type": "agent", "actor_id": "copilot", "review_reasons": ["agent_generated", "versioned"]}
        ],
    )
    monkeypatch.setattr(
        mcp_server,
        "build_workstream_switch_package",
        lambda root, current_workstream_id, target_workstream_id, **kwargs: {
            "current_workstream_id": current_workstream_id,
            "target_workstream_id": target_workstream_id,
            "state_gap": {"needed_now_but_not_open": ["focus target"], "risky_to_carry": ["stale context"]},
        },
    )

    handoff_package = asyncio.run(
        mcp_server._handle_tool(
            "rememb_handoff_package",
            {"workstream_id": "ws_agent", "next_goal": "Ship review mode"},
            FakeTextContent,
        )
    )
    review_queue = asyncio.run(
        mcp_server._handle_tool(
            "rememb_review_queue",
            {"workstream_id": "ws_agent"},
            FakeTextContent,
        )
    )
    switch_package = asyncio.run(
        mcp_server._handle_tool(
            "rememb_workstream_switch_package",
            {"current_workstream_id": "ws_agent", "target_workstream_id": "ws_other"},
            FakeTextContent,
        )
    )

    assert "Next goal: Ship review mode" in handoff_package[0].text
    assert "Operational handoff:" in handoff_package[0].text
    assert "What changed: Added review mode" in handoff_package[0].text
    assert "Review queue:" in review_queue[0].text
    assert "abcd1234 status=pending kind=decision actor=agent:copilot" in review_queue[0].text
    assert "reasons=agent_generated,versioned" in review_queue[0].text
    assert "Freeze current: ws_agent" in switch_package[0].text
    assert "Resume target: ws_other" in switch_package[0].text


def test_handle_tool_closes_session_with_handoff_and_updates_review(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "close_session_with_handoff",
        lambda root, workstream_id, **kwargs: {
            "review_entry": {"id": "revw1111", "session_id": kwargs.get("session_id") or "sess_a"},
            "handoff_entry": {"id": "hand2222"},
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "update_review_status",
        lambda root, entry_id, review_status, review_notes=None, review_reason=None, validation_notes=None, source_context_entry_ids=None: {"id": entry_id, "structured": {"review_status": review_status}},
    )

    close_result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_execution_close_and_handoff",
            {"workstream_id": "ws_agent", "execution_id": "sess_a", "outcome": "done", "next_goal": "next"},
            FakeTextContent,
        )
    )
    update_result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_review_update",
            {"entry_id": "abcd1234", "review_status": "approved", "review_notes": "ok"},
            FakeTextContent,
        )
    )

    assert "review=revw1111 handoff=hand2222" in close_result[0].text
    assert "Updated review status for abcd1234 -> approved" in update_result[0].text


def test_handle_tool_reads_advanced_review_and_compare_surfaces(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "get_review_session",
        lambda root, workstream_id, session_id, include_deleted=False: {
            "workstream_id": workstream_id,
            "session_id": session_id,
            "operational_status": "awaiting_review",
            "pending_review_count": 2,
            "entry_count": 4,
            "active_decision_ids": ["dec22222"],
            "resume": {"next_execution": {"goal": "Resume ws_agent"}},
            "execution_snapshot": {"inputs": {"source_context_entry_ids": ["ctx11111"]}, "outputs": {"entry_ids": ["out11111", "out22222"]}, "review_result": {"pending_human_validation": 2}},
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "get_review_workstream",
        lambda root, workstream_id, include_deleted=False: {
            "workstream_id": workstream_id,
            "operational_status": "awaiting_review",
            "pending_review_count": 2,
            "sessions": [{"session_id": "sess_a"}, {"session_id": "sess_b"}],
            "resume": {"next_execution": {"goal": "Resume ws_agent"}},
            "review_policy_summary": {"escalate_for_validation": 2, "auto_approve": 0, "auto_dismiss": 0},
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "list_workstream_queue",
        lambda root, status=None, include_deleted=False, limit=None: [
            {"workstream_id": "ws_agent", "operational_status": "awaiting_review", "pending_review_count": 2, "session_count": 2}
        ],
    )
    monkeypatch.setattr(
        mcp_server,
        "compare_sessions",
        lambda root, workstream_id, base_session_id, target_session_id, include_deleted=False: {
            "workstream_id": workstream_id,
            "delta": {"new_open_loops": ["ship compare"], "resolved_open_loops": ["wire filters"], "new_decision_entry_ids": ["dec22222"], "risk_shift": {"base_pending_human_validation": 1, "target_pending_human_validation": 2}},
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "compare_workstreams",
        lambda root, left_workstream_id, right_workstream_id, include_deleted=False: {
            "delta": {
                "operational_status_changed": True,
                "left_only_open_loops": ["ship compare"],
                "right_only_open_loops": ["connect queue"],
            },
            "switch_package": {"state_gap": {"needed_now_but_not_open": ["focus target"]}},
        },
    )

    review_session = asyncio.run(
        mcp_server._handle_tool(
            "rememb_review_execution_get",
            {"workstream_id": "ws_agent", "execution_id": "sess_a"},
            FakeTextContent,
        )
    )
    review_workstream = asyncio.run(
        mcp_server._handle_tool(
            "rememb_review_workstream_get",
            {"workstream_id": "ws_agent"},
            FakeTextContent,
        )
    )
    queue = asyncio.run(
        mcp_server._handle_tool(
            "rememb_workstream_queue",
            {"status": "awaiting_review"},
            FakeTextContent,
        )
    )
    compare_session = asyncio.run(
        mcp_server._handle_tool(
            "rememb_compare_executions",
            {"workstream_id": "ws_agent", "base_execution_id": "sess_a", "target_execution_id": "sess_b"},
            FakeTextContent,
        )
    )
    compare_workstream = asyncio.run(
        mcp_server._handle_tool(
            "rememb_compare_workstreams",
            {"left_workstream_id": "ws_agent", "right_workstream_id": "ws_other"},
            FakeTextContent,
        )
    )

    assert "Review execution anchor: sess_a" in review_session[0].text
    assert "Next execution goal: Resume ws_agent" in review_session[0].text
    assert "Snapshot: inputs=1 outputs=2 pending_human_validation=2" in review_session[0].text
    assert "Active decisions: dec22222" in review_session[0].text
    assert "Review workstream: ws_agent" in review_workstream[0].text
    assert "Execution history: 2" in review_workstream[0].text
    assert "Policy summary: escalate=2 auto_approve=0 auto_dismiss=0" in review_workstream[0].text
    assert "Workstream queue:" in queue[0].text
    assert "ws_agent status=awaiting_review pending_review=2 execution_history=2" in queue[0].text
    assert "New open loops: ship compare" in compare_session[0].text
    assert "New decisions: dec22222" in compare_session[0].text
    assert "Risk shift: base_pending=1 target_pending=2" in compare_session[0].text
    assert "Status changed: true" in compare_workstream[0].text
    assert "Switch target gap: focus target" in compare_workstream[0].text


def test_handle_tool_manages_workstream_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "list_workstreams",
        lambda root, limit=None, include_deleted=False: [{"workstream_id": "ws_agent", "entry_count": 3, "session_count": 1, "goal": "Ship UI"}],
    )
    monkeypatch.setattr(
        mcp_server,
        "open_workstream",
        lambda root, goal, **kwargs: {"workstream_id": kwargs.get("workstream_id") or "ws_agent", "created": True, "entry": {"id": "open1111"}},
    )
    monkeypatch.setattr(
        mcp_server,
        "start_session",
        lambda root, workstream_id, **kwargs: {"id": "sess1111", "session_id": kwargs.get("session_id") or "sess_a"},
    )
    monkeypatch.setattr(
        mcp_server,
        "close_session",
        lambda root, workstream_id, **kwargs: {"id": "close111", "session_id": kwargs.get("session_id") or "sess_a"},
    )

    listed = asyncio.run(mcp_server._handle_tool("rememb_workstream_list", {}, FakeTextContent))
    opened = asyncio.run(
        mcp_server._handle_tool("rememb_workstream_open", {"goal": "Ship UI", "workstream_id": "ws_agent"}, FakeTextContent)
    )
    started = asyncio.run(
        mcp_server._handle_tool("rememb_execution_start", {"workstream_id": "ws_agent", "execution_id": "sess_a"}, FakeTextContent)
    )
    closed = asyncio.run(
        mcp_server._handle_tool(
            "rememb_execution_close",
            {"workstream_id": "ws_agent", "execution_id": "sess_a", "outcome": "done"},
            FakeTextContent,
        )
    )

    assert "Recent workstreams:" in listed[0].text
    assert "ws_agent" in listed[0].text
    assert "Workstream ws_agent created" in opened[0].text
    assert "Started execution anchor sess_a" in started[0].text
    assert "Closed execution anchor sess_a" in closed[0].text


def test_handle_tool_reads_and_writes_structured_handoff(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "write_structured_handoff",
        lambda root, workstream_id, **kwargs: {"id": "hando111", "section": "actions", "workstream_id": workstream_id},
    )
    monkeypatch.setattr(
        mcp_server,
        "read_structured_handoff",
        lambda root, **kwargs: {
            "entry_id": "hando111",
            "workstream_id": kwargs.get("workstream_id"),
            "session_id": "sess_a",
            "goal": "Ship parity",
            "summary": "Everything aligned",
            "next_steps": ["validate"],
            "related_entries": [{"raw": "deadbeef@v2", "entry_id": "deadbeef", "version": 2}],
        },
    )

    created = asyncio.run(
        mcp_server._handle_tool(
            "rememb_handoff_write_structured",
            {"workstream_id": "ws_agent", "goal": "Ship parity"},
            FakeTextContent,
        )
    )
    payload = asyncio.run(
        mcp_server._handle_tool(
            "rememb_handoff_read_structured",
            {"workstream_id": "ws_agent"},
            FakeTextContent,
        )
    )

    assert "Saved structured handoff" in created[0].text
    assert "Handoff entry: hando111" in payload[0].text
    assert "Related entries: deadbeef@v2" in payload[0].text


def test_get_root_uses_global_home_and_auto_initializes(monkeypatch, tmp_path):
    state = {"initialized": False, "init_calls": 0}
    expected_root = Path(tmp_path)

    monkeypatch.setattr(mcp_server, "global_root", lambda: expected_root)

    def fake_is_initialized(root: Path) -> bool:
        assert root == expected_root
        return state["initialized"]

    def fake_init(root: Path, project_name: str = "", global_mode: bool = False):
        assert root == expected_root
        assert project_name == "global"
        assert global_mode is True
        state["initialized"] = True
        state["init_calls"] += 1
        return root / ".rememb"

    monkeypatch.setattr(mcp_server, "is_initialized", fake_is_initialized)
    monkeypatch.setattr(mcp_server, "init", fake_init)
    mcp_server._mcp_context.clear_root_cache()

    resolved = mcp_server._get_root()

    assert resolved == expected_root
    assert state["init_calls"] == 1


def test_handle_tool_lists_local_skills(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "list_skill_definitions",
        lambda: [
            {
                "id": "agent-browser",
                "name": "agent-browser",
                "description": "Browser automation CLI for AI agents.",
                "path": "/tmp/agent-browser/SKILL.md",
                "root": "/tmp",
            }
        ],
    )

    result = asyncio.run(mcp_server._handle_tool("rememb_list_skills", {}, FakeTextContent))

    assert len(result) == 1
    assert "agent-browser" in result[0].text
    assert "/tmp/agent-browser/SKILL.md" in result[0].text


def test_handle_tool_returns_skill_content(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "load_skill_definition",
        lambda skill: {
            "id": "agent-browser",
            "name": "agent-browser",
            "description": "Browser automation CLI for AI agents.",
            "path": "/tmp/agent-browser/SKILL.md",
            "content": "# Skill\nUse this skill for browser automation.",
        }
        if skill == "agent-browser"
        else None,
    )

    result = asyncio.run(
        mcp_server._handle_tool("rememb_use_skill", {"skill": "agent-browser"}, FakeTextContent)
    )

    assert len(result) == 1
    assert "Skill: agent-browser" in result[0].text
    assert "Use this skill for browser automation." in result[0].text


def test_list_skill_definitions_reads_bundled_rememb_skills():
    skills = list_skill_definitions()

    assert any(skill["id"] == "rememb-mcp" for skill in skills)


def test_load_skill_definition_reads_bundled_rememb_skill_content():
    skill = load_skill_definition("rememb-mcp")

    assert skill is not None
    assert skill["id"] == "rememb-mcp"
    assert "Use this skill when working on rememb MCP tools" in skill["content"]