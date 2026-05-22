from __future__ import annotations

from fastapi.testclient import TestClient

import rememb.web as web
from rememb.store import init, write_entry


client = TestClient(web.app)


def test_index_exposes_deleted_and_history_controls():
    response = client.get("/")

    assert response.status_code == 200
    assert "Show deleted" in response.text
    assert "Version history" in response.text
    assert "Timeline" in response.text
    assert "Side-by-side diff" in response.text
    assert "Use as from" in response.text
    assert "Use as to" in response.text
    assert "current vs previous" in response.text
    assert "/api/entries/" in response.text


def test_entries_endpoint_hides_deleted_by_default(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(web, "_get_root", lambda: root)

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
    monkeypatch.setattr(web, "_get_root", lambda: root)

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
