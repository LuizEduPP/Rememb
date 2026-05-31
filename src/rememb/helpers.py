"""Helper functions and classes for rememb operations."""

import gc
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["TQDM_DISABLE"] = "0"

try:
    import tqdm.std as tqdm_std

    tqdm_write_lock = getattr(tqdm_std, "TqdmDefaultWriteLock", None)
    if tqdm_write_lock is not None:
        tqdm_write_lock.create_mp_lock()
except Exception:
    pass

import hashlib
import json
import logging
import platform
import re
import threading
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Callable, Protocol, TypeVar, runtime_checkable

try:
    import numpy as np
except ImportError:
    np = None

from rememb.config import (
    DEFAULT_ALL_SECTION_COLOR,
    DEFAULT_REMOVED_SECTION_NAME,
    DEFAULT_SECTION_COLORS,
    DEFAULT_SECTIONS,
    DEFAULT_CONFIG,
    DEFAULT_SEMANTIC_MODEL_NAME,
    DEFAULT_SEMANTIC_CONFLICT_THRESHOLD,
    DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS,
    NON_NEGATIVE_INT_CONFIG_KEYS,
    POSITIVE_INT_CONFIG_KEYS,
    UNIT_INTERVAL_FLOAT_CONFIG_KEYS,
)
from rememb.utils import _rememb_path, _entries_path, _config_path, _meta_path, _now, is_initialized
from rememb.exceptions import (
    RemembNotInitializedError,
    RemembValidationError,
    RemembStorageError,
)

logger = logging.getLogger(__name__)

_SEARCH_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
_ModifierResult = TypeVar("_ModifierResult")


def _requires_exclusive_lock(mode: str) -> bool:
    """Return whether the file mode can mutate file contents."""
    return any(flag in mode for flag in ("+", "w", "a", "x"))


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


def _save_json_object(filepath: Path, data: dict[str, Any]) -> None:
    """Save a JSON object atomically."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)
    tmp_path = filepath.parent / (filepath.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
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

        if key in POSITIVE_INT_CONFIG_KEYS:
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                raise RemembValidationError(f"{key} must be a positive integer.") from None
            if parsed <= 0:
                raise RemembValidationError(f"{key} must be a positive integer.")
            next_config[key] = parsed
            continue

        if key in NON_NEGATIVE_INT_CONFIG_KEYS:
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                raise RemembValidationError(f"{key} must be a non-negative integer.") from None
            if parsed < 0:
                raise RemembValidationError(f"{key} must be a non-negative integer.")
            next_config[key] = parsed
            continue

        if key in UNIT_INTERVAL_FLOAT_CONFIG_KEYS:
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

@runtime_checkable
class MemoryStore(Protocol):
    """Abstract protocol for memory store operations."""
    
    def write_entry(
        self,
        root: Path,
        section: str,
        content: str,
        tags: list[str] | None = None,
        skip_duplicates: bool = True,
        semantic_scope: str = "global",
    ) -> dict:
        """Write a new entry to memory."""
        ...

    def write_entries(
        self,
        root: Path,
        items: list[dict[str, Any]],
        skip_duplicates: bool = True,
        semantic_scope: str = "global",
    ) -> list[dict]:
        """Write multiple entries to memory atomically."""
        ...
    
    def read_entries(self, root: Path, section: str | None = None) -> list[dict]:
        """Read entries from memory."""
        ...

    def read_entries_page(
        self,
        root: Path,
        section: str | None = None,
        *,
        tag: str | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "storage",
        descending: bool = False,
    ) -> dict[str, Any]:
        """Read one page of entries from memory."""
        ...

    def get_config(self, root: Path) -> dict[str, Any]:
        """Load the effective configuration for the given root."""
        ...

    def update_config(self, root: Path, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist validated configuration updates for the given root."""
        ...
    
    def search_entries(
        self,
        root: Path,
        query: str,
        top_k: int = 5,
        section: str | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        """Search entries by content or tags."""
        ...
    
    def delete_entry(self, root: Path, entry_id: str) -> bool:
        """Delete an entry by ID."""
        ...

    def delete_entries(self, root: Path, entry_ids: list[str]) -> list[str]:
        """Delete multiple entries by ID."""
        ...
    
    def edit_entry(self, root: Path, entry_id: str, content: str | None = None, section: str | None = None, tags: list[str] | None = None) -> dict | None:
        """Edit an existing entry."""
        ...

    def edit_entries(self, root: Path, updates: list[dict[str, Any]]) -> list[dict | None]:
        """Edit multiple entries atomically."""
        ...
    
    def clear_entries(self, root: Path, *, confirm: bool = False) -> int:
        """Clear all entries."""
        ...


class StoreContext:
    """Encapsulates cache and config for store operations.
    
    Manages embedding model cache and configuration cache
    to enable dependency injection and easier testing.
    """
    def __init__(self):
        self._model_cache: dict[str, Any] = {}
        self._config_cache: dict[str, dict[str, Any]] = {}
        self._model_lock = threading.Lock()
        self._model_release_timer: threading.Timer | None = None

    def clear_config_cache(self, root: Path | None = None) -> None:
        if root is None:
            self._config_cache.clear()
            return
        self._config_cache.pop(str(root), None)

    @staticmethod
    def _parse_non_negative_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def get_semantic_model_name(self, root: Path | None = None) -> str:
        env_model_name = os.getenv("REMEMB_SEMANTIC_MODEL_NAME")
        if env_model_name and env_model_name.strip():
            return env_model_name.strip()

        if root is not None:
            config = self.get_config(root)
            config_model_name = str(config.get("semantic_model_name", "")).strip()
            if config_model_name:
                return config_model_name

        return DEFAULT_SEMANTIC_MODEL_NAME

    def get_model_idle_ttl_seconds(self, root: Path | None = None) -> int:
        env_ttl = self._parse_non_negative_int(os.getenv("REMEMB_SEMANTIC_MODEL_IDLE_TTL_SECONDS"))
        if env_ttl is not None:
            return env_ttl

        if root is not None:
            config = self.get_config(root)
            config_ttl = self._parse_non_negative_int(config.get("semantic_model_idle_ttl_seconds"))
            if config_ttl is not None:
                return config_ttl

        return DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS

    def _cancel_release_timer_locked(self) -> None:
        if self._model_release_timer is not None:
            self._model_release_timer.cancel()
            self._model_release_timer = None

    def release_model(self) -> None:
        """Release the embedding model cache to free resident memory."""
        with self._model_lock:
            self._cancel_release_timer_locked()
            model = self._model_cache.pop("model", None)
            self._model_cache.pop("model_name", None)

        if model is not None:
            del model
            gc.collect()

    def schedule_model_release(self, root: Path | None = None) -> None:
        """Schedule embedding model eviction after the configured idle window."""
        idle_ttl_seconds = self.get_model_idle_ttl_seconds(root)
        if idle_ttl_seconds == 0:
            self.release_model()
            return

        with self._model_lock:
            if "model" not in self._model_cache:
                return

            self._cancel_release_timer_locked()
            timer = threading.Timer(idle_ttl_seconds, self.release_model)
            timer.daemon = True
            self._model_release_timer = timer
            timer.start()

    def get_model(self, root: Path | None = None):
        """Get or create embedding model.
        
        Returns:
            SentenceTransformer model instance (cached)
        """
        model_name = self.get_semantic_model_name(root)

        with self._model_lock:
            self._cancel_release_timer_locked()
            cached_model = self._model_cache.get("model")
            cached_model_name = self._model_cache.get("model_name")

        if cached_model is not None and cached_model_name == model_name:
            return cached_model

        if cached_model is not None and cached_model_name != model_name:
            self.release_model()

        if "model" not in self._model_cache:
            try:
                import torch
                torch.set_num_threads(1)
            except ImportError:
                pass
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name)
            with self._model_lock:
                self._model_cache["model"] = model
                self._model_cache["model_name"] = model_name
                return self._model_cache["model"]
    
    def get_config(self, root: Path) -> dict[str, Any]:
        """Load configuration from .rememb/config.json or use defaults.
        
        Args:
            root: Project root path
        
        Returns:
            Configuration dictionary with limits and settings
        """
        root_key = str(root)
        if root_key in self._config_cache:
            return self._config_cache[root_key]
        
        config_path = _config_path(root)
        config_needs_write = False
        if config_path.exists():
            try:
                loaded_config = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(loaded_config, dict):
                    config = dict(loaded_config)
                else:
                    config = {}
                    config_needs_write = True
            except (json.JSONDecodeError, OSError):
                config = {}
                config_needs_write = True
        else:
            config = {}
            config_needs_write = True

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
            _save_json_object(config_path, config)
        
        self._config_cache[root_key] = config
        return config

    def update_config(self, root: Path, config: dict[str, Any]) -> dict[str, Any]:
        """Persist validated configuration and refresh cache."""
        config_path = _config_path(root)
        _save_json_object(config_path, config)
        root_key = str(root)
        self._config_cache[root_key] = dict(config)
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
        RemembNotInitializedError: If .rememb/entries.json does not exist
    """
    if not is_initialized(root):
        raise RemembNotInitializedError("rememb not initialized. Run `rememb init` first.")

@contextmanager
def _file_lock(filepath: Path, mode: str = "r+"):
    """Backward-compatible wrapper around the shared storage file lock."""
    from rememb.storage.locking import file_lock

    with file_lock(filepath, mode=mode) as handle:
        yield handle


def _load_entries(root: Path) -> list[dict]:
    """Load entries from the configured storage backend."""
    from rememb.storage import get_storage_backend

    return get_storage_backend(root).load_entries(root)


def _save_entries(root: Path, entries: list[dict]) -> None:
    """Save entries through the configured storage backend."""
    from rememb.storage import get_storage_backend

    get_storage_backend(root).save_entries(root, entries)


def _atomic_modify(root: Path, modifier: Callable[[list[dict]], _ModifierResult]) -> _ModifierResult:
    """Execute modifier function atomically through the storage backend."""
    from rememb.storage import get_storage_backend

    return get_storage_backend(root).atomic_modify(root, modifier)

def _compute_entries_hash(entries: list[dict]) -> str:
    """Compute SHA256 hash of entries for cache validation.
    
    Args:
        entries: List of entry dictionaries
    
    Returns:
        Hexadecimal hash string
    """
    content = json.dumps(entries, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


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


def _load_or_compute_embeddings(root: Path, texts: list[str], entries: list[dict], model, *, persist: bool = True) -> Any:
    """Load embeddings from disk cache or compute and persist them."""
    numpy_module = np
    if numpy_module is None:
        raise ImportError(
            "Semantic search requires numpy and sentence-transformers.\n"
            "Install with: pip install rememb"
        )

    current_hash = _compute_entries_hash(entries)
    embeddings_path = _rememb_path(root) / "embeddings.npy"
    hash_path = _rememb_path(root) / "embeddings.hash"

    if persist and embeddings_path.exists() and hash_path.exists():
        try:
            if hash_path.read_text(encoding="utf-8") == current_hash:
                return numpy_module.load(str(embeddings_path))
        except (OSError, ValueError):
            pass

    embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
    if persist:
        numpy_module.save(str(embeddings_path), embeddings)
        hash_path.write_text(current_hash, encoding="utf-8")
    return embeddings

def _check_semantic_conflict(root: Path, entries: list[dict], content: str, model, threshold: float = DEFAULT_SEMANTIC_CONFLICT_THRESHOLD, *, persist: bool = True) -> dict | None:
    """Check if the content is semantically a duplicate of an existing entry.
    
    Args:
        root: Project root path
        entries: List of entry dictionaries
        content: New content string
        model: Embedding model instance
        
    Returns:
        Conflicting entry dictionary if found, None otherwise
    """
    if np is None or not entries:
        return None
        
    texts = [e["content"] for e in entries]
    embeddings = _load_or_compute_embeddings(root, texts, entries, model, persist=persist)
        
    query_vec = model.encode([content], show_progress_bar=False)[0]
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec)
    
    for i, e in enumerate(entries):
        base_score = np.dot(embeddings[i], query_vec) / (norms[i] if norms[i] > 0 else 1e-10)
        if base_score > threshold:
            return e
    return None


def _semantic_search(root: Path, entries: list[dict], query: str, top_k: int, model, *, persist: bool = True) -> list[dict]:
    """Perform semantic search using embeddings.
    
    Args:
        root: Project root path
        entries: List of entry dictionaries to search
        query: Search query string
        top_k: Maximum number of results to return
        model: Embedding model instance
    
    Returns:
        List of top-k entries ranked by semantic similarity
    """
    if np is None:
        raise ImportError(
            "Semantic search requires numpy and sentence-transformers.\n"
            "Install with: pip install rememb"
        )
    if model is None:
        raise ImportError(
            "Semantic search requires sentence-transformers.\n"
            "Install with: pip install rememb"
        )

    texts = [_search_document(e) for e in entries]
    embeddings = _load_or_compute_embeddings(root, texts, entries, model, persist=persist)

    query_vec = model.encode([query], show_progress_bar=False)[0]
    normalized_query = _normalize_search_text(query)
    query_tokens = _search_tokens(query)

    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec)
    scores = np.zeros(len(entries))
    
    from datetime import datetime, timezone
    now_ts = datetime.now(timezone.utc).timestamp()
    
    for i, e in enumerate(entries):
        semantic_score = np.dot(embeddings[i], query_vec) / (norms[i] if norms[i] > 0 else 1e-10)
        document = texts[i]
        document_tokens = _search_tokens(document)
        lexical_score = 0.0

        if normalized_query and normalized_query in document:
            lexical_score += 0.18

        if query_tokens and document_tokens:
            overlap_ratio = len(query_tokens & document_tokens) / len(query_tokens)
            lexical_score += overlap_ratio * 0.22

        tag_tokens: set[str] = set()
        for tag in e.get("tags", []):
            tag_tokens.update(_search_tokens(tag))
        if query_tokens and tag_tokens:
            tag_overlap_ratio = len(query_tokens & tag_tokens) / len(query_tokens)
            lexical_score += tag_overlap_ratio * 0.12

        base_score = float(semantic_score) + lexical_score

        try:
            entry_timestamp = str(e.get("updated_at") or e.get("created_at") or "")
            pts = datetime.strptime(entry_timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            days_old = (now_ts - pts) / 86400.0
            decay = max(0.92, 1.0 - (days_old * 0.0006))
            base_score *= decay
        except Exception:
            pass
            
        scores[i] = max(-1.0, base_score)

    top_indices = np.argsort(scores)[::-1][:top_k]
    ranked: list[dict] = []
    for index in top_indices:
        item = dict(entries[index])
        item["score"] = round(float(scores[index]), 4)
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


