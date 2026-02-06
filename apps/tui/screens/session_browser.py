"""Session browser screen for AG3NT TUI."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

if TYPE_CHECKING:
    from ..utils.sessions import SessionInfo


class SessionBrowser(ModalScreen):
    """Modal for browsing and resuming sessions."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("enter", "select", "Resume"),
        ("delete", "delete_session", "Delete"),
        ("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    SessionBrowser {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }

    #session-browser {
        width: 80;
        height: 30;
        background: #1e1e1e;
        border: solid #3a3a3a;
        padding: 1 2;
    }

    #session-browser .title {
        text-style: bold;
        color: #10b981;
        text-align: center;
        width: 100%;
        padding: 1 0;
    }

    #session-browser .subtitle {
        color: #6b6b6b;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #session-browser DataTable {
        height: 1fr;
        margin: 1 0;
    }

    #session-browser DataTable > .datatable--header {
        background: #2f2f2f;
        color: #a1a1a1;
    }

    #session-browser DataTable > .datatable--cursor {
        background: #6366f1;
        color: #ececec;
    }

    #session-browser .buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #session-browser Button {
        margin: 0 1;
    }

    #session-browser .hint {
        color: #6b6b6b;
        text-align: center;
        width: 100%;
        margin-top: 1;
    }

    #session-browser .empty-state {
        text-align: center;
        color: #6b6b6b;
        padding: 4;
    }
    """

    class SessionSelected(Message):
        """Message sent when a session is selected for resumption."""

        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class SessionDeleted(Message):
        """Message sent when a session is deleted."""

        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    def __init__(self, sessions: list[SessionInfo] | None = None) -> None:
        """Initialize session browser.

        Args:
            sessions: List of sessions to display. If None, will be loaded from app.
        """
        super().__init__()
        self._sessions = sessions or []
        self._session_map: dict[str, SessionInfo] = {}

    def compose(self) -> ComposeResult:
        with Container(id="session-browser"):
            yield Static("Session History", classes="title")
            yield Static(
                "Select a session to resume or delete",
                classes="subtitle",
            )
            yield DataTable(id="sessions-table", cursor_type="row")
            yield Horizontal(
                Button("Resume", id="resume", variant="primary"),
                Button("Delete", id="delete", variant="error"),
                Button("Close", id="close"),
                classes="buttons",
            )
            yield Static(
                "[dim]Enter[/dim] resume • [dim]Delete[/dim] remove • [dim]Esc[/dim] close",
                classes="hint",
            )

    def on_mount(self) -> None:
        """Populate the table with sessions."""
        table = self.query_one("#sessions-table", DataTable)
        table.add_columns("Date", "Title", "Messages", "Tokens")
        table.cursor_type = "row"

        # Try to load sessions from app if not provided
        if not self._sessions:
            try:
                if hasattr(self.app, "session_manager"):
                    self._sessions = self.app.session_manager.list_sessions()
            except Exception:
                pass

        if not self._sessions:
            # Show empty state
            table.add_row("", "No sessions found", "", "")
            return

        # Build session map and populate table
        for session in self._sessions:
            self._session_map[session.session_id] = session

            # Format date
            date_str = self._format_date(session.last_message_at)

            # Format title
            title = session.title or "(No title)"
            if len(title) > 40:
                title = title[:37] + "..."

            # Format tokens
            if session.total_tokens >= 1000:
                tokens_str = f"{session.total_tokens / 1000:.1f}K"
            else:
                tokens_str = str(session.total_tokens)

            table.add_row(
                date_str,
                title,
                str(session.message_count),
                tokens_str,
                key=session.session_id,
            )

    def _format_date(self, dt: datetime) -> str:
        """Format datetime for display."""
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            return dt.strftime("%I:%M %p")
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return dt.strftime("%A")  # Day name
        else:
            return dt.strftime("%b %d")

    def _get_selected_session_id(self) -> str | None:
        """Get the currently selected session ID."""
        table = self.query_one("#sessions-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            try:
                row_key = table.get_row_at(table.cursor_row)
                # row_key is the key we passed to add_row
                if row_key and row_key.value in self._session_map:
                    return row_key.value
            except Exception:
                pass
        return None

    def action_close(self) -> None:
        """Close the browser."""
        self.dismiss(None)

    def action_select(self) -> None:
        """Select the current session for resumption."""
        session_id = self._get_selected_session_id()
        if session_id:
            self.post_message(self.SessionSelected(session_id))
            self.dismiss(session_id)

    def action_delete_session(self) -> None:
        """Delete the selected session."""
        session_id = self._get_selected_session_id()
        if session_id:
            # Remove from table
            table = self.query_one("#sessions-table", DataTable)
            try:
                table.remove_row(session_id)
            except Exception:
                pass

            # Remove from map
            self._session_map.pop(session_id, None)

            # Notify app
            self.post_message(self.SessionDeleted(session_id))

    def action_refresh(self) -> None:
        """Refresh the session list."""
        if hasattr(self.app, "session_manager"):
            self._sessions = self.app.session_manager.list_sessions()
            self._session_map.clear()

            table = self.query_one("#sessions-table", DataTable)
            table.clear()

            # Re-populate
            for session in self._sessions:
                self._session_map[session.session_id] = session
                date_str = self._format_date(session.last_message_at)
                title = session.title or "(No title)"
                if len(title) > 40:
                    title = title[:37] + "..."
                if session.total_tokens >= 1000:
                    tokens_str = f"{session.total_tokens / 1000:.1f}K"
                else:
                    tokens_str = str(session.total_tokens)
                table.add_row(
                    date_str,
                    title,
                    str(session.message_count),
                    tokens_str,
                    key=session.session_id,
                )

    @on(Button.Pressed, "#resume")
    def on_resume_pressed(self) -> None:
        """Handle resume button."""
        self.action_select()

    @on(Button.Pressed, "#delete")
    def on_delete_pressed(self) -> None:
        """Handle delete button."""
        self.action_delete_session()

    @on(Button.Pressed, "#close")
    def on_close_pressed(self) -> None:
        """Handle close button."""
        self.action_close()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle double-click on row."""
        self.action_select()
