"""Textual TUI for rememb."""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import webbrowser

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid, ScrollableContainer, Center
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Rule,
    Select,
    Static,
    TextArea,
    MarkdownViewer,
)
from textual.binding import Binding
from textual import on
from textual.message import Message
from typing import Callable

from rememb.config import (
    DEFAULT_ALL_SECTION_COLOR,
    DEFAULT_CUSTOM_SECTION_ICON,
    DEFAULT_REMOVED_SECTION_NAME,
    DEFAULT_SECTION_COLORS,
    DEFAULT_SECTION_ICONS,
    DEFAULT_SECTIONS,
    SECTION_ICON_CHOICES,
    SEMANTIC_MODEL_CHOICES,
)
from rememb.store import (
    get_config,
    update_config,
    read_entries_page,
    search_entries,
    get_stats,
    write_entry,
    edit_entry,
    delete_entry,
    consolidate_entries,
)
from rememb.utils import find_root, global_root, is_initialized

CURRENT_SECTION_ICONS = dict(DEFAULT_SECTION_ICONS)
CURRENT_SECTION_COLORS = dict(DEFAULT_SECTION_COLORS)

SECTION_LABELS = {
    "project": "Project",
    "actions": "Actions",
    "systems": "Systems",
    "requests": "Requests",
    "user": "User",
    "context": "Context",
}

STORE_PAGE_SIZE = 96
CARD_TAG_PREVIEW_LIMIT = 4


def _section_label(section: str | None) -> str:
    if not section:
        return "All"
    return SECTION_LABELS.get(section, section.replace("_", " ").replace("-", " ").title())


def _section_icon(section: str | None) -> str:
    if not section:
        return "◉"
    return CURRENT_SECTION_ICONS.get(section, DEFAULT_CUSTOM_SECTION_ICON)


def _section_color(section: str | None) -> str:
    if not section:
        return DEFAULT_ALL_SECTION_COLOR
    return CURRENT_SECTION_COLORS.get(section, DEFAULT_ALL_SECTION_COLOR)


def _apply_section_appearance_config(config: dict) -> None:
    CURRENT_SECTION_ICONS.clear()
    CURRENT_SECTION_ICONS.update(DEFAULT_SECTION_ICONS)
    CURRENT_SECTION_ICONS.update(config.get("section_icons", {}))

    CURRENT_SECTION_COLORS.clear()
    CURRENT_SECTION_COLORS.update(DEFAULT_SECTION_COLORS)
    CURRENT_SECTION_COLORS.update(config.get("section_colors", {}))


def _section_options(sections: list[str], current: str | None = None) -> list[tuple[str, str]]:
    ordered = [section for section in sections if section]
    if current and current not in ordered:
        ordered.append(current)
    return [(f"{_section_icon(section)}  {_section_label(section)}", section) for section in ordered]


def _default_section(sections: list[str]) -> str:
    if "context" in sections:
        return "context"
    return sections[0] if sections else "context"


def _semantic_model_options(current: str | None = None) -> list[tuple[str, str]]:
    options = [
        (f"{choice['label']} ({choice['name']})", choice["name"])
        for choice in SEMANTIC_MODEL_CHOICES
    ]
    names = {value for _, value in options}
    if current and current not in names:
        options.append((f"Custom ({current})", current))
    return options


def _semantic_model_help(model_name: str) -> str:
    for choice in SEMANTIC_MODEL_CHOICES:
        if choice["name"] == model_name:
            return choice["description"]
    return "Custom sentence-transformers model name loaded from local cache or Hugging Face."


def _section_icon_select_options(current: str | None = None) -> list[tuple[str, str]]:
    options = [(f"{item['icon']}  {item['label']}", item["icon"]) for item in SECTION_ICON_CHOICES]
    known_icons = {value for _, value in options}
    if current and current not in known_icons:
        options.append((f"{current}  Custom", current))
    return options


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "N/A"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return parsed.strftime("%d/%m/%Y %H:%M UTC")
    except ValueError:
        return value


def _visible_card_tags(tags: list[str]) -> tuple[list[str], int]:
    visible_tags = list(tags[:CARD_TAG_PREVIEW_LIMIT])
    hidden_count = max(0, len(tags) - len(visible_tags))
    return visible_tags, hidden_count


class ActionTriggered(Message):
    """Posted when a button inside a card is pressed."""
    def __init__(self, action: str, entry: dict) -> None:
        super().__init__()
        self.action = action
        self.entry = entry


class TagSelected(Message):
    """Posted when the user clicks a tag pill."""

    def __init__(self, tag: str) -> None:
        super().__init__()
        self.tag = tag


class SectionItem(Static):
    """Clickable section item in the sidebar."""

    def __init__(self, section: str | None, count: int = 0, active: bool = False):
        super().__init__()
        self.section_name = section
        self.count = count
        self._active = active
        self._color = _section_color(section)
        name = _section_label(section)
        icon = _section_icon(section)
        self._label_text = f"{icon}  {name}"

    def render(self) -> str:
        return f"{self._label_text}  [dim]({self.count})[/dim]"

    def on_mount(self) -> None:
        self.styles.width = "100%"
        self.styles.height = 3
        self.styles.content_align = ("left", "middle")
        self.styles.padding = (0, 1)
        self.styles.margin = (0, 0, 0, 0)
        self.styles.border_left = ("tall", "transparent")
        if self._active:
            self.styles.background = self._color + "22"
            self.styles.color = self._color
            self.styles.text_style = "bold"
            self.styles.border_left = ("tall", self._color)
        

    def on_click(self) -> None:
        self.post_message(SectionSelected(self.section_name))


class SectionSelected(Message):
    """Posted when the user clicks a section."""
    def __init__(self, section: str | None) -> None:
        super().__init__()
        self.section = section


class SidebarActionButton(Button):
    """Full-width action button used in the sidebar."""

    def __init__(self, *args, margin_top: int = 0, margin_bottom: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self._margin_top = margin_top
        self._margin_bottom = margin_bottom

    def on_mount(self) -> None:
        self.styles.width = "100%"
        self.styles.margin_top = self._margin_top
        self.styles.margin_bottom = self._margin_bottom


class ToolbarActionButton(Button):
    """Compact action button used in the search toolbar."""

    def __init__(self, *args, min_width: int = 18, **kwargs):
        super().__init__(*args, **kwargs)
        self._min_width = min_width

    def on_mount(self) -> None:
        self.styles.width = "auto"
        self.styles.min_width = self._min_width
        self.styles.margin_left = 1


class ModalActionButton(Button):
    """Action button used in modal and side-panel footers."""

    def on_mount(self) -> None:
        self.styles.margin_left = 1


class CardActionButton(Button):
    """Compact icon button used inside entry cards."""

    def on_mount(self) -> None:
        self.styles.min_width = 5
        self.styles.width = 5
        self.styles.height = 3
        self.styles.padding = (0, 0)
        self.styles.content_align = ("center", "middle")
        self.styles.background = "transparent"


class SafeMarkdownViewer(MarkdownViewer):
    """MarkdownViewer variant that handles links defensively."""

    def _handle_markdown_target(self, location: str | Path) -> tuple[str, Path | str | None]:
        target = str(location).strip()
        parsed = urlparse(target)

        if parsed.scheme in {"http", "https"}:
            return "external", target
        if parsed.scheme == "file":
            return "file", Path(parsed.path)
        if parsed.scheme:
            return "unsupported", target
        return "file", Path(target).expanduser()

    async def go(self, location: str | Path) -> None:
        kind, target = self._handle_markdown_target(location)

        if kind == "external":
            if getattr(self, "_open_links", False):
                webbrowser.open(str(target))
            else:
                self.notify("External links are disabled", severity="warning")
            return

        if kind == "unsupported":
            self.notify(f"Unsupported link: {target}", severity="warning")
            return

        local_path = target if isinstance(target, Path) else Path(str(target))
        if not local_path.exists():
            self.notify(f"Invalid link target: {local_path}", severity="warning")
            return

        await super().go(local_path)

    async def _on_markdown_link_clicked(self, message) -> None:
        message.stop()
        await self.go(message.href)


class FieldBlock(Vertical):
    """Labeled form field block used across panels and modals."""

    def __init__(self, label: str, control: Widget, help_text: str | None = None):
        super().__init__()
        self._label = label
        self._control = control
        self._help_text = help_text

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="field-label")
        yield self._control
        if self._help_text:
            yield Label(self._help_text, classes="field-help")

    def on_mount(self) -> None:
        self.styles.height = "auto"
        self.styles.margin = (1, 0, 2, 0)
        for field_label in self.query(".field-label"):
            field_label.styles.margin_bottom = 1
        for help_label in self.query(".field-help"):
            help_label.styles.color = "#a7b1c2"
            help_label.styles.height = "auto"
            help_label.styles.margin_top = 1


class CardSectionLabel(Label):
    """Styled section label used inside entry cards."""

    def __init__(self, text: str, color: str, **kwargs):
        super().__init__(text, **kwargs)
        self._color = color

    def on_mount(self) -> None:
        self.styles.color = self._color
        self.styles.margin = (1, 0, 0, 0)
        self.styles.height = 2


class CardMetaLine(Label):
    """Compact metadata line for entry timestamps."""

    def on_mount(self) -> None:
        self.styles.height = 1
        self.styles.margin = (0, 0, 0, 0)
        self.styles.color = "#a7b1c2"


class TagRow(Horizontal):
    """Horizontal row for wrapped card tag pills."""

    def on_mount(self) -> None:
        self.styles.height = 3
        self.styles.margin_bottom = 1


class TagPill(Label):
    """Styled tag pill used inside entry cards."""

    def __init__(self, tag: str, color: str, *, clickable: bool = True, **kwargs):
        super().__init__(f" {tag} ", **kwargs)
        self.tag = tag
        self._color = color
        self._clickable = clickable

    def on_mount(self) -> None:
        self.styles.color = self._color
        self.styles.border = ("round", self._color + "88")
        self.styles.padding = (0, 1)
        self.styles.margin_right = 1
        self.styles.width = "auto"
        self.styles.shrink = True
        self.styles.height = 3
        self.styles.content_align = ("center", "middle")

    def on_click(self) -> None:
        if self._clickable:
            self.post_message(TagSelected(self.tag))


class EntryCard(Widget):
    """Single card representing one memory entry."""

    def __init__(self, entry: dict):
        import uuid
        uid = uuid.uuid4().hex[:8]
        super().__init__()
        self.entry = entry
        self.entry_id = entry.get("id", "???")
        self.section = entry.get("section", "context")
        self.color = _section_color(self.section)
        self._uid = uid

    def compose(self) -> ComposeResult:
        with Vertical(id="card-root"):
            with Vertical(id="card-body"):
                with Horizontal():
                    yield Label(
                        f"[dim]#{self.entry_id[:8]}[/dim]",
                        id=f"cid-{self._uid}",
                    )
                    yield CardActionButton("◉", id="view-card", classes="act-btn", tooltip="View entry")
                    yield CardActionButton("✎", id="edit-card", classes="act-btn", tooltip="Edit entry")
                    yield CardActionButton("✕", id="delete-card", classes="act-btn del-btn", tooltip="Delete entry")

                section_label = _section_label(self.section)
                icon = _section_icon(self.section)
                yield CardSectionLabel(
                    f"[b]{icon}  {section_label}[/b]",
                    self.color,
                    id=f"csec-{self._uid}",
                )

                yield Rule(line_style="heavy")

                content = self.entry.get("content", "")
                preview = content[:150] + "…" if len(content) > 150 else content
                yield Static(preview, id=f"ccnt-{self._uid}")

                yield CardMetaLine(
                    f"[dim]Created:[/dim] {_format_timestamp(self.entry.get('created_at'))}",
                    id=f"ccrt-{self._uid}",
                    classes="meta-line",
                )
                yield CardMetaLine(
                    f"[dim]Updated:[/dim] {_format_timestamp(self.entry.get('updated_at'))}",
                    id=f"cupd-{self._uid}",
                    classes="meta-line",
                )

            tags = self.entry.get("tags", [])
            if tags:
                with Vertical(id=f"cftr-{self._uid}"):
                    yield Rule()
                    row: list = []
                    rows: list = []
                    line_len = 0
                    max_w = 36
                    visible_tags, hidden_count = _visible_card_tags(tags)
                    render_tags = list(visible_tags)
                    if hidden_count:
                        render_tags.append(f"+{hidden_count}")
                    for tag in render_tags:
                        w = len(tag) + 3
                        if line_len + w > max_w and row:
                            rows.append(row)
                            row = []
                            line_len = 0
                        row.append(tag)
                        line_len += w
                    if row:
                        rows.append(row)
                    for i, row_tags in enumerate(rows):
                        with TagRow(classes="tag-row"):
                            for tag in row_tags:
                                yield TagPill(
                                    tag,
                                    self.color,
                                    clickable=not tag.startswith("+"),
                                    classes="tag-pill",
                                )

    def on_mount(self) -> None:
        self.styles.height = "auto"
        self.styles.padding = (1, 2)
        self.styles.border = ("round", self.color)
        self.styles.margin = (0, 0, 0, 0)

        header_row = self.query_one(Horizontal)
        header_row.styles.height = 3
        header_row.styles.align = ("left", "middle")

        id_lbl = self.query_one(f"#cid-{self._uid}")
        id_lbl.styles.width = "1fr"
        id_lbl.styles.content_align = ("left", "middle")
        id_lbl.styles.height = 3

        for btn in self.query(".act-btn"):
            btn.styles.border = ("round", self.color + "66")
            btn.styles.color = self.color

        for rule in self.query(Rule):
            rule.styles.color = self.color + "44"
            rule.styles.margin = (0, 0, 0, 0)

        root = self.query_one("#card-root")
        root.styles.height = "auto"

        body = self.query_one("#card-body")
        body.styles.height = "auto"

        content = self.query_one(f"#ccnt-{self._uid}")
        content.styles.height = 5
        content.styles.overflow = "hidden"
        content.styles.margin = (1, 0)
        content.styles.text_wrap = "wrap"

        try:
            footer = self.query_one(f"#cftr-{self._uid}")
            footer.styles.height = "auto"
        except Exception:
            pass

    @on(Button.Pressed, "#edit-card")
    def on_edit(self) -> None:
        self.post_message(ActionTriggered("edit", self.entry))

    @on(Button.Pressed, "#view-card")
    def on_view(self) -> None:
        self.post_message(ActionTriggered("view", self.entry))

    @on(Button.Pressed, "#delete-card")
    def on_delete(self) -> None:
        self.post_message(ActionTriggered("delete", self.entry))


class EntryScrollContainer(ScrollableContainer):
    """Container com callback ao se aproximar do fim da rolagem."""

    def __init__(self, on_near_end: Callable[[], None], *children, threshold: int = 6, **kwargs):
        super().__init__(*children, **kwargs)
        self._on_near_end = on_near_end
        self._threshold = threshold

    def set_threshold(self, threshold: int) -> None:
        self._threshold = max(0, threshold)

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if self.max_scroll_y - new_value <= self._threshold:
            self._on_near_end()


class RemembApp(App):
    """Modern rememb interface built around a card grid."""

    TITLE = "Rememb"
    SUB_TITLE = "Persistent memory standard for AI agents"

    CSS = """
    #body    { width: 100%; height: 1fr; }
    #sidebar { width: 30; height: 1fr; }
    #main-area { width: 1fr; height: 1fr; }
    #content-area { width: 1fr; height: 1fr; }
    #entries-grid { layout: grid; grid-size: 3; grid-gutter: 1; height: auto; }
    #side-panel { width: 50; height: 1fr; display: none; border-left: solid #2e343b; }
    #modal   { width: 72; height: auto; }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_entry", "New", show=True),
        Binding("f2", "open_config", "Config", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("ctrl+d", "consolidate", "Consolidate", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, root_path=None):
        super().__init__()
        self._root_path = root_path
        self.current_entries = []
        self.current_section = None
        self.current_query = ""
        self.active_tag: str | None = None
        self.latest_first = True
        self.rendered_count = 0
        self.loaded_offset = 0
        self.has_more_entries = False
        self.sections = list(DEFAULT_SECTIONS)
        self.entry_batch_size = 24
        self.entry_load_threshold = 6
        self._panel_mode: str | None = None
        self._panel_entry: dict | None = None

    def _visible_sections(self, stats: dict) -> list[str]:
        visible = list(self.sections)
        for section in stats.get("by_section", {}):
            if section not in visible:
                visible.append(section)
        return visible

    def _sync_section_select(self, select_id: str, *, current: str | None = None) -> None:
        select = self.query_one(select_id, Select)
        select.set_options(_section_options(self.sections, current))
        default_section = _default_section(self.sections)
        select.value = current if current else default_section

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield SidebarActionButton("＋  New Entry", id="btn-new-entry", variant="primary", flat=True, margin_bottom=1)
                yield Rule()
                yield Label(" SECTIONS", id="sections-title")
                yield Rule()
                yield ScrollableContainer(id="sidebar-sections")
                yield Rule()
                yield SidebarActionButton("⚙  Config", id="btn-config", variant="default", flat=True, margin_top=1)
                yield SidebarActionButton("↻  Refresh", id="btn-refresh", variant="warning", flat=True, margin_top=1)
                yield SidebarActionButton("⇵  Consolidate", id="btn-consolidate", variant="success", flat=True, margin_top=1)
                yield SidebarActionButton("⏻  Quit", id="btn-quit", variant="error", flat=True, margin_top=1)

            with Vertical(id="main-area"):
                with Horizontal(id="search-bar"):
                    yield Input(placeholder="⌕  Search memory...", id="search-box")
                    yield Label("Tag: all", id="tag-filter-indicator")
                    yield ToolbarActionButton("✕  Clear Tag", id="btn-clear-tag", variant="default", flat=True, min_width=14)
                    yield ToolbarActionButton("↓  Latest First", id="btn-sort-order", variant="default", flat=True)
                yield Rule()
                with Horizontal(id="content-area"):
                    with EntryScrollContainer(self._maybe_load_more_entries, id="main-scroll"):
                        yield Grid(id="entries-grid")
                    with ScrollableContainer(id="side-panel"):
                        yield Label("", id="panel-title")
                        yield Rule()
                        yield FieldBlock("Content", TextArea("", id="panel-content"))
                        yield FieldBlock(
                            "Section",
                            Select(
                                _section_options(self.sections),
                                value=_default_section(self.sections),
                                id="panel-section",
                                allow_blank=False,
                            ),
                        )
                        yield FieldBlock(
                            "Tags  (comma-separated)",
                            Input(placeholder="tag1, tag2", id="panel-tags"),
                        )
                        yield SafeMarkdownViewer(
                            "",
                            id="panel-markdown-viewer",
                            show_table_of_contents=False,
                            open_links=False,
                        )
                        yield Rule()
                        with Horizontal(id="panel-buttons"):
                            yield ModalActionButton("Cancel", id="panel-cancel", variant="default", flat=True)
                            yield ModalActionButton("Save", id="panel-save", variant="success", flat=True)

        yield Footer()

    def on_mount(self) -> None:
        self.theme = "nord"
        self._apply_sidebar_styles()
        self._apply_main_styles()
        self._refresh_ui()
        self._update_grid_columns()

    def _apply_sidebar_styles(self) -> None:
        BORDER_DIM = "#2e343b"

        sidebar = self.query_one("#sidebar")
        sidebar.styles.border_right = ("solid", BORDER_DIM)
        sidebar.styles.padding = (1, 1)

        sec_title = self.query_one("#sections-title")
        sec_title.styles.text_style = "bold dim"
        sec_title.styles.height = 1
        sec_title.styles.content_align = ("left", "middle")

        sections_area = self.query_one("#sidebar-sections")
        sections_area.styles.height = "1fr"

    def _apply_main_styles(self) -> None:
        BORDER_DIM = "#2e343b"

        main_area = self.query_one("#main-area")
        main_area.styles.padding = (1, 2, 0, 2)

        search_bar = self.query_one("#search-bar")
        search_bar.styles.height = 3
        search_bar.styles.padding = (0, 0)
        search_bar.styles.align = ("left", "middle")

        search_box = self.query_one("#search-box")
        search_box.styles.width = "1fr"

        tag_indicator = self.query_one("#tag-filter-indicator")
        tag_indicator.styles.width = "auto"
        tag_indicator.styles.min_width = 14
        tag_indicator.styles.margin_left = 1
        tag_indicator.styles.content_align = ("center", "middle")
        tag_indicator.styles.height = 3
        tag_indicator.styles.color = "#88c0d0"

        main_scroll = self.query_one("#main-scroll")
        main_scroll.styles.padding = (1, 0)

        panel = self.query_one("#side-panel")
        panel.styles.padding = (2, 3)

        panel_title = self.query_one("#panel-title")
        panel_title.styles.height = 3
        panel_title.styles.content_align = ("left", "middle")
        panel_title.styles.margin_bottom = 1

        panel_ta = self.query_one("#panel-content", TextArea)
        panel_ta.styles.height = 10

        panel_markdown_viewer = self.query_one("#panel-markdown-viewer", SafeMarkdownViewer)
        panel_markdown_viewer.styles.height = "1fr"
        panel_markdown_viewer.styles.display = "none"
        panel_markdown_viewer.styles.margin_bottom = 1
        if hasattr(panel_markdown_viewer, "code_indent_guides"):
            panel_markdown_viewer.code_indent_guides = False

        for lbl in panel.query(".field-label"):
            lbl.styles.height = 2
            lbl.styles.content_align = ("left", "middle")

        panel_btns = self.query_one("#panel-buttons")
        panel_btns.styles.height = 4
        panel_btns.styles.align = ("right", "middle")
        panel_btns.styles.margin_top = 2

    def _get_root(self):
        if self._root_path: return self._root_path
        try: return find_root()
        except Exception:
            root = global_root()
            if not is_initialized(root):
                from rememb.store import init
                init(root, project_name="global", global_mode=True)
            return root

    def _refresh_ui(self, section: str | None = None) -> None:
        self.current_query = ""
        root = self._get_root()
        self._load_tui_config(root)
        stats = get_stats(root)
        visible_sections = self._visible_sections(stats)
        self.current_section = section if section in visible_sections or section is None else None
        self._update_sort_button()

        container = self.query_one("#sidebar-sections")
        container.remove_children()

        all_item = SectionItem(None, stats["total"], active=(self.current_section is None))
        container.mount(all_item)

        for sec_name in visible_sections:
            count = stats["by_section"].get(sec_name, 0)
            item = SectionItem(sec_name, count, active=(self.current_section == sec_name))
            container.mount(item)

        self._load_entries(self.current_section)
        self._update_tag_filter_ui()

    def _load_tui_config(self, root) -> None:
        config = get_config(root)
        _apply_section_appearance_config(config)
        self.sections = list(config.get("sections", DEFAULT_SECTIONS))
        batch_size = config.get("entry_batch_size", self.entry_batch_size)
        load_threshold = config.get("entry_load_threshold", self.entry_load_threshold)

        try:
            self.entry_batch_size = max(1, int(batch_size))
        except (TypeError, ValueError):
            self.entry_batch_size = 24

        try:
            self.entry_load_threshold = max(0, int(load_threshold))
        except (TypeError, ValueError):
            self.entry_load_threshold = 6

        self.query_one("#main-scroll", EntryScrollContainer).set_threshold(self.entry_load_threshold)
        self._sync_section_select("#panel-section", current=self.query_one("#panel-section", Select).value)

    def _sort_entries(self, entries: list[dict]) -> list[dict]:
        return sorted(
            entries,
            key=lambda entry: entry.get("updated_at") or entry.get("created_at") or "",
            reverse=self.latest_first,
        )

    def _reset_loaded_entries(self) -> None:
        self.current_entries = []
        self.rendered_count = 0
        self.loaded_offset = 0
        self.has_more_entries = False

    def _load_next_store_page(self, reset: bool = False) -> None:
        if self.current_query:
            return

        if reset:
            self._reset_loaded_entries()
        elif not self.has_more_entries and self.loaded_offset > 0:
            return

        page = read_entries_page(
            self._get_root(),
            self.current_section,
            tag=self.active_tag,
            offset=self.loaded_offset,
            limit=STORE_PAGE_SIZE,
            sort_by="recent",
            descending=self.latest_first,
        )

        if reset:
            self.current_entries = list(page["items"])
        else:
            self.current_entries.extend(page["items"])
        self.loaded_offset = page["next_offset"]
        self.has_more_entries = page["has_more"]

    def _render_entries(self, reset: bool = False) -> None:
        if reset:
            self.rendered_count = 0
            self.query_one("#entries-grid", Grid).remove_children()
            self.query_one("#main-scroll", EntryScrollContainer).scroll_home(animate=False, immediate=True, x_axis=False)

        self._render_next_batch()
        if reset:
            self.call_after_refresh(self._ensure_viewport_filled)

    def _render_next_batch(self) -> None:
        if self.rendered_count >= len(self.current_entries):
            return

        next_count = min(self.rendered_count + self.entry_batch_size, len(self.current_entries))
        grid = self.query_one("#entries-grid", Grid)
        for entry in self.current_entries[self.rendered_count:next_count]:
            grid.mount(EntryCard(entry))
        self.rendered_count = next_count

    def _ensure_viewport_filled(self) -> None:
        main_scroll = self.query_one("#main-scroll", EntryScrollContainer)
        if main_scroll.max_scroll_y > 0:
            return

        if self.rendered_count < len(self.current_entries):
            previous_count = self.rendered_count
            self._render_next_batch()
            if self.rendered_count > previous_count:
                self.call_after_refresh(self._ensure_viewport_filled)
            return

        if self.has_more_entries:
            previous_count = len(self.current_entries)
            self._load_next_store_page()
            if len(self.current_entries) > previous_count:
                self._render_next_batch()
                self.call_after_refresh(self._ensure_viewport_filled)

    def _maybe_load_more_entries(self) -> None:
        if self.rendered_count < len(self.current_entries):
            self._render_next_batch()
            return

        if self.has_more_entries:
            previous_count = len(self.current_entries)
            self._load_next_store_page()
            if len(self.current_entries) > previous_count:
                self._render_next_batch()
                self.call_after_refresh(self._ensure_viewport_filled)

    def _update_sort_button(self) -> None:
        label = "↓  Latest First" if self.latest_first else "↑  Oldest First"
        self.query_one("#btn-sort-order", Button).label = label

    def _update_tag_filter_ui(self) -> None:
        indicator = self.query_one("#tag-filter-indicator", Label)
        clear_button = self.query_one("#btn-clear-tag", Button)
        if self.active_tag:
            indicator.update(f"Tag: {self.active_tag}")
            clear_button.display = True
        else:
            indicator.update("Tag: all")
            clear_button.display = False

    def _apply_active_filters(self) -> None:
        self._update_tag_filter_ui()
        if self.current_query:
            root = self._get_root()
            self.loaded_offset = 0
            self.has_more_entries = False
            self.current_entries = self._sort_entries(
                search_entries(
                    root,
                    self.current_query,
                    top_k=20,
                    section=self.current_section,
                    tag=self.active_tag,
                )
            )
            self._render_entries(reset=True)
            return

        self._load_entries(self.current_section)

    def _load_entries(self, section: str | None = None) -> None:
        try:
            self.current_section = section
            self._load_next_store_page(reset=True)
        except Exception:
            self._reset_loaded_entries()
        self._render_entries(reset=True)

    @on(SectionSelected)
    def handle_section_selected(self, message: SectionSelected) -> None:
        self._refresh_ui(message.section)

    @on(ActionTriggered)
    def handle_card_action(self, message: ActionTriggered) -> None:
        if message.action == "view":
            self._view_entry(message.entry)
        elif message.action == "edit":
            self._edit_entry(message.entry)
        elif message.action == "delete":
            self._delete_entry(message.entry)

    @on(TagSelected)
    def handle_tag_selected(self, message: TagSelected) -> None:
        self.active_tag = None if self.active_tag == message.tag else message.tag
        self._apply_active_filters()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-new-entry":
            self.action_new_entry()
        elif btn_id == "btn-config":
            self.action_open_config()
        elif btn_id == "btn-refresh":
            self.action_refresh()
        elif btn_id == "btn-clear-tag":
            self.action_clear_tag_filter()
        elif btn_id == "btn-sort-order":
            self.action_toggle_sort_order()
        elif btn_id == "btn-consolidate":
            self.action_consolidate()
        elif btn_id == "btn-quit":
            self.app.exit()

    @on(Input.Submitted, "#search-box")
    def on_search(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            self.current_query = ""
            self._apply_active_filters()
            return
        self.current_query = query
        self._apply_active_filters()

    def _render_entry_markdown(self, entry: dict) -> str:
        tags = ", ".join(entry.get("tags", [])) or "None"
        return "\n".join(
            [
                f"# Memory {entry['id'][:8]}",
                f"- **Section:** {_section_label(entry.get('section', 'context'))}",
                f"- **Tags:** {tags}",
                f"- **Created:** {_format_timestamp(entry.get('created_at'))}",
                f"- **Updated:** {_format_timestamp(entry.get('updated_at'))}",
                "",
                "---",
                "",
                entry.get("content", ""),
            ]
        )

    def _open_panel(self, mode: str, entry: dict | None = None) -> None:
        self._panel_mode = mode
        self._panel_entry = entry
        panel = self.query_one("#side-panel")
        panel.display = True

        title = self.query_one("#panel-title")
        if mode == "new":
            title.update("❆  New Entry")
        elif mode == "view" and entry:
            title.update(f"◉  View  [dim]#{entry['id'][:8]}[/dim]")
        else:
            title.update(f"✎  Edit  [dim]#{entry['id'][:8]}[/dim]")

        panel_markdown_viewer = self.query_one("#panel-markdown-viewer", SafeMarkdownViewer)
        cancel_btn = self.query_one("#panel-cancel", Button)
        save_btn = self.query_one("#panel-save", Button)

        is_view_mode = mode == "view"
        for field in panel.query(FieldBlock):
            field.display = not is_view_mode
        panel_markdown_viewer.display = is_view_mode
        save_btn.display = not is_view_mode
        cancel_btn.label = "Close" if is_view_mode else "Cancel"

        content_ta = self.query_one("#panel-content", TextArea)
        content_ta.clear()
        if mode == "edit" and entry:
            content_ta.insert(entry["content"])

        current_section = entry["section"] if mode == "edit" and entry else _default_section(self.sections)
        self._sync_section_select("#panel-section", current=current_section)

        tags_input = self.query_one("#panel-tags", Input)
        tags_input.value = ", ".join(entry["tags"]) if mode == "edit" and entry else ""

        if is_view_mode and entry:
            markdown = self._render_entry_markdown(entry)
            self.call_after_refresh(lambda: panel_markdown_viewer.document.update(markdown))
        else:
            self.call_after_refresh(lambda: panel_markdown_viewer.document.update(""))

        self._update_grid_columns()
        if is_view_mode:
            self.call_after_refresh(panel_markdown_viewer.focus)
        else:
            self.query_one("#panel-content").focus()

    def _close_panel(self) -> None:
        self.query_one("#side-panel").display = False
        self._panel_mode = None
        self._panel_entry = None
        self._update_grid_columns()

    @on(Button.Pressed, "#panel-cancel")
    def on_panel_cancel(self) -> None:
        self._close_panel()

    @on(Button.Pressed, "#panel-save")
    def on_panel_save(self) -> None:
        content = self.query_one("#panel-content", TextArea).text.strip()
        if not content:
            return
        section = self.query_one("#panel-section", Select).value or "context"
        tags = [t.strip() for t in self.query_one("#panel-tags", Input).value.split(",") if t.strip()]
        if self._panel_mode == "new":
            write_entry(self._get_root(), section, content, tags)
            self.notify("Entry saved", severity="information")
        elif self._panel_mode == "edit" and self._panel_entry:
            edit_entry(self._get_root(), self._panel_entry["id"], content=content, section=section, tags=tags)
            self.notify("Entry updated", severity="information")
        self._close_panel()
        self._refresh_ui(self.current_section)

    def action_new_entry(self) -> None:
        self._open_panel("new")

    def action_open_config(self) -> None:
        root = self._get_root()
        self.push_screen(ConfigScreen(root, get_config(root)), self._handle_config_saved)

    def _handle_config_saved(self, saved_config: dict | None) -> None:
        if not saved_config:
            return
        if self.current_section and self.current_section not in saved_config.get("sections", []):
            self.current_section = None
        self._refresh_ui(self.current_section)
        self.notify("Configuration updated", severity="information")

    def _view_entry(self, entry: dict) -> None:
        self._open_panel("view", entry)

    def _edit_entry(self, entry: dict) -> None:
        self._open_panel("edit", entry)

    def _delete_entry(self, entry: dict) -> None:
        self.push_screen(DeleteConfirmScreen(self._get_root(), entry["id"], entry["content"]), lambda del_ok: self._refresh_ui(self.current_section) if del_ok else None)

    def action_refresh(self) -> None:
        self._refresh_ui(self.current_section)
        self.notify("Memory refreshed", severity="information")

    def action_clear_tag_filter(self) -> None:
        if not self.active_tag:
            return
        self.active_tag = None
        self._apply_active_filters()
        self.notify("Tag filter cleared", severity="information")

    def action_toggle_sort_order(self) -> None:
        self.latest_first = not self.latest_first
        self._update_sort_button()
        if self.current_query:
            self.current_entries = self._sort_entries(self.current_entries)
            self._render_entries(reset=True)
        else:
            self._load_entries(self.current_section)
        mode = "latest first" if self.latest_first else "oldest first"
        self.notify(f"Order changed: {mode}", severity="information")

    def action_consolidate(self) -> None:
        try:
            result = consolidate_entries(
                self._get_root(),
                section=self.current_section,
                mode="semantic",
                similarity_threshold=0.88,
            )
            target = result["section"] if result["section"] else "all sections"
            self._refresh_ui(self.current_section)
            self.notify(
                f"Consolidated {target}: removed {result['removed_count']} duplicates",
                severity="information",
            )
        except Exception as e:
            self.notify(f"Consolidation failed: {e}", severity="error")

    def action_focus_search(self) -> None:
        self.query_one("#search-box").focus()

    def _update_grid_columns(self) -> None:
        width = self.size.width
        if width >= 180:
            cols = 4
        elif width >= 120:
            cols = 3
        elif width >= 80:
            cols = 2
        else:
            cols = 1
        grid = self.query_one("#entries-grid", Grid)
        grid.styles.grid_size_columns = cols

    def on_resize(self, event) -> None:
        self._update_grid_columns()
        self.call_after_refresh(self._ensure_viewport_filled)


class _ModalBase(Screen):
    """Base class for centered modal screens."""

    def on_mount(self) -> None:
        self.styles.align = ("center", "middle")

        modal = self.query_one("#modal")
        modal.styles.border = ("round", "#5e81ac")
        modal.styles.padding = (2, 3)

        title = self.query_one("#modal-title")
        title.styles.text_style = "bold"
        title.styles.text_align = "center"
        title.styles.margin_bottom = 1
        title.styles.height = 2
        title.styles.content_align = ("center", "middle")

        for lbl in self.query(".field-label"):
            lbl.styles.text_style = "bold"

        try:
            btn_row = self.query_one(".modal-buttons")
            btn_row.styles.height = 4
            btn_row.styles.align = ("right", "middle")
            btn_row.styles.margin_top = 1
            for btn in btn_row.query(Button):
                btn.styles.margin_left = 1
        except Exception:
            pass


class NewEntryScreen(_ModalBase):
    def __init__(self, root, sections: list[str]):
        super().__init__()
        self._root = root
        self._sections = sections

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal"):
                yield Label("❆  New Memory Entry", id="modal-title")
                yield Rule()
                yield FieldBlock("Content", TextArea(id="content-input"))
                yield FieldBlock(
                    "Section",
                    Select(
                        _section_options(self._sections),
                        value=_default_section(self._sections),
                        id="section-input",
                        allow_blank=False,
                    ),
                )
                yield FieldBlock("Tags  (comma-separated)", Input(placeholder="tag1, tag2, tag3", id="tags-input"))
                yield Rule()
                with Horizontal(classes="modal-buttons"):
                    yield ModalActionButton("Cancel", id="btn-cancel", variant="default")
                    yield ModalActionButton("Save", id="btn-save", variant="success")

    @on(Button.Pressed, "#btn-save")
    def save(self) -> None:
        content = self.query_one("#content-input").text.strip()
        if not content:
            return
        section = self.query_one(Select, "#section-input").value or "context"
        tags = [t.strip() for t in self.query_one("#tags-input").value.split(",") if t.strip()]
        write_entry(self._root, section, content, tags)
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(False)


class EditEntryScreen(_ModalBase):
    def __init__(self, root, entry, sections: list[str]):
        super().__init__()
        self._root = root
        self._entry = entry
        self._sections = sections

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal"):
                yield Label(f"✎  Edit  [dim]#{self._entry['id'][:8]}[/dim]", id="modal-title")
                yield Rule()
                yield FieldBlock("Content", TextArea(self._entry["content"], id="content-input"))
                yield FieldBlock(
                    "Section",
                    Select(
                        _section_options(self._sections, self._entry["section"]),
                        value=self._entry["section"],
                        id="section-input",
                        allow_blank=False,
                    ),
                )
                yield FieldBlock(
                    "Tags  (comma-separated)",
                    Input(value=", ".join(self._entry["tags"]), id="tags-input"),
                )
                yield Rule()
                with Horizontal(classes="modal-buttons"):
                    yield ModalActionButton("Cancel", id="btn-cancel", variant="default")
                    yield ModalActionButton("Update", id="btn-save", variant="primary")

    @on(Button.Pressed, "#btn-save")
    def update(self) -> None:
        edit_entry(
            self._root, self._entry["id"],
            content=self.query_one("#content-input").text,
            section=self.query_one(Select, "#section-input").value,
            tags=[t.strip() for t in self.query_one("#tags-input").value.split(",") if t.strip()],
        )
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(False)


class DeleteConfirmScreen(_ModalBase):
    def __init__(self, root, entry_id, content):
        super().__init__()
        self._root = root
        self._eid = entry_id
        self._c = content

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal"):
                yield Label("✕  Remove Memory?", id="modal-title")
                yield Rule()
                yield Label(f"[dim]ID:[/dim]  [b]{self._eid[:8]}[/b]", classes="field-label")
                yield Static(f'"{self._c[:180]}…"')
                yield Rule()
                yield Label("[bold red]This action is irreversible.[/bold red]", classes="field-label")
                with Horizontal(classes="modal-buttons"):
                    yield ModalActionButton("No, go back", id="btn-cancel", variant="default", flat=True)
                    yield ModalActionButton("Yes, remove", id="btn-confirm", variant="error", flat=True)

    @on(Button.Pressed, "#btn-confirm")
    def delete(self) -> None:
        delete_entry(self._root, self._eid)
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(False)


class ConfigScreen(_ModalBase):
    def __init__(self, root, config: dict):
        super().__init__()
        self._root = root
        self._config = config
        self._sections = list(config.get("sections", DEFAULT_SECTIONS))

    @staticmethod
    def _section_icon_select_id(section: str) -> str:
        return f"cfg-section-icon-{section}"

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal"):
                yield Label("⚙  Configuration", id="modal-title")
                yield Rule()
                with ScrollableContainer(id="config-scroll"):
                    yield FieldBlock(
                        "Sections  (one per line)",
                        TextArea("\n".join(self._config.get("sections", [])), id="cfg-sections"),
                        f"Names are normalized to lowercase and duplicate sections are ignored after normalization. If you remove a section that still has entries, those entries move automatically to '{DEFAULT_REMOVED_SECTION_NAME}'. New sections get a random color and start with the generic icon until you reopen this screen to customize them.",
                    )
                    for section in self._sections:
                        yield FieldBlock(
                            f"Icon for {_section_label(section)}",
                            Select(
                                _section_icon_select_options(str(self._config.get("section_icons", {}).get(section, _section_icon(section)))),
                                value=str(self._config.get("section_icons", {}).get(section, _section_icon(section))),
                                id=self._section_icon_select_id(section),
                                allow_blank=False,
                            ),
                            f"Current color: {self._config.get('section_colors', {}).get(section, _section_color(section))}.",
                        )
                    yield FieldBlock(
                        "Semantic Model",
                        Select(
                            _semantic_model_options(str(self._config.get("semantic_model_name", ""))),
                            value=str(self._config.get("semantic_model_name", "")),
                            id="cfg-semantic-model-name",
                            allow_blank=False,
                        ),
                        _semantic_model_help(str(self._config.get("semantic_model_name", ""))),
                    )
                    yield FieldBlock(
                        "Semantic Model Idle TTL (seconds)",
                        Input(
                            value=str(self._config.get("semantic_model_idle_ttl_seconds", "")),
                            id="cfg-semantic-model-idle-ttl-seconds",
                        ),
                        "How long the embedding model stays loaded after use before being released from memory. Use 0 to unload immediately.",
                    )
                    yield FieldBlock(
                        "Max Content Length",
                        Input(value=str(self._config.get("max_content_length", "")), id="cfg-max-content-length"),
                        "Maximum number of characters allowed in a single memory entry.",
                    )
                    yield FieldBlock(
                        "Max Tag Length",
                        Input(value=str(self._config.get("max_tag_length", "")), id="cfg-max-tag-length"),
                        "Maximum length for each tag after sanitization.",
                    )
                    yield FieldBlock(
                        "Max Tags Per Entry",
                        Input(value=str(self._config.get("max_tags_per_entry", "")), id="cfg-max-tags-per-entry"),
                        "Maximum number of tags accepted on one memory entry.",
                    )
                    yield FieldBlock(
                        "Max Entries",
                        Input(value=str(self._config.get("max_entries", "")), id="cfg-max-entries"),
                        "Hard cap for stored entries. New writes are blocked after this limit.",
                    )
                    yield FieldBlock(
                        "Entry Batch Size",
                        Input(value=str(self._config.get("entry_batch_size", "")), id="cfg-entry-batch-size"),
                        "How many cards the TUI renders at a time while scrolling.",
                    )
                    yield FieldBlock(
                        "Entry Load Threshold",
                        Input(
                            value=str(self._config.get("entry_load_threshold", "")),
                            id="cfg-entry-load-threshold",
                        ),
                        "Distance from the bottom that triggers the next lazy-load batch in the TUI.",
                    )
                yield Rule()
                with Horizontal(classes="modal-buttons"):
                    yield ModalActionButton("Cancel", id="btn-cancel", variant="default")
                    yield ModalActionButton("Save", id="btn-save", variant="primary")

    def on_mount(self) -> None:
        super().on_mount()
        modal = self.query_one("#modal")
        modal.styles.width = 112
        modal.styles.height = 38

        scroll = self.query_one("#config-scroll", ScrollableContainer)
        scroll.styles.height = "1fr"
        scroll.styles.padding = (0, 1, 0, 0)

        sections = self.query_one("#cfg-sections", TextArea)
        sections.styles.height = 10

        for field in self.query(Input):
            field.styles.width = "100%"

        for field in self.query(Select):
            field.styles.width = "100%"

    @on(Button.Pressed, "#btn-save")
    def save(self) -> None:
        sections_text = self.query_one("#cfg-sections", TextArea).text
        sections = [line.strip() for line in sections_text.replace(",", "\n").splitlines() if line.strip()]
        section_icons = {}
        for section in self._sections:
            if section in sections:
                section_icons[section] = self.query_one(f"#{self._section_icon_select_id(section)}", Select).value

        updates = {
            "sections": sections,
            "section_icons": section_icons,
            "semantic_model_name": self.query_one("#cfg-semantic-model-name", Select).value,
            "semantic_model_idle_ttl_seconds": self.query_one("#cfg-semantic-model-idle-ttl-seconds", Input).value,
            "max_content_length": self.query_one("#cfg-max-content-length", Input).value,
            "max_tag_length": self.query_one("#cfg-max-tag-length", Input).value,
            "max_tags_per_entry": self.query_one("#cfg-max-tags-per-entry", Input).value,
            "max_entries": self.query_one("#cfg-max-entries", Input).value,
            "entry_batch_size": self.query_one("#cfg-entry-batch-size", Input).value,
            "entry_load_threshold": self.query_one("#cfg-entry-load-threshold", Input).value,
        }
        try:
            saved_config = update_config(self._root, updates)
        except Exception as error:
            self.notify(f"Config save failed: {error}", severity="error")
            return
        self.dismiss(saved_config)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(None)


def run_tui(root_path=None):
    """Run the TUI application."""
    RemembApp(root_path).run()


if __name__ == "__main__":
    RemembApp().run()