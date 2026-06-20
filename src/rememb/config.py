"""Configuration constants for rememb."""

from typing import Any

REMEMB_DIR = ".rememb"
ENTRIES_FILE = "entries.json"
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
DEFAULT_SEMANTIC_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_SEMANTIC_CONFLICT_THRESHOLD = 0.88
SEMANTIC_MODEL_CHOICES = [
    {
        "name": "paraphrase-multilingual-MiniLM-L12-v2",
        "label": "MiniLM L12 - Fast and Lightweight (CPU)",
        "description": "Ideal for machines without a GPU. Extremely fast and low memory usage, supporting over 50 languages.",
    },
    {
        "name": "paraphrase-multilingual-mpnet-base-v2",
        "label": "Multilingual MPNet - Balanced (Plug & Play)",
        "description": "High accuracy for 50+ languages with deep semantic understanding. Perfect for GPU acceleration without requiring text prefixes.",
    },
    {
        "name": "BAAI/bge-m3",
        "label": "BGE-M3 - Enthusiast (High Performance)",
        "description": "Raw model with long context windows and support for over 100 languages. Requires heavy dedicated hardware.",
    },
    {
        "name": "sentence-transformers/LaBSE",
        "label": "LaBSE - Cross-lingual Search (Heavy CPU/Basic GPU)",
        "description": "Focused on massive cross-lingual alignment. Useful for finding English terms while searching in Portuguese.",
    }
]

DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS = 15
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
    "semantic_model_idle_ttl_seconds",
    "entry_load_threshold",
})

UNIT_INTERVAL_FLOAT_CONFIG_KEYS = frozenset({
    "semantic_conflict_threshold",
})

DEFAULT_CONFIG: dict[str, Any] = {
	"max_content_length": DEFAULT_MAX_CONTENT_LENGTH,
	"max_tag_length": DEFAULT_MAX_TAG_LENGTH,
	"max_tags_per_entry": DEFAULT_MAX_TAGS_PER_ENTRY,
	"max_entries": DEFAULT_MAX_ENTRIES,
	"sections": DEFAULT_SECTIONS.copy(),
	"section_colors": DEFAULT_SECTION_COLORS.copy(),
	"semantic_model_name": DEFAULT_SEMANTIC_MODEL_NAME,
	"semantic_model_idle_ttl_seconds": DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS,
	"semantic_conflict_threshold": DEFAULT_SEMANTIC_CONFLICT_THRESHOLD,
	"entry_batch_size": ENTRY_BATCH_SIZE,
	"entry_load_threshold": ENTRY_LOAD_THRESHOLD,
	"storage_backend": "json",
}
