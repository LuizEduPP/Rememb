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

from rememb.config import DEFAULT_SEMANTIC_CONFLICT_THRESHOLD, SEMANTIC_MODEL_CHOICES
from rememb.exceptions import RemembError, rememb_error_http_status, rememb_error_response_text
from rememb.store import (
    build_handoff_package,
    compare_sessions,
    compare_workstreams,
    close_session,
    close_session_with_handoff,
    consolidate_entries,
    diff_entry_versions,
    delete_entry,
    edit_entry,
    get_config,
    get_handoff_restore_context,
    get_review_session,
    get_review_workstream,
    get_stats,
    get_workstream_state,
    init,
    list_handoffs,
    list_entry_versions,
    list_review_queue,
    list_workstream_queue,
    list_workstreams,
    open_workstream,
    read_structured_handoff,
    read_entries_page,
    resume_workstream,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    start_session,
    update_review_status,
    update_config,
    update_workstream_state,
    write_handoff,
    write_entry,
    write_structured_handoff,
)
from rememb.utils import (
    ensure_global_root,
    list_skill_definitions,
    load_skill_definition,
)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="rememb", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── Root resolution ────────────────────────────────────────────────────────────

def _get_root() -> Path:
    """Return the global root, auto-initializing if needed."""
    return ensure_global_root(init)


def _raise_http_error(exc: Exception, *, default_status: int = 422) -> None:
    if isinstance(exc, RemembError):
        raise HTTPException(
            status_code=rememb_error_http_status(exc, default_status=default_status),
            detail=rememb_error_response_text(exc),
        ) from exc
    raise HTTPException(status_code=default_status, detail=str(exc)) from exc


# ── Request / Response models ─────────────────────────────────────────────────

class WriteRequest(BaseModel):
    content: str
    section: str
    tags: list[str] = []
    semantic_scope: str = "global"
    workstream_id: str | None = None
    session_id: str | None = None


class EditRequest(BaseModel):
    content: str | None = None
    section: str | None = None
    tags: list[str] | None = None
    workstream_id: str | None = None
    session_id: str | None = None


class HandoffWriteRequest(BaseModel):
    goal: str
    summary: str | None = None
    current_state: list[str] | None = None
    open_loops: list[str] | None = None
    next_steps: list[str] | None = None
    related_entries: list[str] | None = None
    restore_section: str = "actions"
    restore_query: str | None = None
    include_deleted: bool = False
    tags: list[str] | None = None
    workstream_id: str | None = None
    session_id: str | None = None


class WorkstreamOpenRequest(BaseModel):
    goal: str
    workstream_id: str | None = None
    summary: str | None = None
    tags: list[str] | None = None


class WorkstreamStateUpdateRequest(BaseModel):
    session_id: str | None = None
    goal: str | None = None
    summary: str | None = None
    current_state: list[str] | None = None
    decisions: list[str] | None = None
    open_loops: list[str] | None = None
    next_steps: list[str] | None = None
    essential_context: list[str] | None = None
    optional_context: list[str] | None = None
    archived_context: list[str] | None = None
    risk_flags: list[str] | None = None
    obsolete_context: list[str] | None = None
    related_entry_ids: list[str] | None = None
    merge: bool = True


class SessionStartRequest(BaseModel):
    goal: str | None = None
    summary: str | None = None
    session_id: str | None = None
    tags: list[str] | None = None


class SessionCloseRequest(BaseModel):
    session_id: str | None = None
    outcome: str
    status: str = "paused"
    next_steps: list[str] | None = None
    open_loops: list[str] | None = None
    related_entry_ids: list[str] | None = None
    next_goal: str | None = None


class SessionCloseAndHandoffRequest(SessionCloseRequest):
    next_goal: str
    summary: str | None = None
    essential_context: list[str] | None = None
    optional_context: list[str] | None = None
    archived_context: list[str] | None = None
    risk_flags: list[str] | None = None
    obsolete_context: list[str] | None = None
    include_deleted: bool = False
    audience: str = "agent"


class StructuredHandoffRequest(BaseModel):
    session_id: str | None = None
    goal: str
    summary: str | None = None
    current_state: list[str] | None = None
    decisions: list[str] | None = None
    open_loops: list[str] | None = None
    next_steps: list[str] | None = None
    essential_context: list[str] | None = None
    optional_context: list[str] | None = None
    archived_context: list[str] | None = None
    related_entries: list[str] | None = None
    risk_flags: list[str] | None = None
    obsolete_context: list[str] | None = None
    restore_section: str = "actions"
    restore_query: str | None = None
    include_deleted: bool = False
    tags: list[str] | None = None
    audience: str = "agent"


class ReviewStatusRequest(BaseModel):
    review_status: str
    review_notes: str | None = None
    review_reason: str | None = None
    validation_notes: str | None = None
    source_context_entry_ids: list[str] | None = None


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, Any]


class ConsolidateRequest(BaseModel):
    section: str | None = None
    mode: str = "exact"
    similarity_threshold: float = DEFAULT_SEMANTIC_CONFLICT_THRESHOLD


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


@app.get("/api/handoffs")
async def handoff_list_endpoint(
    include_deleted: bool = Query(False),
    limit: int | None = Query(None, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        items = await asyncio.to_thread(list_handoffs, root, limit=limit, include_deleted=include_deleted)
        return {"items": items}
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/workstreams")
async def workstream_list_endpoint(
    include_deleted: bool = Query(False),
    limit: int | None = Query(None, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        items = await asyncio.to_thread(list_workstreams, root, limit=limit, include_deleted=include_deleted)
        return {"items": items}
    except Exception as exc:
        _raise_http_error(exc)


@app.post("/api/workstreams/open", status_code=201)
async def workstream_open_endpoint(req: WorkstreamOpenRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.post("/api/handoffs", status_code=201)
async def create_handoff(req: HandoffWriteRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        entry = await asyncio.to_thread(
            write_handoff,
            root,
            req.goal,
            summary=req.summary,
            current_state=req.current_state,
            open_loops=req.open_loops,
            next_steps=req.next_steps,
            related_entries=req.related_entries,
            restore_section=req.restore_section,
            restore_query=req.restore_query,
            include_deleted=req.include_deleted,
            tags=req.tags,
            workstream_id=req.workstream_id,
            session_id=req.session_id,
        )
        return {"entry": entry}
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/workstreams/{workstream_id}/state")
async def workstream_state_endpoint(
    workstream_id: str,
    session_id: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        state = await asyncio.to_thread(
            get_workstream_state,
            root,
            workstream_id,
            session_id=session_id,
            include_deleted=include_deleted,
        )
        if state is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return state
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/workstreams/{workstream_id}/resume")
async def workstream_resume_endpoint(
    workstream_id: str,
    session_id: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        resume = await asyncio.to_thread(
            resume_workstream,
            root,
            workstream_id,
            session_id=session_id,
            include_deleted=include_deleted,
        )
        if resume is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return resume
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@app.post("/api/workstreams/{workstream_id}/state")
async def workstream_state_update_endpoint(workstream_id: str, req: WorkstreamStateUpdateRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.post("/api/workstreams/{workstream_id}/sessions/start", status_code=201)
async def session_start_endpoint(workstream_id: str, req: SessionStartRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.post("/api/workstreams/{workstream_id}/sessions/close", status_code=201)
async def session_close_endpoint(workstream_id: str, req: SessionCloseRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.post("/api/workstreams/{workstream_id}/handoff", status_code=201)
async def structured_handoff_write_endpoint(workstream_id: str, req: StructuredHandoffRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
            audience=req.audience,
        )
        return {"entry": entry}
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/workstreams/{workstream_id}/handoff-package")
async def handoff_package_endpoint(
    workstream_id: str,
    session_id: str | None = Query(None),
    next_goal: str | None = Query(None),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        payload = await asyncio.to_thread(
            build_handoff_package,
            root,
            workstream_id,
            session_id=session_id,
            next_goal=next_goal,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@app.post("/api/workstreams/{workstream_id}/sessions/close-and-handoff", status_code=201)
async def session_close_and_handoff_endpoint(workstream_id: str, req: SessionCloseAndHandoffRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
            audience=req.audience,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Workstream not found.")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/review")
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
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.get("/api/review/workstreams/{workstream_id}")
async def review_workstream_endpoint(workstream_id: str, include_deleted: bool = Query(False)) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.get("/api/review/workstreams/{workstream_id}/sessions/{session_id}")
async def review_session_endpoint(workstream_id: str, session_id: str, include_deleted: bool = Query(False)) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        payload = await asyncio.to_thread(
            get_review_session,
            root,
            workstream_id,
            session_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/workstreams/queue")
async def workstream_queue_endpoint(
    status: str | None = Query(None),
    include_deleted: bool = Query(False),
    limit: int | None = Query(None, ge=1, le=100),
) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.get("/api/workstreams/{workstream_id}/compare/sessions")
async def compare_sessions_endpoint(
    workstream_id: str,
    base_session_id: str = Query(...),
    target_session_id: str = Query(...),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        payload = await asyncio.to_thread(
            compare_sessions,
            root,
            workstream_id,
            base_session_id,
            target_session_id,
            include_deleted=include_deleted,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Session comparison not available.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@app.get("/api/workstreams/compare")
async def compare_workstreams_endpoint(
    left_workstream_id: str = Query(...),
    right_workstream_id: str = Query(...),
    include_deleted: bool = Query(False),
) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.post("/api/review/{entry_id}")
async def review_status_endpoint(entry_id: str, req: ReviewStatusRequest) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)


@app.get("/api/workstreams/{workstream_id}/handoff")
async def structured_handoff_read_endpoint(
    workstream_id: str,
    session_id: str | None = Query(None),
    include_deleted: bool = Query(True),
) -> dict:
    root = await asyncio.to_thread(_get_root)
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
        _raise_http_error(exc)



@app.get("/api/handoffs/{entry_id}/restore-context")
async def handoff_restore_context_endpoint(entry_id: str, include_deleted: bool = Query(True)) -> dict:
    root = await asyncio.to_thread(_get_root)
    try:
        parsed = await asyncio.to_thread(get_handoff_restore_context, root, entry_id, include_deleted=include_deleted)
        if parsed is None:
            raise HTTPException(status_code=404, detail="Handoff not found.")
        return parsed
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


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
            workstream_id=req.workstream_id,
            session_id=req.session_id,
        )
        return {"entry": entry}
    except Exception as exc:
        _raise_http_error(exc)



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
            workstream_id=req.workstream_id,
            session_id=req.session_id,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry not found.")
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)



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
        _raise_http_error(exc, default_status=500)



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
        _raise_http_error(exc)



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
        _raise_http_error(exc)



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
        _raise_http_error(exc)



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
        _raise_http_error(exc)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_web(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the rememb web UI server."""
    import uvicorn

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
