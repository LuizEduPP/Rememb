from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from rememb.exceptions import (
    RemembNotInitializedError,
    RemembValidationError,
    RemembStorageError,
    RemembConfigError,
    RemembError,
)
from rememb.config import CONFIG_FILE, DEFAULT_CONFIG, META_FILE, SECTIONS
from rememb.utils import _rememb_path, _entries_path, _meta_path, _now
from rememb.helpers import (
    MemoryStore,
    _load_entries,
    _atomic_modify,
    _semantic_search,
    _sanitize_content,
    _sanitize_tags,
    _store_context,
    _validate_section,
    _assert_initialized,
)

logger = logging.getLogger(__name__)


__all__ = [
    "SECTIONS",
    "init",
    "get_config",
    "write_entry",
    "consolidate_entries",
    "read_entries",
    "read_entries_page",
    "search_entries",
    "delete_entry",
    "edit_entry",
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

    entries_file = _entries_path(root)
    if not entries_file.exists():
        entries_file.write_text(json.dumps([], indent=2), encoding="utf-8")

    meta_file = _meta_path(root)
    if not meta_file.exists():
        meta = {
            "version": "1",
            "project": project_name or ("global" if global_mode else root.name),
            "created_at": _now(),
            "sections": SECTIONS,
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    config_file = rememb / CONFIG_FILE
    config_data = DEFAULT_CONFIG.copy()
    if config_file.exists():
        try:
            loaded_config = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(loaded_config, dict):
                config_data.update(loaded_config)
        except (json.JSONDecodeError, OSError):
            pass
    config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
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
) -> dict:
    """Write a new entry to memory.
    
    Args:
        root: Project root path
        section: Section name (one of SECTIONS)
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
    logger.debug(
        f"write_entry called: section={section}, skip_duplicates={skip_duplicates}, semantic_scope={semantic_scope}"
    )
    _assert_initialized(root)
    section = _validate_section(section)
    normalized_scope = semantic_scope.lower().strip()
    if normalized_scope not in {"global", "section"}:
        raise RemembValidationError("Invalid semantic_scope. Use 'global' or 'section'.")

    content = _sanitize_content(content, root)
    tags = _sanitize_tags(tags or [], root)
    logger.info(f"Writing entry to section '{section}'")

    def add_entry(entries: list[dict]) -> dict:
        config = _store_context.get_config(root)
        max_entries = config["max_entries"]
        if len(entries) >= max_entries:
            raise RemembConfigError(f"Maximum number of entries ({max_entries}) reached. Delete some entries first.")
        
        if skip_duplicates:
            for e in entries:
                if e["section"] == section and e["content"] == content:
                    raise RemembValidationError(f"Duplicate entry: same content already exists in section '{section}' (id: {e['id']})")
                    
            try:
                from rememb.helpers import _check_semantic_conflict
                model = _store_context.get_model(root)
                semantic_entries = entries
                if normalized_scope == "section":
                    semantic_entries = [e for e in entries if e.get("section") == section]
                conflict = _check_semantic_conflict(root, semantic_entries, content, model)
                if conflict:
                    raise RemembValidationError(
                        f"🚨 Semantic Bodyguard triggered: You attempted to save something nearly identical to [id: {conflict['id']}] "
                        f"in section '{conflict['section']}'.\nIf you meant to update a rule, use the 'rememb_edit' tool with this ID instead."
                    )
            except ImportError:
                pass
            finally:
                _store_context.schedule_model_release(root)
        
        existing_ids = {e["id"] for e in entries}
        new_id = str(uuid.uuid4())[:8]
        max_attempts = 100
        attempts = 0
        while new_id in existing_ids and attempts < max_attempts:
            new_id = str(uuid.uuid4())[:8]
            attempts += 1
        
        if new_id in existing_ids:
            raise RemembStorageError("Failed to generate unique ID after 100 attempts. Too many entries.")
        
        now = _now()
        entry = {
            "id": new_id,
            "section": section,
            "content": content,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
        }
        entries.append(entry)
        return entry
    
    return _atomic_modify(root, add_entry)


def get_config(root: Path) -> dict:
    """Return the effective configuration for the given root."""
    _assert_initialized(root)
    return dict(_store_context.get_config(root))


def consolidate_entries(
    root: Path,
    section: str | None = None,
    mode: str = "exact",
    similarity_threshold: float = 0.88,
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
    target_section = _validate_section(section) if section else None
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
    def remove_entry(entries: list[dict]) -> bool:
        original_len = len(entries)
        for i, e in enumerate(entries):
            if e["id"] == entry_id:
                entries.pop(i)
                logger.info(f"Deleted entry {entry_id}")
                return True
        logger.warning(f"Entry {entry_id} not found for deletion")
        return False
    
    return _atomic_modify(root, remove_entry)


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


def edit_entry(root: Path, entry_id: str, content: str | None = None, section: str | None = None, tags: list[str] | None = None) -> dict | None:
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
    def modify_entry(entries: list[dict]) -> dict | None:
        for e in entries:
            if e["id"] == entry_id:
                if content is not None:
                    e["content"] = _sanitize_content(content, root)
                if section is not None:
                    e["section"] = _validate_section(section)
                if tags is not None:
                    e["tags"] = _sanitize_tags(tags, root)
                e["updated_at"] = _now()
                logger.info(f"Edited entry {entry_id}")
                return e
        logger.warning(f"Entry {entry_id} not found for editing")
        return None
    
    return _atomic_modify(root, modify_entry)


def read_entries(root: Path, section: str | None = None) -> list[dict]:
    """Read entries from memory.
    
    Args:
        root: Project root path
        section: Optional section filter
    
    Returns:
        List of entry dictionaries
    
    Raises:
        RemembNotInitializedError: If rememb not initialized
    """
    logger.debug(f"read_entries called: section={section}")
    _assert_initialized(root)
    entries = _load_entries(root)
    if section:
        entries = [e for e in entries if e["section"] == section.lower()]
    logger.info(f"Read {len(entries)} entries" + (f" from section '{section}'" if section else ""))
    return entries


def read_entries_page(
    root: Path,
    section: str | None = None,
    *,
    offset: int = 0,
    limit: int = 100,
    sort_by: str = "storage",
    descending: bool = False,
) -> dict:
    """Read a page of entries from memory.

    Args:
        root: Project root path
        section: Optional section filter
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
        "read_entries_page called: section=%s, offset=%s, limit=%s, sort_by=%s, descending=%s",
        section,
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

    entries = _load_entries(root)
    if section:
        entries = [e for e in entries if e["section"] == section.lower()]

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
        f" from section '{section}'" if section else "",
    )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
        "has_more": next_offset < total,
    }


def search_entries(root: Path, query: str, top_k: int = 5) -> list[dict]:
    """Search entries by semantic similarity.
    
    Args:
        root: Project root path
        query: Search query (natural language or keywords)
        top_k: Maximum number of results to return
    
    Returns:
        List of top-k matching entries ranked by similarity
    """
    logger.debug(f"search_entries called: query='{query}', top_k={top_k}")
    entries = _load_entries(root)
    if not entries:
        logger.warning("No entries to search")
        return []

    try:
        model = _store_context.get_model(root)
        try:
            results = _semantic_search(root, entries, query, top_k, model)
        finally:
            _store_context.schedule_model_release(root)
    except ImportError as e:
        raise RemembError(str(e)) from e
        
    logger.info(f"Search returned {len(results)} results for query '{query}'")
    
    if results:
        def bump_access(all_entries: list[dict]) -> None:
            updated = False
            result_ids = {r["id"] for r in results}
            now_str = _now()
            for e in all_entries:
                if e["id"] in result_ids:
                    e["access_count"] = e.get("access_count", 0) + 1
                    e["last_accessed"] = now_str
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
    entries = _load_entries(root)
    total = len(entries)
    by_section = {s: 0 for s in SECTIONS}
    for e in entries:
        sec = e.get("section", "context")
        if sec in by_section:
            by_section[sec] += 1
    entries_path = _entries_path(root)
    size_kb = round(entries_path.stat().st_size / 1024, 1) if entries_path.exists() else 0
    timestamps = sorted(e.get("created_at", "") for e in entries if e.get("created_at"))
    oldest = timestamps[0][:10] if timestamps else "—"
    newest = timestamps[-1][:10] if timestamps else "—"
    return {
        "total": total,
        "by_section": by_section,
        "size_kb": size_kb,
        "oldest": oldest,
        "newest": newest,
    }


def format_entries(entries: list[dict], include_id: bool = False) -> str:
    """Format entries for display.
    
    Args:
        entries: List of entry dictionaries
        include_id: If True, include entry IDs in output
    
    Returns:
        Formatted markdown string
    """
    if not entries:
        return "No memory entries found."

    by_section: dict[str, list] = {}
    for e in entries:
        by_section.setdefault(e["section"], []).append(e)

    lines = ["# Memory Context (rememb)\n"]
    for section, items in by_section.items():
        lines.append(f"## {section.capitalize()}")
        for item in items:
            tags = f" [{', '.join(item['tags'])}]" if item.get("tags") else ""
            prefix = f"[{item['id']}] " if include_id else ""
            lines.append(f"- {prefix}{item['content']}{tags}")
        lines.append("")

    return "\n".join(lines)

_store_instance = type('StoreModule', (), {
    'get_config': get_config,
    'write_entry': write_entry,
    'consolidate_entries': consolidate_entries,
    'read_entries': read_entries,
    'read_entries_page': read_entries_page,
    'search_entries': search_entries,
    'delete_entry': delete_entry,
    'edit_entry': edit_entry,
    'clear_entries': clear_entries,
})()
assert isinstance(_store_instance, MemoryStore), "store.py must implement MemoryStore Protocol"
