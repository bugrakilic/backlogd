"""Pilot tests for the Phase 3 Textual TUI (headless, no user input)."""
import pytest

from textual.widgets import DataTable, Input, Label, ListView, Select, Static

from backlogd import BacklogManager
from tui import BacklogApp

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def data_dir(tmp_path):
    m = BacklogManager(data_dir=str(tmp_path / "db"))
    m.create_project("demo")
    m.add_item("demo", "Login page", "Auth UI", priority="high",
               sprint="Sprint 1", assignee="jane", story_points=5)
    m.add_item("demo", "Fix crash", "Null pointer", priority="critical",
               assignee="bob", story_points=3)
    return str(tmp_path / "db")


async def test_boots_with_table_rows(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        table = app.query_one("#items", DataTable)
        assert table.row_count == 2
        assert "demo" in (app.sub_title or "")


async def test_filter_narrows_table(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.click("#filter")
        await pilot.press(*"crash")
        await pilot.pause()
        assert app.query_one("#items", DataTable).row_count == 1
        await pilot.press("escape")
        await pilot.pause()
        filt = app.query_one("#filter", Input)
        filt.value = ""
        await pilot.pause()
        assert app.query_one("#items", DataTable).row_count == 2


async def test_sort_key_cycles(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        assert app.sort_key is None
        await pilot.press("s")
        await pilot.pause()
        assert app.sort_key == "priority"
        assert "sort=priority" in (app.sub_title or "")


async def test_sidebar_lists_projects(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        view = app.query_one("#projects", ListView)
        # "All projects" entry + one project.
        assert len(view.children) == 2


async def test_escape_leaves_filter_keeps_text(data_dir):
    from textual.widgets import DataTable
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("/")
        assert isinstance(app.focused, Input)
        await pilot.press(*"zzz-no-match")
        await pilot.pause()
        assert app.query_one("#items", DataTable).row_count == 0
        await pilot.press("escape")  # back to table, filter kept
        await pilot.pause()
        assert isinstance(app.focused, DataTable)
        assert app.query_one("#filter", Input).value == "zzz-no-match"
        await pilot.press("escape")  # already home -> clears filter
        await pilot.pause()
        assert app.query_one("#filter", Input).value == ""
        assert app.query_one("#items", DataTable).row_count == 2


async def test_enter_leaves_filter(data_dir):
    from textual.widgets import DataTable
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("/")
        await pilot.press(*"login")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.focused, DataTable)
        assert app.query_one("#items", DataTable).row_count == 1


async def test_typing_jk_in_filter_does_not_move_table(data_dir):
    from textual.widgets import DataTable
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("/")
        before = app.query_one("#items", DataTable).cursor_coordinate
        await pilot.press("j", "k")
        await pilot.pause()
        assert isinstance(app.focused, Input)
        assert app.query_one("#filter", Input).value == "jk"
        assert app.query_one("#items", DataTable).cursor_coordinate == before


async def test_board_tab_groups_cards(data_dir):
    from tui import BOARD_ORDER
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.pause()
        assert app._view == "board"
        assert len(app.query_one("#col-todo", ListView).children) == 2
        assert len(app.query_one("#col-in_progress", ListView).children) == 0
        await pilot.press("1")
        await pilot.pause()
        assert app._view == "table"


async def test_space_advances_board_card(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#col-todo", ListView).focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert len(app.query_one("#col-todo", ListView).children) == 1
        assert len(app.query_one("#col-in_progress", ListView).children) == 1


async def test_stats_tab_renders(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("3")
        await pilot.pause()
        assert "2 items" in app._stats_text
        assert "By status:" in app._stats_text


async def test_new_item_modal_creates_row(data_dir):
    from tui import ItemFormScreen
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, ItemFormScreen)
        app.screen.query_one("#m-title", Input).value = "TUI task"
        await pilot.pause()
        app.screen._save()
        await pilot.pause()
        assert not isinstance(app.screen, ItemFormScreen)
        assert app.query_one("#items", DataTable).row_count == 3


async def test_new_item_requires_title(data_dir):
    from tui import ItemFormScreen
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        app.screen._save()  # empty title -> stays open with error
        await pilot.pause()
        assert isinstance(app.screen, ItemFormScreen)
        assert "required" in str(app.screen.query_one("#m-error", Static).render())
        assert app.query_one("#items", DataTable).row_count == 2


async def test_delete_item_with_confirm(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("d")
        await pilot.pause()
        await pilot.click("#btn-ok")
        await pilot.pause()
        assert app.query_one("#items", DataTable).row_count == 1


async def test_enter_opens_detail(data_dir):
    from tui import DetailScreen
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DetailScreen)


async def test_new_project_sidebar_updates(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("N")
        await pilot.pause()
        app.screen.query_one("#m-name", Input).value = "second"
        await pilot.pause()
        await pilot.click("#btn-save")
        await pilot.pause()
        assert len(app.query_one("#projects", ListView).children) == 3
        assert app.project == "second"


async def test_export_dialog_writes_file(data_dir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("X")
        await pilot.pause()
        app.screen.query_one("#m-file", Input).value = "out.csv"
        await pilot.pause()
        await pilot.click("#btn-save")
        await pilot.pause()
        assert (tmp_path / "out.csv").exists()


async def test_palette_opens_and_closes(data_dir):
    from textual.command import CommandPalette
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CommandPalette)


def _two_project_dir(tmp_path):
    m = BacklogManager(data_dir=str(tmp_path / "db2"))
    m.create_project("alpha")
    m.add_item("alpha", "A1", "x", sprint="S1")
    m.update_item("alpha", "ALPHA-1", status="done")
    m.create_project("beta")
    m.add_item("beta", "B1", "y", sprint="S2")
    return str(tmp_path / "db2")


async def test_done_hidden_by_default_until_all(tmp_path):
    d = _two_project_dir(tmp_path)
    app = BacklogApp(data_dir=d, project="alpha")
    async with app.run_test() as pilot:
        # ALPHA-1 is done -> hidden by the default "open" filter.
        assert app.query_one("#items", DataTable).row_count == 0
        app.query_one("#f-status", Select).value = "all"
        await pilot.pause()
        assert app.query_one("#items", DataTable).row_count == 1


async def test_sprint_filter_narrows_table(data_dir):
    from textual.widgets import Select
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        app.query_one("#f-sprint", Select).value = "Sprint 1"
        await pilot.pause()
        assert app.query_one("#items", DataTable).row_count == 1
        assert "sprint=Sprint 1" in (app.sub_title or "")


async def test_all_projects_aggregate_view(tmp_path):
    d = _two_project_dir(tmp_path)
    app = BacklogApp(data_dir=d, project="alpha")
    async with app.run_test() as pilot:
        view = app.query_one("#projects", ListView)
        view.focus()
        await pilot.pause()
        await pilot.press("up")  # highlight the "All projects" entry
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.show_all is True
        # beta B1 (todo) + nothing else open: alpha's item is done.
        assert app.query_one("#items", DataTable).row_count == 1
        assert "all projects" in (app.sub_title or "")


async def test_resume_last_project(tmp_path, monkeypatch):
    import tui
    d = _two_project_dir(tmp_path)
    monkeypatch.setattr(tui, "load_config", lambda: {"last_project": "beta"})
    app = BacklogApp(data_dir=d)
    async with app.run_test() as pilot:
        assert app.project == "beta"


async def test_detail_shows_created(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        meta = str(app.screen.query_one("#detail-meta", Static).render())
        assert "Created" in meta


async def test_sidebar_breakdown_and_statusline(data_dir):
    app = BacklogApp(data_dir=data_dir)
    async with app.run_test() as pilot:
        labels = [str(c.query_one(Label).render())
                  for c in app.query_one("#projects", ListView).children]
        assert any("open" in lab for lab in labels)
        assert "projects" in (app.sub_title or "")
        assert "db=" in (app.sub_title or "")
