from __future__ import annotations

from pathlib import Path

from rememb.store import write_entry
from rememb.web.app import _STATIC_DIR


def test_index_assets_and_offline_shell(client):
    for name in ("index.html", "style.css", "app.js", "logo.png"):
        assert (_STATIC_DIR / name).is_file(), name

    response = client.get("/")
    assert response.status_code == 200
    assert "{{STYLE_VERSION}}" not in response.text
    assert "style.css?v=" in response.text
    assert response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"
    assert "Show deleted" in response.text
    assert "Skills" in response.text
    assert "https://cdn.tailwindcss.com" not in response.text
    assert "https://fonts.googleapis.com" not in response.text

    script = client.get("/static/app.js").text
    assert "Version history" in script
    assert "/api/export" in script
    assert "Storage backend" in script
    assert "/api/skills/" in script


def test_entries_hide_deleted_and_support_history(client, web_store: Path):
    created = client.post(
        "/api/entries",
        json={"content": "line one\nline two", "section": "project", "tags": ["draft"]},
    ).json()["entry"]
    client.put(f"/api/entries/{created['id']}", json={"content": "line one\nline three", "tags": ["released"]})
    live = write_entry(web_store, "project", "Still active", ["alpha"])
    client.delete(f"/api/entries/{created['id']}")

    visible = client.get("/api/entries").json()["items"]
    hidden = client.get("/api/entries", params={"include_deleted": True}).json()["items"]
    versions = client.get(f"/api/entries/{created['id']}/versions").json()["versions"]
    restored = client.post(f"/api/entries/{created['id']}/restore").json()["entry"]
    previous = client.post(f"/api/entries/{created['id']}/versions/1/restore").json()["entry"]

    assert [item["id"] for item in visible] == [live["id"]]
    assert {item["id"] for item in hidden} == {created["id"], live["id"]}
    assert [version["version"] for version in versions] == [1, 2, 3]
    assert restored["version"] == 4
    assert previous["content"] == "line one\nline two"
    assert client.get(f"/api/entries/{created['id']}/diff", params={"from_version": 1, "to_version": 2}).status_code == 200
    assert client.put(f"/api/entries/{'deadbeef'}", json={"content": "nope"}).status_code == 404


def test_export_config_consolidate_and_system(client, web_store: Path):
    first = write_entry(web_store, "project", "Same text", ["a"], skip_duplicates=False)
    write_entry(web_store, "project", "Same text", ["b"], skip_duplicates=False)

    exported = client.get("/api/export", params={"include_versions": False})
    assert exported.status_code == 200
    assert "attachment" in exported.headers.get("content-disposition", "")
    assert exported.json()["format"] == "rememb-export"
    assert client.get("/api/export", params={"entry_id": "deadbeef"}).status_code == 404

    info = client.get("/api/system/info").json()
    stats = client.get("/api/stats").json()
    assert info["storage_backend"] == "json"
    assert "entries.json" in info["storage_files"]
    assert stats["storage_backend"] == "json"
    assert stats["total_entries"] == 2

    config = client.get("/api/config").json()
    assert config["storage_backend"] == "json"
    updated = client.put("/api/config", json={"updates": {"max_tags_per_entry": 12}})
    assert updated.status_code == 200
    assert updated.json()["max_tags_per_entry"] == 12

    consolidated = client.post("/api/consolidate", json={"section": "project"})
    assert consolidated.status_code == 200
    assert consolidated.json()["result"]["removed_count"] == 1
    assert client.get("/api/stats").json()["total_entries"] == 1
    assert first["section"] == "project"


def test_skill_routes(client):
    listing = client.get("/api/skills")
    assert listing.status_code == 200
    skills = listing.json()["skills"]
    assert skills
    skill_id = next((item["id"] for item in skills if item["id"] == "agent-browser"), skills[0]["id"])

    detail = client.get(f"/api/skills/{skill_id}").json()["skill"]
    assert any(item["path"] == "SKILL.md" for item in detail["files"])
    assert client.get(f"/api/skills/{skill_id}/file", params={"path": "missing/nope.md"}).status_code == 404
    assert client.get(f"/api/skills/{skill_id}/file", params={"path": "../README.md"}).status_code in {404, 422}

    if skill_id == "agent-browser":
        file_response = client.get(
            f"/api/skills/{skill_id}/file",
            params={"path": "references/authentication.md"},
        )
        assert file_response.status_code == 200
        assert file_response.json()["file"]["path"] == "references/authentication.md"
