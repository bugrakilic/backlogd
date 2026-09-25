#!/usr/bin/env python3
"""
backlogd - CLI-Based Product Backlog Manager
A terminal-based tool to manage product backlogs with local YAML storage.
"""

import os
import sys
import yaml
import csv
import argparse
import shlex
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from art import text2art

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.columns import Columns
    from rich.markdown import Markdown
    from rich.rule import Rule
    from rich.theme import Theme
    from rich import box
    from rich.markup import escape
    import pandas as pd
except ImportError:
    print("Required packages not installed. Please run:")
    print("pip install rich pyyaml pandas openpyxl")
    sys.exit(1)

# --- Phase 2: optional enhanced prompting (graceful fallback to rich) ---
try:
    import questionary
    _HAS_QUESTIONARY = True
except ImportError:
    questionary = None
    _HAS_QUESTIONARY = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.completion import WordCompleter
    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    PromptSession = None
    FileHistory = None
    WordCompleter = None
    _HAS_PROMPT_TOOLKIT = False

try:
    import readline  # noqa: F401  (stdlib history for rich fallback on unix)
except ImportError:
    readline = None


def get_config_path() -> Path:
    return Path.home() / ".backlogdrc"


def load_config() -> dict:
    try:
        import json
        cfg = get_config_path()
        if cfg.exists():
            return json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_config(data: dict) -> None:
    try:
        import json
        cfg = get_config_path()
        cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# --- Phase 1 TUI theme (rich-only, 256-color safe, NO_COLOR aware) ---
BACKLOGD_THEME = Theme({
    "brand": "bold cyan",
    "muted": "dim white",
    "accent": "bold magenta",
    "success": "bold green",
    "warning": "bold yellow",
    "danger": "bold red",
    "pri.critical": "bold red",
    "pri.high": "red",
    "pri.medium": "yellow",
    "pri.low": "green",
    "st.todo": "blue",
    "st.in_progress": "yellow",
    "st.done": "green",
    "st.blocked": "red",
    "id": "bold cyan",
    "header": "bold white",
})

PRIORITY_STYLE = {
    "critical": "pri.critical",
    "high": "pri.high",
    "medium": "pri.medium",
    "low": "pri.low",
}

STATUS_STYLE = {
    "todo": "st.todo",
    "in_progress": "st.in_progress",
    "done": "st.done",
    "blocked": "st.blocked",
}

PRIORITY_ICON = {
    "critical": "!!",
    "high": "^",
    "medium": "o",
    "low": "-",
}

STATUS_ICON = {
    "todo": "( )",
    "in_progress": "(~)",
    "done": "(x)",
    "blocked": "(!)",
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
STATUS_ORDER = {"todo": 0, "in_progress": 1, "blocked": 2, "done": 3}

POINTS_MIN, POINTS_MAX = 0, 100


def coerce_points(value) -> Optional[int]:
    """Return int in range or None. Never raises (CLI + interactive safe)."""
    if value is None or value == "":
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if POINTS_MIN <= v <= POINTS_MAX else None


def points_arg(value: str) -> int:
    """argparse type for --points: int in 0-100 or ArgumentTypeError."""
    try:
        v = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid points value: {value!r} (0-100)")
    if not POINTS_MIN <= v <= POINTS_MAX:
        raise argparse.ArgumentTypeError(f"points must be {POINTS_MIN}-{POINTS_MAX}")
    return v


def get_console() -> Console:
    """Themed console. Respects NO_COLOR and caps width for readability."""
    no_color = os.environ.get("NO_COLOR") is not None
    return Console(theme=BACKLOGD_THEME, no_color=no_color, width=min(100, Console().width))


def styled_priority(priority: str) -> str:
    style = PRIORITY_STYLE.get(priority, "")
    icon = PRIORITY_ICON.get(priority, "•")
    return f"[{style}]{icon} {escape(priority)}[/]" if style else escape(priority)


def styled_status(status: str) -> str:
    style = STATUS_STYLE.get(status, "")
    icon = STATUS_ICON.get(status, "•")
    label = status.replace("_", " ")
    return f"[{style}]{icon} {escape(label)}[/]" if style else escape(label)


def _bar(count: int, total: int, width: int = 16, fill: str = "#") -> str:
    """Small inline bar for stats tables. No extra deps. ASCII-safe for Windows."""
    if total <= 0:
        return "[muted]" + "-" * width + "[/]"
    filled = round(count / total * width)
    return f"[accent]{fill * filled}[/][muted]{'-' * (width - filled)}[/]"


def _truncate(text: str, limit: int = 42) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass
class BacklogItem:
    id: str
    title: str
    description: str
    priority: str
    status: str
    sprint: Optional[str] = None
    epic: Optional[str] = None
    assignee: Optional[str] = None
    story_points: Optional[int] = None
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


class BacklogManager:
    def __init__(self, data_dir: str = "database_backlogd"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.console = get_console()
        self.projects: Dict[str, List[BacklogItem]] = {}
        self.load_projects()
    
    def get_project_file(self, project_name: str) -> Path:
        """Get the YAML file path for a project."""
        return self.data_dir / f"{project_name}.yaml"
    
    def load_projects(self):
        """Load all projects from YAML files."""
        for yaml_file in self.data_dir.glob("*.yaml"):
            project_name = yaml_file.stem
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f) or []
                self.projects[project_name] = [
                    BacklogItem(**item) for item in data
                ]
            except Exception as e:
                self.console.print(f"[red]Error loading {project_name}: {e}[/red]")
    
    def save_project(self, project_name: str):
        """Save a project to its YAML file."""
        if project_name not in self.projects:
            return
        
        project_file = self.get_project_file(project_name)
        data = [asdict(item) for item in self.projects[project_name]]
        
        try:
            with open(project_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            self.console.print(f"[red]Error saving {project_name}: {e}[/red]")
    
    def list_projects(self):
        """Display all available projects."""
        if not self.projects:
            self.console.print(Panel(
                "[warning]No projects yet.[/]\n\n"
                "[muted]Get started:[/]\n"
                "  • [brand]create-project demo[/]\n"
                "  • [brand]use demo[/] then [brand]add \"First task\" \"Describe it\"[/]",
                title="Projects", border_style="yellow",
            ))
            return

        table = Table(title="Available Projects", box=box.ROUNDED,
                      show_header=True, header_style="header", expand=True)
        table.add_column("Project", style="id", no_wrap=True)
        table.add_column("Items", justify="right", style="accent")
        table.add_column("Open", justify="right", style="warning")
        table.add_column("Done", justify="right", style="success")
        table.add_column("Points", justify="right", style="muted")
        table.add_column("Breakdown", style="muted")

        for project_name, items in sorted(self.projects.items()):
            open_n = sum(1 for i in items if i.status in ("todo", "in_progress", "blocked"))
            done_n = sum(1 for i in items if i.status == "done")
            pts = sum(i.story_points or 0 for i in items)
            counts = {}
            for item in items:
                counts[item.status] = counts.get(item.status, 0) + 1
            bits = []
            for st in ("todo", "in_progress", "blocked", "done"):
                if st in counts:
                    bits.append(styled_status(st) + f" ×{counts[st]}")
            table.add_row(
                escape(project_name), str(len(items)),
                str(open_n), str(done_n), str(pts),
                "  ".join(bits) if bits else "[muted]Empty[/]",
            )

        self.console.print(table)
        self.console.print("[muted]Tip: use <project> • board • stats • search <text>[/]")
    
    def create_project(self, project_name: str):
        """Create a new project."""
        if project_name in self.projects:
            self.console.print(f"[red]Project '{project_name}' already exists.[/red]")
            return False
        
        self.projects[project_name] = []
        self.save_project(project_name)
        self.console.print(f"[green]Project '{project_name}' created successfully.[/green]")
        return True
    
    def delete_project(self, project_name: str):
        """Delete a project and its file."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False
        
        if Confirm.ask(f"Are you sure you want to delete project '{project_name}'?"):
            return self.remove_project(project_name)
        return False

    def remove_project(self, project_name: str) -> bool:
        """Delete a project without prompting (for the TUI)."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False
        try:
            self.get_project_file(project_name).unlink(missing_ok=True)
        except Exception as e:
            self.console.print(f"[red]Could not delete file: {e}[/red]")
            return False
        del self.projects[project_name]
        self.console.print(f"[green]Project '{project_name}' deleted successfully.[/green]")
        return True
    
    def generate_item_id(self, project_name: str) -> str:
        """Generate a unique ID for a backlog item."""
        if project_name not in self.projects:
            return f"{project_name.upper()}-1"
        
        existing_ids = [item.id for item in self.projects[project_name]]
        counter = len(existing_ids) + 1
        
        while f"{project_name.upper()}-{counter}" in existing_ids:
            counter += 1
        
        return f"{project_name.upper()}-{counter}"
    
    def add_item(self, project_name: str, title: str, description: str,
                 priority: str = "medium", sprint: str = None, epic: str = None,
                 assignee: str = None, story_points: int = None):
        """Add a new backlog item to a project."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False

        if priority not in ("low", "medium", "high", "critical"):
            self.console.print(f"[warning]Unknown priority '{priority}'. Using 'medium'.[/]")
            priority = "medium"
        points = coerce_points(story_points)
        if story_points not in (None, "") and points is None:
            self.console.print(f"[warning]Points must be {POINTS_MIN}-{POINTS_MAX}. Saved without points.[/]")

        item_id = self.generate_item_id(project_name)
        item = BacklogItem(
            id=item_id,
            title=title,
            description=description,
            priority=priority,
            status=Status.TODO.value,
            sprint=sprint,
            epic=epic,
            assignee=assignee,
            story_points=points
        )
        
        self.projects[project_name].append(item)
        self.save_project(project_name)
        
        self.console.print(f"[green]Item '{item_id}' added to project '{project_name}'.[/green]")
        return True
    
    def update_item(self, project_name: str, item_id: str, **kwargs):
        """Update an existing backlog item."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False

        # CLI uses --points, model field is story_points.
        if "points" in kwargs and "story_points" not in kwargs:
            kwargs["story_points"] = kwargs.pop("points")
        elif "points" in kwargs:
            kwargs.pop("points")
        if "story_points" in kwargs:
            raw = kwargs["story_points"]
            points = coerce_points(raw)
            if raw is not None and points is None:
                self.console.print(f"[warning]Points must be {POINTS_MIN}-{POINTS_MAX}. Kept old value.[/]")
                kwargs.pop("story_points")
            else:
                kwargs["story_points"] = points
        if "priority" in kwargs and kwargs["priority"] not in (
                "low", "medium", "high", "critical"):
            self.console.print(f"[warning]Unknown priority '{kwargs['priority']}'. Skipped.[/]")
            kwargs.pop("priority")
        if "status" in kwargs and kwargs["status"] not in (
                "todo", "in_progress", "done", "blocked"):
            self.console.print(f"[warning]Unknown status '{kwargs['status']}'. Skipped.[/]")
            kwargs.pop("status")

        for item in self.projects[project_name]:
            if item.id == item_id:
                for key, value in kwargs.items():
                    if hasattr(item, key) and value is not None:
                        setattr(item, key, value)
                item.updated_at = datetime.now().isoformat()
                self.save_project(project_name)
                self.console.print(f"[green]Item '{item_id}' updated successfully.[/green]")
                return True
        
        self.console.print(f"[red]Item '{item_id}' not found in project '{project_name}'.[/red]")
        return False
    
    def delete_item(self, project_name: str, item_id: str):
        """Delete a backlog item."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False
        
        for i, item in enumerate(self.projects[project_name]):
            if item.id == item_id:
                if Confirm.ask(f"Delete item '{item_id}: {item.title}'?"):
                    return self.remove_item(project_name, item_id)
                return False

        self.console.print(f"[red]Item '{item_id}' not found.[/red]")
        return False

    def remove_item(self, project_name: str, item_id: str) -> bool:
        """Delete an item without prompting (for the TUI)."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False
        for i, item in enumerate(self.projects[project_name]):
            if item.id == item_id:
                del self.projects[project_name][i]
                self.save_project(project_name)
                self.console.print(f"[green]Item '{item_id}' deleted successfully.[/green]")
                return True
        self.console.print(f"[red]Item '{item_id}' not found.[/red]")
        return False
    
    def filter_items(self, items: List[BacklogItem], priority: str = None,
                     sprint: str = None, epic: str = None, status: str = None,
                     assignee: str = None, search: str = None) -> List[BacklogItem]:
        """Shared filtering + search used by list/board/stats/search."""
        result = list(items)
        if priority:
            wants = {p.strip().lower() for p in priority.split(",")}
            result = [i for i in result if i.priority.lower() in wants]
        if status:
            wants = {s.strip().lower() for s in status.split(",")}
            result = [i for i in result if i.status.lower() in wants]
        if sprint:
            result = [i for i in result if (i.sprint or "").lower() == sprint.lower()]
        if epic:
            result = [i for i in result if (i.epic or "").lower() == epic.lower()]
        if assignee:
            result = [i for i in result if (i.assignee or "").lower() == assignee.lower()]
        if search:
            q = search.lower()
            result = [i for i in result if q in i.title.lower()
                      or q in (i.description or "").lower()
                      or q in i.id.lower()]
        return result

    def sort_items(self, items: List[BacklogItem], sort: str = None) -> List[BacklogItem]:
        """Sort helper: priority | status | points | updated | title."""
        if not sort:
            return sorted(items, key=lambda i: (
                PRIORITY_ORDER.get(i.priority, 9),
                STATUS_ORDER.get(i.status, 9),
                i.id,
            ))
        s = sort.lower()
        if s == "priority":
            return sorted(items, key=lambda i: (PRIORITY_ORDER.get(i.priority, 9), i.id))
        if s == "status":
            return sorted(items, key=lambda i: (STATUS_ORDER.get(i.status, 9), i.id))
        if s in ("points", "story_points"):
            return sorted(items, key=lambda i: (-(i.story_points or 0), i.id))
        if s == "updated":
            return sorted(items, key=lambda i: i.updated_at or "", reverse=True)
        if s == "title":
            return sorted(items, key=lambda i: i.title.lower())
        return list(items)

    def distinct_values(self, project_name: str, field: str) -> List[str]:
        """Existing values for autocomplete (sprint/epic/assignee)."""
        if project_name not in self.projects:
            return []
        seen = []
        for item in self.projects[project_name]:
            v = getattr(item, field, None)
            if v and v not in seen:
                seen.append(v)
        return sorted(seen)

    def list_items(self, project_name: str = None, priority: str = None,
                   sprint: str = None, epic: str = None, status: str = None,
                   assignee: str = None, search: str = None, sort: str = None):
        """List backlog items with optional filtering."""
        if project_name and project_name not in self.projects:
            self.console.print(f"[danger]Project '{escape(project_name)}' not found.[/]")
            return

        projects_to_show = {project_name: self.projects[project_name]} if project_name else self.projects
        if not projects_to_show:
            self.console.print(Panel(
                "[warning]No projects yet.[/]\n[muted]Try:[/] [brand]create-project demo[/]",
                title="Items", border_style="yellow"))
            return

        any_shown = False
        for proj_name, items in sorted(projects_to_show.items()):
            if not items:
                continue

            filtered = self.filter_items(items, priority=priority, sprint=sprint,
                                         epic=epic, status=status,
                                         assignee=assignee, search=search)
            if not filtered:
                continue
            filtered = self.sort_items(filtered, sort=sort)
            any_shown = True

            # Active-filter subtitle
            active = []
            for k, v in [("priority", priority), ("status", status), ("sprint", sprint),
                         ("epic", epic), ("assignee", assignee), ("search", search)]:
                if v:
                    active.append(f"{k}={v}")
            subtitle = " • ".join(active) if active else f"{len(filtered)} item(s)"

            narrow = (self.console.width or 100) < 100
            table = Table(title=f"Backlog Items - {proj_name}",
                          caption=f"[muted]{escape(subtitle)}[/]",
                          box=box.ROUNDED, show_header=True,
                          header_style="header", expand=False)
            table.add_column("ID", style="id", no_wrap=True)
            table.add_column("Title", style="white", max_width=40, overflow="fold")
            table.add_column("Priority", no_wrap=True)
            table.add_column("Status", no_wrap=True)
            if not narrow:
                table.add_column("Sprint", style="muted", max_width=14, overflow="ellipsis")
                table.add_column("Epic", style="muted", max_width=14, overflow="ellipsis")
            table.add_column("Assignee", style="muted", max_width=14, overflow="ellipsis")
            table.add_column("Pts", justify="right", style="accent")

            for item in filtered:
                row = [
                    escape(item.id),
                    escape(_truncate(item.title, 44)),
                    styled_priority(item.priority),
                    styled_status(item.status),
                ]
                if not narrow:
                    row += [escape(item.sprint or "-"), escape(item.epic or "-")]
                row += [
                    escape(item.assignee or "-"),
                    str(item.story_points) if item.story_points else "-",
                ]
                table.add_row(*row)
            if narrow:
                self.console.print("[muted]Narrow view: sprint/epic hidden. Widen terminal or use 'show ID'.[/]")

            self.console.print(table)

        if not any_shown:
            self.console.print(Panel(
                "[warning]No items match.[/]\n[muted]Try:[/] [brand]items all[/] "
                "or loosen filters • [brand]search <text>[/] • [brand]board[/]",
                title="Items", border_style="yellow"))
        else:
            self.console.print("[muted]Tip: show <id> • board • stats • search <text>[/]")
    
    def show_item_details(self, project_name: str, item_id: str):
        """Rich detail: Markdown description + metadata grid."""
        if project_name not in self.projects:
            self.console.print(f"[danger]Project '{escape(project_name)}' not found.[/]")
            return

        target = None
        for item in self.projects[project_name]:
            if item.id.lower() == item_id.lower():
                target = item
                break
        if not target:
            self.console.print(f"[danger]Item '{escape(item_id)}' not found.[/]")
            return

        meta = Table(box=None, show_header=False, padding=(0, 2))
        meta.add_column("Key", style="brand", no_wrap=True)
        meta.add_column("Value")
        meta.add_row("Priority", styled_priority(target.priority))
        meta.add_row("Status", styled_status(target.status))
        meta.add_row("Sprint", escape(target.sprint or "Not assigned"))
        meta.add_row("Epic", escape(target.epic or "Not assigned"))
        meta.add_row("Assignee", escape(target.assignee or "Unassigned"))
        meta.add_row("Points", str(target.story_points or "Not estimated"))
        meta.add_row("Created", (target.created_at or "Unknown")[:19])
        meta.add_row("Updated", (target.updated_at or "Unknown")[:19])

        self.console.print(Rule(f"[header]{escape(target.id)} - {escape(_truncate(target.title, 60))}[/]", style="brand"))
        self.console.print(Panel(
            Markdown(target.description or "_No description._"),
            title="Description", border_style="cyan"))
        self.console.print(Panel(meta, title="Details", border_style="green"))
        self.console.print("[muted]Tip: update ID • board • stats[/]")

    def board(self, project_name: str, priority: str = None, sprint: str = None,
              epic: str = None, assignee: str = None, search: str = None):
        """Kanban board grouped by status. Rich-only, no new deps."""
        if project_name not in self.projects:
            self.console.print(f"[danger]Project '{escape(project_name)}' not found.[/]")
            return
        items = self.filter_items(self.projects[project_name], priority=priority,
                                  sprint=sprint, epic=epic,
                                  assignee=assignee, search=search)
        if not items:
            self.console.print(Panel(
                "[warning]Board is empty for these filters.[/]\n"
                "[muted]Try:[/] [brand]items all[/] or [brand]add \"Title\" \"Desc\"[/]",
                title=f"Board — {project_name}", border_style="yellow"))
            return

        order = ["todo", "in_progress", "blocked", "done"]
        labels = {"todo": "( ) To Do", "in_progress": "(~) In Progress",
                  "blocked": "(!) Blocked", "done": "(x) Done"}
        borders = {"todo": "blue", "in_progress": "yellow",
                   "blocked": "red", "done": "green"}
        panels = []
        total_pts = sum(i.story_points or 0 for i in items)
        for st in order:
            col = self.sort_items([i for i in items if i.status == st])
            pts = sum(i.story_points or 0 for i in col)
            if not col:
                body = "[muted]— empty —[/]"
            else:
                lines = []
                for it in col[:12]:
                    lines.append(
                        f"[id]{escape(it.id)}[/] {styled_priority(it.priority)} "
                        f"[accent]{it.story_points or '—'}pt[/]\n"
                        f"  {escape(_truncate(it.title, 30))}\n"
                        f"  [muted]{escape(_truncate(it.assignee or 'unassigned', 22))}[/]"
                    )
                if len(col) > 12:
                    lines.append(f"[muted]… +{len(col) - 12} more (use items --status {st})[/]")
                body = "\n".join(lines)
            panels.append(Panel(body, title=f"{labels[st]} ({len(col)} • {pts}pt)",
                                border_style=borders[st], padding=(1, 1)))
        self.console.print(Columns(panels, equal=True, expand=True))
        self.console.print(
            f"[muted]{len(items)} cards • {total_pts} pts • "
            f"move with: update <id> then set status[/]")

    def stats(self, project_name: str = None):
        """Dashboard: totals, status/priority bars, points, top assignees/sprints."""
        if project_name and project_name not in self.projects:
            self.console.print(f"[danger]Project '{escape(project_name)}' not found.[/]")
            return
        scope = {project_name: self.projects[project_name]} if project_name else self.projects
        if not scope:
            self.console.print(Panel("[warning]No projects yet.[/]",
                                     title="Stats", border_style="yellow"))
            return
        for proj_name, items in sorted(scope.items()):
            total = len(items)
            pts_total = sum(i.story_points or 0 for i in items)
            pts_done = sum((i.story_points or 0) for i in items if i.status == "done")
            open_n = sum(1 for i in items if i.status != "done")
            title = f"Stats — {proj_name}  •  {total} items  •  {open_n} open  •  {pts_done}/{pts_total} pts done"
            self.console.print(Rule(title, style="brand"))

            if not items:
                self.console.print("[muted]Empty project. Add items to see breakdown.[/]")
                continue

            # Status table with bars
            st_table = Table(title="By status", box=box.ROUNDED, show_header=True,
                             header_style="header", expand=False)
            st_table.add_column("Status")
            st_table.add_column("Count", justify="right")
            st_table.add_column("Share", justify="left")
            st_table.add_column("Points", justify="right")
            for st in ("todo", "in_progress", "blocked", "done"):
                c = sum(1 for i in items if i.status == st)
                p = sum((i.story_points or 0) for i in items if i.status == st)
                st_table.add_row(styled_status(st), str(c),
                                 _bar(c, total) + f"  [muted]{c * 100 // total if total else 0}%[/]",
                                 str(p))
            # Priority table with bars
            pri_table = Table(title="By priority", box=box.ROUNDED, show_header=True,
                              header_style="header", expand=False)
            pri_table.add_column("Priority")
            pri_table.add_column("Count", justify="right")
            pri_table.add_column("Share", justify="left")
            for pr in ("critical", "high", "medium", "low"):
                c = sum(1 for i in items if i.priority == pr)
                pri_table.add_row(styled_priority(pr), str(c),
                                  _bar(c, total) + f"  [muted]{c * 100 // total if total else 0}%[/]")
            self.console.print(st_table)
            self.console.print(pri_table)

            # Top assignees / sprints / epics
            def top_counts(key, limit=5):
                counts: Dict[str, int] = {}
                for i in items:
                    v = getattr(i, key) or "-"
                    counts[v] = counts.get(v, 0) + 1
                return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]

            meta = Table(title="Top assignees / sprints / epics",
                         box=box.ROUNDED, show_header=True,
                         header_style="header", expand=False)
            meta.add_column("Assignee")
            meta.add_column("N", justify="right")
            meta.add_column("Sprint")
            meta.add_column("N", justify="right")
            meta.add_column("Epic")
            meta.add_column("N", justify="right")
            ta, ts, te = top_counts("assignee"), top_counts("sprint"), top_counts("epic")
            for k in range(max(len(ta), len(ts), len(te))):
                meta.add_row(
                    escape(ta[k][0]) if k < len(ta) else "",
                    str(ta[k][1]) if k < len(ta) else "",
                    escape(ts[k][0]) if k < len(ts) else "",
                    str(ts[k][1]) if k < len(ts) else "",
                    escape(te[k][0]) if k < len(te) else "",
                    str(te[k][1]) if k < len(te) else "",
                )
            self.console.print(meta)
        self.console.print("[muted]Tip: board • items --priority high • search <text>[/]")

    def search_items(self, project_name: str, query: str, status: str = None,
                     priority: str = None, sort: str = None):
        """Full-text search across id/title/description."""
        if project_name not in self.projects:
            self.console.print(f"[danger]Project '{escape(project_name)}' not found.[/]")
            return
        if not query:
            self.console.print("[danger]Usage: search <text>[/]")
            return
        hits = self.filter_items(self.projects[project_name], status=status,
                                 priority=priority, search=query)
        hits = self.sort_items(hits, sort=sort)
        if not hits:
            self.console.print(Panel(
                f"[warning]No matches for '{escape(query)}'.[/]\n"
                "[muted]Search covers ID, title and description (case-insensitive).[/]",
                title=f"Search — {project_name}", border_style="yellow"))
            return
        table = Table(title=f"Search - '{query}' in {project_name} ({len(hits)})",
                      box=box.ROUNDED, show_header=True,
                      header_style="header", expand=False)
        table.add_column("ID", style="id", no_wrap=True)
        table.add_column("Title", max_width=36, overflow="fold")
        table.add_column("Priority", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Assignee", style="muted", max_width=12, overflow="ellipsis")
        for it in hits[:50]:
            table.add_row(escape(it.id), escape(_truncate(it.title)),
                          styled_priority(it.priority),
                          styled_status(it.status),
                          escape(it.assignee or "—"))
        self.console.print(table)
        if len(hits) > 50:
            self.console.print(f"[muted]… +{len(hits) - 50} more. Refine query or use items filters.[/]")

    def export_to_csv(self, project_name: str, filename: str = None):
        """Export project backlog to CSV."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False
        
        if not filename:
            filename = f"{project_name}_backlog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                if not self.projects[project_name]:
                    self.console.print(f"[yellow]No items to export in project '{project_name}'.[/yellow]")
                    return False
                
                fieldnames = list(asdict(self.projects[project_name][0]).keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for item in self.projects[project_name]:
                    writer.writerow(asdict(item))
            
            self.console.print(f"[green]Exported to {filename}[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]Export failed: {e}[/red]")
            return False
    
    def export_to_xlsx(self, project_name: str, filename: str = None):
        """Export project backlog to Excel."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return False
        
        if not self.projects[project_name]:
            self.console.print(f"[yellow]No items to export in project '{project_name}'.[/yellow]")
            return False
        
        if not filename:
            filename = f"{project_name}_backlog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        try:
            data = [asdict(item) for item in self.projects[project_name]]
            df = pd.DataFrame(data)
            df.to_excel(filename, index=False, engine='openpyxl')
            self.console.print(f"[green]Exported to {filename}[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]Export failed: {e}[/red]")
            return False

    def _all_rows(self) -> List[dict]:
        rows = []
        for proj_name in sorted(self.projects):
            for item in self.projects[proj_name]:
                row = asdict(item)
                row = {"project": proj_name, **row}
                rows.append(row)
        return rows

    def export_all_to_csv(self, filename: str = None):
        """Export every project to one combined CSV (with project column)."""
        if not self.projects or not any(self.projects.values()):
            self.console.print("[warning]Nothing to export.[/]")
            return False
        if not filename:
            filename = f"backlogd_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            rows = self._all_rows()
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            self.console.print(f"[success]Exported {len(rows)} items to {escape(filename)}[/]")
            return True
        except Exception as e:
            self.console.print(f"[danger]Export failed: {escape(str(e))}[/]")
            return False

    def export_all_to_xlsx(self, filename: str = None):
        """Export every project to one combined Excel file (with project column)."""
        if not self.projects or not any(self.projects.values()):
            self.console.print("[warning]Nothing to export.[/]")
            return False
        if not filename:
            filename = f"backlogd_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        try:
            pd.DataFrame(self._all_rows()).to_excel(filename, index=False, engine='openpyxl')
            self.console.print(f"[success]Exported to {escape(filename)}[/]")
            return True
        except Exception as e:
            self.console.print(f"[danger]Export failed: {escape(str(e))}[/]")
            return False

    def import_from_csv(self, project_name: str, filename: str):
        """Import items from a CSV file (export format). Creates project if needed."""
        if not filename or not Path(filename).exists():
            self.console.print(f"[danger]File '{escape(filename or '')}' not found.[/]")
            return False
        if project_name not in self.projects:
            self.projects[project_name] = []
            self.console.print(f"[brand]Created project '{escape(project_name)}' for import.[/]")
        valid_pri = ("low", "medium", "high", "critical")
        valid_st = ("todo", "in_progress", "done", "blocked")
        imported, skipped = 0, 0
        try:
            with open(filename, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    title = (row.get("title") or "").strip()
                    if not title:
                        skipped += 1
                        continue
                    pri = (row.get("priority") or "medium").strip().lower()
                    st = (row.get("status") or "todo").strip().lower()
                    item_id = (row.get("id") or "").strip()
                    existing = {i.id for i in self.projects[project_name]}
                    if not item_id or item_id in existing:
                        item_id = self.generate_item_id(project_name)
                        existing.add(item_id)
                    item = BacklogItem(
                        id=item_id,
                        title=title,
                        description=row.get("description") or "",
                        priority=pri if pri in valid_pri else "medium",
                        status=st if st in valid_st else "todo",
                        sprint=row.get("sprint") or None,
                        epic=row.get("epic") or None,
                        assignee=row.get("assignee") or None,
                        story_points=coerce_points((row.get("story_points") or "").strip()),
                    )
                    if row.get("created_at"):
                        item.created_at = row["created_at"]
                    self.projects[project_name].append(item)
                    imported += 1
            self.save_project(project_name)
            self.console.print(
                f"[success]Imported {imported} item(s) into '{escape(project_name)}'[/]"
                + (f" [muted]({skipped} skipped)[/]" if skipped else ""))
            return True
        except Exception as e:
            self.console.print(f"[danger]Import failed: {escape(str(e))}[/]")
            return False


class InteractiveCLI:
    """Interactive CLI shell for the product backlog manager."""
    
    def __init__(self, manager: BacklogManager):
        self.manager = manager
        self.console = get_console()
        self.current_project = None
        self.running = True
        self._session = None
        # Restore last project (Phase 2)
        try:
            last = load_config().get("last_project")
            if last and last in self.manager.projects:
                self.current_project = last
        except Exception:
            pass
        # prompt_toolkit session with history (optional)
        if _HAS_PROMPT_TOOLKIT:
            try:
                self._session = PromptSession(
                    history=FileHistory(str(Path.home() / ".backlogd_history")))
            except Exception:
                self._session = None

        # Command mapping
        self.commands = {
            'help': self.show_help,
            'h': self.show_help,
            '?': self.show_help,
            'exit': self.exit_cli,
            'quit': self.exit_cli,
            'q': self.exit_cli,
            'clear': self.clear_screen,
            'cls': self.clear_screen,

            # Project commands
            'projects': self.list_projects,
            'use': self.use_project,
            'create-project': self.create_project,
            'delete-project': self.delete_project,

            # Item commands (Phase 1 views)
            'items': self.list_items,
            'ls': self.list_items,
            'board': self.show_board,
            'kanban': self.show_board,
            'stats': self.show_stats,
            'dashboard': self.show_stats,
            'search': self.search,
            'find': self.search,
            'add': self.add_item,
            'update': self.update_item,
            'delete': self.delete_item,
            'show': self.show_item,

            # Export / import commands
            'export-csv': self.export_csv,
            'export-xlsx': self.export_xlsx,
            'import-csv': self.import_csv,

            # Full-screen TUI
            'tui': self.launch_tui,

            # Status
            'status': self.show_status,
        }
    
    def show_banner(self):
        """Display the application banner."""
        ascii_art = text2art("backlogd")
        subtitle = """
Product Backlog Manager for CLI

A powerful terminal-based tool for managing product backlogs with YAML storage and rich formatting. 

Type 'help' for available commands or 'exit' to quit. 
        """
        self.console.print(Text(ascii_art, style="bold cyan"))
        self.console.print(subtitle, style="bold cyan")
    
    def get_prompt(self):
        """Get the CLI prompt string: backlogd>> or backlogd (demo)>>."""
        if self.current_project:
            return f"[success]backlogd[/] [brand]({escape(self.current_project)})[/]>> "
        return "[success]backlogd[/]>> "

    def get_plain_prompt(self) -> str:
        if self.current_project:
            return f"backlogd ({self.current_project})>> "
        return "backlogd>> "

    def _remember_project(self):
        try:
            save_config({"last_project": self.current_project})
        except Exception:
            pass

    def _completer(self):
        if not _HAS_PROMPT_TOOLKIT:
            return None
        words = list(self.commands.keys()) + [
            "--priority", "--status", "--sprint", "--epic",
            "--assignee", "--search", "--sort", "all",
        ]
        words += list(self.manager.projects.keys())
        if self.current_project and self.current_project in self.manager.projects:
            words += [i.id for i in self.manager.projects[self.current_project][:200]]
        try:
            return WordCompleter(words, ignore_case=True)
        except Exception:
            return None

    def _ask_input(self) -> str:
        """History + autocomplete when prompt_toolkit is available."""
        if self._session is not None:
            try:
                return self._session.prompt(
                    self.get_plain_prompt(), completer=self._completer())
            except KeyboardInterrupt:
                raise
            except Exception:
                pass
        return Prompt.ask(self.get_prompt(), console=self.console)

    def show_help(self, args=None):
        """Show help information."""
        help_text = """
[brand]Views:[/brand]
  [success]items[/] [filters]      Table view (hides done unless [success]all[/])
  [success]items all[/] [filters]  Include done items
  [success]board[/], kanban [filters]  Kanban grouped by status
  [success]stats[/], dashboard [project]  Totals + bars + tops
  [success]search[/], find <text> [--status ..] [--priority ..]  Full-text search

[brand]General:[/brand]
  help, h, ?           Show this help
  exit, quit, q        Exit
  clear, cls           Clear screen
  status               Current project summary
  tui [project]        Full-screen TUI (sidebar + table)

[brand]Projects:[/brand]
  projects             List all projects
  use <project>        Switch project
  create-project <name>
  delete-project <name>

[brand]Items:[/brand]
  add <title> <desc>   Add (guided: selects + autocomplete)
  update <id>          Update interactively
  delete <id>          Delete with confirm
  show <id>            Full details (Markdown + grid)

[brand]Import / Export:[/brand]
  export-csv [--all] [file]  Export project (or --all combined)
  export-xlsx [--all] [file] Export project (or --all combined)
  import-csv <file>          Import CSV into current project

[brand]Filters (items / board):[/brand]
  --priority <low,medium,high,critical>  (comma allowed)
  --status <todo,in_progress,blocked,done>  (comma allowed)
  --sprint <name>  --epic <name>  --assignee <name>
  --search <text>  --sort <priority|status|points|updated|title>

[brand]Examples:[/brand]
  use web-app
  board --sprint \"Sprint 1\"
  stats
  search login --status todo,in_progress
  items --priority high --assignee jane --sort points
        """
        panel = Panel(help_text, title="Help", border_style="blue")
        self.console.print(panel)
    
    def show_goodbye(self):
        """Single ASCII-safe exit message (dynamic year, no emoji)."""
        year = datetime.now().year
        self.console.print(
            f"[success]Bye! Data saved to {escape(str(self.manager.data_dir))}/. "
            "Resume with: python backlogd.py[/]")
        self.console.print(
            f"[muted]backlogd - by [link=https://bugrakilic.net]Bugra Kilic[/link] "
            f"with AI assistance (c) {year}[/]\n")

    def exit_cli(self, args=None):
        """Exit the CLI."""
        self.show_goodbye()
        self.running = False
    
    def clear_screen(self, args=None):
        """Clear the screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
        self.show_banner()
    
    def show_status(self, args=None):
        """Mini-dashboard: project, totals, status bars, points."""
        proj = self.current_project
        total_projects = len(self.manager.projects)
        self.console.print(Rule("[header]Status[/]", style="brand"))
        info = Table(box=None, show_header=False, padding=(0, 2))
        info.add_column("K", style="brand", no_wrap=True)
        info.add_column("V")
        info.add_row("Active project", escape(proj) if proj else "[muted]None (use <project>)[/]")
        info.add_row("Total projects", str(total_projects))
        info.add_row("Data dir", escape(str(self.manager.data_dir)))
        info.add_row("Forms", "questionary" if _HAS_QUESTIONARY else "rich (pip install questionary for selects)")
        info.add_row("History", "prompt_toolkit" if _HAS_PROMPT_TOOLKIT else "off (pip install prompt_toolkit)")
        self.console.print(Panel(info, title="Session", border_style="cyan"))

        if proj and proj in self.manager.projects:
            items = self.manager.projects[proj]
            total = len(items)
            pts = sum(i.story_points or 0 for i in items)
            done = sum(1 for i in items if i.status == "done")
            t = Table(title=f"{proj} - {total} items, {done} done, {pts} pts",
                      box=box.ROUNDED, header_style="header", expand=False)
            t.add_column("Status")
            t.add_column("N", justify="right")
            t.add_column("Share")
            for st in ("todo", "in_progress", "blocked", "done"):
                c = sum(1 for i in items if i.status == st)
                t.add_row(styled_status(st), str(c),
                          _bar(c, total) + f"  [muted]{c * 100 // total if total else 0}%[/]")
            self.console.print(t)
            self.console.print("[muted]Tip: board • stats • items • search <text>[/]")
    
    def list_projects(self, args=None):
        """List all projects."""
        self.manager.list_projects()
    
    def use_project(self, args):
        """Switch to a project."""
        if not args:
            self.console.print("[red]Usage: use <project-name>[/red]")
            return
        
        project_name = args[0]
        if project_name in self.manager.projects:
            self.current_project = project_name
            self._remember_project()
            self.console.print(f"[success]Switched to project '{escape(project_name)}'[/]")
            self.console.print(f"[muted]Prompt is now:[/] [brand]backlogd ({escape(project_name)})>>[/]")
        else:
            self.console.print(f"[danger]Project '{escape(project_name)}' not found.[/]")
            if self.manager.projects:
                self.console.print(f"[warning]Available: {escape(', '.join(sorted(self.manager.projects.keys())))}[/]")

    def create_project(self, args):
        """Create a new project."""
        if not args:
            self.console.print("[danger]Usage: create-project <project-name>[/]")
            return

        project_name = args[0]
        if self.manager.create_project(project_name):
            self.current_project = project_name
            self._remember_project()

    def delete_project(self, args):
        """Delete a project."""
        if not args:
            self.console.print("[danger]Usage: delete-project <project-name>[/]")
            return

        project_name = args[0]
        if self.manager.delete_project(project_name):
            if self.current_project == project_name:
                self.current_project = None
                self._remember_project()
    
    def list_items(self, args):
        """List items with optional filtering."""
        if not self.current_project:
            self.console.print("[danger]No project selected. Use 'use <project>'.[/]")
            return

        args = list(args or [])
        show_all = "all" in args

        filters = self.parse_filter_args(args)

        # Unless "all" is specified, exclude "done" items (but respect explicit --status)
        if not show_all and "status" not in filters:
            filters['status'] = 'todo,in_progress,blocked'

        allowed = {"priority", "status", "sprint", "epic", "assignee", "search", "sort"}
        filters = {k: v for k, v in filters.items() if k in allowed}
        self.manager.list_items(project_name=self.current_project, **filters)

    def show_board(self, args):
        """Kanban board for current project."""
        if not self.current_project:
            self.console.print("[danger]No project selected. Use 'use <project>'.[/]")
            return
        filters = self.parse_filter_args(list(args or []))
        allowed = {"priority", "sprint", "epic", "assignee", "search"}
        filters = {k: v for k, v in filters.items() if k in allowed}
        self.manager.board(self.current_project, **filters)

    def show_stats(self, args):
        """Dashboard stats. `stats [project]` defaults to current project."""
        if args:
            self.manager.stats(args[0])
        elif self.current_project:
            self.manager.stats(self.current_project)
        else:
            self.manager.stats(None)

    def search(self, args):
        """Full-text search: search <text> [--status ..] [--priority ..]."""
        if not self.current_project:
            self.console.print("[danger]No project selected. Use 'use <project>'.[/]")
            return
        if not args:
            self.console.print("[danger]Usage: search <text> [--status ..] [--priority ..][/]")
            return
        args = list(args)
        # First non-flag tokens are the query
        query_parts = []
        rest = []
        seen_flag = False
        for tok in args:
            if tok.startswith("--"):
                seen_flag = True
            if not seen_flag and not tok.startswith("--"):
                query_parts.append(tok)
            else:
                if tok.startswith("--") or seen_flag and tok not in query_parts:
                    rest.append(tok)
        # query may also come via --search
        filters = self.parse_filter_args(rest)
        query = " ".join(query_parts) or filters.pop("search", "")
        if not query:
            self.console.print("[danger]Usage: search <text>[/]")
            return
        self.manager.search_items(
            self.current_project, query,
            status=filters.get("status"), priority=filters.get("priority"),
            sort=filters.get("sort"))

    def parse_filter_args(self, args):
        """Parse --key value filter arguments."""
        filters = {}
        i = 0
        allowed = {"priority", "status", "sprint", "epic", "assignee", "search", "sort"}
        while i < len(args):
            tok = args[i]
            if tok == "all":
                i += 1
                continue
            if tok.startswith('--'):
                name = tok[2:].lower()
                if name in allowed and i + 1 < len(args) and not args[i + 1].startswith('--'):
                    filters[name] = args[i + 1]
                    i += 2
                else:
                    i += 1
            else:
                i += 1
        return filters
    
    # --- Phase 2 form helpers (questionary first, rich fallback) ---
    def _form_text(self, message: str, default: str = "") -> str:
        if _HAS_QUESTIONARY:
            try:
                ans = questionary.text(message, default=default).ask()
                return ans or ""
            except Exception:
                pass
        return Prompt.ask(f"[brand]{escape(message)}[/]", default=default)

    def _form_select(self, message: str, choices: List[str], default: str = None) -> Optional[str]:
        if _HAS_QUESTIONARY:
            try:
                ans = questionary.select(message, choices=choices, default=default).ask()
                return ans
            except Exception:
                pass
        return Prompt.ask(f"[brand]{escape(message)}[/]",
                          choices=choices, default=default or choices[0])

    def _form_optional_choice(self, message: str, existing: List[str],
                              current: str = None) -> Optional[str]:
        """Free-text with suggestions. Empty keeps current/None."""
        hint = f"existing: {', '.join(existing[:5])}" if existing else "new value"
        label = f"{message} [{current or '-'}] ({hint}, Enter to keep)"
        if _HAS_QUESTIONARY and existing:
            try:
                ans = questionary.autocomplete(label, choices=existing, default="").ask()
                return (ans or "").strip() or None
            except Exception:
                pass
        ans = Prompt.ask(f"[brand]{escape(message)} [{escape(current or '-')}] watch={escape(','.join(existing[:4])) if existing else 'none'}[/]",
                         default="")
        return ans.strip() or None

    @staticmethod
    def _parse_points(raw: str) -> Optional[int]:
        raw = (raw or "").strip()
        if not raw:
            return None
        if raw.isdigit() and 0 <= int(raw) <= 100:
            return int(raw)
        return "invalid"

    def add_item(self, args):
        """Guided add: selects + autocomplete when questionary is installed."""
        if not self.current_project:
            self.console.print("[danger]No project selected. Use 'use <project>'.[/]")
            return

        try:
            if len(args) >= 2:
                title, description = args[0], args[1]
            else:
                title = self._form_text("Title", default="")
                if not title.strip():
                    self.console.print("[warning]Title is required. Cancelled.[/]")
                    return
                description = self._form_text("Description", default="")

            priority = self._form_select(
                "Priority", ["low", "medium", "high", "critical"], default="medium")
            if priority is None:
                self.console.print("\n[warning]Operation cancelled.[/]")
                return

            proj = self.current_project
            sprints = self.manager.distinct_values(proj, "sprint")
            epics = self.manager.distinct_values(proj, "epic")
            assignees = self.manager.distinct_values(proj, "assignee")

            sprint = self._form_optional_choice("Sprint", sprints)
            epic = self._form_optional_choice("Epic", epics)
            assignee = self._form_optional_choice("Assignee", assignees)

            pts_raw = self._form_text("Story points 0-100 (optional)", default="")
            points = self._parse_points(pts_raw)
            if points == "invalid":
                self.console.print("[warning]Points must be 0-100. Saved without points.[/]")
                points = None

            self.manager.add_item(proj, title, description, priority=priority,
                                  sprint=sprint, epic=epic,
                                  assignee=assignee, story_points=points)

        except KeyboardInterrupt:
            self.console.print("\n[warning]Operation cancelled.[/]")
        except Exception as e:
            self.console.print(f"[danger]Error adding item: {escape(str(e))}[/]")
    
    def update_item(self, args):
        """Interactive update item."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        if not args:
            self.console.print("[red]Usage: update <item-id>[/red]")
            return
        
        item_id = args[0]
        
        # Find the item first
        item = None
        for i in self.manager.projects[self.current_project]:
            if i.id == item_id:
                item = i
                break
        
        if not item:
            self.console.print(f"[red]Item '{item_id}' not found.[/red]")
            return
        
        try:
            self.console.print(f"[brand]Updating {escape(item_id)}: {escape(item.title)}[/]")
            self.console.print("[muted]Enter keeps current value. Esc cancels (questionary).[/]")

            updates = {}
            proj = self.current_project
            sprints = [s for s in self.manager.distinct_values(proj, "sprint") if s != item.sprint]
            epics = [s for s in self.manager.distinct_values(proj, "epic") if s != item.epic]
            assignees = [s for s in self.manager.distinct_values(proj, "assignee") if s != item.assignee]

            new_title = self._form_text(f"Title [{item.title}]", default="")
            if new_title.strip():
                updates['title'] = new_title.strip()

            new_desc = self._form_text(
                f"Description [{_truncate(item.description or '', 40)}]", default="")
            if new_desc.strip():
                updates['description'] = new_desc.strip()

            if _HAS_QUESTIONARY:
                try:
                    new_priority = questionary.select(
                        f"Priority [{item.priority}] (Enter keeps)",
                        choices=["keep", "low", "medium", "high", "critical"],
                        default="keep").ask()
                    if new_priority in (None,):
                        self.console.print("\n[warning]Operation cancelled.[/]")
                        return
                    if new_priority != "keep":
                        updates['priority'] = new_priority
                    new_status = questionary.select(
                        f"Status [{item.status}] (Enter keeps)",
                        choices=["keep", "todo", "in_progress", "done", "blocked"],
                        default="keep").ask()
                    if new_status is None:
                        self.console.print("\n[warning]Operation cancelled.[/]")
                        return
                    if new_status != "keep":
                        updates['status'] = new_status
                except Exception:
                    pass
            else:
                new_priority = Prompt.ask("Priority (Enter keeps)",
                                          choices=["", "low", "medium", "high", "critical"],
                                          default="")
                if new_priority:
                    updates['priority'] = new_priority
                new_status = Prompt.ask("Status (Enter keeps)",
                                        choices=["", "todo", "in_progress", "done", "blocked"],
                                        default="")
                if new_status:
                    updates['status'] = new_status

            v = self._form_optional_choice("Sprint", sprints, current=item.sprint)
            if v:
                updates['sprint'] = v
            v = self._form_optional_choice("Epic", epics, current=item.epic)
            if v:
                updates['epic'] = v
            v = self._form_optional_choice("Assignee", assignees, current=item.assignee)
            if v:
                updates['assignee'] = v

            pts_raw = self._form_text(
                f"Story points [{item.story_points or '-'}] 0-100", default="")
            pts = self._parse_points(pts_raw)
            if pts == "invalid":
                self.console.print("[warning]Points must be 0-100. Kept old value.[/]")
            elif pts is not None:
                updates['story_points'] = pts

            if updates:
                self.manager.update_item(self.current_project, item_id, **updates)
            else:
                self.console.print("[warning]No changes made.[/]")

        except KeyboardInterrupt:
            self.console.print("\n[warning]Operation cancelled.[/]")
        except Exception as e:
            self.console.print(f"[danger]Error updating item: {escape(str(e))}[/]")
    
    def delete_item(self, args):
        """Delete an item."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        if not args:
            self.console.print("[red]Usage: delete <item-id>[/red]")
            return
        
        item_id = args[0]
        self.manager.delete_item(self.current_project, item_id)
    
    def show_item(self, args):
        """Show item details."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        if not args:
            self.console.print("[red]Usage: show <item-id>[/red]")
            return
        
        item_id = args[0]
        self.manager.show_item_details(self.current_project, item_id)
    
    def export_csv(self, args):
        """Export to CSV. `export-csv [--all] [filename]`."""
        args = list(args or [])
        if "--all" in args or "all" in args:
            self.manager.export_all_to_csv(next((a for a in args if a not in ("--all", "all")), None))
            return
        if not self.current_project:
            self.console.print("[danger]No project selected. Use 'use <project>' or 'export-csv --all'.[/]")
            return
        self.manager.export_to_csv(self.current_project, args[0] if args else None)

    def export_xlsx(self, args):
        """Export to Excel. `export-xlsx [--all] [filename]`."""
        args = list(args or [])
        if "--all" in args or "all" in args:
            self.manager.export_all_to_xlsx(next((a for a in args if a not in ("--all", "all")), None))
            return
        if not self.current_project:
            self.console.print("[danger]No project selected. Use 'use <project>' or 'export-xlsx --all'.[/]")
            return
        self.manager.export_to_xlsx(self.current_project, args[0] if args else None)

    def import_csv(self, args):
        """Import from CSV. `import-csv <filename>` (current project) or `import-csv <project> <filename>`."""
        args = list(args or [])
        if len(args) == 1:
            if not self.current_project:
                self.console.print("[danger]Usage: import-csv <filename> (needs a project selected)[/]")
                return
            self.manager.import_from_csv(self.current_project, args[0])
        elif len(args) >= 2:
            self.manager.import_from_csv(args[0], args[1])
            if self.manager.projects.get(args[0]) is not None:
                self.current_project = args[0]
                self._remember_project()
        else:
            self.console.print("[danger]Usage: import-csv <filename>[/]")
    
    def launch_tui(self, args):
        """Launch the full-screen Textual TUI; return here on exit."""
        project = args[0] if args else self.current_project
        try:
            from tui import BacklogApp
        except ImportError:
            self.console.print("[danger]TUI needs 'textual'. Run: pip install -r requirements.txt[/]")
            return
        try:
            BacklogApp(data_dir=str(self.manager.data_dir), project=project).run()
        finally:
            self.manager.load_projects()
            if self.current_project not in self.manager.projects:
                self.current_project = None

    def parse_command(self, user_input):
        """Parse user input into command and arguments."""
        try:
            parts = shlex.split(user_input.strip())
            if not parts:
                return None, []
            return parts[0].lower(), parts[1:]
        except ValueError:
            # Handle unmatched quotes
            parts = user_input.strip().split()
            if not parts:
                return None, []
            return parts[0].lower(), parts[1:]
    
    def show_onboarding(self):
        """First-run hints when there is nothing to show yet."""
        self.console.print(Panel(
            "[brand]Welcome to backlogd.[/]\n\n"
            "[muted]Get going in 30 seconds:[/]\n"
            "  1. [success]create-project demo[/]\n"
            "  2. [success]use demo[/]  (prompt becomes [brand]backlogd (demo)>>[/])\n"
            "  3. [success]add \"Login\" \"Auth UI\"[/]\n"
            "  4. [success]board[/]  [success]stats[/]  [success]search login[/]\n\n"
            "[muted]Set NO_COLOR=1 to disable colors. "
            "Install questionary + prompt_toolkit for selects, history and autocomplete.[/]",
            title="Onboarding", border_style="green"))

    def run(self):
        """Run the interactive CLI."""
        self.show_banner()
        if self.current_project:
            self.console.print(f"[muted]Resumed last project:[/] [brand]({escape(self.current_project)})[/]")
        if not self.manager.projects:
            self.show_onboarding()

        while self.running:
            try:
                user_input = self._ask_input()
                
                if not user_input.strip():
                    continue
                
                command, args = self.parse_command(user_input)
                
                if command in self.commands:
                    self.commands[command](args)
                else:
                    self.console.print(f"[red]Unknown command: {command}[/red]")
                    self.console.print("[yellow]Type 'help' for available commands.[/yellow]")
            
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use 'exit' to quit.[/yellow]")
            except EOFError:
                self.console.print("")
                self.show_goodbye()
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")


def create_parser():
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(description="backlogd - CLI Product Backlog Manager")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Project commands
    proj_parser = subparsers.add_parser('project', help='Project management')
    proj_subparsers = proj_parser.add_subparsers(dest='project_action')
    
    proj_subparsers.add_parser('list', help='List all projects')
    
    create_proj = proj_subparsers.add_parser('create', help='Create a new project')
    create_proj.add_argument('name', help='Project name')
    
    delete_proj = proj_subparsers.add_parser('delete', help='Delete a project')
    delete_proj.add_argument('name', help='Project name')
    
    # Item commands
    item_parser = subparsers.add_parser('item', help='Item management')
    item_subparsers = item_parser.add_subparsers(dest='item_action')
    
    # Add item
    add_item = item_subparsers.add_parser('add', help='Add a new item')
    add_item.add_argument('project', help='Project name')
    add_item.add_argument('title', help='Item title')
    add_item.add_argument('description', help='Item description')
    add_item.add_argument('--priority', choices=['low', 'medium', 'high', 'critical'], default='medium')
    add_item.add_argument('--sprint', help='Sprint name')
    add_item.add_argument('--epic', help='Epic name')
    add_item.add_argument('--assignee', help='Assignee name')
    add_item.add_argument('--points', type=points_arg, help='Story points (0-100)')

    # Update item
    update_item = item_subparsers.add_parser('update', help='Update an item')
    update_item.add_argument('project', help='Project name')
    update_item.add_argument('id', help='Item ID')
    update_item.add_argument('--title', help='New title')
    update_item.add_argument('--description', help='New description')
    update_item.add_argument('--priority', choices=['low', 'medium', 'high', 'critical'])
    update_item.add_argument('--status', choices=['todo', 'in_progress', 'done', 'blocked'])
    update_item.add_argument('--sprint', help='Sprint name')
    update_item.add_argument('--epic', help='Epic name')
    update_item.add_argument('--assignee', help='Assignee name')
    update_item.add_argument('--points', type=points_arg, help='Story points (0-100)')
    
    # Delete item
    delete_item = item_subparsers.add_parser('delete', help='Delete an item')
    delete_item.add_argument('project', help='Project name')
    delete_item.add_argument('id', help='Item ID')
    
    # Show item details
    show_item = item_subparsers.add_parser('show', help='Show item details')
    show_item.add_argument('project', help='Project name')
    show_item.add_argument('id', help='Item ID')
    
    # List items
    list_items = item_subparsers.add_parser('list', help='List items (table)')
    list_items.add_argument('--project', help='Project name')
    list_items.add_argument('--priority', help='Priority filter (comma allowed)')
    list_items.add_argument('--sprint', help='Sprint name')
    list_items.add_argument('--epic', help='Epic name')
    list_items.add_argument('--assignee', help='Assignee filter')
    list_items.add_argument('--status', help='Status filter (comma allowed)')
    list_items.add_argument('--search', help='Search text (id/title/description)')
    list_items.add_argument('--sort', choices=['priority', 'status', 'points', 'updated', 'title'],
                            help='Sort order')

    # Board view
    board_items = item_subparsers.add_parser('board', help='Kanban board by status')
    board_items.add_argument('--project', required=True, help='Project name')
    board_items.add_argument('--priority', help='Priority filter')
    board_items.add_argument('--sprint', help='Sprint name')
    board_items.add_argument('--epic', help='Epic name')
    board_items.add_argument('--assignee', help='Assignee filter')
    board_items.add_argument('--search', help='Search text')

    # Stats dashboard
    stats_items = item_subparsers.add_parser('stats', help='Stats dashboard')
    stats_items.add_argument('--project', help='Project name (omit for all)')

    # Search
    search_items = item_subparsers.add_parser('search', help='Full-text search')
    search_items.add_argument('--project', required=True, help='Project name')
    search_items.add_argument('query', help='Search text')
    search_items.add_argument('--status', help='Status filter')
    search_items.add_argument('--priority', help='Priority filter')
    
    # Export commands
    export_parser = subparsers.add_parser('export', help='Export data')
    export_subparsers = export_parser.add_subparsers(dest='export_format')

    csv_export = export_subparsers.add_parser('csv', help='Export to CSV')
    csv_export.add_argument('project', nargs='?', help='Project name (omit with --all)')
    csv_export.add_argument('--filename', help='Output filename')
    csv_export.add_argument('--all', action='store_true', help='Export all projects combined')

    xlsx_export = export_subparsers.add_parser('xlsx', help='Export to Excel')
    xlsx_export.add_argument('project', nargs='?', help='Project name (omit with --all)')
    xlsx_export.add_argument('--filename', help='Output filename')
    xlsx_export.add_argument('--all', action='store_true', help='Export all projects combined')

    # Import commands
    import_parser = subparsers.add_parser('import', help='Import data')
    import_subparsers = import_parser.add_subparsers(dest='import_format')

    csv_import = import_subparsers.add_parser('csv', help='Import from CSV (export format)')
    csv_import.add_argument('project', help='Project name (created if missing)')
    csv_import.add_argument('--filename', required=True, help='Input CSV file')

    # Full-screen TUI (Phase 3, Textual; lazy import so classic CLI needs nothing new)
    tui_parser = subparsers.add_parser('tui', help='Launch full-screen TUI')
    tui_parser.add_argument('--project', help='Project to open (default: first)')
    tui_parser.add_argument('--data-dir', default='database_backlogd', help='Data directory')
    
    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    
    # If no arguments provided, start interactive mode
    if len(sys.argv) == 1:
        manager = BacklogManager()
        cli = InteractiveCLI(manager)
        cli.run()
        return
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = BacklogManager()
    
    # Project commands
    if args.command == 'project':
        if args.project_action == 'list':
            manager.list_projects()
        elif args.project_action == 'create':
            manager.create_project(args.name)
        elif args.project_action == 'delete':
            manager.delete_project(args.name)
    
    # Item commands
    elif args.command == 'item':
        if args.item_action == 'add':
            manager.add_item(
                args.project, args.title, args.description,
                priority=args.priority, sprint=args.sprint, epic=args.epic,
                assignee=args.assignee, story_points=args.points
            )
        elif args.item_action == 'update':
            update_data = {k: v for k, v in vars(args).items() 
                          if v is not None and k not in ['command', 'item_action', 'project', 'id']}
            manager.update_item(args.project, args.id, **update_data)
        elif args.item_action == 'delete':
            manager.delete_item(args.project, args.id)
        elif args.item_action == 'show':
            manager.show_item_details(args.project, args.id)
        elif args.item_action == 'list':
            manager.list_items(
                project_name=args.project, priority=args.priority,
                sprint=args.sprint, epic=args.epic, status=args.status,
                assignee=args.assignee, search=args.search, sort=args.sort
            )
        elif args.item_action == 'board':
            manager.board(
                args.project, priority=args.priority, sprint=args.sprint,
                epic=args.epic, assignee=args.assignee, search=args.search
            )
        elif args.item_action == 'stats':
            manager.stats(args.project)
        elif args.item_action == 'search':
            manager.search_items(
                args.project, args.query,
                status=args.status, priority=args.priority
            )
    
    # Export commands
    elif args.command == 'export':
        if args.export_format == 'csv':
            if getattr(args, 'all', False):
                manager.export_all_to_csv(args.filename)
            elif args.project:
                manager.export_to_csv(args.project, args.filename)
            else:
                parser.error("export csv needs a project or --all")
        elif args.export_format == 'xlsx':
            if getattr(args, 'all', False):
                manager.export_all_to_xlsx(args.filename)
            elif args.project:
                manager.export_to_xlsx(args.project, args.filename)
            else:
                parser.error("export xlsx needs a project or --all")

    # Import commands
    elif args.command == 'import':
        if args.import_format == 'csv':
            manager.import_from_csv(args.project, args.filename)

    # Full-screen TUI
    elif args.command == 'tui':
        try:
            from tui import BacklogApp
        except ImportError:
            print("TUI needs the 'textual' package. Run: pip install -r requirements.txt")
            sys.exit(1)
        BacklogApp(data_dir=args.data_dir, project=args.project).run()


if __name__ == "__main__":
    main()