#!/usr/bin/env python3
"""AG3NT TUI - A high-quality terminal interface for AG3NT.

Usage:
    python ag3nt_tui.py
    python -m ag3nt_tui

Environment:
    AG3NT_GATEWAY_URL - Gateway URL (auto-detected or default: http://127.0.0.1:18789)
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Optional

import httpx
from dotenv import load_dotenv
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Container, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Footer,
    Header,
    Static,
    TextArea,
    Button,
    Label,
)


load_dotenv()

# Default ports to probe in order
DEFAULT_PORTS = [18789, 18790, 18791, 18792, 18793]


def discover_gateway_url() -> str:
    """Discover the Gateway URL by:
    1. Checking AG3NT_GATEWAY_URL environment variable
    2. Reading from ~/.ag3nt/runtime.json (written by start.ps1)
    3. Probing default ports for a live Gateway
    """
    # 1. Environment variable takes precedence
    env_url = os.getenv("AG3NT_GATEWAY_URL")
    if env_url:
        return env_url

    # 2. Try to read from runtime.json
    runtime_path = Path.home() / ".ag3nt" / "runtime.json"
    try:
        if runtime_path.exists():
            content = runtime_path.read_text(encoding="utf-8")
            runtime = json.loads(content)
            gateway_url = runtime.get("gatewayUrl")
            if gateway_url:
                # Verify the Gateway is actually responding
                try:
                    resp = httpx.get(f"{gateway_url}/api/health", timeout=2.0)
                    if resp.status_code == 200:
                        return gateway_url
                except Exception:
                    # Gateway from runtime.json is not responding, continue to probe
                    pass
    except Exception:
        # Ignore errors reading runtime.json
        pass

    # 3. Probe default ports
    for port in DEFAULT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            resp = httpx.get(f"{url}/api/health", timeout=1.0)
            if resp.status_code == 200:
                return url
        except Exception:
            # Port not responding, try next
            pass

    # Fallback to default
    return "http://127.0.0.1:18789"


GATEWAY_URL = discover_gateway_url()
VERSION = "0.1.0"

# ═══════════════════════════════════════════════════════════════════════════════
# SLEEK DARK THEME - Sophisticated color palette inspired by modern AI interfaces
# ═══════════════════════════════════════════════════════════════════════════════

# Color Palette
COLORS = {
    "bg_dark": "#0d0d0d",        # Deep black background
    "bg_main": "#171717",        # Main background (like ChatGPT)
    "bg_surface": "#1e1e1e",     # Elevated surface
    "bg_input": "#2f2f2f",       # Input field background
    "bg_hover": "#3a3a3a",       # Hover state
    "border": "#3a3a3a",         # Subtle borders
    "border_focus": "#6366f1",   # Focus border (indigo)
    "text_primary": "#ececec",   # Primary text
    "text_secondary": "#a1a1a1", # Secondary/muted text
    "text_dim": "#6b6b6b",       # Dimmed text
    "accent": "#10b981",         # Primary accent (emerald green)
    "accent_alt": "#6366f1",     # Secondary accent (indigo)
    "error": "#ef4444",          # Error red
    "warning": "#f59e0b",        # Warning amber
    "success": "#10b981",        # Success green
    "bash": "#ec4899",           # Bash mode (pink)
    "command": "#8b5cf6",        # Command mode (purple)
}

# AP3X ASCII Art Banner - Clean, no box (X in red!)
AP3X_ASCII = """
  [bold #ececec]█████╗  ██████╗  ██████╗[/bold #ececec] [bold #ef4444]██╗  ██╗[/bold #ef4444]
 [bold #ececec]██╔══██╗ ██╔══██╗ ╚════██╗[/bold #ececec][bold #ef4444]╚██╗██╔╝[/bold #ef4444]
 [bold #ececec]███████║ ██████╔╝  █████╔╝[/bold #ececec] [bold #ef4444]╚███╔╝[/bold #ef4444]
 [bold #ececec]██╔══██║ ██╔═══╝   ╚═══██╗[/bold #ececec] [bold #ef4444]██╔██╗[/bold #ef4444]
 [bold #ececec]██║  ██║ ██║      ██████╔╝[/bold #ececec][bold #ef4444]██╔╝ ██╗[/bold #ef4444]
 [bold #ececec]╚═╝  ╚═╝ ╚═╝      ╚═════╝[/bold #ececec] [bold #ef4444]╚═╝  ╚═╝[/bold #ef4444]
"""


class WelcomeBanner(Static):
    """Welcome banner with AP3X ASCII art - Sleek dark theme."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        padding: 1 2;
        margin: 1 0;
        text-align: center;
    }
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the welcome banner."""
        banner_text = f"{AP3X_ASCII}\n"
        banner_text += f"[#a1a1a1]v{VERSION}[/#a1a1a1]  [#6b6b6b]•[/#6b6b6b]  [#6b6b6b]{GATEWAY_URL}[/#6b6b6b]\n\n"
        banner_text += "[#10b981]What would you like to build today?[/#10b981]\n\n"
        banner_text += "[#6b6b6b]╭──────────────────────────────────────────────────────────╮[/#6b6b6b]\n"
        banner_text += "[#6b6b6b]│[/#6b6b6b]  [#a1a1a1]Enter[/#a1a1a1] send  [#6b6b6b]•[/#6b6b6b]  [#a1a1a1]Ctrl+J[/#a1a1a1] newline  [#6b6b6b]•[/#6b6b6b]  [#a1a1a1]F1[/#a1a1a1] help  [#6b6b6b]•[/#6b6b6b]  [#ec4899]![/#ec4899] bash  [#6b6b6b]│[/#6b6b6b]\n"
        banner_text += "[#6b6b6b]╰──────────────────────────────────────────────────────────╯[/#6b6b6b]"
        super().__init__(banner_text, **kwargs)


class CommandPalette(ModalScreen):
    """Command palette modal screen."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("enter", "select", "Select"),
    ]

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
            ("cmd-copy-session", "Copy Session ID"),
            ("cmd-session-info", "View Session Info"),
            ("cmd-control-panel", "Open Control Panel"),
            ("cmd-node-status", "View Node Status"),
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


class HelpScreen(ModalScreen):
    """Help modal screen."""

    BINDINGS = [("escape", "dismiss", "Close"), ("f1", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        help_text = """
## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **Enter** | Send message |
| **Ctrl+J / Shift+Enter** | New line in input |
| **Ctrl+L** | Clear chat |
| **Ctrl+P** | Command palette |
| **Ctrl+C** | Quit (double press) |
| **Escape** | Interrupt / Close dialogs |
| **F1** | Show this help |
| **Up/Down** | History navigation |

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/clear` | Clear chat and start new session |
| `/quit` | Exit the TUI |
| `/status` | Show connection status |
| `/nodes` | Show connected nodes |
| `/tokens` | Show token usage |

## Bash Commands

| Prefix | Description |
|--------|-------------|
| `!command` | Execute bash command directly |

## Tips

- The agent may take a while to respond to complex queries
- Code blocks in responses have syntax highlighting
- Response time is shown in the status bar
- Press Escape to interrupt a running agent
"""
        yield Container(
            Static(Markdown(help_text), id="help-content"),
            Button("Close", id="help-close", variant="primary"),
            id="help-dialog",
        )

    @on(Button.Pressed, "#help-close")
    def close_help(self) -> None:
        self.dismiss()


class UserMessage(Static):
    """Widget displaying a user message - Sleek dark theme."""

    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #2f2f2f;
        border-left: wide #6366f1;
    }
    """

    def __init__(self, content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._content = content

    def compose(self) -> ComposeResult:
        text = Text()
        text.append("› ", style="bold #6366f1")
        text.append(self._content, style="#ececec")
        yield Static(text)


class AssistantMessage(Vertical):
    """Widget displaying an assistant message with markdown support - Sleek dark theme."""

    DEFAULT_CSS = """
    AssistantMessage {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #1e1e1e;
        border-left: wide #10b981;
    }

    AssistantMessage .assistant-header {
        height: auto;
        margin-bottom: 1;
    }

    AssistantMessage .assistant-content {
        height: auto;
        color: #ececec;
    }
    """

    def __init__(self, content: str = "", response_time: Optional[float] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._content = content
        self._response_time = response_time

    def compose(self) -> ComposeResult:
        time_info = ""
        if self._response_time:
            time_info = f" [#6b6b6b]• {self._response_time:.1f}s[/#6b6b6b]"
        yield Static(f"[bold #10b981]AP3X[/bold #10b981]{time_info}", classes="assistant-header")
        yield Static(Markdown(self._content), classes="assistant-content")


class SystemMessage(Static):
    """Widget displaying a system message - Terminal style with syntax highlighting."""

    DEFAULT_CSS = """
    SystemMessage {
        height: auto;
        padding: 0 4;
        margin: 0 0;
        text-align: left;
    }
    """

    # Keywords to highlight with colors
    HIGHLIGHTS = {
        # Success/positive keywords - green
        "Connected": "#10b981",
        "approved": "#10b981",
        "Ready": "#10b981",
        "Success": "#10b981",
        "OK": "#10b981",
        "Done": "#10b981",
        # Action keywords - cyan
        "Connecting": "#22d3ee",
        "Auto-approving": "#22d3ee",
        "Opening": "#22d3ee",
        "Resending": "#22d3ee",
        "Starting": "#22d3ee",
        "Clearing": "#22d3ee",
        # Important items - yellow/amber
        "Gateway": "#fbbf24",
        "Session": "#f59e0b",
        "Node": "#f59e0b",
        # Identifiers/codes - purple
        "code:": "#a78bfa",
        "tui-": "#a78bfa",
    }

    def __init__(self, message: str, **kwargs) -> None:
        text = Text()
        text.append("→ ", style="bold #6b6b6b")

        # Apply syntax highlighting
        remaining = message
        while remaining:
            # Check for AP3X first (special case: white AP3 + red X)
            ap3x_pos = remaining.find("AP3X")

            # Find the earliest keyword match
            earliest_pos = len(remaining)
            earliest_keyword = None
            earliest_color = None

            for keyword, color in self.HIGHLIGHTS.items():
                pos = remaining.find(keyword)
                if pos != -1 and pos < earliest_pos:
                    earliest_pos = pos
                    earliest_keyword = keyword
                    earliest_color = color

            # AP3X takes priority if it comes before or at the same position
            if ap3x_pos != -1 and (ap3x_pos < earliest_pos or earliest_keyword == "AP3X"):
                # Add text before AP3X
                if ap3x_pos > 0:
                    text.append(remaining[:ap3x_pos], style="#a1a1a1")
                # Add AP3 in white, X in red
                text.append("AP3", style="bold #ececec")
                text.append("X", style="bold #ef4444")
                remaining = remaining[ap3x_pos + 4:]
            elif earliest_keyword:
                # Add text before the keyword
                if earliest_pos > 0:
                    text.append(remaining[:earliest_pos], style="#a1a1a1")
                # Add the highlighted keyword
                text.append(earliest_keyword, style=f"bold {earliest_color}")
                # Continue with the rest
                remaining = remaining[earliest_pos + len(earliest_keyword):]
            else:
                # No more keywords, add the rest
                text.append(remaining, style="#a1a1a1")
                break

        super().__init__(text, **kwargs)


class ErrorMessage(Static):
    """Widget displaying an error message - Sleek dark theme."""

    DEFAULT_CSS = """
    ErrorMessage {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #2d1b1b;
        border-left: wide #ef4444;
    }
    """

    def __init__(self, error: str, **kwargs) -> None:
        text = Text()
        text.append("✕ ", style="bold #ef4444")
        text.append(error, style="#ececec")
        super().__init__(text, **kwargs)


class BashOutputMessage(Vertical):
    """Widget displaying bash command output - Sleek dark theme."""

    DEFAULT_CSS = """
    BashOutputMessage {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #1a1a2e;
        border-left: wide #ec4899;
    }

    BashOutputMessage .bash-command {
        height: auto;
        margin-bottom: 1;
    }

    BashOutputMessage .bash-output {
        height: auto;
        color: #a1a1a1;
    }
    """

    def __init__(self, command: str, output: str, exit_code: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._command = command
        self._output = output
        self._exit_code = exit_code

    def compose(self) -> ComposeResult:
        yield Static(f"[bold #ec4899]$[/bold #ec4899] [#ececec]{self._command}[/#ececec]", classes="bash-command")
        if self._output:
            yield Static(Text(self._output, style="#a1a1a1"), classes="bash-output")
        if self._exit_code != 0:
            yield Static(f"[#ef4444]Exit code: {self._exit_code}[/#ef4444]")


class LoadingWidget(Static):
    """Animated loading indicator - Sleek dark theme."""

    DEFAULT_CSS = """
    LoadingWidget {
        height: auto;
        padding: 1 2;
        margin: 0 2;
        background: #1e1e1e;
        border-left: wide #6366f1;
    }
    """

    # Elegant dot animation
    SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, status: str = "Thinking") -> None:
        super().__init__()
        self._status = status
        self._frame = 0
        self._start_time: Optional[float] = None
        self._paused = False

    def on_mount(self) -> None:
        self._start_time = time.time()
        self.set_interval(0.08, self._update_animation)

    def _update_animation(self) -> None:
        if self._paused:
            return
        self._frame = (self._frame + 1) % len(self.SPINNER_FRAMES)
        self.refresh()

    def render(self) -> Text:
        text = Text()
        frame = self.SPINNER_FRAMES[self._frame]
        text.append(f"{frame} ", style="bold #6366f1")
        text.append(f"{self._status}", style="#a1a1a1")
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            text.append(f" • {elapsed}s", style="#6b6b6b")
        return text

    def set_status(self, status: str) -> None:
        self._status = status
        self.refresh()

    def pause(self, status: str = "Awaiting decision") -> None:
        self._paused = True
        self._status = status
        self.refresh()

    def resume(self) -> None:
        self._paused = False
        self._status = "Thinking"


class StatusBar(Horizontal):
    """Status bar - Sleek dark theme."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: #0d0d0d;
        padding: 0 2;
        border-top: solid #3a3a3a;
    }

    StatusBar .status-mode {
        width: auto;
        padding: 0 1;
        margin-right: 1;
    }

    StatusBar .status-mode.normal {
        display: none;
    }

    StatusBar .status-mode.bash {
        background: #ec4899;
        color: #0d0d0d;
        text-style: bold;
    }

    StatusBar .status-mode.command {
        background: #8b5cf6;
        color: #0d0d0d;
        text-style: bold;
    }

    StatusBar .status-message {
        width: 1fr;
        padding: 0 1;
        color: #6b6b6b;
    }

    StatusBar .status-info {
        width: auto;
        padding: 0 1;
        color: #6b6b6b;
    }
    """

    mode: reactive[str] = reactive("normal", init=False)
    status_message: reactive[str] = reactive("", init=False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_id: Optional[str] = None
        self._response_time: Optional[float] = None
        self._message_count: int = 0

    def compose(self) -> ComposeResult:
        yield Static("", classes="status-mode normal", id="mode-indicator")
        yield Static("", classes="status-message", id="status-message")
        yield Static("", classes="status-info", id="status-info")

    def watch_mode(self, mode: str) -> None:
        try:
            indicator = self.query_one("#mode-indicator", Static)
        except NoMatches:
            return
        indicator.remove_class("normal", "bash", "command")
        if mode == "bash":
            indicator.update(" BASH ")
            indicator.add_class("bash")
        elif mode == "command":
            indicator.update(" CMD ")
            indicator.add_class("command")
        else:
            indicator.update("")
            indicator.add_class("normal")

    def watch_status_message(self, new_value: str) -> None:
        try:
            msg_widget = self.query_one("#status-message", Static)
        except NoMatches:
            return
        msg_widget.update(new_value)

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_status_message(self, message: str) -> None:
        self.status_message = message

    def update_info(
        self,
        session_id: Optional[str] = None,
        response_time: Optional[float] = None,
        increment_messages: bool = False,
    ) -> None:
        if session_id is not None:
            self._session_id = session_id
        if response_time is not None:
            self._response_time = response_time
        if increment_messages:
            self._message_count += 1
        self._refresh_info()

    def _refresh_info(self) -> None:
        try:
            info = self.query_one("#status-info", Static)
        except NoMatches:
            return
        parts = []
        if self._session_id:
            parts.append(f"📍 {self._session_id[:8]}")
        if self._response_time:
            parts.append(f"⏱ {self._response_time:.1f}s")
        parts.append(f"💬 {self._message_count}")
        parts.append("F1=Help")
        info.update(" │ ".join(parts))


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


class AG3NTApp(App):
    """AG3NT Terminal User Interface - Sleek Dark Theme Edition."""

    # Very smooth scrolling
    SCROLL_SENSITIVITY_Y = 0.25

    # Sleek dark theme CSS
    CSS = """
    /* ═══════════════════════════════════════════════════════════════════════════
       SLEEK DARK THEME - Sophisticated, minimal, modern
       ═══════════════════════════════════════════════════════════════════════════ */

    Screen {
        background: #171717;
        layout: grid;
        grid-size: 1;
        grid-rows: 1fr auto auto auto;
    }

    /* Header styling */
    Header {
        background: #0d0d0d;
        color: #ececec;
        border-bottom: solid #3a3a3a;
    }

    HeaderTitle {
        color: #10b981;
        text-style: bold;
    }

    /* Main chat container */
    #chat-container {
        margin: 0;
        padding: 1 0;
        scrollbar-gutter: stable;
        background: #171717;
        scrollbar-background: #171717;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #6366f1;
        scrollbar-color-active: #10b981;
    }

    #welcome-banner {
        text-align: center;
        margin: 2 0;
    }

    /* Loading container */
    #loading-container {
        height: auto;
        margin: 0;
        padding: 0;
    }

    #loading-container.hidden {
        display: none;
    }

    /* Input wrapper */
    #input-wrapper {
        height: auto;
        margin: 0;
        padding: 0;
        background: #171717;
    }

    /* Command Palette - modal overlay style */
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

    /* Help dialog - sleek modal */
    #help-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
        background: #1e1e1e;
        border: solid #3a3a3a;
        padding: 2;
    }

    #help-content {
        height: auto;
        max-height: 60;
        overflow-y: auto;
        color: #ececec;
    }

    #help-close {
        margin-top: 2;
        width: 100%;
        background: #6366f1;
        color: #ececec;
        border: none;
    }

    #help-close:hover {
        background: #4f46e5;
    }

    HelpScreen {
        align: center middle;
        background: #0d0d0d 90%;
    }

    /* Footer styling */
    Footer {
        background: #0d0d0d;
        color: #6b6b6b;
        border-top: solid #3a3a3a;
    }

    FooterKey {
        background: transparent;
        color: #6b6b6b;
    }

    FooterKey .footer-key--key {
        background: #2f2f2f;
        color: #a1a1a1;
    }

    FooterKey:hover {
        background: #2f2f2f;
    }

    FooterKey:hover .footer-key--key {
        background: #6366f1;
        color: #ececec;
    }

    /* Button styling */
    Button {
        background: #2f2f2f;
        color: #ececec;
        border: solid #3a3a3a;
    }

    Button:hover {
        background: #3a3a3a;
        border: solid #6366f1;
    }

    Button.-primary {
        background: #6366f1;
        color: #ececec;
        border: none;
    }

    Button.-primary:hover {
        background: #4f46e5;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("f1", "help", "Help", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    TITLE = "AP3X"
    SUB_TITLE = "Personal AI Assistant"

    def __init__(self) -> None:
        super().__init__()
        self.session_id: Optional[str] = None
        # Long timeout for complex agent responses (5 minutes)
        self.http_client = httpx.AsyncClient(base_url=GATEWAY_URL, timeout=300.0)
        self._pending_request = False
        self._request_start_time: Optional[float] = None
        self._loading_widget: Optional[LoadingWidget] = None
        self._command_history: list[str] = []
        self._history_index: int = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            WelcomeBanner(id="welcome-banner"),
            id="chat-container",
        )
        yield Container(id="loading-container", classes="hidden")
        yield Container(ChatInput(id="chat-input"), id="input-wrapper")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_ready(self) -> None:
        """Focus the input when app is ready."""
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.focus_input()

    def on_click(self, event: events.Click) -> None:
        """Focus the input when clicking anywhere."""
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.focus_input()

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_command_palette(self) -> None:
        """Show command palette."""
        self.push_screen(CommandPalette())

    def on_command_palette_command_selected(self, event: CommandPalette.CommandSelected) -> None:
        """Handle command selection from palette."""
        command_id = event.command_id

        if command_id == "cmd-reconnect":
            self.check_gateway()
        elif command_id == "cmd-clear":
            self.action_clear()
        elif command_id == "cmd-copy-session":
            if self.session_id:
                # On Windows, use clip; on Unix, try pbcopy/xclip
                import subprocess
                import platform
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["clip"], input=self.session_id.encode(), check=True)
                    elif platform.system() == "Darwin":
                        subprocess.run(["pbcopy"], input=self.session_id.encode(), check=True)
                    else:
                        subprocess.run(["xclip", "-selection", "clipboard"], input=self.session_id.encode(), check=True)
                    self.add_system_message(f"Session ID copied to clipboard: {self.session_id}")
                except Exception as e:
                    self.add_system_message(f"Session ID: {self.session_id} (copy failed: {e})")
            else:
                self.add_system_message("No active session")
        elif command_id == "cmd-session-info":
            if self.session_id:
                self.add_system_message(f"Session ID: {self.session_id}")
            else:
                self.add_system_message("No active session")
        elif command_id == "cmd-control-panel":
            import webbrowser
            webbrowser.open("http://127.0.0.1:18789/")
            self.add_system_message("Opening Control Panel in browser...")
        elif command_id == "cmd-node-status":
            self.show_node_status()
        elif command_id == "cmd-help":
            self.action_help()
        elif command_id == "cmd-quit":
            self.action_quit()

    @work(exclusive=False, thread=False)
    async def show_node_status(self) -> None:
        """Show node status information."""
        try:
            resp = await self.http_client.get("/api/nodes/status")
            if resp.status_code == 200:
                data = resp.json()
                local = data.get("localNode", {})
                node_name = local.get("name", "Unknown")
                node_type = local.get("type", "Unknown")
                caps = local.get("capabilities", [])
                caps_str = ", ".join(caps) if caps else "None"

                self.add_system_message(
                    f"Node: {node_name}\n"
                    f"Type: {node_type}\n"
                    f"Capabilities: {caps_str}"
                )
            else:
                self.add_error_message(f"Failed to get node status: {resp.status_code}")
        except Exception as e:
            self.add_error_message(f"Error getting node status: {e}")

    async def on_mount(self) -> None:
        """Initialize the app on mount."""
        self.add_system_message("Connecting to AP3X...")
        self.check_gateway()

    def on_chat_input_mode_changed(self, event: ChatInput.ModeChanged) -> None:
        """Handle mode change from chat input."""
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_mode(event.mode)
        except NoMatches:
            pass

    @work(exclusive=True, thread=False)
    async def check_gateway(self) -> None:
        """Check gateway connection and initialize session."""
        status_bar = self.query_one("#status-bar", StatusBar)
        try:
            # Check health
            resp = await self.http_client.get("/api/health")
            if resp.status_code == 200:
                status_bar.set_status_message("Connected to AP3X")
                self.add_system_message("Connected to AP3X!")

                # Get node info
                node_resp = await self.http_client.get("/api/nodes/status")
                if node_resp.status_code == 200:
                    data = node_resp.json()
                    local = data.get("localNode", {})
                    node_name = local.get("name", "Unknown")
                    status_bar.set_status_message(f"Node: {node_name}")

                # Create session
                await self.create_session()
            else:
                status_bar.set_status_message("Gateway error")
                self.add_error_message(f"Gateway returned {resp.status_code}")
        except httpx.ConnectError:
            status_bar.set_status_message("Gateway disconnected")
            self.add_error_message(
                f"Cannot connect to Gateway at {GATEWAY_URL}\n"
                "Make sure the Gateway is running: cd apps/gateway && node dist/index.js"
            )
        except Exception as e:
            status_bar.set_status_message("Error")
            self.add_error_message(f"Error: {e}")

    async def create_session(self) -> None:
        """Create and auto-approve a new session for local dev."""
        self.session_id = f"tui-{uuid.uuid4()}"
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(session_id=self.session_id)

        # Send initial message to trigger session creation
        try:
            resp = await self.http_client.post(
                "/api/chat",
                json={"text": "hello", "session_id": self.session_id},
            )
            data = resp.json()

            # Check if pairing is needed (API uses camelCase)
            if data.get("pairingRequired") or data.get("pairing_required"):
                code = data.get("pairingCode") or data.get("pairing_code", "")
                session_key = data.get("session_id", self.session_id)
                self.add_system_message(f"Session requires approval (code: {code}). Auto-approving...")

                # Auto-approve for local TUI - use the session key from response
                approve_resp = await self.http_client.post(
                    f"/api/sessions/cli:local:{session_key}/approve",
                    json={"approved": True, "code": code},
                )
                if approve_resp.status_code == 200:
                    self.add_system_message("Session approved! Ready to chat.")
                else:
                    error_data = approve_resp.json()
                    self.add_error_message(f"Failed to approve: {error_data}")
            elif data.get("ok"):
                self.add_system_message("Session ready! Type a message to start.")
            else:
                # Session created but got an error - might need different handling
                self.add_system_message("Session created. Type a message to start.")
        except Exception as e:
            self.add_error_message(f"Session error: {e}")

    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(UserMessage(content))
        container.scroll_end(animate=True)
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(increment_messages=True)

    def add_assistant_message(self, content: str, response_time: Optional[float] = None) -> None:
        """Add an assistant message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(AssistantMessage(content, response_time=response_time))
        container.scroll_end(animate=True)
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(response_time=response_time, increment_messages=True)

    def add_system_message(self, content: str) -> None:
        """Add a system message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(SystemMessage(content))
        container.scroll_end(animate=True)

    def add_error_message(self, content: str) -> None:
        """Add an error message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(ErrorMessage(content))
        container.scroll_end(animate=True)

    def add_bash_output(self, command: str, output: str, exit_code: int = 0) -> None:
        """Add a bash command output to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(BashOutputMessage(command, output, exit_code))
        container.scroll_end(animate=True)

    def show_loading(self, show: bool = True, status: str = "Thinking") -> None:
        """Show/hide loading indicator."""
        loading_container = self.query_one("#loading-container", Container)
        if show:
            loading_container.remove_class("hidden")
            # Create and mount the loading widget
            if self._loading_widget is None:
                self._loading_widget = LoadingWidget(status)
                loading_container.mount(self._loading_widget)
            else:
                self._loading_widget.set_status(status)
            # Disable input while loading
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.set_submit_enabled(False)
        else:
            loading_container.add_class("hidden")
            # Remove loading widget
            if self._loading_widget is not None:
                self._loading_widget.remove()
                self._loading_widget = None
            # Re-enable input
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.set_submit_enabled(True)
            chat_input.focus_input()

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle message submission from ChatInput."""
        text = event.value
        mode = event.mode
        if not text or self._pending_request:
            return

        # Add to command history
        self._command_history.append(text)
        self._history_index = len(self._command_history)

        # Handle bash commands (! prefix)
        if mode == "bash" or text.startswith("!"):
            cmd = text[1:] if text.startswith("!") else text
            self.add_user_message(f"!{cmd}")
            self.run_bash_command(cmd)
            return

        # Handle slash commands
        if mode == "command" or text.startswith("/"):
            cmd = text.lower().strip()
            if cmd in ("/quit", "/exit", "/q"):
                self.exit()
                return
            if cmd in ("/clear", "/cls"):
                self.action_clear()
                return
            if cmd == "/help":
                self.action_help()
                return
            if cmd == "/status":
                self.add_system_message(f"Session: {self.session_id or 'None'}")
                return
            if cmd == "/nodes":
                self.fetch_node_info()
                return
            if cmd == "/tokens":
                self.add_system_message("Token tracking not yet implemented.")
                return
            # Unknown command
            self.add_error_message(f"Unknown command: {cmd}")
            return

        # Regular message - send to agent
        self.add_user_message(text)
        self.send_message(text)

    @work(exclusive=True, thread=False)
    async def run_bash_command(self, command: str) -> None:
        """Run a bash command and display output."""
        self.show_loading(True, "Running command")
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout + result.stderr
            self.add_bash_output(command, output.strip(), result.returncode)
        except subprocess.TimeoutExpired:
            self.add_error_message(f"Command timed out: {command}")
        except Exception as e:
            self.add_error_message(f"Command error: {e}")
        finally:
            self.show_loading(False)

    @work(exclusive=True, thread=False)
    async def fetch_node_info(self) -> None:
        """Fetch and display node information."""
        try:
            resp = await self.http_client.get("/api/nodes")
            if resp.status_code == 200:
                data = resp.json()
                nodes = data.get("nodes", [])
                if nodes:
                    info = "**Connected Nodes:**\n\n"
                    for node in nodes:
                        info += f"- **{node.get('name', 'Unknown')}** ({node.get('type', 'unknown')})\n"
                        caps = node.get("capabilities", [])
                        if caps:
                            info += f"  Capabilities: {', '.join(caps)}\n"
                    self.add_assistant_message(info)
                else:
                    self.add_system_message("No nodes connected.")
            else:
                self.add_error_message(f"Failed to fetch nodes: {resp.status_code}")
        except Exception as e:
            self.add_error_message(f"Error fetching nodes: {e}")

    @work(exclusive=True, thread=False)
    async def send_message(self, text: str) -> None:
        """Send message to the agent with response time tracking."""
        self._pending_request = True
        self._request_start_time = time.time()
        self.show_loading(True)

        try:
            resp = await self.http_client.post(
                "/api/chat",
                json={"text": text, "session_id": self.session_id},
            )
            data = resp.json()

            # Check if pairing is required (session expired or new)
            if data.get("pairingRequired") or data.get("pairing_required"):
                code = data.get("pairingCode") or data.get("pairing_code", "")
                session_key = data.get("session_id", self.session_id)
                self.add_system_message(
                    f"Session needs re-approval (code: {code}). Auto-approving..."
                )

                # Auto-approve
                approve_resp = await self.http_client.post(
                    f"/api/sessions/cli:local:{session_key}/approve",
                    json={"approved": True, "code": code},
                )
                if approve_resp.status_code == 200:
                    self.add_system_message("Re-approved! Resending message...")
                    # Resend the message
                    resp2 = await self.http_client.post(
                        "/api/chat",
                        json={"text": text, "session_id": self.session_id},
                    )
                    data = resp2.json()
                else:
                    self.add_error_message("Failed to re-approve session")
                    return

            # Calculate response time
            response_time = time.time() - self._request_start_time

            if data.get("ok"):
                agent_text = data.get("text", "")
                if agent_text:
                    self.add_assistant_message(agent_text, response_time=response_time)
                else:
                    self.add_system_message("(Agent returned empty response)")
            else:
                # Show the text if available (might be an error message from agent)
                agent_text = data.get("text", "")
                if agent_text:
                    self.add_assistant_message(agent_text, response_time=response_time)
                else:
                    error = data.get("error", "Unknown error")
                    self.add_error_message(f"API Error: {error}")
        except httpx.TimeoutException:
            self.add_error_message(
                "Request timed out (5 min). The agent may still be processing."
            )
        except Exception as e:
            self.add_error_message(f"Error: {e}")
        finally:
            self._pending_request = False
            self.show_loading(False)

    def action_clear(self) -> None:
        """Clear chat history and create new session."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.remove_children()
        # Mount welcome banner again
        container.mount(WelcomeBanner(id="welcome-banner"))
        self.add_system_message("Chat cleared. Starting new session...")
        # Create new session
        self.session_id = f"tui-{uuid.uuid4()}"
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(session_id=self.session_id)

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_cancel(self) -> None:
        """Cancel current operation."""
        if self._pending_request:
            self.add_system_message("(Cancellation not supported yet)")

    async def on_unmount(self) -> None:
        """Cleanup on exit."""
        await self.http_client.aclose()


def main() -> None:
    """Run the AP3X TUI."""
    app = AG3NTApp()
    app.run()


if __name__ == "__main__":
    main()

