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
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich import box
    from rich.markup import escape
    import pandas as pd
except ImportError:
    print("Required packages not installed. Please run:")
    print("pip install rich pyyaml pandas openpyxl")
    sys.exit(1)


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
        self.console = Console()
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
            self.console.print("[yellow]No projects found.[/yellow]")
            return
        
        table = Table(title="Available Projects", box=box.ROUNDED)
        table.add_column("Project Name", style="cyan")
        table.add_column("Items", justify="right", style="magenta")
        table.add_column("Status", style="green")
        
        for project_name, items in self.projects.items():
            status_counts = {}
            for item in items:
                status_counts[item.status] = status_counts.get(item.status, 0) + 1
            
            status_text = " | ".join([f"{k}: {v}" for k, v in status_counts.items()])
            table.add_row(project_name, str(len(items)), status_text or "Empty")
        
        self.console.print(table)
    
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
            project_file = self.get_project_file(project_name)
            if project_file.exists():
                project_file.unlink()
            del self.projects[project_name]
            self.console.print(f"[green]Project '{project_name}' deleted successfully.[/green]")
            return True
        return False
    
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
            story_points=story_points
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
                    del self.projects[project_name][i]
                    self.save_project(project_name)
                    self.console.print(f"[green]Item '{item_id}' deleted successfully.[/green]")
                    return True
                return False
        
        self.console.print(f"[red]Item '{item_id}' not found.[/red]")
        return False
    
    def list_items(self, project_name: str = None, priority: str = None, 
                   sprint: str = None, epic: str = None, status: str = None):
        """List backlog items with optional filtering."""
        if project_name and project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return
        
        projects_to_show = {project_name: self.projects[project_name]} if project_name else self.projects
        
        for proj_name, items in projects_to_show.items():
            if not items:
                continue
            
            # Apply filters
            filtered_items = items
            if priority:
                filtered_items = [item for item in filtered_items if item.priority == priority]
            if sprint:
                filtered_items = [item for item in filtered_items if item.sprint == sprint]
            if epic:
                filtered_items = [item for item in filtered_items if item.epic == epic]
            if status:
                filtered_items = [item for item in filtered_items if item.status == status]
            
            if not filtered_items:
                continue
            
            # Create table
            table = Table(title=f"Backlog Items - {proj_name}", box=box.ROUNDED)
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="white")
            table.add_column("Priority", style="red")
            table.add_column("Status", style="green")
            table.add_column("Sprint", style="blue")
            table.add_column("Epic", style="magenta")
            table.add_column("Assignee", style="yellow")
            table.add_column("Points", justify="right")
            
            for item in filtered_items:
                priority_color = {
                    "critical": "[bold red]",
                    "high": "[red]",
                    "medium": "[yellow]",
                    "low": "[green]"
                }.get(item.priority, "")
                
                status_color = {
                    "todo": "[blue]",
                    "in_progress": "[yellow]",
                    "done": "[green]",
                    "blocked": "[red]"
                }.get(item.status, "")
                
                table.add_row(
                    item.id,
                    item.title[:50] + "..." if len(item.title) > 50 else item.title,
                    f"{priority_color}{item.priority}[/]",
                    f"{status_color}{item.status}[/]",
                    item.sprint or "-",
                    item.epic or "-",
                    item.assignee or "-",
                    str(item.story_points) if item.story_points else "-"
                )
            
            self.console.print(table)
    
    def show_item_details(self, project_name: str, item_id: str):
        """Show detailed information about a backlog item."""
        if project_name not in self.projects:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            return
        
        for item in self.projects[project_name]:
            if item.id == item_id:
                panel_content = f"""
[bold cyan]Title:[/bold cyan] {item.title}
[bold cyan]Description:[/bold cyan] {item.description}
[bold cyan]Priority:[/bold cyan] {item.priority}
[bold cyan]Status:[/bold cyan] {item.status}
[bold cyan]Sprint:[/bold cyan] {item.sprint or 'Not assigned'}
[bold cyan]Epic:[/bold cyan] {item.epic or 'Not assigned'}
[bold cyan]Assignee:[/bold cyan] {item.assignee or 'Unassigned'}
[bold cyan]Story Points:[/bold cyan] {item.story_points or 'Not estimated'}
[bold cyan]Created:[/bold cyan] {item.created_at[:19] if item.created_at else 'Unknown'}
[bold cyan]Updated:[/bold cyan] {item.updated_at[:19] if item.updated_at else 'Unknown'}
                """.strip()
                
                panel = Panel(panel_content, title=f"Item Details - {item.id}", border_style="blue")
                self.console.print(panel)
                return
        
        self.console.print(f"[red]Item '{item_id}' not found.[/red]")
    
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


class InteractiveCLI:
    """Interactive CLI shell for the product backlog manager."""
    
    def __init__(self, manager: BacklogManager):
        self.manager = manager
        self.console = Console()
        self.current_project = None
        self.running = True
        
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
            
            # Item commands
            'items': self.list_items,
            'add': self.add_item,
            'update': self.update_item,
            'delete': self.delete_item,
            'show': self.show_item,
            
            # Export commands
            'export-csv': self.export_csv,
            'export-xlsx': self.export_xlsx,
            
            # Status
            'status': self.show_status,
        }
    
    def show_banner(self):
        """Display the application banner."""
        banner = """
╔══════════════════════════════════════════════════════════════╗
║        🎯 backlogd - CLI Product Backlog Manager             ║
║                                                              ║
║  A powerful terminal-based tool for managing product         ║
║  backlogs with YAML storage and rich formatting.             ║
║                                                              ║
║  Type 'help' for available commands or 'exit' to quit.       ║
╚══════════════════════════════════════════════════════════════╝
        """
        self.console.print(banner, style="bold cyan")
    
    def get_prompt(self):
        """Get the CLI prompt string."""
        project_info = f"[{self.current_project}]" if self.current_project else "[no project]"
        return f"[bold green]backlogd[/bold green][cyan]{project_info}[/cyan]>> "
    
    def show_help(self, args=None):
        """Show help information."""
        help_text = """
[bold cyan]Available Commands:[/bold cyan]

[bold yellow]General:[/bold yellow]
  help, h, ?           Show this help message
  exit, quit, q        Exit the application
  clear, cls           Clear the screen
  status               Show current status

[bold yellow]Project Management:[/bold yellow]
  projects             List all projects
  use <project>        Switch to a project
  create-project <name> Create a new project
  delete-project <name> Delete a project

[bold yellow]Item Management:[/bold yellow]
  items [filters]      List items in current project
  add <title> <desc>   Add a new item (interactive)
  update <id>          Update an item (interactive)
  delete <id>          Delete an item
  show <id>            Show item details

[bold yellow]Export:[/bold yellow]
  export-csv [filename]  Export current project to CSV
  export-xlsx [filename] Export current project to Excel

[bold yellow]Filtering Options (for 'items' command):[/bold yellow]
  --priority <level>   Filter by priority (low, medium, high, critical)
  --status <status>    Filter by status (todo, in_progress, done, blocked)
  --sprint <name>      Filter by sprint
  --epic <name>        Filter by epic
  --assignee <name>    Filter by assignee

[bold yellow]Examples:[/bold yellow]
  use web-app
  items --priority high --status todo
  add "User Login" "Implement authentication system"
  update TEST-APP-1
  show TEST-APP-1
        """
        panel = Panel(help_text, title="Help", border_style="blue")
        self.console.print(panel)
    
    def exit_cli(self, args=None):
        """Exit the CLI."""
        self.console.print("[yellow]Goodbye! 👋[/yellow]")
        self.running = False
    
    def clear_screen(self, args=None):
        """Clear the screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
        self.show_banner()
    
    def show_status(self, args=None):
        """Show current status."""
        status_info = f"""
[bold cyan]Current Status:[/bold cyan]
• Active Project: {self.current_project or 'None'}
• Total Projects: {len(self.manager.projects)}
• Data Directory: {self.manager.data_dir}
        """
        
        if self.current_project and self.current_project in self.manager.projects:
            items = self.manager.projects[self.current_project]
            status_counts = {}
            for item in items:
                status_counts[item.status] = status_counts.get(item.status, 0) + 1
            
            status_info += f"\n[bold cyan]Current Project Items:[/bold cyan]\n"
            for status, count in status_counts.items():
                status_info += f"• {status}: {count}\n"
            status_info += f"• Total: {len(items)}"
        
        panel = Panel(status_info.strip(), title="Status", border_style="green")
        self.console.print(panel)
    
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
            self.console.print(f"[green]Switched to project '{project_name}'[/green]")
        else:
            self.console.print(f"[red]Project '{project_name}' not found.[/red]")
            self.console.print(f"[yellow]Available projects: {', '.join(self.manager.projects.keys())}[/yellow]")
    
    def create_project(self, args):
        """Create a new project."""
        if not args:
            self.console.print("[red]Usage: create-project <project-name>[/red]")
            return
        
        project_name = args[0]
        if self.manager.create_project(project_name):
            self.current_project = project_name
    
    def delete_project(self, args):
        """Delete a project."""
        if not args:
            self.console.print("[red]Usage: delete-project <project-name>[/red]")
            return
        
        project_name = args[0]
        if self.manager.delete_project(project_name):
            if self.current_project == project_name:
                self.current_project = None
    
    def list_items(self, args):
        """List items with optional filtering."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        # Parse filter arguments
        filters = self.parse_filter_args(args)
        self.manager.list_items(
            project_name=self.current_project,
            **filters
        )
    
    def parse_filter_args(self, args):
        """Parse filter arguments from command line."""
        filters = {}
        i = 0
        while i < len(args):
            if args[i].startswith('--'):
                filter_name = args[i][2:]  # Remove '--'
                if i + 1 < len(args) and not args[i + 1].startswith('--'):
                    filters[filter_name] = args[i + 1]
                    i += 2
                else:
                    i += 1
            else:
                i += 1
        return filters
    
    def add_item(self, args):
        """Interactive add item."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        try:
            # Get basic info from args or prompt
            if len(args) >= 2:
                title = args[0]
                description = args[1]
            else:
                title = Prompt.ask("[cyan]Enter item title[/cyan]")
                description = Prompt.ask("[cyan]Enter item description[/cyan]")
            
            # Get optional fields
            priority = Prompt.ask(
                "[cyan]Priority[/cyan]", 
                choices=["low", "medium", "high", "critical"], 
                default="medium"
            )
            
            sprint = Prompt.ask("[cyan]Sprint (optional)[/cyan]", default="")
            epic = Prompt.ask("[cyan]Epic (optional)[/cyan]", default="")
            assignee = Prompt.ask("[cyan]Assignee (optional)[/cyan]", default="")
            
            story_points = None
            points_input = Prompt.ask("[cyan]Story points (optional)[/cyan]", default="")
            if points_input.isdigit():
                story_points = int(points_input)
            
            self.manager.add_item(
                self.current_project, title, description,
                priority=priority,
                sprint=sprint or None,
                epic=epic or None,
                assignee=assignee or None,
                story_points=story_points
            )
        
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Operation cancelled.[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error adding item: {e}[/red]")
    
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
            self.console.print(f"[cyan]Updating item '{item_id}': {item.title}[/cyan]")
            self.console.print("[yellow]Press Enter to keep current value[/yellow]")
            
            # Get updates
            updates = {}
            
            new_title = Prompt.ask(f"Title [{item.title}]", default="")
            if new_title:
                updates['title'] = new_title
            
            new_desc = Prompt.ask(f"Description [{item.description[:50]}...]", default="")
            if new_desc:
                updates['description'] = new_desc
            
            new_priority = Prompt.ask(
                f"Priority [{item.priority}]",
                choices=["low", "medium", "high", "critical"],
                default=""
            )
            if new_priority:
                updates['priority'] = new_priority
            
            new_status = Prompt.ask(
                f"Status [{item.status}]",
                choices=["todo", "in_progress", "done", "blocked"],
                default=""
            )
            if new_status:
                updates['status'] = new_status
            
            new_sprint = Prompt.ask(f"Sprint [{item.sprint or 'None'}]", default="")
            if new_sprint:
                updates['sprint'] = new_sprint
            
            new_epic = Prompt.ask(f"Epic [{item.epic or 'None'}]", default="")
            if new_epic:
                updates['epic'] = new_epic
            
            new_assignee = Prompt.ask(f"Assignee [{item.assignee or 'None'}]", default="")
            if new_assignee:
                updates['assignee'] = new_assignee
            
            new_points = Prompt.ask(f"Story points [{item.story_points or 'None'}]", default="")
            if new_points and new_points.isdigit():
                updates['story_points'] = int(new_points)
            
            if updates:
                self.manager.update_item(self.current_project, item_id, **updates)
            else:
                self.console.print("[yellow]No changes made.[/yellow]")
        
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Operation cancelled.[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error updating item: {e}[/red]")
    
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
        """Export to CSV."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        filename = args[0] if args else None
        self.manager.export_to_csv(self.current_project, filename)
    
    def export_xlsx(self, args):
        """Export to Excel."""
        if not self.current_project:
            self.console.print("[red]No project selected. Use 'use <project>' to select a project.[/red]")
            return
        
        filename = args[0] if args else None
        self.manager.export_to_xlsx(self.current_project, filename)
    
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
    
    def run(self):
        """Run the interactive CLI."""
        self.show_banner()
        
        while self.running:
            try:
                user_input = Prompt.ask(self.get_prompt(), console=self.console)
                
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
                self.console.print("\n[yellow]Goodbye! 👋[/yellow]")
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
    add_item.add_argument('--points', type=int, help='Story points')
    
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
    update_item.add_argument('--points', type=int, help='Story points')
    
    # Delete item
    delete_item = item_subparsers.add_parser('delete', help='Delete an item')
    delete_item.add_argument('project', help='Project name')
    delete_item.add_argument('id', help='Item ID')
    
    # Show item details
    show_item = item_subparsers.add_parser('show', help='Show item details')
    show_item.add_argument('project', help='Project name')
    show_item.add_argument('id', help='Item ID')
    
    # List items
    list_items = item_subparsers.add_parser('list', help='List items')
    list_items.add_argument('--project', help='Project name')
    list_items.add_argument('--priority', choices=['low', 'medium', 'high', 'critical'])
    list_items.add_argument('--sprint', help='Sprint name')
    list_items.add_argument('--epic', help='Epic name')
    list_items.add_argument('--status', choices=['todo', 'in_progress', 'done', 'blocked'])
    
    # Export commands
    export_parser = subparsers.add_parser('export', help='Export data')
    export_subparsers = export_parser.add_subparsers(dest='export_format')
    
    csv_export = export_subparsers.add_parser('csv', help='Export to CSV')
    csv_export.add_argument('project', help='Project name')
    csv_export.add_argument('--filename', help='Output filename')
    
    xlsx_export = export_subparsers.add_parser('xlsx', help='Export to Excel')
    xlsx_export.add_argument('project', help='Project name')
    xlsx_export.add_argument('--filename', help='Output filename')
    
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
                sprint=args.sprint, epic=args.epic, status=args.status
            )
    
    # Export commands
    elif args.command == 'export':
        if args.export_format == 'csv':
            manager.export_to_csv(args.project, args.filename)
        elif args.export_format == 'xlsx':
            manager.export_to_xlsx(args.project, args.filename)


if __name__ == "__main__":
    main()