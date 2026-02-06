"""Multi-edit tool for AG3NT.

Applies N sequential edits to a single file in one tool call, reducing
round-trips for multi-point edits. Each edit sees the result of the
previous one. Uses the fuzzy edit engine for tolerant matching.

Usage:
    from ag3nt_agent.multi_edit_tool import get_multi_edit_tool

    tool = get_multi_edit_tool()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from ag3nt_agent.fuzzy_edit import fuzzy_replace

logger = logging.getLogger("ag3nt.multi_edit")


@tool
def multi_edit(
    file_path: str,
    edits: list[dict[str, str]],
) -> dict[str, Any]:
    """Apply multiple sequential edits to a single file.

    Each edit is applied in order, and each subsequent edit sees the result
    of the previous one. Uses fuzzy matching for tolerant string replacement.

    If any edit fails, processing stops and the file is NOT modified.
    Only when all edits succeed is the file written back to disk.

    Args:
        file_path: Absolute or workspace-relative path to the file to edit.
        edits: List of edit operations, each a dict with:
            - old_string: The text to find and replace
            - new_string: The replacement text

    Returns:
        Dictionary with:
            - success: bool — whether all edits were applied
            - results: list of per-edit results with index, status, strategy
            - edits_applied: number of edits successfully applied
            - edits_total: total number of edits requested

    Examples:
        # Rename a variable and update its type annotation
        multi_edit(
            file_path="/workspace/app.py",
            edits=[
                {"old_string": "user_name: str", "new_string": "username: str"},
                {"old_string": "print(user_name)", "new_string": "print(username)"},
            ]
        )
    """
    if not edits:
        return {
            "success": False,
            "error": "No edits provided",
            "results": [],
            "edits_applied": 0,
            "edits_total": 0,
        }

    # Resolve file path
    path = Path(file_path)
    if not path.is_absolute():
        workspace = Path.home() / ".ag3nt" / "workspace"
        path = workspace / file_path

    if not path.exists():
        return {
            "success": False,
            "error": f"File not found: {file_path}",
            "results": [],
            "edits_applied": 0,
            "edits_total": len(edits),
        }

    if not path.is_file():
        return {
            "success": False,
            "error": f"Not a file: {file_path}",
            "results": [],
            "edits_applied": 0,
            "edits_total": len(edits),
        }

    # Read current content
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {
            "success": False,
            "error": f"Failed to read file: {e}",
            "results": [],
            "edits_applied": 0,
            "edits_total": len(edits),
        }

    # Apply edits sequentially
    results: list[dict[str, Any]] = []

    for i, edit in enumerate(edits):
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")

        if not old_string:
            results.append({
                "index": i,
                "status": "error",
                "error": "old_string is empty",
            })
            return {
                "success": False,
                "results": results,
                "edits_applied": i,
                "edits_total": len(edits),
            }

        result = fuzzy_replace(content, old_string, new_string)

        if isinstance(result, str):
            # Error — fuzzy_replace returns error string on failure
            results.append({
                "index": i,
                "status": "error",
                "error": result,
            })
            return {
                "success": False,
                "results": results,
                "edits_applied": i,
                "edits_total": len(edits),
            }

        new_content, occurrences, strategy = result
        content = new_content
        results.append({
            "index": i,
            "status": "ok",
            "strategy": strategy,
            "occurrences": occurrences,
        })
        logger.debug(
            "Edit %d/%d applied via %s (%d occurrence(s))",
            i + 1, len(edits), strategy, occurrences,
        )

    # All edits succeeded — write file
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return {
            "success": False,
            "error": f"Failed to write file: {e}",
            "results": results,
            "edits_applied": len(edits),
            "edits_total": len(edits),
        }

    logger.info("multi_edit: %d edit(s) applied to %s", len(edits), file_path)

    return {
        "success": True,
        "results": results,
        "edits_applied": len(edits),
        "edits_total": len(edits),
    }


def get_multi_edit_tool():
    """Get the multi_edit tool for the agent.

    Returns:
        LangChain tool for multi-edit operations
    """
    return multi_edit
