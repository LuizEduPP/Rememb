"""Configuration constants for rememb."""

from typing import Any

REMEMB_DIR = ".rememb"
ENTRIES_FILE = "entries.json"
ENTRIES_DB_FILE = "entries.db"
META_FILE = "meta.json"
CONFIG_FILE = "config.json"

ENTRY_ID_LENGTH = 8
ENTRY_ID_PATTERN = rf"^[a-f0-9]{{{ENTRY_ID_LENGTH}}}$"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 18181
DEFAULT_SSE_PORT = 8765
DEFAULT_SSE_PATH = "/sse"
DEFAULT_MESSAGE_PATH = "/messages/"

DEFAULT_SEARCH_TOP_K = 5
DEFAULT_RECENT_LIMIT = 10
DEFAULT_TAG_LIMIT = 50
DEFAULT_PAGE_LIMIT = 100

DEFAULT_SECTION_COLORS = {
    "project": "#d84848",
    "actions": "#d08020",
    "systems": "#d4c430",
    "requests": "#40c040",
    "user": "#20d4c4",
    "context": "#c060f0",
}
DEFAULT_SECTIONS = list(DEFAULT_SECTION_COLORS)
DEFAULT_MCP_SECTION = "context"
DEFAULT_REMOVED_SECTION_NAME = "uncategorized"
DEFAULT_ALL_SECTION_COLOR = "#95a5a6"
STORAGE_BACKEND_JSON = "json"
STORAGE_BACKEND_SQLITE = "sqlite"
DEFAULT_STORAGE_BACKEND = STORAGE_BACKEND_JSON

_POSITIVE_INT_DEFAULTS = {
    "max_content_length": 1_000_000,
    "max_tag_length": 500,
    "max_tags_per_entry": 100,
    "max_entries": 100_000,
    "entry_batch_size": 24,
}
_NON_NEGATIVE_INT_DEFAULTS = {
    "entry_load_threshold": 6,
}

POSITIVE_INT_CONFIG_KEYS = frozenset(_POSITIVE_INT_DEFAULTS)
NON_NEGATIVE_INT_CONFIG_KEYS = frozenset(_NON_NEGATIVE_INT_DEFAULTS)

DEFAULT_CONFIG: dict[str, Any] = {
    **_POSITIVE_INT_DEFAULTS,
    **_NON_NEGATIVE_INT_DEFAULTS,
    "sections": list(DEFAULT_SECTIONS),
    "section_colors": dict(DEFAULT_SECTION_COLORS),
    "storage_backend": DEFAULT_STORAGE_BACKEND,
}
