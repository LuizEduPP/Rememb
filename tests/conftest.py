from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rememb.store import init
from rememb.web import app, deps


@pytest.fixture
def store(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    init(root)
    return root


@pytest.fixture
def web_store(monkeypatch: pytest.MonkeyPatch, store: Path) -> Path:
    monkeypatch.setattr(deps, "get_root", lambda: store)
    return store


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
