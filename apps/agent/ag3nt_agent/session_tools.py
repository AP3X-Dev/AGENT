"""Session management tools for AG3NT agent.

Provides tools to list, query, and interact with sessions from the agent.
Sessions represent channel+user combinations with message history.
"""
from __future__ import annotations

import httpx
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Any


@dataclass
class SessionInfo:
    """Information about a session."""
    id: str
    channel_type: str
    channel_id: str
    chat_id: str
    user_id: str
    user_name: str | None
    created_at: datetime
    last_activity_at: datetime
    paired: bool
    message_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionInfo":
        """Create SessionInfo from a dictionary (API response)."""
        return cls(
            id=data["id"],
            channel_type=data["channelType"],
            channel_id=data["channelId"],
            chat_id=data.get("chatId", ""),
            user_id=data["userId"],
            user_name=data.get("userName"),
            created_at=datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00")),
            last_activity_at=datetime.fromisoformat(data["lastActivityAt"].replace("Z", "+00:00")),
            paired=data["paired"],
            message_count=data.get("messageCount", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "channel_type": self.channel_type,
            "channel_id": self.channel_id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "created_at": self.created_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "paired": self.paired,
            "message_count": self.message_count,
        }


@dataclass
class Message:
    """A message in session history."""
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    tool_calls: list[dict[str, Any]] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create Message from a dictionary (API response)."""
        return cls(
            id=data["id"],
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
            tool_calls=data.get("toolCalls"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result


@dataclass
class SessionToolsResult:
    """Result from a session tools operation."""
    success: bool
    data: Any = None
    error: str | None = None


class SessionTools:
    """Tools for managing sessions from the agent.

    Provides methods to list sessions, get session details, retrieve
    message history, and send messages to other sessions.
    """

    def __init__(self, gateway_url: str = "http://localhost:18789"):
        """Initialize session tools.

        Args:
            gateway_url: Base URL of the Gateway API.
        """
        self.gateway_url = gateway_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.gateway_url,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def list_sessions(
        self,
        *,
        channel_type: str | None = None,
        limit: int = 20,
    ) -> list[SessionInfo]:
        """List active sessions.

        Args:
            channel_type: Filter by channel type (e.g., 'telegram', 'discord').
            limit: Maximum number of sessions to return.

        Returns:
            List of SessionInfo objects.
        """
        client = await self._get_client()
        params: dict[str, Any] = {"limit": limit}
        if channel_type:
            params["channelType"] = channel_type

        response = await client.get("/api/sessions", params=params)
        response.raise_for_status()

        data = response.json()
        sessions = data.get("sessions", [])
        return [SessionInfo.from_dict(s) for s in sessions]

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """Get details of a specific session.

        Args:
            session_id: The session ID to retrieve.

        Returns:
            SessionInfo if found, None otherwise.
        """
        client = await self._get_client()

        try:
            response = await client.get(f"/api/sessions/{session_id}")
            response.raise_for_status()
            return SessionInfo.from_dict(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_history(
        self,
        session_id: str,
        *,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Message]:
        """Get message history for a session.

        Args:
            session_id: The session ID to get history for.
            limit: Maximum number of messages to return.
            before: Only return messages before this timestamp.

        Returns:
            List of Message objects in chronological order.
        """
        client = await self._get_client()
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before.isoformat()

        response = await client.get(
            f"/api/sessions/{session_id}/history",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        messages = data.get("messages", [])
        return [Message.from_dict(m) for m in messages]

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        as_system: bool = False,
    ) -> SessionToolsResult:
        """Send a message to another session.

        This allows the agent to send messages to sessions other than
        the current one, enabling cross-session communication.

        Args:
            session_id: The session ID to send the message to.
            content: The message content.
            as_system: If True, send as a system message instead of assistant.

        Returns:
            SessionToolsResult with success status and message ID.
        """
        client = await self._get_client()

        try:
            response = await client.post(
                f"/api/sessions/{session_id}/message",
                json={
                    "content": content,
                    "role": "system" if as_system else "assistant",
                },
            )
            response.raise_for_status()

            data = response.json()
            return SessionToolsResult(
                success=data.get("success", True),
                data={"message_id": data.get("messageId")},
            )
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response.content else {}
            return SessionToolsResult(
                success=False,
                error=error_data.get("error", f"HTTP {e.response.status_code}"),
            )

    async def delete_session(self, session_id: str) -> SessionToolsResult:
        """Delete a session and its message history.

        Args:
            session_id: The session ID to delete.

        Returns:
            SessionToolsResult with success status.
        """
        client = await self._get_client()

        try:
            response = await client.delete(f"/api/sessions/{session_id}")
            response.raise_for_status()
            return SessionToolsResult(success=True)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return SessionToolsResult(success=False, error="Session not found")
            error_data = e.response.json() if e.response.content else {}
            return SessionToolsResult(
                success=False,
                error=error_data.get("error", f"HTTP {e.response.status_code}"),
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "SessionTools":
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Convenience functions for creating LangChain tools

def create_list_sessions_tool(gateway_url: str = "http://localhost:18789"):
    """Create a LangChain tool for listing sessions.

    Args:
        gateway_url: Base URL of the Gateway API.

    Returns:
        A function that can be used as a LangChain tool.
    """
    tools = SessionTools(gateway_url)

    async def list_sessions(channel_type: str | None = None, limit: int = 20) -> str:
        """List active sessions. Optionally filter by channel type."""
        try:
            sessions = await tools.list_sessions(channel_type=channel_type, limit=limit)
            if not sessions:
                return "No active sessions found."

            lines = [f"Found {len(sessions)} session(s):"]
            for s in sessions:
                lines.append(
                    f"- {s.id} ({s.channel_type}): user={s.user_name or s.user_id}, "
                    f"messages={s.message_count}, paired={s.paired}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing sessions: {e}"

    return list_sessions


def create_get_session_history_tool(gateway_url: str = "http://localhost:18789"):
    """Create a LangChain tool for getting session history.

    Args:
        gateway_url: Base URL of the Gateway API.

    Returns:
        A function that can be used as a LangChain tool.
    """
    tools = SessionTools(gateway_url)

    async def get_session_history(session_id: str, limit: int = 20) -> str:
        """Get message history for a session."""
        try:
            messages = await tools.get_history(session_id, limit=limit)
            if not messages:
                return f"No messages found for session {session_id}."

            lines = [f"Last {len(messages)} message(s) for session {session_id}:"]
            for m in messages:
                content_preview = m.content[:100] + "..." if len(m.content) > 100 else m.content
                lines.append(f"[{m.role}] {content_preview}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error getting session history: {e}"

    return get_session_history


def create_send_message_tool(gateway_url: str = "http://localhost:18789"):
    """Create a LangChain tool for sending messages to sessions.

    Args:
        gateway_url: Base URL of the Gateway API.

    Returns:
        A function that can be used as a LangChain tool.
    """
    tools = SessionTools(gateway_url)

    async def send_message_to_session(session_id: str, content: str) -> str:
        """Send a message to another session."""
        try:
            result = await tools.send_message(session_id, content)
            if result.success:
                return f"Message sent successfully to session {session_id}."
            return f"Failed to send message: {result.error}"
        except Exception as e:
            return f"Error sending message: {e}"

    return send_message_to_session

