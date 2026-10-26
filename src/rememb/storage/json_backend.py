"""JSON file storage backend (default)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, TypeVar

from rememb.exceptions import RemembStorageError
from rememb.helpers import _fsync_handle, _json_text, _write_json
from rememb.storage.locking import file_lock
from rememb.utils import _entries_path

logger = logging.getLogger(__name__)

_ModifierResult = TypeVar("_ModifierResult")


class JsonEntryStorage:
    """Store entries in `.rememb/entries.json`."""

    def is_initialized(self, root: Path) -> bool:
        return _entries_path(root).exists()

    def ensure_initialized(self, root: Path) -> None:
        filepath = _entries_path(root)
        if not filepath.exists():
            _write_json(filepath, [])

    def load_entries(self, root: Path) -> list[dict[str, Any]]:
        filepath = _entries_path(root)
        with file_lock(filepath, mode="r") as f:
            raw = f.read()
        try:
            entries = json.loads(raw)
            logger.debug("Loaded %s entries from %s", len(entries), filepath)
            return entries
        except json.JSONDecodeError as e:
            backup_path = filepath.parent / (filepath.name + ".corrupted")
            try:
                if not backup_path.exists():
                    backup_path.write_bytes(filepath.read_bytes())
            except OSError:
                pass

            try:
                entries: list[dict[str, Any]] = []
                raw_stripped = raw.strip()
                if raw_stripped.startswith("["):
                    json_objects = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw)
                    for obj_str in json_objects:
                        try:
                            entry = json.loads(obj_str)
                            if isinstance(entry, dict) and "id" in entry:
                                entries.append(entry)
                        except json.JSONDecodeError:
                            continue

                if entries:
                    self.save_entries(root, entries)
                    return entries
            except Exception:
                pass

            raise RemembStorageError(
                f"Memory file is corrupted ({filepath}): {e}\n"
                f"Backup saved to {backup_path}. Delete {filepath} to reset."
            ) from e

    def save_entries(self, root: Path, entries: list[dict[str, Any]]) -> None:
        filepath = _entries_path(root)
        _write_json(filepath, entries)
        logger.debug("Saved %s entries to %s", len(entries), filepath)

    def atomic_modify(
        self,
        root: Path,
        modifier: Callable[[list[dict[str, Any]]], _ModifierResult],
    ) -> _ModifierResult:
        filepath = _entries_path(root)
        with file_lock(filepath, mode="r+") as f:
            raw = f.read()
            logger.debug("Atomic modify on %s", filepath)
            try:
                entries = json.loads(raw)
            except json.JSONDecodeError as e:
                raise RemembStorageError(
                    f"Memory file is corrupted ({filepath}): {e}\n"
                    f"Fix manually or delete {filepath} to reset."
                ) from e

            result = modifier(entries)

            data = _json_text(entries)
            f.seek(0)
            f.write(data)
            f.truncate()
            _fsync_handle(f)
            return result
