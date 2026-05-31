"""Cross-platform file locking for storage backends."""

from __future__ import annotations

import platform
from contextlib import contextmanager
from pathlib import Path
from typing import IO


def _requires_exclusive_lock(mode: str) -> bool:
    """Return whether the file mode can mutate file contents."""
    return any(flag in mode for flag in ("+", "w", "a", "x"))


@contextmanager
def file_lock(filepath: Path, mode: str = "r+"):
    """Context manager for cross-platform file locking."""
    if not filepath.exists() and _requires_exclusive_lock(mode):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("[]", encoding="utf-8")

    f: IO[str] = open(filepath, mode, encoding="utf-8")
    wants_exclusive_lock = _requires_exclusive_lock(mode)
    is_windows = platform.system() == "Windows"
    try:
        if is_windows:
            import msvcrt

            lock_mode = getattr(msvcrt, "LK_LOCK", 1) if wants_exclusive_lock else getattr(msvcrt, "LK_RLCK", 1)
            getattr(msvcrt, "locking")(f.fileno(), lock_mode, 1)
        else:
            import fcntl

            fcntl.flock(f, fcntl.LOCK_EX if wants_exclusive_lock else fcntl.LOCK_SH)
        yield f
    finally:
        if is_windows:
            import msvcrt

            getattr(msvcrt, "locking")(f.fileno(), getattr(msvcrt, "LK_UNLCK", 1), 1)
        else:
            import fcntl

            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
