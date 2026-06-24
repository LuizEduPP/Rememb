from __future__ import annotations

import asyncio

import rememb.mcp_server as mcp_server
from rememb.store import (
    edit_entry,
    get_entry,
    init,
    list_entry_tags,
    read_recent_entries,
    write_entry,
)
from tests.test_mcp_server import FakeTextContent


def test_get_entry_and_tags(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    entry = write_entry(root, "project", "Alpha note about auth.", ["auth", "alpha"])
    write_entry(root, "actions", "Beta follow-up.", ["auth"])

    fetched = get_entry(root, entry["id"])
    tags = list_entry_tags(root)

    assert fetched is not None
    assert fetched["id"] == entry["id"]
    assert {item["tag"] for item in tags} >= {"auth", "alpha"}


def test_read_recent_entries_orders_by_update_time(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    first = write_entry(root, "project", "First")
    write_entry(root, "project", "Second")
    edit_entry(root, first["id"], "First updated")

    recent = read_recent_entries(root, limit=2)

    assert recent[0]["id"] == first["id"]


def test_handle_tool_get_and_list_tags(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_root", lambda: tmp_path)
    init(tmp_path)
    entry = write_entry(tmp_path, "project", "Tagged note.", ["alpha"])

    get_result = asyncio.run(
        mcp_server._handle_tool("rememb_get", {"entry_id": entry["id"]}, FakeTextContent)
    )
    tags_result = asyncio.run(
        mcp_server._handle_tool("rememb_list_tags", {}, FakeTextContent)
    )

    assert entry["id"] in get_result[0].text
    assert "alpha: 1" in tags_result[0].text
