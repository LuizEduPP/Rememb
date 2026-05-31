from __future__ import annotations

from pathlib import Path
from typing import Any

from rememb.exceptions import RemembValidationError
from rememb.utils import _find_entry, _parse_handoff_reference

from rememb.store._common import (
    _HANDOFF_SECTION,
    _HANDOFF_TAG,
    _generate_handoff,
    _handoff_structured_payload,
    _next_execution_payload,
    _normalize_handoff_lines,
    _normalize_optional_text,
    _normalize_related_reference_ids,
    _normalize_workstream_id,
    _workstream_entries,
    _workstream_latest_session_id,
)
from rememb.store.crud import read_entries, write_entry
from rememb.store.workstreams import (
    close_session,
    get_workstream_state,
    resume_workstream,
)


def write_structured_handoff(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    goal: str,
    summary: str | None = None,
    current_state: list[str] | None = None,
    decisions: list[str] | None = None,
    open_loops: list[str] | None = None,
    next_steps: list[str] | None = None,
    essential_context: list[str] | None = None,
    optional_context: list[str] | None = None,
    archived_context: list[str] | None = None,
    related_entries: list[str] | None = None,
    risk_flags: list[str] | None = None,
    obsolete_context: list[str] | None = None,
    restore_section: str = _HANDOFF_SECTION,
    restore_query: str | None = None,
    include_deleted: bool = False,
    tags: list[str] | None = None,
    audience: str = "agent",
) -> dict[str, Any]:
    """Persist a structured handoff payload for a workstream/session."""
    normalized_workstream_id = _normalize_workstream_id(workstream_id)
    effective_session_id = _normalize_optional_text(session_id) or _workstream_latest_session_id(
        _workstream_entries(root, normalized_workstream_id, include_deleted=include_deleted)
    )
    normalized_related_entries = _normalize_handoff_lines(related_entries)
    payload = _generate_handoff(
        goal,
        summary=summary,
        current_state=current_state,
        open_loops=open_loops,
        next_steps=next_steps,
        related_entries=normalized_related_entries,
        restore_section=restore_section,
        restore_query=restore_query,
        include_deleted=include_deleted,
        tags=tags,
    )
    structured = dict(payload.get("structured") or {})
    normalized_restore_context = payload.get("restore_context") or structured.get("restore_context") or {}
    structured.update(
        {
            "summary": _normalize_optional_text(summary) or structured.get("summary") or "",
            "decisions": _normalize_handoff_lines(decisions),
            "essential_context": _normalize_handoff_lines(essential_context) or list(structured.get("current_state") or []),
            "optional_context": _normalize_handoff_lines(optional_context),
            "archived_context": _normalize_handoff_lines(archived_context),
            "risk_flags": _normalize_handoff_lines(risk_flags),
            "obsolete_context": _normalize_handoff_lines(obsolete_context),
            "audience": _normalize_optional_text(audience) or "agent",
            "handoff_schema": "agent-first-operational-v1",
            "restore_context": normalized_restore_context,
            "restore_hint": dict(normalized_restore_context),
            "related_entries": [
                _parse_handoff_reference(item)
                for item in normalized_related_entries
            ],
        }
    )
    structured["next_execution"] = _next_execution_payload(
        goal=str(structured.get("goal") or ""),
        summary=str(structured.get("summary") or ""),
        current_state=list(structured.get("current_state") or []),
        open_loops=list(structured.get("open_loops") or []),
        next_steps=list(structured.get("next_steps") or []),
        compressed_context={
            "essential": list(structured.get("essential_context") or []),
            "optional": list(structured.get("optional_context") or []),
            "archived": list(structured.get("archived_context") or []),
            "risky": list(structured.get("risk_flags") or []),
            "obsolete": list(structured.get("obsolete_context") or []),
        },
        restore_context=normalized_restore_context,
        related_entry_ids=_normalize_related_reference_ids(normalized_related_entries),
    )
    return write_entry(
        root,
        payload["section"],
        payload["content"],
        payload["tags"],
        meta_schema_version=payload.get("meta_schema_version"),
        workstream_id=normalized_workstream_id,
        session_id=effective_session_id,
        entry_kind=payload.get("entry_kind"),
        entry_role=payload.get("entry_role"),
        related_entry_ids=_normalize_related_reference_ids(normalized_related_entries),
        structured=structured,
    )


def read_structured_handoff(
    root: Path,
    *,
    entry_id: str | None = None,
    workstream_id: str | None = None,
    session_id: str | None = None,
    include_deleted: bool = True,
) -> dict[str, Any] | None:
    """Read a structured handoff payload by entry id or workstream scope."""
    entry: dict[str, Any] | None = None
    if entry_id is not None:
        entry = _find_entry(read_entries(root, include_deleted=include_deleted), entry_id)
    else:
        if workstream_id is None:
            raise RemembValidationError("Provide entry_id or workstream_id.")
        entries = _workstream_entries(root, workstream_id, session_id=session_id, include_deleted=include_deleted)
        entry = next((item for item in reversed(entries) if item.get("entry_kind") == "handoff"), None)

    if entry is None:
        return None
    if entry.get("entry_kind") != "handoff" and _HANDOFF_TAG not in (entry.get("tags") or []):
        return None

    structured = _handoff_structured_payload(entry)
    restore_context = structured.get("restore_context")
    if not isinstance(restore_context, dict):
        restore_context = structured.get("restore_hint") if isinstance(structured.get("restore_hint"), dict) else {}
    return {
        "entry_id": entry.get("id"),
        "workstream_id": entry.get("workstream_id"),
        "session_id": entry.get("session_id"),
        "handoff_schema": structured.get("handoff_schema") or "agent-first-operational-v1",
        "goal": structured.get("goal") or "",
        "summary": structured.get("summary") or "",
        "current_state": list(structured.get("current_state") or []),
        "decisions": list(structured.get("decisions") or []),
        "open_loops": list(structured.get("open_loops") or []),
        "next_steps": list(structured.get("next_steps") or []),
        "essential_context": list(structured.get("essential_context") or []),
        "optional_context": list(structured.get("optional_context") or []),
        "archived_context": list(structured.get("archived_context") or []),
        "risk_flags": list(structured.get("risk_flags") or []),
        "obsolete_context": list(structured.get("obsolete_context") or []),
        "audience": "agent",
        "requested_audience": structured.get("requested_audience") or structured.get("audience") or "agent",
        "restore_context": restore_context,
        "restore_hint": dict(restore_context),
        "related_entries": list(structured.get("related_entries") or []),
        "next_execution": dict(structured.get("next_execution") or {}),
    }


def build_handoff_package(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    next_goal: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Build a minimal anti-context-switch package for the next session."""
    resume = resume_workstream(
        root,
        workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
    )
    if resume is None:
        return None
    state = get_workstream_state(
        root,
        workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
    )
    if state is None:
        return None
    normalized_goal = _normalize_optional_text(next_goal) or resume.get("goal") or workstream_id
    compressed_context = dict(resume.get("compressed_context") or _merge_compressed_context())
    if not compressed_context.get("essential"):
        compressed_context["essential"] = list(resume.get("current_state") or [])
    shared = {
        "workstream_id": resume["workstream_id"],
        "session_id": resume.get("session_id"),
        "handoff_schema": "agent-first-operational-v1",
        "current_goal": resume.get("goal") or "",
        "next_goal": normalized_goal,
        "execution_history_count": state.get("execution_history_count") or state.get("session_count") or 0,
        "restore_context": dict(resume.get("restore_context") or {}),
        "restore_hint": dict(resume.get("restore_context") or {}),
        "current_state": list(resume.get("current_state") or []),
        "open_loops": list(resume.get("open_loops") or []),
        "next_steps": list(resume.get("next_steps") or []),
        "related_entry_ids": list(resume.get("related_entry_ids") or []),
        "focus_entry_ids": list(resume.get("focus_entry_ids") or []),
        "compressed_context": compressed_context,
        "what_changed": list(resume.get("what_changed") or []),
        "latest_review": state.get("latest_review"),
        "active_decision_ids": list(resume.get("active_decision_ids") or []),
    }
    shared["operational_handoff"] = {
        "goal": normalized_goal,
        "current_state": list(resume.get("current_state") or []),
        "decisions": list(resume.get("active_decision_ids") or []),
        "open_loops": list(resume.get("open_loops") or []),
        "next_steps": list(resume.get("next_steps") or []),
        "essential_context": list(compressed_context.get("essential") or []),
        "optional_context": list(compressed_context.get("optional") or []),
        "related_entries": list(resume.get("related_entry_ids") or []),
        "restore_hint": dict(resume.get("restore_context") or {}),
        "risk_flags": list(compressed_context.get("risky") or []),
    }
    shared["next_execution"] = _next_execution_payload(
        goal=normalized_goal,
        summary=str(resume.get("summary") or ""),
        current_state=list(resume.get("current_state") or []),
        open_loops=list(resume.get("open_loops") or []),
        next_steps=list(resume.get("next_steps") or []),
        compressed_context=compressed_context,
        restore_context=dict(resume.get("restore_context") or {}),
        related_entry_ids=list(resume.get("related_entry_ids") or []),
        focus_entry_ids=list(resume.get("focus_entry_ids") or []),
    )
    shared["agent_handoff"] = {
        "goal": normalized_goal,
        "summary": resume.get("summary") or "",
        "current_state": list(resume.get("current_state") or []),
        "decisions": list(resume.get("active_decision_ids") or []),
        "open_loops": list(resume.get("open_loops") or []),
        "next_steps": list(resume.get("next_steps") or []),
        "essential_context": list(compressed_context.get("essential") or []),
        "optional_context": list(compressed_context.get("optional") or []),
        "archived_context": list(compressed_context.get("archived") or []),
        "risk_flags": list(compressed_context.get("risky") or []),
        "obsolete_context": list(compressed_context.get("obsolete") or []),
        "related_entries": list(resume.get("related_entry_ids") or []),
        "restore_context": dict(resume.get("restore_context") or {}),
        "restore_hint": dict(resume.get("restore_context") or {}),
        "audience": "agent",
    }
    shared["human_handoff"] = {
        "goal": normalized_goal,
        "summary": resume.get("summary") or "",
        "what_changed": list(resume.get("what_changed") or []),
        "open_loops": list(resume.get("open_loops") or []),
        "next_steps": list(resume.get("next_steps") or []),
        "watchouts": list(compressed_context.get("risky") or []),
        "related_entries": list(resume.get("related_entry_ids") or []),
        "restore_context": dict(resume.get("restore_context") or {}),
        "audience": "human",
    }
    return shared


def close_session_with_handoff(
    root: Path,
    workstream_id: str,
    *,
    outcome: str,
    next_goal: str,
    session_id: str | None = None,
    status: str = "paused",
    summary: str | None = None,
    open_loops: list[str] | None = None,
    next_steps: list[str] | None = None,
    essential_context: list[str] | None = None,
    optional_context: list[str] | None = None,
    archived_context: list[str] | None = None,
    risk_flags: list[str] | None = None,
    obsolete_context: list[str] | None = None,
    related_entry_ids: list[str] | None = None,
    include_deleted: bool = False,
    audience: str = "agent",
) -> dict[str, Any] | None:
    """Close a session and persist the next-goal handoff in one operation."""
    review_entry = close_session(
        root,
        workstream_id,
        session_id=session_id,
        outcome=outcome,
        status=status,
        next_steps=next_steps,
        open_loops=open_loops,
        related_entry_ids=related_entry_ids,
        next_goal=next_goal,
    )
    if review_entry is None:
        return None
    handoff_package = build_handoff_package(
        root,
        workstream_id,
        session_id=session_id or review_entry.get("session_id"),
        next_goal=next_goal,
        include_deleted=include_deleted,
    ) or {}
    selected_handoff = handoff_package.get("operational_handoff") or handoff_package.get("agent_handoff")
    selected_handoff = selected_handoff if isinstance(selected_handoff, dict) else {}
    requested_audience = str(audience).strip().lower() or "agent"
    handoff_entry = write_structured_handoff(
        root,
        workstream_id,
        session_id=session_id or review_entry.get("session_id"),
        goal=str(selected_handoff.get("goal") or next_goal).strip(),
        summary=_normalize_optional_text(summary) or _normalize_optional_text(selected_handoff.get("summary")) or "",
        current_state=list(selected_handoff.get("current_state") or handoff_package.get("current_state") or []),
        decisions=list(selected_handoff.get("decisions") or handoff_package.get("active_decision_ids") or []),
        open_loops=_normalize_handoff_lines(open_loops) if open_loops is not None else list(selected_handoff.get("open_loops") or handoff_package.get("open_loops") or []),
        next_steps=_normalize_handoff_lines(next_steps) if next_steps is not None else list(selected_handoff.get("next_steps") or handoff_package.get("next_steps") or []),
        essential_context=_normalize_handoff_lines(essential_context) if essential_context is not None else list(selected_handoff.get("essential_context") or (handoff_package.get("compressed_context") or {}).get("essential") or []),
        optional_context=_normalize_handoff_lines(optional_context) if optional_context is not None else list(selected_handoff.get("optional_context") or (handoff_package.get("compressed_context") or {}).get("optional") or []),
        archived_context=_normalize_handoff_lines(archived_context) if archived_context is not None else list(selected_handoff.get("archived_context") or (handoff_package.get("compressed_context") or {}).get("archived") or []),
        risk_flags=_normalize_handoff_lines(risk_flags) if risk_flags is not None else list(selected_handoff.get("risk_flags") or (handoff_package.get("compressed_context") or {}).get("risky") or []),
        obsolete_context=_normalize_handoff_lines(obsolete_context) if obsolete_context is not None else list(selected_handoff.get("obsolete_context") or (handoff_package.get("compressed_context") or {}).get("obsolete") or []),
        related_entries=list(selected_handoff.get("related_entries") or handoff_package.get("related_entry_ids") or []),
        restore_section=str((selected_handoff.get("restore_context") or {}).get("section") or (handoff_package.get("restore_context") or {}).get("section") or _HANDOFF_SECTION),
        restore_query=_normalize_optional_text((selected_handoff.get("restore_context") or {}).get("query")) or _normalize_optional_text((handoff_package.get("restore_context") or {}).get("query")),
        include_deleted=bool((selected_handoff.get("restore_context") or {}).get("include_deleted", include_deleted)),
        tags=["anti-context-switch", "handoff-agent"],
        audience=requested_audience,
    )
    return {
        "review_entry": review_entry,
        "handoff_entry": handoff_entry,
        "handoff_package": handoff_package,
    }

