"""Approval flow widgets for AG3NT TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static

from .tool_icons import get_tool_icon

if TYPE_CHECKING:
    from textual.widget import Widget


# Tools that require approval by default
SENSITIVE_TOOLS = {
    # File write operations
    "write_file", "write", "edit_file", "edit", "multi_edit",
    "delete_file", "apply_patch",
    # Shell/command execution
    "shell", "bash", "execute", "exec_command",
    "sandbox_run_command", "process_tool",
    # Git operations that modify state
    "git_commit", "git_push", "git_checkout", "git_branch",
    # Web operations that could leak data
    "http_request",
}


def requires_approval(tool_name: str) -> bool:
    """Check if a tool requires user approval.

    Args:
        tool_name: Name of the tool

    Returns:
        True if the tool requires approval
    """
    return tool_name in SENSITIVE_TOOLS


class ApprovalRequest(Vertical):
    """Inline approval request for tool execution."""

    DEFAULT_CSS = """
    ApprovalRequest {
        background: #1e1e1e;
        border: solid #f59e0b;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    ApprovalRequest .title {
        text-style: bold;
        color: #f59e0b;
        height: auto;
    }
    ApprovalRequest .tool-info {
        height: auto;
        margin: 1 0;
    }
    ApprovalRequest .preview {
        background: #171717;
        padding: 1;
        margin: 1 0;
        max-height: 15;
        overflow-y: auto;
        height: auto;
    }
    ApprovalRequest .buttons {
        margin-top: 1;
        height: auto;
    }
    ApprovalRequest Button {
        margin-right: 1;
    }
    ApprovalRequest .hint {
        color: #6b6b6b;
        margin-top: 1;
        height: auto;
    }
    """

    class Approved(Message):
        """User approved the tool execution."""

        def __init__(
            self, tool_call_id: str, auto_approve: bool = False
        ) -> None:
            self.tool_call_id = tool_call_id
            self.auto_approve = auto_approve
            super().__init__()

    class Rejected(Message):
        """User rejected the tool execution."""

        def __init__(self, tool_call_id: str) -> None:
            self.tool_call_id = tool_call_id
            super().__init__()

    def __init__(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str,
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.tool_call_id = tool_call_id
        self.description = description
        self.can_focus = True

    def compose(self) -> ComposeResult:
        icon = get_tool_icon(self.tool_name)
        yield Static("[#f59e0b]⚠[/#f59e0b] Approval Required", classes="title")
        yield Static(
            f"[{icon.color}]{icon.symbol}[/{icon.color}] [bold]{self.tool_name}[/bold]"
            + (f": {self.description}" if self.description else ""),
            classes="tool-info",
        )
        yield self._render_tool_preview()
        yield Horizontal(
            Button("Approve (y)", id="approve", variant="success"),
            Button("Reject (n)", id="reject", variant="error"),
            Button("Auto-approve all (a)", id="auto-approve", variant="warning"),
            classes="buttons",
        )
        yield Static(
            "[dim]Press [bold]y[/bold] to approve, [bold]n[/bold] to reject, "
            "[bold]a[/bold] to auto-approve all[/dim]",
            classes="hint",
        )

    def _render_tool_preview(self) -> Widget:
        """Render tool-specific preview (file content, diff, command, etc.)."""
        if self.tool_name in ("write_file", "write"):
            return self._render_file_write_preview()
        elif self.tool_name in ("edit_file", "edit", "multi_edit"):
            return self._render_file_edit_preview()
        elif self.tool_name in ("shell", "bash", "execute", "exec_command"):
            return self._render_command_preview()
        elif self.tool_name == "delete_file":
            return self._render_delete_preview()
        elif self.tool_name == "apply_patch":
            return self._render_patch_preview()
        elif self.tool_name.startswith("git_"):
            return self._render_git_preview()
        else:
            return self._render_generic_preview()

    def _render_file_write_preview(self) -> Widget:
        """Render file write preview with syntax highlighting."""
        path = self.tool_args.get("file_path") or self.tool_args.get("path", "")
        content = self.tool_args.get("content", "")

        # Detect language from extension
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "jsx": "javascript",
            "rs": "rust",
            "go": "go",
            "rb": "ruby",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "h": "c",
            "hpp": "cpp",
            "cs": "csharp",
            "sh": "bash",
            "bash": "bash",
            "zsh": "bash",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "toml": "toml",
            "md": "markdown",
            "html": "html",
            "css": "css",
            "sql": "sql",
        }
        lang = lang_map.get(ext, ext or "text")

        lines = content.split("\n")
        preview = "\n".join(lines[:20])
        if len(lines) > 20:
            preview += f"\n... ({len(lines) - 20} more lines)"

        text = Text()
        text.append(f"📄 {path}\n\n", style="bold #22d3ee")
        try:
            syntax = Syntax(preview, lang, theme="monokai", line_numbers=True)
            return Vertical(
                Static(text),
                Static(syntax),
                classes="preview",
            )
        except Exception:
            return Static(f"{text}{preview}", classes="preview")

    def _render_file_edit_preview(self) -> Widget:
        """Render file edit preview."""
        path = self.tool_args.get("file_path") or self.tool_args.get("path", "")
        old_string = self.tool_args.get("old_string", "")
        new_string = self.tool_args.get("new_string", "")

        text = Text()
        text.append(f"📝 {path}\n\n", style="bold #fbbf24")
        text.append("--- Old\n", style="bold red")
        old_preview = old_string[:200] + ("..." if len(old_string) > 200 else "")
        text.append(old_preview + "\n\n", style="red")
        text.append("+++ New\n", style="bold green")
        new_preview = new_string[:200] + ("..." if len(new_string) > 200 else "")
        text.append(new_preview, style="green")

        return Static(text, classes="preview")

    def _render_command_preview(self) -> Widget:
        """Render shell command preview."""
        cmd = self.tool_args.get("command", "")
        cwd = self.tool_args.get("cwd", "")
        timeout = self.tool_args.get("timeout", "")

        text = Text()
        text.append("$ ", style="bold #ec4899")
        text.append(cmd, style="#ececec")
        if cwd:
            text.append(f"\n[dim]Working directory: {cwd}[/dim]")
        if timeout:
            text.append(f"\n[dim]Timeout: {timeout}s[/dim]")

        return Static(text, classes="preview")

    def _render_delete_preview(self) -> Widget:
        """Render file delete preview."""
        path = self.tool_args.get("file_path") or self.tool_args.get("path", "")
        text = Text()
        text.append("🗑 ", style="bold #ef4444")
        text.append(f"Delete: {path}", style="#ef4444")
        return Static(text, classes="preview")

    def _render_patch_preview(self) -> Widget:
        """Render patch preview."""
        patch = self.tool_args.get("patch", "")
        preview = patch[:500] + ("..." if len(patch) > 500 else "")
        return Static(f"[#f59e0b]🩹 Patch:[/#f59e0b]\n{preview}", classes="preview")

    def _render_git_preview(self) -> Widget:
        """Render git operation preview."""
        text = Text()
        text.append(f"⎇ {self.tool_name}\n", style="bold #f97316")

        for key, value in self.tool_args.items():
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            text.append(f"  {key}: ", style="dim")
            text.append(f"{val_str}\n", style="#ececec")

        return Static(text, classes="preview")

    def _render_generic_preview(self) -> Widget:
        """Render generic args preview."""
        text = Text()
        for key, value in list(self.tool_args.items())[:5]:
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            text.append(f"{key}: ", style="dim")
            text.append(f"{val_str}\n", style="#ececec")
        return Static(text, classes="preview")

    def on_mount(self) -> None:
        """Focus the widget when mounted."""
        self.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "approve":
            self.post_message(self.Approved(self.tool_call_id))
        elif event.button.id == "reject":
            self.post_message(self.Rejected(self.tool_call_id))
        elif event.button.id == "auto-approve":
            self.post_message(self.Approved(self.tool_call_id, auto_approve=True))
        self.remove()

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard shortcuts."""
        if event.key == "y":
            self.post_message(self.Approved(self.tool_call_id))
            self.remove()
            event.stop()
        elif event.key == "n":
            self.post_message(self.Rejected(self.tool_call_id))
            self.remove()
            event.stop()
        elif event.key == "a":
            self.post_message(self.Approved(self.tool_call_id, auto_approve=True))
            self.remove()
            event.stop()


class ApprovalBanner(Static):
    """Simple banner shown when approval is pending."""

    DEFAULT_CSS = """
    ApprovalBanner {
        background: #f59e0b;
        color: #0d0d0d;
        text-align: center;
        padding: 0 2;
        text-style: bold;
        height: 1;
        dock: top;
    }
    """

    def __init__(self, count: int = 1, **kwargs) -> None:
        text = f"⚠ {count} action{'s' if count > 1 else ''} awaiting approval"
        super().__init__(text, **kwargs)

    def update_count(self, count: int) -> None:
        """Update the pending count."""
        self.update(f"⚠ {count} action{'s' if count > 1 else ''} awaiting approval")
