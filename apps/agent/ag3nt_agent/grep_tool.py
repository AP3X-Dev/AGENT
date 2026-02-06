"""Grep content search tool for AG3NT.

This module provides powerful content search using Python's re module.
Supports regex patterns, context lines, file filtering, and multiple output modes.

Usage:
    from ag3nt_agent.grep_tool import grep_search, get_grep_tool

    # Direct search
    result = grep_search("def.*tool", path="/workspace/project", glob="*.py")

    # Get as LangChain tool
    tool = get_grep_tool()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Default limits
DEFAULT_MAX_RESULTS = 50
DEFAULT_MAX_FILE_SIZE = 1_000_000  # 1MB max file size to search
DEFAULT_MAX_LINE_LENGTH = 2000  # Truncate lines longer than this

# Binary file detection
BINARY_CHECK_BYTES = 8192  # Check first 8KB for binary content

# Patterns to always ignore (common binary/cache directories)
DEFAULT_IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
    ".eggs",
}

# Common binary file extensions to skip
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".o", ".a",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".class", ".jar", ".war",
    ".db", ".sqlite", ".sqlite3",
}


@dataclass
class GrepMatch:
    """A single grep match result."""
    file: str
    line_number: int
    content: str
    context_before: list[str]
    context_after: list[str]


def _get_workspace_root() -> Path:
    """Get the default workspace root directory.

    Returns:
        Path to ~/.ag3nt/workspace/
    """
    workspace = Path.home() / ".ag3nt" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary by looking for null bytes.

    Args:
        file_path: Path to the file

    Returns:
        True if file appears to be binary
    """
    # Check extension first
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    try:
        with open(file_path, "rb") as f:
            chunk = f.read(BINARY_CHECK_BYTES)
            # Look for null bytes which indicate binary content
            return b"\x00" in chunk
    except (OSError, IOError):
        return True  # Assume binary if we can't read


def _should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped.

    Args:
        dir_name: Name of the directory

    Returns:
        True if directory should be skipped
    """
    return dir_name in DEFAULT_IGNORE_DIRS or dir_name.startswith(".")


def _matches_glob(file_path: Path, glob_pattern: str | None) -> bool:
    """Check if a file matches a glob pattern.

    Args:
        file_path: Path to check
        glob_pattern: Glob pattern (e.g., "*.py", "*.{ts,tsx}")

    Returns:
        True if file matches pattern
    """
    if not glob_pattern:
        return True

    import fnmatch

    name = file_path.name

    # Handle brace expansion like "*.{ts,tsx}"
    if "{" in glob_pattern and "}" in glob_pattern:
        match = re.match(r"(.*)(\{[^}]+\})(.*)", glob_pattern)
        if match:
            prefix, braces, suffix = match.groups()
            options = braces[1:-1].split(",")
            return any(fnmatch.fnmatch(name, f"{prefix}{opt}{suffix}") for opt in options)

    return fnmatch.fnmatch(name, glob_pattern)


def _get_file_type_extensions(file_type: str) -> set[str]:
    """Get file extensions for a given file type.

    Args:
        file_type: Type name like "py", "js", "ts", etc.

    Returns:
        Set of extensions including the dot
    """
    type_map = {
        "py": {".py", ".pyi", ".pyw"},
        "python": {".py", ".pyi", ".pyw"},
        "js": {".js", ".mjs", ".cjs"},
        "javascript": {".js", ".mjs", ".cjs"},
        "ts": {".ts", ".tsx", ".mts", ".cts"},
        "typescript": {".ts", ".tsx", ".mts", ".cts"},
        "jsx": {".jsx"},
        "tsx": {".tsx"},
        "java": {".java"},
        "c": {".c", ".h"},
        "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".c++", ".h++"},
        "rust": {".rs"},
        "go": {".go"},
        "rb": {".rb", ".rake", ".gemspec"},
        "ruby": {".rb", ".rake", ".gemspec"},
        "php": {".php"},
        "swift": {".swift"},
        "kt": {".kt", ".kts"},
        "kotlin": {".kt", ".kts"},
        "scala": {".scala"},
        "cs": {".cs"},
        "csharp": {".cs"},
        "sh": {".sh", ".bash", ".zsh"},
        "shell": {".sh", ".bash", ".zsh"},
        "yaml": {".yaml", ".yml"},
        "yml": {".yaml", ".yml"},
        "json": {".json"},
        "xml": {".xml"},
        "html": {".html", ".htm"},
        "css": {".css"},
        "scss": {".scss", ".sass"},
        "md": {".md", ".markdown"},
        "markdown": {".md", ".markdown"},
        "sql": {".sql"},
        "graphql": {".graphql", ".gql"},
        "toml": {".toml"},
        "ini": {".ini", ".cfg"},
        "dockerfile": {"Dockerfile", ".dockerfile"},
    }

    return type_map.get(file_type.lower(), {f".{file_type}"})


def _maybe_truncate_result(result: dict[str, Any]) -> dict[str, Any]:
    """Apply smart truncation to grep results if they are very large.

    Serializes the match content and checks if it exceeds truncation
    thresholds.  If so, saves full results to disk and trims the
    returned matches.
    """
    try:
        from ag3nt_agent.output_truncation import maybe_truncate

        # Serialize matches to estimate size
        import json
        serialized = json.dumps(result["matches"], default=str)

        _, was_truncated, saved_path = maybe_truncate(serialized)
        if was_truncated and saved_path:
            result["truncated"] = True
            result["full_output_path"] = saved_path
            result["truncation_note"] = (
                f"Results truncated. Full output saved to {saved_path}. "
                "Use read_file to examine the full results."
            )
    except ImportError:
        pass  # output_truncation not available

    return result


def grep_search(
    pattern: str,
    path: str | None = None,
    glob: str | None = None,
    file_type: str | None = None,
    context_lines: int = 0,
    context_before: int | None = None,
    context_after: int | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    case_insensitive: bool = False,
    multiline: bool = False,
    output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches",
    head_limit: int = 0,
    offset: int = 0,
) -> dict[str, Any]:
    """Search file contents for a regex pattern.

    Args:
        pattern: Regex pattern to search for
        path: File or directory to search (default: workspace root)
        glob: Filter files by glob pattern (e.g., "*.py", "*.{ts,tsx}")
        file_type: Filter by file type (e.g., "py", "js", "ts")
        context_lines: Lines of context before and after match
        context_before: Lines before match (overrides context_lines)
        context_after: Lines after match (overrides context_lines)
        max_results: Maximum matches to return (default: 50)
        case_insensitive: Ignore case when matching (default: False)
        multiline: Enable multiline mode for patterns spanning lines
        output_mode: "files_with_matches", "content", or "count"
        head_limit: Limit output to first N entries (0 = unlimited)
        offset: Skip first N entries before applying head_limit

    Returns:
        Dictionary with matches based on output_mode:
        - files_with_matches: List of file paths with matches
        - content: List of matches with line content and context
        - count: Count of matches per file
    """
    # Determine search root
    if path:
        if path.startswith("/workspace/"):
            search_root = _get_workspace_root() / path[11:]
        elif path.startswith("/"):
            search_root = _get_workspace_root() / path[1:]
        else:
            search_root = Path(path)
    else:
        search_root = _get_workspace_root()

    # Handle single file
    if search_root.is_file():
        files_to_search = [search_root]
        search_root = search_root.parent
    elif search_root.is_dir():
        files_to_search = None  # Will walk directory
    else:
        return {
            "matches": [],
            "count": 0,
            "error": f"Path does not exist: {search_root}",
        }

    # Compile regex
    flags = re.IGNORECASE if case_insensitive else 0
    if multiline:
        flags |= re.MULTILINE | re.DOTALL

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return {
            "matches": [],
            "count": 0,
            "error": f"Invalid regex pattern: {e}",
        }

    # Determine context lines
    ctx_before = context_before if context_before is not None else context_lines
    ctx_after = context_after if context_after is not None else context_lines

    # Get file type extensions
    type_extensions = _get_file_type_extensions(file_type) if file_type else None

    # Collect results
    matches: list[dict[str, Any]] = []
    files_with_matches: set[str] = set()
    match_counts: dict[str, int] = {}
    total_matches = 0

    def process_file(file_path: Path) -> None:
        nonlocal total_matches

        # Skip binary files
        if _is_binary_file(file_path):
            return

        # Check file type
        if type_extensions and file_path.suffix.lower() not in type_extensions:
            if file_path.name not in type_extensions:  # For Dockerfile etc.
                return

        # Check glob pattern
        if not _matches_glob(file_path, glob):
            return

        # Check file size
        try:
            if file_path.stat().st_size > DEFAULT_MAX_FILE_SIZE:
                logger.debug(f"Skipping large file: {file_path}")
                return
        except OSError:
            return

        # Read and search file
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError) as e:
            logger.debug(f"Failed to read {file_path}: {e}")
            return

        # Get relative path
        try:
            rel_path = str(file_path.relative_to(search_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(file_path).replace("\\", "/")

        lines = content.splitlines()
        file_matches = 0

        if multiline:
            # For multiline patterns, search entire content
            for match in regex.finditer(content):
                if total_matches >= max_results * 2:  # Get extra for offset
                    break

                file_matches += 1
                total_matches += 1
                files_with_matches.add(rel_path)

                if output_mode == "content":
                    # Calculate line number from match position
                    line_num = content[:match.start()].count("\n") + 1
                    matched_text = match.group()

                    # Truncate if too long
                    if len(matched_text) > DEFAULT_MAX_LINE_LENGTH:
                        matched_text = matched_text[:DEFAULT_MAX_LINE_LENGTH] + "..."

                    matches.append({
                        "file": rel_path,
                        "line": line_num,
                        "content": matched_text,
                        "match_start": match.start(),
                        "match_end": match.end(),
                    })
        else:
            # Search line by line
            for i, line in enumerate(lines, start=1):
                if total_matches >= max_results * 2:  # Get extra for offset
                    break

                if regex.search(line):
                    file_matches += 1
                    total_matches += 1
                    files_with_matches.add(rel_path)

                    if output_mode == "content":
                        # Truncate line if too long
                        content_line = line
                        if len(content_line) > DEFAULT_MAX_LINE_LENGTH:
                            content_line = content_line[:DEFAULT_MAX_LINE_LENGTH] + "..."

                        # Get context
                        before = []
                        after = []
                        if ctx_before > 0:
                            start = max(0, i - 1 - ctx_before)
                            before = lines[start:i - 1]
                        if ctx_after > 0:
                            end = min(len(lines), i + ctx_after)
                            after = lines[i:end]

                        matches.append({
                            "file": rel_path,
                            "line": i,
                            "content": content_line,
                            "context_before": before,
                            "context_after": after,
                        })

        if file_matches > 0:
            match_counts[rel_path] = file_matches

    # Process files
    if files_to_search:
        for f in files_to_search:
            process_file(f)
    else:
        for root, dirs, files in os.walk(search_root):
            # Filter directories in-place to prevent descent
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            for filename in files:
                if total_matches >= max_results * 2:
                    break
                process_file(Path(root) / filename)

    # Apply offset and head_limit
    if output_mode == "files_with_matches":
        result_list = sorted(files_with_matches)
        if offset:
            result_list = result_list[offset:]
        if head_limit > 0:
            result_list = result_list[:head_limit]

        return {
            "matches": result_list,
            "count": len(result_list),
            "total_files": len(files_with_matches),
            "pattern": pattern,
            "search_root": str(search_root),
        }

    elif output_mode == "content":
        if offset:
            matches = matches[offset:]
        if head_limit > 0:
            matches = matches[:head_limit]
        else:
            matches = matches[:max_results]

        result = {
            "matches": matches,
            "count": len(matches),
            "total_matches": total_matches,
            "pattern": pattern,
            "search_root": str(search_root),
        }

        # Smart truncation for large content results
        result = _maybe_truncate_result(result)
        return result

    else:  # count
        count_list = [{"file": f, "count": c} for f, c in sorted(match_counts.items())]
        if offset:
            count_list = count_list[offset:]
        if head_limit > 0:
            count_list = count_list[:head_limit]

        return {
            "matches": count_list,
            "count": len(count_list),
            "total_matches": total_matches,
            "pattern": pattern,
            "search_root": str(search_root),
        }


@tool
def grep_tool(
    pattern: str,
    path: str | None = None,
    glob: str | None = None,
    file_type: str | None = None,
    context_lines: int = 0,
    case_insensitive: bool = False,
    multiline: bool = False,
    output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """Search file contents for a regex pattern.

    A powerful search tool for finding text patterns in files. Supports
    full regex syntax, file filtering, and multiple output modes.

    Args:
        pattern: Regex pattern to search for (e.g., "def.*tool", "class\\s+\\w+")
        path: File or directory to search (default: workspace root)
        glob: Filter files by glob pattern (e.g., "*.py", "*.{ts,tsx}")
        file_type: Filter by file type (e.g., "py", "js", "ts", "rust", "go")
        context_lines: Lines of context before and after each match
        case_insensitive: Ignore case when matching (default: False)
        multiline: Enable multiline mode for patterns spanning lines
        output_mode: Output format:
            - "files_with_matches": Just file paths (default)
            - "content": Full match content with line numbers
            - "count": Match counts per file
        max_results: Maximum matches to return (default: 50)

    Returns:
        Dictionary with matches based on output_mode.

    Examples:
        # Find function definitions in Python files
        grep_tool("def \\w+\\(", file_type="py", output_mode="content")

        # Find all files containing "TODO"
        grep_tool("TODO", output_mode="files_with_matches")

        # Count occurrences of "import" per file
        grep_tool("^import ", file_type="py", output_mode="count")

        # Find class definitions with context
        grep_tool("class \\w+", context_lines=2, output_mode="content")

        # Case-insensitive search
        grep_tool("error", case_insensitive=True, output_mode="content")
    """
    return grep_search(
        pattern,
        path=path,
        glob=glob,
        file_type=file_type,
        context_lines=context_lines,
        case_insensitive=case_insensitive,
        multiline=multiline,
        output_mode=output_mode,
        max_results=max_results,
    )


def get_grep_tool():
    """Get the grep search tool for the agent.

    Returns:
        LangChain tool for grep content search
    """
    return grep_tool
