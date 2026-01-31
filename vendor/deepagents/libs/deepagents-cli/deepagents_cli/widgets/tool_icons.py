"""Tool icon registry for TUI display.

Maps tool names to Unicode symbols for visual identification in the terminal.
Inspired by the AG3NTIC web UI's icon system but adapted for terminal display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ToolIcon:
    """Represents a tool's visual identity in the TUI."""

    symbol: str
    color: str  # Rich color name or hex
    category: str  # For grouping similar tools

    def styled(self) -> str:
        """Return the symbol with Rich markup styling."""
        return f"[{self.color}]{self.symbol}[/{self.color}]"


# Tool icon registry - maps tool names to their visual representation
TOOL_ICONS: dict[str, ToolIcon] = {
    # Shell/Terminal tools
    "shell": ToolIcon("⚡", "yellow", "terminal"),
    "execute": ToolIcon("⚡", "yellow", "terminal"),
    "bash": ToolIcon("⚡", "yellow", "terminal"),
    "sandbox_run_command": ToolIcon("⚡", "yellow", "terminal"),
    # File operations
    "read_file": ToolIcon("📄", "cyan", "file"),
    "read": ToolIcon("📄", "cyan", "file"),
    "write_file": ToolIcon("📝", "green", "file"),
    "write": ToolIcon("📝", "green", "file"),
    "edit_file": ToolIcon("✏️", "blue", "file"),
    "edit": ToolIcon("✏️", "blue", "file"),
    "delete_file": ToolIcon("🗑️", "red", "file"),
    # Directory operations
    "read_directory": ToolIcon("📁", "cyan", "directory"),
    "list_directory": ToolIcon("📁", "cyan", "directory"),
    "sandbox_list_files": ToolIcon("📁", "cyan", "directory"),
    # Web/Search tools
    "web_search": ToolIcon("🔍", "magenta", "web"),
    "research": ToolIcon("🔍", "magenta", "web"),
    "tavily_search": ToolIcon("🔍", "magenta", "web"),
    "internet_search": ToolIcon("🔍", "magenta", "web"),
    "web": ToolIcon("🌐", "blue", "web"),
    "web_fetch": ToolIcon("🌐", "blue", "web"),
    "fetch_url": ToolIcon("🌐", "blue", "web"),
    "http_request": ToolIcon("🌐", "blue", "web"),
    # Task/Planning tools
    "add_tasks": ToolIcon("📋", "green", "planning"),
    "update_tasks": ToolIcon("📋", "yellow", "planning"),
    "update_task_list": ToolIcon("📋", "yellow", "planning"),
    "write_todos": ToolIcon("📋", "green", "planning"),
    # Subagent/Task delegation
    "task": ToolIcon("🤖", "magenta", "agent"),
    # Code execution (E2B sandbox)
    "execute_code": ToolIcon("▶️", "green", "sandbox"),
    "install_packages": ToolIcon("📦", "blue", "sandbox"),
    "sandbox_upload_file": ToolIcon("⬆️", "cyan", "sandbox"),
    "sandbox_download_file": ToolIcon("⬇️", "cyan", "sandbox"),
    "sandbox_cleanup": ToolIcon("🧹", "yellow", "sandbox"),
    # Image tools
    "generate_image": ToolIcon("🖼️", "magenta", "image"),
    "edit_image": ToolIcon("🖼️", "blue", "image"),
    # Research tools
    "deep_research": ToolIcon("✨", "magenta", "research"),
    # MCP tools (generic)
    "mcp": ToolIcon("🔌", "cyan", "mcp"),
    # Git tools
    "git": ToolIcon("📊", "orange1", "git"),
    "git_status": ToolIcon("📊", "orange1", "git"),
    "git_diff": ToolIcon("📊", "orange1", "git"),
    "git_commit": ToolIcon("📊", "green", "git"),
}

# Default icon for unknown tools
DEFAULT_ICON = ToolIcon("🔧", "white", "unknown")


def get_tool_icon(tool_name: str) -> ToolIcon:
    """Get the icon for a tool by name.

    Args:
        tool_name: The name of the tool (case-insensitive)

    Returns:
        The ToolIcon for the tool, or DEFAULT_ICON if not found
    """
    return TOOL_ICONS.get(tool_name.lower(), DEFAULT_ICON)


def get_tool_symbol(tool_name: str) -> str:
    """Get just the symbol for a tool.

    Args:
        tool_name: The name of the tool

    Returns:
        The Unicode symbol for the tool
    """
    return get_tool_icon(tool_name).symbol


def get_styled_tool_symbol(tool_name: str) -> str:
    """Get the styled symbol with Rich markup.

    Args:
        tool_name: The name of the tool

    Returns:
        The symbol with Rich color markup
    """
    return get_tool_icon(tool_name).styled()


# Tool categories for grouping in UI
TOOL_CATEGORIES: dict[str, str] = {
    "terminal": "Terminal Commands",
    "file": "File Operations",
    "directory": "Directory Operations",
    "web": "Web & Search",
    "planning": "Planning & Tasks",
    "agent": "Agent Delegation",
    "sandbox": "Code Sandbox",
    "image": "Image Generation",
    "research": "Research",
    "mcp": "MCP Tools",
    "git": "Git Operations",
    "unknown": "Other Tools",
}

