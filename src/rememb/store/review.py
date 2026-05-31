from __future__ import annotations

from pathlib import Path
from typing import Any

from rememb.exceptions import RemembValidationError
from rememb.utils import _find_entry, _normalize_handoff_lines, _now

from rememb.store._common import (
    _REVIEW_STATUS_VALUES,
    _compare_text_block,
    _entry_preview,
    _execution_snapshot_payload,
    _normalize_optional_text,
    _review_item,
    _session_compare_payload,
    _switch_gap_payload,
    _workstream_entries,
    _workstream_operational_status,
)
from rememb.store.crud import edit_entry, read_entries
from rememb.store.handoffs import build_handoff_package
from rememb.store.workstreams import (
    get_workstream_state,
    list_workstreams,
    resume_workstream,
)


def list_review_queue(
    root: Path,
    *,
    workstream_id: str | None = None,
    session_id: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    entry_kind: str | None = None,
    review_status: str | None = None,
    include_deleted: bool = False,
    pending_only: bool = True,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List entries that should be reviewed, with diff context when available."""
    entries = (
        _workstream_entries(root, workstream_id, session_id=session_id, include_deleted=include_deleted)
        if workstream_id is not None
        else read_entries(root, include_deleted=include_deleted)
    )
    items: list[dict[str, Any]] = []
    normalized_actor_type = _normalize_optional_text(actor_type)
    normalized_actor_id = _normalize_optional_text(actor_id)
    normalized_entry_kind = _normalize_optional_text(entry_kind)
    normalized_review_status = _normalize_optional_text(review_status)
    for entry in reversed(entries):
        review_item = _review_item(root, entry)
        if pending_only and review_item["review_status"] in {"approved", "dismissed"}:
            continue
        if not review_item["review_reasons"] and review_item["review_status"] == "pending":
            continue
        if session_id is not None and entry.get("session_id") != session_id:
            continue
        if normalized_actor_type and review_item.get("actor_type") != normalized_actor_type:
            continue
        if normalized_actor_id and review_item.get("actor_id") != normalized_actor_id:
            continue
        if normalized_entry_kind and review_item.get("entry_kind") != normalized_entry_kind:
            continue
        if normalized_review_status and review_item.get("review_status") != normalized_review_status:
            continue
        items.append(review_item)
        if limit is not None and limit >= 0 and len(items) >= limit:
            break
    return items


def get_review_session(
    root: Path,
    workstream_id: str,
    session_id: str,
    *,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Aggregate review context for one workstream session."""
    entries = _workstream_entries(root, workstream_id, session_id=session_id, include_deleted=include_deleted)
    if not entries:
        return None
    review_items = list_review_queue(
        root,
        workstream_id=workstream_id,
        session_id=session_id,
        include_deleted=include_deleted,
        pending_only=False,
    )
    resume = resume_workstream(root, workstream_id, session_id=session_id, include_deleted=include_deleted)
    state = get_workstream_state(root, workstream_id, session_id=session_id, include_deleted=include_deleted)
    latest_handoff = next((entry for entry in reversed(entries) if entry.get("entry_kind") == "handoff"), None)
    latest_state = next((entry for entry in reversed(entries) if entry.get("entry_kind") == "state"), None)
    latest_review = next((entry for entry in reversed(entries) if entry.get("entry_kind") == "review"), None)
    pending_review_count = sum(
        1
        for item in review_items
        if ((item.get("agent_review") or {}).get("policy") or {}).get("requires_human_validation")
        and not ((item.get("human_validation") or {}).get("finalized"))
    )
    return {
        "workstream_id": workstream_id,
        "session_id": session_id,
        "execution_id": session_id,
        "operational_status": _workstream_operational_status(entries, pending_review_count),
        "entry_count": len(entries),
        "review_count": len(review_items),
        "pending_review_count": pending_review_count,
        "latest_handoff": _entry_preview(latest_handoff) if latest_handoff else None,
        "latest_state": _entry_preview(latest_state) if latest_state else None,
        "latest_review": _entry_preview(latest_review) if latest_review else None,
        "resume": _session_compare_payload(session_id, entries, resume),
        "execution_snapshot": _execution_snapshot_payload(entries=entries, resume=resume, review_items=review_items),
        "review_items": review_items,
        "timeline": list((state or {}).get("timeline") or []),
        "active_decision_ids": list((resume or {}).get("active_decision_ids") or []),
    }


def get_review_workstream(
    root: Path,
    workstream_id: str,
    *,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Aggregate review context for a whole workstream."""
    entries = _workstream_entries(root, workstream_id, include_deleted=include_deleted)
    if not entries:
        return None
    state = get_workstream_state(root, workstream_id, include_deleted=include_deleted)
    resume = resume_workstream(root, workstream_id, include_deleted=include_deleted)
    review_items = list_review_queue(root, workstream_id=workstream_id, include_deleted=include_deleted, pending_only=False)
    session_ids = [item.get("session_id") for item in (state or {}).get("sessions") or [] if item.get("session_id")]
    session_groups = [
        get_review_session(root, workstream_id, session_id, include_deleted=include_deleted)
        for session_id in session_ids
    ]
    execution_history = [item for item in session_groups if item is not None]
    pending_review_count = sum(
        1
        for item in review_items
        if ((item.get("agent_review") or {}).get("policy") or {}).get("requires_human_validation")
        and not ((item.get("human_validation") or {}).get("finalized"))
    )
    return {
        "workstream_id": workstream_id,
        "operational_status": _workstream_operational_status(entries, pending_review_count),
        "entry_count": len(entries),
        "review_count": len(review_items),
        "pending_review_count": pending_review_count,
        "resume": resume,
        "latest_handoff": (state or {}).get("latest_handoff"),
        "latest_state": (state or {}).get("latest_state"),
        "latest_review": (state or {}).get("latest_review"),
        "review_items": review_items,
        "review_policy_summary": {
            "escalate_for_validation": sum(1 for item in review_items if (item.get("agent_review") or {}).get("decision") == "escalate_for_validation"),
            "auto_approve": sum(1 for item in review_items if (item.get("agent_review") or {}).get("decision") == "auto_approve"),
            "auto_dismiss": sum(1 for item in review_items if (item.get("agent_review") or {}).get("decision") == "auto_dismiss"),
        },
        "sessions": execution_history,
        "execution_history": execution_history,
        "execution_history_count": len(execution_history),
    }


def build_workstream_switch_package(
    root: Path,
    current_workstream_id: str,
    target_workstream_id: str,
    *,
    current_session_id: str | None = None,
    target_session_id: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Build an anti-context-switch package to freeze one workstream and resume another."""
    current_resume = resume_workstream(root, current_workstream_id, session_id=current_session_id, include_deleted=include_deleted)
    target_resume = resume_workstream(root, target_workstream_id, session_id=target_session_id, include_deleted=include_deleted)
    if current_resume is None or target_resume is None:
        return None
    current_package = build_handoff_package(
        root,
        current_workstream_id,
        session_id=current_session_id,
        next_goal=current_resume.get("goal") or current_workstream_id,
        include_deleted=include_deleted,
    ) or {}
    target_package = build_handoff_package(
        root,
        target_workstream_id,
        session_id=target_session_id,
        next_goal=(target_resume.get("next_execution") or {}).get("goal") or target_resume.get("goal") or target_workstream_id,
        include_deleted=include_deleted,
    ) or {}
    return {
        "switch_mode": "anti_context_switch",
        "current_workstream_id": current_workstream_id,
        "target_workstream_id": target_workstream_id,
        "current_execution_id": current_resume.get("session_id"),
        "target_execution_id": target_resume.get("session_id"),
        "freeze_current": {
            "workstream_id": current_workstream_id,
            "operational_status": current_resume.get("operational_status") or "active",
            "pending_review_count": current_resume.get("pending_review_count") or 0,
            "next_execution": dict(current_package.get("next_execution") or current_resume.get("next_execution") or {}),
            "handoff_package": current_package,
        },
        "resume_target": {
            "workstream_id": target_workstream_id,
            "operational_status": target_resume.get("operational_status") or "active",
            "pending_review_count": target_resume.get("pending_review_count") or 0,
            "next_execution": dict(target_package.get("next_execution") or target_resume.get("next_execution") or {}),
            "handoff_package": target_package,
        },
        "state_gap": _switch_gap_payload(current_resume, target_resume),
    }


def list_workstream_queue(
    root: Path,
    *,
    status: str | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List workstreams as an operational queue with explicit statuses."""
    items = list_workstreams(root, limit=None, include_deleted=include_deleted)
    normalized_status = _normalize_optional_text(status)
    if normalized_status:
        items = [item for item in items if item.get("operational_status") == normalized_status]
    if limit is not None and limit >= 0:
        return items[:limit]
    return items


def compare_sessions(
    root: Path,
    workstream_id: str,
    left_session_id: str,
    right_session_id: str,
    *,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Compare two sessions inside the same workstream."""
    left_entries = _workstream_entries(root, workstream_id, session_id=left_session_id, include_deleted=include_deleted)
    right_entries = _workstream_entries(root, workstream_id, session_id=right_session_id, include_deleted=include_deleted)
    if not left_entries or not right_entries:
        return None
    left_resume = resume_workstream(root, workstream_id, session_id=left_session_id, include_deleted=include_deleted)
    right_resume = resume_workstream(root, workstream_id, session_id=right_session_id, include_deleted=include_deleted)
    left_review = get_review_session(root, workstream_id, left_session_id, include_deleted=include_deleted)
    right_review = get_review_session(root, workstream_id, right_session_id, include_deleted=include_deleted)
    left_snapshot = dict((left_review or {}).get("execution_snapshot") or {})
    right_snapshot = dict((right_review or {}).get("execution_snapshot") or {})
    return {
        "workstream_id": workstream_id,
        "base_execution_id": left_session_id,
        "target_execution_id": right_session_id,
        "left": {
            "resume": _session_compare_payload(left_session_id, left_entries, left_resume),
            "review": left_review,
        },
        "right": {
            "resume": _session_compare_payload(right_session_id, right_entries, right_resume),
            "review": right_review,
        },
        "delta": {
            "new_open_loops": [item for item in (right_resume or {}).get("open_loops", []) if item not in (left_resume or {}).get("open_loops", [])],
            "resolved_open_loops": [item for item in (left_resume or {}).get("open_loops", []) if item not in (right_resume or {}).get("open_loops", [])],
            "new_next_steps": [item for item in (right_resume or {}).get("next_steps", []) if item not in (left_resume or {}).get("next_steps", [])],
            "new_focus_entry_ids": [item for item in (right_resume or {}).get("focus_entry_ids", []) if item not in (left_resume or {}).get("focus_entry_ids", [])],
            "new_decision_entry_ids": [
                item
                for item in (right_snapshot.get("outputs", {}).get("by_kind", {}).get("decision") or [])
                if item not in (left_snapshot.get("outputs", {}).get("by_kind", {}).get("decision") or [])
            ],
            "resolved_decision_entry_ids": [
                item
                for item in (left_snapshot.get("outputs", {}).get("by_kind", {}).get("decision") or [])
                if item not in (right_snapshot.get("outputs", {}).get("by_kind", {}).get("decision") or [])
            ],
            "risk_shift": {
                "base_pending_human_validation": left_snapshot.get("review_result", {}).get("pending_human_validation") or 0,
                "target_pending_human_validation": right_snapshot.get("review_result", {}).get("pending_human_validation") or 0,
            },
        },
        "decision_diff": _compare_text_block(
            list((left_snapshot.get("outputs", {}).get("by_kind", {}).get("decision") or [])),
            list((right_snapshot.get("outputs", {}).get("by_kind", {}).get("decision") or [])),
            left_label=f"{left_session_id}:decisions",
            right_label=f"{right_session_id}:decisions",
        ),
        "risk_diff": _compare_text_block(
            [
                f"pending_human_validation={left_snapshot.get('review_result', {}).get('pending_human_validation') or 0}",
                *[f"{key}={value}" for key, value in sorted((left_snapshot.get("review_result", {}).get("agent_decisions") or {}).items())],
            ],
            [
                f"pending_human_validation={right_snapshot.get('review_result', {}).get('pending_human_validation') or 0}",
                *[f"{key}={value}" for key, value in sorted((right_snapshot.get("review_result", {}).get("agent_decisions") or {}).items())],
            ],
            left_label=f"{left_session_id}:risk",
            right_label=f"{right_session_id}:risk",
        ),
        "current_state_diff": _compare_text_block(
            list((left_resume or {}).get("current_state") or []),
            list((right_resume or {}).get("current_state") or []),
            left_label=f"{left_session_id}:current_state",
            right_label=f"{right_session_id}:current_state",
        ),
        "open_loops_diff": _compare_text_block(
            list((left_resume or {}).get("open_loops") or []),
            list((right_resume or {}).get("open_loops") or []),
            left_label=f"{left_session_id}:open_loops",
            right_label=f"{right_session_id}:open_loops",
        ),
        "next_steps_diff": _compare_text_block(
            list((left_resume or {}).get("next_steps") or []),
            list((right_resume or {}).get("next_steps") or []),
            left_label=f"{left_session_id}:next_steps",
            right_label=f"{right_session_id}:next_steps",
        ),
    }


def compare_workstreams(
    root: Path,
    left_workstream_id: str,
    right_workstream_id: str,
    *,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    """Compare two workstreams at the resume layer."""
    left_resume = resume_workstream(root, left_workstream_id, include_deleted=include_deleted)
    right_resume = resume_workstream(root, right_workstream_id, include_deleted=include_deleted)
    left_state = get_workstream_state(root, left_workstream_id, include_deleted=include_deleted)
    right_state = get_workstream_state(root, right_workstream_id, include_deleted=include_deleted)
    left_entries = _workstream_entries(root, left_workstream_id, include_deleted=include_deleted)
    right_entries = _workstream_entries(root, right_workstream_id, include_deleted=include_deleted)
    if left_resume is None or right_resume is None or left_state is None or right_state is None:
        return None
    left_pending = len(list_review_queue(root, workstream_id=left_workstream_id, include_deleted=include_deleted, pending_only=True))
    right_pending = len(list_review_queue(root, workstream_id=right_workstream_id, include_deleted=include_deleted, pending_only=True))
    left_status = _workstream_operational_status(left_entries, left_pending)
    right_status = _workstream_operational_status(right_entries, right_pending)
    return {
        "left": {
            "workstream_id": left_workstream_id,
            "resume": left_resume,
            "state": left_state,
        },
        "right": {
            "workstream_id": right_workstream_id,
            "resume": right_resume,
            "state": right_state,
        },
        "delta": {
            "operational_status_changed": left_status != right_status,
            "left_operational_status": left_status,
            "right_operational_status": right_status,
            "left_only_open_loops": [item for item in left_resume.get("open_loops", []) if item not in right_resume.get("open_loops", [])],
            "right_only_open_loops": [item for item in right_resume.get("open_loops", []) if item not in left_resume.get("open_loops", [])],
            "left_only_focus_entry_ids": [item for item in left_resume.get("focus_entry_ids", []) if item not in right_resume.get("focus_entry_ids", [])],
            "right_only_focus_entry_ids": [item for item in right_resume.get("focus_entry_ids", []) if item not in left_resume.get("focus_entry_ids", [])],
            "left_pending_review_count": left_pending,
            "right_pending_review_count": right_pending,
        },
        "switch_package": build_workstream_switch_package(
            root,
            left_workstream_id,
            right_workstream_id,
            include_deleted=include_deleted,
        ),
        "open_loops_diff": _compare_text_block(
            list(left_resume.get("open_loops") or []),
            list(right_resume.get("open_loops") or []),
            left_label=f"{left_workstream_id}:open_loops",
            right_label=f"{right_workstream_id}:open_loops",
        ),
        "next_steps_diff": _compare_text_block(
            list(left_resume.get("next_steps") or []),
            list(right_resume.get("next_steps") or []),
            left_label=f"{left_workstream_id}:next_steps",
            right_label=f"{right_workstream_id}:next_steps",
        ),
    }


def update_review_status(
    root: Path,
    entry_id: str,
    review_status: str,
    *,
    review_notes: str | None = None,
    review_reason: str | None = None,
    validation_notes: str | None = None,
    source_context_entry_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Persist the review decision for one entry."""
    normalized_status = str(review_status).strip().lower()
    if normalized_status not in _REVIEW_STATUS_VALUES:
        raise RemembValidationError("review_status must be one of: pending, approved, needs_revision, dismissed.")
    entry = _find_entry(read_entries(root, include_deleted=True), entry_id)
    if entry is None:
        return None
    structured = dict(entry.get("structured") or {}) if isinstance(entry.get("structured"), dict) else {}
    structured["review_status"] = normalized_status
    structured["review_notes"] = _normalize_optional_text(review_notes) or ""
    structured["review_reason"] = _normalize_optional_text(review_reason) or ""
    structured["validation_notes"] = _normalize_optional_text(validation_notes) or ""
    if source_context_entry_ids is not None:
        structured["source_context_entry_ids"] = _normalize_handoff_lines(source_context_entry_ids)
    structured["reviewed_at"] = _now()
    structured["human_validation"] = {
        "status": normalized_status,
        "notes": structured["review_notes"],
        "reason": structured["review_reason"],
        "validation_notes": structured["validation_notes"],
        "reviewed_at": structured["reviewed_at"],
    }
    return edit_entry(
        root,
        entry_id,
        workstream_id=entry.get("workstream_id"),
        session_id=entry.get("session_id"),
        entry_kind=entry.get("entry_kind"),
        entry_role=entry.get("entry_role"),
        actor_type=entry.get("actor_type"),
        actor_id=entry.get("actor_id"),
        related_entry_ids=list(entry.get("related_entry_ids") or []),
        structured=structured,
    )
