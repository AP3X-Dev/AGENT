"""Keyboard shortcut hints widget for AG3NT TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual.reactive import reactive

if TYPE_CHECKING:
    pass


class KeyHint(Static):
    """Single keyboard shortcut hint.

    Displays a key combination and its action in a compact format.
    """

    DEFAULT_CSS = """
    KeyHint {
        width: auto;
        height: 1;
    }

    KeyHint .key {
        background: #2f2f2f;
        color: #a1a1a1;
        padding: 0 1;
    }

    KeyHint .action {
        color: #6b6b6b;
        padding: 0 1;
    }
    """

    def __init__(self, key: str, action: str, **kwargs) -> None:
        """Initialize key hint.

        Args:
            key: Key combination (e.g., "Ctrl+H")
            action: Action description (e.g., "History")
        """
        super().__init__(**kwargs)
        self.key = key
        self.action = action

    def compose(self) -> ComposeResult:
        yield Static(self.key, classes="key")
        yield Static(self.action, classes="action")


class HintsBar(Horizontal):
    """Bar showing contextual keyboard shortcuts.

    Updates based on the current context/mode.
    """

    DEFAULT_CSS = """
    HintsBar {
        height: 1;
        width: 100%;
        background: #0d0d0d;
        padding: 0 1;
        dock: bottom;
    }

    HintsBar .separator {
        color: #3a3a3a;
        padding: 0 1;
    }
    """

    context: reactive[str] = reactive("default")

    # Hint sets for different contexts
    HINT_SETS = {
        "default": [
            ("Enter", "Send"),
            ("Ctrl+L", "Clear"),
            ("Ctrl+P", "Commands"),
            ("Ctrl+H", "History"),
            ("F1", "Help"),
        ],
        "input": [
            ("Enter", "Send"),
            ("Shift+Enter", "New Line"),
            ("Up/Down", "History"),
            ("Esc", "Cancel"),
        ],
        "approval": [
            ("Y", "Approve"),
            ("N", "Reject"),
            ("A", "Auto-approve All"),
            ("Esc", "Cancel"),
        ],
        "modal": [
            ("Enter", "Select"),
            ("Esc", "Close"),
            ("Up/Down", "Navigate"),
        ],
        "session_browser": [
            ("Enter", "Resume"),
            ("Delete", "Remove"),
            ("R", "Refresh"),
            ("Esc", "Close"),
        ],
        "loading": [
            ("Esc", "Cancel"),
        ],
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._hints: list[tuple[str, str]] = []

    def on_mount(self) -> None:
        """Set default hints on mount."""
        self._update_hints()

    def watch_context(self, context: str) -> None:
        """Update hints when context changes."""
        self._update_hints()

    def _update_hints(self) -> None:
        """Update the displayed hints based on current context."""
        self._hints = self.HINT_SETS.get(self.context, self.HINT_SETS["default"])
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the hint display."""
        # Build hint text
        parts = []
        for key, action in self._hints:
            parts.append(f"[#2f2f2f on #171717] {key} [/][#6b6b6b] {action}[/]")

        hint_text = "  ".join(parts)
        self.update(hint_text)

    def set_context(self, context: str) -> None:
        """Set the current context for hints.

        Args:
            context: Context name (default, input, approval, modal, etc.)
        """
        self.context = context


class ContextualHints(Static):
    """Inline contextual hints that appear near relevant UI elements.

    Shows brief hints based on the current state.
    """

    DEFAULT_CSS = """
    ContextualHints {
        width: 100%;
        height: auto;
        text-align: center;
        color: #6b6b6b;
        padding: 0 1;
    }
    """

    visible: reactive[bool] = reactive(True)
    hint_text: reactive[str] = reactive("")

    def watch_visible(self, visible: bool) -> None:
        """Show/hide the hints."""
        self.display = visible

    def watch_hint_text(self, text: str) -> None:
        """Update the hint text."""
        self.update(text)

    def show_hint(self, text: str) -> None:
        """Show a hint message.

        Args:
            text: Hint text to display
        """
        self.hint_text = text
        self.visible = True

    def hide(self) -> None:
        """Hide the hints."""
        self.visible = False

    def show_input_hints(self) -> None:
        """Show input-related hints."""
        self.show_hint(
            "[dim]Enter[/] send • [dim]Shift+Enter[/] new line • "
            "[dim]![/] bash • [dim]/[/] command"
        )

    def show_approval_hints(self) -> None:
        """Show approval-related hints."""
        self.show_hint(
            "[dim]Y[/] approve • [dim]N[/] reject • [dim]A[/] auto-approve all"
        )

    def show_navigation_hints(self) -> None:
        """Show navigation hints."""
        self.show_hint(
            "[dim]Up/Down[/] navigate • [dim]Enter[/] select • [dim]Esc[/] close"
        )


class FirstRunHints(Static):
    """Welcome hints shown on first run.

    Provides a quick overview of key features for new users.
    """

    DEFAULT_CSS = """
    FirstRunHints {
        width: 100%;
        height: auto;
        padding: 2;
        margin: 1 2;
        background: #1e293b;
        border: solid #334155;
        text-align: center;
    }

    FirstRunHints .title {
        color: #10b981;
        text-style: bold;
        margin-bottom: 1;
    }

    FirstRunHints .hints-grid {
        margin: 1 0;
    }

    FirstRunHints .dismiss-hint {
        color: #6b6b6b;
        margin-top: 1;
    }
    """

    class Dismissed(Static):
        """User dismissed the first run hints."""
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Welcome to AP3X", classes="title")
        yield Static(
            "[#a1a1a1]Quick Start:[/]\n\n"
            "[#6366f1]Ctrl+P[/] Command palette  •  "
            "[#6366f1]Ctrl+H[/] Session history  •  "
            "[#6366f1]F1[/] Full help\n\n"
            "[#a1a1a1]Type a message and press Enter to start chatting.[/]",
            classes="hints-grid",
        )
        yield Static(
            "[dim]Press any key to dismiss[/]",
            classes="dismiss-hint",
        )

    def on_key(self) -> None:
        """Dismiss on any key press."""
        self.remove()
        self.post_message(self.Dismissed())


class ModeIndicator(Static):
    """Shows current input mode with visual indicator.

    Displays whether user is in normal, bash, or command mode.
    """

    DEFAULT_CSS = """
    ModeIndicator {
        width: auto;
        height: 1;
        padding: 0 1;
    }

    ModeIndicator.normal {
        color: #6366f1;
    }

    ModeIndicator.bash {
        color: #ec4899;
    }

    ModeIndicator.command {
        color: #10b981;
    }
    """

    mode: reactive[str] = reactive("normal")

    MODE_DISPLAY = {
        "normal": ("●", "Chat"),
        "bash": ("$", "Bash"),
        "command": ("/", "Command"),
    }

    def watch_mode(self, mode: str) -> None:
        """Update display when mode changes."""
        # Update CSS class
        for m in self.MODE_DISPLAY:
            self.remove_class(m)
        self.add_class(mode)

        # Update text
        symbol, label = self.MODE_DISPLAY.get(mode, ("?", "Unknown"))
        self.update(f"{symbol} {label}")
