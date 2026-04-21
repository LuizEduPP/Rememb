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
from rememb.config import META_FILE, SECTIONS
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
    "write_entry",
    "read_entries",
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


def write_entry(root: Path, section: str, content: str, tags: list[str] | None = None, skip_duplicates: bool = True) -> dict:
    """Write a new entry to memory.
    
    Args:
        root: Project root path
        section: Section name (one of SECTIONS)
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
    logger.debug(f"write_entry called: section={section}, skip_duplicates={skip_duplicates}")
    _assert_initialized(root)
    section = _validate_section(section)

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
                model = _store_context.get_model()
                conflict = _check_semantic_conflict(root, entries, content, model)
                if conflict:
                    raise RemembValidationError(
                        f"🚨 Semantic Bodyguard triggered: You attempted to save something nearly identical to [id: {conflict['id']}] "
                        f"in section '{conflict['section']}'.\nIf you meant to update a rule, use the 'rememb_edit' tool with this ID instead."
                    )
            except ImportError:
                pass
        
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
        model = _store_context.get_model()
        results = _semantic_search(root, entries, query, top_k, model)
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
    'write_entry': write_entry,
    'read_entries': read_entries,
    'search_entries': search_entries,
    'delete_entry': delete_entry,
    'edit_entry': edit_entry,
    'clear_entries': clear_entries,
})()
assert isinstance(_store_instance, MemoryStore), "store.py must implement MemoryStore Protocol"
