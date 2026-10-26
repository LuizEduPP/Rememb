"""Entry and search API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from rememb.config import DEFAULT_ENTRY_BATCH_SIZE
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
from rememb.web.deps import call_store
from rememb.web.schemas import EditRequest, WriteRequest

router = APIRouter()


@router.get("/api/entries")
async def list_entries(
    section: str | None = Query(None),
    tag: str | None = Query(None),
    include_deleted: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_ENTRY_BATCH_SIZE, ge=1, le=100),
    sort_by: str = Query("recent"),
    descending: bool = Query(True),
) -> dict:
    return await call_store(
        read_entries_page,
        section,
        tag=tag,
        include_deleted=include_deleted,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        descending=descending,
    )


@router.post("/api/entries", status_code=201)
async def create_entry(req: WriteRequest) -> dict:
    entry = await call_store(
        write_entry,
        req.section,
        req.content,
        req.tags if req.tags else None,
    )
    return {"entry": entry}


@router.put("/api/entries/{entry_id}")
async def update_entry(entry_id: str, req: EditRequest) -> dict:
    entry = await call_store(
        edit_entry,
        entry_id,
        req.content,
        req.section,
        req.tags,
        not_found="Entry not found.",
    )
    return {"entry": entry}


@router.delete("/api/entries/{entry_id}", status_code=204)
async def remove_entry(entry_id: str) -> None:
    await call_store(
        delete_entry,
        entry_id,
        default_status=500,
        not_found="Entry not found.",
        missing=False,
    )


@router.post("/api/entries/{entry_id}/restore")
async def restore_deleted_entry_endpoint(entry_id: str) -> dict:
    entry = await call_store(
        restore_deleted_entry,
        entry_id,
        not_found="Deleted entry not found.",
    )
    return {"entry": entry}


@router.get("/api/entries/{entry_id}/versions")
async def entry_versions(entry_id: str, include_deleted: bool = Query(True)) -> dict:
    versions = await call_store(
        list_entry_versions,
        entry_id,
        include_deleted=include_deleted,
        not_found="Entry not found.",
        missing=[],
    )
    return {"versions": versions}


@router.post("/api/entries/{entry_id}/versions/{version}/restore")
async def restore_entry_version_endpoint(entry_id: str, version: int) -> dict:
    entry = await call_store(
        restore_entry_version,
        entry_id,
        version,
        not_found="Entry or version not found.",
    )
    return {"entry": entry}


@router.get("/api/entries/{entry_id}/diff")
async def entry_diff(entry_id: str, from_version: int = Query(..., ge=1), to_version: int = Query(..., ge=1)) -> dict:
    return await call_store(
        diff_entry_versions,
        entry_id,
        from_version,
        to_version,
        not_found="Entry or version not found.",
    )


@router.get("/api/search")
async def search(
    q: str = Query(""),
    section: str | None = Query(None),
    tag: str | None = Query(None),
    include_deleted: bool = Query(False),
    top_k: int = Query(20, ge=1, le=100),
) -> dict:
    results = await call_store(
        search_entries,
        q,
        top_k,
        section,
        tag,
        include_deleted=include_deleted,
    )
    return {"results": results}
