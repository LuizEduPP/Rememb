"""Utility functions for rememb."""

import html
import logging
import os
import re
import warnings
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rememb.config import REMEMB_DIR, ENTRIES_FILE, ENTRIES_DB_FILE, META_FILE, CONFIG_FILE
from rememb.exceptions import RemembNotInitializedError, RemembValidationError

logger = logging.getLogger(__name__)


def _rememb_path(root: Path) -> Path:
    """Get path to .rememb directory."""
    return root / REMEMB_DIR


def _entries_path(root: Path) -> Path:
    """Get path to entries.json file."""
    return _rememb_path(root) / ENTRIES_FILE


def _entries_db_path(root: Path) -> Path:
    """Get path to entries.db file."""
    return _rememb_path(root) / ENTRIES_DB_FILE


def _meta_path(root: Path) -> Path:
    """Get path to meta.json file."""
    return _rememb_path(root) / META_FILE


def _config_path(root: Path) -> Path:
    """Get path to config.json file."""
    return _rememb_path(root) / CONFIG_FILE


def _validate_entry_id(entry_id: str) -> bool:
    """Validate entry ID format.
    
    Args:
        entry_id: Entry ID to validate
    
    Returns:
        True if entry_id matches 8 hex characters, False otherwise
    """
    return bool(re.match(r"^[a-f0-9]{8}$", entry_id, re.IGNORECASE))


def _parse_tags(tags: str | None) -> list[str] | None:
    """Parse comma-separated tags string into list.
    
    Args:
        tags: Comma-separated tags string or None
    
    Returns:
        List of tags or None if tags is None or empty
    """
    if not tags:
        return None
    return [t.strip() for t in tags.split(",")]


def _extract_summary(content: str) -> str:
    """Extract summary from content, skipping frontmatter and markdown.
    
    Args:
        content: File content to extract summary from
    
    Returns:
        First meaningful sentence or line from content
    """
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            v = value.strip()
            if len(v) > 20 and " " in v:
                return v
        content = content[fm_match.end():].strip()

    skip = re.compile(r"^(#+\s|[-*+]\s|>\s|```|\s*$)", re.IGNORECASE)
    lines = []
    for line in content.splitlines():
        if skip.match(line):
            if lines:
                break
            continue
        lines.append(line.strip())

    if lines:
        return " ".join(lines)
    return content.strip().replace("\n", " ").strip()


def _read_file_content(path: Path) -> str:
    """Read content from file based on extension.
    
    Args:
        path: File path to read
    
    Returns:
        File content as string, or empty string if error
    
    Supports:
        .md, .txt: Plain text
        .pdf: PDF text extraction (requires pypdf)
    """
    if path.suffix.lower() in {".md", ".txt"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError, PermissionError) as e:
            return ""
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return " ".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            return ""
        except (OSError, PermissionError) as e:
            return ""
        except (pypdf.PdfReadError, pypdf.PdfStreamError, ValueError) as e:
            return ""
    return ""


def _parse_simple_frontmatter(content: str) -> dict[str, str]:
    """Parse simple YAML-like frontmatter key/value pairs."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if not match:
        return {}

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        metadata[key.strip()] = value.strip().strip('"\'')
    return metadata


def _default_skill_roots() -> list[Path]:
    """Return bundled skill roots shipped with rememb."""
    import rememb_skills

    package_root = Path(rememb_skills.__file__).resolve().parent
    return [package_root] if package_root.is_dir() else []


def list_skill_definitions(skill_roots: list[Path] | None = None) -> list[dict[str, str]]:
    """List local skills discovered from configured skill roots."""
    definitions: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for root in skill_roots or _default_skill_roots():
        if not root.is_dir():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            resolved = str(skill_file.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            content = _read_file_content(skill_file)
            metadata = _parse_simple_frontmatter(content)
            identifier = skill_file.parent.name
            name = metadata.get("name") or identifier
            description = metadata.get("description") or _extract_summary(content)
            definitions.append(
                {
                    "id": identifier,
                    "name": name,
                    "description": description,
                    "path": str(skill_file),
                    "root": str(root),
                }
            )

    definitions.sort(key=lambda item: (item["name"].lower(), item["id"].lower(), item["path"]))
    return definitions


_SKILL_SKIP_DIR_NAMES = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}
_SKILL_TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".css",
    ".html",
    ".htm",
    ".xml",
    ".csv",
    ".sql",
    ".rs",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".mdc",
    ".example",
}


def _match_skill_definition(skill_name: str, skill_roots: list[Path] | None = None) -> dict[str, str] | None:
    normalized = skill_name.strip().lower()
    if not normalized:
        return None

    exact_id_matches: list[dict[str, str]] = []
    exact_name_matches: list[dict[str, str]] = []

    for definition in list_skill_definitions(skill_roots):
        if definition["id"].lower() == normalized:
            exact_id_matches.append(definition)
        if definition["name"].strip().lower() == normalized:
            exact_name_matches.append(definition)

    matches = exact_id_matches or exact_name_matches
    if len(matches) != 1:
        return None
    return dict(matches[0])


def _skill_directory(definition: dict[str, str]) -> Path:
    return Path(definition["path"]).resolve().parent


def _is_skipped_skill_path(path: Path, skill_dir: Path) -> bool:
    try:
        relative_parts = path.relative_to(skill_dir).parts
    except ValueError:
        return True
    return any(part in _SKILL_SKIP_DIR_NAMES for part in relative_parts)


def _safe_skill_file(skill_dir: Path, relative_path: str) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise RemembValidationError("Skill file path is required.")
    normalized = relative_path.replace("\\", "/").strip().lstrip("/")
    if not normalized:
        raise RemembValidationError("Skill file path is required.")
    candidate = (skill_dir / normalized).resolve()
    root = skill_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RemembValidationError("Invalid skill file path.") from exc
    if _is_skipped_skill_path(candidate, root):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _read_skill_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_file_content(path)
    if suffix in _SKILL_TEXT_SUFFIXES or suffix == "":
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in data[:1024]:
        return ""
    return data.decode("utf-8", errors="replace")


def list_skill_files(skill_name: str, skill_roots: list[Path] | None = None) -> list[dict[str, Any]] | None:
    definition = _match_skill_definition(skill_name, skill_roots)
    if definition is None:
        return None
    skill_dir = _skill_directory(definition)
    files: list[dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or _is_skipped_skill_path(path, skill_dir):
            continue
        relative = path.relative_to(skill_dir).as_posix()
        files.append(
            {
                "path": relative,
                "name": path.name,
                "suffix": path.suffix.lower(),
                "bytes": path.stat().st_size,
            }
        )
    return files


def load_skill_file(
    skill_name: str,
    relative_path: str,
    skill_roots: list[Path] | None = None,
) -> dict[str, Any] | None:
    definition = _match_skill_definition(skill_name, skill_roots)
    if definition is None:
        return None
    skill_dir = _skill_directory(definition)
    path = _safe_skill_file(skill_dir, relative_path)
    if path is None:
        return None
    relative = path.relative_to(skill_dir).as_posix()
    return {
        "skill_id": definition["id"],
        "skill_name": definition["name"],
        "path": relative,
        "name": path.name,
        "suffix": path.suffix.lower(),
        "bytes": path.stat().st_size,
        "content": _read_skill_file_text(path),
    }


def load_skill_definition(skill_name: str, skill_roots: list[Path] | None = None) -> dict[str, Any] | None:
    """Load a single local skill by identifier or declared frontmatter name."""
    match = _match_skill_definition(skill_name, skill_roots)
    if match is None:
        return None
    skill_path = Path(match["path"])
    match["content"] = _read_file_content(skill_path)
    match["files"] = list_skill_files(match["id"], skill_roots) or []
    match["current_path"] = "SKILL.md"
    return match


def global_root() -> Path:
    """Return the global root directory (user home)."""
    return Path.home()


def find_root(start: Path | None = None, local: bool = False) -> Path:
    """Find the .rememb directory by searching upward from start path.
    
    Args:
        start: Starting path for search (default: current directory)
        local: If True, use current directory even if .rememb not found
    
    Returns:
        Path to directory containing .rememb
    
    Raises:
        RemembNotInitializedError: If .rememb not found and local=False
        PermissionError: If local=True but directory not writable
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / REMEMB_DIR).is_dir():
            logger.debug(f"Found .rememb at {parent}")
            return parent

    if local:
        if not os.access(current, os.W_OK):
            raise PermissionError(f"Cannot write to directory: {current}")
        logger.debug(f"Using local mode at {current}")
        return current

    raise RemembNotInitializedError(f"No .rememb directory found. Run 'rememb init' first.")


def is_initialized(root: Path) -> bool:
    """Check if rememb is initialized at the given root."""
    rememb_dir = _rememb_path(root)
    if _entries_path(root).exists():
        return True
    return _entries_db_path(root).exists()


def ensure_global_root(initializer: Callable[[Path, str, bool], object]) -> Path:
    """Return the global root, initializing the store if needed."""
    root = global_root()
    if not is_initialized(root):
        initializer(root, "global", True)
    if not is_initialized(root):
        raise RemembNotInitializedError("Global rememb not initialized.")
    return root


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

def escape(text: str) -> str:
    """Escape markup-like characters for safe terminal output."""
    return html.escape(text)
