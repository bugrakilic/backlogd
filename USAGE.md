# Usage of backlogd

### Full-screen TUI (Phase 3, needs `textual`)
python backlogd.py tui --project test-app   # full TUI, `q` quits
backlogd (test-app)>> tui                   # launch from interactive mode

Views: `1` table, `2` board, `3` stats. Filter bar narrows table + board
(text, status, priority, sprint, epic — status defaults to `open`);
`s` cycles sort; `tab` cycles focus. Sidebar top entry aggregates all projects.
Items: `n` new, `e` edit, `d` delete (confirm), `enter` details,
`space` advance status (todo -> doing -> done).
Projects: sidebar `enter` switches, `N` new, `D` delete (confirm).
Data: `X` export (project/all, csv/xlsx), `I` import CSV.
`/` focuses filter (`enter`/`esc` leaves it, `esc` again clears),
`ctrl+k` command palette covers every operation, `?` help, `q` quit.

Prompt shows the active project: `backlogd>>` or `backlogd (demo)>>`.
Last used project is remembered (`~/.backlogdrc`). History lives in
`~/.backlogd_history` when `prompt_toolkit` is installed.

### Project management
backlogd>> create-project test-app      # Create new project
backlogd>> use test-app                 # Switch (prompt becomes backlogd (test-app)>>)
backlogd (test-app)>> projects          # List all projects
backlogd (test-app)>> delete-project old-project  # Delete a project

### Views (work on current project)
backlogd (test-app)>> items                          # Table (hides done)
backlogd (test-app)>> items all                      # Table incl. done
backlogd (test-app)>> items --priority high          # Filter by priority
backlogd (test-app)>> items --status todo --sprint Sprint-1  # Multiple filters
backlogd (test-app)>> items --assignee jane --sort points    # Assignee + sort
backlogd (test-app)>> board                          # Kanban grouped by status
backlogd (test-app)>> board --sprint Sprint-1        # Filtered kanban
backlogd (test-app)>> stats                          # Dashboard with bars
backlogd (test-app)>> search login                   # Full-text search
backlogd (test-app)>> search login --status todo,in_progress

### Item management
backlogd (test-app)>> add "User Login" "Auth system" # Add (guided prompts)
backlogd (test-app)>> update TEST-APP-1              # Update (selects keep current)
backlogd (test-app)>> show TEST-APP-1                # Markdown + details grid
backlogd (test-app)>> delete TEST-APP-1              # Delete with confirm

### Export / import
backlogd (test-app)>> export-csv                     # Export project to CSV
backlogd (test-app)>> export-csv --all               # Export ALL projects, one file
backlogd (test-app)>> export-xlsx myfile.xlsx        # Export project to Excel
backlogd (test-app)>> import-csv backup.csv          # Import into current project
backlogd (test-app)>> import-csv new-proj backup.csv # Import (creates project)

### Utility
backlogd (test-app)>> status                         # Mini-dashboard
backlogd (test-app)>> help                           # Show help
backlogd (test-app)>> clear                          # Clear screen
backlogd (test-app)>> exit                           # Exit application

### Notes
- Filters accept commas: `--priority high,critical --status todo,in_progress,blocked`
- `--sort priority|status|points|updated|title`
- Story points are 0-100 everywhere (CLI rejects others, interactive warns)
- `NO_COLOR=1` disables colors; narrow terminals auto-hide sprint/epic columns
