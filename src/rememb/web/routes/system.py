"""System, config, stats, skills, and consolidate API routes."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import Response

from rememb import __version__
from rememb.config import DEFAULT_STORAGE_BACKEND
from rememb.helpers import _config_path, _json_text, _meta_path
from rememb.store import consolidate_entries, export_entries, get_config, get_stats, update_config
from rememb.utils import (
    _entries_db_path,
    _entries_path,
    list_skill_definitions,
    load_skill_definition,
    load_skill_file,
)
from rememb.web import deps
from rememb.web.deps import call_store, missing_or_404, raise_http_error
from rememb.web.schemas import ConfigUpdateRequest, ConsolidateRequest

router = APIRouter()


def _storage_files(root: Path) -> list[str]:
    candidates = [
        _entries_path(root),
        _entries_db_path(root),
        _config_path(root),
        _meta_path(root),
    ]
    return [path.name for path in candidates if path.exists()]


def _stats_payload(raw: dict) -> dict:
    return {
        "total_entries": raw["total"],
        "deleted_entries": raw.get("deleted_total", 0),
        "sections": raw["by_section"],
        "store_size_kb": raw["size_kb"],
        "storage_backend": raw.get("storage_backend", DEFAULT_STORAGE_BACKEND),
        "oldest": raw.get("oldest", "—"),
        "newest": raw.get("newest", "—"),
    }


@router.get("/api/stats")
async def stats_endpoint() -> dict:
    return _stats_payload(await call_store(get_stats))


@router.get("/api/config")
async def config_get() -> dict:
    return await call_store(get_config)


@router.put("/api/config")
async def config_update(req: ConfigUpdateRequest) -> dict:
    return await call_store(update_config, req.updates)


@router.get("/api/skills")
async def skills_endpoint() -> dict:
    skills = await asyncio.to_thread(list_skill_definitions)
    return {"skills": skills}


@router.get("/api/skills/{skill_id}")
async def skill_detail_endpoint(skill_id: str) -> dict:
    skill = await asyncio.to_thread(load_skill_definition, skill_id)
    return {"skill": missing_or_404(skill, detail="Skill not found.")}


@router.get("/api/skills/{skill_id}/file")
async def skill_file_endpoint(skill_id: str, path: str = Query(...)) -> dict:
    try:
        skill_file = await asyncio.to_thread(load_skill_file, skill_id, path)
    except Exception as exc:
        raise_http_error(exc)
    return {"file": missing_or_404(skill_file, detail="Skill file not found.")}


@router.post("/api/consolidate")
async def consolidate(req: ConsolidateRequest) -> dict:
    return {"result": await call_store(consolidate_entries, req.section)}


@router.get("/api/system/info")
async def system_info_endpoint() -> dict:
    root = await asyncio.to_thread(deps.get_root)
    raw = await asyncio.to_thread(get_stats, root)
    skills = await asyncio.to_thread(list_skill_definitions)
    return {
        "storage_backend": raw.get("storage_backend", DEFAULT_STORAGE_BACKEND),
        "storage_files": _storage_files(root),
        "skills_count": len(skills),
        "version": __version__,
    }


def _export_filename(payload: dict, entry_id: str | None) -> str:
    stamp = re.sub(r"[^0-9T]", "", str(payload.get("exported_at", "")))[:15]
    versions_suffix = "with-versions" if payload.get("include_versions") else "current"
    if entry_id:
        return f"rememb-{entry_id}-{versions_suffix}.json"
    return f"rememb-export-{stamp or 'now'}-{versions_suffix}.json"


@router.get("/api/export")
async def export_endpoint(
    entry_id: str | None = Query(None),
    include_versions: bool = Query(True),
    include_deleted: bool = Query(False),
) -> Response:
    payload = await call_store(
        export_entries,
        entry_id=entry_id,
        include_versions=include_versions,
        include_deleted=include_deleted,
        not_found="Entry not found.",
    )
    filename = _export_filename(payload, entry_id)
    return Response(
        content=_json_text(payload, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
