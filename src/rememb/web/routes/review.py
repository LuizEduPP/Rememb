"""Review API routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from rememb.store import (
    get_review_session,
    get_review_workstream,
    list_review_queue,
    update_review_status,
)
from rememb.web import deps
from rememb.web.deps import raise_http_error
from rememb.web.schemas import ReviewStatusRequest

router = APIRouter()


@router.get("/api/review")
async def review_queue_endpoint(
    workstream_id: str | None = Query(None),
    session_id: str | None = Query(None),
    actor_type: str | None = Query(None),
    actor_id: str | None = Query(None),
    entry_kind: str | None = Query(None),
    review_status: str | None = Query(None),
    include_deleted: bool = Query(False),
    pending_only: bool = Query(True),
    limit: int | None = Query(None, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        items = await asyncio.to_thread(
            list_review_queue,
            root,
            workstream_id=workstream_id,
            session_id=session_id,
            actor_type=actor_type,
            actor_id=actor_id,
            entry_kind=entry_kind,
            review_status=review_status,
            include_deleted=include_deleted,
            pending_only=pending_only,
            limit=limit,
        )
        return {"items": items}
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/review/workstreams/{workstream_id}")
async def review_workstream_endpoint(workstream_id: str, include_deleted: bool = Query(False)) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            get_review_workstream,
            root,
            workstream_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/review/workstreams/{workstream_id}/executions/{execution_id}")
async def review_execution_endpoint(workstream_id: str, execution_id: str, include_deleted: bool = Query(False)) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            get_review_session,
            root,
            workstream_id,
            execution_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Execution anchor not found.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/review/{entry_id}")
async def review_status_endpoint(entry_id: str, req: ReviewStatusRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            update_review_status,
            root,
            entry_id,
            req.review_status,
            review_notes=req.review_notes,
            review_reason=req.review_reason,
            validation_notes=req.validation_notes,
            source_context_entry_ids=req.source_context_entry_ids,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)
