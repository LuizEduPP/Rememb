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

from rememb.config import REMEMB_DIR, ENTRIES_FILE, META_FILE, CONFIG_FILE
from rememb.exceptions import RemembNotInitializedError, RemembValidationError

HANDOFF_SECTION = "actions"
HANDOFF_TAG = "handoff"
HANDOFF_HEADING_PREFIX = "## "

logger = logging.getLogger(__name__)


def _rememb_path(root: Path) -> Path:
    """Get path to .rememb directory."""
    return root / REMEMB_DIR


def _entries_path(root: Path) -> Path:
    """Get path to entries.json file."""
    return _rememb_path(root) / ENTRIES_FILE


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
    """Return configured skill roots from the optional rememb-skills package."""
    roots: list[Path] = []
    try:
        import rememb_skills

        package_root = Path(rememb_skills.__file__).resolve().parent
        if package_root.is_dir():
            roots.append(package_root)
    except ImportError:
        pass
    return roots


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


def load_skill_definition(skill_name: str, skill_roots: list[Path] | None = None) -> dict[str, str] | None:
    """Load a single local skill by identifier or declared frontmatter name."""
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

    match = dict(matches[0])
    skill_path = Path(match["path"])
    match["content"] = _read_file_content(skill_path)
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
    if (_entries_path(root)).exists():
        return True
    return (rememb_dir / "entries.db").exists()


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


def _normalize_handoff_lines(items: list[str] | None) -> list[str]:
    if not items:
        return []
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_handoff_goal_tag(goal: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", goal.strip().lower()).strip("-")
    return f"goal:{slug or 'handoff'}"


def _handoff_list_block(items: list[str], *, ordered: bool = False) -> list[str]:
    if not items:
        return ["- None recorded."]
    if ordered:
        return [f"{index}. {item}" for index, item in enumerate(items, start=1)]
    return [f"- {item}" for item in items]


def _handoff_text_block(text: str | None, *, fallback: str) -> list[str]:
    value = str(text or "").strip()
    return [value or fallback]


def _split_handoff_sections(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for raw_line in str(content).splitlines():
        line = raw_line.rstrip()
        if line.startswith(HANDOFF_HEADING_PREFIX):
            current_heading = line[len(HANDOFF_HEADING_PREFIX):].strip().lower()
            sections.setdefault(current_heading, [])
            continue
        if current_heading is not None:
            sections[current_heading].append(line)
    return sections


def _parse_handoff_list(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
            continue
        numbered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if numbered:
            items.append(numbered.group(1).strip())
    return [item for item in items if item and item.lower() != "none recorded."]


def _parse_handoff_reference(value: str) -> dict[str, Any]:
    raw = value.strip()
    match = re.match(r"^(?P<entry_id>[0-9a-f]{8})(?:@v(?P<version>\d+))?$", raw, re.IGNORECASE)
    if not match:
        return {"raw": raw, "entry_id": raw, "version": None}
    version = match.group("version")
    return {
        "raw": raw,
        "entry_id": match.group("entry_id").lower(),
        "version": int(version) if version else None,
    }


def _parse_restore_context(lines: list[str], *, default_section: str = HANDOFF_SECTION) -> dict[str, Any]:
    restore_context = {
        "section": default_section,
        "query": "",
        "include_deleted": False,
    }
    for line in lines:
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key == "section" and normalized_value:
            restore_context["section"] = normalized_value
        elif normalized_key == "query":
            restore_context["query"] = normalized_value
        elif normalized_key == "include_deleted":
            restore_context["include_deleted"] = normalized_value.lower() == "true"
    return restore_context


def _current_entry_version(entry: dict[str, Any]) -> int:
    raw_version = entry.get("version", 1)
    try:
        parsed_version = int(str(raw_version).strip())
    except (TypeError, ValueError):
        return 1
    return parsed_version if parsed_version > 0 else 1


_ENTRY_REVISION_METADATA_FIELDS = (
    "meta_schema_version",
    "workstream_id",
    "session_id",
    "entry_kind",
    "entry_role",
    "actor_type",
    "actor_id",
    "parent_entry_id",
    "supersedes_entry_id",
    "related_entry_ids",
    "structured",
)


def _entry_history(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw_history = entry.get("history")
    if not isinstance(raw_history, list):
        return []
    return [dict(item) for item in raw_history if isinstance(item, dict)]


def _entry_revision_snapshot(entry: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "version": _current_entry_version(entry),
        "section": str(entry.get("section", "")),
        "content": str(entry.get("content", "")),
        "tags": list(entry.get("tags", [])) if isinstance(entry.get("tags"), list) else [],
        "created_at": str(entry.get("created_at", "")),
        "updated_at": str(entry.get("updated_at", "")),
        "deleted_at": str(entry.get("deleted_at", "")),
    }
    for field in _ENTRY_REVISION_METADATA_FIELDS:
        if field not in entry:
            continue
        value = entry[field]
        if isinstance(value, list):
            snapshot[field] = list(value)
        elif isinstance(value, dict):
            snapshot[field] = dict(value)
        else:
            snapshot[field] = value
    return snapshot


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
    for field in _ENTRY_REVISION_METADATA_FIELDS:
        if field not in revision:
            entry.pop(field, None)
            continue
        value = revision[field]
        if isinstance(value, list):
            entry[field] = list(value)
        elif isinstance(value, dict):
            entry[field] = dict(value)
        else:
            entry[field] = value
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
