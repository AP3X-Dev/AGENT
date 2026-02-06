"""Session persistence for AG3NT TUI."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional


@dataclass
class SessionInfo:
    """Information about a chat session."""

    session_id: str
    created_at: datetime
    last_message_at: datetime
    message_count: int
    title: str  # First user message, truncated
    total_tokens: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_message_at": self.last_message_at.isoformat(),
            "message_count": self.message_count,
            "title": self.title,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_row(cls, row: tuple) -> SessionInfo:
        """Create from database row."""
        return cls(
            session_id=row[0],
            created_at=datetime.fromisoformat(row[1]),
            last_message_at=datetime.fromisoformat(row[2]),
            message_count=row[3],
            title=row[4],
            total_tokens=row[5] if len(row) > 5 else 0,
        )


class SessionManager:
    """Manages session persistence in SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize session manager.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.ag3nt/tui_sessions.db
        """
        if db_path is None:
            db_path = Path.home() / ".ag3nt" / "tui_sessions.db"
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_message_at TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    title TEXT DEFAULT '',
                    total_tokens INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_last_message
                ON sessions(last_message_at DESC)
            """)
            conn.commit()

    def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        """List recent sessions.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of SessionInfo ordered by last message time (newest first)
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT session_id, created_at, last_message_at,
                       message_count, title, total_tokens
                FROM sessions
                ORDER BY last_message_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [SessionInfo.from_row(row) for row in rows]

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get a specific session.

        Args:
            session_id: Session ID to retrieve

        Returns:
            SessionInfo if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT session_id, created_at, last_message_at,
                       message_count, title, total_tokens
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return SessionInfo.from_row(row) if row else None

    def save_session(self, info: SessionInfo) -> None:
        """Save or update session info.

        Args:
            info: Session information to save
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                (session_id, created_at, last_message_at, message_count, title, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    info.session_id,
                    info.created_at.isoformat(),
                    info.last_message_at.isoformat(),
                    info.message_count,
                    info.title,
                    info.total_tokens,
                ),
            )
            conn.commit()

    def update_session(
        self,
        session_id: str,
        message_count: Optional[int] = None,
        title: Optional[str] = None,
        total_tokens: Optional[int] = None,
    ) -> None:
        """Update specific fields of a session.

        Args:
            session_id: Session ID to update
            message_count: New message count (optional)
            title: New title (optional)
            total_tokens: New token count (optional)
        """
        updates = ["last_message_at = ?"]
        values = [datetime.now().isoformat()]

        if message_count is not None:
            updates.append("message_count = ?")
            values.append(message_count)
        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if total_tokens is not None:
            updates.append("total_tokens = ?")
            values.append(total_tokens)

        values.append(session_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                values,
            )
            conn.commit()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID to delete

        Returns:
            True if session was deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_session(self, session_id: str, title: str = "") -> SessionInfo:
        """Create a new session.

        Args:
            session_id: Unique session ID
            title: Session title (usually first message)

        Returns:
            Created SessionInfo
        """
        now = datetime.now()
        info = SessionInfo(
            session_id=session_id,
            created_at=now,
            last_message_at=now,
            message_count=0,
            title=title[:100] if title else "",
            total_tokens=0,
        )
        self.save_session(info)
        return info

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    def cleanup_old_sessions(self, keep_count: int = 50) -> int:
        """Remove old sessions, keeping only the most recent.

        Args:
            keep_count: Number of recent sessions to keep

        Returns:
            Number of sessions deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get IDs to keep
            keep_ids = conn.execute(
                """
                SELECT session_id FROM sessions
                ORDER BY last_message_at DESC
                LIMIT ?
                """,
                (keep_count,),
            ).fetchall()
            keep_set = {row[0] for row in keep_ids}

            # Delete others
            if keep_set:
                placeholders = ",".join("?" * len(keep_set))
                cursor = conn.execute(
                    f"DELETE FROM sessions WHERE session_id NOT IN ({placeholders})",
                    list(keep_set),
                )
            else:
                cursor = conn.execute("DELETE FROM sessions")

            conn.commit()
            return cursor.rowcount
