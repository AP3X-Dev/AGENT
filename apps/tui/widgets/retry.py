"""Retry widget for failed requests in AG3NT TUI."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static
from textual.containers import Vertical


class RetryBanner(Vertical):
    """Banner shown when a request fails with retry option.

    Displays the error message and provides retry/dismiss buttons.
    """

    DEFAULT_CSS = """
    RetryBanner {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #2d1f1f;
        border: solid #7f1d1d;
    }

    RetryBanner .error-icon {
        color: #ef4444;
        text-style: bold;
    }

    RetryBanner .error-message {
        color: #fca5a5;
        margin: 0 0 1 0;
    }

    RetryBanner .buttons {
        height: auto;
        align: left middle;
    }

    RetryBanner Button {
        margin-right: 1;
    }

    RetryBanner Button#retry {
        background: #10b981;
    }

    RetryBanner Button#retry:hover {
        background: #059669;
    }

    RetryBanner Button#dismiss {
        background: #4b5563;
    }

    RetryBanner Button#dismiss:hover {
        background: #374151;
    }
    """

    class RetryRequested(Message):
        """User requested to retry the failed request."""

        def __init__(self, original_message: str, request_id: str = "") -> None:
            self.original_message = original_message
            self.request_id = request_id
            super().__init__()

    class Dismissed(Message):
        """User dismissed the retry banner."""

        def __init__(self, request_id: str = "") -> None:
            self.request_id = request_id
            super().__init__()

    def __init__(
        self,
        error_message: str,
        original_message: str = "",
        request_id: str = "",
        show_details: bool = True,
        **kwargs,
    ) -> None:
        """Initialize retry banner.

        Args:
            error_message: The error message to display
            original_message: The original user message that failed
            request_id: Optional request ID for tracking
            show_details: Whether to show error details
        """
        super().__init__(**kwargs)
        self.error_message = error_message
        self.original_message = original_message
        self.request_id = request_id
        self.show_details = show_details

    def compose(self) -> ComposeResult:
        yield Static("✗ Request Failed", classes="error-icon")
        if self.show_details:
            # Truncate long error messages
            msg = self.error_message
            if len(msg) > 200:
                msg = msg[:197] + "..."
            yield Static(msg, classes="error-message")
        yield Horizontal(
            Button("Retry", id="retry", variant="success"),
            Button("Dismiss", id="dismiss", variant="default"),
            classes="buttons",
        )

    @on(Button.Pressed, "#retry")
    def on_retry_pressed(self) -> None:
        """Handle retry button press."""
        self.post_message(
            self.RetryRequested(self.original_message, self.request_id)
        )
        self.remove()

    @on(Button.Pressed, "#dismiss")
    def on_dismiss_pressed(self) -> None:
        """Handle dismiss button press."""
        self.post_message(self.Dismissed(self.request_id))
        self.remove()


class TimeoutBanner(Vertical):
    """Banner shown when a request times out.

    Similar to RetryBanner but with timeout-specific messaging.
    """

    DEFAULT_CSS = """
    TimeoutBanner {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #2d2a1f;
        border: solid #a16207;
    }

    TimeoutBanner .timeout-icon {
        color: #f59e0b;
        text-style: bold;
    }

    TimeoutBanner .timeout-message {
        color: #fcd34d;
        margin: 0 0 1 0;
    }

    TimeoutBanner .buttons {
        height: auto;
        align: left middle;
    }

    TimeoutBanner Button {
        margin-right: 1;
    }
    """

    class RetryRequested(Message):
        """User requested to retry the timed out request."""

        def __init__(self, original_message: str) -> None:
            self.original_message = original_message
            super().__init__()

    class WaitRequested(Message):
        """User requested to wait longer."""

        def __init__(self, original_message: str) -> None:
            self.original_message = original_message
            super().__init__()

    class Dismissed(Message):
        """User dismissed the timeout banner."""
        pass

    def __init__(
        self,
        original_message: str = "",
        timeout_seconds: int = 300,
        **kwargs,
    ) -> None:
        """Initialize timeout banner.

        Args:
            original_message: The original user message that timed out
            timeout_seconds: How long the request ran before timing out
        """
        super().__init__(**kwargs)
        self.original_message = original_message
        self.timeout_seconds = timeout_seconds

    def compose(self) -> ComposeResult:
        yield Static("⏱ Request Timed Out", classes="timeout-icon")
        yield Static(
            f"The request took longer than {self.timeout_seconds // 60} minutes. "
            "The agent may still be processing in the background.",
            classes="timeout-message",
        )
        yield Horizontal(
            Button("Retry", id="retry", variant="primary"),
            Button("Wait Longer", id="wait", variant="warning"),
            Button("Dismiss", id="dismiss", variant="default"),
            classes="buttons",
        )

    @on(Button.Pressed, "#retry")
    def on_retry_pressed(self) -> None:
        """Handle retry button press."""
        self.post_message(self.RetryRequested(self.original_message))
        self.remove()

    @on(Button.Pressed, "#wait")
    def on_wait_pressed(self) -> None:
        """Handle wait button press."""
        self.post_message(self.WaitRequested(self.original_message))
        self.remove()

    @on(Button.Pressed, "#dismiss")
    def on_dismiss_pressed(self) -> None:
        """Handle dismiss button press."""
        self.post_message(self.Dismissed())
        self.remove()


class OfflineBanner(Vertical):
    """Banner shown when the app is offline.

    Provides reconnection options and offline mode indicator.
    """

    DEFAULT_CSS = """
    OfflineBanner {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: #1f2937;
        border: solid #4b5563;
    }

    OfflineBanner .offline-icon {
        color: #9ca3af;
        text-style: bold;
    }

    OfflineBanner .offline-message {
        color: #d1d5db;
        margin: 0 0 1 0;
    }

    OfflineBanner .buttons {
        height: auto;
        align: left middle;
    }

    OfflineBanner Button {
        margin-right: 1;
    }

    OfflineBanner Button#reconnect {
        background: #6366f1;
    }

    OfflineBanner Button#reconnect:hover {
        background: #4f46e5;
    }
    """

    class ReconnectRequested(Message):
        """User requested to reconnect."""
        pass

    class Dismissed(Message):
        """User dismissed the offline banner."""
        pass

    def __init__(
        self,
        gateway_url: str = "",
        show_url: bool = True,
        **kwargs,
    ) -> None:
        """Initialize offline banner.

        Args:
            gateway_url: The gateway URL that couldn't be reached
            show_url: Whether to show the URL in the message
        """
        super().__init__(**kwargs)
        self.gateway_url = gateway_url
        self.show_url = show_url

    def compose(self) -> ComposeResult:
        yield Static("○ Offline", classes="offline-icon")
        msg = "Cannot connect to the AG3NT gateway."
        if self.show_url and self.gateway_url:
            msg += f"\n{self.gateway_url}"
        yield Static(msg, classes="offline-message")
        yield Horizontal(
            Button("Reconnect", id="reconnect", variant="primary"),
            Button("Dismiss", id="dismiss", variant="default"),
            classes="buttons",
        )

    @on(Button.Pressed, "#reconnect")
    def on_reconnect_pressed(self) -> None:
        """Handle reconnect button press."""
        self.post_message(self.ReconnectRequested())
        self.remove()

    @on(Button.Pressed, "#dismiss")
    def on_dismiss_pressed(self) -> None:
        """Handle dismiss button press."""
        self.post_message(self.Dismissed())
        self.remove()
