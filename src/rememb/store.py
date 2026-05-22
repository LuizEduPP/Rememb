from __future__ import annotations

import json
import logging
from difflib import unified_diff
import uuid
from pathlib import Path
from typing import Any

from rememb.exceptions import (
    RemembNotInitializedError,
    RemembValidationError,
    RemembStorageError,
    RemembConfigError,
    RemembError,
)
from rememb.config import DEFAULT_CONFIG, DEFAULT_REMOVED_SECTION_NAME, DEFAULT_SEMANTIC_CONFLICT_THRESHOLD
from rememb.utils import _rememb_path, _entries_path, _meta_path, _config_path, _now
from rememb.helpers import (
    MemoryStore,
    _load_entries,
    _atomic_modify,
    _get_sections,
    _is_hex_color,
    _normalize_sections,
    _normalize_section_colors,
    _save_json_object,
    _semantic_search,
    _sanitize_content,
    _sanitize_tags,
    _store_context,
    _validate_section,
    _assert_initialized,
)

logger = logging.getLogger(__name__)


_POSITIVE_INT_CONFIG_KEYS = {
    "max_content_length",
    "max_tag_length",
    "max_tags_per_entry",
    "max_entries",
    "entry_batch_size",
}

_NON_NEGATIVE_INT_CONFIG_KEYS = {
    "semantic_model_idle_ttl_seconds",
    "entry_load_threshold",
}

_FLOAT_0_1_CONFIG_KEYS = {
    "semantic_conflict_threshold",
}


def _current_entry_version(entry: dict[str, Any]) -> int:
    raw_version = entry.get("version", 1)
    try:
        parsed_version = int(str(raw_version).strip())
    except (TypeError, ValueError):
        return 1
    return parsed_version if parsed_version > 0 else 1


def _entry_history(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw_history = entry.get("history")
    if not isinstance(raw_history, list):
        return []
    return [dict(item) for item in raw_history if isinstance(item, dict)]


def _entry_revision_snapshot(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": _current_entry_version(entry),
        "section": str(entry.get("section", "")),
        "content": str(entry.get("content", "")),
        "tags": list(entry.get("tags", [])) if isinstance(entry.get("tags"), list) else [],
        "created_at": str(entry.get("created_at", "")),
        "updated_at": str(entry.get("updated_at", "")),
        "deleted_at": str(entry.get("deleted_at", "")),
    }


def _deleted_at(entry: dict[str, Any]) -> str | None:
    value = str(entry.get("deleted_at", "")).strip()
    return value or None


def _is_deleted_entry(entry: dict[str, Any]) -> bool:
    return _deleted_at(entry) is not None


def _filter_deleted(entries: list[dict[str, Any]], *, include_deleted: bool) -> list[dict[str, Any]]:
    if include_deleted:
        return list(entries)
    return [entry for entry in entries if not _is_deleted_entry(entry)]


def _entry_revision_list(entry: dict[str, Any]) -> list[dict[str, Any]]:
    revisions = _entry_history(entry)
    revisions.append(_entry_revision_snapshot(entry))
    revisions.sort(key=lambda revision: int(revision.get("version", 1)))
    return revisions


def _find_entry(entries: list[dict[str, Any]], entry_id: str) -> dict[str, Any] | None:
    for entry in entries:
        if str(entry.get("id", "")) == entry_id:
            return entry
    return None


def _find_entry_revision(entry: dict[str, Any], version: int) -> dict[str, Any] | None:
    for revision in _entry_revision_list(entry):
        if int(revision.get("version", 0)) == version:
            return dict(revision)
    return None


def _apply_revision(entry: dict[str, Any], revision: dict[str, Any], *, restore_deleted: bool = False) -> None:
    entry["section"] = str(revision.get("section", ""))
    entry["content"] = str(revision.get("content", ""))
    entry["tags"] = list(revision.get("tags", [])) if isinstance(revision.get("tags"), list) else []
    if restore_deleted:
        entry.pop("deleted_at", None)


def _revision_label(entry_id: str, version: int) -> str:
    return f"{entry_id}@v{version}"


def _normalize_version_number(version: object) -> int:
    try:
        parsed = int(str(version).strip())
    except (TypeError, ValueError):
        raise RemembValidationError("version must be a positive integer.") from None
    if parsed <= 0:
        raise RemembValidationError("version must be a positive integer.")
    return parsed


def _validate_sections_config(root: Path, raw_sections: object) -> list[str]:
    if not isinstance(raw_sections, list):
        raise RemembValidationError("sections must be a list of section names.")

    for item in raw_sections:
        if not isinstance(item, str):
            raise RemembValidationError("sections must contain only strings.")

    normalized = _normalize_sections(raw_sections)

    if not normalized:
        raise RemembValidationError("At least one section is required.")

    return normalized


def _plan_section_migration(
    root: Path,
    current_sections: list[str],
    requested_sections: list[str],
) -> tuple[list[str], set[str], str | None]:
    entries = _load_entries(root)
    removed_sections = set(current_sections) - set(requested_sections)
    used_removed_sections = {
        str(entry.get("section", "")).strip().lower()
        for entry in entries
        if str(entry.get("section", "")).strip().lower() in removed_sections
    }

    final_sections = list(requested_sections)
    migration_target: str | None = None
    if used_removed_sections:
        migration_target = DEFAULT_REMOVED_SECTION_NAME
        if migration_target not in final_sections:
            final_sections.append(migration_target)

    return final_sections, used_removed_sections, migration_target


def _migrate_entries_to_section(root: Path, source_sections: set[str], target_section: str) -> dict[str, str]:
    def migrate(entries: list[dict]) -> dict[str, str]:
        moved_entries: dict[str, str] = {}
        for entry in entries:
            current_section = str(entry.get("section", "")).strip().lower()
            if current_section in source_sections:
                moved_entries[str(entry.get("id", ""))] = current_section
                entry["section"] = target_section
                entry["updated_at"] = _now()
        return moved_entries

    return _atomic_modify(root, migrate)


def _restore_migrated_entries(root: Path, moved_entries: dict[str, str]) -> None:
    if not moved_entries:
        return

    def restore(entries: list[dict]) -> None:
        for entry in entries:
            entry_id = str(entry.get("id", ""))
            if entry_id in moved_entries:
                entry["section"] = moved_entries[entry_id]
                entry["updated_at"] = _now()
        return None

    _atomic_modify(root, restore)


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
            entries.append(entry)
            created_entries.append(entry)
        logger.info("Wrote %s entries", len(created_entries))
        return created_entries

    return _atomic_modify(root, add_entries)


def _sync_meta_sections(root: Path, sections: list[str], *, project_name: str | None = None) -> None:
    meta_file = _meta_path(root)
    existing_meta: dict[str, object] = {}
    if meta_file.exists():
        try:
            loaded_meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(loaded_meta, dict):
                existing_meta = dict(loaded_meta)
        except (json.JSONDecodeError, OSError):
            existing_meta = {}

    meta = dict(existing_meta)
    meta["version"] = str(meta.get("version") or "1")
    meta["project"] = str(meta.get("project") or project_name or root.name)
    meta["created_at"] = str(meta.get("created_at") or _now())
    meta["sections"] = list(sections)
    _save_json_object(meta_file, meta)


def _validate_config_updates(
    root: Path,
    current_config: dict[str, object],
    updates: dict[str, object],
) -> dict[str, object]:
    if not isinstance(updates, dict) or not updates:
        raise RemembValidationError("Provide at least one configuration field to update.")

    next_config: dict[str, object] = dict(current_config)
    for key, value in updates.items():
        if key not in current_config:
            raise RemembValidationError(f"Unknown config key: {key}")

        if key in _POSITIVE_INT_CONFIG_KEYS:
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                raise RemembValidationError(f"{key} must be a positive integer.") from None
            if parsed <= 0:
                raise RemembValidationError(f"{key} must be a positive integer.")
            next_config[key] = parsed
            continue

        if key in _NON_NEGATIVE_INT_CONFIG_KEYS:
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                raise RemembValidationError(f"{key} must be a non-negative integer.") from None
            if parsed < 0:
                raise RemembValidationError(f"{key} must be a non-negative integer.")
            next_config[key] = parsed
            continue

        if key in _FLOAT_0_1_CONFIG_KEYS:
            try:
                parsed_f = float(str(value).strip())
            except (TypeError, ValueError):
                raise RemembValidationError(f"{key} must be a float between 0.0 and 1.0.") from None
            if not (0.0 <= parsed_f <= 1.0):
                raise RemembValidationError(f"{key} must be between 0.0 and 1.0.")
            next_config[key] = parsed_f
            continue

        if key == "semantic_model_name":
            model_name = str(value).strip()
            if not model_name:
                raise RemembValidationError("semantic_model_name cannot be empty.")
            next_config[key] = model_name
            continue

        if key == "sections":
            next_config[key] = _validate_sections_config(root, value)
            continue

        if key == "section_colors":
            if not isinstance(value, dict):
                raise RemembValidationError("section_colors must be a dictionary keyed by section name.")
            for section_name, color in value.items():
                if not isinstance(section_name, str) or not _is_hex_color(color):
                    raise RemembValidationError("section_colors values must be hex colors like #12abef.")
            next_config[key] = {str(section_name): str(color).strip().lower() for section_name, color in value.items()}
            continue

        next_config[key] = value

    current_sections = _validate_sections_config(root, current_config["sections"])
    requested_sections = _validate_sections_config(root, next_config.get("sections", current_sections))
    final_sections, used_removed_sections, migration_target = _plan_section_migration(
        root,
        current_sections,
        requested_sections,
    )
    next_config["sections"] = final_sections
    next_config["section_colors"] = _normalize_section_colors(next_config.get("section_colors"), final_sections)
    next_config["_used_removed_sections"] = used_removed_sections
    next_config["_migration_target"] = migration_target

    return next_config


__all__ = [
    "init",
    "get_config",
    "update_config",
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
        [{"section": section, "content": content, "tags": tags or []}],
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
    return edit_entries(
        root,
        [{"entry_id": entry_id, "content": content, "section": section, "tags": tags}],
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
