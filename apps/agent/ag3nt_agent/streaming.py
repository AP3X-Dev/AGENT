"""Tool execution streaming for real-time progress updates.

This module provides infrastructure for streaming tool execution events
to the Gateway, enabling real-time UI updates during long-running operations.

Events:
- tool_start: Tool execution begins
- tool_progress: Intermediate progress update (for long operations)
- tool_end: Tool execution completed successfully
- tool_error: Tool execution failed

Usage:
    from ag3nt_agent.streaming import StreamingContext, get_stream_manager

    # In a tool function:
    async with StreamingContext(session_id, "read_file") as ctx:
        ctx.emit_progress("Reading file...", progress=0.5)
        result = do_work()
        return result  # tool_end emitted automatically
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("ag3nt.streaming")


class EventType(str, Enum):
    """Types of streaming events."""

    TOOL_START = "tool_start"
    TOOL_PROGRESS = "tool_progress"
    TOOL_END = "tool_end"
    TOOL_ERROR = "tool_error"


@dataclass
class ToolEvent:
    """Event emitted during tool execution."""

    event_type: EventType
    session_id: str
    tool_name: str
    tool_call_id: str
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "timestamp": self.timestamp,
            **self.data,
        }


class StreamManager:
    """Manages streaming subscriptions and event dispatch.

    Singleton that handles:
    - WebSocket connections from Gateway
    - Event routing to appropriate subscribers
    - Buffering for disconnected clients
    """

    _instance: StreamManager | None = None

    def __init__(self) -> None:
        # session_id -> list of callbacks
        self._subscribers: dict[str, list[Callable[[ToolEvent], None]]] = {}
        # session_id -> list of buffered events (for reconnection)
        self._event_buffer: dict[str, list[ToolEvent]] = {}
        self._buffer_max_size = 100
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> StreamManager:
        """Get the singleton StreamManager instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def subscribe(
        self,
        session_id: str,
        callback: Callable[[ToolEvent], None],
    ) -> Callable[[], None]:
        """Subscribe to events for a session.

        Args:
            session_id: Session to subscribe to
            callback: Function called for each event

        Returns:
            Unsubscribe function
        """
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []

        self._subscribers[session_id].append(callback)
        logger.debug(f"Subscribed to session {session_id[:16]}...")

        # Send any buffered events
        if session_id in self._event_buffer:
            for event in self._event_buffer[session_id]:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error sending buffered event: {e}")
            # Clear buffer after sending
            del self._event_buffer[session_id]

        def unsubscribe() -> None:
            if session_id in self._subscribers:
                try:
                    self._subscribers[session_id].remove(callback)
                    if not self._subscribers[session_id]:
                        del self._subscribers[session_id]
                except ValueError:
                    pass
            logger.debug(f"Unsubscribed from session {session_id[:16]}...")

        return unsubscribe

    def emit(self, event: ToolEvent) -> None:
        """Emit an event to all subscribers.

        If no subscribers, buffers the event for later delivery.
        """
        session_id = event.session_id

        if session_id in self._subscribers:
            for callback in self._subscribers[session_id]:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
        else:
            # Buffer event for later delivery
            if session_id not in self._event_buffer:
                self._event_buffer[session_id] = []

            self._event_buffer[session_id].append(event)

            # Trim buffer if too large
            if len(self._event_buffer[session_id]) > self._buffer_max_size:
                self._event_buffer[session_id] = self._event_buffer[session_id][
                    -self._buffer_max_size :
                ]

        logger.debug(
            f"Event {event.event_type.value} for {event.tool_name} "
            f"(session {session_id[:16]}...)"
        )

    def get_subscriber_count(self, session_id: str) -> int:
        """Get number of subscribers for a session."""
        return len(self._subscribers.get(session_id, []))

    def clear_buffer(self, session_id: str) -> None:
        """Clear buffered events for a session."""
        self._event_buffer.pop(session_id, None)


def get_stream_manager() -> StreamManager:
    """Get the global StreamManager instance."""
    return StreamManager.get_instance()


class StreamingContext:
    """Context manager for streaming tool execution.

    Automatically emits tool_start and tool_end/tool_error events.

    Usage:
        async with StreamingContext(session_id, "my_tool", tool_call_id) as ctx:
            ctx.emit_progress("Working...", progress=0.5)
            return result
    """

    def __init__(
        self,
        session_id: str,
        tool_name: str,
        tool_call_id: str | None = None,
        args: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id or str(uuid.uuid4())
        self.args = args or {}
        self._manager = get_stream_manager()
        self._start_time = 0.0

    def __enter__(self) -> StreamingContext:
        self._start_time = time.time()
        self._manager.emit(
            ToolEvent(
                event_type=EventType.TOOL_START,
                session_id=self.session_id,
                tool_name=self.tool_name,
                tool_call_id=self.tool_call_id,
                data={"args": self._truncate_args(self.args)},
            )
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = int((time.time() - self._start_time) * 1000)

        if exc_type is not None:
            # Error occurred
            self._manager.emit(
                ToolEvent(
                    event_type=EventType.TOOL_ERROR,
                    session_id=self.session_id,
                    tool_name=self.tool_name,
                    tool_call_id=self.tool_call_id,
                    data={
                        "error": str(exc_val),
                        "error_type": exc_type.__name__,
                        "duration_ms": duration_ms,
                    },
                )
            )
        else:
            # Success
            self._manager.emit(
                ToolEvent(
                    event_type=EventType.TOOL_END,
                    session_id=self.session_id,
                    tool_name=self.tool_name,
                    tool_call_id=self.tool_call_id,
                    data={"duration_ms": duration_ms},
                )
            )

        return False  # Don't suppress exceptions

    async def __aenter__(self) -> StreamingContext:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)

    def emit_progress(
        self,
        message: str,
        progress: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a progress update.

        Args:
            message: Human-readable progress message
            progress: Optional progress percentage (0.0 to 1.0)
            data: Optional additional data
        """
        event_data = {"message": message}
        if progress is not None:
            event_data["progress"] = max(0.0, min(1.0, progress))
        if data:
            event_data.update(data)

        self._manager.emit(
            ToolEvent(
                event_type=EventType.TOOL_PROGRESS,
                session_id=self.session_id,
                tool_name=self.tool_name,
                tool_call_id=self.tool_call_id,
                data=event_data,
            )
        )

    def emit_result_preview(
        self,
        preview: str,
        total_size: int | None = None,
    ) -> None:
        """Emit a preview of the result (for large outputs).

        Args:
            preview: Truncated preview of result
            total_size: Total size of full result
        """
        self.emit_progress(
            "Result preview",
            data={
                "preview": preview,
                "total_size": total_size,
            },
        )

    @staticmethod
    def _truncate_args(args: dict[str, Any], max_len: int = 200) -> dict[str, Any]:
        """Truncate long argument values for streaming."""
        truncated = {}
        for key, value in args.items():
            if isinstance(value, str) and len(value) > max_len:
                truncated[key] = value[:max_len] + f"... ({len(value)} chars)"
            elif isinstance(value, (list, dict)) and len(str(value)) > max_len:
                truncated[key] = f"<{type(value).__name__} with {len(value)} items>"
            else:
                truncated[key] = value
        return truncated


def emit_tool_event(
    session_id: str,
    tool_name: str,
    tool_call_id: str,
    event_type: EventType,
    data: dict[str, Any] | None = None,
) -> None:
    """Convenience function to emit a tool event.

    Args:
        session_id: Session ID
        tool_name: Name of the tool
        tool_call_id: Unique ID for this tool call
        event_type: Type of event
        data: Additional event data
    """
    get_stream_manager().emit(
        ToolEvent(
            event_type=event_type,
            session_id=session_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            data=data or {},
        )
    )
