"""Command palette screen for AG3NT TUI."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static


class CommandPalette(ModalScreen):
    """Command palette modal screen."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("enter", "select", "Select"),
    ]

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #command-palette-container {
        width: 45;
        height: auto;
        background: #1e1e1e;
        border: solid #3a3a3a;
        padding: 1 2;
    }

    .palette-item {
        width: 100%;
        height: 1;
        padding: 0 1;
        margin: 0;
        background: transparent;
        color: #ececec;
    }

    .palette-item:hover {
        background: #2a2a2a;
    }
    """

    class CommandSelected(Message):
        """Message sent when a command is selected."""

        def __init__(self, command_id: str) -> None:
            self.command_id = command_id
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self.cursor_index = 0
        self.commands = [
            ("cmd-reconnect", "Reconnect to Gateway"),
            ("cmd-clear", "Clear Chat History"),
            ("cmd-sessions", "Browse Session History"),
            ("cmd-copy-session", "Copy Session ID"),
            ("cmd-session-info", "View Session Info"),
            ("cmd-control-panel", "Open Control Panel"),
            ("cmd-node-status", "View Node Status"),
            ("cmd-toggle-auto", "Toggle Auto-Approve"),
            ("cmd-toggle-go", "Toggle Go Mode ⚡"),
            ("cmd-help", "Show Help"),
            ("cmd-quit", "Quit Application"),
        ]

    def compose(self) -> ComposeResult:
        yield Container(
            *[
                Static(
                    f"[#6b6b6b]→[/#6b6b6b] {label}",
                    id=cmd_id,
                    classes="palette-item",
                )
                for cmd_id, label in self.commands
            ],
            id="command-palette-container",
        )

    def on_mount(self) -> None:
        """Highlight first item on mount."""
        self.update_cursor()

    def update_cursor(self) -> None:
        """Update the visual cursor position."""
        for i, (cmd_id, label) in enumerate(self.commands):
            item = self.query_one(f"#{cmd_id}", Static)
            if i == self.cursor_index:
                item.update(f"[#10b981]→ {label}[/#10b981]")
            else:
                item.update(f"[#6b6b6b]→[/#6b6b6b] {label}")

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        self.cursor_index = (self.cursor_index - 1) % len(self.commands)
        self.update_cursor()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        self.cursor_index = (self.cursor_index + 1) % len(self.commands)
        self.update_cursor()

    def action_select(self) -> None:
        """Select current item."""
        cmd_id, _ = self.commands[self.cursor_index]
        self.post_message(self.CommandSelected(cmd_id))
        self.dismiss()

    def on_click(self, event: events.Click) -> None:
        """Handle click on items."""
        for i, (cmd_id, _) in enumerate(self.commands):
            try:
                item = self.query_one(f"#{cmd_id}", Static)
                if item.region.contains(event.screen_x, event.screen_y):
                    self.cursor_index = i
                    self.action_select()
                    break
            except Exception:
                pass
