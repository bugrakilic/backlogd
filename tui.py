#!/usr/bin/env python3
"""backlogd TUI (Phase 3): full-screen Textual app.

Classic CLI stays in backlogd.py. This module drives the same
BacklogManager (filter/sort/add/update/remove/import/export), so the
YAML format never diverges between CLI and TUI.
Run:  python backlogd.py tui   (or:  python tui.py)
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    Static,
)

from backlogd import BacklogManager, coerce_points, load_config, save_config

# Same visual language as the CLI theme (ASCII-safe, Windows-friendly).
PRI_STYLE = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "green",
}
ST_STYLE = {
    "todo": "blue",
    "in_progress": "yellow",
    "done": "green",
    "blocked": "red",
}
PRI_ICON = {"critical": "!!", "high": "^", "medium": "o", "low": "-"}
ST_ICON = {"todo": "( )", "in_progress": "(~)", "done": "(x)", "blocked": "(!)"}

SORTS = [None, "priority", "status", "points", "updated", "title"]
BOARD_ORDER = ["todo", "in_progress", "blocked", "done"]
BOARD_LABEL = {"todo": "( ) To Do", "in_progress": "(~) Doing",
               "blocked": "(!) Blocked", "done": "(x) Done"}
NEXT_STATUS = {"todo": "in_progress", "in_progress": "done",
               "blocked": "todo", "done": None}

TABLE_COLUMNS = [
    ("ID", "id"),
    ("Title", "title"),
    ("Priority", "priority"),
    ("Status", "status"),
    ("Sprint", "sprint"),
    ("Epic", "epic"),
    ("Assignee", "assignee"),
    ("Pts", "points"),
]

# Single source of truth for palette + help: (action, title, keys).
COMMAND_REGISTRY = [
    ("goto_table", "Go to Table view", "1"),
    ("goto_board", "Go to Board view", "2"),
    ("goto_stats", "Go to Stats view", "3"),
    ("focus_filter", "Focus filter", "/"),
    ("back_to_table", "Back to table / clear filter", "esc"),
    ("cycle_sort", "Cycle sort order", "s"),
    ("new_item", "New item", "n"),
    ("edit_item", "Edit selected item", "e"),
    ("delete_item", "Delete selected item", "d"),
    ("show_detail", "Show item details", "enter"),
    ("advance_item", "Advance status", "space"),
    ("new_project", "New project", "N"),
    ("delete_project", "Delete current project", "D"),
    ("export_dialog", "Export...", "X"),
    ("import_dialog", "Import CSV...", "I"),
    ("open_palette", "Command palette", "ctrl+k"),
    ("show_help", "Help", "?"),
    ("smart_quit", "Quit", "q"),
]


def _cell(text: str, style: str = "") -> Text:
    return Text(text, style=style or "")


class ItemsTable(DataTable):
    """Table where Enter opens the detail view.

    Stock DataTable binds enter to select_cursor (widget bindings beat
    app bindings), which trapped our app-level `enter` = detail action.
    """

    BINDINGS = [b for b in DataTable.BINDINGS if b.key != "enter"] + [
        Binding("enter", "open_detail", "Detail", show=False)
    ]

    def action_open_detail(self) -> None:
        show = getattr(self.app, "action_show_detail", None)
        if show is not None:
            show()


def _ascii_bar(count: int, total: int, width: int = 14) -> str:
    if total <= 0:
        return "-" * width
    filled = round(count / total * width)
    return "#" * filled + "-" * (width - filled)


class HelpScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Close"),
                ("q", "app.pop_screen", "Close")]

    def compose(self) -> ComposeResult:
        lines = ["backlogd TUI keys\n"]
        for _action, title, keys in COMMAND_REGISTRY:
            lines.append(f"{keys + ' ':12} {title}")
        lines += ["",
                  "tab ............ cycle focus (sidebar/filter/table)",
                  "arrows ......... move in focused widget",
                  "Filtering also narrows the board; stats ignores it."]
        yield Static("\n".join(lines), id="help-box")


class DetailScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Close"),
                ("e", "edit", "Edit"), ("d", "delete", "Delete")]

    def __init__(self, project: str, item_id: str) -> None:
        super().__init__()
        self.project = project
        self.item_id = item_id

    def compose(self) -> ComposeResult:
        app = self.app
        item = next((i for i in app.manager.projects.get(self.project, [])
                     if i.id == self.item_id), None)
        with Vertical(id="modal"):
            if item is None:
                yield Static("Item no longer exists.", id="detail-meta")
            else:
                yield Label(f"{self.project}: {item.id} - {item.title}",
                            id="detail-title")
                yield Markdown(item.description or "_No description._",
                               id="detail-desc")
                yield Static(
                    f"Priority: {item.priority}   Status: {item.status}\n"
                    f"Sprint: {item.sprint or '-'}   Epic: {item.epic or '-'}\n"
                    f"Assignee: {item.assignee or '-'}   "
                    f"Points: {item.story_points if item.story_points else '-'}\n"
                    f"Created: {(item.created_at or '')[:19]}\n"
                    f"Updated: {(item.updated_at or '')[:19]}",
                    id="detail-meta")
            with Horizontal(id="btn-row"):
                yield Button("Edit (e)", id="btn-edit")
                yield Button("Delete (d)", id="btn-del")
                yield Button("Close", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss(None)
        elif event.button.id == "btn-edit":
            self.dismiss(None)
            self.app.edit_item_by_ref((self.project, self.item_id))
        elif event.button.id == "btn-del":
            self.dismiss(None)
            self.app.delete_item_by_ref((self.project, self.item_id))

    def action_edit(self) -> None:
        self.dismiss(None)
        self.app.edit_item_by_ref((self.project, self.item_id))

    def action_delete(self) -> None:
        self.dismiss(None)
        self.app.delete_item_by_ref((self.project, self.item_id))


class ItemFormScreen(ModalScreen):
    """New / edit form. Validates like the CLI (title required, 0-100 pts)."""

    def __init__(self, project: str, item_id: Optional[str] = None) -> None:
        super().__init__()
        self.project = project
        self.item_id = item_id

    def compose(self) -> ComposeResult:
        app = self.app
        item = None
        if self.item_id:
            item = next((i for i in app.manager.projects.get(self.project, [])
                         if i.id == self.item_id), None)
        title = "Edit item" if item else "New item"
        with Vertical(id="modal"):
            yield Label(title, id="modal-title")
            yield Static("", id="m-error")
            yield Input(value=item.title if item else "",
                        placeholder="Title (required)", id="m-title")
            yield Input(value=item.description if item else "",
                        placeholder="Description", id="m-desc")
            yield Select([("low", "low"), ("medium", "medium"),
                          ("high", "high"), ("critical", "critical")],
                         value=item.priority if item else "medium",
                         id="m-priority")
            if item:
                yield Select([("todo", "todo"), ("in_progress", "in_progress"),
                              ("done", "done"), ("blocked", "blocked")],
                             value=item.status, id="m-status")
            yield Input(
                value=item.sprint if item and item.sprint else "",
                placeholder="Sprint",
                suggester=SuggestFromList(
                    app.manager.distinct_values(self.project, "sprint"),
                    case_sensitive=False),
                id="m-sprint")
            yield Input(
                value=item.epic if item and item.epic else "",
                placeholder="Epic",
                suggester=SuggestFromList(
                    app.manager.distinct_values(self.project, "epic"),
                    case_sensitive=False),
                id="m-epic")
            yield Input(
                value=item.assignee if item and item.assignee else "",
                placeholder="Assignee",
                suggester=SuggestFromList(
                    app.manager.distinct_values(self.project, "assignee"),
                    case_sensitive=False),
                id="m-assignee")
            yield Input(
                value=str(item.story_points) if item and item.story_points else "",
                placeholder="Story points 0-100 (optional)", id="m-points")
            with Horizontal(id="btn-row"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-save":
            self._save()

    def _save(self) -> None:
        app = self.app
        err = self.query_one("#m-error", Static)
        title = self.query_one("#m-title", Input).value.strip()
        if not title:
            err.update("Title is required.")
            return
        points_raw = self.query_one("#m-points", Input).value.strip()
        points = coerce_points(points_raw)
        if points_raw and points is None:
            err.update("Story points must be 0-100 (or empty).")
            return
        desc = self.query_one("#m-desc", Input).value
        priority = self.query_one("#m-priority", Select).value
        sprint = self.query_one("#m-sprint", Input).value.strip() or None
        epic = self.query_one("#m-epic", Input).value.strip() or None
        assignee = self.query_one("#m-assignee", Input).value.strip() or None
        if self.item_id:
            data = {"title": title, "description": desc, "priority": priority,
                    "sprint": sprint, "epic": epic, "assignee": assignee,
                    "story_points": points}
            try:
                data["status"] = self.query_one("#m-status", Select).value
            except Exception:
                pass
            ok = app.manager.update_item(self.project, self.item_id, **data)
            if ok:
                app.notify(f"Updated {self.item_id}")
            self.dismiss(ok)
        else:
            ok = app.manager.add_item(self.project, title, desc,
                                      priority=priority, sprint=sprint,
                                      epic=epic, assignee=assignee,
                                      story_points=points)
            if ok:
                app.notify(f"Added to {self.project}")
            self.dismiss(ok)


class ConfirmScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel"),
                ("y", "confirm", "Confirm"), ("n", "app.pop_screen", "Cancel")]

    def __init__(self, message: str, ok_label: str = "Delete") -> None:
        super().__init__()
        self.message = message
        self.ok_label = ok_label

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Static(self.message, id="confirm-msg")
            with Horizontal(id="btn-row"):
                yield Button(self.ok_label, variant="error", id="btn-ok")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-ok")

    def action_confirm(self) -> None:
        self.dismiss(True)


class ProjectScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label("New project", id="modal-title")
            yield Static("", id="m-error")
            yield Input(placeholder="Project name", id="m-name")
            with Horizontal(id="btn-row"):
                yield Button("Create", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        else:
            name = self.query_one("#m-name", Input).value.strip()
            if not name:
                self.query_one("#m-error", Static).update("Name is required.")
                return
            if name in self.app.manager.projects:
                self.query_one("#m-error", Static).update("Project exists.")
                return
            self.app.manager.create_project(name)
            self.dismiss(name)


class ExportScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label("Export", id="modal-title")
            yield Select([("This project", "current"), ("All projects", "all")],
                         value="current", id="m-scope")
            yield Select([("CSV", "csv"), ("Excel", "xlsx")],
                         value="csv", id="m-format")
            yield Input(placeholder="Filename (empty = auto)", id="m-file")
            with Horizontal(id="btn-row"):
                yield Button("Export", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return
        app = self.app
        scope = self.query_one("#m-scope", Select).value
        fmt = self.query_one("#m-format", Select).value
        filename = self.query_one("#m-file", Input).value.strip() or None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if scope == "all":
            if not filename:
                filename = f"backlogd_all_{ts}.{fmt}"
            ok = (app.manager.export_all_to_csv(filename) if fmt == "csv"
                  else app.manager.export_all_to_xlsx(filename))
        else:
            if not app.project:
                self.dismiss(None)
                app.notify("No project selected", severity="warning")
                return
            if not filename:
                filename = f"{app.project}_backlog_{ts}.{fmt}"
            ok = (app.manager.export_to_csv(app.project, filename) if fmt == "csv"
                  else app.manager.export_to_xlsx(app.project, filename))
        if ok:
            app.notify(f"Exported to {filename}")
        self.dismiss(filename if ok else None)


class ImportScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        app = self.app
        with Vertical(id="modal"):
            yield Label("Import CSV", id="modal-title")
            yield Static("", id="m-error")
            yield Input(value=app.project or "", placeholder="Project",
                        id="m-project")
            yield Input(placeholder="CSV file path", id="m-file")
            with Horizontal(id="btn-row"):
                yield Button("Import", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
            return
        app = self.app
        project = self.query_one("#m-project", Input).value.strip()
        filename = self.query_one("#m-file", Input).value.strip()
        if not project or not filename:
            self.query_one("#m-error", Static).update(
                "Project and file are required.")
            return
        ok = app.manager.import_from_csv(project, filename)
        if ok:
            app.notify(f"Imported into {project}")
        self.dismiss(ok)


class BacklogCommands(Provider):
    """Ctrl+K palette covering every TUI operation."""

    def _hits(self, query: str, scored: bool):
        from textual.command import DiscoveryHit
        for action, title, keys in COMMAND_REGISTRY:
            if query and query not in f"{title} {keys}".lower():
                continue
            # Parentheses, not [brackets]: the palette parses display
            # text as Rich markup and [/] would crash it.
            label = f"{title}  ({keys})"
            cmd = getattr(self.app, f"action_{action}")
            if scored:
                yield Hit(1.0, label, cmd, help="backlogd")
            else:
                yield DiscoveryHit(label, cmd, help="backlogd")

    async def discover(self) -> Hits:
        for hit in self._hits("", scored=False):
            yield hit

    async def search(self, query: str) -> Hits:
        for hit in self._hits(query.lower(), scored=True):
            yield hit


class BacklogApp(App):
    """Sidebar + Table / Board / Stats views with full item management."""

    COMMANDS = App.COMMANDS | {BacklogCommands}

    CSS = """
    #sidebar { width: 30; border-right: solid green; }
    #side-title { text-style: bold; padding: 0 1; }
    #side-hint { padding: 0 1; color: gray; }
    #main { width: 1fr; }
    #tabbar { padding: 0 1; text-style: bold; }
    #filterbar { height: auto; margin: 0 1; }
    #filter { width: 1fr; }
    #f-status { width: 12; margin-left: 1; }
    #f-priority { width: 10; margin-left: 1; }
    #f-sprint { width: 16; margin-left: 1; }
    #f-epic { width: 16; margin-left: 1; }
    #statusline { padding: 0 1; color: gray; }
    #help-box { padding: 2 4; border: solid cyan; width: 64; }
    #board-cols { height: 1fr; }
    .bcol { width: 1fr; border-right: solid gray; }
    .bcol-head { text-style: bold; padding: 0 1; }
    #modal { padding: 1 2; border: solid cyan; width: 64; }
    #modal-title { text-style: bold; }
    #m-error { color: red; }
    #detail-title { text-style: bold; }
    #btn-row { height: auto; margin-top: 1; }
    #btn-row Button { margin-right: 1; }
    """

    BINDINGS = [
        ("q", "smart_quit", "Quit"),
        ("/", "focus_filter", "Filter"),
        ("escape", "back_to_table", "Back"),
        ("s", "cycle_sort", "Sort"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("1", "goto_table", "Table"),
        ("2", "goto_board", "Board"),
        ("3", "goto_stats", "Stats"),
        ("n", "new_item", "New"),
        ("e", "edit_item", "Edit"),
        ("d", "delete_item", "Delete"),
        ("enter", "show_detail", "Detail"),
        ("space", "advance_item", "Advance"),
        ("N", "new_project", "NewProj"),
        ("D", "delete_project", "DelProj"),
        ("X", "export_dialog", "Export"),
        ("I", "import_dialog", "Import"),
        ("ctrl+k", "command_palette", "Palette"),
        ("?", "show_help", "Help"),
    ]

    def __init__(self, data_dir: str = "database_backlogd",
                 project: Optional[str] = None) -> None:
        super().__init__()
        self.manager = BacklogManager(data_dir=data_dir)
        names = sorted(self.manager.projects)
        if project in self.manager.projects:
            self.project: Optional[str] = project
        else:
            # Resume last CLI/TUI project like the interactive shell does.
            try:
                last = load_config().get("last_project")
            except Exception:
                last = None
            self.project = (last if last in self.manager.projects
                            else (names[0] if names else None))
        self._projects: List[str] = []
        self._sort_idx = 0
        self._filter = ""
        self._f_status: str = "open"
        self._f_priority: Optional[str] = None
        self._f_sprint: Optional[str] = None
        self._f_epic: Optional[str] = None
        self._view = "table"
        self.show_all = False
        self._table_refs: List[tuple] = []
        self._board: Dict[str, list] = {}
        self._stats_text = ""
        self._table_has_project_col = False

    def _remember(self) -> None:
        try:
            save_config({"last_project": self.project})
        except Exception:
            pass

    # -- layout ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Projects", id="side-title")
                yield ListView(id="projects")
                yield Static("N new - D delete", id="side-hint")
            with Vertical(id="main"):
                yield Static("", id="tabbar")
                with Horizontal(id="filterbar"):
                    yield Input(placeholder="Filter id/title/desc... (/ in, enter/esc out)",
                                id="filter")
                    yield Select([("open", "open"), ("all", "all"),
                                  ("todo", "todo"), ("doing", "in_progress"),
                                  ("blocked", "blocked"), ("done", "done")],
                                 value="open", id="f-status")
                    yield Select([("all", "all"), ("low", "low"),
                                  ("medium", "medium"), ("high", "high"),
                                  ("critical", "critical")],
                                 value="all", id="f-priority")
                    yield Select([("sprint: all", "all")], value="all",
                                 id="f-sprint")
                    yield Select([("epic: all", "all")], value="all",
                                 id="f-epic")
                with Vertical(id="view-table"):
                    yield ItemsTable(id="items", zebra_stripes=True)
                with Horizontal(id="board-cols"):
                    for st in BOARD_ORDER:
                        with Vertical(classes="bcol"):
                            yield Label("", classes="bcol-head",
                                        id=f"head-{st}")
                            yield ListView(id=f"col-{st}")
                with VerticalScroll(id="view-stats"):
                    yield Static("", id="stats-body")
                yield Static("", id="statusline")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#items", DataTable)
        for label, key in TABLE_COLUMNS:
            table.add_column(label, key=key)
        self.query_one("#board-cols").styles.display = "none"
        self.query_one("#view-stats").styles.display = "none"
        self.refresh_projects()
        self.refresh_current_view()
        self._update_tabbar()
        table.focus()

    # -- guards ---------------------------------------------------------
    def _modal_open(self) -> bool:
        return isinstance(self.screen, ModalScreen)

    def _typing(self) -> bool:
        return isinstance(self.focused, (Input, Select))

    # -- data -----------------------------------------------------------
    @property
    def sort_key(self) -> Optional[str]:
        return SORTS[self._sort_idx]

    def refresh_projects(self) -> None:
        view = self.query_one("#projects", ListView)
        view.clear()
        self._projects = sorted(self.manager.projects)
        total = sum(len(v) for v in self.manager.projects.values())
        view.append(ListItem(Label(f"All projects ({total})")))
        for name in self._projects:
            items = self.manager.projects[name]
            open_n = sum(1 for i in items if i.status != "done")
            done_n = sum(1 for i in items if i.status == "done")
            view.append(ListItem(
                Label(f"{name} ({open_n} open, {done_n} done)")))
        if self.show_all:
            view.index = 0
        elif self.project in self._projects:
            view.index = 1 + self._projects.index(self.project)
        self.refresh_filter_options()

    def refresh_filter_options(self) -> None:
        """Rebuild sprint/epic options for the current scope."""
        scope = (self.manager.projects.values()
                 if self.show_all or not self.project
                 else [self.manager.projects.get(self.project, [])])
        sprints, epics = set(), set()
        for items in scope:
            for i in items:
                if i.sprint:
                    sprints.add(i.sprint)
                if i.epic:
                    epics.add(i.epic)
        for wid, values, current in (
                ("#f-sprint", sorted(sprints), self._f_sprint),
                ("#f-epic", sorted(epics), self._f_epic)):
            try:
                sel = self.query_one(wid, Select)
            except Exception:
                continue
            label = wid[2:].replace("f-", "")
            sel.set_options([(f"{label}: all", "all")] +
                            [(v, v) for v in values])
            if current not in values:
                sel.value = "all"

    def scope_projects(self):
        """Project names in scope: all, or just the current one."""
        if self.show_all:
            return sorted(self.manager.projects)
        if self.project in self.manager.projects:
            return [self.project]
        return []

    def filtered(self):
        """Scoped items with search + status/priority/sprint/epic filters."""
        if self._f_status in (None, "all"):
            status = None
        elif self._f_status == "open":
            status = "todo,in_progress,blocked"
        else:
            status = self._f_status
        out = []
        for name in self.scope_projects():
            out.extend(
                (name, i) for i in self.manager.filter_items(
                    self.manager.projects[name], status=status,
                    priority=self._f_priority, sprint=self._f_sprint,
                    epic=self._f_epic, search=self._filter or None))
        return out

    def current_refs(self):
        """Sorted [(project, item)] refs for the current view."""
        refs = self.filtered()
        pos = {}
        for n, it in enumerate(self.manager.sort_items(
                [i for _, i in refs], sort=self.sort_key)):
            pos.setdefault(id(it), n)
        return sorted(refs, key=lambda r: (pos.get(id(r[1]), 0), r[0], r[1]))

    def refresh_table(self) -> None:
        table = self.query_one("#items", DataTable)
        # Project column only pays off in the aggregate view.
        if self.show_all != self._table_has_project_col:
            table.clear(columns=True)
            cols = list(TABLE_COLUMNS)
            if self.show_all:
                cols.insert(1, ("Project", "project"))
            for label, key in cols:
                table.add_column(label, key=key)
            self._table_has_project_col = self.show_all
        else:
            table.clear()
        self._table_refs = self.current_refs()
        for proj, item in self._table_refs:
            row = [_cell(item.id, "bold cyan")]
            if self.show_all:
                row.append(_cell(proj))
            row += [
                _cell(item.title),
                _cell(f"{PRI_ICON.get(item.priority, '?')} {item.priority}",
                      PRI_STYLE.get(item.priority, "")),
                _cell(f"{ST_ICON.get(item.status, '?')} {item.status.replace('_', ' ')}",
                      ST_STYLE.get(item.status, "")),
                _cell(item.sprint or "-"),
                _cell(item.epic or "-"),
                _cell(item.assignee or "-"),
                _cell(str(item.story_points) if item.story_points else "-"),
            ]
            table.add_row(*row, key=f"{proj}\0{item.id}")
        self.refresh_statusline()

    def refresh_board(self) -> None:
        refs = self.current_refs()
        items = {(p, i.id): i for p, i in refs}
        self._board = {st: [] for st in BOARD_ORDER}
        for proj, item in refs:
            self._board[item.status].append((proj, item.id))
        for st in BOARD_ORDER:
            view = self.query_one(f"#col-{st}", ListView)
            view.clear()
            for proj, item_id in self._board[st]:
                item = items[(proj, item_id)]
                pts = f"{item.story_points}pt" if item.story_points else "-pt"
                prefix = f"{proj}: " if self.show_all else ""
                view.append(ListItem(Label(
                    f"{prefix}{item.id} {PRI_ICON.get(item.priority, '?')}"
                    f"{item.priority} {pts} {item.title[:32]}")))
            # Pre-highlight the first card so space/enter work immediately.
            view.index = 0 if self._board[st] else None
            pts = sum(items[r].story_points or 0 for r in self._board[st])
            self.query_one(f"#head-{st}", Label).update(
                f"{BOARD_LABEL[st]} ({len(self._board[st])} - {pts}pt)")
        self.refresh_statusline()

    def refresh_stats(self) -> None:
        names = self.scope_projects()
        lines = []
        for name in names:
            items = self.manager.projects[name]
            total = len(items)
            pts_total = sum(i.story_points or 0 for i in items)
            pts_done = sum((i.story_points or 0) for i in items
                           if i.status == "done")
            open_n = sum(1 for i in items if i.status != "done")
            lines += [f"{name}: {total} items, "
                      f"{open_n} open, {pts_done}/{pts_total} pts done", ""]
            lines.append("By status:")
            for st in BOARD_ORDER:
                c = sum(1 for i in items if i.status == st)
                p = sum((i.story_points or 0) for i in items if i.status == st)
                pct = c * 100 // total if total else 0
                lines.append(f"  {ST_ICON[st]} {st:12} {c:3} "
                             f"{_ascii_bar(c, total)} {pct:3}% ({p} pts)")
            lines.append("")
            lines.append("By priority:")
            for pr in ("critical", "high", "medium", "low"):
                c = sum(1 for i in items if i.priority == pr)
                pct = c * 100 // total if total else 0
                lines.append(f"  {PRI_ICON[pr]} {pr:12} {c:3} "
                             f"{_ascii_bar(c, total)} {pct:3}%")
            lines.append("")
        if not lines:
            lines = ["no projects -- press N for new project"]
        self._stats_text = "\n".join(lines).rstrip()
        self.query_one("#stats-body", Static).update(self._stats_text)
        self.refresh_statusline()

    def refresh_statusline(self) -> None:
        names = self.scope_projects()
        items = [i for n in names for i in self.manager.projects[n]]
        open_n = sum(1 for i in items if i.status != "done")
        shown = len(self.current_refs())
        sort = self.sort_key or "default"
        bits = []
        if self._filter:
            bits.append(f"filter='{self._filter}'")
        if self._f_status and self._f_status != "open":
            bits.append(f"status={self._f_status}")
        if self._f_priority:
            bits.append(f"priority={self._f_priority}")
        if self._f_sprint:
            bits.append(f"sprint={self._f_sprint}")
        if self._f_epic:
            bits.append(f"epic={self._f_epic}")
        filt = (" " + " ".join(bits)) if bits else ""
        scope = "all projects" if self.show_all else (self.project or "no project")
        db = self.manager.data_dir.name
        line = (f"{scope} [{self._view}]: {shown}/{len(items)} shown, "
                f"{open_n} open, sort={sort}{filt} "
                f"- {len(self.manager.projects)} projects - db={db}")
        if names and shown == 0:
            line += " -- no matches (esc: back, esc again: clear)"
        if not self.manager.projects:
            line = "no projects -- press N for new project"
        try:
            self.query_one("#statusline", Static).update(line)
        except Exception:
            pass
        try:
            self.sub_title = line
        except Exception:
            pass

    def _update_tabbar(self) -> None:
        parts = []
        for i, name in enumerate(["Table", "Board", "Stats"]):
            key = name.lower()
            parts.append(f"{i + 1}:[{name}]" if self._view == key
                         else f"{i + 1}: {name} ")
        try:
            self.query_one("#tabbar", Static).update("  ".join(parts))
        except Exception:
            pass

    def refresh_current_view(self) -> None:
        if self._view == "board":
            self.refresh_board()
        elif self._view == "stats":
            self.refresh_stats()
        else:
            self.refresh_table()

    def refresh_all(self) -> None:
        self.refresh_projects()
        self.refresh_current_view()

    def selected_ref(self) -> Optional[tuple]:
        """(project, id) of the highlighted card/row, or None."""
        if self._view == "board":
            focused = self.focused
            for st in BOARD_ORDER:
                try:
                    view = self.query_one(f"#col-{st}", ListView)
                except Exception:
                    continue
                if focused is view and view.index is not None:
                    cards = self._board.get(st, [])
                    if 0 <= view.index < len(cards):
                        return cards[view.index]
            return None
        table = self.query_one("#items", DataTable)
        idx = table.cursor_row
        if 0 <= idx < len(self._table_refs):
            proj, item = self._table_refs[idx]
            return (proj, item.id)
        return None

    def selected_id(self) -> Optional[str]:
        ref = self.selected_ref()
        return ref[1] if ref else None

    # -- events ---------------------------------------------------------
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        view_id = event.list_view.id or ""
        if view_id == "projects":
            # Index 0 is the aggregate entry; the rest are projects.
            idx = event.list_view.index
            if idx == 0:
                self.show_all = True
                self.refresh_current_view()
                self.focus_default()
            elif idx is not None and 1 <= idx <= len(self._projects):
                self.show_all = False
                self.project = self._projects[idx - 1]
                self._remember()
                self.refresh_all()
                self.focus_default()
        elif view_id.startswith("col-"):
            st = view_id[4:]
            idx = event.list_view.index
            cards = self._board.get(st, [])
            if idx is not None and 0 <= idx < len(cards):
                proj, item_id = cards[idx]
                self.push_screen(DetailScreen(proj, item_id))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self._filter = event.value or ""
            if self._view in ("table", "board"):
                self.refresh_current_view()
            else:
                self.refresh_statusline()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter in the filter: keep the text, hand focus back to content.
        if event.input.id == "filter":
            self.focus_default()

    @staticmethod
    def _sel_val(value) -> Optional[str]:
        # Select posts Select.NULL (NoSelection) while options rebuild;
        # never let that sentinel leak into filters.
        if value is None or value == "all" or not isinstance(value, str):
            return None
        return value

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "f-status":
            self._f_status = (event.value if event.value in
                              ("open", "all", "todo", "in_progress",
                               "blocked", "done") else "open")
        elif event.select.id == "f-priority":
            self._f_priority = self._sel_val(event.value)
        elif event.select.id == "f-sprint":
            self._f_sprint = self._sel_val(event.value)
        elif event.select.id == "f-epic":
            self._f_epic = self._sel_val(event.value)
        else:
            return
        if self._view in ("table", "board"):
            self.refresh_current_view()
        else:
            self.refresh_statusline()

    def focus_default(self) -> None:
        try:
            if self._view == "board":
                self.query_one("#col-todo", ListView).focus()
            elif self._view == "stats":
                self.query_one("#view-stats", VerticalScroll).focus()
            else:
                self.query_one("#items", DataTable).focus()
        except Exception:
            pass

    def _goto(self, view: str) -> None:
        self._view = view
        for vid, vname in (("#view-table", "table"),
                           ("#board-cols", "board"),
                           ("#view-stats", "stats")):
            try:
                self.query_one(vid).styles.display = (
                    "block" if vname == view else "none")
            except Exception:
                pass
        self._update_tabbar()
        self.refresh_current_view()
        self.focus_default()

    # -- actions --------------------------------------------------------
    def action_focus_filter(self) -> None:
        if self._modal_open():
            return
        self.query_one("#filter", Input).focus()

    def action_back_to_table(self) -> None:
        """Esc: leave the filter (keep text); pressed in content with an
        active filter, it clears the filter instead."""
        if self._modal_open():
            return
        filt = self.query_one("#filter", Input)
        if self.focused is filt:
            self.focus_default()
        elif self._filter:
            filt.value = ""  # fires Input.Changed -> refresh
            self.focus_default()
        else:
            self.focus_default()

    def action_cycle_sort(self) -> None:
        if self._modal_open() or self._typing():
            return
        self._sort_idx = (self._sort_idx + 1) % len(SORTS)
        self.refresh_current_view()

    def _table_or_col_focused(self) -> bool:
        if isinstance(self.focused, DataTable):
            return True
        return isinstance(self.focused, ListView)

    def action_cursor_down(self) -> None:
        # Scoped so typing j/k in the filter (or elsewhere) never moves
        # content from under you.
        if self._modal_open() or not self._table_or_col_focused():
            return
        try:
            self.focused.action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        if self._modal_open() or not self._table_or_col_focused():
            return
        try:
            self.focused.action_cursor_up()
        except Exception:
            pass

    def action_goto_table(self) -> None:
        if not self._modal_open():
            self._goto("table")

    def action_goto_board(self) -> None:
        if not self._modal_open():
            self._goto("board")

    def action_goto_stats(self) -> None:
        if not self._modal_open():
            self._goto("stats")

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_smart_quit(self) -> None:
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
        else:
            self.exit()

    def _need_project(self) -> bool:
        if not self.project or self.project not in self.manager.projects:
            self.notify("No project selected - press N for new project",
                        severity="warning")
            return False
        return True

    # -- item ops -------------------------------------------------------
    def action_new_item(self) -> None:
        if self._modal_open() or self._typing():
            return
        if not self._need_project():
            return
        self.push_screen(ItemFormScreen(self.project),
                         callback=lambda _ok: self.refresh_all())

    def edit_item_by_ref(self, ref: Optional[tuple]) -> None:
        if not ref:
            return
        proj, item_id = ref
        if proj not in self.manager.projects:
            return
        self.push_screen(ItemFormScreen(proj, item_id),
                         callback=lambda _ok: self.refresh_all())

    # Kept for palette/tests compat; prefer edit_item_by_ref.
    def edit_item_by_id(self, item_id: Optional[str]) -> None:
        if item_id and self.project in self.manager.projects:
            self.edit_item_by_ref((self.project, item_id))

    def action_edit_item(self) -> None:
        if self._modal_open() or self._typing():
            return
        ref = self.selected_ref()
        if not ref:
            self.notify("Nothing selected", severity="warning")
            return
        self.edit_item_by_ref(ref)

    def delete_item_by_ref(self, ref: Optional[tuple]) -> None:
        if not ref:
            return
        proj, item_id = ref
        if proj not in self.manager.projects:
            return
        def after(ok):
            if ok and self.manager.remove_item(proj, item_id):
                self.notify(f"Deleted {item_id}")
            self.refresh_all()
        self.push_screen(
            ConfirmScreen(f"Delete item '{item_id}'?", ok_label="Delete"),
            callback=after)

    def delete_item_by_id(self, item_id: Optional[str]) -> None:
        if item_id and self.project in self.manager.projects:
            self.delete_item_by_ref((self.project, item_id))

    def action_delete_item(self) -> None:
        if self._modal_open() or self._typing():
            return
        ref = self.selected_ref()
        if not ref:
            self.notify("Nothing selected", severity="warning")
            return
        self.delete_item_by_ref(ref)

    def action_show_detail(self) -> None:
        if (self._modal_open() or self._typing()
                or isinstance(self.focused, Button)):
            return
        ref = self.selected_ref()
        if ref:
            self.push_screen(DetailScreen(*ref))

    def action_advance_item(self) -> None:
        if (self._modal_open() or self._typing()
                or isinstance(self.focused, Button)):
            return
        ref = self.selected_ref()
        if not ref:
            return
        proj, item_id = ref
        item = next((i for i in self.manager.projects.get(proj, [])
                     if i.id == item_id), None)
        if not item:
            return
        nxt = NEXT_STATUS.get(item.status)
        if not nxt:
            self.notify(f"{item_id} is already done")
            return
        self.manager.update_item(proj, item_id, status=nxt)
        self.notify(f"{item_id} -> {nxt}")
        self.refresh_all()

    # -- project ops ----------------------------------------------------
    def action_new_project(self) -> None:
        if self._modal_open() or self._typing():
            return
        def after(name):
            if name:
                self.project = name
                self.show_all = False
                self._remember()
                self.notify(f"Project '{name}' created")
            self.refresh_all()
        self.push_screen(ProjectScreen(), callback=after)

    def action_delete_project(self) -> None:
        if self._modal_open() or self._typing():
            return
        if not self._need_project():
            return
        name = self.project
        items = self.manager.projects.get(name, [])
        def after(ok):
            if ok and self.manager.remove_project(name):
                names = sorted(self.manager.projects)
                self.project = names[0] if names else None
                self.show_all = False
                self._remember()
                self.notify(f"Project '{name}' deleted")
            self.refresh_all()
        self.push_screen(
            ConfirmScreen(f"Delete project '{name}' "
                          f"({len(items)} items)? This removes its file.",
                          ok_label="Delete"),
            callback=after)

    # -- data exchange --------------------------------------------------
    def action_export_dialog(self) -> None:
        if self._modal_open() or self._typing():
            return
        self.push_screen(ExportScreen(), callback=lambda _r: None)

    def action_import_dialog(self) -> None:
        if self._modal_open() or self._typing():
            return
        def after(ok):
            if ok:
                self.refresh_all()
        self.push_screen(ImportScreen(), callback=after)

    def action_open_palette(self) -> None:
        try:
            self.action_command_palette()
        except AttributeError:
            from textual.command import CommandPalette
            self.push_screen(CommandPalette())


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="backlogd TUI (Phase 3)")
    parser.add_argument("--data-dir", default="database_backlogd")
    parser.add_argument("--project", default=None)
    args = parser.parse_args()
    BacklogApp(data_dir=args.data_dir, project=args.project).run()


if __name__ == "__main__":
    main()
