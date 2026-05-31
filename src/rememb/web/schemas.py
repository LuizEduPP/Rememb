"""Request models for the rememb web API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from rememb.config import DEFAULT_SEMANTIC_CONFLICT_THRESHOLD


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
    next_goal: str  # type: ignore[assignment]
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
