"""Configuration constants for rememb."""

# Directory and file names
REMEMB_DIR = ".rememb"
ENTRIES_FILE = "entries.json"
META_FILE = "meta.json"
CONFIG_FILE = "config.json"

# Section definitions
SECTIONS = ["project", "actions", "systems", "requests", "user", "context"]

# Configurable limits to prevent DoS
DEFAULT_MAX_CONTENT_LENGTH = 1000000  # 1MB per entry
DEFAULT_MAX_TAG_LENGTH = 500
DEFAULT_MAX_TAGS_PER_ENTRY = 100
DEFAULT_MAX_ENTRIES = 100000
