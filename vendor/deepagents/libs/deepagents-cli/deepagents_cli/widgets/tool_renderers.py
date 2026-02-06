"""Tool renderers for approval widgets - registry pattern.

This module provides:
1. Approval widget renderers for HITL display
2. Integration with the new tool display system
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Any

from deepagents_cli.widgets.tool_call_display import (
    ToolCallDisplayBase,
    create_tool_display,
)
from deepagents_cli.widgets.tool_widgets import (
    EditFileApprovalWidget,
    GenericApprovalWidget,
    WriteFileApprovalWidget,
)

if TYPE_CHECKING:
    from deepagents_cli.widgets.tool_widgets import ToolApprovalWidget


class ToolRenderer:
    """Base renderer for tool approval widgets."""

    def get_approval_widget(
        self, tool_args: dict[str, Any]
    ) -> tuple[type[ToolApprovalWidget], dict[str, Any]]:
        """Get the approval widget class and data for this tool.

        Args:
            tool_args: The tool arguments from action_request

        Returns:
            Tuple of (widget_class, data_dict)
        """
        return GenericApprovalWidget, tool_args


class WriteFileRenderer(ToolRenderer):
    """Renderer for write_file tool - shows full file content."""

    def get_approval_widget(
        self, tool_args: dict[str, Any]
    ) -> tuple[type[ToolApprovalWidget], dict[str, Any]]:
        # Extract file extension for syntax highlighting
        file_path = tool_args.get("file_path", "")
        content = tool_args.get("content", "")

        # Get file extension
        file_extension = "text"
        if "." in file_path:
            file_extension = file_path.rsplit(".", 1)[-1]

        data = {
            "file_path": file_path,
            "content": content,
            "file_extension": file_extension,
        }
        return WriteFileApprovalWidget, data


class EditFileRenderer(ToolRenderer):
    """Renderer for edit_file tool - shows unified diff."""

    def get_approval_widget(
        self, tool_args: dict[str, Any]
    ) -> tuple[type[ToolApprovalWidget], dict[str, Any]]:
        file_path = tool_args.get("file_path", "")
        old_string = tool_args.get("old_string", "")
        new_string = tool_args.get("new_string", "")

        # Generate unified diff
        diff_lines = self._generate_diff(old_string, new_string)

        data = {
            "file_path": file_path,
            "diff_lines": diff_lines,
            "old_string": old_string,
            "new_string": new_string,
        }
        return EditFileApprovalWidget, data

    def _generate_diff(self, old_string: str, new_string: str) -> list[str]:
        """Generate unified diff lines from old and new strings."""
        if not old_string and not new_string:
            return []

        old_lines = old_string.split("\n") if old_string else []
        new_lines = new_string.split("\n") if new_string else []

        # Generate unified diff
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
            n=3,  # Context lines
        )

        # Skip the first two header lines (--- and +++)
        diff_list = list(diff)
        return diff_list[2:] if len(diff_list) > 2 else diff_list


class ExecCommandRenderer(ToolRenderer):
    """Renderer for exec_command tool - shows command text."""

    def get_approval_widget(
        self, tool_args: dict[str, Any]
    ) -> tuple[type[ToolApprovalWidget], dict[str, Any]]:
        command = tool_args.get("command", "")
        bg = tool_args.get("background", False)
        data = {
            "command": command,
            "background": bg,
            "workdir": tool_args.get("workdir", ""),
        }
        return GenericApprovalWidget, data


class ApplyPatchRenderer(ToolRenderer):
    """Renderer for apply_patch tool - shows file list."""

    def get_approval_widget(
        self, tool_args: dict[str, Any]
    ) -> tuple[type[ToolApprovalWidget], dict[str, Any]]:
        import re

        patch_text = tool_args.get("patch", "")
        files = re.findall(
            r"\*\*\*\s+(Add|Update|Delete)\s+File:\s*(.+)",
            patch_text,
            re.IGNORECASE,
        )
        file_list = [{"action": a.lower(), "path": p.strip()} for a, p in files]
        data = {
            "files": file_list,
            "file_count": len(file_list),
            "dry_run": tool_args.get("dry_run", False),
        }
        return GenericApprovalWidget, data


# Registry mapping tool names to renderers
# Note: bash/shell use minimal approval (no renderer needed) - see ApprovalMenu._MINIMAL_TOOLS
_RENDERER_REGISTRY: dict[str, type[ToolRenderer]] = {
    "write_file": WriteFileRenderer,
    "edit_file": EditFileRenderer,
    "exec_command": ExecCommandRenderer,
    "apply_patch": ApplyPatchRenderer,
}


def get_renderer(tool_name: str) -> ToolRenderer:
    """Get the renderer for a tool by name.

    Args:
        tool_name: The name of the tool

    Returns:
        The appropriate ToolRenderer instance
    """
    renderer_class = _RENDERER_REGISTRY.get(tool_name, ToolRenderer)
    return renderer_class()


def get_tool_display_widget(
    tool_name: str, args: dict[str, Any] | None = None, **kwargs: Any
) -> ToolCallDisplayBase:
    """Get the appropriate display widget for a tool.

    This is the main entry point for creating tool display widgets.
    It uses the registry in tool_call_display.py to select the
    appropriate specialized widget class.

    Args:
        tool_name: Name of the tool
        args: Tool arguments
        **kwargs: Additional arguments passed to the widget

    Returns:
        An instance of the appropriate ToolCallDisplayBase subclass
    """
    return create_tool_display(tool_name, args, **kwargs)
