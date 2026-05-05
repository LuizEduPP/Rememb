from __future__ import annotations

from dataclasses import dataclass

from rememb.mcp_server import _build_tools


@dataclass
class FakeTool:
    name: str
    description: str
    inputSchema: dict


def test_build_tools_exposes_expected_public_contract():
    tools = _build_tools(FakeTool)
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {
        "rememb_read",
        "rememb_search",
        "rememb_write",
        "rememb_edit",
        "rememb_delete",
        "rememb_clear",
        "rememb_stats",
        "rememb_consolidate",
        "rememb_init",
    }
    assert by_name["rememb_search"].inputSchema["required"] == ["query"]
    assert by_name["rememb_write"].inputSchema["properties"]["semantic_scope"]["default"] == "global"
    assert "section" in by_name["rememb_read"].inputSchema["properties"]