"""Helper functions and classes for rememb operations."""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["TQDM_DISABLE"] = "0"

try:
    from tqdm.std import TqdmDefaultWriteLock
    TqdmDefaultWriteLock.create_mp_lock()
except Exception:
    pass

import hashlib
import json
import logging
import platform
import re
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, runtime_checkable

try:
    import numpy as np
except ImportError:
    np = None

from rememb.config import (
    SECTIONS,
    CONFIG_FILE,
    DEFAULT_MAX_CONTENT_LENGTH,
    DEFAULT_MAX_TAG_LENGTH,
    DEFAULT_MAX_TAGS_PER_ENTRY,
    DEFAULT_MAX_ENTRIES,
)
from rememb.utils import _rememb_path, _entries_path, is_initialized
from rememb.exceptions import (
    RemembNotInitializedError,
    RemembValidationError,
    RemembStorageError,
)

logger = logging.getLogger(__name__)

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
    
    def read_entries(self, root: Path, section: str | None = None) -> list[dict]:
        """Read entries from memory."""
        ...
    
    def search_entries(self, root: Path, query: str, top_k: int = 5) -> list[dict]:
        """Search entries by content or tags."""
        ...
    
    def delete_entry(self, root: Path, entry_id: str) -> bool:
        """Delete an entry by ID."""
        ...
    
    def edit_entry(self, root: Path, entry_id: str, content: str | None = None, section: str | None = None, tags: list[str] | None = None) -> dict | None:
        """Edit an existing entry."""
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
        self._model_cache: dict = {}
        self._config_cache: dict = {}
    
    def get_model(self):
        """Get or create embedding model.
        
        Returns:
            SentenceTransformer model instance (cached)
        """
        if "model" not in self._model_cache:
            try:
                import torch
                torch.set_num_threads(1)
            except ImportError:
                pass
            from sentence_transformers import SentenceTransformer
            self._model_cache["model"] = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model_cache["model"]
    
    def get_config(self, root: Path) -> dict:
        """Load configuration from .rememb/config.json or use defaults.
        
        Args:
            root: Project root path
        
        Returns:
            Configuration dictionary with limits and settings
        """
        root_key = str(root)
        if root_key in self._config_cache:
            return self._config_cache[root_key]
        
        config_path = _rememb_path(root) / CONFIG_FILE
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                config = {}
        else:
            config = {}
        
        defaults = {
            "max_content_length": DEFAULT_MAX_CONTENT_LENGTH,
            "max_tag_length": DEFAULT_MAX_TAG_LENGTH,
            "max_tags_per_entry": DEFAULT_MAX_TAGS_PER_ENTRY,
            "max_entries": DEFAULT_MAX_ENTRIES,
        }
        
        for key, value in defaults.items():
            if key not in config:
                config[key] = value
        
        self._config_cache[root_key] = config
        return config


_store_context = StoreContext()


def _validate_section(section: str) -> str:
    """Validate and normalize section name.

    Args:
        section: Section name to validate

    Returns:
        Lowercase section name

    Raises:
        RemembValidationError: If section is not in SECTIONS
    """
    section = section.lower()
    if section not in SECTIONS:
        raise RemembValidationError(f"Invalid section '{section}'. Choose from: {', '.join(SECTIONS)}")
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
    """Context manager for cross-platform file locking.
    
    Args:
        filepath: Path to file to lock
        mode: File mode (r+ for read/write, r for read)
    
    Yields:
        Open file handle with lock acquired
    """
    if not filepath.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("[]", encoding="utf-8")
    
    f = open(filepath, mode, encoding="utf-8")
    is_windows = platform.system() == "Windows"
    try:
        if is_windows:
            import msvcrt
            lock_mode = 2 if "w" in mode else 0
            msvcrt.locking(f.fileno(), lock_mode, -1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX if "w" in mode else fcntl.LOCK_SH)
        yield f
    finally:
        if is_windows:
            import msvcrt
            msvcrt.locking(f.fileno(), 0, -1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _load_entries(root: Path) -> list[dict]:
    """Load entries from JSON file with corruption recovery.
    
    Args:
        root: Project root path
    
    Returns:
        List of entry dictionaries
    
    Raises:
        RemembStorageError: If file is corrupted and recovery fails
    """
    filepath = _entries_path(root)
    with _file_lock(filepath, mode="r") as f:
        raw = f.read()
    try:
        entries = json.loads(raw)
        logger.debug(f"Loaded {len(entries)} entries from {filepath}")
        return entries
    except json.JSONDecodeError as e:
        backup_path = filepath.parent / (filepath.name + ".corrupted")
        try:
            if not backup_path.exists():
                backup_path.write_bytes(filepath.read_bytes())
        except OSError:
            pass
        
        try:
            entries = []
            raw_stripped = raw.strip()
            if raw_stripped.startswith("["):
                json_objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw)
                for obj_str in json_objects:
                    try:
                        entry = json.loads(obj_str)
                        if isinstance(entry, dict) and "id" in entry:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            
            if entries:
                _save_entries(root, entries)
                return entries
        except Exception:
            pass
        
        raise RemembStorageError(
            f"Memory file is corrupted ({filepath}): {e}\n"
            f"Backup saved to {backup_path}. Delete {filepath} to reset."
        ) from e


def _save_entries(root: Path, entries: list[dict]) -> None:
    """Save entries to JSON file atomically.
    
    Args:
        root: Project root path
        entries: List of entry dictionaries to save
    """
    filepath = _entries_path(root)
    data = json.dumps(entries, indent=2)
    tmp_path = filepath.parent / (filepath.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(filepath)
        logger.debug(f"Saved {len(entries)} entries to {filepath}")
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _atomic_modify(root: Path, modifier) -> any:
    """Execute modifier function atomically with file lock.
    
    Args:
        root: Project root path
        modifier: Function that takes entries list and returns modified result
    
    Returns:
        Result from modifier function
    
    Raises:
        RemembStorageError: If file is corrupted
    """
    filepath = _entries_path(root)
    with _file_lock(filepath, mode="r+") as f:
        raw = f.read()
        logger.debug(f"Atomic modify on {filepath}")
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RemembStorageError(
                f"Memory file is corrupted ({filepath}): {e}\n"
                f"Fix manually or delete {filepath} to reset."
            ) from e
        
        result = modifier(entries)
        
        data = json.dumps(entries, indent=2)
        f.seek(0)
        f.write(data)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
        return result

def _compute_entries_hash(entries: list[dict]) -> str:
    """Compute SHA256 hash of entries for cache validation.
    
    Args:
        entries: List of entry dictionaries
    
    Returns:
        Hexadecimal hash string
    """
    content = json.dumps(entries, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()

def _check_semantic_conflict(root: Path, entries: list[dict], content: str, model) -> dict | None:
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
    current_hash = _compute_entries_hash(entries)
    embeddings_path = _rememb_path(root) / "embeddings.npy"
    hash_path = _rememb_path(root) / "embeddings.hash"
    
    cache_valid = False
    if embeddings_path.exists() and hash_path.exists():
        try:
            if hash_path.read_text(encoding="utf-8") == current_hash:
                embeddings = np.load(str(embeddings_path))
                cache_valid = True
        except (OSError, ValueError):
            pass
            
    if not cache_valid:
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
        np.save(str(embeddings_path), embeddings)
        hash_path.write_text(current_hash, encoding="utf-8")
        
    query_vec = model.encode([content], show_progress_bar=False)[0]
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec)
    
    for i, e in enumerate(entries):
        base_score = np.dot(embeddings[i], query_vec) / (norms[i] if norms[i] > 0 else 1e-10)
        if base_score > 0.88:
            return e
    return None


def _semantic_search(root: Path, entries: list[dict], query: str, top_k: int, model) -> list[dict]:
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
            "Install with: pip install rememb[semantic]"
        )
    if model is None:
        raise ImportError(
            "Semantic search requires sentence-transformers.\n"
            "Install with: pip install rememb[semantic]"
        )

    texts = [e["content"] for e in entries]
    
    current_hash = _compute_entries_hash(entries)
    embeddings_path = _rememb_path(root) / "embeddings.npy"
    hash_path = _rememb_path(root) / "embeddings.hash"
    
    cache_valid = False
    if embeddings_path.exists() and hash_path.exists():
        try:
            stored_hash = hash_path.read_text(encoding="utf-8")
            if stored_hash == current_hash:
                embeddings = np.load(str(embeddings_path))
                cache_valid = True
        except (OSError, ValueError):
            pass
    
    if not cache_valid:
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
        np.save(str(embeddings_path), embeddings)
        hash_path.write_text(current_hash, encoding="utf-8")
    
    query_vec = model.encode([query], show_progress_bar=False)[0]
    
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec)
    scores = np.zeros(len(entries))
    
    query_lower = query.lower()
    query_tokens = [t for t in re.split(r'\W+', query_lower) if len(t) > 2]
    
    from datetime import datetime, timezone
    now_ts = datetime.now(timezone.utc).timestamp()
    
    for i, e in enumerate(entries):
        base_score = np.dot(embeddings[i], query_vec) / (norms[i] if norms[i] > 0 else 1e-10)
        
        content_lower = e["content"].lower()
        if query_lower in content_lower:
            base_score += 0.3
        else:
            matches = sum(1 for t in query_tokens if t in content_lower)
            if matches > 0 and len(query_tokens) > 0:
                base_score += 0.15 * (matches / len(query_tokens))
                
        try:
            pts = datetime.strptime(e.get("updated_at", e.get("created_at")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            days_old = (now_ts - pts) / 86400.0
            decay = max(0.70, 1.0 - (days_old * 0.003)) 
            base_score *= decay
        except Exception:
            pass
            
        scores[i] = base_score

    top_indices = np.argsort(scores)[::-1][:top_k]
    return [entries[i] for i in top_indices]

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
    content = " ".join(content.split())
    
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
        tag = "".join(c for c in tag if c.isalnum() or c in "-_")
        
        if len(tag) > max_tag_length:
            tag = tag[:max_tag_length]
        
        if tag and tag not in sanitized:
            sanitized.append(tag)
    
    return sanitized


