"""Utility functions for rememb."""

import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rememb.config import (
    CONFIG_FILE,
    ENTRIES_DB_FILE,
    ENTRIES_FILE,
    ENTRY_ID_LENGTH,
    ENTRY_ID_PATTERN,
    META_FILE,
    REMEMB_DIR,
    TEXT_ELLIPSIS,
    TIMESTAMP_FORMAT,
)
from rememb.exceptions import RemembNotInitializedError, RemembValidationError


def _rememb_path(root: Path) -> Path:
    return root / REMEMB_DIR


def _store_file(root: Path, name: str) -> Path:
    return _rememb_path(root) / name


def _entries_path(root: Path) -> Path:
    return _store_file(root, ENTRIES_FILE)


def _entries_db_path(root: Path) -> Path:
    return _store_file(root, ENTRIES_DB_FILE)


def _meta_path(root: Path) -> Path:
    return _store_file(root, META_FILE)


def _config_path(root: Path) -> Path:
    return _store_file(root, CONFIG_FILE)


def clip_text(value: str, limit: int | None) -> str:
    """Collapse whitespace and optionally cap length with a single ellipsis."""
    text = " ".join(value.split()).strip()
    if limit is None or limit < 0 or len(text) <= limit:
        return text
    mark = TEXT_ELLIPSIS
    if limit <= len(mark):
        return text[:limit]
    return text[: limit - len(mark)].rstrip() + mark


def parse_int(value: object, *, name: str, minimum: int) -> int:
    kind = "positive integer" if minimum > 0 else "non-negative integer"
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        raise RemembValidationError(f"{name} must be a {kind}.") from None
    if parsed < minimum:
        raise RemembValidationError(f"{name} must be a {kind}.")
    return parsed


def _validate_entry_id(entry_id: str) -> bool:
    """Return True when entry_id matches the store id shape."""
    return bool(re.match(ENTRY_ID_PATTERN, entry_id, re.IGNORECASE))


def invalid_entry_id_message(entry_id: object) -> str:
    return f"Invalid entry ID format: {entry_id}. Expected {ENTRY_ID_LENGTH} hex characters."


def require_entry_id(entry_id: object) -> str:
    text = str(entry_id or "")
    if not _validate_entry_id(text):
        raise RemembValidationError(invalid_entry_id_message(entry_id))
    return text.lower()


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _frontmatter_body(content: str) -> tuple[str, str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return "", content
    return match.group(1), content[match.end():].lstrip()


def _frontmatter_pairs(block: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            pairs.append((key.strip(), value.strip().strip("\"'")))
    return pairs


def _parse_simple_frontmatter(content: str) -> dict[str, str]:
    block, _ = _frontmatter_body(content)
    return {key: value for key, value in _frontmatter_pairs(block)}


def _extract_summary(content: str) -> str:
    """Extract summary from content, skipping frontmatter and markdown."""
    block, body = _frontmatter_body(content)
    for _, value in _frontmatter_pairs(block):
        if value:
            return value

    skip = re.compile(r"^(#+\s|[-*+]\s|>\s|```|\s*$)", re.IGNORECASE)
    lines = []
    for line in body.splitlines():
        if skip.match(line):
            if lines:
                break
            continue
        lines.append(line.strip())

    if lines:
        return " ".join(lines)
    return body.strip().replace("\n", " ").strip()


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
        except (OSError, UnicodeDecodeError, PermissionError):
            return ""
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return " ".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            return ""
        except (OSError, PermissionError):
            return ""
        except (pypdf.PdfReadError, pypdf.PdfStreamError, ValueError):
            return ""
    return ""


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


def _skill_context(
    skill_name: str, skill_roots: list[Path] | None = None
) -> tuple[dict[str, str], Path] | None:
    definition = _match_skill_definition(skill_name, skill_roots)
    if definition is None:
        return None
    return definition, _skill_directory(definition)


def _skill_file_info(path: Path, skill_dir: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(skill_dir).as_posix(),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "bytes": path.stat().st_size,
    }


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
    if b"\x00" in data:
        return ""
    return data.decode("utf-8", errors="replace")


def list_skill_files(skill_name: str, skill_roots: list[Path] | None = None) -> list[dict[str, Any]] | None:
    context = _skill_context(skill_name, skill_roots)
    if context is None:
        return None
    _, skill_dir = context
    files: list[dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and not _is_skipped_skill_path(path, skill_dir):
            files.append(_skill_file_info(path, skill_dir))
    return files


def load_skill_file(
    skill_name: str,
    relative_path: str,
    skill_roots: list[Path] | None = None,
) -> dict[str, Any] | None:
    context = _skill_context(skill_name, skill_roots)
    if context is None:
        return None
    definition, skill_dir = context
    path = _safe_skill_file(skill_dir, relative_path)
    if path is None:
        return None
    return {
        "skill_id": definition["id"],
        "skill_name": definition["name"],
        **_skill_file_info(path, skill_dir),
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


def is_initialized(root: Path) -> bool:
    """Check if rememb is initialized at the given root."""
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
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


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
    return parse_int(version, name="version", minimum=1)
