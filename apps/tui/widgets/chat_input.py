"""Chat input widget for AG3NT TUI."""

from __future__ import annotations

from typing import ClassVar, Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, TextArea


class ChatTextArea(TextArea):
    """TextArea subclass with custom key handling for chat input."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+j", "insert_newline", "New Line", show=False, priority=True),
        Binding("shift+enter", "insert_newline", "New Line", show=False, priority=True),
    ]

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class HistoryNavigate(Message):
        """Request history navigation."""
        def __init__(self, direction: str, current_input: str) -> None:
            self.direction = direction  # "up" or "down"
            self.current_input = current_input
            super().__init__()

    def __init__(self, **kwargs) -> None:
        kwargs.pop("placeholder", None)
        super().__init__(**kwargs)
        self._submit_enabled = True

    def action_insert_newline(self) -> None:
        self.insert("\n")

    async def _on_key(self, event: events.Key) -> None:
        if event.key in ("shift+enter", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            value = self.text.strip()
            if value and self._submit_enabled:
                self.post_message(self.Submitted(value))
            return
        # History navigation - only when on first/last line
        if event.key == "up":
            # Navigate history up when cursor is on first line
            cursor_row = self.cursor_location[0]
            if cursor_row == 0:
                event.prevent_default()
                event.stop()
                self.post_message(self.HistoryNavigate("up", self.text))
                return
        if event.key == "down":
            # Navigate history down when cursor is on last line
            cursor_row = self.cursor_location[0]
            line_count = self.text.count("\n") + 1
            if cursor_row >= line_count - 1:
                event.prevent_default()
                event.stop()
                self.post_message(self.HistoryNavigate("down", self.text))
                return
        await super()._on_key(event)

    def set_submit_enabled(self, enabled: bool) -> None:
        self._submit_enabled = enabled

    def clear_text(self) -> None:
        self.text = ""
        self.move_cursor((0, 0))


class ChatInput(Vertical):
    """Chat input widget - Sleek dark theme like ChatGPT."""

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        min-height: 3;
        max-height: 12;
        padding: 1;
        margin: 0 2 1 2;
        background: #2f2f2f;
        border: solid #3a3a3a;
    }

    ChatInput:focus-within {
        border: solid #6366f1;
    }

    ChatInput .input-row {
        height: auto;
        width: 100%;
    }

    ChatInput .input-prompt {
        width: 3;
        height: 1;
        padding: 0 1;
        color: #6366f1;
        text-style: bold;
    }

    ChatInput ChatTextArea {
        width: 1fr;
        height: auto;
        min-height: 1;
        max-height: 8;
        border: none;
        background: transparent;
        padding: 0;
        color: #ececec;
    }

    ChatInput ChatTextArea:focus {
        border: none;
    }
    """

    class Submitted(Message):
        def __init__(self, value: str, mode: str = "normal") -> None:
            super().__init__()
            self.value = value
            self.mode = mode

    class ModeChanged(Message):
        def __init__(self, mode: str) -> None:
            super().__init__()
            self.mode = mode

    mode: reactive[str] = reactive("normal")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._text_area: Optional[ChatTextArea] = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="input-row"):
            yield Static(">", classes="input-prompt", id="prompt")
            yield ChatTextArea(id="chat-input")

    def on_mount(self) -> None:
        self._text_area = self.query_one("#chat-input", ChatTextArea)
        self._text_area.focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        if text.startswith("!"):
            self.mode = "bash"
        elif text.startswith("/"):
            self.mode = "command"
        else:
            self.mode = "normal"

    def on_chat_text_area_submitted(self, event: ChatTextArea.Submitted) -> None:
        value = event.value
        if value:
            self.post_message(self.Submitted(value, self.mode))
            if self._text_area:
                self._text_area.clear_text()
            self.mode = "normal"

    def watch_mode(self, mode: str) -> None:
        self.post_message(self.ModeChanged(mode))

    def focus_input(self) -> None:
        if self._text_area:
            self._text_area.focus()

    @property
    def value(self) -> str:
        if self._text_area:
            return self._text_area.text
        return ""

    def set_submit_enabled(self, enabled: bool) -> None:
        if self._text_area:
            self._text_area.set_submit_enabled(enabled)

    def set_text(self, text: str) -> None:
        """Set the input text programmatically."""
        if self._text_area:
            self._text_area.text = text
            # Move cursor to end
            lines = text.split("\n")
            row = len(lines) - 1
            col = len(lines[-1]) if lines else 0
            self._text_area.move_cursor((row, col))
