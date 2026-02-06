"""Loading widget for AG3NT TUI."""

from __future__ import annotations

import time
from typing import Optional

from rich.text import Text
from textual.widgets import Static


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
        self._tool_name: Optional[str] = None
        self._tool_args: Optional[str] = None
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

        # Show tool info if available
        if self._tool_name:
            text.append(f": ", style="#6b6b6b")
            text.append(f"{self._tool_name}", style="bold #f59e0b")
            if self._tool_args:
                text.append(f" ({self._tool_args})", style="#6b6b6b")

        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            text.append(f" • {elapsed}s", style="#6b6b6b")
        return text

    def set_status(self, status: str) -> None:
        self._status = status
        self.refresh()

    def set_tool(self, tool_name: str, tool_args: str = "") -> None:
        """Show current tool being executed."""
        self._tool_name = tool_name
        self._tool_args = tool_args
        self.refresh()

    def clear_tool(self) -> None:
        """Clear tool display."""
        self._tool_name = None
        self._tool_args = None
        self.refresh()

    def pause(self, status: str = "Awaiting decision") -> None:
        self._paused = True
        self._status = status
        self.refresh()

    def resume(self) -> None:
        self._paused = False
        self._status = "Thinking"
