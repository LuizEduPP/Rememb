"""Utility functions for rememb."""

import html
import logging
import os
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from rememb.config import REMEMB_DIR, ENTRIES_FILE, META_FILE
from rememb.exceptions import RemembError, RemembNotInitializedError

console = Console()

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
    return _entries_path(root).exists()


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def escape(text: str) -> str:
    """Escape markup-like characters for safe terminal output."""
    return html.escape(text)


def _print_error(message: str, **kwargs) -> None:
    """Print error message.
    
    Args:
        message: Error message to display
    """
    print(f"\n✗ Error: {message}\n")


def _print_success(message: str, **kwargs) -> None:
    """Print success message.
    
    Args:
        message: Success message to display
    """
    print(f"\n✓ {message}\n")


def _print_warning(message: str, **kwargs) -> None:
    """Print warning message.
    
    Args:
        message: Warning message to display
    """
    print(f"\n⚠ {message}\n")


def _print_info(message: str, **kwargs) -> None:
    """Print info message.
    
    Args:
        message: Info message to display
    """
    print(f"\n{message}\n")


def _handle_error(func, *args, **kwargs) -> Any:
    """Handle RemembError and print error message.
    
    Args:
        func: Function to execute
        *args: Arguments to pass to function
        **kwargs: Keyword arguments to pass to function
    
    Returns:
        Result from function
    
    Raises:
        typer.Exit: If RemembError occurs
    """
    try:
        return func(*args, **kwargs)
    except RemembError as e:
        _print_error(str(e))
        raise typer.Exit(1)


def _validate_entry_id_or_exit(entry_id: str) -> None:
    """Validate entry ID format and exit if invalid.
    
    Args:
        entry_id: Entry ID to validate
    
    Raises:
        typer.Exit: If entry_id is invalid
    """
    if not _validate_entry_id(entry_id):
        _print_error(f"Invalid entry ID format\n{entry_id}\nExpected: 8 hexadecimal characters (e.g., a1b2c3d4)")
        raise typer.Exit(1)


def _root() -> Path:
    """
    Get project root, fallback to global if not found.
    
    Auto-initializes global root (~/.rememb) if no local .rememb is found.
    
    Returns:
        Path to project root or initialized global root
    
    Raises:
        typer.Exit: If global root cannot be initialized
    """
    from rememb.store import init as _init
    try:
        root = find_root()
        if is_initialized(root):
            return root
        _print_error("Not initialized\nRun 'rememb init' first")
        raise typer.Exit(1)
    except RemembNotInitializedError:
        root = global_root()
        if not is_initialized(root):
            try:
                _init(root, project_name="global", global_mode=True)
            except PermissionError as e:
                _print_error(f"Permission denied\nCannot create ~/.rememb/ directory\n{e}")
                raise typer.Exit(1)
            except OSError as e:
                _print_error(f"System error\nCannot initialize rememb storage\n{e}")
                raise typer.Exit(1)
        return root


def _print_table(entries: list[dict]) -> None:
    """Print entries in a formatted table.
    
    Args:
        entries: List of entry dictionaries to display
    """
    if not entries:
        print("No entries found.")
        return

    print(f"\n{'ID':<10} {'Section':<12} {'Content':<50} {'Tags':<20} {'Created':<22} {'Updated':<22}")
    print("-" * 130)

    for e in entries:
        content = e["content"][:47] + "..." if len(e["content"]) > 50 else e["content"]
        tags = ", ".join(e.get("tags", []))[:17] or "-"
        if len(", ".join(e.get("tags", []))) > 20:
            tags = tags[:17] + "..."
        print(f"{e['id']:<10} {e['section']:<12} {content:<50} {tags:<20} {e['created_at']:<22} {e.get('updated_at', 'N/A'):<22}")
    print()
