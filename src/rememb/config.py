"""Configuration constants for rememb."""

from typing import Any

REMEMB_DIR = ".rememb"
ENTRIES_FILE = "entries.json"
ENTRIES_DB_FILE = "entries.db"
META_FILE = "meta.json"
CONFIG_FILE = "config.json"

DEFAULT_SECTIONS = ["project", "actions", "systems", "requests", "user", "context"]
DEFAULT_REMOVED_SECTION_NAME = "uncategorized"
DEFAULT_ALL_SECTION_COLOR = "#95a5a6"
DEFAULT_SECTION_COLORS = {
	"project": "#d84848",
	"actions": "#d08020",
	"systems": "#d4c430",
	"requests": "#40c040",
	"user": "#20d4c4",
	"context": "#c060f0",
}
DEFAULT_MAX_CONTENT_LENGTH = 1000000
DEFAULT_MAX_TAG_LENGTH = 500
DEFAULT_MAX_TAGS_PER_ENTRY = 100
DEFAULT_MAX_ENTRIES = 100000
ENTRY_BATCH_SIZE = 24
ENTRY_LOAD_THRESHOLD = 6

POSITIVE_INT_CONFIG_KEYS = frozenset({
    "max_content_length",
    "max_tag_length",
    "max_tags_per_entry",
    "max_entries",
    "entry_batch_size",
})

NON_NEGATIVE_INT_CONFIG_KEYS = frozenset({
    "entry_load_threshold",
})

UNIT_INTERVAL_FLOAT_CONFIG_KEYS: frozenset[str] = frozenset()

DEFAULT_CONFIG: dict[str, Any] = {
	"max_content_length": DEFAULT_MAX_CONTENT_LENGTH,
	"max_tag_length": DEFAULT_MAX_TAG_LENGTH,
	"max_tags_per_entry": DEFAULT_MAX_TAGS_PER_ENTRY,
	"max_entries": DEFAULT_MAX_ENTRIES,
	"sections": DEFAULT_SECTIONS.copy(),
	"section_colors": DEFAULT_SECTION_COLORS.copy(),
	"entry_batch_size": ENTRY_BATCH_SIZE,
	"entry_load_threshold": ENTRY_LOAD_THRESHOLD,
	"storage_backend": "json",
}
