from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

import rememb.mcp_server as mcp_server
from rememb.config import SEARCH_EXCERPT_CHARS
from rememb.mcp_server import _build_tools, configure_mcp_stores
from rememb.mcp_stores import GLOBAL_STORE_ID, normalize_project_root
from rememb.store import delete_entries, edit_entry, read_entries, write_entry
from rememb.utils import list_skill_definitions


@dataclass
class FakeTool:
    name: str
    description: str
    inputSchema: dict


@dataclass
class FakeTextContent:
    type: str
    text: str


EXPECTED_TOOLS = {
    "rememb_list_stores",
    "rememb_get",
    "rememb_recent",
    "rememb_list_tags",
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
    "rememb_list_skills",
    "rememb_use_skill",
}


@pytest.fixture
def handle(monkeypatch: pytest.MonkeyPatch, store: Path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda _store_id=None: store)

    def run(name: str, arguments: dict | None = None) -> str:
        result = asyncio.run(mcp_server._handle_tool(name, arguments or {}, FakeTextContent))
        return result[0].text

    return run


def test_build_tools_exposes_current_contract():
    configure_mcp_stores([])
    by_name = {tool.name: tool for tool in _build_tools(FakeTool)}

    assert set(by_name) == EXPECTED_TOOLS
    assert by_name["rememb_get"].inputSchema["required"] == ["entry_id"]
    assert by_name["rememb_search"].inputSchema["required"] == ["query"]
    assert by_name["rememb_diff"].inputSchema["required"] == ["entry_id", "from_version", "to_version"]
    assert by_name["rememb_use_skill"].inputSchema["required"] == ["skill"]
    assert {"store", "content", "entries"} <= set(by_name["rememb_write"].inputSchema["properties"])
    assert {"store", "entry_id", "updates"} <= set(by_name["rememb_edit"].inputSchema["properties"])
    assert "entry_ids" in by_name["rememb_delete"].inputSchema["properties"]
    assert "store" not in by_name["rememb_list_stores"].inputSchema["properties"]
    assert "store" not in by_name["rememb_list_skills"].inputSchema["properties"]
    assert by_name["rememb_stats"].inputSchema["properties"]["store"]["default"] == GLOBAL_STORE_ID
    assert "short excerpt" in by_name["rememb_search"].description
    assert "0 returns the full body" in by_name["rememb_search"].inputSchema["properties"]["max_chars"]["description"]
    assert str(SEARCH_EXCERPT_CHARS) in by_name["rememb_search"].inputSchema["properties"]["max_chars"]["description"]


def test_handle_read_tools(handle, store: Path):
    entry = write_entry(store, "project", "Tagged note about auth.", ["alpha"])

    assert entry["id"] in handle("rememb_get", {"entry_id": entry["id"]})
    assert "Invalid entry ID" in handle("rememb_get", {"entry_id": "bad"})
    assert "alpha: 1" in handle("rememb_list_tags")
    assert "Tagged note about auth." in handle("rememb_recent")
    assert "Tagged note about auth." in handle("rememb_read")
    assert "Tagged note about auth." in handle("rememb_search", {"query": "auth"})
    assert "Page 0" in handle("rememb_read_page", {"limit": 1})


def test_search_defaults_to_excerpt_and_get_returns_body(handle, store: Path):
    body = "token " + ("alpha " * 80)
    entry = write_entry(store, "project", body, ["search"])

    excerpt = handle("rememb_search", {"query": "token"})
    full = handle("rememb_search", {"query": "token", "max_chars": 0})
    fetched = handle("rememb_get", {"entry_id": entry["id"]})

    assert entry["id"] in excerpt
    assert "score:" in excerpt
    assert "..." in excerpt
    assert body not in excerpt
    assert body in full
    assert body in fetched


def test_handle_write_edit_delete_and_clear(handle, store: Path):
    single = handle("rememb_write", {"content": "Solo note", "section": "project"})
    assert "Saved [project]" in single

    batch = handle(
        "rememb_write",
        {
            "entries": [
                {"content": "First batch", "section": "project", "tags": ["a"]},
                {"content": "Second batch", "section": "actions"},
            ]
        },
    )
    assert "Saved 2 entries" in batch

    first, second, third = read_entries(store)
    edited = handle(
        "rememb_edit",
        {"updates": [{"entry_id": first["id"], "content": "Solo note edited"}, {"entry_id": "deadbeef", "section": "project"}]},
    )
    assert "Processed 2 updates (1 updated)" in edited
    assert first["id"] in handle("rememb_edit", {"entry_id": first["id"], "tags": ["solo"]})

    deleted = handle("rememb_delete", {"entry_ids": [second["id"], "deadbeef"]})
    assert "Processed 2 deletions (1 deleted)" in deleted
    assert third["id"] in handle("rememb_delete", {"entry_id": third["id"]})
    assert "Total entries:" in handle("rememb_stats")
    assert "Cleared" in handle("rememb_clear", {"confirm": True})


def test_handle_versions_restore_diff_and_consolidate(handle, store: Path):
    entry = write_entry(store, "project", "old text", ["keep"])
    edit_entry(store, entry["id"], "new text")
    write_entry(store, "project", "dup text", ["a"], skip_duplicates=False)
    write_entry(store, "project", "dup text", ["b"], skip_duplicates=False)

    assert f"Versions for {entry['id']}" in handle("rememb_versions", {"entry_id": entry["id"]})
    assert f"Diff {entry['id']} v1 -> v2" in handle(
        "rememb_diff", {"entry_id": entry["id"], "from_version": 1, "to_version": 2}
    )

    delete_entries(store, [entry["id"]])
    assert "Restored deleted entry" in handle("rememb_restore", {"entry_id": entry["id"]})
    assert "Removed 1 duplicate" in handle("rememb_consolidate")


def test_configure_mcp_stores_and_route_by_store(tmp_path: Path):
    project_a = tmp_path / "mavsa"
    project_b = tmp_path / "other"
    project_a.mkdir()
    project_b.mkdir()
    rememb_dir = (tmp_path / "proj" / ".rememb")
    rememb_dir.mkdir(parents=True)

    registry = configure_mcp_stores([project_a, project_b, project_a])
    assert registry.ids() == [GLOBAL_STORE_ID, "mavsa", "other"]
    assert registry.get("mavsa").root == project_a.resolve()
    assert normalize_project_root(rememb_dir) == rememb_dir.parent.resolve()

    configure_mcp_stores([tmp_path / "proj"])
    listed = asyncio.run(mcp_server._handle_tool("rememb_list_stores", {}, FakeTextContent))[0].text
    assert "global" in listed
    assert "proj" in listed

    written = asyncio.run(
        mcp_server._handle_tool(
            "rememb_write",
            {"store": "proj", "content": "Project-only fact", "section": "project", "tags": ["t"]},
            FakeTextContent,
        )
    )[0].text
    assert "[store=proj]" in written
    stats = asyncio.run(mcp_server._handle_tool("rememb_stats", {"store": "proj"}, FakeTextContent))[0].text
    assert "[store=proj]" in stats
    assert "Total entries: 1" in stats

    configure_mcp_stores([])
    missing = asyncio.run(mcp_server._handle_tool("rememb_stats", {"store": "missing"}, FakeTextContent))[0].text
    assert "Unknown store 'missing'" in missing


def test_handle_skills_and_unknown_tool(handle):
    skills = list_skill_definitions()
    assert skills
    listing = handle("rememb_list_skills")
    assert skills[0]["id"] in listing or skills[0]["name"] in listing
    loaded = handle("rememb_use_skill", {"skill": skills[0]["id"]})
    assert "Skill:" in loaded
    assert "Unknown tool" in handle("rememb_nope")
