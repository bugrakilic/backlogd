# backlogd - CLI & TUI Product Backlog Manager 

A powerful terminal-based tool for managing product backlogs with YAML storage and rich formatting. Built for developers and product managers who prefer command-line interfaces for their workflow management. 

![Logo](./static/images/backlogd_banner_v1.png)

## Features

- **Interactive CLI Shell**: Prompt shows the project (`backlogd (demo)>>`), last project remembered, history + autocomplete when `prompt_toolkit` is installed
- **Full-screen TUI**: `python backlogd.py tui` — sidebar, table/board/stats tabs, item + project management, export/import dialogs, `Ctrl+K` palette (Textual, full CLI parity)
- **Views**: Table (`items`), kanban (`board`), dashboard (`stats`), full-text search (`search`)
- **Project Management**: Create, delete and switch between multiple projects
- **Backlog Item Management**: Guided add/update with selects + autocomplete when `questionary` is installed, rich Markdown detail view
- **Rich Filtering**: Filter by priority, status, sprint, epic or assignee (comma lists), sort by priority/status/points/updated/title
- **Data Export/Import**: Export single project or `--all` to CSV/Excel, import CSV back
- **YAML Storage**: Human-readable local storage using YAML files
- **Beautiful Terminal UI**: Themed Rich output, `NO_COLOR` support, narrow-terminal friendly
- **Comprehensive Metadata**: Track story points (0-100 validated), sprints, epics, assignees and timestamps

## Installation

### Prerequisites

- Python 3.9 or higher (required by Textual for the `tui` mode)
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

Core deps are `rich`, `pyyaml`, `pandas`, `openpyxl`, `art`.
Optional but recommended for the best interactive experience
(selects, autocomplete, history): `questionary`, `prompt_toolkit` —
both are already in `requirements.txt` and degrade gracefully if missing.

### Make Executable (Optional)

```bash
chmod +x backlogd.py
```

## Quick Start

### Interactive Mode (Recommended)

Simply run the script without arguments to enter interactive mode:

```bash
python backlogd.py
# or if made executable:
./backlogd.py
```

## Interactive Mode Commands

### General Commands
- `help`, `h`, `?` - Show help information
- `exit`, `quit`, `q` - Exit the application
- `clear`, `cls` - Clear the screen
- `status` - Show current status

### Project Management
- `projects` - List all projects
- `use <project>` - Switch to a project
- `create-project <name>` - Create a new project
- `delete-project <name>` - Delete a project

### Views
- `items [all] [filters]` - Table view (hides `done` unless `all`)
- `board [filters]` / `kanban` - Kanban grouped by status
- `stats [project]` / `dashboard` - Totals, bars, top assignees/sprints/epics
- `search <text> [--status ..] [--priority ..]` / `find` - Full-text search

### Item Management
- `add <title> <description>` - Add a new item (guided prompts)
- `update <id>` - Update an item (selects keep current value)
- `delete <id>` - Delete an item
- `show <id>` - Markdown description + details grid

### Export / Import
- `export-csv [--all] [filename]` - Export project (or all combined) to CSV
- `export-xlsx [--all] [filename]` - Export project (or all combined) to Excel
- `import-csv <filename>` - Import CSV into the current project

### Filtering Options
Use these flags with `items` / `board`:
- `--priority <level>` - low, medium, high, critical (comma lists allowed)
- `--status <status>` - todo, in_progress, done, blocked (comma lists allowed)
- `--sprint <name>` - Filter by sprint
- `--epic <name>` - Filter by epic
- `--assignee <name>` - Filter by assignee
- `--search <text>` - Search id/title/description
- `--sort <key>` - priority, status, points, updated, title

## Data Structure

Each backlog item contains:
- **ID**: Auto-generated unique identifier (e.g., PROJECT-1)
- **Title**: Brief description of the item
- **Description**: Detailed description
- **Priority**: low, medium, high, or critical
- **Status**: todo, in_progress, done, or blocked
- **Sprint**: Optional sprint assignment
- **Epic**: Optional epic grouping
- **Assignee**: Optional team member assignment
- **Story Points**: Optional estimation
- **Timestamps**: Created and updated timestamps

## Usage Examples

### Interactive Mode Workflow

```bash
# Start the application
python backlogd.py

# Create and switch to a project
create-project web-app
use web-app

# Add some items
add "User Registration" "Allow users to create accounts"
add "Password Reset" "Implement forgot password functionality"

# List items
items

# Filter items
items --priority high --status todo

# Update an item
update WEB-APP-1

# Export data
export-csv web-app-backlog.csv
```

### Command Line Workflow

```bash
# Create a project
python backlogd.py project create mobile-app

# Add items with details
python backlogd.py item add mobile-app "Push Notifications" "Implement push notifications" \
  --priority high --sprint "Sprint 1" --assignee "john.doe" --points 8

# List all items in a project
python backlogd.py item list --project mobile-app

# Filter items
python backlogd.py item list --project mobile-app --priority high --status todo

# Board / stats / search
python backlogd.py item board --project mobile-app
python backlogd.py item stats --project mobile-app
python backlogd.py item search --project mobile-app push

# Update an item (points are validated 0-100)
python backlogd.py item update mobile-app MOBILE-APP-1 --status in_progress --assignee "jane.smith"

# Show item details
python backlogd.py item show mobile-app MOBILE-APP-1

# Export to Excel (or everything at once)
python backlogd.py export xlsx mobile-app --filename mobile-backlog.xlsx
python backlogd.py export csv --all --filename all-backlog.csv

# Import a CSV back (creates the project if missing)
python backlogd.py import csv mobile-app --filename mobile-backlog.csv
```

## File Structure

```
backlogd/
├── backlogd.py           # Main application (manager + classic CLI)
├── tui.py                # Full-screen Textual TUI (`tui` command)
├── tests/                # Smoke + TUI pilot tests
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── USAGE.md            # Simple usage instructions
└── database_backlogd/   # Data directory (auto-created)
    ├── project1.yaml    # Project data files
    ├── project2.yaml
    └── ...
```

## Data Storage

- **Format**: YAML files for human readability
- **Location**: `database_backlogd/` directory (auto-created)
- **Naming**: Each project gets its own `<project-name>.yaml` file
- **Backup**: Files are plain text and can be easily backed up or version controlled

## Advanced Features

### Story Points and Estimation
Track story points for sprint planning and capacity management.

### Sprint and Epic Organization
Group related items using sprints and epics for better project organization.

### Rich Filtering
Combine multiple filters to find exactly the items you need.

### Export Options
Generate reports in CSV or Excel format for stakeholders who prefer spreadsheets.
Use `--all` for one combined file with a `project` column, and `import csv`
to load an exported file back (missing projects are created, id clashes get new ids).

## Error Handling

The application includes comprehensive error handling:
- Graceful handling of missing files or corrupted data
- User-friendly error messages
- Safe file operations with backup preservation
- Input validation and sanitization

## Contributing

This is a single-file Python application designed for simplicity and portability. To contribute:

1. Fork the repository
2. Make your changes to `backlogd.py`
3. Test thoroughly in both interactive and command-line modes
4. Submit a pull request

## License

This project is open source. Please check the repository for license details.

## Troubleshooting

### Common Issues

**Missing Dependencies**
```bash
pip install -r requirements.txt
# minimal core only:
pip install rich pyyaml pandas openpyxl art
```

**Permission Issues**
```bash
chmod +x backlogd.py
```

**Data Directory Access**
The application needs write access to create the `database_backlogd/` directory in the current working directory.

### Getting Help

- Use `help` command in interactive mode
- Check command syntax with `--help` flag
- Review the examples in this README

## Roadmap

Done:
- Phase 1: theme, `board`, `stats`, `search`, responsive tables
- Phase 2: `backlogd (project)>>` prompt, guided forms, history/autocomplete,
  last-project resume, rich `show`/`status`
- Small wins: `export --all`, CSV import, 0-100 points validation, onboarding,
  `NO_COLOR`/narrow support, smoke tests, updated docs
- Phase 3: Textual TUI at full CLI parity — board/stats tabs, item modals
  (new/edit/delete/detail), project create/delete, export/import dialogs,
  `Ctrl+K` palette + registry-driven help, 23 pilot tests
- Gap close-out: sprint/epic filters, all-projects aggregate view,
  last-project resume, open-by-default filter, sidebar breakdowns,
  Created timestamp, richer statusline (31 tests total)

Potential future enhancements:
- Package split (`backlogd/` + thin `backlogd.py` shim) when single-file limits bite
- Web interface option
- Team collaboration features
- Integration with popular project management tools
- Team collaboration features
- Advanced reporting and analytics
- Custom field support