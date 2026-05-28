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
        "rememb_handoff_package",
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
    assert by_name["rememb_handoff_package"].inputSchema["required"] == ["workstream_id"]
    assert by_name["rememb_workstream_switch_package"].inputSchema["required"] == ["current_workstream_id", "target_workstream_id"]
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


