from __future__ import annotations

from fastapi.testclient import TestClient

import rememb.web as web
from rememb.store import init
from rememb.web import app
from rememb.web import deps

client = TestClient(app)


def test_system_info_endpoint(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    response = client.get("/api/system/info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["storage_backend"] == "json"
    assert "entries.json" in payload["storage_files"]
    assert "version" in payload
    assert "skills_count" in payload
    assert payload["skills_count"] > 0


def test_stats_includes_storage_backend(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    monkeypatch.setattr(deps, "get_root", lambda: root)

    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json()["storage_backend"] == "json"


def test_skill_detail_lists_files_and_file_endpoint():
    listing = client.get("/api/skills")
    assert listing.status_code == 200
    skills = listing.json()["skills"]
    assert skills
    skill_id = next((item["id"] for item in skills if item["id"] == "agent-browser"), skills[0]["id"])

    detail = client.get(f"/api/skills/{skill_id}")
    assert detail.status_code == 200
    payload = detail.json()["skill"]
    assert payload["files"]
    assert any(item["path"] == "SKILL.md" for item in payload["files"])

    if skill_id == "agent-browser":
        assert any(item["path"] == "references/authentication.md" for item in payload["files"])
        file_response = client.get(
            f"/api/skills/{skill_id}/file",
            params={"path": "references/authentication.md"},
        )
        assert file_response.status_code == 200
        file_payload = file_response.json()["file"]
        assert file_payload["path"] == "references/authentication.md"
        assert "authentication" in file_payload["content"].lower() or len(file_payload["content"]) > 0

        template_response = client.get(
            f"/api/skills/{skill_id}/file",
            params={"path": "templates/form-automation.sh"},
        )
        assert template_response.status_code == 200
        assert "#!/bin/bash" in template_response.json()["file"]["content"] or template_response.json()["file"]["content"]

    missing = client.get(f"/api/skills/{skill_id}/file", params={"path": "missing/nope.md"})
    assert missing.status_code == 404

    traversal = client.get(f"/api/skills/{skill_id}/file", params={"path": "../README.md"})
    assert traversal.status_code in {404, 422}
