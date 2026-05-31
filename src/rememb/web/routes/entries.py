"""Entry and search API routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from rememb.store import (
    delete_entry,
    diff_entry_versions,
    edit_entry,
    list_entry_versions,
    read_entries_page,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    write_entry,
)
from rememb.web import deps
from rememb.web.deps import raise_http_error
from rememb.web.schemas import EditRequest, WriteRequest

router = APIRouter()


@router.get("/api/entries")
async def list_entries(
    section: str | None = Query(None),
    tag: str | None = Query(None),
    include_deleted: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    sort_by: str = Query("recent"),
    descending: bool = Query(True),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
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


@router.post("/api/entries", status_code=201)
async def create_entry(req: WriteRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            write_entry,
            root,
            req.section,
            req.content,
            req.tags if req.tags else None,
            True,
            req.semantic_scope,
            workstream_id=req.workstream_id,
            session_id=req.session_id,
        )
        return {"entry": entry}
    except Exception as exc:
        raise_http_error(exc)


@router.put("/api/entries/{entry_id}")
async def update_entry(entry_id: str, req: EditRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            edit_entry,
            root,
            entry_id,
            req.content,
            req.section,
            req.tags,
            workstream_id=req.workstream_id,
            session_id=req.session_id,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.delete("/api/entries/{entry_id}", status_code=204)
async def remove_entry(entry_id: str) -> None:
    root = await asyncio.to_thread(deps.get_root)
    try:
        deleted = await asyncio.to_thread(delete_entry, root, entry_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Entry not found.")
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc, default_status=500)


@router.post("/api/entries/{entry_id}/restore")
async def restore_deleted_entry_endpoint(entry_id: str) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(restore_deleted_entry, root, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Deleted entry not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/entries/{entry_id}/versions")
async def entry_versions(entry_id: str, include_deleted: bool = Query(True)) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    versions = await asyncio.to_thread(list_entry_versions, root, entry_id, include_deleted=include_deleted)
    if not versions:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"versions": versions}


@router.post("/api/entries/{entry_id}/versions/{version}/restore")
async def restore_entry_version_endpoint(entry_id: str, version: int) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(restore_entry_version, root, entry_id, version)
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry or version not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/entries/{entry_id}/diff")
async def entry_diff(entry_id: str, from_version: int = Query(..., ge=1), to_version: int = Query(..., ge=1)) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    diff = await asyncio.to_thread(diff_entry_versions, root, entry_id, from_version, to_version)
    if diff is None:
        raise HTTPException(status_code=404, detail="Entry or version not found.")
    return diff


@router.get("/api/search")
async def search(
    q: str = Query(""),
    section: str | None = Query(None),
    tag: str | None = Query(None),
    include_deleted: bool = Query(False),
    top_k: int = Query(20, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
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
