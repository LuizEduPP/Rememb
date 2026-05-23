from __future__ import annotations

import json
import logging
from difflib import unified_diff
import uuid
from pathlib import Path
from typing import Any

from rememb.exceptions import (
    RemembValidationError,
    RemembStorageError,
    RemembConfigError,
    RemembError,
)
from rememb.config import DEFAULT_CONFIG, DEFAULT_SEMANTIC_CONFLICT_THRESHOLD
from rememb.utils import (
    HANDOFF_SECTION,
    HANDOFF_TAG,
    _apply_revision,
    _config_path,
    _current_entry_version,
    _deleted_at,
    _entries_path,
    _entry_history,
    _entry_revision_list,
    _entry_revision_snapshot,
    _filter_deleted,
    _find_entry,
    _find_entry_revision,
    _handoff_list_block,
    _handoff_text_block,
    _normalize_handoff_goal_tag,
    _normalize_handoff_lines,
    _normalize_version_number,
    _now,
    _parse_handoff_list,
    _parse_handoff_reference,
    _parse_restore_context,
    _rememb_path,
    _revision_label,
    _split_handoff_sections,
    _is_deleted_entry,
)
from rememb.helpers import (
    MemoryStore,
    _load_entries,
    _atomic_modify,
    _get_sections,
    _migrate_entries_to_section,
    _restore_migrated_entries,
    _semantic_search,
    _sanitize_content,
    _sanitize_tags,
    _store_context,
    _sync_meta_sections,
    _validate_section,
    _validate_config_updates,
    _assert_initialized,
)

logger = logging.getLogger(__name__)

_HANDOFF_SECTION = HANDOFF_SECTION
_HANDOFF_TAG = HANDOFF_TAG
_ENTRY_KIND_VALUES = {"memory", "decision", "state", "handoff", "artifact", "review"}
_ENTRY_ROLE_VALUES = {"essential", "optional", "supporting", "checkpoint", "final"}
_ACTOR_TYPE_VALUES = {"agent", "human", "system"}
_REVIEW_STATUS_VALUES = {"pending", "approved", "needs_revision", "dismissed"}
_ENTRY_METADATA_FIELDS = (
    "meta_schema_version",
    "workstream_id",
    "session_id",
    "entry_kind",
    "entry_role",
    "actor_type",
    "actor_id",
    "parent_entry_id",
    "supersedes_entry_id",
    "related_entry_ids",
    "structured",
)


def _normalize_entry_metadata_value(field: str, value: Any) -> Any:
    if field == "meta_schema_version":
        if not isinstance(value, int) or value < 1:
            raise RemembValidationError("meta_schema_version must be a positive integer.")
        return value

    if field in {"workstream_id", "session_id", "actor_id", "parent_entry_id", "supersedes_entry_id"}:
        normalized = str(value).strip()
        if not normalized:
            raise RemembValidationError(f"{field} cannot be empty.")
        return normalized

    if field == "entry_kind":
        normalized = str(value).strip().lower()
        if normalized not in _ENTRY_KIND_VALUES:
            raise RemembValidationError(
                "entry_kind must be one of: memory, decision, state, handoff, artifact, review."
            )
        return normalized

    if field == "entry_role":
        normalized = str(value).strip().lower()
        if normalized not in _ENTRY_ROLE_VALUES:
            raise RemembValidationError(
                "entry_role must be one of: essential, optional, supporting, checkpoint, final."
            )
        return normalized

    if field == "actor_type":
        normalized = str(value).strip().lower()
        if normalized not in _ACTOR_TYPE_VALUES:
            raise RemembValidationError("actor_type must be one of: agent, human, system.")
        return normalized

    if field == "related_entry_ids":
        if not isinstance(value, list):
            raise RemembValidationError("related_entry_ids must be an array of non-empty strings.")
        normalized_list: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if not normalized:
                raise RemembValidationError("related_entry_ids cannot contain empty values.")
            normalized_list.append(normalized)
        return normalized_list

    if field == "structured":
        if not isinstance(value, dict):
            raise RemembValidationError("structured must be an object.")
        try:
            json.dumps(value)
        except TypeError as exc:
            raise RemembValidationError("structured must be JSON-serializable.") from exc
        return value

    raise RemembValidationError(f"Unsupported entry metadata field: {field}")


def _extract_entry_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in _ENTRY_METADATA_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        metadata[field] = _normalize_entry_metadata_value(field, payload[field])
    return metadata


def generate_handoff(
    goal: str,
    *,
    summary: str | None = None,
    current_state: list[str] | None = None,
    open_loops: list[str] | None = None,
    next_steps: list[str] | None = None,
    related_entries: list[str] | None = None,
    restore_section: str = _HANDOFF_SECTION,
    restore_query: str | None = None,
    include_deleted: bool = False,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a structured handoff payload stored as a normal entry."""
    normalized_goal = str(goal).strip()
    if not normalized_goal:
        raise RemembValidationError("goal is required.")

    normalized_current_state = _normalize_handoff_lines(current_state)
    normalized_open_loops = _normalize_handoff_lines(open_loops)
    normalized_next_steps = _normalize_handoff_lines(next_steps)
    normalized_related_entries = _normalize_handoff_lines(related_entries)
    normalized_tags = _normalize_handoff_lines(tags)
    handoff_tags = [_HANDOFF_TAG, _normalize_handoff_goal_tag(normalized_goal), *normalized_tags]
    restore_query_value = str(restore_query or normalized_goal).strip()

    content_lines = [
        "# Handoff",
        "",
        "## Goal",
        *_handoff_text_block(normalized_goal, fallback="No goal recorded."),
        "",
        "## Summary",
        *_handoff_text_block(summary, fallback="No summary provided."),
        "",
        "## Current State",
        *_handoff_list_block(normalized_current_state),
        "",
        "## Open Loops",
        *_handoff_list_block(normalized_open_loops),
        "",
        "## Next Steps",
        *_handoff_list_block(normalized_next_steps, ordered=True),
        "",
        "## Related Entries",
        *_handoff_list_block(normalized_related_entries),
        "",
        "## Restore Context",
        f"section={str(restore_section).strip() or _HANDOFF_SECTION}",
        f"query={restore_query_value}",
        f"include_deleted={'true' if include_deleted else 'false'}",
    ]

    return {
        "section": _HANDOFF_SECTION,
        "tags": handoff_tags,
        "content": "\n".join(content_lines),
        "meta_schema_version": 1,
        "entry_kind": "handoff",
        "entry_role": "final",
        "structured": {
            "goal": normalized_goal,
            "summary": str(summary or "").strip(),
            "current_state": normalized_current_state,
            "decisions": [],
            "open_loops": normalized_open_loops,
            "next_steps": normalized_next_steps,
            "essential_context": normalized_current_state,
            "optional_context": [],
            "risk_flags": [],
            "restore_context": {
                "section": str(restore_section).strip() or _HANDOFF_SECTION,
                "query": restore_query_value,
                "include_deleted": include_deleted,
            },
            "restore_hint": {
                "section": str(restore_section).strip() or _HANDOFF_SECTION,
                "query": restore_query_value,
                "include_deleted": include_deleted,
            },
            "related_entries": [
                {"entry_id": item, "version": None, "reason": None}
                for item in normalized_related_entries
            ],
        },
        "goal": normalized_goal,
        "restore_context": {
            "section": str(restore_section).strip() or _HANDOFF_SECTION,
            "query": restore_query_value,
            "include_deleted": include_deleted,
        },
        "related_entries": normalized_related_entries,
    }


def write_handoff(
    root: Path,
    goal: str,
    *,
    summary: str | None = None,
    current_state: list[str] | None = None,
    open_loops: list[str] | None = None,
    next_steps: list[str] | None = None,
    related_entries: list[str] | None = None,
    restore_section: str = _HANDOFF_SECTION,
    restore_query: str | None = None,
    include_deleted: bool = False,
    tags: list[str] | None = None,
    workstream_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Persist a handoff as a normal entry in the actions section."""
    payload = generate_handoff(
        goal,
        summary=summary,
        current_state=current_state,
        open_loops=open_loops,
        next_steps=next_steps,
        related_entries=related_entries,
        restore_section=restore_section,
        restore_query=restore_query,
        include_deleted=include_deleted,
        tags=tags,
    )
    return write_entry(
        root,
        payload["section"],
        payload["content"],
        payload["tags"],
        meta_schema_version=payload.get("meta_schema_version"),
        workstream_id=workstream_id,
        session_id=session_id,
        entry_kind=payload.get("entry_kind"),
        entry_role=payload.get("entry_role"),
        structured=payload.get("structured"),
    )


def list_handoffs(root: Path, *, limit: int | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
    """List stored handoff entries, newest first."""
    _assert_initialized(root)
    handoffs = [
        entry
        for entry in read_entries(root, _HANDOFF_SECTION, include_deleted=include_deleted)
        if _HANDOFF_TAG in entry.get("tags", [])
    ]
    handoffs.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    if limit is not None and limit >= 0:
        return handoffs[:limit]
    return handoffs


def parse_handoff_restore_context(entry_or_content: dict[str, Any] | str) -> dict[str, Any]:
    """Parse a handoff entry body and extract restore hints and related references."""
    content = entry_or_content.get("content", "") if isinstance(entry_or_content, dict) else str(entry_or_content)
    sections = _split_handoff_sections(content)
    goal_lines = [line.strip() for line in sections.get("goal", []) if line.strip()]
    summary_lines = [line.strip() for line in sections.get("summary", []) if line.strip()]
    current_state = _parse_handoff_list(sections.get("current state", []))
    open_loops = _parse_handoff_list(sections.get("open loops", []))
    next_steps = _parse_handoff_list(sections.get("next steps", []))
    related_entries = [_parse_handoff_reference(item) for item in _parse_handoff_list(sections.get("related entries", []))]
    restore_context = _parse_restore_context(sections.get("restore context", []))

    return {
        "goal": " ".join(goal_lines),
        "summary": " ".join(summary_lines),
        "current_state": current_state,
        "open_loops": open_loops,
        "next_steps": next_steps,
        "related_entries": related_entries,
        "restore_context": restore_context,
    }


def get_handoff(root: Path, entry_id: str, *, include_deleted: bool = True) -> dict[str, Any] | None:
    """Return a stored handoff entry by ID."""
    for handoff in list_handoffs(root, include_deleted=include_deleted):
        if str(handoff.get("id", "")) == entry_id:
            return handoff
    return None


def get_handoff_restore_context(root: Path, entry_id: str, *, include_deleted: bool = True) -> dict[str, Any] | None:
    """Return parsed restore hints for a stored handoff entry."""
    handoff = get_handoff(root, entry_id, include_deleted=include_deleted)
    if handoff is None:
        return None
    return parse_handoff_restore_context(handoff)


def _entry_timestamp(entry: dict[str, Any]) -> str:
    return str(entry.get("updated_at") or entry.get("created_at") or "")


def _normalize_workstream_id(workstream_id: str) -> str:
    normalized = str(workstream_id).strip()
    if not normalized:
        raise RemembValidationError("workstream_id cannot be empty.")
    return normalized


def _normalize_optional_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    normalized = str(session_id).strip()
    if not normalized:
        raise RemembValidationError("session_id cannot be empty when provided.")
    return normalized


def _workstream_entries(
    root: Path,
    workstream_id: str,
    *,
    session_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    normalized_workstream_id = _normalize_workstream_id(workstream_id)
    normalized_session_id = _normalize_optional_session_id(session_id)
    entries = read_entries(root, include_deleted=include_deleted)
    filtered_with_order = [
        (index, entry)
        for index, entry in enumerate(entries)
        if entry.get("workstream_id") == normalized_workstream_id
        and (normalized_session_id is None or entry.get("session_id") == normalized_session_id)
    ]
    filtered_with_order.sort(key=lambda item: (_entry_timestamp(item[1]), item[0]))
    return [entry for _, entry in filtered_with_order]


def _entry_preview(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "section": entry.get("section"),
        "session_id": entry.get("session_id"),
        "entry_kind": entry.get("entry_kind"),
        "entry_role": entry.get("entry_role"),
        "updated_at": entry.get("updated_at"),
        "created_at": entry.get("created_at"),
        "related_entry_ids": entry.get("related_entry_ids", []),
    }


def _workstream_timeline_preview(entry: dict[str, Any]) -> dict[str, Any]:
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    summary = ""
    if isinstance(structured, dict):
        summary = str(
            structured.get("summary")
            or structured.get("goal")
            or structured.get("outcome")
            or ""
        ).strip()
    if not summary:
        summary = str(entry.get("content") or "").strip().splitlines()[0] if str(entry.get("content") or "").strip() else ""

    return {
        "id": entry.get("id"),
        "section": entry.get("section"),
        "session_id": entry.get("session_id"),
        "entry_kind": entry.get("entry_kind"),
        "entry_role": entry.get("entry_role"),
        "updated_at": entry.get("updated_at"),
        "created_at": entry.get("created_at"),
        "deleted_at": entry.get("deleted_at"),
        "summary": summary,
        "related_entry_ids": entry.get("related_entry_ids", []),
    }


def _handoff_structured_payload(entry: dict[str, Any]) -> dict[str, Any]:
    structured = entry.get("structured")
    if isinstance(structured, dict) and structured:
        return dict(structured)
    return parse_handoff_restore_context(entry)


def _generate_prefixed_identifier(prefix: str, existing_values: set[str]) -> str:
    candidate = f"{prefix}_{str(uuid.uuid4())[:8]}"
    attempts = 0
    while candidate in existing_values and attempts < 100:
        candidate = f"{prefix}_{str(uuid.uuid4())[:8]}"
        attempts += 1
    if candidate in existing_values:
        raise RemembStorageError(f"Failed to generate unique {prefix} identifier after 100 attempts.")
    return candidate


def _workstream_latest_session_id(entries: list[dict[str, Any]]) -> str | None:
    for entry in reversed(entries):
        session_id = entry.get("session_id")
        if isinstance(session_id, str) and session_id.strip():
            return session_id.strip()
    return None


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_optional_lines(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return _normalize_handoff_lines(values)


def _workstream_state_content(structured: dict[str, Any], *, label: str) -> str:
    current_state = structured.get("current_state") or []
    open_loops = structured.get("open_loops") or []
    next_steps = structured.get("next_steps") or []
    lines = [
        f"# {label}",
        "",
        f"Goal: {structured.get('goal') or 'No goal recorded.'}",
    ]
    summary = structured.get("summary")
    if summary:
        lines.extend(["", f"Summary: {summary}"])
    if current_state:
        lines.extend(["", "Current state:", *[f"- {item}" for item in current_state]])
    if open_loops:
        lines.extend(["", "Open loops:", *[f"- {item}" for item in open_loops]])
    if next_steps:
        lines.extend(["", "Next steps:", *[f"{index + 1}. {item}" for index, item in enumerate(next_steps)]])
    return "\n".join(lines)


def _normalize_related_reference_ids(related_entries: list[str] | None) -> list[str]:
    if not related_entries:
        return []
    normalized: list[str] = []
    for item in _normalize_handoff_lines(related_entries):
        parsed = _parse_handoff_reference(item)
        entry_id = parsed.get("entry_id")
        if isinstance(entry_id, str) and entry_id and entry_id not in normalized:
            normalized.append(entry_id)
    return normalized


def _dedupe_preserving_order(values: list[str | None]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if not value or value in unique_values:
            continue
        unique_values.append(value)
    return unique_values


def _structured_list(structured: dict[str, Any], field: str) -> list[str]:
    value = structured.get(field)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _merge_compressed_context(*payloads: dict[str, Any]) -> dict[str, list[str]]:
    buckets = {
        "essential": [],
        "optional": [],
        "archived": [],
        "risky": [],
        "obsolete": [],
    }
    field_map = {
        "essential": "essential_context",
        "optional": "optional_context",
        "archived": "archived_context",
        "risky": "risk_flags",
        "obsolete": "obsolete_context",
    }
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for bucket, field in field_map.items():
            for item in _structured_list(payload, field):
                if item not in buckets[bucket]:
                    buckets[bucket].append(item)
    return buckets


def _workstream_anchor_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    for kind in ("review", "handoff", "state"):
        entry = next((item for item in reversed(entries) if item.get("entry_kind") == kind), None)
        if entry is not None:
            return entry
    return entries[-1] if entries else None


def _timeline_since_anchor(entries: list[dict[str, Any]], anchor_entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not entries:
        return []
    if anchor_entry is None:
        return [_workstream_timeline_preview(entry) for entry in reversed(entries[-5:])]
    try:
        anchor_index = next(index for index, item in enumerate(entries) if item.get("id") == anchor_entry.get("id"))
    except StopIteration:
        anchor_index = len(entries) - 1
    changed_entries = entries[anchor_index + 1 :]
    return [_workstream_timeline_preview(entry) for entry in reversed(changed_entries[-5:])]


def _review_status_from_entry(entry: dict[str, Any]) -> str:
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    status = str(structured.get("review_status") or "pending").strip().lower()
    if status not in _REVIEW_STATUS_VALUES:
        return "pending"
    return status


def _review_reasons(entry: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    if entry.get("actor_type") == "agent":
        reasons.append("agent_generated")
    if int(_current_entry_version(entry) or 1) > 1:
        reasons.append("versioned")
    entry_kind = str(entry.get("entry_kind") or "").strip()
    if entry_kind in {"decision", "artifact", "review"}:
        reasons.append(f"kind:{entry_kind}")
    if _structured_list(structured, "risk_flags"):
        reasons.append("risk_flags")
    if str(structured.get("event") or "") == "session_close":
        reasons.append("session_close")
    if entry.get("supersedes_entry_id"):
        reasons.append("superseded")
    if str(structured.get("restored_from") or "").strip():
        reasons.append("restored")
    return reasons


def _causal_context_ids(entry: dict[str, Any]) -> list[str]:
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    values = _dedupe_preserving_order([
        *(entry.get("related_entry_ids") or []),
        entry.get("parent_entry_id"),
        entry.get("supersedes_entry_id"),
        *(_structured_list(structured, "source_context_entry_ids") if isinstance(structured, dict) else []),
    ])
    return values


def _decision_is_active(entry: dict[str, Any], entries: list[dict[str, Any]]) -> bool:
    entry_id = str(entry.get("id") or "")
    if not entry_id or entry.get("entry_kind") != "decision":
        return False
    for candidate in entries:
        if candidate.get("supersedes_entry_id") == entry_id:
            return False
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    return _review_status_from_entry(entry) not in {"dismissed"} and str(structured.get("status") or "active") != "superseded"


def _workstream_operational_status(entries: list[dict[str, Any]], pending_review_count: int) -> str:
    if pending_review_count > 0:
        return "awaiting_review"
    if not entries:
        return "active"
    latest_entry = entries[-1]
    latest_kind = str(latest_entry.get("entry_kind") or "")
    structured = latest_entry.get("structured") if isinstance(latest_entry.get("structured"), dict) else {}
    latest_status = str(structured.get("status") or "").strip().lower()
    if latest_kind == "handoff":
        return "frozen"
    if latest_kind == "review" and latest_status in {"paused", "completed", "frozen"}:
        return "frozen"
    return "active"


def _session_compare_payload(session_id: str, entries: list[dict[str, Any]], resume: dict[str, Any] | None) -> dict[str, Any]:
    actor_breakdown: dict[str, int] = {}
    source_context_entry_ids: list[str] = []
    related_entry_ids: list[str] = []
    for entry in entries:
        actor_key = str(entry.get("actor_type") or "unknown")
        actor_breakdown[actor_key] = actor_breakdown.get(actor_key, 0) + 1
        for source_context_entry_id in _causal_context_ids(entry):
            if source_context_entry_id not in source_context_entry_ids:
                source_context_entry_ids.append(source_context_entry_id)
        for related_entry_id in entry.get("related_entry_ids") or []:
            if related_entry_id not in related_entry_ids:
                related_entry_ids.append(related_entry_id)
    return {
        "session_id": session_id,
        "execution_id": session_id,
        "entry_count": len(entries),
        "latest_entry_id": entries[-1].get("id") if entries else None,
        "goal": (resume or {}).get("goal") or "",
        "summary": (resume or {}).get("summary") or "",
        "current_state": list((resume or {}).get("current_state") or []),
        "open_loops": list((resume or {}).get("open_loops") or []),
        "next_steps": list((resume or {}).get("next_steps") or []),
        "focus_entry_ids": list((resume or {}).get("focus_entry_ids") or []),
        "compressed_context": dict((resume or {}).get("compressed_context") or {}),
        "what_changed": list((resume or {}).get("what_changed") or []),
        "next_execution": dict((resume or {}).get("next_execution") or {}),
        "provenance": {
            "source_context_entry_ids": source_context_entry_ids,
            "related_entry_ids": related_entry_ids,
            "actor_breakdown": actor_breakdown,
        },
        "review_pipeline": {
            "pending_count": sum(1 for entry in entries if _review_status_from_entry(entry) not in {"approved", "dismissed"} and _review_reasons(entry)),
            "finalized_count": sum(1 for entry in entries if _review_status_from_entry(entry) in {"approved", "dismissed"}),
        },
    }


def _compare_text_block(left: list[str], right: list[str], *, left_label: str, right_label: str) -> str:
    return "\n".join(
        unified_diff(
            left,
            right,
            fromfile=left_label,
            tofile=right_label,
            lineterm="",
        )
    )


def _agent_review_payload(entry: dict[str, Any], structured: dict[str, Any], review_reasons: list[str]) -> dict[str, Any]:
    risk_flags = _normalize_handoff_lines(structured.get("risk_flags"))
    source_context_entry_ids = _causal_context_ids(entry)
    current_version = int(_current_entry_version(entry) or 1)
    entry_kind = str(entry.get("entry_kind") or "")

    risk_level = "low"
    if risk_flags or entry_kind in {"decision", "review"}:
        risk_level = "medium"
    if entry.get("supersedes_entry_id") or current_version > 1:
        risk_level = "high"
    if any("approval" in flag.lower() or "human" in flag.lower() for flag in risk_flags):
        risk_level = "critical"

    priority = "low"
    if entry_kind in {"decision", "handoff", "review"} or source_context_entry_ids:
        priority = "medium"
    if risk_level in {"high", "critical"}:
        priority = "high"

    confidence = "medium"
    if not risk_flags and source_context_entry_ids:
        confidence = "high"
    if risk_level in {"high", "critical"}:
        confidence = "low"

    decision = "auto_approve"
    if str(structured.get("status") or "").strip().lower() == "superseded":
        decision = "auto_dismiss"
    elif risk_level in {"medium", "high", "critical"} or str(entry.get("actor_type") or "") == "agent":
        decision = "escalate_for_validation"

    return {
        "decision": decision,
        "risk_level": risk_level,
        "confidence": confidence,
        "priority": priority,
        "reason": "; ".join(review_reasons or ["No explicit review reason captured."]),
        "reasons": list(review_reasons or []),
        "risk_flags": risk_flags,
        "policy": {
            "mode": "agent_supervision",
            "requires_human_validation": decision == "escalate_for_validation",
            "escalation_target": "human" if decision == "escalate_for_validation" else "agent",
            "queue_bucket": f"{priority}:{risk_level}",
        },
    }


def _provenance_payload(entry: dict[str, Any], current_version: int, previous_version: int | None) -> dict[str, Any]:
    return {
        "actor": {
            "type": entry.get("actor_type") or "unknown",
            "id": entry.get("actor_id") or "",
        },
        "source_context_entry_ids": _causal_context_ids(entry),
        "related_entry_ids": list(entry.get("related_entry_ids") or []),
        "supersedes_entry_id": entry.get("supersedes_entry_id"),
        "parent_entry_id": entry.get("parent_entry_id"),
        "current_version": current_version,
        "previous_version": previous_version,
        "versioned": previous_version is not None,
        "captured_at": _entry_timestamp(entry),
    }


def _next_execution_payload(
    *,
    goal: str,
    summary: str,
    current_state: list[str],
    open_loops: list[str],
    next_steps: list[str],
    compressed_context: dict[str, list[str]],
    restore_context: dict[str, Any],
    related_entry_ids: list[str],
    focus_entry_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "goal": goal,
        "summary": summary,
        "resume_mode": "goal_oriented",
        "essential_context": list(compressed_context.get("essential") or current_state),
        "optional_context": list(compressed_context.get("optional") or []),
        "archived_context": list(compressed_context.get("archived") or []),
        "risky_context": list(compressed_context.get("risky") or []),
        "obsolete_context": list(compressed_context.get("obsolete") or []),
        "current_state": list(current_state),
        "open_loops": list(open_loops),
        "next_steps": list(next_steps),
        "restore_context": dict(restore_context),
        "related_entry_ids": list(related_entry_ids),
        "focus_entry_ids": list(focus_entry_ids or []),
    }


def _review_item(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    current_version = int(_current_entry_version(entry) or 1)
    previous_version = current_version - 1 if current_version > 1 else None
    diff_text = None
    if previous_version is not None:
        diff_payload = diff_entry_versions(root, str(entry.get("id") or ""), previous_version, current_version)
        diff_text = diff_payload.get("diff") if isinstance(diff_payload, dict) else None
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    review_reasons = _review_reasons(entry)
    agent_review = _agent_review_payload(entry, structured, review_reasons)
    return {
        "entry_id": entry.get("id"),
        "workstream_id": entry.get("workstream_id"),
        "session_id": entry.get("session_id"),
        "execution_id": entry.get("session_id"),
        "entry_kind": entry.get("entry_kind"),
        "entry_role": entry.get("entry_role"),
        "actor_type": entry.get("actor_type"),
        "actor_id": entry.get("actor_id"),
        "updated_at": _entry_timestamp(entry),
        "review_status": _review_status_from_entry(entry),
        "review_notes": _normalize_optional_text(structured.get("review_notes")) or "",
        "review_reasons": review_reasons,
        "current_version": current_version,
        "previous_version": previous_version,
        "diff": diff_text,
        "summary": _workstream_timeline_preview(entry).get("summary") or "",
        "related_entry_ids": list(entry.get("related_entry_ids") or []),
        "source_context_entry_ids": _causal_context_ids(entry),
        "supersedes_entry_id": entry.get("supersedes_entry_id"),
        "agent_review": agent_review,
        "human_validation": {
            "status": _review_status_from_entry(entry),
            "notes": _normalize_optional_text(structured.get("review_notes")) or "",
            "reason": _normalize_optional_text(structured.get("review_reason")) or "",
            "validation_notes": _normalize_optional_text(structured.get("validation_notes")) or "",
            "reviewed_at": _normalize_optional_text(structured.get("reviewed_at")) or "",
            "finalized": _review_status_from_entry(entry) in {"approved", "dismissed"},
        },
        "provenance": _provenance_payload(entry, current_version, previous_version),
    }


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
    payload = generate_handoff(
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
        "deprecated": True,
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
        "deprecated": True,
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
    return {
        "workstream_id": workstream_id,
        "session_id": session_id,
        "execution_id": session_id,
        "entry_count": len(entries),
        "review_count": len(review_items),
        "pending_review_count": sum(1 for item in review_items if item.get("review_status") not in {"approved", "dismissed"}),
        "latest_handoff": _entry_preview(latest_handoff) if latest_handoff else None,
        "latest_state": _entry_preview(latest_state) if latest_state else None,
        "latest_review": _entry_preview(latest_review) if latest_review else None,
        "resume": _session_compare_payload(session_id, entries, resume),
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
    return {
        "workstream_id": workstream_id,
        "operational_status": _workstream_operational_status(entries, sum(1 for item in review_items if item.get("review_status") not in {"approved", "dismissed"})),
        "entry_count": len(entries),
        "review_count": len(review_items),
        "pending_review_count": sum(1 for item in review_items if item.get("review_status") not in {"approved", "dismissed"}),
        "resume": resume,
        "latest_handoff": (state or {}).get("latest_handoff"),
        "latest_state": (state or {}).get("latest_state"),
        "latest_review": (state or {}).get("latest_review"),
        "review_items": review_items,
        "sessions": execution_history,
        "execution_history": execution_history,
        "execution_history_count": len(execution_history),
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
        },
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
    if left_resume is None or right_resume is None or left_state is None or right_state is None:
        return None
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
            "operational_status_changed": left_resume.get("operational_status") != right_resume.get("operational_status"),
            "left_only_open_loops": [item for item in left_resume.get("open_loops", []) if item not in right_resume.get("open_loops", [])],
            "right_only_open_loops": [item for item in right_resume.get("open_loops", []) if item not in left_resume.get("open_loops", [])],
            "left_only_focus_entry_ids": [item for item in left_resume.get("focus_entry_ids", []) if item not in right_resume.get("focus_entry_ids", [])],
            "right_only_focus_entry_ids": [item for item in right_resume.get("focus_entry_ids", []) if item not in left_resume.get("focus_entry_ids", [])],
        },
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


def _normalize_semantic_scope(semantic_scope: str) -> str:
    normalized_scope = semantic_scope.lower().strip()
    if normalized_scope not in {"global", "section"}:
        raise RemembValidationError("Invalid semantic_scope. Use 'global' or 'section'.")
    return normalized_scope


def _generate_entry_id(existing_ids: set[str]) -> str:
    new_id = str(uuid.uuid4())[:8]
    max_attempts = 100
    attempts = 0
    while new_id in existing_ids and attempts < max_attempts:
        new_id = str(uuid.uuid4())[:8]
        attempts += 1

    if new_id in existing_ids:
        raise RemembStorageError("Failed to generate unique ID after 100 attempts. Too many entries.")

    existing_ids.add(new_id)
    return new_id


def write_entries(
    root: Path,
    items: list[dict[str, Any]],
    skip_duplicates: bool = True,
    semantic_scope: str = "global",
) -> list[dict]:
    """Write multiple entries to memory atomically."""
    logger.debug(
        "write_entries called: items=%s, skip_duplicates=%s, semantic_scope=%s",
        len(items),
        skip_duplicates,
        semantic_scope,
    )
    _assert_initialized(root)
    if not items:
        raise RemembValidationError("At least one entry is required.")

    normalized_scope = _normalize_semantic_scope(semantic_scope)
    prepared_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RemembValidationError("Each batch entry must be an object.")
        if "content" not in item:
            raise RemembValidationError("Each batch entry must include content.")
        prepared_items.append(
            {
                "section": _validate_section(str(item.get("section", "project")), root),
                "content": _sanitize_content(item["content"], root),
                "tags": _sanitize_tags(item.get("tags") or [], root),
                "metadata": _extract_entry_metadata(item),
            }
        )

    def add_entries(entries: list[dict]) -> list[dict]:
        config = _store_context.get_config(root)
        max_entries = config["max_entries"]
        if len(entries) + len(prepared_items) > max_entries:
            raise RemembConfigError(f"Maximum number of entries ({max_entries}) reached. Delete some entries first.")

        if skip_duplicates:
            existing_by_key = {
                (entry["section"], entry["content"]): entry
                for entry in entries
            }
            seen_batch_keys: set[tuple[str, str]] = set()
            for item in prepared_items:
                key = (item["section"], item["content"])
                existing = existing_by_key.get(key)
                if existing:
                    raise RemembValidationError(
                        f"Duplicate entry: same content already exists in section '{item['section']}' (id: {existing['id']})"
                    )
                if key in seen_batch_keys:
                    raise RemembValidationError(
                        f"Duplicate entry: same content appears multiple times in section '{item['section']}' within the batch"
                    )
                seen_batch_keys.add(key)

            try:
                from rememb.helpers import _check_semantic_conflict

                model = _store_context.get_model(root)
                for item in prepared_items:
                    semantic_entries = entries
                    if normalized_scope == "section":
                        semantic_entries = [
                            entry for entry in entries if entry.get("section") == item["section"]
                        ]
                    conflict = _check_semantic_conflict(
                        root,
                        semantic_entries,
                        item["content"],
                        model,
                        threshold=float(config["semantic_conflict_threshold"]),
                        persist=(normalized_scope != "section"),
                    )
                    if conflict:
                        raise RemembValidationError(
                            f"Semantic Bodyguard triggered: You attempted to save something nearly identical to [id: {conflict['id']}] "
                            f"in section '{conflict['section']}'.\nIf you meant to update a rule, use the 'rememb_edit' tool with this ID instead."
                        )
            except ImportError:
                pass
            finally:
                _store_context.schedule_model_release(root)

        existing_ids = {entry["id"] for entry in entries}
        now = _now()
        created_entries: list[dict] = []
        for item in prepared_items:
            entry = {
                "id": _generate_entry_id(existing_ids),
                "section": item["section"],
                "content": item["content"],
                "tags": item["tags"],
                "version": 1,
                "history": [],
                "created_at": now,
                "updated_at": now,
            }
            entry.update(item["metadata"])
            entries.append(entry)
            created_entries.append(entry)
        logger.info("Wrote %s entries", len(created_entries))
        return created_entries

    return _atomic_modify(root, add_entries)


__all__ = [
    "init",
    "get_config",
    "update_config",
    "generate_handoff",
    "write_handoff",
    "list_handoffs",
    "list_workstreams",
    "open_workstream",
    "get_handoff",
    "get_handoff_restore_context",
    "get_workstream_state",
    "parse_handoff_restore_context",
    "read_structured_handoff",
    "resume_workstream",
    "build_handoff_package",
    "get_review_session",
    "get_review_workstream",
    "list_workstream_queue",
    "compare_sessions",
    "compare_workstreams",
    "start_session",
    "close_session",
    "close_session_with_handoff",
    "update_workstream_state",
    "list_review_queue",
    "update_review_status",
    "write_structured_handoff",
    "write_entry",
    "write_entries",
    "consolidate_entries",
    "read_entries",
    "read_entries_page",
    "search_entries",
    "delete_entry",
    "delete_entries",
    "list_entry_versions",
    "restore_entry_version",
    "diff_entry_versions",
    "restore_deleted_entry",
    "edit_entry",
    "edit_entries",
    "clear_entries",
    "format_entries",
    "get_stats",
]


def init(root: Path, project_name: str = "", global_mode: bool = False) -> Path:
    """Initialize rememb at the given root directory.
    
    Args:
        root: Project root path
        project_name: Optional project name for metadata
        global_mode: If True, initialize in global home directory
    
    Returns:
        Path to .rememb directory
    """
    logger.debug(f"init called: root={root}, project_name={project_name}, global_mode={global_mode}")
    rememb = _rememb_path(root)
    rememb.mkdir(parents=True, exist_ok=True)

    config_file = _config_path(root)
    config_data = DEFAULT_CONFIG.copy()
    if config_file.exists():
        try:
            loaded_config = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(loaded_config, dict):
                config_data.update(loaded_config)
        except (json.JSONDecodeError, OSError):
            pass

    entries_file = _entries_path(root)
    if not entries_file.exists():
        entries_file.write_text(json.dumps([], indent=2), encoding="utf-8")

    config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    _sync_meta_sections(
        root,
        list(config_data["sections"]),
        project_name=project_name or ("global" if global_mode else root.name),
    )
    _store_context.clear_config_cache(root)

    if not global_mode:
        gitignore = root / ".gitignore"
        gitignore_lines = [".rememb/embeddings.npy\n", ".rememb/embeddings.hash\n"]
        try:
            content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
            existing_lines = {line.strip() for line in content.splitlines()}
            additions = "".join(l for l in gitignore_lines if l.strip() not in existing_lines)
            if additions:
                gitignore.write_text((content.rstrip() + "\n" + additions) if content else additions, encoding="utf-8")
        except (OSError, PermissionError):
            pass

    logger.info(f"Initialized rememb at {rememb}")
    return rememb


def write_entry(
    root: Path,
    section: str,
    content: str,
    tags: list[str] | None = None,
    skip_duplicates: bool = True,
    semantic_scope: str = "global",
    *,
    meta_schema_version: int | None = None,
    workstream_id: str | None = None,
    session_id: str | None = None,
    entry_kind: str | None = None,
    entry_role: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    parent_entry_id: str | None = None,
    supersedes_entry_id: str | None = None,
    related_entry_ids: list[str] | None = None,
    structured: dict[str, Any] | None = None,
) -> dict:
    """Write a new entry to memory.
    
    Args:
        root: Project root path
        section: Section name (one of the configured sections)
        content: Entry content (1-3 sentences recommended)
        tags: Optional list of tags for categorization
        skip_duplicates: If True, reject duplicate content in same section
        semantic_scope: Scope for semantic duplicate guard: "global" or "section"
    
    Returns:
        Created entry dictionary with id, section, content, tags, timestamps
    
    Raises:
        RemembNotInitializedError: If rememb not initialized
        RemembValidationError: If section invalid or duplicate detected
        RemembConfigError: If max entries limit reached
        RemembStorageError: If ID generation fails
    """
    logger.info(f"Writing entry to section '{section}'")
    return write_entries(
        root,
        [{
            "section": section,
            "content": content,
            "tags": tags or [],
            "meta_schema_version": meta_schema_version,
            "workstream_id": workstream_id,
            "session_id": session_id,
            "entry_kind": entry_kind,
            "entry_role": entry_role,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "parent_entry_id": parent_entry_id,
            "supersedes_entry_id": supersedes_entry_id,
            "related_entry_ids": related_entry_ids,
            "structured": structured,
        }],
        skip_duplicates=skip_duplicates,
        semantic_scope=semantic_scope,
    )[0]


def get_config(root: Path) -> dict:
    """Return the effective configuration for the given root."""
    _assert_initialized(root)
    return dict(_store_context.get_config(root))


def update_config(root: Path, updates: dict[str, object]) -> dict:
    """Persist validated configuration updates for the given root."""
    _assert_initialized(root)
    current_config = _store_context.get_config(root)
    validated_config = _validate_config_updates(root, current_config, updates)
    raw_used_removed_sections = validated_config.pop("_used_removed_sections", set())
    used_removed_sections = raw_used_removed_sections if isinstance(raw_used_removed_sections, set) else set()
    raw_migration_target = validated_config.pop("_migration_target", None)
    migration_target = raw_migration_target if isinstance(raw_migration_target, str) else None
    moved_entries: dict[str, str] = {}

    try:
        if used_removed_sections and migration_target:
            moved_entries = _migrate_entries_to_section(root, used_removed_sections, migration_target)
        updated_config = _store_context.update_config(root, validated_config)
        _sync_meta_sections(root, list(updated_config["sections"]))
        return updated_config
    except Exception:
        if moved_entries:
            try:
                _restore_migrated_entries(root, moved_entries)
            except Exception:
                logger.exception("Failed to restore entries after configuration update error.")
        raise


def consolidate_entries(
    root: Path,
    section: str | None = None,
    mode: str = "exact",
    similarity_threshold: float = DEFAULT_SEMANTIC_CONFLICT_THRESHOLD,
) -> dict:
    """Consolidate entries with exact or semantic duplicate detection.

    Args:
        root: Project root path
        section: Optional section filter. When provided, only that section is deduplicated.
        mode: Consolidation mode. Supported: "exact" or "semantic".
        similarity_threshold: Cosine similarity threshold used when mode="semantic".

    Returns:
        Dictionary with consolidation summary
    """
    logger.debug(
        f"consolidate_entries called: section={section}, mode={mode}, similarity_threshold={similarity_threshold}"
    )
    _assert_initialized(root)
    target_section = _validate_section(section, root) if section else None
    normalized_mode = mode.lower().strip()

    if normalized_mode not in {"exact", "semantic"}:
        raise RemembValidationError("Invalid consolidation mode. Use 'exact' or 'semantic'.")

    if similarity_threshold <= 0 or similarity_threshold > 1:
        raise RemembValidationError("similarity_threshold must be > 0 and <= 1.")

    def _safe_int(value: object) -> int:
        return value if isinstance(value, int) else 0

    def _safe_str(value: object) -> str:
        return value if isinstance(value, str) else ""

    def _entry_key(entry: dict) -> tuple[str, str]:
        content = _safe_str(entry.get("content"))
        normalized = " ".join(content.split()).strip().lower()
        return _safe_str(entry.get("section", "context")), normalized

    def _pick_timestamp(current: str, incoming: str, *, prefer_latest: bool) -> str:
        if not current:
            return incoming
        if not incoming:
            return current
        if prefer_latest:
            return current if current >= incoming else incoming
        return current if current <= incoming else incoming

    def _pick_content(current: str, incoming: str) -> str:
        if len(incoming.strip()) > len(current.strip()):
            return incoming
        return current

    def _cosine_similarity(vec_a: object, vec_b: object) -> float:
        if not isinstance(vec_a, (list, tuple)) or not isinstance(vec_b, (list, tuple)):
            return 0.0
        if len(vec_a) == 0 or len(vec_b) == 0 or len(vec_a) != len(vec_b):
            return 0.0

        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for a, b in zip(vec_a, vec_b):
            af = float(a)
            bf = float(b)
            dot += af * bf
            norm_a += af * af
            norm_b += bf * bf

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))

    def _consolidate(entries: list[dict]) -> dict:
        total_before = len(entries)
        kept: list[dict] = []
        index_by_key: dict[tuple[str, str], int] = {}
        semantic_refs: dict[str, list[tuple[int, object]]] = {}
        removed_ids: list[str] = []
        merged_groups = 0
        model = None
        embeddings_by_idx: dict[int, object] = {}

        if normalized_mode == "semantic":
            try:
                model = _store_context.get_model(root)
                if model is None:
                    raise RemembError("Semantic model unavailable")
            except ImportError as e:
                raise RemembError(str(e)) from e
            try:
                target_indexes = []
                target_texts = []
                for idx, entry in enumerate(entries):
                    entry_section = _safe_str(entry.get("section", "context"))
                    if target_section and entry_section != target_section:
                        continue
                    target_indexes.append(idx)
                    target_texts.append(_safe_str(entry.get("content")))

                if target_texts:
                    vectors = model.encode(target_texts, show_progress_bar=False, batch_size=32)
                    for local_idx, global_idx in enumerate(target_indexes):
                        embeddings_by_idx[global_idx] = vectors[local_idx].tolist()
            finally:
                _store_context.schedule_model_release(root)

        for idx, entry in enumerate(entries):
            entry_section = _safe_str(entry.get("section", "context"))
            if target_section and entry_section != target_section:
                kept.append(entry)
                continue

            existing_idx = None
            if normalized_mode == "exact":
                key = _entry_key(entry)
                existing_idx = index_by_key.get(key)
            else:
                entry_vec = embeddings_by_idx.get(idx)
                if entry_vec is not None:
                    section_refs = semantic_refs.get(entry_section, [])
                    best_idx = None
                    best_score = -1.0
                    for kept_idx, ref_vec in section_refs:
                        score = _cosine_similarity(entry_vec, ref_vec)
                        if score >= similarity_threshold and score > best_score:
                            best_score = score
                            best_idx = kept_idx
                    existing_idx = best_idx

            if existing_idx is None:
                kept_idx = len(kept)
                kept.append(entry)
                if normalized_mode == "exact":
                    key = _entry_key(entry)
                    index_by_key[key] = kept_idx
                else:
                    entry_vec = embeddings_by_idx.get(idx)
                    if entry_vec is not None:
                        semantic_refs.setdefault(entry_section, []).append((kept_idx, entry_vec))
                continue

            merged_groups += 1
            existing = kept[existing_idx]

            existing_tags = existing.get("tags", [])
            incoming_tags = entry.get("tags", [])
            merged_tags = []
            for tag in [*existing_tags, *incoming_tags]:
                if isinstance(tag, str) and tag not in merged_tags:
                    merged_tags.append(tag)
            existing["tags"] = merged_tags

            existing["content"] = _pick_content(
                _safe_str(existing.get("content")),
                _safe_str(entry.get("content")),
            )
            existing["created_at"] = _pick_timestamp(
                _safe_str(existing.get("created_at")),
                _safe_str(entry.get("created_at")),
                prefer_latest=False,
            )
            existing["updated_at"] = _pick_timestamp(
                _safe_str(existing.get("updated_at")),
                _safe_str(entry.get("updated_at")),
                prefer_latest=True,
            )

            existing_access = _safe_int(existing.get("access_count"))
            incoming_access = _safe_int(entry.get("access_count"))
            total_access = existing_access + incoming_access
            if total_access > 0:
                existing["access_count"] = total_access

            existing_last_accessed = _safe_str(existing.get("last_accessed"))
            incoming_last_accessed = _safe_str(entry.get("last_accessed"))
            last_accessed = _pick_timestamp(
                existing_last_accessed,
                incoming_last_accessed,
                prefer_latest=True,
            )
            if last_accessed:
                existing["last_accessed"] = last_accessed

            removed_id = _safe_str(entry.get("id"))
            if removed_id:
                removed_ids.append(removed_id)

        entries[:] = kept
        removed_count = total_before - len(kept)

        return {
            "total_before": total_before,
            "total_after": len(kept),
            "removed_count": removed_count,
            "merged_groups": merged_groups,
            "removed_ids": removed_ids,
            "section": target_section,
            "mode": normalized_mode,
            "similarity_threshold": similarity_threshold,
        }

    return _atomic_modify(root, _consolidate)


def delete_entry(root: Path, entry_id: str) -> bool:
    """Delete an entry by ID.
    
    Args:
        root: Project root path
        entry_id: 8-character hexadecimal entry ID
    
    Returns:
        True if entry was deleted, False if not found
    """
    logger.debug(f"delete_entry called: entry_id={entry_id}")
    return entry_id in delete_entries(root, [entry_id])


def delete_entries(root: Path, entry_ids: list[str]) -> list[str]:
    """Soft-delete multiple entries by ID atomically."""
    logger.debug("delete_entries called: entry_ids=%s", len(entry_ids))
    _assert_initialized(root)
    if not entry_ids:
        raise RemembValidationError("At least one entry_id is required.")

    target_ids = {entry_id for entry_id in entry_ids}

    def remove_entries(entries: list[dict]) -> list[str]:
        deleted_ids: list[str] = []
        seen_deleted: set[str] = set()
        now_str = _now()
        for entry in entries:
            current_id = entry["id"]
            if current_id in target_ids and current_id not in seen_deleted:
                if _is_deleted_entry(entry):
                    continue
                history = _entry_history(entry)
                history.append(_entry_revision_snapshot(entry))
                entry["history"] = history
                entry["version"] = _current_entry_version(entry) + 1
                entry["deleted_at"] = now_str
                entry["updated_at"] = now_str
                deleted_ids.append(current_id)
                seen_deleted.add(current_id)
        if deleted_ids:
            logger.info("Deleted %s entries", len(deleted_ids))
        else:
            logger.warning("No entries found for deletion")
        return deleted_ids

    return _atomic_modify(root, remove_entries)


def restore_deleted_entry(root: Path, entry_id: str) -> dict | None:
    """Restore a soft-deleted entry by ID."""
    logger.debug("restore_deleted_entry called: entry_id=%s", entry_id)
    _assert_initialized(root)

    def restore(entries: list[dict]) -> dict | None:
        entry = _find_entry(entries, entry_id)
        if entry is None or not _is_deleted_entry(entry):
            return None
        history = _entry_history(entry)
        history.append(_entry_revision_snapshot(entry))
        entry["history"] = history
        entry["version"] = _current_entry_version(entry) + 1
        entry.pop("deleted_at", None)
        entry["updated_at"] = _now()
        return entry

    return _atomic_modify(root, restore)


def clear_entries(root: Path, *, confirm: bool = False) -> int:
    """Clear all entries from memory.
    
    Args:
        root: Project root path
        confirm: Must be True to proceed (safety guard)
    
    Returns:
        Number of entries cleared
    
    Raises:
        RemembValidationError: If confirm=False
        RemembNotInitializedError: If rememb not initialized
    """
    logger.debug(f"clear_entries called: confirm={confirm}")
    if not confirm:
        raise RemembValidationError("Clearing all entries requires confirm=True")
    _assert_initialized(root)
    
    def clear_all(entries: list[dict]) -> int:
        count = len(entries)
        entries.clear()
        
        embeddings_path = _rememb_path(root) / "embeddings.npy"
        hash_path = _rememb_path(root) / "embeddings.hash"
        if embeddings_path.exists():
            embeddings_path.unlink()
        if hash_path.exists():
            hash_path.unlink()
        
        logger.info(f"Cleared {count} entries")
        return count
    
    return _atomic_modify(root, clear_all)


def edit_entry(
    root: Path,
    entry_id: str,
    content: str | None = None,
    section: str | None = None,
    tags: list[str] | None = None,
    *,
    meta_schema_version: int | None = None,
    workstream_id: str | None = None,
    session_id: str | None = None,
    entry_kind: str | None = None,
    entry_role: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    parent_entry_id: str | None = None,
    supersedes_entry_id: str | None = None,
    related_entry_ids: list[str] | None = None,
    structured: dict[str, Any] | None = None,
) -> dict | None:
    """Edit an existing entry by ID.
    
    Args:
        root: Project root path
        entry_id: 8-character hexadecimal entry ID
        content: New content (optional)
        section: New section (optional)
        tags: New tags list (optional)
    
    Returns:
        Updated entry dictionary if found, None otherwise
    
    Raises:
        RemembValidationError: If section invalid
    """
    logger.debug(f"edit_entry called: entry_id={entry_id}, content={content is not None}, section={section is not None}, tags={tags is not None}")
    return edit_entries(
        root,
        [{
            "entry_id": entry_id,
            "content": content,
            "section": section,
            "tags": tags,
            "meta_schema_version": meta_schema_version,
            "workstream_id": workstream_id,
            "session_id": session_id,
            "entry_kind": entry_kind,
            "entry_role": entry_role,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "parent_entry_id": parent_entry_id,
            "supersedes_entry_id": supersedes_entry_id,
            "related_entry_ids": related_entry_ids,
            "structured": structured,
        }],
    )[0]


def edit_entries(root: Path, updates: list[dict[str, Any]]) -> list[dict | None]:
    """Edit multiple entries atomically."""
    logger.debug("edit_entries called: updates=%s", len(updates))
    _assert_initialized(root)
    if not updates:
        raise RemembValidationError("At least one update is required.")

    prepared_updates: list[dict[str, Any]] = []
    for update in updates:
        if not isinstance(update, dict):
            raise RemembValidationError("Each batch update must be an object.")
        entry_id = str(update.get("entry_id", "")).strip()
        if not entry_id:
            raise RemembValidationError("Each batch update must include entry_id.")
        metadata_present = any(field in update for field in _ENTRY_METADATA_FIELDS)
        if update.get("content") is None and update.get("section") is None and update.get("tags") is None and not metadata_present:
            raise RemembValidationError(
                f"Provide at least one field to update for entry {entry_id}: content, section, tags, or metadata."
            )

        prepared_update: dict[str, Any] = {"entry_id": entry_id}
        if update.get("content") is not None:
            prepared_update["content"] = _sanitize_content(update["content"], root)
        if update.get("section") is not None:
            prepared_update["section"] = _validate_section(update["section"], root)
        if update.get("tags") is not None:
            prepared_update["tags"] = _sanitize_tags(update["tags"], root)
        for field in _ENTRY_METADATA_FIELDS:
            if field not in update:
                continue
            value = update[field]
            if value is None:
                prepared_update[field] = None
            else:
                prepared_update[field] = _normalize_entry_metadata_value(field, value)
        prepared_updates.append(prepared_update)

    def modify_entries(entries: list[dict]) -> list[dict | None]:
        entries_by_id = {entry["id"]: entry for entry in entries}
        results: list[dict | None] = []
        for update in prepared_updates:
            entry = entries_by_id.get(update["entry_id"])
            if entry is None:
                results.append(None)
                continue
            history = _entry_history(entry)
            history.append(_entry_revision_snapshot(entry))
            if "content" in update:
                entry["content"] = update["content"]
            if "section" in update:
                entry["section"] = update["section"]
            if "tags" in update:
                entry["tags"] = update["tags"]
            for field in _ENTRY_METADATA_FIELDS:
                if field not in update:
                    continue
                if update[field] is None:
                    entry.pop(field, None)
                else:
                    entry[field] = update[field]
            entry["history"] = history
            entry["version"] = _current_entry_version(entry) + 1
            entry["updated_at"] = _now()
            results.append(entry)
        updated_count = sum(1 for result in results if result is not None)
        if updated_count:
            logger.info("Edited %s entries", updated_count)
        else:
            logger.warning("No entries found for editing")
        return results

    return _atomic_modify(root, modify_entries)


def read_entries(root: Path, section: str | None = None, *, include_deleted: bool = False) -> list[dict]:
    """Read entries from memory.
    
    Args:
        root: Project root path
        section: Optional section filter
        include_deleted: If True, include soft-deleted entries
    
    Returns:
        List of entry dictionaries
    
    Raises:
        RemembNotInitializedError: If rememb not initialized
    """
    logger.debug(f"read_entries called: section={section}")
    _assert_initialized(root)
    entries = _filter_deleted(_load_entries(root), include_deleted=include_deleted)
    if section:
        entries = [e for e in entries if e["section"] == section.lower()]
    logger.info(f"Read {len(entries)} entries" + (f" from section '{section}'" if section else ""))
    return entries


def read_entries_page(
    root: Path,
    section: str | None = None,
    *,
    tag: str | None = None,
    include_deleted: bool = False,
    offset: int = 0,
    limit: int = 100,
    sort_by: str = "storage",
    descending: bool = False,
) -> dict:
    """Read a page of entries from memory.

    Args:
        root: Project root path
        section: Optional section filter
        tag: Optional exact tag filter
        include_deleted: If True, include soft-deleted entries
        offset: Zero-based start index in the filtered/sorted result set
        limit: Maximum number of entries to return
        sort_by: Sort mode, either "storage" or "recent"
        descending: If True, return the selected sort in descending order

    Returns:
        Dictionary with items, total, offset, limit, next_offset, and has_more

    Raises:
        RemembNotInitializedError: If rememb not initialized
        RemembValidationError: If offset, limit, or sort_by are invalid
    """
    logger.debug(
        "read_entries_page called: section=%s, tag=%s, offset=%s, limit=%s, sort_by=%s, descending=%s",
        section,
        tag,
        offset,
        limit,
        sort_by,
        descending,
    )
    _assert_initialized(root)

    if offset < 0:
        raise RemembValidationError("offset must be >= 0")
    if limit <= 0:
        raise RemembValidationError("limit must be > 0")

    normalized_sort = sort_by.lower().strip()
    if normalized_sort not in {"storage", "recent"}:
        raise RemembValidationError("sort_by must be 'storage' or 'recent'")

    entries = _filter_deleted(_load_entries(root), include_deleted=include_deleted)
    if section:
        entries = [e for e in entries if e["section"] == section.lower()]
    if tag:
        normalized_tag = tag.lower().strip()
        entries = [e for e in entries if normalized_tag in e.get("tags", [])]

    if normalized_sort == "recent":
        entries = sorted(
            entries,
            key=lambda entry: entry.get("updated_at") or entry.get("created_at") or "",
            reverse=descending,
        )
    elif descending:
        entries = list(reversed(entries))

    total = len(entries)
    items = entries[offset:offset + limit]
    next_offset = offset + len(items)

    logger.info(
        "Read page of %s entries (offset=%s, limit=%s, total=%s)%s",
        len(items),
        offset,
        limit,
        total,
        (
            (f" from section '{section}'" if section else "")
            + (f" with tag '{tag}'" if tag else "")
        ),
    )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
        "has_more": next_offset < total,
    }


def search_entries(
    root: Path,
    query: str,
    top_k: int = 5,
    section: str | None = None,
    tag: str | None = None,
    *,
    include_deleted: bool = False,
) -> list[dict]:
    """Search entries by semantic similarity.
    
    Args:
        root: Project root path
        query: Search query (natural language or keywords)
        top_k: Maximum number of results to return
        section: Optional section filter applied before semantic search
        tag: Optional exact tag filter applied before semantic search
    
    Returns:
        List of top-k matching entries ranked by similarity
    """
    logger.debug(
        "search_entries called: query='%s', top_k=%s, section=%s, tag=%s",
        query,
        top_k,
        section,
        tag,
    )
    _assert_initialized(root)
    entries = _filter_deleted(_load_entries(root), include_deleted=include_deleted)
    if section:
        entries = [entry for entry in entries if entry.get("section") == section.lower()]
    if tag:
        normalized_tag = tag.lower().strip()
        entries = [entry for entry in entries if normalized_tag in entry.get("tags", [])]
    if not entries:
        logger.warning("No entries to search")
        return []

    try:
        model = _store_context.get_model(root)
        try:
            results = _semantic_search(root, entries, query, top_k, model, persist=not bool(section or tag))
        finally:
            _store_context.schedule_model_release(root)
    except ImportError as e:
        raise RemembError(str(e)) from e
        
    logger.info(f"Search returned {len(results)} results for query '{query}'")

    if results:
        def bump_access(all_entries: list[dict]) -> bool:
            updated = False
            result_ids = {result["id"] for result in results}
            now_str = _now()
            for entry in all_entries:
                if entry["id"] in result_ids and not _is_deleted_entry(entry):
                    entry["access_count"] = entry.get("access_count", 0) + 1
                    entry["last_accessed"] = now_str
                    updated = True
            return updated

        _atomic_modify(root, bump_access)

    return results


def get_stats(root: Path) -> dict:
    """Compute memory statistics.
    
    Args:
        root: Project root path
    
    Returns:
        Dictionary with total, by_section, size_kb, oldest, newest
    """
    _assert_initialized(root)
    entries = _load_entries(root)
    active_entries = [entry for entry in entries if not _is_deleted_entry(entry)]
    deleted_entries = [entry for entry in entries if _is_deleted_entry(entry)]
    total = len(active_entries)
    by_section = {s: 0 for s in _get_sections(root)}
    for e in active_entries:
        sec = e.get("section", "context")
        if sec not in by_section:
            by_section[sec] = 0
        by_section[sec] += 1
    entries_path = _entries_path(root)
    size_kb = round(entries_path.stat().st_size / 1024, 1) if entries_path.exists() else 0
    timestamps = sorted(e.get("created_at", "") for e in active_entries if e.get("created_at"))
    oldest = timestamps[0][:10] if timestamps else "—"
    newest = timestamps[-1][:10] if timestamps else "—"
    return {
        "total": total,
        "deleted_total": len(deleted_entries),
        "by_section": by_section,
        "size_kb": size_kb,
        "oldest": oldest,
        "newest": newest,
    }


def list_entry_versions(root: Path, entry_id: str, *, include_deleted: bool = True) -> list[dict[str, Any]]:
    """List all known revisions for an entry, oldest to newest."""
    logger.debug("list_entry_versions called: entry_id=%s", entry_id)
    _assert_initialized(root)
    entry = _find_entry(_load_entries(root), entry_id)
    if entry is None:
        return []
    if _is_deleted_entry(entry) and not include_deleted:
        return []
    return _entry_revision_list(entry)


def restore_entry_version(root: Path, entry_id: str, version: int) -> dict | None:
    """Restore an entry to a previous version as a new head revision."""
    logger.debug("restore_entry_version called: entry_id=%s, version=%s", entry_id, version)
    _assert_initialized(root)
    normalized_version = _normalize_version_number(version)

    def restore(entries: list[dict]) -> dict | None:
        entry = _find_entry(entries, entry_id)
        if entry is None:
            return None
        revision = _find_entry_revision(entry, normalized_version)
        if revision is None:
            return None
        history = _entry_history(entry)
        history.append(_entry_revision_snapshot(entry))
        entry["history"] = history
        _apply_revision(entry, revision, restore_deleted=True)
        entry["version"] = _current_entry_version(entry) + 1
        entry["updated_at"] = _now()
        return entry

    return _atomic_modify(root, restore)


def diff_entry_versions(root: Path, entry_id: str, from_version: int, to_version: int) -> dict[str, Any] | None:
    """Return a unified diff between two revisions of the same entry."""
    logger.debug(
        "diff_entry_versions called: entry_id=%s, from_version=%s, to_version=%s",
        entry_id,
        from_version,
        to_version,
    )
    _assert_initialized(root)
    normalized_from = _normalize_version_number(from_version)
    normalized_to = _normalize_version_number(to_version)
    entry = _find_entry(_load_entries(root), entry_id)
    if entry is None:
        return None
    from_revision = _find_entry_revision(entry, normalized_from)
    to_revision = _find_entry_revision(entry, normalized_to)
    if from_revision is None or to_revision is None:
        return None
    diff_text = "\n".join(
        unified_diff(
            str(from_revision.get("content", "")).splitlines(),
            str(to_revision.get("content", "")).splitlines(),
            fromfile=_revision_label(entry_id, normalized_from),
            tofile=_revision_label(entry_id, normalized_to),
            lineterm="",
        )
    )
    return {
        "entry_id": entry_id,
        "from_version": normalized_from,
        "to_version": normalized_to,
        "from_revision": from_revision,
        "to_revision": to_revision,
        "diff": diff_text,
    }


def format_entries(
    entries: list[dict],
    include_id: bool = False,
    *,
    include_score: bool = False,
    max_chars: int | None = None,
    summary_only: bool = False,
) -> str:
    """Format entries for display.
    
    Args:
        entries: List of entry dictionaries
        include_id: If True, include entry IDs in output
        include_score: If True, include semantic scores when available
        max_chars: Optional maximum number of content characters per entry
        summary_only: If True, render a compact one-line summary per entry
    
    Returns:
        Formatted markdown string
    """
    if not entries:
        return "No memory entries found."

    def _truncate(text: str) -> str:
        value = " ".join(text.split()).strip()
        if max_chars is not None and max_chars >= 0 and len(value) > max_chars:
            if max_chars <= 3:
                return value[:max_chars]
            return value[: max_chars - 3].rstrip() + "..."
        return value

    by_section: dict[str, list] = {}
    for e in entries:
        by_section.setdefault(e["section"], []).append(e)

    lines = ["# Memory Context (rememb)\n"]
    for section, items in by_section.items():
        lines.append(f"## {section.capitalize()}")
        for item in items:
            content = _truncate(str(item.get("content", "")))
            if summary_only and not content:
                content = ""
            tags = f" [{', '.join(item['tags'])}]" if item.get("tags") else ""
            score = item.get("score")
            score_text = f" (score: {float(score):.3f})" if include_score and isinstance(score, (int, float)) else ""
            prefix = f"[{item['id']}] " if include_id else ""
            if summary_only:
                lines.append(f"- {prefix}{content}{score_text}{tags}")
            else:
                ts = (item.get("updated_at") or item.get("created_at") or "")[:10]
                ts_str = f" [{ts}]" if ts else ""
                lines.append(f"- {prefix}{content}{score_text}{tags}{ts_str}")
        lines.append("")

    return "\n".join(lines)

_store_instance = type('StoreModule', (), {
    'get_config': get_config,
    'update_config': update_config,
    'write_entry': write_entry,
    'write_entries': write_entries,
    'consolidate_entries': consolidate_entries,
    'read_entries': read_entries,
    'read_entries_page': read_entries_page,
    'search_entries': search_entries,
    'delete_entry': delete_entry,
    'delete_entries': delete_entries,
    'edit_entry': edit_entry,
    'edit_entries': edit_entries,
    'clear_entries': clear_entries,
})()
assert isinstance(_store_instance, MemoryStore), "store.py must implement MemoryStore Protocol"
