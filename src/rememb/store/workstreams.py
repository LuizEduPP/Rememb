from __future__ import annotations

from pathlib import Path
from typing import Any

from rememb.exceptions import RemembValidationError

from rememb.store._common import (
    _HANDOFF_SECTION,
    _decision_is_active,
    _dedupe_preserving_order,
    _entry_preview,
    _entry_timestamp,
    _generate_prefixed_identifier,
    _handoff_structured_payload,
    _merge_compressed_context,
    _next_execution_payload,
    _normalize_handoff_lines,
    _normalize_optional_lines,
    _normalize_optional_session_id,
    _normalize_optional_text,
    _normalize_related_reference_ids,
    _normalize_workstream_id,
    _review_status_from_entry,
    _timeline_since_anchor,
    _workstream_anchor_entry,
    _workstream_entries,
    _workstream_latest_session_id,
    _workstream_operational_status,
    _workstream_state_content,
    _workstream_timeline_preview,
)
from rememb.store.crud import read_entries, write_entry


def get_workstream_state(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Aggregate the current state of a workstream and its sessions."""
    entries = _workstream_entries(
        root,
        workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
    )
    if not entries:
        return None

    sessions: dict[str, dict[str, Any]] = {}
    latest_state_entry: dict[str, Any] | None = None
    latest_handoff_entry: dict[str, Any] | None = None

    for entry in entries:
        entry_session_id = str(entry.get("session_id") or "")
        if entry_session_id:
            session_bucket = sessions.setdefault(
                entry_session_id,
                {
                    "session_id": entry.get("session_id"),
                    "entry_count": 0,
                    "latest_updated_at": "",
                    "latest_entry_id": None,
                    "latest_entry_kind": None,
                    "latest_handoff_id": None,
                    "latest_state_id": None,
                    "latest_position": -1,
                },
            )
            session_bucket["entry_count"] += 1
            session_bucket["latest_updated_at"] = _entry_timestamp(entry)
            session_bucket["latest_entry_id"] = entry.get("id")
            session_bucket["latest_entry_kind"] = entry.get("entry_kind")
            session_bucket["latest_position"] = len(sessions) + session_bucket["entry_count"]
            if entry.get("entry_kind") == "handoff":
                session_bucket["latest_handoff_id"] = entry.get("id")
            if entry.get("entry_kind") == "state":
                session_bucket["latest_state_id"] = entry.get("id")
        if entry.get("entry_kind") == "handoff":
            latest_handoff_entry = entry
        if entry.get("entry_kind") == "state":
            latest_state_entry = entry

    latest_entry = entries[-1]
    ordered_sessions = sorted(
        sessions.values(),
        key=lambda item: (str(item.get("latest_updated_at") or ""), int(item.get("latest_position") or -1)),
        reverse=True,
    )
    timeline = [
        _workstream_timeline_preview(entry)
        for entry in reversed(entries)
    ]
    for item in ordered_sessions:
        item.pop("latest_position", None)

    latest_review_entry = next((entry for entry in reversed(entries) if entry.get("entry_kind") == "review"), None)

    return {
        "workstream_id": _normalize_workstream_id(workstream_id),
        "session_id": _normalize_optional_session_id(session_id),
        "entry_count": len(entries),
        "session_count": len(ordered_sessions),
        "execution_history_count": len(ordered_sessions),
        "latest_entry": _entry_preview(latest_entry),
        "latest_handoff": _entry_preview(latest_handoff_entry) if latest_handoff_entry else None,
        "latest_state": _entry_preview(latest_state_entry) if latest_state_entry else None,
        "latest_review": _entry_preview(latest_review_entry) if latest_review_entry else None,
        "sessions": ordered_sessions,
        "execution_history": ordered_sessions,
        "timeline": timeline,
    }


def resume_workstream(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Return a compact operational resume payload for a workstream."""
    entries = _workstream_entries(
        root,
        workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
    )
    if not entries:
        return None

    state = get_workstream_state(
        root,
        workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
    )
    if state is None:
        return None

    latest_handoff_entry = next((entry for entry in reversed(entries) if entry.get("entry_kind") == "handoff"), None)
    latest_state_entry = next((entry for entry in reversed(entries) if entry.get("entry_kind") == "state"), None)
    latest_entry = entries[-1]

    handoff_payload = _handoff_structured_payload(latest_handoff_entry) if latest_handoff_entry else {}
    state_payload = (
        latest_state_entry.get("structured")
        if latest_state_entry is not None and isinstance(latest_state_entry.get("structured"), dict)
        else {}
    )
    related_entry_ids: list[str] = []
    for source in (latest_handoff_entry, latest_state_entry, latest_entry):
        if not source:
            continue
        for related_entry_id in source.get("related_entry_ids", []):
            if related_entry_id not in related_entry_ids:
                related_entry_ids.append(related_entry_id)

    focus_entry_ids = _dedupe_preserving_order([
        state.get("latest_handoff", {}).get("id") if state.get("latest_handoff") else None,
        state.get("latest_state", {}).get("id") if state.get("latest_state") else None,
        state.get("latest_entry", {}).get("id") if state.get("latest_entry") else None,
    ])

    restore_context = handoff_payload.get("restore_context")
    if not isinstance(restore_context, dict):
        restore_context = handoff_payload.get("restore_hint") if isinstance(handoff_payload.get("restore_hint"), dict) else {}
    if not restore_context:
        restore_context = {
            "section": str(latest_entry.get("section") or "actions"),
            "query": str(handoff_payload.get("goal") or state_payload.get("goal") or latest_entry.get("workstream_id") or workstream_id),
            "include_deleted": include_deleted,
        }

    compressed_context = _merge_compressed_context(state_payload, handoff_payload)
    if not compressed_context["essential"]:
        compressed_context["essential"] = list(handoff_payload.get("current_state") or state_payload.get("current_state") or [])
    anchor_entry = _workstream_anchor_entry(entries)
    changed_entries = _timeline_since_anchor(entries, anchor_entry)
    goal = handoff_payload.get("goal") or state_payload.get("goal") or latest_entry.get("content", "")
    summary = handoff_payload.get("summary") or state_payload.get("summary") or ""
    current_state = handoff_payload.get("current_state") or state_payload.get("current_state") or []
    open_loops = handoff_payload.get("open_loops") or state_payload.get("open_loops") or []
    next_steps = handoff_payload.get("next_steps") or state_payload.get("next_steps") or []
    from rememb.store.review import list_review_queue

    pending_review_count = len(list_review_queue(
        root,
        workstream_id=workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
        pending_only=True,
    ))

    return {
        "workstream_id": state["workstream_id"],
        "session_id": latest_entry.get("session_id") or state.get("session_id"),
        "entry_count": state["entry_count"],
        "session_count": state["session_count"],
        "execution_history_count": state["execution_history_count"],
        "focus_entry_ids": focus_entry_ids,
        "latest_entry_id": latest_entry.get("id"),
        "latest_entry_kind": latest_entry.get("entry_kind"),
        "goal": goal,
        "summary": summary,
        "current_state": current_state,
        "open_loops": open_loops,
        "next_steps": next_steps,
        "restore_context": restore_context,
        "related_entry_ids": related_entry_ids,
        "compressed_context": compressed_context,
        "operational_status": _workstream_operational_status(entries, pending_review_count),
        "pending_review_count": pending_review_count,
        "next_execution": _next_execution_payload(
            goal=goal,
            summary=summary,
            current_state=list(current_state),
            open_loops=list(open_loops),
            next_steps=list(next_steps),
            compressed_context=compressed_context,
            restore_context=restore_context,
            related_entry_ids=related_entry_ids,
            focus_entry_ids=focus_entry_ids,
        ),
        "what_changed": changed_entries,
        "review_anchor_entry_id": anchor_entry.get("id") if anchor_entry else None,
        "active_decision_ids": [entry.get("id") for entry in entries if _decision_is_active(entry, entries)],
    }


def list_workstreams(
    root: Path,
    *,
    limit: int | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """List aggregated workstreams derived from existing entries."""
    from rememb.store.review import list_review_queue

    entries = read_entries(root, include_deleted=include_deleted)
    workstream_ids = {
        str(entry.get("workstream_id")).strip()
        for entry in entries
        if isinstance(entry.get("workstream_id"), str) and str(entry.get("workstream_id")).strip()
    }
    items: list[dict[str, Any]] = []
    for workstream_id in workstream_ids:
        workstream_entries = _workstream_entries(root, workstream_id, include_deleted=include_deleted)
        if not workstream_entries:
            continue
        latest_entry = workstream_entries[-1]
        state = get_workstream_state(root, workstream_id, include_deleted=include_deleted)
        resume = resume_workstream(root, workstream_id, include_deleted=include_deleted)
        pending_review_count = len(list_review_queue(root, workstream_id=workstream_id, include_deleted=include_deleted, pending_only=True))
        operational_status = _workstream_operational_status(workstream_entries, pending_review_count)
        items.append(
            {
                "workstream_id": workstream_id,
                "entry_count": len(workstream_entries),
                "session_count": state["session_count"] if state else 0,
                "execution_history_count": state["execution_history_count"] if state else 0,
                "latest_entry": _entry_preview(latest_entry),
                "latest_handoff": state.get("latest_handoff") if state else None,
                "latest_state": state.get("latest_state") if state else None,
                "latest_session_id": _workstream_latest_session_id(workstream_entries),
                "goal": (resume or {}).get("goal") or latest_entry.get("content", ""),
                "summary": (resume or {}).get("summary") or "",
                "operational_status": operational_status,
                "pending_review_count": pending_review_count,
                "active_decision_ids": list((resume or {}).get("active_decision_ids") or []),
                "next_execution": dict((resume or {}).get("next_execution") or {}),
                "updated_at": _entry_timestamp(latest_entry),
            }
        )
    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    if limit is not None and limit >= 0:
        return items[:limit]
    return items


def open_workstream(
    root: Path,
    goal: str,
    *,
    workstream_id: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Create or reopen a logical workstream."""
    normalized_goal = str(goal).strip()
    if not normalized_goal:
        raise RemembValidationError("goal is required.")

    existing_entries = read_entries(root, include_deleted=True)
    normalized_workstream_id = _normalize_optional_text(workstream_id)
    if normalized_workstream_id is None:
        used_ids = {
            str(entry.get("workstream_id")).strip()
            for entry in existing_entries
            if isinstance(entry.get("workstream_id"), str) and str(entry.get("workstream_id")).strip()
        }
        normalized_workstream_id = _generate_prefixed_identifier("ws", used_ids)

    workstream_entries = _workstream_entries(root, normalized_workstream_id, include_deleted=True)
    if workstream_entries:
        latest_entry = workstream_entries[-1]
        return {
            "workstream_id": normalized_workstream_id,
            "created": False,
            "entry": latest_entry,
            "state": get_workstream_state(root, normalized_workstream_id, include_deleted=True),
        }

    structured = {
        "goal": normalized_goal,
        "summary": _normalize_optional_text(summary) or "",
        "current_state": [],
        "decisions": [],
        "open_loops": [],
        "next_steps": [],
        "essential_context": [],
        "optional_context": [],
        "risk_flags": [],
        "status": "active",
    }
    entry = write_entry(
        root,
        "actions",
        _workstream_state_content(structured, label="Workstream Opened"),
        ["workstream", *(tags or [])],
        workstream_id=normalized_workstream_id,
        entry_kind="state",
        entry_role="checkpoint",
        structured=structured,
    )
    return {
        "workstream_id": normalized_workstream_id,
        "created": True,
        "entry": entry,
        "state": get_workstream_state(root, normalized_workstream_id),
    }


def update_workstream_state(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    goal: str | None = None,
    summary: str | None = None,
    current_state: list[str] | None = None,
    decisions: list[str] | None = None,
    open_loops: list[str] | None = None,
    next_steps: list[str] | None = None,
    essential_context: list[str] | None = None,
    optional_context: list[str] | None = None,
    archived_context: list[str] | None = None,
    risk_flags: list[str] | None = None,
    obsolete_context: list[str] | None = None,
    related_entry_ids: list[str] | None = None,
    merge: bool = True,
) -> dict[str, Any] | None:
    """Write a structured state checkpoint for a workstream."""
    workstream_entries = _workstream_entries(root, workstream_id, include_deleted=False)
    if not workstream_entries:
        return None

    latest_state_entry = next((entry for entry in reversed(workstream_entries) if entry.get("entry_kind") == "state"), None)
    base_structured = {}
    if merge and latest_state_entry is not None and isinstance(latest_state_entry.get("structured"), dict):
        base_structured = dict(latest_state_entry["structured"])
    resume = resume_workstream(root, workstream_id, session_id=session_id, include_deleted=False) or {}
    effective_session_id = _normalize_optional_text(session_id) or _workstream_latest_session_id(workstream_entries)
    structured = {
        "goal": _normalize_optional_text(goal) or base_structured.get("goal") or resume.get("goal") or workstream_id,
        "summary": _normalize_optional_text(summary) or base_structured.get("summary") or resume.get("summary") or "",
        "current_state": _normalize_optional_lines(current_state) if current_state is not None else list(base_structured.get("current_state") or resume.get("current_state") or []),
        "decisions": _normalize_optional_lines(decisions) if decisions is not None else list(base_structured.get("decisions") or []),
        "open_loops": _normalize_optional_lines(open_loops) if open_loops is not None else list(base_structured.get("open_loops") or resume.get("open_loops") or []),
        "next_steps": _normalize_optional_lines(next_steps) if next_steps is not None else list(base_structured.get("next_steps") or resume.get("next_steps") or []),
        "essential_context": _normalize_optional_lines(essential_context) if essential_context is not None else list(base_structured.get("essential_context") or []),
        "optional_context": _normalize_optional_lines(optional_context) if optional_context is not None else list(base_structured.get("optional_context") or []),
        "archived_context": _normalize_optional_lines(archived_context) if archived_context is not None else list(base_structured.get("archived_context") or []),
        "risk_flags": _normalize_optional_lines(risk_flags) if risk_flags is not None else list(base_structured.get("risk_flags") or []),
        "obsolete_context": _normalize_optional_lines(obsolete_context) if obsolete_context is not None else list(base_structured.get("obsolete_context") or []),
        "status": "active",
    }
    return write_entry(
        root,
        "actions",
        _workstream_state_content(structured, label="Workstream State Update"),
        ["workstream", "state"],
        workstream_id=_normalize_workstream_id(workstream_id),
        session_id=effective_session_id,
        entry_kind="state",
        entry_role="checkpoint",
        related_entry_ids=related_entry_ids,
        structured=structured,
    )


def start_session(
    root: Path,
    workstream_id: str,
    *,
    goal: str | None = None,
    summary: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any] | None:
    """Start a new logical session inside a workstream."""
    normalized_workstream_id = _normalize_workstream_id(workstream_id)
    workstream_entries = _workstream_entries(root, normalized_workstream_id, include_deleted=False)
    if not workstream_entries:
        return None
    used_session_ids = {
        str(entry.get("session_id")).strip()
        for entry in workstream_entries
        if isinstance(entry.get("session_id"), str) and str(entry.get("session_id")).strip()
    }
    effective_session_id = _normalize_optional_text(session_id) or _generate_prefixed_identifier("sess", used_session_ids)
    resume = resume_workstream(root, normalized_workstream_id, include_deleted=False) or {}
    structured = {
        "goal": _normalize_optional_text(goal) or resume.get("goal") or normalized_workstream_id,
        "summary": _normalize_optional_text(summary) or resume.get("summary") or "",
        "current_state": list(resume.get("current_state") or []),
        "decisions": [],
        "open_loops": list(resume.get("open_loops") or []),
        "next_steps": list(resume.get("next_steps") or []),
        "essential_context": list(resume.get("current_state") or []),
        "optional_context": [],
        "archived_context": list((resume.get("compressed_context") or {}).get("archived") or []),
        "risk_flags": [],
        "obsolete_context": list((resume.get("compressed_context") or {}).get("obsolete") or []),
        "status": "active",
        "event": "session_start",
    }
    return write_entry(
        root,
        "actions",
        _workstream_state_content(structured, label="Session Started"),
        ["session", "start", *(tags or [])],
        workstream_id=normalized_workstream_id,
        session_id=effective_session_id,
        entry_kind="state",
        entry_role="checkpoint",
        structured=structured,
    )


def close_session(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    outcome: str,
    status: str = "paused",
    next_steps: list[str] | None = None,
    open_loops: list[str] | None = None,
    related_entry_ids: list[str] | None = None,
    next_goal: str | None = None,
) -> dict[str, Any] | None:
    """Close the active or selected session and record a structured review entry."""
    normalized_workstream_id = _normalize_workstream_id(workstream_id)
    normalized_outcome = str(outcome).strip()
    if not normalized_outcome:
        raise RemembValidationError("outcome is required.")
    workstream_entries = _workstream_entries(root, normalized_workstream_id, include_deleted=False)
    if not workstream_entries:
        return None
    effective_session_id = _normalize_optional_text(session_id) or _workstream_latest_session_id(workstream_entries)
    if effective_session_id is None:
        return None
    structured = {
        "outcome": normalized_outcome,
        "status": _normalize_optional_text(status) or "paused",
        "open_loops": _normalize_handoff_lines(open_loops),
        "next_steps": _normalize_handoff_lines(next_steps),
        "next_goal": _normalize_optional_text(next_goal) or "",
        "event": "session_close",
    }
    content_lines = [
        "# Session Closed",
        "",
        f"Outcome: {normalized_outcome}",
        f"Status: {structured['status']}",
    ]
    if structured["open_loops"]:
        content_lines.extend(["", "Open loops:", *[f"- {item}" for item in structured["open_loops"]]])
    if structured["next_steps"]:
        content_lines.extend(["", "Next steps:", *[f"{index + 1}. {item}" for index, item in enumerate(structured["next_steps"]) ]])
    if structured["next_goal"]:
        content_lines.extend(["", f"Next goal: {structured['next_goal']}"])
    return write_entry(
        root,
        "actions",
        "\n".join(content_lines),
        ["session", "close", structured["status"]],
        workstream_id=normalized_workstream_id,
        session_id=effective_session_id,
        entry_kind="review",
        entry_role="final",
        related_entry_ids=related_entry_ids,
        structured=structured,
    )

