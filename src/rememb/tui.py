"""Textual TUI for rememb."""

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid, ScrollableContainer
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
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



class SectionButton(Button):
    """Botão da barra lateral com contador e ícone."""
    def __init__(self, section: str | None, count: int = 0, active: bool = False):
        name = section.capitalize() if section else "All"
        icon = SECTION_ICONS.get(section, "◎") if section else "◉"
        label = f"{icon} {name} "
        classes = "nav-btn"
        if section:
            classes += f" {section}"
        if active:
            classes += " -active"
        super().__init__(label, classes=classes)
        self.section_name = section
        self.count = count

    def render(self):
        name = str(self.label)
        return f"{name}\n[dim]({self.count})[/dim]"

class EntryCard(Static):
    """Card individual representando uma entrada de memória."""
    def __init__(self, entry: dict):
        super().__init__()
        self.entry = entry
        self.entry_id = entry.get("id", "???")
        self.section = entry.get("section", "context")
        self.color = SECTION_COLORS.get(self.section, "#888")

    def compose(self) -> ComposeResult:
        with Vertical(classes="card-container"):
            with Horizontal(classes="card-header"):
                yield Label(f"# [b]{self.entry_id[:8]}[/b]", classes="card-id")
                with Horizontal(classes="card-actions"):
                    yield Button("✎", id="edit-card", classes="action-icon-btn", tooltip="Edit")
                    yield Button("✕", id="delete-card", classes="action-icon-btn delete", tooltip="Delete")

            section_label = SECTION_LABELS.get(self.section, self.section.capitalize())
            yield Label(f"[b]{section_label}[/b]", classes="card-section-label")

            content = self.entry.get("content", "")
            yield Static(content, classes="card-content-text")

            tags = self.entry.get("tags", [])
            with Horizontal(classes="card-tags-area"):
                if not tags:
                    yield Label("")
                else:
                    for tag in tags:
                        yield Label(tag, classes="tag-pill")

    def on_mount(self):
        BG_CARD = "#1e2227"
        BG_HOVER = "#252a31"
        BG_DARK = "#121417"
        BORDER_DIM = "#2e343b"

        
        
        self.styles.height = "100%"
        self.styles.min_height = 15
        self.styles.padding = (1, 1, 1, 1)
        
        self.styles.border = ("round", self.color)
        self.styles.border_radius = 1

        
        header = self.query_one(".card-header")
        header.styles.height = 3
        header.styles.align = ("left", "middle")
        header.styles.margin_bottom = 1

        
        card_id = self.query_one(".card-id")
        card_id.styles.width = "1fr"
        card_id.styles.height = 3
        card_id.styles.content_align = ("left", "middle")

        
        actions = self.query_one(".card-actions")
        actions.styles.width = "auto"
        actions.styles.height = 3
        actions.styles.align = ("right", "middle")
        actions.styles.content_align = ("right", "middle")

        
        for btn in self.query(".action-icon-btn"):
            btn.styles.min_width = 6
            btn.styles.width = 6
            btn.styles.height = 3
            btn.styles.background = "transparent"
            btn.styles.border = ("round", self.color + "60")
            btn.styles.border_radius = 1
            btn.styles.color = self.color
            btn.styles.padding = (0, 0, 0, 0)
            btn.styles.margin_left = 1

        
        section_label = self.query_one(".card-section-label")
        section_label.styles.color = self.color
        section_label.styles.margin = (1, 0, 1, 0)

        
        content = self.query_one(".card-content-text")
        content.styles.height = "auto"
        content.styles.text_wrap = "wrap"
        content.styles.overflow = "hidden"
        content.styles.margin_bottom = 1

        
        tags_area = self.query_one(".card-tags-area")
        tags_area.styles.height = "auto"
        tags_area.styles.align = ("left", "top")

        for tag in self.query(".tag-pill"):
            tag.styles.color = self.color
            tag.styles.width = "auto"
            tag.styles.shrink = True
            tag.styles.padding = (0, 1, 0, 1)
            tag.styles.margin_right = 4
            tag.styles.border = ("round", self.color)
            tag.styles.border_radius = 1

    @on(Button.Pressed, "#edit-card")
    def on_edit(self):
        self.post_message(ActionTriggered("edit", self.entry))

    @on(Button.Pressed, "#delete-card")
    def on_delete(self):
        self.post_message(ActionTriggered("delete", self.entry))



class RemembApp(App):
    """Interface moderna para o rememb com Grid de Cards."""

    TITLE = "rememb"
    SUB_TITLE = "persistent memory"
    
    CSS = """
    #body { width: 100%; height: 1fr; }
    #sidebar { width: 26; height: 1fr; }
    #main-area { width: 1fr; height: 1fr; }
    #entries-grid { layout: grid; grid-size: 3; grid-rows: 18; grid-gutter: 1; height: auto; }
    #modal { width: 70; height: auto; }
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

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("rememb", id="sidebar-app-name")
                yield Button("＋ New", id="btn-new-entry", variant="primary")
                yield Label("SECTIONS", classes="sidebar-title")
                yield Vertical(id="sidebar-buttons-container")
                with Vertical(id="sidebar-bottom-buttons"):
                    yield Button("↻ Refresh", id="btn-refresh", classes="sidebar-bottom-btn")
                    yield Button("⏻ Quit", id="btn-quit", classes="sidebar-bottom-btn")

            with Vertical(id="main-area"):
                with Horizontal(id="search-container"):
                    yield Label("⌕", classes="search-icon")
                    yield Input(placeholder="Search memory...", id="search-box")
                with ScrollableContainer(id="main-scroll"):
                    yield Grid(id="entries-grid")

        yield Footer()

    def on_mount(self) -> None:
        self.theme = "nord"
        self._apply_styles()
        self._refresh_ui()

    def _apply_styles(self):
        """Apply programmatic styles to widgets."""
        
        BG_DARK = "#121417"
        BG_SIDEBAR = "#1a1d21"
        BG_CARD = "#1e2227"
        BG_HOVER = "#252a31"
        BORDER_DIM = "#2e343b"
        TEXT_DIM = "#6b7280"

        
        

        
        app_name = self.query_one("#sidebar-app-name")
        app_name.styles.text_align = "center"
        app_name.styles.text_style = "bold"
        app_name.styles.margin = (0, 0, 1, 0)

        
        sidebar = self.query_one("#sidebar")
        
        sidebar.styles.border_right = ("solid", BORDER_DIM)
        sidebar.styles.padding = (1, 1, 1, 1)

        
        title = self.query_one(".sidebar-title")
        title.styles.text_align = "center"
        title.styles.margin = (0, 0, 1, 0)

        
        btn_container = self.query_one("#sidebar-buttons-container")
        btn_container.styles.height = "1fr"

        
        bottom = self.query_one("#sidebar-bottom-buttons")
        bottom.styles.height = "auto"
        for btn in bottom.query(Button):
            btn.styles.width = "100%"
            btn.styles.margin_top = 1

        
        new_btn = self.query_one("#btn-new-entry")
        new_btn.styles.width = "100%"
        new_btn.styles.margin_bottom = 1

        
        search = self.query_one("#search-container")
        search.styles.height = 5
        
        search.styles.border_bottom = ("solid", BORDER_DIM)
        search.styles.padding = (1, 2, 1, 2)
        search.styles.align = ("left", "middle")

        
        search_box = self.query_one("#search-box")
        search_box.styles.width = "1fr"
        search_box.styles.max_width = 60
        
        search_box.styles.padding = (0, 1, 0, 1)

        
        search_icon = self.query_one(".search-icon")
        search_icon.styles.margin = (0, 1, 0, 1)

        
        main_scroll = self.query_one("#main-scroll")
        main_scroll.styles.padding = (1, 2, 1, 2)

        
        footer = self.query_one(Footer)
        

    def _get_root(self):
        if self._root_path: return self._root_path
        try: return find_root()
        except:
            root = global_root()
            if not is_initialized(root):
                from rememb.store import init
                init(root, project_name="global", global_mode=True)
            return root

    def _refresh_ui(self, section: str | None = None) -> None:
        """Atualiza Sidebar e Grid de Cards."""
        self.current_section = section
        root = self._get_root()
        stats = get_stats(root)

        
        side_container = self.query_one("#sidebar-buttons-container")
        side_container.query("*").remove()

        BG_CARD_HOVER = "#252a31"
        BORDER_DIM = "#2e343b"
        TEXT_DIM = "#6b7280"

        all_btn = SectionButton(None, stats["total"], active=(section is None))
        side_container.mount(all_btn)

        for sec_name in SECTIONS:
            count = stats["by_section"].get(sec_name, 0)
            btn = SectionButton(sec_name, count, active=(section == sec_name))
            side_container.mount(btn)

        
        for btn in side_container.query(SectionButton):
            btn.styles.width = "100%"
            btn.styles.height = "auto"
            btn.styles.min_height = 4
            btn.styles.margin = (0, 0, 1, 0)
            btn.styles.padding = (0, 1, 0, 1)
            btn.styles.border = None
            btn.styles.border_radius = 1
            btn.styles.background = "transparent"
            btn.styles.text_align = "left"
            btn.styles.content_align = ("left", "top")

            if btn.has_class("-active"):
                section_key = btn.section_name if btn.section_name else "all"
                color = SECTION_COLORS.get(section_key, "#95a5a6")
                btn.styles.background = color + "25"  
                btn.styles.color = color
                btn.styles.text_style = "bold"
                btn.styles.border_left = ("thick", color)


        
        self._load_entries(section)

    def _load_entries(self, section: str | None = None) -> None:
        root = self._get_root()
        try:
            self.current_entries = read_entries(root, section)
        except:
            self.current_entries = []

        grid = self.query_one("#entries-grid", Grid)
        grid.query("*").remove()
        
        for entry in self.current_entries:
            grid.mount(EntryCard(entry))

    @on(ActionTriggered)
    def handle_card_action(self, message: ActionTriggered):
        """Gerencia ações vindas de dentro dos cards."""
        if message.action == "edit":
            self._edit_entry(message.entry)
        elif message.action == "delete":
            self._delete_entry(message.entry)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if isinstance(event.button, SectionButton):
            section = event.button.section_name
            self._refresh_ui(section)
        elif btn_id == "btn-new-entry":
            self.action_new_entry()
        elif btn_id == "btn-refresh":
            self.action_refresh()
        elif btn_id == "btn-quit":
            self.app.exit()

    @on(Input.Submitted, "#search-box")
    def on_search(self, event: Input.Submitted):
        query = event.value.strip()
        if not query:
            self._refresh_ui(self.current_section)
            return
        
        root = self._get_root()
        results = search_entries(root, query, top_k=20)
        
        grid = self.query_one("#entries-grid", Grid)
        grid.query("*").remove()
        for entry in results:
            grid.mount(EntryCard(entry))

    
    def action_new_entry(self) -> None:
        self.push_screen(NewEntryScreen(self._get_root()), lambda saved: self._refresh_ui(self.current_section) if saved else None)

    def _edit_entry(self, entry: dict) -> None:
        self.push_screen(EditEntryScreen(self._get_root(), entry), lambda saved: self._refresh_ui(self.current_section) if saved else None)

    def _delete_entry(self, entry: dict) -> None:
        self.push_screen(DeleteConfirmScreen(self._get_root(), entry["id"], entry["content"]), lambda del_ok: self._refresh_ui(self.current_section) if del_ok else None)

    def action_refresh(self) -> None:
        self._refresh_ui(self.current_section)
        self.notify("Memory refreshed")

    def action_focus_search(self) -> None:
        self.query_one("#search-box").focus()



class NewEntryScreen(Screen):
    def __init__(self, root): super().__init__(); self._root = root
    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label("New Memory Entry", id="modal-title")
            yield Label("Content:", classes="field-label")
            yield TextArea(id="content-input", classes="field-input")
            yield Label("Section:", classes="field-label")
            yield Input(placeholder="e.g. project, context, user...", id="section-input", classes="field-input")
            yield Label("Tags (comma-separated):", classes="field-label")
            yield Input(placeholder="tag1, tag2", id="tags-input", classes="field-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="error")
                yield Button("Save", id="btn-save", variant="success")
    @on(Button.Pressed, "#btn-save")
    def save(self):
        content = self.query_one("#content-input").text.strip()
        if not content: return
        section = self.query_one("#section-input").value.strip() or "context"
        tags = [t.strip() for t in self.query_one("#tags-input").value.split(",") if t.strip()]
        write_entry(self._root, section, content, tags)
        self.dismiss(True)
    @on(Button.Pressed, "#btn-cancel")
    def cancel(self): self.dismiss(False)

class EditEntryScreen(Screen):
    def __init__(self, root, entry): super().__init__(); self._root = root; self._entry = entry
    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(f"Edit Entry {self._entry['id'][:8]}", id="modal-title")
            yield Label("Content:", classes="field-label")
            yield TextArea(self._entry['content'], id="content-input", classes="field-input")
            yield Label("Section:", classes="field-label")
            yield Input(value=self._entry['section'], id="section-input", classes="field-input")
            yield Label("Tags:", classes="field-label")
            yield Input(value=", ".join(self._entry['tags']), id="tags-input", classes="field-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel")
                yield Button("Update", id="btn-save", variant="primary")
    @on(Button.Pressed, "#btn-save")
    def update(self):
        edit_entry(self._root, self._entry['id'], content=self.query_one("#content-input").text, 
                section=self.query_one("#section-input").value, 
                tags=[t.strip() for t in self.query_one("#tags-input").value.split(",") if t.strip()])
        self.dismiss(True)
    @on(Button.Pressed, "#btn-cancel")
    def cancel(self): self.dismiss(False)

class DeleteConfirmScreen(Screen):
    def __init__(self, root, entry_id, content): super().__init__(); self._root = root; self._eid = entry_id; self._c = content
    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label("Remove this memory?", id="modal-title")
            yield Label(f"ID: [b]{self._eid[:8]}[/b]", classes="card-id")
            yield Label(f'"{self._c[:150]}..."', classes="card-content-text")
            yield Label("[bold red]This action is irreversible.[/bold red]", classes="field-label")
            with Horizontal(classes="modal-buttons"):
                yield Button("No, go back", id="btn-cancel")
                yield Button("Yes, remove", id="btn-confirm", variant="error")
    @on(Button.Pressed, "#btn-confirm")
    def delete(self): delete_entry(self._root, self._eid); self.dismiss(True)
    @on(Button.Pressed, "#btn-cancel")
    def cancel(self): self.dismiss(False)

def run_tui(root_path=None):
    """Run the TUI application."""
    RemembApp(root_path).run()

if __name__ == "__main__":
    RemembApp().run()