"""Glob file pattern search tool for AG3NT.

This module provides fast file pattern matching using Python's pathlib.
Supports glob patterns like "**/*.py", "src/**/*.tsx", etc.

Usage:
    from ag3nt_agent.glob_tool import glob_search, get_glob_tool

    # Direct search
    result = glob_search("**/*.py", path="/workspace/project")

    # Get as LangChain tool
    tool = get_glob_tool()
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Default maximum results to prevent overwhelming output
DEFAULT_MAX_RESULTS = 100

# Patterns to always ignore (common binary/cache directories)
DEFAULT_IGNORE_PATTERNS = [
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
    "*.egg-info",
    ".eggs",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.exe",
]


def _get_workspace_root() -> Path:
    """Get the default workspace root directory.

    Returns:
        Path to ~/.ag3nt/workspace/
    """
    workspace = Path.home() / ".ag3nt" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _load_gitignore_patterns(root: Path) -> list[str]:
    """Load patterns from .gitignore file if it exists.

    Args:
        root: Root directory to search for .gitignore

    Returns:
        List of gitignore patterns
    """
    gitignore_path = root / ".gitignore"
    patterns = []

    if gitignore_path.exists():
        try:
            with open(gitignore_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception as e:
            logger.warning(f"Failed to read .gitignore: {e}")

    return patterns


def _should_ignore(path: Path, root: Path, ignore_patterns: list[str]) -> bool:
    """Check if a path should be ignored based on patterns.

    Args:
        path: Path to check
        root: Root directory for relative path calculation
        ignore_patterns: List of patterns to check against

    Returns:
        True if path should be ignored
    """
    try:
        rel_path = path.relative_to(root)
        rel_str = str(rel_path).replace("\\", "/")  # Normalize path separators
    except ValueError:
        rel_str = str(path).replace("\\", "/")

    # Check each part of the path
    parts = rel_str.split("/")

    for pattern in ignore_patterns:
        # Handle directory patterns (ending with /)
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            if any(fnmatch.fnmatch(part, dir_pattern) for part in parts):
                return True
        else:
            # Match against full path or any component
            if fnmatch.fnmatch(rel_str, pattern):
                return True
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True

    return False


def glob_search(
    pattern: str,
    path: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    respect_gitignore: bool = True,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Find files matching a glob pattern.

    Searches for files matching the given glob pattern, sorted by modification
    time (most recent first). Supports recursive patterns with **.

    Args:
        pattern: Glob pattern to match (e.g., "**/*.py", "src/**/*.tsx")
        path: Directory to search in (default: workspace root)
        max_results: Maximum number of files to return (default: 100)
        respect_gitignore: Whether to respect .gitignore patterns (default: True)
        include_hidden: Whether to include hidden files/dirs (default: False)

    Returns:
        Dictionary containing:
        - matches: List of matching file paths (relative to search root)
        - count: Number of matches found
        - truncated: Whether results were truncated
        - search_root: The directory that was searched
    """
    # Determine search root
    if path:
        # Handle both virtual paths (/workspace/...) and real paths
        if path.startswith("/workspace/"):
            search_root = _get_workspace_root() / path[11:]  # Strip /workspace/
        elif path.startswith("/"):
            search_root = _get_workspace_root() / path[1:]  # Strip leading /
        else:
            search_root = Path(path)
    else:
        search_root = _get_workspace_root()

    # Ensure search root exists
    if not search_root.exists():
        return {
            "matches": [],
            "count": 0,
            "truncated": False,
            "search_root": str(search_root),
            "error": f"Directory does not exist: {search_root}",
        }

    if not search_root.is_dir():
        return {
            "matches": [],
            "count": 0,
            "truncated": False,
            "search_root": str(search_root),
            "error": f"Path is not a directory: {search_root}",
        }

    # Build ignore patterns
    ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
    if respect_gitignore:
        ignore_patterns.extend(_load_gitignore_patterns(search_root))

    # Perform glob search
    matches: list[tuple[Path, float]] = []

    try:
        for match in search_root.glob(pattern):
            # Skip directories (only return files)
            if match.is_dir():
                continue

            # Skip hidden files if not requested
            if not include_hidden and any(part.startswith(".") for part in match.parts):
                # Allow if explicitly searching for hidden files
                if not pattern.startswith("."):
                    continue

            # Skip ignored patterns
            if _should_ignore(match, search_root, ignore_patterns):
                continue

            # Get modification time for sorting
            try:
                mtime = match.stat().st_mtime
            except OSError:
                mtime = 0

            matches.append((match, mtime))
    except Exception as e:
        logger.error(f"Glob search error: {e}")
        return {
            "matches": [],
            "count": 0,
            "truncated": False,
            "search_root": str(search_root),
            "error": f"Search failed: {e}",
        }

    # Sort by modification time (most recent first)
    matches.sort(key=lambda x: x[1], reverse=True)

    # Check if truncated
    total_count = len(matches)
    truncated = total_count > max_results

    # Limit results
    matches = matches[:max_results]

    # Convert to relative paths
    result_paths = []
    for match_path, _ in matches:
        try:
            rel_path = match_path.relative_to(search_root)
            result_paths.append(str(rel_path).replace("\\", "/"))
        except ValueError:
            result_paths.append(str(match_path).replace("\\", "/"))

    return {
        "matches": result_paths,
        "count": len(result_paths),
        "total_found": total_count,
        "truncated": truncated,
        "search_root": str(search_root),
        "pattern": pattern,
    }


@tool
def glob_tool(
    pattern: str,
    path: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """Find files matching a glob pattern.

    Fast file pattern matching tool that works with any codebase size.
    Returns matching file paths sorted by modification time (most recent first).

    Use this tool when you need to find files by name patterns.

    Args:
        pattern: Glob pattern to match files against (e.g., "**/*.py", "src/**/*.tsx")
        path: Directory to search in (default: workspace root). Use virtual paths
              like "/workspace/project" or relative paths.
        max_results: Maximum number of files to return (default: 100)

    Returns:
        Dictionary with matching files, count, and search metadata.

    Examples:
        # Find all Python files
        glob_tool("**/*.py")

        # Find TypeScript files in src directory
        glob_tool("**/*.tsx", path="/workspace/myproject/src")

        # Find config files
        glob_tool("**/config.*")

        # Find test files
        glob_tool("**/test_*.py")
    """
    return glob_search(pattern, path=path, max_results=max_results)


def get_glob_tool():
    """Get the glob search tool for the agent.

    Returns:
        LangChain tool for glob file search
    """
    return glob_tool
