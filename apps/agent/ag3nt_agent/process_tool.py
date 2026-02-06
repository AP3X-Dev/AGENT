"""Background process session manager for AG3NT.

Companion to exec_tool.py - provides session management actions for
background processes including listing, polling, log viewing, input,
key sending, killing, and cleanup.

Usage:
    from ag3nt_agent.process_tool import get_process_tool

    tool = get_process_tool()
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.process")


@tool
def process_tool(
    action: Literal["list", "poll", "log", "write", "send_keys", "kill", "clear", "remove"],
    session_id: str | None = None,
    input_text: str | None = None,
    keys: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    """Manage background process sessions started by exec_command.

    Provides actions to interact with running and finished background processes.

    Args:
        action: The action to perform:
            - list: Show all running and finished sessions
            - poll: Get new output since last poll for a session
            - log: Get line-based output slice from a session
            - write: Write text to a session's stdin
            - send_keys: Send named keys (Enter, Ctrl-C, Up, Down, etc.)
            - kill: Kill a running session (SIGKILL)
            - clear: Reset a session's output buffer
            - remove: Delete a session from the registry
        session_id: Target session ID (required for all actions except list)
        input_text: Text to write to stdin (for 'write' action)
        keys: Named key to send (for 'send_keys' action).
              Supported: Enter, Tab, Escape, Ctrl-C, Ctrl-D, Ctrl-Z,
              Ctrl-L, Up, Down, Left, Right, Backspace, Delete
        offset: Line offset for 'log' action (default: 0)
        limit: Max lines for 'log' action (default: all)

    Returns:
        Action-specific result dict

    Examples:
        # List all sessions
        process_tool(action="list")

        # Poll for new output
        process_tool(action="poll", session_id="abc12345")

        # View log with pagination
        process_tool(action="log", session_id="abc12345", offset=0, limit=50)

        # Send Ctrl-C to a running process
        process_tool(action="send_keys", session_id="abc12345", keys="Ctrl-C")

        # Kill a running process
        process_tool(action="kill", session_id="abc12345")
    """
    from ag3nt_agent.exec_tool import ProcessRegistry

    registry = ProcessRegistry.get_instance()

    if action == "list":
        sessions = registry.list_all()
        # Also run cleanup of old finished sessions
        cleaned = registry.cleanup()
        return {
            "sessions": sessions,
            "total": len(sessions),
            "cleaned_up": cleaned,
        }

    # All other actions require session_id
    if not session_id:
        return {"error": f"session_id is required for action '{action}'"}

    session = registry.get(session_id)
    if session is None:
        return {"error": f"Session '{session_id}' not found"}

    if action == "poll":
        pending = session.get_pending_output()
        return {
            "session_id": session_id,
            "status": session.status,
            "new_output": pending,
            "exit_code": session.exit_code,
            "duration": round(session.duration, 2),
            "truncated": session.truncated,
        }

    if action == "log":
        output = session.get_output_slice(offset=offset, limit=limit)
        total_lines = len(session.output_buffer.split("\n"))
        return {
            "session_id": session_id,
            "status": session.status,
            "output": output,
            "offset": offset,
            "limit": limit,
            "total_lines": total_lines,
        }

    if action == "write":
        if not input_text:
            return {"error": "input_text is required for 'write' action"}
        if session.status != "running":
            return {"error": f"Session is not running (status: {session.status})"}
        success = session.write_stdin(input_text)
        return {
            "session_id": session_id,
            "success": success,
            "written": input_text if success else None,
        }

    if action == "send_keys":
        if not keys:
            return {"error": "keys is required for 'send_keys' action"}
        if session.status != "running":
            return {"error": f"Session is not running (status: {session.status})"}
        success = session.send_keys(keys)
        return {
            "session_id": session_id,
            "success": success,
            "keys_sent": keys if success else None,
        }

    if action == "kill":
        if session.status != "running":
            return {
                "session_id": session_id,
                "status": session.status,
                "message": "Session is not running",
            }
        session.kill()
        registry.finish(session_id)
        return {
            "session_id": session_id,
            "status": "killed",
            "exit_code": session.exit_code,
        }

    if action == "clear":
        session.clear_output()
        return {
            "session_id": session_id,
            "status": session.status,
            "message": "Output buffer cleared",
        }

    if action == "remove":
        if session.status == "running":
            session.kill()
            registry.finish(session_id)
        success = registry.remove(session_id)
        return {
            "session_id": session_id,
            "removed": success,
        }

    return {"error": f"Unknown action: {action}"}


def get_process_tool():
    """Get the process management tool for the agent.

    Returns:
        LangChain tool for background process management
    """
    return process_tool
