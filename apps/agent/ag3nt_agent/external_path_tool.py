"""External path access tool for AG3NT.

Provides a tool for requesting access to files/directories outside the workspace.
Integrates with the HITL (Human-in-the-Loop) approval flow.

When the agent needs to access a path outside the configured workspace:
1. It calls `request_external_access` with the target path
2. This triggers an interrupt for user approval
3. User approves or denies
4. If approved, the path is cached and future access is allowed

Usage:
    # In agent context
    result = request_external_access(
        path="/some/external/path",
        operation="read",
        reason="User asked me to analyze this file"
    )
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from langchain_core.tools import tool

from ag3nt_agent.tool_policy import PathProtection

logger = logging.getLogger("ag3nt.external_path")


@tool
def request_external_access(
    path: str,
    operation: Literal["read", "write", "execute"] = "read",
    reason: str = "",
) -> str:
    """Request access to a file or directory outside the workspace.

    Use this tool when you need to access a path that's outside the current
    project workspace. The user will be prompted to approve or deny access.

    Once approved, access to that directory is cached for the session,
    so you won't need to request again for other files in the same directory.

    Args:
        path: The absolute path to the file or directory you want to access
        operation: The type of access needed: "read", "write", or "execute"
        reason: Brief explanation of why you need access (shown to user)

    Returns:
        "approved" if access was granted, or an error message if denied
    """
    # Normalize the path
    abs_path = os.path.abspath(os.path.expanduser(path))

    # Get PathProtection instance
    protection = PathProtection.get_instance()

    # Check if already in workspace (no approval needed)
    if protection.is_within_workspace(abs_path):
        return f"approved - path is within workspace"

    # This tool will trigger an interrupt; the response handling happens
    # after the user approves via the HITL flow.
    # When this tool is executed (post-approval), we record the approval.

    # Get session ID from context (will be set by middleware)
    session_id = os.environ.get("AG3NT_CURRENT_SESSION", "default")

    # Record the approval (this is called after HITL approval)
    protection.record_approval(session_id, abs_path, approved=True)

    logger.info(f"External path access approved: {abs_path} ({operation})")

    return f"approved - access granted to {os.path.dirname(abs_path)}"


def format_external_access_request(tool_call: dict, _state=None, _runtime=None) -> str:
    """Format an external path access request for display to the user.

    Used as the description callback for the interrupt_on configuration.
    """
    args = tool_call.get("args", {})
    path = args.get("path", "unknown")
    operation = args.get("operation", "access")
    reason = args.get("reason", "")

    # Normalize for display
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))
        dir_path = os.path.dirname(abs_path)
    except Exception:
        abs_path = path
        dir_path = path

    # Get workspace info
    protection = PathProtection.get_instance()
    workspace = protection._workspace_root or "(not set)"

    lines = [
        f"📁 **External Path Access Request**",
        f"",
        f"**Path:** `{abs_path}`",
        f"**Operation:** {operation}",
        f"**Current workspace:** `{workspace}`",
    ]

    if reason:
        lines.append(f"**Reason:** {reason}")

    lines.extend([
        f"",
        f"This path is outside your project workspace.",
        f"If approved, access to `{dir_path}` will be allowed for this session.",
    ])

    return "\n".join(lines)


def check_and_request_external_access(
    path: str,
    session_id: str,
    operation: str = "access",
) -> tuple[bool, str | None]:
    """Check if external path access is allowed, return info for request if not.

    This is a helper function for tools that need to check path access
    before proceeding.

    Args:
        path: The path to check
        session_id: Current session ID
        operation: Type of operation (for display)

    Returns:
        (True, None) if access is allowed
        (False, message) if access needs approval, with message for user
    """
    protection = PathProtection.get_instance()
    allowed, message = protection.check_path(path, session_id, operation)

    if allowed:
        return True, None

    return False, message


def get_external_access_tools() -> list:
    """Get the list of external path access tools.

    Returns:
        List containing the request_external_access tool
    """
    return [request_external_access]


# Tool name constant for interrupt_on configuration
EXTERNAL_ACCESS_TOOL = "request_external_access"
