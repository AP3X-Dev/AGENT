"""Tool call display widgets for AG3NT TUI."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Collapsible, Static

from .tool_icons import get_tool_icon

if TYPE_CHECKING:
    from typing import Any


class ToolCallDisplay(Vertical):
    """Display a tool call with status, args, and output."""

    DEFAULT_CSS = """
    ToolCallDisplay {
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $surface-lighten-1;
        height: auto;
    }
    ToolCallDisplay.running {
        border-left: thick #f59e0b;
    }
    ToolCallDisplay.success {
        border-left: thick #10b981;
    }
    ToolCallDisplay.error {
        border-left: thick #ef4444;
    }
    ToolCallDisplay .tool-header {
        height: auto;
    }
    ToolCallDisplay .tool-args {
        height: auto;
        color: #6b6b6b;
    }
    ToolCallDisplay .tool-status {
        height: auto;
    }
    """

    status: reactive[str] = reactive("pending")

    def __init__(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.tool_call_id = tool_call_id
        self._output: str | None = None
        self._error: str | None = None
        self._start_time = time.time()

    def compose(self) -> ComposeResult:
        icon = get_tool_icon(self.tool_name)
        yield Static(
            f"[{icon.color}]{icon.symbol}[/] {self.tool_name}",
            id="tool-header",
            classes="tool-header",
        )
        yield Static(self._format_args(), id="tool-args", classes="tool-args")
        yield Static("", id="tool-status", classes="tool-status")
        yield Collapsible(
            Static("", id="tool-output"),
            title="Output",
            collapsed=True,
            id="output-collapsible",
        )

    def _format_args(self) -> str:
        """Format tool args for display (truncated)."""
        parts = []
        for k, v in list(self.tool_args.items())[:3]:
            val_str = str(v)
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            parts.append(f"{k}={val_str}")
        return " ".join(parts)

    def set_running(self) -> None:
        """Mark tool as running."""
        self.status = "running"
        self.add_class("running")
        self._update_status_display()

    def set_complete(self, output: str) -> None:
        """Mark tool as complete with output."""
        self._output = output
        self.status = "success"
        self.remove_class("running")
        self.add_class("success")
        self._update_status_display()
        self._update_output_display()

    def set_error(self, error: str) -> None:
        """Mark tool as errored."""
        self._error = error
        self.status = "error"
        self.remove_class("running")
        self.add_class("error")
        self._update_status_display()
        self._update_output_display()

    def _update_status_display(self) -> None:
        try:
            status = self.query_one("#tool-status", Static)
        except Exception:
            return
        elapsed = time.time() - self._start_time
        if self.status == "running":
            status.update(f"[#f59e0b]⠋ Running ({elapsed:.1f}s)...[/#f59e0b]")
        elif self.status == "success":
            status.update(f"[#10b981]✓ Complete ({elapsed:.1f}s)[/#10b981]")
        elif self.status == "error":
            status.update(f"[#ef4444]✗ Error ({elapsed:.1f}s)[/#ef4444]")

    def _update_output_display(self) -> None:
        try:
            output_widget = self.query_one("#tool-output", Static)
            collapsible = self.query_one("#output-collapsible", Collapsible)
        except Exception:
            return

        content = self._error or self._output or ""
        if content:
            # Show preview (3 lines)
            lines = content.split("\n")
            preview = "\n".join(lines[:3])
            if len(lines) > 3:
                preview += f"\n[dim]... ({len(lines) - 3} more lines)[/dim]"
            output_widget.update(preview)
            collapsible.collapsed = False


# Registry for specialized tool displays
_TOOL_DISPLAY_REGISTRY: dict[str, type[ToolCallDisplay]] = {}


def register_tool_display(tool_name: str, display_class: type[ToolCallDisplay]) -> None:
    """Register a custom display class for a tool."""
    _TOOL_DISPLAY_REGISTRY[tool_name] = display_class


def create_tool_display(
    tool_name: str, args: dict[str, Any], call_id: str
) -> ToolCallDisplay:
    """Factory function to create appropriate tool display."""
    display_class = _TOOL_DISPLAY_REGISTRY.get(tool_name, ToolCallDisplay)
    return display_class(tool_name, args, call_id)


# Specialized displays
class FileOperationDisplay(ToolCallDisplay):
    """Display for file read/write/edit operations."""

    def _format_args(self) -> str:
        path = self.tool_args.get("file_path") or self.tool_args.get("path", "")
        return f"[#22d3ee]{path}[/#22d3ee]"


class ShellCommandDisplay(ToolCallDisplay):
    """Display for shell/bash commands."""

    def _format_args(self) -> str:
        cmd = self.tool_args.get("command", "")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"[#ec4899]$ {cmd}[/#ec4899]"


class WebSearchDisplay(ToolCallDisplay):
    """Display for web search operations."""

    def _format_args(self) -> str:
        query = self.tool_args.get("query", "")
        if len(query) > 50:
            query = query[:47] + "..."
        return f'[#60a5fa]"{query}"[/#60a5fa]'


class GitDisplay(ToolCallDisplay):
    """Display for git operations."""

    def _format_args(self) -> str:
        parts = []
        for key in ["branch", "message", "files"]:
            if key in self.tool_args:
                val = str(self.tool_args[key])
                if len(val) > 30:
                    val = val[:27] + "..."
                parts.append(f"{key}={val}")
        return " ".join(parts) if parts else ""


# Register specialized displays
register_tool_display("read_file", FileOperationDisplay)
register_tool_display("read", FileOperationDisplay)
register_tool_display("write_file", FileOperationDisplay)
register_tool_display("write", FileOperationDisplay)
register_tool_display("edit_file", FileOperationDisplay)
register_tool_display("edit", FileOperationDisplay)
register_tool_display("shell", ShellCommandDisplay)
register_tool_display("bash", ShellCommandDisplay)
register_tool_display("execute", ShellCommandDisplay)
register_tool_display("exec_command", ShellCommandDisplay)
register_tool_display("web_search", WebSearchDisplay)
register_tool_display("internet_search", WebSearchDisplay)
register_tool_display("git_status", GitDisplay)
register_tool_display("git_commit", GitDisplay)
register_tool_display("git_diff", GitDisplay)
