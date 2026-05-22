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
    assert "updates" in by_name["rememb_edit"].inputSchema["properties"]
    assert "entry_ids" in by_name["rememb_delete"].inputSchema["properties"]
    assert by_name["rememb_use_skill"].inputSchema["required"] == ["skill"]


def test_handle_tool_supports_batch_write(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "write_entries",
        lambda root, entries, skip_duplicates, semantic_scope: [
            {"id": "11111111", "section": entries[0]["section"]},
            {"id": "22222222", "section": entries[1]["section"]},
        ],
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_write",
            {
                "entries": [
                    {"content": "First", "section": "project", "tags": ["a"]},
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


def test_handle_tool_supports_batch_edit(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "edit_entries",
        lambda root, updates: [
            {"id": updates[0]["entry_id"]},
            None,
        ],
    )

    result = asyncio.run(
        mcp_server._handle_tool(
            "rememb_edit",
            {
                "updates": [
                    {"entry_id": "abcd1234", "content": "Updated"},
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