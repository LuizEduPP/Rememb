"""Core storage engine for .rememb/"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REMEMB_DIR = ".rememb"
GLOBAL_REMEMB_DIR = Path.home() / ".rememb"
ENTRIES_FILE = "entries.json"
META_FILE = "meta.json"

SECTIONS = ["project", "actions", "systems", "requests", "user", "context"]


def global_root() -> Path:
    """Returns the global memory root: ~/.rememb/"""
    return Path.home()


def _rememb_path(root: Path) -> Path:
    return root / REMEMB_DIR


def _entries_path(root: Path) -> Path:
    return _rememb_path(root) / ENTRIES_FILE


def _meta_path(root: Path) -> Path:
    return _rememb_path(root) / META_FILE


def find_root(start: Optional[Path] = None, local: bool = False) -> Path:
    """Find .rememb/ root.

    Priority:
    1. Walk up from start looking for a local .rememb/ (if --local or found naturally)
    2. Fall back to global ~/.rememb/
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / REMEMB_DIR).is_dir():
            return parent

    if local:
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
        gitignore_line = ".rememb/embeddings.npy\n"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if gitignore_line.strip() not in content:
                gitignore.write_text(content.rstrip() + "\n" + gitignore_line, encoding="utf-8")

    return rememb


def write_entry(root: Path, section: str, content: str, tags: list[str] | None = None) -> dict:
    if not is_initialized(root):
        raise RuntimeError("rememb not initialized. Run `rememb init` first.")

    section = section.lower()
    if section not in SECTIONS:
        raise ValueError(f"Invalid section '{section}'. Choose from: {', '.join(SECTIONS)}")

    entries = _load_entries(root)
    entry = {
        "id": str(uuid.uuid4())[:8],
        "section": section,
        "content": content,
        "tags": tags or [],
        "created_at": _now(),
    }
    entries.append(entry)
    _save_entries(root, entries)
    return entry


def read_entries(root: Path, section: Optional[str] = None) -> list[dict]:
    if not is_initialized(root):
        raise RuntimeError("rememb not initialized. Run `rememb init` first.")
    entries = _load_entries(root)
    if section:
        entries = [e for e in entries if e["section"] == section.lower()]
    return entries


def search_entries(root: Path, query: str, top_k: int = 5) -> list[dict]:
    """Semantic search using sentence-transformers. Falls back to keyword search."""
    entries = _load_entries(root)
    if not entries:
        return []

    try:
        return _semantic_search(root, entries, query, top_k)
    except Exception:
        return _keyword_search(entries, query, top_k)


def _semantic_search(root: Path, entries: list[dict], query: str, top_k: int) -> list[dict]:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [e["content"] for e in entries]

    embeddings_path = _rememb_path(root) / "embeddings.npy"
    if embeddings_path.exists():
        embeddings = np.load(str(embeddings_path))
        if len(embeddings) != len(texts):
            embeddings = model.encode(texts)
            np.save(str(embeddings_path), embeddings)
    else:
        embeddings = model.encode(texts)
        np.save(str(embeddings_path), embeddings)

    query_vec = model.encode([query])[0]
    scores = np.dot(embeddings, query_vec) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec) + 1e-9
    )
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [entries[i] for i in top_indices]


def _keyword_search(entries: list[dict], query: str, top_k: int) -> list[dict]:
    q = query.lower()
    scored = []
    for entry in entries:
        score = entry["content"].lower().count(q)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def _load_entries(root: Path) -> list[dict]:
    raw = _entries_path(root).read_text(encoding="utf-8")
    return json.loads(raw)


def _save_entries(root: Path, entries: list[dict]) -> None:
    _entries_path(root).write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
