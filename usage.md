# Usage of backlogd

### Project management
backlogd[no project]>> projects                    # List all projects
backlogd[no project]>> create-project test-app      # Create new project
backlogd[no project]>> use test-app                 # Switch to project
backlogd[test-app]>> delete-project old-project     # Delete a project

### Item management (works on current project)
backlogd[test-app]>> items                          # List all items
backlogd[test-app]>> items --priority high          # Filter by priority
backlogd[test-app]>> items --status todo --sprint Sprint-1  # Multiple filters
backlogd[test-app]>> add "User Login" "Auth system" # Add item (interactive)
backlogd[test-app]>> update test-app-1               # Update item (interactive)
backlogd[test-app]>> show test-app-1                # Show item details
backlogd[test-app]>> delete test-app-1              # Delete item

### Export
backlogd[test-app]>> export-csv                     # Export to CSV
backlogd[test-app]>> export-xlsx myfile.xlsx       # Export to Excel

### Utility
backlogd[test-app]>> status                         # Show current status
backlogd[test-app]>> help                           # Show help
backlogd[test-app]>> clear                          # Clear screen
backlogd[test-app]>> exit                           # Exit application