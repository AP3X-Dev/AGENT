"""Message widgets for AG3NT TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

if TYPE_CHECKING:
    from typing import Optional


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
    """Widget displaying an assistant message with markdown support - Sleek dark theme.

    Supports streaming: use append_content() to add chunks incrementally.
    """

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

    AssistantMessage .response-time {
        color: #6b6b6b;
    }
    """

    def __init__(
        self, content: str = "", response_time: Optional[float] = None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._content = content
        self._response_time = response_time
        self._content_widget: Static | None = None
        self._time_widget: Static | None = None
        self._is_streaming = not content  # Empty content = streaming mode

    def compose(self) -> ComposeResult:
        time_info = ""
        if self._response_time:
            time_info = f" [#6b6b6b]• {self._response_time:.1f}s[/#6b6b6b]"
        yield Static(
            f"[bold #10b981]AP3X[/bold #10b981]{time_info}",
            classes="assistant-header",
            id="header",
        )
        yield Static(Markdown(self._content), classes="assistant-content", id="content")

    def on_mount(self) -> None:
        """Cache widget references."""
        self._content_widget = self.query_one("#content", Static)

    def append_content(self, chunk: str) -> None:
        """Append streaming chunk without full re-render."""
        self._content += chunk
        # Get widget reference - query if not cached yet (on_mount may not have run)
        if self._content_widget is None:
            try:
                self._content_widget = self.query_one("#content", Static)
            except Exception:
                return  # Widget not ready yet
        if self._content_widget:
            self._content_widget.update(Markdown(self._content))
            # Force immediate refresh of both the content widget and this container
            self._content_widget.refresh(layout=True)
            self.refresh(layout=True)

    def finalize(self, response_time: float) -> None:
        """Mark message as complete with response time."""
        self._response_time = response_time
        self._is_streaming = False
        try:
            header = self.query_one("#header", Static)
            header.update(
                f"[bold #10b981]AP3X[/bold #10b981] [#6b6b6b]• {response_time:.1f}s[/#6b6b6b]"
            )
            header.refresh(layout=True)
        except Exception:
            pass
        # Force refresh of the entire message
        self.refresh(layout=True)


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
        "Complete": "#10b981",
        "enabled": "#10b981",
        "ENABLED": "#10b981",
        # Action keywords - cyan
        "Connecting": "#22d3ee",
        "Auto-approving": "#22d3ee",
        "Opening": "#22d3ee",
        "Resending": "#22d3ee",
        "Starting": "#22d3ee",
        "Clearing": "#22d3ee",
        "Running": "#22d3ee",
        "Cancelled": "#22d3ee",
        "disabled": "#22d3ee",
        # Important items - yellow/amber
        "Gateway": "#fbbf24",
        "Session": "#f59e0b",
        "Node": "#f59e0b",
        "Theme": "#f59e0b",
        # Identifiers/codes - purple
        "code:": "#a78bfa",
        "tui-": "#a78bfa",
        # Special modes
        "GO MODE": "#ef4444",
        "Auto-approve": "#10b981",
    }

    def __init__(self, message: str, **kwargs) -> None:
        # Check if message contains rich markup (square brackets with style)
        if "[" in message and "]" in message and "/" in message:
            # Use rich markup directly
            text = Text.from_markup(f"[bold #6b6b6b]→[/bold #6b6b6b] {message}")
        else:
            # Apply keyword-based syntax highlighting
            text = Text()
            text.append("→ ", style="bold #6b6b6b")
            text = self._apply_highlighting(text, message)

        super().__init__(text, **kwargs)

    def _apply_highlighting(self, text: Text, message: str) -> Text:
        """Apply keyword-based syntax highlighting."""
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

        return text


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

    def __init__(
        self, command: str, output: str, exit_code: int = 0, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._command = command
        self._output = output
        self._exit_code = exit_code

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold #ec4899]$[/bold #ec4899] [#ececec]{self._command}[/#ececec]",
            classes="bash-command",
        )
        if self._output:
            yield Static(Text(self._output, style="#a1a1a1"), classes="bash-output")
        if self._exit_code != 0:
            yield Static(f"[#ef4444]Exit code: {self._exit_code}[/#ef4444]")
