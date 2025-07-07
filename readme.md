# backlogd - Product Backlog Manager for CLI

A powerful terminal-based tool for managing product backlogs with YAML storage and rich formatting. Built for developers and product managers who prefer command-line interfaces for their workflow management. 

![Logo](./static/images/backlogd_banner_v1.png)

## Demo 

![Demo of my application](./static/images/backlogd_gif_v1.gif)

## Features

- **Interactive CLI Shell**: Full-featured interactive mode with command completion and help
- **Project Management**: Create, delete and switch between multiple projects
- **Backlog Item Management**: Add, update, delete and view backlog items with rich details
- **Rich Filtering**: Filter items by priority, status, sprint, epic or assignee
- **Data Export**: Export to CSV or Excel formats
- **YAML Storage**: Human-readable local storage using YAML files
- **Beautiful Terminal UI**: Rich formatting with colors, tables and panels
- **Comprehensive Metadata**: Track story points, sprints, epics, assignees and timestamps

## Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

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

### Item Management
- `items [filters]` - List items in current project
- `add <title> <description>` - Add a new item (interactive)
- `update <id>` - Update an item (interactive)
- `delete <id>` - Delete an item
- `show <id>` - Show detailed item information

### Export
- `export-csv [filename]` - Export current project to CSV
- `export-xlsx [filename]` - Export current project to Excel

### Filtering Options
Use these flags with the `items` command:
- `--priority <level>` - Filter by priority (low, medium, high, critical)
- `--status <status>` - Filter by status (todo, in_progress, done, blocked)
- `--sprint <name>` - Filter by sprint
- `--epic <name>` - Filter by epic
- `--assignee <name>` - Filter by assignee

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

# Update an item
python backlogd.py item update mobile-app MOBILE-APP-1 --status in_progress --assignee "jane.smith"

# Show item details
python backlogd.py item show mobile-app MOBILE-APP-1

# Export to Excel
python backlogd.py export xlsx mobile-app --filename mobile-backlog.xlsx
```

## File Structure

```
backlogd/
├── backlogd.py           # Main application
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

Potential future enhancements:
- Integration with popular project management tools
- Web interface option
- Team collaboration features
- Advanced reporting and analytics
- Custom field support
- Import from other backlog tools