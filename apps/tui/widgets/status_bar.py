"""Status bar widget for AG3NT TUI."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Static


class ConnectionStatus(Enum):
    """Connection status states."""

    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


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

    StatusBar .status-connection {
        width: auto;
        padding: 0 1;
    }

    StatusBar .status-connection.connected {
        color: #10b981;
    }

    StatusBar .status-connection.connecting {
        color: #f59e0b;
    }

    StatusBar .status-connection.disconnected {
        color: #ef4444;
    }

    StatusBar .status-connection.error {
        color: #ef4444;
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

    StatusBar .auto-approve-on {
        color: #10b981;
    }

    StatusBar .auto-approve-off {
        color: #f59e0b;
    }
    """

    mode: reactive[str] = reactive("normal", init=False)
    status_message: reactive[str] = reactive("", init=False)
    auto_approve: reactive[bool] = reactive(False)
    go_mode: reactive[bool] = reactive(False)
    token_count: reactive[int] = reactive(0)
    connection_status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)

    CONNECTION_SYMBOLS = {
        ConnectionStatus.CONNECTED: ("●", "Connected"),
        ConnectionStatus.CONNECTING: ("◐", "Connecting"),
        ConnectionStatus.DISCONNECTED: ("○", "Offline"),
        ConnectionStatus.ERROR: ("✗", "Error"),
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_id: Optional[str] = None
        self._response_time: Optional[float] = None
        self._message_count: int = 0

    def compose(self) -> ComposeResult:
        yield Static("○", classes="status-connection disconnected", id="connection-indicator")
        yield Static("", classes="status-mode normal", id="mode-indicator")
        yield Static("", classes="status-message", id="status-message")
        yield Static("", classes="status-info", id="status-info")

    def watch_connection_status(self, status: ConnectionStatus) -> None:
        """Update connection indicator when status changes."""
        try:
            indicator = self.query_one("#connection-indicator", Static)
        except NoMatches:
            return
        # Update CSS class
        for s in ConnectionStatus:
            indicator.remove_class(s.value)
        indicator.add_class(status.value)
        # Update symbol
        symbol, _ = self.CONNECTION_SYMBOLS.get(status, ("?", "Unknown"))
        indicator.update(symbol)

    def set_connected(self) -> None:
        """Set connection status to connected."""
        self.connection_status = ConnectionStatus.CONNECTED

    def set_disconnected(self) -> None:
        """Set connection status to disconnected."""
        self.connection_status = ConnectionStatus.DISCONNECTED

    def set_connecting(self) -> None:
        """Set connection status to connecting."""
        self.connection_status = ConnectionStatus.CONNECTING

    def set_connection_error(self) -> None:
        """Set connection status to error."""
        self.connection_status = ConnectionStatus.ERROR

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

    def watch_auto_approve(self, value: bool) -> None:
        self._refresh_info()

    def watch_go_mode(self, value: bool) -> None:
        self._refresh_info()

    def watch_token_count(self, value: int) -> None:
        self._refresh_info()

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
        if self.token_count > 0:
            if self.token_count >= 1000:
                parts.append(f"🎫 {self.token_count / 1000:.1f}K")
            else:
                parts.append(f"🎫 {self.token_count}")
        # GO mode takes precedence over auto-approve display
        if self.go_mode:
            parts.append("[bold #ef4444]GO[/bold #ef4444]")
        elif self.auto_approve:
            parts.append("[green]auto[/green]")
        else:
            parts.append("[#f59e0b]manual[/#f59e0b]")
        parts.append("F1=Help")
        info.update(" │ ".join(parts))
