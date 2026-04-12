from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REMEMB_DIR = ".rememb"
GLOBAL_REMEMB_DIR = Path.home() / ".rememb"
ENTRIES_FILE = "entries.json"
META_FILE = "meta.json"

SECTIONS = ["project", "actions", "systems", "requests", "user", "context"]

MAX_CONTENT_LENGTH = 10000
MAX_TAG_LENGTH = 50
MAX_TAGS_PER_ENTRY = 10
MAX_ENTRIES = 10000

_model_cache: dict = {}


def _get_embedding_model():
    if "model" not in _model_cache:
        from sentence_transformers import SentenceTransformer
        _model_cache["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    return _model_cache["model"]


@contextmanager
def _file_lock(filepath: Path, mode: str = "r+"):
    import platform
    
    if not filepath.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("[]", encoding="utf-8")
    
    f = open(filepath, mode, encoding="utf-8")
    
    try:
        if platform.system() == "Windows":
            import msvcrt
            lock_mode = 2 if "w" in mode else 0
            msvcrt.locking(f.fileno(), lock_mode, 0x7FFFFFFF)
        else:
            import fcntl
            if "w" in mode:
                fcntl.flock(f, fcntl.LOCK_EX)
            else:
                fcntl.flock(f, fcntl.LOCK_SH)
        yield f
    finally:
        if platform.system() == "Windows":
            import msvcrt
            msvcrt.locking(f.fileno(), 0, 0x7FFFFFFF)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _sanitize_content(content: str) -> str:
    if not isinstance(content, str):
        raise TypeError(f"Content must be string, got {type(content).__name__}")
    
    content = "".join(c for c in content if c == "\n" or c == "\t" or ord(c) >= 32)
    
    content = re.sub(r"[ \t]+", " ", content).strip()
    
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "..."
    
    if not content.strip():
        raise ValueError("Content cannot be empty")
    
    return content


def _sanitize_tags(tags: list[str] | None) -> list[str]:
    if tags is None:
        return []
    
    if not isinstance(tags, list):
        raise TypeError(f"Tags must be list, got {type(tags).__name__}")
    
    if len(tags) > MAX_TAGS_PER_ENTRY:
        raise ValueError(f"Maximum {MAX_TAGS_PER_ENTRY} tags allowed, got {len(tags)}")
    
    sanitized = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        
        tag = tag.lower().strip()
        
        tag = re.sub(r"[^a-z0-9\-_]", "", tag)
        
        if len(tag) > MAX_TAG_LENGTH:
            tag = tag[:MAX_TAG_LENGTH]
        
        if tag and tag not in sanitized:
            sanitized.append(tag)
    
    return sanitized


def _compute_entries_hash(entries: list[dict]) -> str:
    content = json.dumps(entries, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def global_root() -> Path:
    return Path.home()


def _rememb_path(root: Path) -> Path:
    return root / REMEMB_DIR


def _entries_path(root: Path) -> Path:
    return _rememb_path(root) / ENTRIES_FILE


def _meta_path(root: Path) -> Path:
    return _rememb_path(root) / META_FILE


def find_root(start: Optional[Path] = None, local: bool = False) -> Path:
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / REMEMB_DIR).is_dir():
            return parent

    if local:
        if not os.access(current, os.W_OK):
            raise PermissionError(f"Cannot write to directory: {current}")
        return current

    return global_root()


def is_initialized(root: Path) -> bool:
    return _entries_path(root).exists()


def init(root: Path, project_name: str = "", global_mode: bool = False) -> Path:
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
        if gitignore.exists():
            try:
                content = gitignore.read_text(encoding="utf-8")
                for line in gitignore_lines:
                    if line.strip() not in content:
                        content = content.rstrip() + "\n" + line
                gitignore.write_text(content, encoding="utf-8")
            except (OSError, PermissionError):
                pass

    return rememb


def write_entry(root: Path, section: str, content: str, tags: list[str] | None = None, skip_duplicates: bool = True) -> dict:
    if not is_initialized(root):
        raise RuntimeError("rememb not initialized. Run `rememb init` first.")

    section = section.lower()
    if section not in SECTIONS:
        raise ValueError(f"Invalid section '{section}'. Choose from: {', '.join(SECTIONS)}")

    content = _sanitize_content(content)
    tags = _sanitize_tags(tags)

    entries = _load_entries(root)
    
    if len(entries) >= MAX_ENTRIES:
        raise RuntimeError(f"Maximum number of entries ({MAX_ENTRIES}) reached. Delete some entries first.")
    
    if skip_duplicates:
        for e in entries:
            if e["section"] == section and e["content"] == content:
                raise ValueError(f"Duplicate entry: same content already exists in section '{section}' (id: {e['id']})")
    
    existing_ids = {e["id"] for e in entries}
    new_id = str(uuid.uuid4())[:8]
    while new_id in existing_ids:
        new_id = str(uuid.uuid4())[:8]
    
    entry = {
        "id": new_id,
        "section": section,
        "content": content,
        "tags": tags,
        "created_at": _now(),
        "updated_at": _now(),
    }
    entries.append(entry)
    _save_entries(root, entries)
    return entry


def delete_entry(root: Path, entry_id: str) -> bool:
    entries = _load_entries(root)
    new_entries = [e for e in entries if e["id"] != entry_id]
    if len(new_entries) == len(entries):
        return False
    _save_entries(root, new_entries)
    return True


def clear_entries(root: Path, *, confirm: bool = False) -> int:
    if not confirm:
        raise RuntimeError("Clearing all entries requires confirm=True")
    
    if not is_initialized(root):
        raise RuntimeError("rememb not initialized. Run `rememb init` first.")
    
    entries = _load_entries(root)
    count = len(entries)
    
    if count > 0:
        _save_entries(root, [])
        embeddings_path = _rememb_path(root) / "embeddings.npy"
        hash_path = _rememb_path(root) / "embeddings.hash"
        if embeddings_path.exists():
            embeddings_path.unlink()
        if hash_path.exists():
            hash_path.unlink()
    
    return count


def edit_entry(root: Path, entry_id: str, content: Optional[str] = None, section: Optional[str] = None, tags: Optional[list[str]] = None) -> Optional[dict]:
    entries = _load_entries(root)
    for e in entries:
        if e["id"] == entry_id:
            if content is not None:
                e["content"] = _sanitize_content(content)
            if section is not None:
                section = section.lower()
                if section not in SECTIONS:
                    raise ValueError(f"Invalid section '{section}'. Choose from: {', '.join(SECTIONS)}")
                e["section"] = section
            if tags is not None:
                e["tags"] = _sanitize_tags(tags)
            e["updated_at"] = _now()
            _save_entries(root, entries)
            return e
    return None


def read_entries(root: Path, section: Optional[str] = None) -> list[dict]:
    if not is_initialized(root):
        raise RuntimeError("rememb not initialized. Run `rememb init` first.")
    entries = _load_entries(root)
    if section:
        entries = [e for e in entries if e["section"] == section.lower()]
    return entries


def search_entries(root: Path, query: str, top_k: int = 5) -> list[dict]:
    entries = _load_entries(root)
    if not entries:
        return []

    try:
        return _semantic_search(root, entries, query, top_k)
    except ImportError as e:
        raise RuntimeError(f"Semantic search requires: pip install rememb[semantic] ({e})")
    except (RuntimeError, ValueError, OSError) as e:
        return _keyword_search(entries, query, top_k)


def _semantic_search(root: Path, entries: list[dict], query: str, top_k: int) -> list[dict]:
    import numpy as np

    model = _get_embedding_model()
    texts = [e["content"] for e in entries]

    current_hash = _compute_entries_hash(entries)
    embeddings_path = _rememb_path(root) / "embeddings.npy"
    hash_path = _rememb_path(root) / "embeddings.hash"

    cache_valid = False
    embeddings = None

    if embeddings_path.exists() and hash_path.exists():
        stored_hash = hash_path.read_text(encoding="utf-8").strip()
        if stored_hash == current_hash:
            try:
                embeddings = np.load(str(embeddings_path))
                if len(embeddings) == len(texts):
                    cache_valid = True
            except (OSError, ValueError):
                pass

    if not cache_valid:
        embeddings = model.encode(texts, show_progress_bar=False)
        np.save(str(embeddings_path), embeddings)
        hash_path.write_text(current_hash, encoding="utf-8")

    query_vec = model.encode([query], show_progress_bar=False)[0]
    scores = np.dot(embeddings, query_vec) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec) + 1e-9
    )
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [entries[i] for i in top_indices]


def _keyword_search(entries: list[dict], query: str, top_k: int) -> list[dict]:
    tokens = query.lower().split()
    if not tokens:
        return []
    scored = []
    for entry in entries:
        text = entry["content"].lower()
        content_score = sum(text.count(t) for t in tokens)
        tags_score = sum(
            any(t in tag.lower() for t in tokens)
            for tag in entry.get("tags", [])
        ) * 2
        score = content_score + tags_score
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def _load_entries(root: Path) -> list[dict]:
    filepath = _entries_path(root)
    with _file_lock(filepath, mode="r") as f:
        raw = f.read()
        return json.loads(raw)


def _save_entries(root: Path, entries: list[dict]) -> None:
    import tempfile
    filepath = _entries_path(root)
    data = json.dumps(entries, indent=2)
    tmp_path = filepath.parent / (filepath.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(filepath)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
