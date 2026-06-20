"""Storage backend protocol for rememb entry persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

_ModifierResult = TypeVar("_ModifierResult")


@runtime_checkable
class EntryStorageBackend(Protocol):
    """Abstract interface for loading and atomically modifying entries."""

    def load_entries(self, root: Path) -> list[dict[str, Any]]:
        """Load all entries from storage."""
        ...

    def save_entries(self, root: Path, entries: list[dict[str, Any]]) -> None:
        """Persist the full entry list."""
        ...

    def atomic_modify(
        self,
        root: Path,
        modifier: Callable[[list[dict[str, Any]]], _ModifierResult],
    ) -> _ModifierResult:
        """Apply modifier atomically under an exclusive lock."""
        ...

    def ensure_initialized(self, root: Path) -> None:
        """Create storage files/tables if they do not exist."""
        ...

    def is_initialized(self, root: Path) -> bool:
        """Return whether storage has been initialized for root."""
        ...
