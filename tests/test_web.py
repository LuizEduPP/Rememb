from __future__ import annotations

from fastapi.testclient import TestClient

import rememb.web as web
from rememb.web import deps
from rememb.store import init, write_entry


client = TestClient(web.app)


def test_static_assets_ship_with_package():
    from rememb.web.app import _STATIC_DIR

    for name in ("index.html", "style.css", "app.js", "logo.png"):
        path = _STATIC_DIR / name
        assert path.is_file(), f"missing static asset: {name} ({path})"


def test_index_exposes_deleted_and_history_controls():
    response = client.get("/")

    assert response.status_code == 200
    assert "{{STYLE_VERSION}}" not in response.text
    assert "{{APP_VERSION}}" not in response.text
    assert "style.css?v=" in response.text
    assert "app.js?v=" in response.text
    assert response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"
    assert "Show deleted" in response.text
    assert "/static/app.js" in response.text

    app_js = client.get("/static/app.js")
    assert app_js.status_code == 200
    script = app_js.text
    assert "Version history" in script
    assert "Side-by-side diff" in script
    assert "/api/entries/" in script
    assert "/api/export" in script
    assert "Export memory" in script
    assert "Include version history" in script
    assert "renderMarkdownTable" in script
    assert "parseCollapsedMarkdownTable" in script
    assert "isMarkdownTableSeparator" in script
    assert "table-wrap" in script
    assert "Overview" in response.text
    assert "Recent memory" in response.text
    assert "View all" in response.text
    assert "Storage backend" in script
    assert "Save settings" in script
    assert "No bundled skills found" in script
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


def test_export_endpoint_all_and_single(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    first = write_entry(root, "project", "Exportable alpha", ["export"])
    second = write_entry(root, "user", "Exportable beta", ["export"])
    client.put(f"/api/entries/{first['id']}", json={"content": "Exportable alpha edited"})
    client.delete(f"/api/entries/{second['id']}")

    all_current = client.get("/api/export", params={"include_versions": False, "include_deleted": False})
    assert all_current.status_code == 200
    assert "attachment" in all_current.headers.get("content-disposition", "")
    all_payload = all_current.json()
    assert all_payload["format"] == "rememb-export"
    assert all_payload["include_versions"] is False
    assert all_payload["entry_count"] == 1
    assert all_payload["entries"][0]["id"] == first["id"]
    assert "history" not in all_payload["entries"][0]

    all_versions = client.get("/api/export", params={"include_versions": True, "include_deleted": True})
    assert all_versions.status_code == 200
    versions_payload = all_versions.json()
    assert versions_payload["entry_count"] == 2
    by_id = {entry["id"]: entry for entry in versions_payload["entries"]}
    assert "history" in by_id[first["id"]]
    assert len(by_id[first["id"]]["history"]) >= 1
    assert by_id[second["id"]].get("deleted_at")

    single = client.get(
        "/api/export",
        params={"entry_id": first["id"], "include_versions": False},
    )
    assert single.status_code == 200
    single_payload = single.json()
    assert single_payload["entry_count"] == 1
    assert single_payload["entries"][0]["content"] == "Exportable alpha edited"
    assert "history" not in single_payload["entries"][0]
    assert first["id"] in single.headers.get("content-disposition", "")

    missing = client.get("/api/export", params={"entry_id": "deadbeef"})
    assert missing.status_code == 404
