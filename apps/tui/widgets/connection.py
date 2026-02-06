"""Connection status widget for AG3NT TUI."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Optional

from textual.reactive import reactive
from textual.widgets import Static

if TYPE_CHECKING:
    pass


class ConnectionState(Enum):
    """Connection state enumeration."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ConnectionIndicator(Static):
    """Visual indicator for gateway connection status.

    Shows a colored dot and status text that updates based on connection state.
    """

    DEFAULT_CSS = """
    ConnectionIndicator {
        width: auto;
        height: 1;
        padding: 0 1;
    }

    ConnectionIndicator.connected {
        color: #10b981;
    }

    ConnectionIndicator.connecting {
        color: #f59e0b;
    }

    ConnectionIndicator.disconnected {
        color: #ef4444;
    }

    ConnectionIndicator.reconnecting {
        color: #f59e0b;
    }

    ConnectionIndicator.error {
        color: #ef4444;
    }
    """

    state: reactive[ConnectionState] = reactive(ConnectionState.DISCONNECTED)
    _reconnect_attempt: int = 0
    _max_reconnect_attempts: int = 5

    STATE_DISPLAY = {
        ConnectionState.DISCONNECTED: ("○", "Offline"),
        ConnectionState.CONNECTING: ("◐", "Connecting..."),
        ConnectionState.CONNECTED: ("●", "Connected"),
        ConnectionState.RECONNECTING: ("◑", "Reconnecting..."),
        ConnectionState.ERROR: ("✗", "Error"),
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._update_display()

    def watch_state(self, state: ConnectionState) -> None:
        """Update display when state changes."""
        # Update CSS classes
        for s in ConnectionState:
            self.remove_class(s.value)
        self.add_class(state.value)
        self._update_display()

    def _update_display(self) -> None:
        """Update the displayed text."""
        symbol, text = self.STATE_DISPLAY.get(
            self.state, ("?", "Unknown")
        )
        if self.state == ConnectionState.RECONNECTING and self._reconnect_attempt > 0:
            text = f"Reconnecting ({self._reconnect_attempt}/{self._max_reconnect_attempts})..."
        self.update(f"{symbol} {text}")

    def set_connected(self) -> None:
        """Set state to connected."""
        self._reconnect_attempt = 0
        self.state = ConnectionState.CONNECTED

    def set_disconnected(self) -> None:
        """Set state to disconnected."""
        self.state = ConnectionState.DISCONNECTED

    def set_connecting(self) -> None:
        """Set state to connecting."""
        self.state = ConnectionState.CONNECTING

    def set_reconnecting(self, attempt: int = 0) -> None:
        """Set state to reconnecting.

        Args:
            attempt: Current reconnection attempt number
        """
        self._reconnect_attempt = attempt
        self.state = ConnectionState.RECONNECTING
        self._update_display()

    def set_error(self) -> None:
        """Set state to error."""
        self.state = ConnectionState.ERROR


class AutoReconnect:
    """Mixin class providing auto-reconnection logic.

    Add this to your app class to enable automatic reconnection
    when the gateway connection is lost.
    """

    _reconnect_task: Optional[asyncio.Task] = None
    _reconnect_delay: float = 1.0
    _max_reconnect_delay: float = 30.0
    _reconnect_attempts: int = 0
    _max_reconnect_attempts: int = 10

    async def start_reconnect(self) -> None:
        """Start the reconnection process."""
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Already reconnecting

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def stop_reconnect(self) -> None:
        """Stop any ongoing reconnection attempts."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

    async def _reconnect_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        self._reconnect_attempts = 0
        delay = self._reconnect_delay

        while self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1

            # Notify UI of reconnection attempt
            self._on_reconnect_attempt(self._reconnect_attempts)

            try:
                # Try to reconnect
                success = await self._attempt_reconnect()
                if success:
                    self._on_reconnect_success()
                    return
            except Exception as e:
                self._on_reconnect_error(e)

            # Wait before next attempt (exponential backoff)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_reconnect_delay)

        # Max attempts reached
        self._on_reconnect_failed()

    async def _attempt_reconnect(self) -> bool:
        """Attempt to reconnect to the gateway.

        Override this method in your app class.

        Returns:
            True if reconnection succeeded, False otherwise
        """
        raise NotImplementedError("Override _attempt_reconnect in your app class")

    def _on_reconnect_attempt(self, attempt: int) -> None:
        """Called when a reconnection attempt starts.

        Override to update UI.
        """
        pass

    def _on_reconnect_success(self) -> None:
        """Called when reconnection succeeds.

        Override to update UI.
        """
        pass

    def _on_reconnect_error(self, error: Exception) -> None:
        """Called when a reconnection attempt fails.

        Override to update UI.
        """
        pass

    def _on_reconnect_failed(self) -> None:
        """Called when max reconnection attempts reached.

        Override to update UI.
        """
        pass


class DraftManager:
    """Manages draft message persistence.

    Saves draft messages when errors occur so users don't lose their work.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        """Initialize draft manager.

        Args:
            storage_path: Path to store drafts (defaults to ~/.ag3nt/drafts.json)
        """
        from pathlib import Path
        import json

        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path.home() / ".ag3nt" / "drafts.json"

        self._drafts: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Load drafts from storage."""
        import json

        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._drafts = json.load(f)
            except Exception:
                self._drafts = {}

    def _save(self) -> None:
        """Save drafts to storage."""
        import json

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._drafts, f, indent=2)
        except Exception:
            pass  # Don't fail on save errors

    def save_draft(self, session_id: str, content: str) -> None:
        """Save a draft message.

        Args:
            session_id: Session ID to associate draft with
            content: Draft message content
        """
        if content.strip():
            self._drafts[session_id] = content
            self._save()

    def get_draft(self, session_id: str) -> Optional[str]:
        """Get saved draft for a session.

        Args:
            session_id: Session ID to look up

        Returns:
            Draft content if found, None otherwise
        """
        return self._drafts.get(session_id)

    def clear_draft(self, session_id: str) -> None:
        """Clear draft for a session.

        Args:
            session_id: Session ID to clear draft for
        """
        if session_id in self._drafts:
            del self._drafts[session_id]
            self._save()

    def has_draft(self, session_id: str) -> bool:
        """Check if a session has a saved draft.

        Args:
            session_id: Session ID to check

        Returns:
            True if draft exists
        """
        return session_id in self._drafts and bool(self._drafts[session_id].strip())
