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
    assert "section" in by_name["rememb_read"].inputSchema["properties"]
    assert "max_chars" in by_name["rememb_read"].inputSchema["properties"]
    assert by_name["rememb_read_page"].inputSchema["properties"]["offset"]["default"] == 0
    assert by_name["rememb_read_page"].inputSchema["properties"]["summary_only"]["default"] is True
    assert "section" in by_name["rememb_search"].inputSchema["properties"]
    assert "summary_only" in by_name["rememb_search"].inputSchema["properties"]
    assert by_name["rememb_use_skill"].inputSchema["required"] == ["skill"]


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