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
