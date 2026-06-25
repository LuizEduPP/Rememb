"""System, config, stats, skills, and consolidate API routes."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

from rememb import __version__
from rememb.config import SEMANTIC_MODEL_CHOICES
from rememb.store import consolidate_entries, get_config, get_stats, update_config
from rememb.utils import (
    _config_path,
    _entries_db_path,
    _entries_path,
    _meta_path,
    _rememb_path,
    list_skill_definitions,
    load_skill_definition,
)
from rememb.web import deps
from rememb.web.deps import raise_http_error
from rememb.web.schemas import ConfigUpdateRequest, ConsolidateRequest

router = APIRouter()


def _storage_files(root: Path) -> list[str]:
    candidates = [
        _entries_path(root),
        _entries_db_path(root),
        _config_path(root),
        _meta_path(root),
        _rememb_path(root) / "embeddings.npy",
        _rememb_path(root) / "embeddings.hash",
    ]
    return [path.name for path in candidates if path.exists()]


@router.get("/api/stats")
async def stats_endpoint() -> dict:
    root = await asyncio.to_thread(deps.get_root)
    raw = await asyncio.to_thread(get_stats, root)
    return {
        "total_entries": raw["total"],
        "deleted_entries": raw.get("deleted_total", 0),
        "sections": raw["by_section"],
        "store_size_kb": raw["size_kb"],
        "storage_backend": raw.get("storage_backend", "json"),
        "oldest": raw.get("oldest", "—"),
        "newest": raw.get("newest", "—"),
    }


@router.get("/api/config")
async def config_get() -> dict:
    root = await asyncio.to_thread(deps.get_root)
    return await asyncio.to_thread(get_config, root)


@router.put("/api/config")
async def config_update(req: ConfigUpdateRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        updated = await asyncio.to_thread(update_config, root, req.updates)
        return updated
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/models")
async def models_endpoint() -> dict:
    return {"models": SEMANTIC_MODEL_CHOICES}


@router.get("/api/skills")
async def skills_endpoint() -> dict:
    skills = await asyncio.to_thread(list_skill_definitions)
    return {"skills": skills}


@router.get("/api/skills/{skill_id}")
async def skill_detail_endpoint(skill_id: str) -> dict:
    skill = await asyncio.to_thread(load_skill_definition, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return {"skill": skill}


@router.post("/api/consolidate")
async def consolidate(req: ConsolidateRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
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
        raise_http_error(exc)


@router.get("/api/system/info")
async def system_info_endpoint() -> dict:
    root = await asyncio.to_thread(deps.get_root)
    raw = await asyncio.to_thread(get_stats, root)
    skills = await asyncio.to_thread(list_skill_definitions)
    return {
        "storage_backend": raw.get("storage_backend", "json"),
        "storage_files": _storage_files(root),
        "skills_count": len(skills),
        "version": __version__,
    }
