from __future__ import annotations

import json
import logging
import uuid
import warnings
from difflib import unified_diff
from pathlib import Path
from typing import Any

from rememb.config import DEFAULT_CONFIG
from rememb.exceptions import (
    RemembConfigError,
    RemembError,
    RemembNotInitializedError,
    RemembStorageError,
    RemembValidationError,
)
from rememb.helpers import (
    _atomic_modify,
    _assert_initialized,
    _get_sections,
    _load_entries,
    _migrate_entries_to_section,
    _restore_migrated_entries,
    _sanitize_content,
    _sanitize_tags,
    _keyword_search,
    _store_context,
    _sync_meta_sections,
    _validate_config_updates,
    _validate_section,
)
from rememb.utils import (
    _apply_revision,
    _config_path,
    _current_entry_version,
    _deleted_at,
    _entries_db_path,
    _entries_path,
    _entry_history,
    _entry_revision_list,
    _entry_revision_snapshot,
    _filter_deleted,
    _find_entry,
    _find_entry_revision,
    _is_deleted_entry,
    _normalize_version_number,
    _now,
    _rememb_path,
    _revision_label,
)

logger = logging.getLogger(__name__)


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
) -> list[dict]:
    """Write multiple entries to memory atomically."""
    logger.debug(
        "write_entries called: items=%s, skip_duplicates=%s",
        len(items),
        skip_duplicates,
    )
    _assert_initialized(root)
    if not items:
        raise RemembValidationError("At least one entry is required.")

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
            entries.append(entry)
            created_entries.append(entry)
        logger.info("Wrote %s entries", len(created_entries))
        return created_entries

    return _atomic_modify(root, add_entries)




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

    config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    from rememb.storage import get_storage_backend, migrate_json_to_sqlite, normalize_storage_backend

    backend_name = normalize_storage_backend(config_data.get("storage_backend", "json"))
    backend = get_storage_backend(root, backend=backend_name)
    backend.ensure_initialized(root)
    if backend_name == "sqlite" and _entries_path(root).exists():
        migrate_json_to_sqlite(root)

    _sync_meta_sections(
        root,
        list(config_data["sections"]),
        project_name=project_name or ("global" if global_mode else root.name),
    )
    _store_context.clear_config_cache(root)

    if not global_mode:
        gitignore = root / ".gitignore"
        gitignore_lines = [
            ".rememb/entries.db\n",
        ]
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
) -> dict:
    """Write a new entry to memory.
    
    Args:
        root: Project root path
        section: Section name (one of the configured sections)
        content: Entry content (1-3 sentences recommended)
        tags: Optional list of tags for categorization
        skip_duplicates: If True, reject duplicate content in same section
    
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
        }],
        skip_duplicates=skip_duplicates,
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
        previous_backend = str(current_config.get("storage_backend") or "json")
        updated_config = _store_context.update_config(root, validated_config)
        next_backend = str(updated_config.get("storage_backend") or "json")
        if previous_backend != "sqlite" and next_backend == "sqlite":
            from rememb.storage import migrate_json_to_sqlite

            migrate_json_to_sqlite(root)
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
) -> dict:
    """Consolidate entries with exact duplicate detection.

    Args:
        root: Project root path
        section: Optional section filter. When provided, only that section is deduplicated.

    Returns:
        Dictionary with consolidation summary
    """
    logger.debug("consolidate_entries called: section=%s", section)
    _assert_initialized(root)
    target_section = _validate_section(section, root) if section else None

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

    def _consolidate(entries: list[dict]) -> dict:
        total_before = len(entries)
        kept: list[dict] = []
        index_by_key: dict[tuple[str, str], int] = {}
        removed_ids: list[str] = []
        merged_groups = 0

        for entry in entries:
            entry_section = _safe_str(entry.get("section", "context"))
            if target_section and entry_section != target_section:
                kept.append(entry)
                continue

            key = _entry_key(entry)
            existing_idx = index_by_key.get(key)

            if existing_idx is None:
                kept_idx = len(kept)
                kept.append(entry)
                index_by_key[key] = kept_idx
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
            "mode": "exact",
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
        logger.info(f"Cleared {count} entries")
        return count
    
    return _atomic_modify(root, clear_all)


def edit_entry(
    root: Path,
    entry_id: str,
    content: str | None = None,
    section: str | None = None,
    tags: list[str] | None = None,
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
        if update.get("content") is None and update.get("section") is None and update.get("tags") is None:
            raise RemembValidationError(
                f"Provide at least one field to update for entry {entry_id}: content, section, or tags."
            )

        prepared_update: dict[str, Any] = {"entry_id": entry_id}
        if update.get("content") is not None:
            prepared_update["content"] = _sanitize_content(update["content"], root)
        if update.get("section") is not None:
            prepared_update["section"] = _validate_section(update["section"], root)
        if update.get("tags") is not None:
            prepared_update["tags"] = _sanitize_tags(update["tags"], root)
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
    """Search entries by keyword and token overlap.

    Semantic relevance is left to the calling agent. This function performs
    deterministic lexical matching and returns the top_k highest-scoring entries.

    Args:
        root: Project root path
        query: Search query (keywords or short phrases)
        top_k: Maximum number of results to return
        section: Optional section filter applied before search
        tag: Optional exact tag filter applied before search

    Returns:
        List of top-k matching entries ranked by lexical score
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

    results = _keyword_search(entries, query, top_k)

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
    db_path = _entries_db_path(root)
    if db_path.exists():
        size_kb = round(db_path.stat().st_size / 1024, 1)
    elif entries_path.exists():
        size_kb = round(entries_path.stat().st_size / 1024, 1)
    else:
        size_kb = 0
    config = _store_context.get_config(root)
    storage_backend = str(config.get("storage_backend") or "json")
    timestamps = sorted(e.get("created_at", "") for e in active_entries if e.get("created_at"))
    oldest = timestamps[0][:10] if timestamps else "—"
    newest = timestamps[-1][:10] if timestamps else "—"
    return {
        "total": total,
        "deleted_total": len(deleted_entries),
        "by_section": by_section,
        "size_kb": size_kb,
        "storage_backend": storage_backend,
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


AGENT_SUMMARIZE_THRESHOLD = 8


def agent_summarize_hint(entry_count: int, *, has_more: bool = False) -> str:
    """Return guidance for the calling agent when a read payload is large."""
    if entry_count < AGENT_SUMMARIZE_THRESHOLD and not has_more:
        return ""
    more = " More pages may remain." if has_more else ""
    return (
        f"\n---\nAgent note: {entry_count} entries returned.{more} "
        "Summarize task-relevant facts in your working context. "
        "Narrow with section, tag, rememb_search, or smaller rememb_read_page limits when needed."
    )


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
        max_chars: Optional mechanical cap on content characters per entry
        summary_only: Deprecated. Ignored; agents summarize semantically after reads.
    
    Returns:
        Formatted markdown string
    """
    if summary_only:
        warnings.warn(
            "summary_only is deprecated; rememb returns full entry content and agents summarize semantically.",
            DeprecationWarning,
            stacklevel=2,
        )

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
            tags = f" [{', '.join(item['tags'])}]" if item.get("tags") else ""
            score = item.get("score")
            score_text = f" (score: {float(score):.3f})" if include_score and isinstance(score, (int, float)) else ""
            prefix = f"[{item['id']}] " if include_id else ""
            ts = (item.get("updated_at") or item.get("created_at") or "")[:10]
            ts_str = f" [{ts}]" if ts else ""
            lines.append(f"- {prefix}{content}{score_text}{tags}{ts_str}")
        lines.append("")

    return "\n".join(lines)
