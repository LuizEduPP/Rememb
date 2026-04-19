"""Textual TUI for rememb."""

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
)
from textual.binding import Binding
from textual import on
from textual.message import Message

from rememb.store import read_entries, search_entries, get_stats, write_entry, edit_entry, delete_entry, SECTIONS
from rememb.utils import find_root, global_root, is_initialized

SECTION_ICONS = {
    "project": "◈",
    "actions": "↯",
    "systems": "⛭",
    "requests": "✉",
    "user": "☻",
    "context": "✦",
}

SECTION_COLORS = {
    "project": "#d84848",
    "actions": "#d08020",
    "systems": "#d4c430",
    "requests": "#40c040",
    "user": "#20d4c4",
    "context": "#c060f0",
    "all": "#95a5a6",
}

SECTION_LABELS = {
    "project": "Project",
    "actions": "Actions",
    "systems": "Systems",
    "requests": "Requests",
    "user": "User",
    "context": "Context",
}


class ActionTriggered(Message):
    """Enviada quando um botão dentro do card é clicado."""
    def __init__(self, action: str, entry: dict) -> None:
        super().__init__()
        self.action = action
        self.entry = entry


class SectionItem(Static):
    """Item de seção clicável na sidebar."""

    def __init__(self, section: str | None, count: int = 0, active: bool = False):
        super().__init__()
        self.section_name = section
        self.count = count
        self._active = active
        self._color = SECTION_COLORS.get(section if section else "all", "#95a5a6")
        name = SECTION_LABELS.get(section, "All") if section else "All"
        icon = SECTION_ICONS.get(section, "◉") if section else "◉"
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
    """Emitida quando o usuário clica numa seção."""
    def __init__(self, section: str | None) -> None:
        super().__init__()
        self.section = section


class EntryCard(Widget):
    """Card individual representando uma entrada de memória."""

    def __init__(self, entry: dict):
        import uuid
        uid = uuid.uuid4().hex[:8]
        super().__init__()
        self.entry = entry
        self.entry_id = entry.get("id", "???")
        self.section = entry.get("section", "context")
        self.color = SECTION_COLORS.get(self.section, "#888")
        self._uid = uid

    def compose(self) -> ComposeResult:
        with Vertical(id="card-root"):
            with Vertical(id="card-body"):
                with Horizontal():
                    yield Label(
                        f"[dim]#{self.entry_id[:8]}[/dim]",
                        id=f"cid-{self._uid}",
                    )
                    yield Button("✎", id="edit-card", classes="act-btn", tooltip="Edit entry")
                    yield Button("✕", id="delete-card", classes="act-btn del-btn", tooltip="Delete entry")

                section_label = SECTION_LABELS.get(self.section, self.section.capitalize())
                icon = SECTION_ICONS.get(self.section, "◎")
                yield Label(
                    f"[b]{icon}  {section_label}[/b]",
                    id=f"csec-{self._uid}",
                )

                yield Rule(line_style="heavy")

                content = self.entry.get("content", "")
                preview = content[:150] + "…" if len(content) > 150 else content
                yield Static(preview, id=f"ccnt-{self._uid}")

            tags = self.entry.get("tags", [])
            if tags:
                with Vertical(id=f"cftr-{self._uid}"):
                    yield Rule()
                    row: list = []
                    rows: list = []
                    line_len = 0
                    max_w = 36
                    for tag in tags:
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
                        with Horizontal(classes="tag-row"):
                            for tag in row_tags:
                                yield Label(f" {tag} ", classes="tag-pill")

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
            btn.styles.min_width = 5
            btn.styles.width = 5
            btn.styles.height = 3
            btn.styles.padding = (0, 0)
            btn.styles.content_align = ("center", "middle")
            btn.styles.background = "transparent"
            btn.styles.border = ("round", self.color + "66")
            btn.styles.color = self.color

        sec_lbl = self.query_one(f"#csec-{self._uid}")
        sec_lbl.styles.color = self.color
        sec_lbl.styles.margin = (1, 0, 0, 0)
        sec_lbl.styles.height = 2

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

            for row in self.query(".tag-row"):
                row.styles.height = 3
                row.styles.margin_bottom = 1
            for pill in self.query(".tag-pill"):
                pill.styles.color = self.color
                pill.styles.border = ("round", self.color + "88")
                pill.styles.padding = (0, 1)
                pill.styles.margin_right = 1
                pill.styles.width = "auto"
                pill.styles.shrink = True
                pill.styles.height = 3
                pill.styles.content_align = ("center", "middle")
        except Exception:
            pass

    @on(Button.Pressed, "#edit-card")
    def on_edit(self) -> None:
        self.post_message(ActionTriggered("edit", self.entry))

    @on(Button.Pressed, "#delete-card")
    def on_delete(self) -> None:
        self.post_message(ActionTriggered("delete", self.entry))


class RemembApp(App):
    """Interface moderna para o rememb com Grid de Cards."""

    TITLE = "Rememb"
    SUB_TITLE = "Persistent memory standard for AI agents"

    CSS = """
    #body    { width: 100%; height: 1fr; }
    #sidebar { width: 26; height: 1fr; }
    #main-area { width: 1fr; height: 1fr; }
    #content-area { width: 1fr; height: 1fr; }
    #entries-grid { layout: grid; grid-size: 3; grid-gutter: 1; height: auto; }
    #side-panel { width: 50; height: 1fr; display: none; border-left: solid #2e343b; }
    #modal   { width: 72; height: auto; }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_entry", "New", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, root_path=None):
        super().__init__()
        self._root_path = root_path
        self.current_entries = []
        self.current_section = None
        self._panel_mode: str | None = None
        self._panel_entry: dict | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Button("＋  New Entry", id="btn-new-entry", variant="primary", flat=True)
                yield Rule()
                yield Label(" SECTIONS", id="sections-title")
                yield Rule()
                yield ScrollableContainer(id="sidebar-sections")
                yield Rule()
                yield Button("↻  Refresh", id="btn-refresh", variant="warning", flat=True)
                yield Button("⏻  Quit", id="btn-quit", variant="error", flat=True)

            with Vertical(id="main-area"):
                with Horizontal(id="search-bar"):
                    yield Input(placeholder="⌕  Search memory...", id="search-box")
                yield Rule()
                with Horizontal(id="content-area"):
                    with ScrollableContainer(id="main-scroll"):
                        yield Grid(id="entries-grid")
                    with ScrollableContainer(id="side-panel"):
                        yield Label("", id="panel-title")
                        yield Rule()
                        yield Static("")
                        yield Label("Content", classes="field-label")
                        yield Static("")
                        yield TextArea("", id="panel-content")
                        yield Static("")
                        yield Static("")
                        yield Label("Section", classes="field-label")
                        yield Static("")
                        yield Select(SECTION_OPTIONS, value="context", id="panel-section", allow_blank=False)
                        yield Static("")
                        yield Static("")
                        yield Label("Tags  (comma-separated)", classes="field-label")
                        yield Static("")
                        yield Input(placeholder="tag1, tag2", id="panel-tags")
                        yield Static("")
                        yield Static("")
                        yield Rule()
                        with Horizontal(id="panel-buttons"):
                            yield Button("Cancel", id="panel-cancel", variant="default", flat=True)
                            yield Button("Save", id="panel-save", variant="success", flat=True)

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

        new_btn = self.query_one("#btn-new-entry")
        new_btn.styles.width = "100%"
        new_btn.styles.margin_bottom = 1

        sec_title = self.query_one("#sections-title")
        sec_title.styles.text_style = "bold dim"
        sec_title.styles.height = 1
        sec_title.styles.content_align = ("left", "middle")

        sections_area = self.query_one("#sidebar-sections")
        sections_area.styles.height = "1fr"

        refresh_btn = self.query_one("#btn-refresh")
        refresh_btn.styles.width = "100%"
        refresh_btn.styles.margin_top = 1

        quit_btn = self.query_one("#btn-quit")
        quit_btn.styles.width = "100%"
        quit_btn.styles.margin_top = 1

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

        for lbl in panel.query(".field-label"):
            lbl.styles.height = 2
            lbl.styles.content_align = ("left", "middle")

        panel_btns = self.query_one("#panel-buttons")
        panel_btns.styles.height = 4
        panel_btns.styles.align = ("right", "middle")
        panel_btns.styles.margin_top = 2
        for btn in panel_btns.query(Button):
            btn.styles.margin_left = 1

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
        self.current_section = section
        root = self._get_root()
        stats = get_stats(root)

        container = self.query_one("#sidebar-sections")
        container.remove_children()

        all_item = SectionItem(None, stats["total"], active=(section is None))
        container.mount(all_item)

        for sec_name in SECTIONS:
            count = stats["by_section"].get(sec_name, 0)
            item = SectionItem(sec_name, count, active=(section == sec_name))
            container.mount(item)

        self._load_entries(section)

    def _load_entries(self, section: str | None = None) -> None:
        root = self._get_root()
        try:
            self.current_entries = read_entries(root, section)
        except Exception:
            self.current_entries = []

        grid = self.query_one("#entries-grid", Grid)
        grid.remove_children()
        for entry in self.current_entries:
            grid.mount(EntryCard(entry))

    @on(SectionSelected)
    def handle_section_selected(self, message: SectionSelected) -> None:
        self._refresh_ui(message.section)

    @on(ActionTriggered)
    def handle_card_action(self, message: ActionTriggered) -> None:
        if message.action == "edit":
            self._edit_entry(message.entry)
        elif message.action == "delete":
            self._delete_entry(message.entry)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-new-entry":
            self.action_new_entry()
        elif btn_id == "btn-refresh":
            self.action_refresh()
        elif btn_id == "btn-quit":
            self.app.exit()

    @on(Input.Submitted, "#search-box")
    def on_search(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            self._refresh_ui(self.current_section)
            return
        root = self._get_root()
        results = search_entries(root, query, top_k=20)
        grid = self.query_one("#entries-grid", Grid)
        grid.remove_children()
        for entry in results:
            grid.mount(EntryCard(entry))

    def _open_panel(self, mode: str, entry: dict | None = None) -> None:
        self._panel_mode = mode
        self._panel_entry = entry
        panel = self.query_one("#side-panel")
        panel.display = True

        title = self.query_one("#panel-title")
        title.update("❆  New Entry" if mode == "new" else f"✎  Edit  [dim]#{entry['id'][:8]}[/dim]")

        content_ta = self.query_one("#panel-content", TextArea)
        content_ta.clear()
        if mode == "edit" and entry:
            content_ta.insert(entry["content"])

        sel = self.query_one("#panel-section", Select)
        sel.value = (entry["section"] if mode == "edit" and entry else "context")

        tags_input = self.query_one("#panel-tags", Input)
        tags_input.value = ", ".join(entry["tags"]) if mode == "edit" and entry else ""

        self._update_grid_columns()
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

    def _edit_entry(self, entry: dict) -> None:
        self._open_panel("edit", entry)

    def _delete_entry(self, entry: dict) -> None:
        self.push_screen(DeleteConfirmScreen(self._get_root(), entry["id"], entry["content"]), lambda del_ok: self._refresh_ui(self.current_section) if del_ok else None)

    def action_refresh(self) -> None:
        self._refresh_ui(self.current_section)
        self.notify("Memory refreshed", severity="information")

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


class _ModalBase(Screen):
    """Base para telas modais centralizadas."""

    def on_mount(self) -> None:
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
            lbl.styles.margin_top = 1

        try:
            btn_row = self.query_one(".modal-buttons")
            btn_row.styles.height = 4
            btn_row.styles.align = ("right", "middle")
            btn_row.styles.margin_top = 1
            for btn in btn_row.query(Button):
                btn.styles.margin_left = 1
        except Exception:
            pass


SECTION_OPTIONS = [
    (f"{SECTION_ICONS.get(s, '◎')}  {SECTION_LABELS.get(s, s.capitalize())}", s)
    for s in ["project", "actions", "systems", "requests", "user", "context"]
]


class NewEntryScreen(_ModalBase):
    def __init__(self, root):
        super().__init__()
        self._root = root

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal"):
                yield Label("❆  New Memory Entry", id="modal-title")
                yield Rule()
                yield Label("Content", classes="field-label")
                yield TextArea(id="content-input")
                yield Label("Section", classes="field-label")
                yield Select(SECTION_OPTIONS, value="context", id="section-input", allow_blank=False)
                yield Label("Tags  (comma-separated)", classes="field-label")
                yield Input(placeholder="tag1, tag2, tag3", id="tags-input")
                yield Rule()
                with Horizontal(classes="modal-buttons"):
                    yield Button("Cancel", id="btn-cancel", variant="default")
                    yield Button("Save", id="btn-save", variant="success")

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
    def __init__(self, root, entry):
        super().__init__()
        self._root = root
        self._entry = entry

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="modal"):
                yield Label(f"✎  Edit  [dim]#{self._entry['id'][:8]}[/dim]", id="modal-title")
                yield Rule()
                yield Label("Content", classes="field-label")
                yield TextArea(self._entry["content"], id="content-input")
                yield Label("Section", classes="field-label")
                yield Select(SECTION_OPTIONS, value=self._entry["section"], id="section-input", allow_blank=False)
                yield Label("Tags  (comma-separated)", classes="field-label")
                yield Input(value=", ".join(self._entry["tags"]), id="tags-input")
                yield Rule()
                with Horizontal(classes="modal-buttons"):
                    yield Button("Cancel", id="btn-cancel", variant="default")
                    yield Button("Update", id="btn-save", variant="primary")

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
                    yield Button("No, go back", id="btn-cancel", variant="default", flat=True)
                    yield Button("Yes, remove", id="btn-confirm", variant="error", flat=True)

    @on(Button.Pressed, "#btn-confirm")
    def delete(self) -> None:
        delete_entry(self._root, self._eid)
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(False)


def run_tui(root_path=None):
    """Run the TUI application."""
    RemembApp(root_path).run()


if __name__ == "__main__":
    RemembApp().run()