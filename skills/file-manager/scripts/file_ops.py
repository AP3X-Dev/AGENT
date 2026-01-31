#!/usr/bin/env python3
"""
File Operations Script for AG3NT.

Provides platform-specific file management operations:
- Open files with default application
- Reveal files in Explorer/Finder
- Search for files
- Get file information

Usage:
    python file_ops.py open <path>
    python file_ops.py reveal <path>
    python file_ops.py search <pattern> [--location <dir>] [--recursive]
    python file_ops.py info <path>
"""

import argparse
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def get_platform() -> str:
    """Get the current platform: 'windows', 'darwin', or 'linux'."""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "darwin"
    else:
        return "linux"


def open_file(path: str) -> dict[str, Any]:
    """Open a file with its default application."""
    # Handle URLs
    if path.startswith(("http://", "https://", "file://")):
        import webbrowser
        webbrowser.open(path)
        return {"success": True, "message": f"Opened URL: {path}"}

    # Resolve path
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    plat = get_platform()

    try:
        if plat == "windows":
            os.startfile(str(file_path))
        elif plat == "darwin":
            subprocess.run(["open", str(file_path)], check=True)
        else:  # Linux
            subprocess.run(["xdg-open", str(file_path)], check=True)

        return {"success": True, "message": f"Opened: {file_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reveal_file(path: str) -> dict[str, Any]:
    """Reveal a file in the system file manager."""
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    plat = get_platform()

    try:
        if plat == "windows":
            # explorer /select, highlights the file
            subprocess.run(["explorer", "/select,", str(file_path)], check=True)
        elif plat == "darwin":
            # open -R reveals in Finder
            subprocess.run(["open", "-R", str(file_path)], check=True)
        else:  # Linux
            # xdg-open on the parent directory
            parent = file_path.parent
            subprocess.run(["xdg-open", str(parent)], check=True)

        return {"success": True, "message": f"Revealed: {file_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(pattern: str, location: str = ".", recursive: bool = True) -> dict[str, Any]:
    """Search for files matching a pattern."""
    search_path = Path(location).expanduser().resolve()

    if not search_path.exists():
        return {"success": False, "error": f"Location not found: {search_path}"}

    try:
        if recursive:
            matches = list(search_path.rglob(pattern))
        else:
            matches = list(search_path.glob(pattern))

        # Limit results
        max_results = 50
        truncated = len(matches) > max_results
        matches = matches[:max_results]

        results = [str(m) for m in matches]

        return {
            "success": True,
            "pattern": pattern,
            "location": str(search_path),
            "count": len(results),
            "truncated": truncated,
            "files": results,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_file_info(path: str) -> dict[str, Any]:
    """Get detailed information about a file."""
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        stat = file_path.stat()

        info = {
            "success": True,
            "path": str(file_path),
            "name": file_path.name,
            "is_file": file_path.is_file(),
            "is_directory": file_path.is_dir(),
            "size_bytes": stat.st_size,
            "size_human": format_size(stat.st_size),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
        }

        # Add extension info for files
        if file_path.is_file():
            info["extension"] = file_path.suffix
            info["mime_type"] = guess_mime_type(file_path)

        return info
    except Exception as e:
        return {"success": False, "error": str(e)}


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def guess_mime_type(path: Path) -> str:
    """Guess the MIME type of a file."""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def format_result(result: dict[str, Any]) -> str:
    """Format result for human-readable output."""
    if not result.get("success"):
        return f"❌ Error: {result.get('error', 'Unknown error')}"

    if "files" in result:
        # Search results
        lines = [f"🔍 Found {result['count']} files matching '{result['pattern']}'"]
        if result.get("truncated"):
            lines.append("  (showing first 50 results)")
        lines.append("")
        for f in result["files"]:
            lines.append(f"  📄 {f}")
        return "\n".join(lines)

    if "is_file" in result:
        # File info
        lines = [
            f"📄 File Information: {result['name']}",
            "=" * 40,
            f"  Path: {result['path']}",
            f"  Type: {'File' if result['is_file'] else 'Directory'}",
            f"  Size: {result['size_human']}",
            f"  Created: {result['created']}",
            f"  Modified: {result['modified']}",
        ]
        if result.get("extension"):
            lines.append(f"  Extension: {result['extension']}")
        if result.get("mime_type"):
            lines.append(f"  MIME Type: {result['mime_type']}")
        return "\n".join(lines)

    # Generic success message
    return f"✅ {result.get('message', 'Operation completed')}"


def main():
    parser = argparse.ArgumentParser(description="File operations for AG3NT")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Open command
    open_parser = subparsers.add_parser("open", help="Open a file")
    open_parser.add_argument("path", help="File path or URL to open")

    # Reveal command
    reveal_parser = subparsers.add_parser("reveal", help="Reveal file in explorer")
    reveal_parser.add_argument("path", help="File path to reveal")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for files")
    search_parser.add_argument("pattern", help="Search pattern (e.g., *.pdf)")
    search_parser.add_argument("--location", "-l", default=".", help="Directory to search")
    search_parser.add_argument("--recursive", "-r", action="store_true", default=True)
    search_parser.add_argument("--no-recursive", dest="recursive", action="store_false")

    # Info command
    info_parser = subparsers.add_parser("info", help="Get file information")
    info_parser.add_argument("path", help="File path")

    # JSON output flag
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == "open":
        result = open_file(args.path)
    elif args.command == "reveal":
        result = reveal_file(args.path)
    elif args.command == "search":
        result = search_files(args.pattern, args.location, args.recursive)
    elif args.command == "info":
        result = get_file_info(args.path)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)

    # Output
    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))

    # Exit with error code if failed
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()

