"""Helper functions and classes for rememb operations."""

import json
import logging
import os
import re
import warnings
from pathlib import Path
from typing import Any, Callable, TypeVar

from rememb.config import (
    DEFAULT_ALL_SECTION_COLOR,
    DEFAULT_REMOVED_SECTION_NAME,
    DEFAULT_SECTION_COLORS,
    DEFAULT_SECTIONS,
    DEFAULT_CONFIG,
    NON_NEGATIVE_INT_CONFIG_KEYS,
    POSITIVE_INT_CONFIG_KEYS,
)
from rememb.utils import _config_path, _meta_path, _now, is_initialized, parse_int
from rememb.exceptions import (
    RemembNotInitializedError,
    RemembValidationError,
)

logger = logging.getLogger(__name__)

_SEARCH_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
_ModifierResult = TypeVar("_ModifierResult")


def _normalize_sections(value: object) -> list[str]:
    """Normalize configured sections to a unique lowercase list."""
    if not isinstance(value, list):
        return list(DEFAULT_SECTIONS)

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        section = item.strip().lower()
        if not section:
            continue
        section = "".join(char for char in section if char.isalnum() or char in "_-")
        if section and section not in normalized:
            normalized.append(section)

    return normalized or list(DEFAULT_SECTIONS)


def _copy_config_value(value: object) -> object:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _is_hex_color(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()))


def _normalize_section_colors(value: object, sections: list[str]) -> dict[str, str]:
    color_map = value if isinstance(value, dict) else {}
    normalized: dict[str, str] = {}

    for section in sections:
        color = color_map.get(section)
        if _is_hex_color(color):
            normalized[section] = str(color).strip().lower()
        elif section in DEFAULT_SECTION_COLORS:
            normalized[section] = DEFAULT_SECTION_COLORS[section]
        else:
            normalized[section] = DEFAULT_ALL_SECTION_COLOR

    return normalized


def _json_text(data: Any, *, ensure_ascii: bool = True) -> str:
    return json.dumps(data, indent=2, ensure_ascii=ensure_ascii)


def _fsync_handle(handle) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def _read_json(filepath: Path) -> Any:
    return json.loads(filepath.read_text(encoding="utf-8"))


def _read_json_dict(filepath: Path) -> dict[str, Any] | None:
    if not filepath.exists():
        return None
    try:
        loaded = _read_json(filepath)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(loaded, dict):
        return None
    return dict(loaded)


def _write_json(filepath: Path, data: Any) -> None:
    """Save JSON atomically."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_text(data)
    tmp_path = filepath.parent / (filepath.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            _fsync_handle(handle)
        tmp_path.replace(filepath)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _validate_sections_config(raw_sections: object) -> list[str]:
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


def _sync_meta_sections(root: Path, sections: list[str], *, project_name: str | None = None) -> None:
    meta_file = _meta_path(root)
    meta = dict(_read_json_dict(meta_file) or {})
    meta["version"] = str(meta.get("version") or "1")
    meta["project"] = str(meta.get("project") or project_name or root.name)
    meta["created_at"] = str(meta.get("created_at") or _now())
    meta["sections"] = list(sections)
    _write_json(meta_file, meta)


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

        if key in POSITIVE_INT_CONFIG_KEYS:
            next_config[key] = parse_int(value, name=key, minimum=1)
            continue

        if key in NON_NEGATIVE_INT_CONFIG_KEYS:
            next_config[key] = parse_int(value, name=key, minimum=0)
            continue

        if key == "sections":
            next_config[key] = _validate_sections_config(value)
            continue

        if key == "section_colors":
            if not isinstance(value, dict):
                raise RemembValidationError("section_colors must be a dictionary keyed by section name.")
            for section_name, color in value.items():
                if not isinstance(section_name, str) or not _is_hex_color(color):
                    raise RemembValidationError("section_colors values must be hex colors like #12abef.")
            next_config[key] = {str(section_name): str(color).strip().lower() for section_name, color in value.items()}
            continue

        if key == "storage_backend":
            from rememb.storage import normalize_storage_backend

            next_config[key] = normalize_storage_backend(value)
            continue

        next_config[key] = value

    current_sections = _validate_sections_config(current_config["sections"])
    requested_sections = _validate_sections_config(next_config.get("sections", current_sections))
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


class StoreContext:
    """Encapsulates configuration cache for store operations."""

    def __init__(self):
        self._config_cache: dict[str, dict[str, Any]] = {}
        self._config_cache_mtime: dict[str, float | None] = {}

    def clear_config_cache(self, root: Path | None = None) -> None:
        if root is None:
            self._config_cache.clear()
            self._config_cache_mtime.clear()
            return
        root_key = str(root)
        self._config_cache.pop(root_key, None)
        self._config_cache_mtime.pop(root_key, None)

    def get_config(self, root: Path) -> dict[str, Any]:
        """Load configuration from .rememb/config.json or use defaults.
        
        Args:
            root: Project root path
        
        Returns:
            Configuration dictionary with limits and settings
        """
        root_key = str(root)
        config_path = _config_path(root)
        current_mtime = config_path.stat().st_mtime if config_path.exists() else None
        if root_key in self._config_cache and self._config_cache_mtime.get(root_key) == current_mtime:
            return self._config_cache[root_key]
        loaded = _read_json_dict(config_path)
        if loaded is None:
            config = {}
            config_needs_write = True
        else:
            config = loaded
            config_needs_write = False

        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = _copy_config_value(value)
                config_needs_write = True

        # Remove keys that no longer exist in DEFAULT_CONFIG (stale/obsolete)
        stale_keys = [k for k in list(config) if k not in DEFAULT_CONFIG]
        if stale_keys:
            for key in stale_keys:
                del config[key]
            config_needs_write = True

        normalized_sections = _normalize_sections(config.get("sections"))
        if config.get("sections") != normalized_sections:
            config["sections"] = normalized_sections
            config_needs_write = True

        normalized_colors = _normalize_section_colors(config.get("section_colors"), normalized_sections)
        if config.get("section_colors") != normalized_colors:
            config["section_colors"] = normalized_colors
            config_needs_write = True

        if config_needs_write:
            _write_json(config_path, config)
        
        self._config_cache[root_key] = config
        self._config_cache_mtime[root_key] = current_mtime
        return config

    def update_config(self, root: Path, config: dict[str, Any]) -> dict[str, Any]:
        """Persist validated configuration and refresh cache."""
        config_path = _config_path(root)
        _write_json(config_path, config)
        root_key = str(root)
        self._config_cache[root_key] = dict(config)
        self._config_cache_mtime[root_key] = config_path.stat().st_mtime if config_path.exists() else None
        return dict(config)


_store_context = StoreContext()


def _get_sections(root: Path | None = None) -> list[str]:
    """Return the effective section list for the given root."""
    if root is None:
        return list(DEFAULT_SECTIONS)
    return list(_store_context.get_config(root)["sections"])


def _validate_section(section: str, root: Path | None = None) -> str:
    """Validate and normalize section name.

    Args:
        section: Section name to validate

    Returns:
        Lowercase section name

    Raises:
        RemembValidationError: If section is not in the configured section list
    """
    section = section.lower()
    sections = _get_sections(root)
    if section not in sections:
        raise RemembValidationError(f"Invalid section '{section}'. Choose from: {', '.join(sections)}")
    return section


def _assert_initialized(root) -> None:
    """Raise RemembNotInitializedError if rememb is not initialized.

    Args:
        root: Project root path

    Raises:
        RemembNotInitializedError: If rememb storage is not initialized
    """
    if not is_initialized(root):
        raise RemembNotInitializedError("rememb not initialized. Run `rememb init` first.")

def _backend(root: Path, backend: str | None = None):
    from rememb.storage import get_storage_backend

    return get_storage_backend(root, backend=backend)


def _load_entries(root: Path) -> list[dict]:
    """Load entries from the configured storage backend."""
    return _backend(root).load_entries(root)


def _atomic_modify(root: Path, modifier: Callable[[list[dict]], _ModifierResult]) -> _ModifierResult:
    """Execute modifier function atomically through the storage backend."""
    return _backend(root).atomic_modify(root, modifier)


def _normalize_search_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.lower().split()).strip()


def _search_tokens(value: object) -> set[str]:
    normalized = _normalize_search_text(value)
    if not normalized:
        return set()
    return {token for token in _SEARCH_TOKEN_RE.findall(normalized) if token}


def _search_document(entry: dict[str, Any]) -> str:
    content = _normalize_search_text(entry.get("content", ""))
    section = _normalize_search_text(entry.get("section", ""))
    tags = " ".join(
        _normalize_search_text(tag)
        for tag in entry.get("tags", [])
        if isinstance(tag, str)
    )
    return " ".join(part for part in (section, tags, content) if part)


def _keyword_search(
    entries: list[dict],
    query: str,
    top_k: int,
) -> list[dict]:
    """Rank entries by keyword and token overlap.

    Semantic relevance is handled by the calling agent. This function only
    performs deterministic lexical matching over section, tags, and content.
    """
    normalized_query = _normalize_search_text(query)
    query_tokens = _search_tokens(query)
    texts = [_search_document(e) for e in entries]
    scored: list[tuple[float, int]] = []

    for i, entry in enumerate(entries):
        document = texts[i]
        document_tokens = _search_tokens(document)
        score = 0.0

        if normalized_query and normalized_query in document:
            score += 1.0

        if query_tokens and document_tokens:
            score += len(query_tokens & document_tokens) / len(query_tokens)

        tag_tokens: set[str] = set()
        for tag in entry.get("tags", []):
            tag_tokens.update(_search_tokens(tag))
        if query_tokens and tag_tokens:
            score += len(query_tokens & tag_tokens) / len(query_tokens)

        if score <= 0.0:
            continue

        scored.append((score, i))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked: list[dict] = []
    for score, index in scored[:top_k]:
        item = dict(entries[index])
        item["score"] = round(float(score), 4)
        ranked.append(item)
    return ranked


def _sanitize_content(content: str, root: Path) -> str:
    """Sanitize and validate entry content.
    
    Args:
        content: Raw content to sanitize
        root: Project root path for config lookup
    
    Returns:
        Sanitized content with control chars removed and normalized whitespace
    
    Raises:
        RemembValidationError: If content is not a string, empty, or exceeds max length
    """
    if not isinstance(content, str):
        raise RemembValidationError(f"Content must be string, got {type(content).__name__}")
    
    content = "".join(c for c in content if c == "\n" or c == "\t" or ord(c) >= 32)
    normalized_lines = [" ".join(line.split()) for line in content.splitlines()]
    content = "\n".join(normalized_lines).strip()
    
    if not content.strip():
        raise RemembValidationError("Content cannot be empty")
    
    config = _store_context.get_config(root)
    max_length = config["max_content_length"]
    if len(content) > max_length:
        raise RemembValidationError(f"Content too long ({len(content)} chars, max {max_length})")
    
    return content


def _sanitize_tags(tags: list[str], root: Path) -> list[str]:
    """Sanitize and validate entry tags.
    
    Args:
        tags: List of tags to sanitize
        root: Project root path for config lookup
    
    Returns:
        Sanitized list of lowercase alphanumeric tags
    
    Raises:
        RemembValidationError: If tags is None, not a list, or too many tags
    """
    if tags is None:
        return []
    
    if not isinstance(tags, list):
        raise RemembValidationError(f"Tags must be list, got {type(tags).__name__}")
    
    config = _store_context.get_config(root)
    max_tags = config["max_tags_per_entry"]
    max_tag_length = config["max_tag_length"]
    
    if len(tags) > max_tags:
        raise RemembValidationError(f"Too many tags ({len(tags)}, max {max_tags})")
    
    sanitized = []
    for tag in tags:
        if not isinstance(tag, str):
            warnings.warn(f"Tag is not a string (type: {type(tag).__name__}), skipping. Tag: {tag}")
            continue
        
        tag = tag.lower().strip()
        tag = "".join(c for c in tag if c.isalnum() or c in "-_:")
        
        if len(tag) > max_tag_length:
            tag = tag[:max_tag_length]
        
        if tag and tag not in sanitized:
            sanitized.append(tag)
    
    return sanitized


