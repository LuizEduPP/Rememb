"""Configuration constants for rememb."""

from typing import Any

REMEMB_DIR = ".rememb"
ENTRIES_FILE = "entries.json"
META_FILE = "meta.json"
CONFIG_FILE = "config.json"

DEFAULT_SECTIONS = ["project", "actions", "systems", "requests", "user", "context"]
SECTIONS = list(DEFAULT_SECTIONS)
DEFAULT_REMOVED_SECTION_NAME = "uncategorized"
DEFAULT_CUSTOM_SECTION_ICON = "◎"
DEFAULT_ALL_SECTION_COLOR = "#95a5a6"
DEFAULT_SECTION_ICONS = {
	"project": "◈",
	"actions": "↯",
	"systems": "⛭",
	"requests": "✉",
	"user": "☻",
	"context": "✦",
}
DEFAULT_SECTION_COLORS = {
	"project": "#d84848",
	"actions": "#d08020",
	"systems": "#d4c430",
	"requests": "#40c040",
	"user": "#20d4c4",
	"context": "#c060f0",
}
SECTION_COLOR_PALETTE = [		
	"#ff6b6b",
	"#f7b267",
	"#ffd166",
	"#06d6a0",
	"#4cc9f0",
	"#4895ef",
	"#577590",
	"#90be6d",
	"#43aa8b",
	"#f28482",
	"#84a59d",
	"#c77dff",
	"#ffafcc",
	"#b5ead7",
	"#ffc8dd",
	"#d0f4de",
	"#f72585",
	"#720026",
	"#3a0ca3",
	"#4361ee",
	"#4cc9f0",
	"#ff9e00",
	"#fb5607",
	"#ff006e",
	"#8338ec",
	"#3a86ff",
	"#00f5d4",
	"#2ec4b6",
	"#9b5de5",
	"#f15bb5",
	"#00bbf9",
	"#fee440",
	"#31572c",
	"#cdb4db",
	"#ffc8dd",
	"#ffafcc",
	"#bde0fe",
	"#a2d2ff",
	"#e9edc9",
	"#212529",
	"#343a40",
	"#6c757d",
	"#003566",
	"#240046",
]
SECTION_ICON_CHOICES = [
	{"icon": "◈", "label": "Diamond"},
	{"icon": "↯", "label": "Bolt"},
	{"icon": "⛭", "label": "Gear"},
	{"icon": "✉", "label": "Envelope"},
	{"icon": "☻", "label": "User"},
	{"icon": "✦", "label": "Spark"},
	{"icon": "◆", "label": "Lozenge"},
	{"icon": "◉", "label": "Circle"},
	{"icon": "✪", "label": "Star ring"},
	{"icon": "✸", "label": "Burst"},
	{"icon": "▣", "label": "Square"},
	{"icon": "⚑", "label": "Flag"},
	{"icon": "✿", "label": "Flower"},
	{"icon": "☯", "label": "Yin yang"},
	{"icon": "✎", "label": "Pencil"},
	{"icon": "☂", "label": "Umbrella"},
	{"icon": "✈", "label": "Airplane"},
	{"icon": "✂", "label": "Scissors"},
	{"icon": "⚔", "label": "Crossed swords"},
	{"icon": "☀", "label": "Sun"},
	{"icon": "☁", "label": "Cloud"},
	{"icon": "☃", "label": "Snowman"},
	{"icon": "⌘", "label": "Command"},
	{"icon": "⚛", "label": "Atom"},
	{"icon": "☍", "label": "Link"},
	{"icon": "⚿", "label": "Key"},
	{"icon": "⚒", "label": "Tools"},
	{"icon": "⚗", "label": "Lab"},
	{"icon": "⚖", "label": "Balance"},
	{"icon": "♾", "label": "Infinity"},
	{"icon": "♺", "label": "Recycle"},
	{"icon": "⊕", "label": "Addition"},
	{"icon": "⊘", "label": "Block"},
	{"icon": "⌬", "label": "Chemistry"},
	{"icon": "⎋", "label": "Escape"},
	{"icon": "☽", "label": "Moon"},
	{"icon": "☸", "label": "Wheel"},
	{"icon": "♔", "label": "Crown"},
	{"icon": "♞", "label": "Knight"},
	{"icon": "♩", "label": "Music note"},
	{"icon": "⚀", "label": "Dice"},
	{"icon": "⚠", "label": "Alert"},
	{"icon": "⛶", "label": "Focus"},
	{"icon": "✇", "label": "Tape"},
	{"icon": "✒", "label": "Nib"},
	{"icon": "✓", "label": "Checkmark"},
	{"icon": "✖", "label": "Close"},
	{"icon": "❖", "label": "Tile"},
	{"icon": "❍", "label": "Bubble"},
	{"icon": "❐", "label": "Layers"},
	{"icon": "❒", "label": "Container"},
	{"icon": "❣", "label": "Heart point"},
	{"icon": "❦", "label": "Floral heart"},
	{"icon": "☊", "label": "Headphones"},
	{"icon": "☰", "label": "Menu"},
	{"icon": "⚂", "label": "Dice 3"},
	{"icon": "⚃", "label": "Dice 4"},
	{"icon": "⚄", "label": "Dice 5"},
	{"icon": "⚅", "label": "Dice 6"},
	{"icon": DEFAULT_CUSTOM_SECTION_ICON, "label": "Generic"},
]

DEFAULT_MAX_CONTENT_LENGTH = 1000000 
DEFAULT_MAX_TAG_LENGTH = 500
DEFAULT_MAX_TAGS_PER_ENTRY = 100
DEFAULT_MAX_ENTRIES = 100000
DEFAULT_SEMANTIC_MODEL_NAME = "paraphrase-MiniLM-L3-v2"
SEMANTIC_MODEL_CHOICES = [
	{
        "name": "paraphrase-multilingual-MiniLM-L12-v2",
        "label": "Multilingual MiniLM - fast",
        "description": "Fast and efficient model supporting 50+ languages. Best for quick multilingual semantic search.",
    },
    {
        "name": "paraphrase-multilingual-mpnet-base-v2",
        "label": "Multilingual MPNet - high quality",
        "description": "Higher accuracy for 50+ languages with better semantic understanding than MiniLM.",
    },
    {
        "name": "distiluse-base-multilingual-cased-v2",
        "label": "DistilUSE Multilingual - stable",
        "description": "Multilingual model mapped to the same vector space as English models. Excellent for cross-lingual tasks.",
    },
    {
        "name": "sentence-transformers/LaBSE",
        "label": "LaBSE - 109 languages",
        "description": "Language-Agnostic BERT Sentence Embedding. Supports 109 languages with massive cross-lingual alignment.",
    },
    {
        "name": "intfloat/multilingual-e5-small",
        "label": "Multilingual E5 Small - retrieval optimized",
        "description": "Small, state-of-the-art model specifically trained for text retrieval and semantic similarity.",
    },
    {
        "name": "intfloat/multilingual-e5-base",
        "label": "Multilingual E5 Base - balanced",
        "description": "Strong balance between performance and speed for multilingual retrieval tasks.",
    },
	{
		"name": "all-MiniLM-L6-v2",
		"label": "All-MiniLM-L6-v2",
		"description": "Alternative text model with a slightly different training objective than the default.",
	},
]

DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS = 15
ENTRY_BATCH_SIZE = 24
ENTRY_LOAD_THRESHOLD = 6

DEFAULT_CONFIG: dict[str, Any] = {
	"max_content_length": DEFAULT_MAX_CONTENT_LENGTH,
	"max_tag_length": DEFAULT_MAX_TAG_LENGTH,
	"max_tags_per_entry": DEFAULT_MAX_TAGS_PER_ENTRY,
	"max_entries": DEFAULT_MAX_ENTRIES,
	"sections": DEFAULT_SECTIONS.copy(),
	"section_icons": DEFAULT_SECTION_ICONS.copy(),
	"section_colors": DEFAULT_SECTION_COLORS.copy(),
	"semantic_model_name": DEFAULT_SEMANTIC_MODEL_NAME,
	"semantic_model_idle_ttl_seconds": DEFAULT_SEMANTIC_MODEL_IDLE_TTL_SECONDS,
	"entry_batch_size": ENTRY_BATCH_SIZE,
	"entry_load_threshold": ENTRY_LOAD_THRESHOLD,
}
