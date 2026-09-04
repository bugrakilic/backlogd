"""Smoke tests for backlogd (no network, no user input)."""
import argparse
import csv

import pytest

import backlogd
from backlogd import BacklogManager, InteractiveCLI, coerce_points, points_arg


@pytest.fixture()
def manager(tmp_path):
    m = BacklogManager(data_dir=str(tmp_path / "db"))
    m.create_project("demo")
    m.add_item("demo", "Login page", "Auth UI", priority="high",
               sprint="Sprint 1", assignee="jane", story_points=5)
    m.add_item("demo", "Fix crash", "Null pointer on logout", priority="critical",
               assignee="bob", story_points=3)
    return m


def test_plain_prompt_format(manager):
    cli = InteractiveCLI(manager)
    cli.current_project = None  # ignore ~/.backlogdrc restore for determinism
    assert cli.get_plain_prompt() == "backlogd>> "
    cli.current_project = "demo"
    assert cli.get_plain_prompt() == "backlogd (demo)>> "


def test_points_validation():
    assert coerce_points(None) is None
    assert coerce_points("") is None
    assert coerce_points(5) == 5
    assert coerce_points("8") == 8
    assert coerce_points("abc") is None
    assert coerce_points(200) is None
    assert coerce_points(-1) is None
    assert points_arg("10") == 10
    with pytest.raises(argparse.ArgumentTypeError):
        points_arg("200")
    with pytest.raises(argparse.ArgumentTypeError):
        points_arg("x")


def test_filter_assignee_search_sort_regression(manager):
    # 'assignee' used to crash list_items (unexpected kwarg).
    items = manager.projects["demo"]
    assert len(manager.filter_items(items, assignee="jane")) == 1
    assert len(manager.filter_items(items, search="null pointer")) == 1
    assert len(manager.filter_items(items, priority="high,critical")) == 2
    by_points = manager.sort_items(items, sort="points")
    assert [i.story_points for i in by_points] == [5, 3]


def test_add_validates_priority_and_points(manager, capsys):
    manager.add_item("demo", "Bad", "desc", priority="urgent", story_points=999)
    item = manager.projects["demo"][-1]
    assert item.priority == "medium"
    assert item.story_points is None


def test_update_maps_points_kwarg(manager):
    assert manager.update_item("demo", "DEMO-1", points=8) is True
    assert manager.projects["demo"][0].story_points == 8
    # Out-of-range keeps old value.
    assert manager.update_item("demo", "DEMO-1", points=500) is True
    assert manager.projects["demo"][0].story_points == 8


def test_views_render_without_crashing(manager, capsys):
    manager.list_items(project_name="demo", assignee="jane", sort="points")
    manager.board("demo")
    manager.stats("demo")
    manager.search_items("demo", "login")
    manager.show_item_details("demo", "demo-1")  # case-insensitive id
    out = capsys.readouterr().out
    assert "DEMO-1" in out


def test_export_import_roundtrip(manager, tmp_path):
    csv_file = str(tmp_path / "demo.csv")
    assert manager.export_to_csv("demo", csv_file) is True
    with open(csv_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2

    assert manager.export_all_to_csv(str(tmp_path / "all.csv")) is True
    assert manager.import_from_csv("restored", csv_file) is True
    assert len(manager.projects["restored"]) == 2
    # Re-import same file: ids clash -> remapped, count doubles.
    assert manager.import_from_csv("restored", csv_file) is True
    assert len(manager.projects["restored"]) == 4


def test_import_skips_empty_titles(manager, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("id,title,description\nA-1,,nodesc\n", encoding="utf-8")
    assert manager.import_from_csv("demo", str(bad)) is True
    assert len(manager.projects["demo"]) == 2  # unchanged
