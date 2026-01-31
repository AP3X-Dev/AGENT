"""Enhanced tool call display widget with expandable sections.

This module provides an extensible tool call display system inspired by
the AG3NTIC web UI, adapted for the Textual TUI framework.

Features:
- Collapsible/expandable tool output sections
- Tool-specific icons and styling
- Registry pattern for extensibility
- Visual separation from main chat text
- Animated running indicator
"""

from __future__ import annotations

import logging
from time import time
from typing import TYPE_CHECKING, Any, ClassVar

from textual.containers import Vertical
from textual.events import Click
from textual.timer import Timer
from textual.widgets import Static

from deepagents_cli.ui import format_tool_display
from deepagents_cli.widgets.tool_icons import get_styled_tool_symbol, get_tool_icon

if TYPE_CHECKING:
    from textual.app import ComposeResult

_log = logging.getLogger(__name__)


# Maximum lines/chars for preview mode
_PREVIEW_LINES = 3
_PREVIEW_CHARS = 200
_MAX_INLINE_ARGS = 3


class ToolCallDisplayBase(Vertical):
    """Base class for tool call display widgets.

    Subclass this to create specialized displays for different tool types.
    Override _get_key_args_display() for tool-specific inline argument formatting.
    """

    # Spinner frames for running animation
    _SPINNER_FRAMES: ClassVar[tuple[str, ...]] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    DEFAULT_CSS = """
    /* Base styles for all tool display widgets - using inheritance-compatible selectors */
    ToolCallDisplayBase, ToolCallDisplay, WebSearchDisplay, ShellCommandDisplay,
    FileOperationDisplay, TaskAgentDisplay, SandboxToolDisplay {
        height: auto;
        padding: 0 1;
        margin: 1 0;
        background: $surface;
        border-left: thick $secondary;
    }

    ToolCallDisplayBase:hover, ToolCallDisplay:hover, WebSearchDisplay:hover,
    ShellCommandDisplay:hover, FileOperationDisplay:hover, TaskAgentDisplay:hover,
    SandboxToolDisplay:hover {
        background: $surface-lighten-1;
    }

    /* Tool header - the main display line with icon, name, and args */
    .tool-header {
        color: $secondary;
        text-style: bold;
    }

    .tool-header-row {
        layout: horizontal;
        height: auto;
    }

    .tool-icon {
        width: 3;
        text-align: center;
    }

    .tool-name {
        color: $secondary;
        text-style: bold;
    }

    .tool-args-preview {
        color: $text-muted;
        margin-left: 1;
    }

    .tool-status {
        margin-left: auto;
    }

    .tool-status.pending {
        color: $warning;
    }

    .tool-status.success {
        color: $success;
    }

    .tool-status.error {
        color: $error;
    }

    .tool-status.rejected {
        color: $warning;
    }

    .tool-expand-indicator {
        color: $text-muted;
        margin-left: 1;
    }

    .tool-content-section {
        margin-top: 1;
        margin-left: 3;
        padding: 1;
        background: $surface-darken-1;
        border: solid $surface-lighten-1;
    }

    .tool-content-section.collapsed {
        display: none;
    }

    .tool-output-preview {
        margin-left: 3;
        color: $text-muted;
    }

    .tool-output-hint {
        margin-left: 3;
        color: $primary;
        text-style: italic;
    }

    .tool-section-header {
        color: $text-muted;
        text-style: bold;
        text-transform: uppercase;
        margin-bottom: 1;
    }

    .tool-output-content {
        color: $text;
    }

    .tool-args-content {
        color: $text-muted;
    }

    .tool-error-content {
        color: $error;
        background: #7f1d1d20;
        padding: 1;
    }
    """

    def __init__(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the tool call display.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments (optional)
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._args = args or {}
        self._status = "pending"
        self._output: str = ""
        self._error: str = ""
        self._expanded: bool = False
        # Animation state
        self._spinner_position = 0
        self._start_time: float | None = None
        self._animation_timer: Timer | None = None
        # Widget references (set in on_mount)
        self._status_widget: Static | None = None
        self._expand_indicator: Static | None = None
        self._content_section: Vertical | None = None
        self._preview_widget: Static | None = None
        self._hint_widget: Static | None = None

    def _get_key_args_display(self) -> str:
        """Get the key arguments to display inline.

        Override in subclasses for tool-specific formatting.
        Returns empty string by default - subclasses should override.
        """
        # Default implementation returns empty - subclasses can override
        return ""

    def _get_tool_icon(self) -> str:
        """Get the styled icon for this tool."""
        return get_styled_tool_symbol(self._tool_name)

    def _format_tool_name(self) -> str:
        """Format the tool name for display."""
        # Convert snake_case to Title Case
        return self._tool_name.replace("_", " ").title()

    def compose(self) -> ComposeResult:
        """Compose the tool call display layout."""
        # Build header using Rich markup strings (not Text objects)
        icon = self._get_tool_icon()
        name = self._format_tool_name()
        args_preview = self._get_key_args_display()

        # Debug logging to track what's being rendered
        _log.debug(
            f"ToolCallDisplayBase.compose: widget={type(self).__name__}, "
            f"tool={self._tool_name}, icon={icon!r}, name={name!r}, "
            f"args_preview={args_preview!r}"
        )

        # Build header with Rich markup - works reliably with Static
        # Add visible prefix to distinguish from other message types
        if args_preview:
            header_markup = f"[bold cyan]⚙[/bold cyan] {icon} [bold yellow]{name}[/bold yellow] [dim]{args_preview}[/dim]"
        else:
            header_markup = f"[bold cyan]⚙[/bold cyan] {icon} [bold yellow]{name}[/bold yellow]"

        _log.debug(f"ToolCallDisplayBase.compose: header_markup={header_markup!r}")

        # Header row with icon, name, args preview
        yield Static(header_markup, classes="tool-header", id="tool-header")

        # Status indicator (shows spinner while running, then final status)
        yield Static("", classes="tool-status", id="status")

        # Expand/collapse indicator
        yield Static("[dim]▶ Click to expand[/dim]", classes="tool-expand-indicator", id="expand-indicator")

        # Preview area (shown when collapsed)
        yield Static("", classes="tool-output-preview", id="output-preview", markup=False)
        yield Static("", classes="tool-output-hint", id="output-hint")

        # Expandable content section
        with Vertical(classes="tool-content-section collapsed", id="content-section"):
            yield from self._compose_content_section()

    def _compose_content_section(self) -> ComposeResult:
        """Compose the expandable content section.

        Override in subclasses for tool-specific content.
        """
        # Output section
        yield Static("OUTPUT", classes="tool-section-header")
        yield Static("", classes="tool-output-content", id="output-content", markup=False)

        # Arguments section
        yield Static("ARGUMENTS", classes="tool-section-header")
        yield Static("", classes="tool-args-content", id="args-content", markup=False)

        # Error section (hidden by default)
        yield Static("", classes="tool-error-content", id="error-content", markup=False)

    def on_mount(self) -> None:
        """Cache widget references and set initial state."""
        self._status_widget = self.query_one("#status", Static)
        self._expand_indicator = self.query_one("#expand-indicator", Static)
        self._content_section = self.query_one("#content-section", Vertical)
        self._preview_widget = self.query_one("#output-preview", Static)
        self._hint_widget = self.query_one("#output-hint", Static)

        # Hide everything initially
        self._status_widget.display = False
        self._preview_widget.display = False
        self._hint_widget.display = False

    def on_click(self, event: Click) -> None:
        """Handle click to toggle expansion."""
        event.stop()
        self.toggle_expanded()

    def toggle_expanded(self) -> None:
        """Toggle between collapsed and expanded state."""
        if not self._output and not self._error:
            return

        self._expanded = not self._expanded
        self._update_display()

    def _update_display(self) -> None:
        """Update the display based on current state."""
        if not self._content_section or not self._expand_indicator:
            return

        if self._expanded:
            self._content_section.remove_class("collapsed")
            self._expand_indicator.update("[dim]▼ Click to collapse[/dim]")
            self._preview_widget.display = False
            self._hint_widget.display = False
            self._update_content_section()
        else:
            self._content_section.add_class("collapsed")
            self._expand_indicator.update("[dim]▶ Click to expand[/dim]")
            self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview display when collapsed."""
        if not self._output or not self._preview_widget:
            return

        output_stripped = self._output.strip()
        lines = output_stripped.split("\n")
        total_lines = len(lines)
        total_chars = len(output_stripped)

        needs_truncation = total_lines > _PREVIEW_LINES or total_chars > _PREVIEW_CHARS

        if needs_truncation:
            if total_lines > _PREVIEW_LINES:
                preview_text = "\n".join(lines[:_PREVIEW_LINES])
            else:
                preview_text = output_stripped

            if len(preview_text) > _PREVIEW_CHARS:
                preview_text = preview_text[:_PREVIEW_CHARS] + "..."

            self._preview_widget.update(preview_text)
            self._preview_widget.display = True
            self._hint_widget.update("[dim]... (click to expand)[/dim]")
            self._hint_widget.display = True
        elif output_stripped:
            self._preview_widget.update(output_stripped)
            self._preview_widget.display = True
            self._hint_widget.display = False

    def _update_content_section(self) -> None:
        """Update the expanded content section."""
        try:
            output_widget = self.query_one("#output-content", Static)
            args_widget = self.query_one("#args-content", Static)
            error_widget = self.query_one("#error-content", Static)

            if self._output:
                output_widget.update(self._output)
                output_widget.display = True
            else:
                output_widget.display = False

            if self._args:
                import json
                args_str = json.dumps(self._args, indent=2)
                args_widget.update(args_str)
                args_widget.display = True
            else:
                args_widget.display = False

            if self._error:
                error_widget.update(self._error)
                error_widget.display = True
            else:
                error_widget.display = False
        except Exception:
            pass  # Widget not mounted yet

    # Status management methods
    def set_running(self) -> None:
        """Mark the tool as running (approved and executing)."""
        if self._status == "running":
            return

        self._status = "running"
        self._start_time = time()
        if self._status_widget:
            self._status_widget.add_class("pending")
            self._status_widget.display = True
        self._update_running_animation()
        self._animation_timer = self.set_interval(0.1, self._update_running_animation)

    def _update_running_animation(self) -> None:
        """Update the running spinner animation."""
        if self._status != "running" or self._status_widget is None:
            return

        frame = self._SPINNER_FRAMES[self._spinner_position]
        self._spinner_position = (self._spinner_position + 1) % len(self._SPINNER_FRAMES)

        elapsed = ""
        if self._start_time is not None:
            elapsed_secs = int(time() - self._start_time)
            elapsed = f" ({elapsed_secs}s)"

        self._status_widget.update(f"[yellow]{frame} Running...{elapsed}[/yellow]")

    def _stop_animation(self) -> None:
        """Stop the running animation."""
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None

    def set_success(self, result: str = "") -> None:
        """Mark the tool call as successful."""
        self._stop_animation()
        self._status = "success"
        self._output = result
        if self._status_widget:
            self._status_widget.remove_class("pending")
            self._status_widget.add_class("success")
            self._status_widget.update("[green]✓[/green]")
            self._status_widget.display = True
        self._update_display()

    def set_error(self, error: str) -> None:
        """Mark the tool call as failed."""
        self._stop_animation()
        self._status = "error"
        self._error = error
        if self._status_widget:
            self._status_widget.remove_class("pending")
            self._status_widget.add_class("error")
            self._status_widget.update("[red]✗ Error[/red]")
            self._status_widget.display = True
        self._expanded = True  # Auto-expand on error
        self._update_display()

    def set_rejected(self) -> None:
        """Mark the tool call as rejected by user."""
        self._stop_animation()
        self._status = "rejected"
        if self._status_widget:
            self._status_widget.remove_class("pending")
            self._status_widget.add_class("rejected")
            self._status_widget.update("[yellow]✗ Rejected[/yellow]")
            self._status_widget.display = True

    def set_skipped(self) -> None:
        """Mark the tool call as skipped."""
        self._stop_animation()
        self._status = "skipped"
        if self._status_widget:
            self._status_widget.remove_class("pending")
            self._status_widget.add_class("rejected")
            self._status_widget.update("[dim]- Skipped[/dim]")
            self._status_widget.display = True

    @property
    def has_output(self) -> bool:
        """Check if this tool message has output to display."""
        return bool(self._output)


class ToolCallDisplay(ToolCallDisplayBase):
    """Default tool call display widget.

    Provides a generic display for any tool type with expandable output.
    """

    def _get_key_args_display(self) -> str:
        """Get key arguments for inline display."""
        return format_tool_display(self._tool_name, self._args)

    def _filtered_args(self) -> dict[str, Any]:
        """Filter large tool args for display."""
        if self._tool_name not in {"write_file", "edit_file"}:
            return self._args

        filtered: dict[str, Any] = {}
        for key in ("file_path", "path", "replace_all"):
            if key in self._args:
                filtered[key] = self._args[key]
        return filtered


# ============================================================================
# Specialized Tool Display Widgets
# ============================================================================


class ShellCommandDisplay(ToolCallDisplayBase):
    """Display widget for shell/execute/bash commands.

    Shows the command being executed with syntax highlighting.
    """

    def _get_key_args_display(self) -> str:
        """Get the command to display inline."""
        cmd = self._args.get("command") or self._args.get("cmd", "")
        if len(cmd) > 50:
            return cmd[:50] + "..."
        return cmd

    def _format_tool_name(self) -> str:
        """Override to show 'Shell Command'."""
        return "Shell Command"


class FileOperationDisplay(ToolCallDisplayBase):
    """Display widget for file operations (read, write, edit).

    Shows the file path and operation type clearly.
    """

    def _get_key_args_display(self) -> str:
        """Get the file path to display inline."""
        path = (
            self._args.get("file_path")
            or self._args.get("path")
            or self._args.get("filename", "")
        )
        # Show just filename for brevity
        if "/" in path or "\\" in path:
            path = path.replace("\\", "/").split("/")[-1]
        return path

    def _format_tool_name(self) -> str:
        """Format to show specific operation type."""
        name = self._tool_name.lower()
        if "read" in name:
            return "Read File"
        if "write" in name:
            return "Write File"
        if "edit" in name:
            return "Edit File"
        if "delete" in name:
            return "Delete File"
        return "File Operation"


class WebSearchDisplay(ToolCallDisplayBase):
    """Display widget for web search and research tools.

    Shows the search query, URL, or topic prominently.
    """

    def _get_key_args_display(self) -> str:
        """Get the key argument (query, URL, or topic) to display inline."""
        # Try different argument names used by various search/research tools
        value = (
            self._args.get("query")
            or self._args.get("q")
            or self._args.get("url")
            or self._args.get("topic")
            or self._args.get("input")
            or ""
        )
        if not value:
            # If no recognized key, try to get the first non-empty string arg
            for v in self._args.values():
                if isinstance(v, str) and v:
                    value = v
                    break
        if len(value) > 60:
            return f'"{value[:60]}..."'
        return f'"{value}"' if value else ""

    def _format_tool_name(self) -> str:
        """Override to show appropriate name based on tool."""
        name_lower = self._tool_name.lower()
        if name_lower == "research":
            return "Research"
        if name_lower == "internet_search":
            return "Internet Search"
        if "tavily" in name_lower:
            return "Tavily Search"
        if "fetch" in name_lower:
            return "Fetch URL"
        return "Web Search"


class TaskAgentDisplay(ToolCallDisplayBase):
    """Display widget for task/subagent delegation.

    Shows the subagent type and task description.
    """

    def _get_key_args_display(self) -> str:
        """Get the task description to display inline."""
        subagent_type = self._args.get("subagent_type", "")
        description = self._args.get("description", "")
        if subagent_type:
            agent_name = subagent_type.replace("-", " ").replace("_", " ").title()
            if description and len(description) > 40:
                return f"{agent_name}: {description[:40]}..."
            if description:
                return f"{agent_name}: {description}"
            return agent_name
        if description:
            return description[:50] + "..." if len(description) > 50 else description
        return ""

    def _format_tool_name(self) -> str:
        """Override to show 'Task Agent'."""
        return "Task Agent"


class SandboxToolDisplay(ToolCallDisplayBase):
    """Display widget for E2B sandbox tools.

    Shows code execution, package installation, etc.
    """

    def _get_key_args_display(self) -> str:
        """Get key info for sandbox tool display."""
        name = self._tool_name.lower()

        if name == "execute_code":
            lang = self._args.get("language", "python")
            code = self._args.get("code", "")
            first_line = code.split("\n")[0] if code else ""
            if len(first_line) > 40:
                first_line = first_line[:40] + "..."
            return f"[{lang}] {first_line}"

        if name == "install_packages":
            packages = self._args.get("packages", [])
            if isinstance(packages, list):
                pkg_str = ", ".join(packages[:3])
                if len(packages) > 3:
                    pkg_str += f" (+{len(packages) - 3} more)"
                return pkg_str
            return str(packages)

        if name == "sandbox_run_command":
            cmd = self._args.get("command", "")
            return cmd[:50] + "..." if len(cmd) > 50 else cmd

        # Default: show first argument
        for key, value in self._args.items():
            val_str = str(value)
            return val_str[:40] + "..." if len(val_str) > 40 else val_str
        return ""

    def _format_tool_name(self) -> str:
        """Format sandbox tool name nicely."""
        name = self._tool_name.lower()
        if name == "execute_code":
            return "Execute Code"
        if name == "install_packages":
            return "Install Packages"
        if name.startswith("sandbox_"):
            return name.replace("sandbox_", "").replace("_", " ").title()
        return self._tool_name.replace("_", " ").title()


# ============================================================================
# Tool Display Registry and Factory
# ============================================================================

# Mapping of tool names to their specialized display classes
_TOOL_DISPLAY_REGISTRY: dict[str, type[ToolCallDisplayBase]] = {
    # Shell commands
    "shell": ShellCommandDisplay,
    "execute": ShellCommandDisplay,
    "bash": ShellCommandDisplay,
    # File operations
    "read_file": FileOperationDisplay,
    "read": FileOperationDisplay,
    "write_file": FileOperationDisplay,
    "write": FileOperationDisplay,
    "edit_file": FileOperationDisplay,
    "edit": FileOperationDisplay,
    "delete_file": FileOperationDisplay,
    "list_files": FileOperationDisplay,
    "glob": FileOperationDisplay,
    "grep": FileOperationDisplay,
    # Web search and research
    "web_search": WebSearchDisplay,
    "research": WebSearchDisplay,
    "tavily_search": WebSearchDisplay,
    "internet_search": WebSearchDisplay,
    "fetch_url": WebSearchDisplay,
    # Task/subagent
    "task": TaskAgentDisplay,
    # Sandbox tools
    "execute_code": SandboxToolDisplay,
    "install_packages": SandboxToolDisplay,
    "sandbox_upload_file": SandboxToolDisplay,
    "sandbox_download_file": SandboxToolDisplay,
    "sandbox_list_files": SandboxToolDisplay,
    "sandbox_run_command": SandboxToolDisplay,
    "sandbox_cleanup": SandboxToolDisplay,
}


def create_tool_display(
    tool_name: str,
    args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ToolCallDisplayBase:
    """Create the appropriate tool display widget for a tool.

    Args:
        tool_name: Name of the tool
        args: Tool arguments
        **kwargs: Additional arguments passed to widget

    Returns:
        An instance of the appropriate tool display widget
    """
    display_class = _TOOL_DISPLAY_REGISTRY.get(tool_name.lower(), ToolCallDisplay)
    widget = display_class(tool_name, args, **kwargs)
    _log.info(
        f"create_tool_display: tool={tool_name!r}, "
        f"widget_class={type(widget).__name__}, args_keys={list(args.keys()) if args else []}"
    )
    return widget


def register_tool_display(
    tool_name: str, display_class: type[ToolCallDisplayBase]
) -> None:
    """Register a custom display class for a tool.

    Args:
        tool_name: Name of the tool
        display_class: The display class to use
    """
    _TOOL_DISPLAY_REGISTRY[tool_name.lower()] = display_class
