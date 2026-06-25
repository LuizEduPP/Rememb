"""Agent-oriented store helpers for targeted reads and discovery."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rememb.exceptions import RemembValidationError
from rememb.helpers import _assert_initialized, _load_entries
from rememb.store.crud import read_entries
from rememb.utils import _find_entry, _filter_deleted, _validate_entry_id

logger = logging.getLogger(__name__)


def get_entry(root: Path, entry_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    """Return one entry by ID."""
    if not _validate_entry_id(entry_id):
        raise RemembValidationError(f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")
    _assert_initialized(root)
    entries = _filter_deleted(_load_entries(root), include_deleted=include_deleted)
    return _find_entry(entries, entry_id.lower())


def list_entry_tags(root: Path, *, include_deleted: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    """Return tags with usage counts, sorted by frequency."""
    _assert_initialized(root)
    counts: dict[str, int] = {}
    for entry in _filter_deleted(_load_entries(root), include_deleted=include_deleted):
        for tag in entry.get("tags", []):
            if isinstance(tag, str) and tag.strip():
                normalized = tag.strip().lower()
                counts[normalized] = counts.get(normalized, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if limit > 0:
        ranked = ranked[:limit]
    return [{"tag": tag, "count": count} for tag, count in ranked]


def read_recent_entries(
    root: Path,
    *,
    limit: int = 10,
    section: str | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Return recently updated entries."""
    if limit <= 0:
        raise RemembValidationError("limit must be > 0")
    entries = read_entries(root, section, include_deleted=include_deleted)
    entries.sort(
        key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""),
        reverse=True,
    )
    return entries[:limit]
