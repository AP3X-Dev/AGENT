"""Undo/revert tools for AG3NT.

Provides agent-accessible tools for undoing file modifications:
- undo_last: Undo the most recent file-modifying action
- undo_to: Revert to the state before a specific tool call
- show_undo_history: List recent file-modifying actions

Usage:
    from ag3nt_agent.revert_tools import get_revert_tools
    tools = get_revert_tools()
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.tools.revert")

# Session ID used when no explicit session context is available
_DEFAULT_SESSION = "default"


def _get_session_id() -> str:
    """Get the current session ID from environment or default."""
    import os
    return os.environ.get("AG3NT_SESSION_ID", _DEFAULT_SESSION)


@tool
def undo_last() -> str:
    """Undo the most recent file-modifying action (edit_file, write_file, apply_patch).

    Restores the workspace to the state before the last file modification.
    The undone changes can be re-applied with unrevert.

    Returns:
        Description of what was undone, including affected files.
    """
    try:
        from ag3nt_agent.revert import SessionRevert
        revert = SessionRevert.get_instance()
        session_id = _get_session_id()

        if not revert.can_undo(session_id):
            return "Nothing to undo — no file-modifying actions recorded in this session."

        result = revert.undo_last(session_id)
        if result.success:
            parts = [result.message]
            if result.files_changed:
                parts.append("\nRestored files:")
                for f in result.files_changed[:20]:
                    parts.append(f"  - {f}")
                if len(result.files_changed) > 20:
                    parts.append(f"  ... and {len(result.files_changed) - 20} more")
            return "\n".join(parts)
        return result.message

    except Exception as e:
        logger.error("undo_last failed: %s", e)
        return f"Error: {e}"


@tool
def undo_to(tool_call_id: str) -> str:
    """Revert the workspace to the state before a specific tool call.

    This undoes ALL file modifications from the specified tool call onward.
    Use show_undo_history to find the tool_call_id you want to revert to.

    Args:
        tool_call_id: The ID of the tool call to revert to.
                      All changes from this tool call onward will be undone.

    Returns:
        Description of what was reverted, including affected files.
    """
    try:
        from ag3nt_agent.revert import SessionRevert
        revert = SessionRevert.get_instance()
        session_id = _get_session_id()

        result = revert.revert_to(session_id, tool_call_id)
        if result.success:
            parts = [result.message]
            if result.files_changed:
                parts.append("\nRestored files:")
                for f in result.files_changed[:20]:
                    parts.append(f"  - {f}")
                if len(result.files_changed) > 20:
                    parts.append(f"  ... and {len(result.files_changed) - 20} more")
            return "\n".join(parts)
        return result.message

    except Exception as e:
        logger.error("undo_to failed: %s", e)
        return f"Error: {e}"


@tool
def unrevert() -> str:
    """Re-apply the most recently undone changes.

    If you just ran undo_last or undo_to and want to restore the changes
    that were reverted, use this tool.

    Returns:
        Description of what was re-applied.
    """
    try:
        from ag3nt_agent.revert import SessionRevert
        revert = SessionRevert.get_instance()
        session_id = _get_session_id()

        if not revert.can_unrevert(session_id):
            return "Nothing to unrevert — no previous undo in this session."

        result = revert.unrevert(session_id)
        if result.success:
            parts = [result.message]
            if result.files_changed:
                parts.append("\nRestored files:")
                for f in result.files_changed[:20]:
                    parts.append(f"  - {f}")
                if len(result.files_changed) > 20:
                    parts.append(f"  ... and {len(result.files_changed) - 20} more")
            return "\n".join(parts)
        return result.message

    except Exception as e:
        logger.error("unrevert failed: %s", e)
        return f"Error: {e}"


@tool
def show_undo_history(n: int = 10) -> str:
    """Show recent file-modifying actions that can be undone.

    Lists the last N file-modifying tool calls with their IDs,
    so you can use undo_to to revert to a specific point.

    Args:
        n: Number of recent actions to show (default: 10).

    Returns:
        Formatted list of recent actions with tool_call_ids.
    """
    try:
        from ag3nt_agent.revert import SessionRevert
        revert = SessionRevert.get_instance()
        session_id = _get_session_id()

        actions = revert.list_actions(session_id, n=n)
        if not actions:
            return "No file-modifying actions recorded in this session."

        can_unrevert = revert.can_unrevert(session_id)

        lines = [f"Recent file-modifying actions ({len(actions)} shown):"]
        lines.append("")
        for i, a in enumerate(actions, 1):
            files_str = ", ".join(a["files"][:3]) if a["files"] else "unknown"
            if len(a["files"]) > 3:
                files_str += f" +{len(a['files']) - 3} more"
            lines.append(
                f"  {i}. [{a['tool_call_id']}] {a['tool_name'] or 'action'}"
                f" — {files_str}"
            )
            if a["label"]:
                lines.append(f"     Label: {a['label']}")

        if can_unrevert:
            lines.append("")
            lines.append("Tip: A previous undo can be re-applied with unrevert.")

        lines.append("")
        lines.append("Use undo_to(tool_call_id='...') to revert to before a specific action.")
        return "\n".join(lines)

    except Exception as e:
        logger.error("show_undo_history failed: %s", e)
        return f"Error: {e}"


def get_revert_tools() -> list:
    """Get all revert/undo LangChain tools.

    Returns:
        List of @tool decorated revert functions.
    """
    return [undo_last, undo_to, unrevert, show_undo_history]
