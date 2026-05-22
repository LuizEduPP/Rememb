"""Web UI server for rememb."""

from __future__ import annotations

import asyncio
import threading
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rememb.config import SEMANTIC_MODEL_CHOICES
from rememb.exceptions import RemembNotInitializedError
from rememb.store import (
    consolidate_entries,
    diff_entry_versions,
    delete_entry,
    edit_entry,
    get_config,
    get_stats,
    init,
    list_entry_versions,
    read_entries_page,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    update_config,
    write_entry,
)
from rememb.utils import (
    global_root,
    is_initialized,
    list_skill_definitions,
    load_skill_definition,
)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="rememb", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── Root resolution ────────────────────────────────────────────────────────────

def _get_root() -> Path:
    """Return the global root, auto-initializing if needed."""
    root = global_root()
    if not is_initialized(root):
        init(root, project_name="global", global_mode=True)
    if not is_initialized(root):
        raise RemembNotInitializedError("Global rememb not initialized.")
    return root


# ── Request / Response models ─────────────────────────────────────────────────

class WriteRequest(BaseModel):
    content: str
    section: str
    tags: list[str] = []
    semantic_scope: str = "global"


class EditRequest(BaseModel):
    content: str | None = None
    section: str | None = None
    tags: list[str] | None = None


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, Any]


class ConsolidateRequest(BaseModel):
    section: str | None = None
    mode: str = "exact"
    similarity_threshold: float = 0.88


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    html_path = _STATIC_DIR / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/api/entries")
async def list_entries(
    section: str | None = Query(None),
    tag: str | None = Query(None),
    include_deleted: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    sort_by: str = Query("recent"),
    descending: bool = Query(True),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    result = await asyncio.to_thread(
        read_entries_page,
        root,
        section,
        tag=tag,
        include_deleted=include_deleted,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        descending=descending,
    )
    return result


@app.post("/api/entries", status_code=201)
async def create_entry(req: WriteRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        entry = await asyncio.to_thread(
            write_entry,
            root,
            req.section,
            req.content,
            req.tags if req.tags else None,
            True,
            req.semantic_scope,
        )
        return {"entry": entry}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/entries/{entry_id}")
async def update_entry(entry_id: str, req: EditRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        entry = await asyncio.to_thread(
            edit_entry,
            root,
            entry_id,
            req.content,
            req.section,
            req.tags,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/entries/{entry_id}", status_code=204)
async def remove_entry(entry_id: str) -> None:
    root = await asyncio.to_thread(_get_root)
    try:
        deleted = await asyncio.to_thread(delete_entry, root, entry_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Entry not found.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/entries/{entry_id}/restore")
async def restore_deleted_entry_endpoint(entry_id: str) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        entry = await asyncio.to_thread(restore_deleted_entry, root, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Deleted entry not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/entries/{entry_id}/versions")
async def entry_versions(entry_id: str, include_deleted: bool = Query(True)) -> dict:
    root = await asyncio.to_thread(_get_root)
    versions = await asyncio.to_thread(list_entry_versions, root, entry_id, include_deleted=include_deleted)
    if not versions:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"versions": versions}


@app.post("/api/entries/{entry_id}/versions/{version}/restore")
async def restore_entry_version_endpoint(entry_id: str, version: int) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        entry = await asyncio.to_thread(restore_entry_version, root, entry_id, version)
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry or version not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/entries/{entry_id}/diff")
async def entry_diff(entry_id: str, from_version: int = Query(..., ge=1), to_version: int = Query(..., ge=1)) -> dict:
    root = await asyncio.to_thread(_get_root)
    diff = await asyncio.to_thread(diff_entry_versions, root, entry_id, from_version, to_version)
    if diff is None:
        raise HTTPException(status_code=404, detail="Entry or version not found.")
    return diff


@app.get("/api/search")
async def search(
    q: str = Query(""),
    section: str | None = Query(None),
    tag: str | None = Query(None),
    include_deleted: bool = Query(False),
    top_k: int = Query(20, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    results = await asyncio.to_thread(
        search_entries,
        root,
        q,
        top_k,
        section,
        tag,
        include_deleted=include_deleted,
    )
    return {"results": results}


@app.get("/api/stats")
async def stats_endpoint() -> dict:
    root = await asyncio.to_thread(_get_root)
    raw = await asyncio.to_thread(get_stats, root)
    return {
        "total_entries": raw["total"],
        "deleted_entries": raw.get("deleted_total", 0),
        "sections": raw["by_section"],
        "store_size_kb": raw["size_kb"],
        "oldest": raw.get("oldest", "—"),
        "newest": raw.get("newest", "—"),
    }


@app.get("/api/config")
async def config_get() -> dict:
    root = await asyncio.to_thread(_get_root)
    return await asyncio.to_thread(get_config, root)


@app.get("/api/models")
async def models_endpoint() -> dict:
    return {"models": SEMANTIC_MODEL_CHOICES}


@app.get("/api/skills")
async def skills_endpoint() -> dict:
    skills = await asyncio.to_thread(list_skill_definitions)
    return {"skills": skills}


@app.get("/api/skills/{skill_id}")
async def skill_detail_endpoint(skill_id: str) -> dict:
    skill = await asyncio.to_thread(load_skill_definition, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return {"skill": skill}


@app.put("/api/config")
async def config_update(req: ConfigUpdateRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        updated = await asyncio.to_thread(update_config, root, req.updates)
        return updated
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/consolidate")
async def consolidate(req: ConsolidateRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        result = await asyncio.to_thread(
            consolidate_entries,
            root,
            req.section,
            req.mode,
            req.similarity_threshold,
        )
        return {"result": result}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Entry point ───────────────────────────────────────────────────────────────

def run_web(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the rememb web UI server."""
    import uvicorn

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
