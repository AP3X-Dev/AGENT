---
name: file-manager
description: Open files with default applications, reveal files in explorer/finder, and search for files on the system. Requires approval for operations outside workspace.
version: "1.0.0"
tags:
  - files
  - desktop
  - device
  - explorer
triggers:
  - "open file"
  - "open document"
  - "show in explorer"
  - "reveal in finder"
  - "find file"
  - "search files"
  - "open folder"
entrypoints:
  open:
    script: scripts/file_ops.py open
    description: Open a file with its default application
  reveal:
    script: scripts/file_ops.py reveal
    description: Show a file in Explorer/Finder
  search:
    script: scripts/file_ops.py search
    description: Search for files by name or pattern
  info:
    script: scripts/file_ops.py info
    description: Get detailed file information
required_permissions:
  - file_read
  - file_execute
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: device-integration
  node_capability: file_management
---

# File Manager Skill

This skill provides file management operations on the local system. It can open files, reveal them in the file explorer, and search for files.

## ⚠️ Security Note

Operations on files **outside the workspace** require user approval. The agent will pause and ask for confirmation before:
- Opening files outside the current project
- Revealing files in external locations
- Executing any file operations on system directories

## When to Use

- User asks to "open" a document, image, or file
- User wants to "show in explorer" or "reveal in finder"
- User needs to find a file on their system
- User asks about file details (size, dates, type)

## Available Commands

### Open File
Opens a file with its default application.

```bash
python scripts/file_ops.py open "/path/to/document.pdf"
```

**Examples:**
- Open a PDF: `open ~/Documents/report.pdf`
- Open an image: `open ./screenshot.png`
- Open a URL: `open https://example.com`

### Reveal in Explorer/Finder
Shows the file in the system file manager, with the file selected.

```bash
python scripts/file_ops.py reveal "/path/to/file.txt"
```

### Search for Files
Search for files by name or pattern.

```bash
python scripts/file_ops.py search "*.pdf" --location ~/Documents
python scripts/file_ops.py search "report" --location ~/Documents --recursive
```

### Get File Info
Get detailed information about a file.

```bash
python scripts/file_ops.py info "/path/to/file.txt"
```

Returns: size, creation date, modification date, file type, permissions.

## Platform Support

| Operation | Windows | macOS | Linux |
|-----------|---------|-------|-------|
| Open file | ✅ `os.startfile` | ✅ `open` | ✅ `xdg-open` |
| Reveal | ✅ `explorer /select` | ✅ `open -R` | ✅ `xdg-open` (folder) |
| Search | ✅ `dir /s` | ✅ `mdfind` | ✅ `find` |

## Notes

- File paths can be absolute or relative to current directory
- Use forward slashes `/` or escaped backslashes `\\` on Windows
- URLs are also supported for the `open` command
- Search is case-insensitive on Windows and macOS

