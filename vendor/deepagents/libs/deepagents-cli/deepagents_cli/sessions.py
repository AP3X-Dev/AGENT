"""Thread management using LangGraph's built-in checkpoint persistence."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich.table import Table

from deepagents_cli.config import COLORS, console

# Patch aiosqlite.Connection to add is_alive() method required by langgraph-checkpoint>=2.1.0
# See: https://github.com/langchain-ai/langgraph/issues/6583
if not hasattr(aiosqlite.Connection, "is_alive"):

    def _is_alive(self: aiosqlite.Connection) -> bool:
        """Check if the connection is still alive."""
        return self._connection is not None

    aiosqlite.Connection.is_alive = _is_alive


def _format_timestamp(iso_timestamp: str | None) -> str:
    """Format ISO timestamp for display (e.g., 'Dec 30, 6:10pm')."""
    if not iso_timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(iso_timestamp).astimezone()
        return dt.strftime("%b %d, %-I:%M%p").lower().replace("am", "am").replace("pm", "pm")
    except (ValueError, TypeError):
        return ""


def get_db_path() -> Path:
    """Get path to global database."""
    db_dir = Path.home() / ".deepagents"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "sessions.db"


def generate_thread_id() -> str:
    """Generate a new 8-char hex thread ID."""
    return uuid.uuid4().hex[:8]


async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    """Check if a table exists in the database."""
    query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
    async with conn.execute(query, (table,)) as cursor:
        return await cursor.fetchone() is not None


async def list_threads(
    agent_name: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List threads from checkpoints table."""
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        # Return empty if table doesn't exist yet (fresh install)
        if not await _table_exists(conn, "checkpoints"):
            return []

        if agent_name:
            query = """
                SELECT thread_id,
                       json_extract(metadata, '$.agent_name') as agent_name,
                       MAX(json_extract(metadata, '$.updated_at')) as updated_at
                FROM checkpoints
                WHERE json_extract(metadata, '$.agent_name') = ?
                GROUP BY thread_id
                ORDER BY updated_at DESC
                LIMIT ?
            """
            params: tuple = (agent_name, limit)
        else:
            query = """
                SELECT thread_id,
                       json_extract(metadata, '$.agent_name') as agent_name,
                       MAX(json_extract(metadata, '$.updated_at')) as updated_at
                FROM checkpoints
                GROUP BY thread_id
                ORDER BY updated_at DESC
                LIMIT ?
            """
            params = (limit,)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [{"thread_id": r[0], "agent_name": r[1], "updated_at": r[2]} for r in rows]


async def get_most_recent(agent_name: str | None = None) -> str | None:
    """Get most recent thread_id, optionally filtered by agent."""
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        if not await _table_exists(conn, "checkpoints"):
            return None

        if agent_name:
            query = """
                SELECT thread_id FROM checkpoints
                WHERE json_extract(metadata, '$.agent_name') = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
            """
            params: tuple = (agent_name,)
        else:
            query = "SELECT thread_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1"
            params = ()

        async with conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_thread_agent(thread_id: str) -> str | None:
    """Get agent_name for a thread."""
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        if not await _table_exists(conn, "checkpoints"):
            return None

        query = """
            SELECT json_extract(metadata, '$.agent_name')
            FROM checkpoints
            WHERE thread_id = ?
            LIMIT 1
        """
        async with conn.execute(query, (thread_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def thread_exists(thread_id: str) -> bool:
    """Check if a thread exists in checkpoints."""
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        if not await _table_exists(conn, "checkpoints"):
            return False

        query = "SELECT 1 FROM checkpoints WHERE thread_id = ? LIMIT 1"
        async with conn.execute(query, (thread_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def delete_thread(thread_id: str) -> bool:
    """Delete thread checkpoints. Returns True if deleted."""
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        if not await _table_exists(conn, "checkpoints"):
            return False

        cursor = await conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        deleted = cursor.rowcount > 0
        if await _table_exists(conn, "writes"):
            await conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        await conn.commit()
        return deleted


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[AsyncSqliteSaver]:
    """Get AsyncSqliteSaver for the global database."""
    async with AsyncSqliteSaver.from_conn_string(str(get_db_path())) as checkpointer:
        yield checkpointer


async def list_threads_command(
    agent_name: str | None = None,
    limit: int = 20,
) -> None:
    """CLI handler for: deepagents threads list."""
    threads = await list_threads(agent_name, limit=limit)

    if not threads:
        if agent_name:
            console.print(f"[yellow]No threads found for agent '{agent_name}'.[/yellow]")
        else:
            console.print("[yellow]No threads found.[/yellow]")
        console.print("[dim]Start a conversation with: deepagents[/dim]")
        return

    title = f"Threads for '{agent_name}'" if agent_name else "All Threads"

    table = Table(title=title, show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("Thread ID", style="bold")
    table.add_column("Agent")
    table.add_column("Last Used", style="dim")

    for t in threads:
        table.add_row(
            t["thread_id"],
            t["agent_name"] or "unknown",
            _format_timestamp(t.get("updated_at")),
        )

    console.print()
    console.print(table)
    console.print()


async def get_thread_messages(
    thread_id: str,
    limit: int = 50,
) -> list[dict]:
    """Get messages from a thread's checkpoint.

    Returns a list of message dicts with 'role', 'content', and 'id' keys.
    """
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        if not await _table_exists(conn, "checkpoints"):
            return []

        # Get the latest checkpoint for this thread
        query = """
            SELECT checkpoint
            FROM checkpoints
            WHERE thread_id = ?
            ORDER BY checkpoint_id DESC
            LIMIT 1
        """
        async with conn.execute(query, (thread_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return []

            try:
                import json
                checkpoint_blob = row[0]
                # The checkpoint is stored as JSON or msgpack
                if isinstance(checkpoint_blob, bytes):
                    try:
                        # Try JSON first
                        checkpoint = json.loads(checkpoint_blob.decode('utf-8'))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # Try msgpack/ormsgpack
                        try:
                            import ormsgpack
                            checkpoint = ormsgpack.unpackb(checkpoint_blob)
                        except Exception:
                            return []
                elif isinstance(checkpoint_blob, str):
                    checkpoint = json.loads(checkpoint_blob)
                else:
                    return []

                # Extract messages from channel_values
                channel_values = checkpoint.get("channel_values", {})
                messages_data = channel_values.get("messages", [])

                messages = []
                for msg in messages_data[-limit:]:
                    if isinstance(msg, dict):
                        role = msg.get("type", "unknown")
                        content = msg.get("content", "")
                        msg_id = msg.get("id", "")
                    else:
                        # Handle LangChain message objects serialized differently
                        role = getattr(msg, "type", "unknown")
                        content = getattr(msg, "content", str(msg))
                        msg_id = getattr(msg, "id", "")

                    # Normalize role names
                    if role in ("human", "HumanMessage"):
                        role = "user"
                    elif role in ("ai", "AIMessage"):
                        role = "assistant"

                    messages.append({
                        "role": role,
                        "content": content if isinstance(content, str) else str(content),
                        "id": msg_id,
                    })

                return messages
            except Exception:
                return []


async def get_thread_preview(thread_id: str, max_length: int = 60) -> str | None:
    """Get a preview of the thread's last message content."""
    messages = await get_thread_messages(thread_id, limit=5)
    if not messages:
        return None

    # Get the last user or assistant message
    for msg in reversed(messages):
        if msg["role"] in ("user", "assistant"):
            content = msg["content"]
            if len(content) > max_length:
                return content[:max_length] + "..."
            return content
    return None


async def delete_thread_command(thread_id: str) -> None:
    """CLI handler for: deepagents threads delete."""
    deleted = await delete_thread(thread_id)

    if deleted:
        console.print(f"[green]Thread '{thread_id}' deleted.[/green]")
    else:
        console.print(f"[red]Thread '{thread_id}' not found.[/red]")
