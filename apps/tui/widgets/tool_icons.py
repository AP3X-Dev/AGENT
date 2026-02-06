"""Tool icon registry for AG3NT TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolIcon:
    """Icon configuration for a tool."""

    symbol: str
    color: str
    category: str


# Comprehensive tool icon registry
TOOL_ICONS: dict[str, ToolIcon] = {
    # Terminal/Shell tools
    "shell": ToolIcon("$", "#ec4899", "terminal"),
    "bash": ToolIcon("$", "#ec4899", "terminal"),
    "execute": ToolIcon("▶", "#22d3ee", "terminal"),
    "exec_command": ToolIcon("▶", "#22d3ee", "terminal"),
    "process_tool": ToolIcon("⚙", "#22d3ee", "terminal"),
    "sandbox_run_command": ToolIcon("📦", "#22d3ee", "terminal"),

    # File read tools
    "read_file": ToolIcon("📄", "#60a5fa", "file"),
    "read": ToolIcon("📄", "#60a5fa", "file"),

    # File write tools
    "write_file": ToolIcon("✏", "#10b981", "file"),
    "write": ToolIcon("✏", "#10b981", "file"),

    # File edit tools
    "edit_file": ToolIcon("📝", "#fbbf24", "file"),
    "edit": ToolIcon("📝", "#fbbf24", "file"),
    "multi_edit": ToolIcon("📝", "#fbbf24", "file"),

    # File delete tools
    "delete_file": ToolIcon("🗑", "#ef4444", "file"),

    # Patch tools
    "apply_patch": ToolIcon("🩹", "#f59e0b", "file"),

    # Directory tools
    "list_directory": ToolIcon("📁", "#22d3ee", "directory"),
    "read_directory": ToolIcon("📁", "#22d3ee", "directory"),
    "glob_tool": ToolIcon("🔍", "#a78bfa", "directory"),
    "grep_tool": ToolIcon("🔎", "#a78bfa", "directory"),

    # Notebook tools
    "notebook_tool": ToolIcon("📓", "#f97316", "file"),

    # Web tools
    "web_search": ToolIcon("🌐", "#60a5fa", "web"),
    "internet_search": ToolIcon("🌐", "#60a5fa", "web"),
    "web_fetch": ToolIcon("⬇", "#10b981", "web"),
    "fetch_url": ToolIcon("⬇", "#10b981", "web"),
    "http_request": ToolIcon("🔗", "#60a5fa", "web"),

    # Browser tools
    "browser_navigate": ToolIcon("🌍", "#60a5fa", "browser"),
    "browser_click": ToolIcon("👆", "#f59e0b", "browser"),
    "browser_type": ToolIcon("⌨", "#a78bfa", "browser"),
    "browser_screenshot": ToolIcon("📸", "#ec4899", "browser"),
    "browser_scroll": ToolIcon("↕", "#6b7280", "browser"),

    # Memory/Search tools
    "memory_search": ToolIcon("🧠", "#a78bfa", "memory"),
    "codebase_search_tool": ToolIcon("🔬", "#a78bfa", "memory"),
    "memory_summarize": ToolIcon("📊", "#a78bfa", "memory"),

    # Planning tools
    "create_plan": ToolIcon("📋", "#fbbf24", "planning"),
    "update_plan": ToolIcon("✓", "#10b981", "planning"),
    "show_plan": ToolIcon("📋", "#60a5fa", "planning"),

    # Git tools
    "git_status": ToolIcon("⎇", "#f97316", "git"),
    "git_commit": ToolIcon("●", "#10b981", "git"),
    "git_diff": ToolIcon("±", "#fbbf24", "git"),
    "git_log": ToolIcon("📜", "#60a5fa", "git"),
    "git_branch": ToolIcon("⎇", "#a78bfa", "git"),
    "git_checkout": ToolIcon("↪", "#22d3ee", "git"),
    "git_push": ToolIcon("↑", "#10b981", "git"),
    "git_pull": ToolIcon("↓", "#60a5fa", "git"),

    # Agent/Task tools
    "spawn_agent": ToolIcon("🤖", "#a78bfa", "agent"),
    "task": ToolIcon("📌", "#f59e0b", "agent"),
    "run_skill": ToolIcon("⚡", "#fbbf24", "agent"),

    # User interaction tools
    "ask_user": ToolIcon("❓", "#fbbf24", "interaction"),
    "schedule_reminder": ToolIcon("⏰", "#f59e0b", "interaction"),

    # Reasoning tools
    "deep_reasoning": ToolIcon("🧠", "#a78bfa", "reasoning"),

    # LSP tools
    "lsp_tool": ToolIcon("🔧", "#60a5fa", "lsp"),

    # Lint tools
    "lint_tool": ToolIcon("🧹", "#fbbf24", "lint"),

    # Undo/Revert tools
    "undo_last": ToolIcon("↩", "#f59e0b", "revert"),
    "undo_to": ToolIcon("↩", "#f59e0b", "revert"),
    "unrevert": ToolIcon("↪", "#10b981", "revert"),
    "show_undo_history": ToolIcon("📜", "#60a5fa", "revert"),

    # Default
    "_default": ToolIcon("🔧", "#6b7280", "other"),
}


def get_tool_icon(tool_name: str) -> ToolIcon:
    """Get icon for tool, with fallback to default.

    Args:
        tool_name: Name of the tool

    Returns:
        ToolIcon with symbol, color, and category
    """
    return TOOL_ICONS.get(tool_name, TOOL_ICONS["_default"])


def get_category_color(category: str) -> str:
    """Get color for a tool category.

    Args:
        category: Tool category name

    Returns:
        Hex color string
    """
    category_colors = {
        "terminal": "#ec4899",
        "file": "#60a5fa",
        "directory": "#22d3ee",
        "web": "#60a5fa",
        "browser": "#f97316",
        "memory": "#a78bfa",
        "planning": "#fbbf24",
        "git": "#f97316",
        "agent": "#a78bfa",
        "interaction": "#fbbf24",
        "reasoning": "#a78bfa",
        "lsp": "#60a5fa",
        "lint": "#fbbf24",
        "revert": "#f59e0b",
        "other": "#6b7280",
    }
    return category_colors.get(category, "#6b7280")
