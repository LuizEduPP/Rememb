"""JSON file storage backend (default)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, TypeVar

from rememb.exceptions import RemembStorageError
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
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(json.dumps([], indent=2), encoding="utf-8")

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
        data = json.dumps(entries, indent=2)
        tmp_path = filepath.parent / (filepath.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(filepath)
            logger.debug("Saved %s entries to %s", len(entries), filepath)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

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

            data = json.dumps(entries, indent=2)
            f.seek(0)
            f.write(data)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
            return result
