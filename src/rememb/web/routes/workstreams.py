"""Workstream API routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from rememb.store import (
    build_handoff_package,
    build_workstream_switch_package,
    close_session,
    close_session_with_handoff,
    compare_sessions,
    compare_workstreams,
    get_workstream_state,
    list_workstream_queue,
    list_workstreams,
    open_workstream,
    read_structured_handoff,
    resume_workstream,
    start_session,
    update_workstream_state,
    write_structured_handoff,
)
from rememb.web import deps
from rememb.web.deps import raise_http_error
from rememb.web.schemas import (
    SessionCloseAndHandoffRequest,
    SessionCloseRequest,
    SessionStartRequest,
    StructuredHandoffRequest,
    WorkstreamOpenRequest,
    WorkstreamStateUpdateRequest,
)

router = APIRouter()


@router.get("/api/workstreams")
async def workstream_list_endpoint(
    include_deleted: bool = Query(False),
    limit: int | None = Query(None, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        items = await asyncio.to_thread(list_workstreams, root, limit=limit, include_deleted=include_deleted)
        return {"items": items}
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/workstreams/open", status_code=201)
async def workstream_open_endpoint(req: WorkstreamOpenRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        result = await asyncio.to_thread(
            open_workstream,
            root,
            req.goal,
            workstream_id=req.workstream_id,
            summary=req.summary,
            tags=req.tags,
        )
        return result
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/{workstream_id}/state")
async def workstream_state_endpoint(
    workstream_id: str,
    execution_id: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        state = await asyncio.to_thread(
            get_workstream_state,
            root,
            workstream_id,
            session_id=execution_id,
            include_deleted=include_deleted,
        )
        if state is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return state
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/{workstream_id}/resume")
async def workstream_resume_endpoint(
    workstream_id: str,
    execution_id: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        resume = await asyncio.to_thread(
            resume_workstream,
            root,
            workstream_id,
            session_id=execution_id,
            include_deleted=include_deleted,
        )
        if resume is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return resume
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/workstreams/{workstream_id}/state")
async def workstream_state_update_endpoint(workstream_id: str, req: WorkstreamStateUpdateRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            update_workstream_state,
            root,
            workstream_id,
            session_id=req.session_id,
            goal=req.goal,
            summary=req.summary,
            current_state=req.current_state,
            decisions=req.decisions,
            open_loops=req.open_loops,
            next_steps=req.next_steps,
            essential_context=req.essential_context,
            optional_context=req.optional_context,
            archived_context=req.archived_context,
            risk_flags=req.risk_flags,
            obsolete_context=req.obsolete_context,
            related_entry_ids=req.related_entry_ids,
            merge=req.merge,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/workstreams/{workstream_id}/executions/start", status_code=201)
async def execution_start_endpoint(workstream_id: str, req: SessionStartRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            start_session,
            root,
            workstream_id,
            goal=req.goal,
            summary=req.summary,
            session_id=req.session_id,
            tags=req.tags,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/workstreams/{workstream_id}/executions/close", status_code=201)
async def execution_close_endpoint(workstream_id: str, req: SessionCloseRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            close_session,
            root,
            workstream_id,
            session_id=req.session_id,
            outcome=req.outcome,
            status=req.status,
            next_steps=req.next_steps,
            open_loops=req.open_loops,
            related_entry_ids=req.related_entry_ids,
            next_goal=req.next_goal,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/workstreams/{workstream_id}/handoff", status_code=201)
async def structured_handoff_write_endpoint(workstream_id: str, req: StructuredHandoffRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        entry = await asyncio.to_thread(
            write_structured_handoff,
            root,
            workstream_id,
            session_id=req.session_id,
            goal=req.goal,
            summary=req.summary,
            current_state=req.current_state,
            decisions=req.decisions,
            open_loops=req.open_loops,
            next_steps=req.next_steps,
            essential_context=req.essential_context,
            optional_context=req.optional_context,
            archived_context=req.archived_context,
            related_entries=req.related_entries,
            risk_flags=req.risk_flags,
            obsolete_context=req.obsolete_context,
            restore_section=req.restore_section,
            restore_query=req.restore_query,
            include_deleted=req.include_deleted,
            tags=req.tags,
            audience="agent",
        )
        return {"entry": entry}
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/{workstream_id}/handoff-package")
async def handoff_package_endpoint(
    workstream_id: str,
    execution_id: str | None = Query(None),
    next_goal: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            build_handoff_package,
            root,
            workstream_id,
            session_id=execution_id,
            next_goal=next_goal,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.post("/api/workstreams/{workstream_id}/executions/close-and-handoff", status_code=201)
async def execution_close_and_handoff_endpoint(workstream_id: str, req: SessionCloseAndHandoffRequest) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        result = await asyncio.to_thread(
            close_session_with_handoff,
            root,
            workstream_id,
            session_id=req.session_id,
            outcome=req.outcome,
            next_goal=req.next_goal,
            status=req.status,
            summary=req.summary,
            open_loops=req.open_loops,
            next_steps=req.next_steps,
            essential_context=req.essential_context,
            optional_context=req.optional_context,
            archived_context=req.archived_context,
            risk_flags=req.risk_flags,
            obsolete_context=req.obsolete_context,
            related_entry_ids=req.related_entry_ids,
            include_deleted=req.include_deleted,
            audience="agent",
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/queue")
async def workstream_queue_endpoint(
    status: str | None = Query(None),
    include_deleted: bool = Query(False),
    limit: int | None = Query(None, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        items = await asyncio.to_thread(
            list_workstream_queue,
            root,
            status=status,
            include_deleted=include_deleted,
            limit=limit,
        )
        return {"items": items}
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/{workstream_id}/compare/executions")
async def compare_executions_endpoint(
    workstream_id: str,
    base_execution_id: str = Query(...),
    target_execution_id: str = Query(...),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            compare_sessions,
            root,
            workstream_id,
            base_execution_id,
            target_execution_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Execution comparison not available.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/compare")
async def compare_workstreams_endpoint(
    left_workstream_id: str = Query(...),
    right_workstream_id: str = Query(...),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            compare_workstreams,
            root,
            left_workstream_id,
            right_workstream_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Workstream comparison not available.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/switch-package")
async def workstream_switch_package_endpoint(
    current_workstream_id: str = Query(...),
    target_workstream_id: str = Query(...),
    current_execution_id: str | None = Query(None),
    target_execution_id: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            build_workstream_switch_package,
            root,
            current_workstream_id,
            target_workstream_id,
            current_session_id=current_execution_id,
            target_session_id=target_execution_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Workstream switch package not available.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)


@router.get("/api/workstreams/{workstream_id}/handoff")
async def structured_handoff_read_endpoint(
    workstream_id: str,
    session_id: str | None = Query(None),
    include_deleted: bool = Query(True),
) -> dict:
    root = await asyncio.to_thread(deps.get_root)
    try:
        payload = await asyncio.to_thread(
            read_structured_handoff,
            root,
            workstream_id=workstream_id,
            session_id=session_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Structured handoff not found.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise_http_error(exc)
