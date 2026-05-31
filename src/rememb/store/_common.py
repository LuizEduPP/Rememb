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
    _load_entries,
    _atomic_modify,
    _get_sections,
    _migrate_entries_to_section,
    _restore_migrated_entries,
    _semantic_search,
    _sanitize_content,
    _sanitize_tags,
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


def _generate_handoff(
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


def _get_handoff(root: Path, entry_id: str, *, include_deleted: bool = True) -> dict[str, Any] | None:
    """Return a stored handoff entry by ID."""
    for handoff in list_handoffs(root, include_deleted=include_deleted):
        if str(handoff.get("id", "")) == entry_id:
            return handoff
    return None




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
    from rememb.store.crud import read_entries

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


def _execution_snapshot_payload(
    *,
    entries: list[dict[str, Any]],
    resume: dict[str, Any] | None,
    review_items: list[dict[str, Any]],
) -> dict[str, Any]:
    entry_kinds: dict[str, int] = {}
    actor_breakdown: dict[str, int] = {}
    source_context_entry_ids: list[str] = []
    related_entry_ids: list[str] = []
    supersession_chain: list[dict[str, str]] = []
    output_entry_ids: list[str] = []
    outputs_by_kind: dict[str, list[str]] = {}
    touched_sections: list[str] = []

    for entry in entries:
        entry_id = str(entry.get("id") or "").strip()
        if entry_id:
            output_entry_ids.append(entry_id)
        entry_kind = str(entry.get("entry_kind") or "memory")
        entry_kinds[entry_kind] = entry_kinds.get(entry_kind, 0) + 1
        outputs_by_kind.setdefault(entry_kind, [])
        if entry_id:
            outputs_by_kind[entry_kind].append(entry_id)

        actor_type = str(entry.get("actor_type") or "unknown")
        actor_breakdown[actor_type] = actor_breakdown.get(actor_type, 0) + 1

        for source_context_entry_id in _causal_context_ids(entry):
            if source_context_entry_id not in source_context_entry_ids:
                source_context_entry_ids.append(source_context_entry_id)
        for related_entry_id in entry.get("related_entry_ids") or []:
            if related_entry_id not in related_entry_ids:
                related_entry_ids.append(related_entry_id)

        section = str(entry.get("section") or "").strip()
        if section and section not in touched_sections:
            touched_sections.append(section)

        supersedes_entry_id = str(entry.get("supersedes_entry_id") or "").strip()
        if entry_id and supersedes_entry_id:
            structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
            supersession_chain.append(
                {
                    "entry_id": entry_id,
                    "supersedes_entry_id": supersedes_entry_id,
                    "reason": _normalize_optional_text(structured.get("review_reason"))
                    or _normalize_optional_text(structured.get("review_notes"))
                    or _normalize_optional_text(structured.get("validation_notes"))
                    or "superseded_by_newer_revision",
                }
            )

    agent_decision_counts: dict[str, int] = {}
    human_validation_counts: dict[str, int] = {}
    for item in review_items:
        agent_decision = str(((item.get("agent_review") or {}).get("decision") or "unknown"))
        human_status = str(((item.get("human_validation") or {}).get("status") or item.get("review_status") or "pending"))
        agent_decision_counts[agent_decision] = agent_decision_counts.get(agent_decision, 0) + 1
        human_validation_counts[human_status] = human_validation_counts.get(human_status, 0) + 1

    return {
        "inputs": {
            "source_context_entry_ids": source_context_entry_ids,
            "related_entry_ids": related_entry_ids,
            "focus_entry_ids": list((resume or {}).get("focus_entry_ids") or []),
            "restore_context": dict((resume or {}).get("restore_context") or {}),
            "touched_sections": touched_sections,
        },
        "outputs": {
            "entry_ids": output_entry_ids,
            "entry_kinds": entry_kinds,
            "latest_entry_id": entries[-1].get("id") if entries else None,
            "by_kind": outputs_by_kind,
        },
        "review_result": {
            "agent_decisions": agent_decision_counts,
            "human_validation": human_validation_counts,
            "pending_human_validation": sum(
                1
                for item in review_items
                if ((item.get("agent_review") or {}).get("policy") or {}).get("requires_human_validation")
                and not ((item.get("human_validation") or {}).get("finalized"))
            ),
        },
        "provenance": {
            "actor_breakdown": actor_breakdown,
            "supersession_chain": supersession_chain,
        },
    }


def _switch_gap_payload(current_resume: dict[str, Any], target_resume: dict[str, Any]) -> dict[str, Any]:
    current_state = list(current_resume.get("current_state") or [])
    current_essential = list((current_resume.get("compressed_context") or {}).get("essential") or current_state)
    target_next_execution = dict(target_resume.get("next_execution") or {})
    target_essential = list(target_next_execution.get("essential_context") or [])
    target_optional = list(target_next_execution.get("optional_context") or [])
    target_risky = list(target_next_execution.get("risky_context") or [])
    return {
        "open_now_but_not_needed": [item for item in current_state if item not in target_essential],
        "needed_now_but_not_open": [item for item in target_essential if item not in current_state and item not in current_essential],
        "optional_to_load": [item for item in target_optional if item not in current_state and item not in current_essential],
        "risky_to_carry": list(target_risky),
        "focus_entry_ids": list(target_next_execution.get("focus_entry_ids") or []),
    }


def _review_item(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    current_version = int(_current_entry_version(entry) or 1)
    previous_version = current_version - 1 if current_version > 1 else None
    diff_text = None
    if previous_version is not None:
        from rememb.store.crud import diff_entry_versions

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
        "supervision_status": "awaiting_human_validation" if agent_review.get("policy", {}).get("requires_human_validation") else "policy_resolved",
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

