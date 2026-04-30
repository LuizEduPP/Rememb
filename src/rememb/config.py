"""Configuration constants for rememb."""

from typing import Any

REMEMB_DIR = ".rememb"
ENTRIES_FILE = "entries.json"
META_FILE = "meta.json"
CONFIG_FILE = "config.json"

SECTIONS = ["project", "actions", "systems", "requests", "user", "context"]

DEFAULT_MAX_CONTENT_LENGTH = 1000000 
DEFAULT_MAX_TAG_LENGTH = 500
DEFAULT_MAX_TAGS_PER_ENTRY = 100
DEFAULT_MAX_ENTRIES = 100000
DEFAULT_SEMANTIC_MODEL_NAME = "paraphrase-MiniLM-L3-v2"
DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS = 15

DEFAULT_CONFIG: dict[str, Any] = {
	"max_content_length": DEFAULT_MAX_CONTENT_LENGTH,
	"max_tag_length": DEFAULT_MAX_TAG_LENGTH,
	"max_tags_per_entry": DEFAULT_MAX_TAGS_PER_ENTRY,
	"max_entries": DEFAULT_MAX_ENTRIES,
	"semantic_model_name": DEFAULT_SEMANTIC_MODEL_NAME,
	"semantic_model_idle_ttl_seconds": DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS,
}
