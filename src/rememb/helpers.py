"""Helper functions and classes for rememb operations."""

import json
import os
import re
from pathlib import Path
from typing import Any

from rememb.config import (
    CONFIG_FILE,
    DEFAULT_ALL_SECTION_COLOR,
    DEFAULT_CONFIG,
    DEFAULT_SECTION_COLORS,
    DEFAULT_SECTIONS,
)
from rememb.utils import _store_file


def _config_path(root: Path) -> Path:
    return _store_file(root, CONFIG_FILE)


def _normalize_sections(value: object) -> list[str]:
    """Normalize configured sections to a unique lowercase list."""
    if not isinstance(value, list):
        return list(DEFAULT_SECTIONS)

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        section = item.strip().lower()
        if not section:
            continue
        section = "".join(char for char in section if char.isalnum() or char in "_-")
        if section and section not in normalized:
            normalized.append(section)

    return normalized or list(DEFAULT_SECTIONS)


def _copy_config_value(value: object) -> object:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _is_hex_color(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()))


def _normalize_section_colors(value: object, sections: list[str]) -> dict[str, str]:
    color_map = value if isinstance(value, dict) else {}
    normalized: dict[str, str] = {}

    for section in sections:
        color = color_map.get(section)
        if _is_hex_color(color):
            normalized[section] = str(color).strip().lower()
        elif section in DEFAULT_SECTION_COLORS:
            normalized[section] = DEFAULT_SECTION_COLORS[section]
        else:
            normalized[section] = DEFAULT_ALL_SECTION_COLOR

    return normalized


def _json_text(data: Any, *, ensure_ascii: bool = True) -> str:
    return json.dumps(data, indent=2, ensure_ascii=ensure_ascii)


def _fsync_handle(handle) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def _read_json(filepath: Path) -> Any:
    return json.loads(filepath.read_text(encoding="utf-8"))


def _read_json_dict(filepath: Path) -> dict[str, Any] | None:
    if not filepath.exists():
        return None
    try:
        loaded = _read_json(filepath)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(loaded, dict):
        return None
    return dict(loaded)


def _write_json(filepath: Path, data: Any) -> None:
    """Save JSON atomically."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_text(data)
    tmp_path = filepath.parent / (filepath.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            _fsync_handle(handle)
        tmp_path.replace(filepath)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


class StoreContext:
    """Encapsulates configuration cache for store operations."""

    def __init__(self):
        self._config_cache: dict[str, dict[str, Any]] = {}
        self._config_cache_mtime: dict[str, float | None] = {}

    def clear_config_cache(self, root: Path | None = None) -> None:
        if root is None:
            self._config_cache.clear()
            self._config_cache_mtime.clear()
            return
        root_key = str(root)
        self._config_cache.pop(root_key, None)
        self._config_cache_mtime.pop(root_key, None)

    def get_config(self, root: Path) -> dict[str, Any]:
        """Load configuration from .rememb/config.json or use defaults.

        Args:
            root: Project root path

        Returns:
            Configuration dictionary with limits and settings
        """
        root_key = str(root)
        config_path = _config_path(root)
        current_mtime = config_path.stat().st_mtime if config_path.exists() else None
        if root_key in self._config_cache and self._config_cache_mtime.get(root_key) == current_mtime:
            return self._config_cache[root_key]
        loaded = _read_json_dict(config_path)
        if loaded is None:
            config = {}
            config_needs_write = True
        else:
            config = loaded
            config_needs_write = False

        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = _copy_config_value(value)
                config_needs_write = True

        # Remove keys that no longer exist in DEFAULT_CONFIG (stale/obsolete)
        stale_keys = [k for k in list(config) if k not in DEFAULT_CONFIG]
        if stale_keys:
            for key in stale_keys:
                del config[key]
            config_needs_write = True

        normalized_sections = _normalize_sections(config.get("sections"))
        if config.get("sections") != normalized_sections:
            config["sections"] = normalized_sections
            config_needs_write = True

        normalized_colors = _normalize_section_colors(config.get("section_colors"), normalized_sections)
        if config.get("section_colors") != normalized_colors:
            config["section_colors"] = normalized_colors
            config_needs_write = True

        if config_needs_write:
            _write_json(config_path, config)

        self._config_cache[root_key] = config
        self._config_cache_mtime[root_key] = current_mtime
        return config

    def update_config(self, root: Path, config: dict[str, Any]) -> dict[str, Any]:
        """Persist validated configuration and refresh cache."""
        config_path = _config_path(root)
        _write_json(config_path, config)
        root_key = str(root)
        self._config_cache[root_key] = dict(config)
        self._config_cache_mtime[root_key] = config_path.stat().st_mtime if config_path.exists() else None
        return dict(config)


_store_context = StoreContext()
