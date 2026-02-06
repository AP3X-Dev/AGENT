"""State synchronization for Agent ↔ Gateway communication.

This module provides state synchronization between the Agent Worker and Gateway,
allowing both services to share session state with eventual consistency.

Supports:
1. Redis (recommended) - Real pub/sub, horizontal scaling
2. In-memory (fallback) - For single-instance deployments

Usage:
    from ag3nt_agent.state_sync import get_state_sync

    state_sync = await get_state_sync()
    session = await state_sync.get_session("session-123")
    await state_sync.update_session("session-123", {"messageCount": 5})
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("ag3nt.state_sync")


# =============================================================================
# Types
# =============================================================================


@dataclass
class SessionQuotas:
    """Session rate limiting quotas."""

    max_tokens_per_day: int = 100000
    max_requests_per_hour: int = 60
    tokens_used_today: int = 0
    requests_this_hour: int = 0
    quota_reset_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxTokensPerDay": self.max_tokens_per_day,
            "maxRequestsPerHour": self.max_requests_per_hour,
            "tokensUsedToday": self.tokens_used_today,
            "requestsThisHour": self.requests_this_hour,
            "quotaResetAt": self.quota_reset_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionQuotas:
        return cls(
            max_tokens_per_day=data.get("maxTokensPerDay", 100000),
            max_requests_per_hour=data.get("maxRequestsPerHour", 60),
            tokens_used_today=data.get("tokensUsedToday", 0),
            requests_this_hour=data.get("requestsThisHour", 0),
            quota_reset_at=data.get("quotaResetAt", ""),
        )


@dataclass
class SessionState:
    """Unified session state shared between Gateway and Agent."""

    # Identity
    session_id: str
    channel_type: str = ""
    channel_id: str = ""
    chat_id: str = ""
    user_id: str = ""
    user_name: str | None = None

    # Gateway-managed fields
    priority: int = 5
    assigned_agent: str | None = None
    directives: list[dict] = field(default_factory=list)
    quotas: SessionQuotas = field(default_factory=SessionQuotas)
    activation_mode: str = "always"
    paired: bool = False
    pairing_code: str | None = None

    # Agent-managed fields
    message_count: int = 0
    last_turn_at: str | None = None
    active_tools: list[str] = field(default_factory=list)
    pending_approvals: list[dict] = field(default_factory=list)

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Version for optimistic locking
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sessionId": self.session_id,
            "channelType": self.channel_type,
            "channelId": self.channel_id,
            "chatId": self.chat_id,
            "userId": self.user_id,
            "userName": self.user_name,
            "priority": self.priority,
            "assignedAgent": self.assigned_agent,
            "directives": self.directives,
            "quotas": self.quotas.to_dict(),
            "activationMode": self.activation_mode,
            "paired": self.paired,
            "pairingCode": self.pairing_code,
            "messageCount": self.message_count,
            "lastTurnAt": self.last_turn_at,
            "activeTools": self.active_tools,
            "pendingApprovals": self.pending_approvals,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "metadata": self.metadata,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        """Create from dictionary."""
        return cls(
            session_id=data.get("sessionId", ""),
            channel_type=data.get("channelType", ""),
            channel_id=data.get("channelId", ""),
            chat_id=data.get("chatId", ""),
            user_id=data.get("userId", ""),
            user_name=data.get("userName"),
            priority=data.get("priority", 5),
            assigned_agent=data.get("assignedAgent"),
            directives=data.get("directives", []),
            quotas=SessionQuotas.from_dict(data.get("quotas", {})),
            activation_mode=data.get("activationMode", "always"),
            paired=data.get("paired", False),
            pairing_code=data.get("pairingCode"),
            message_count=data.get("messageCount", 0),
            last_turn_at=data.get("lastTurnAt"),
            active_tools=data.get("activeTools", []),
            pending_approvals=data.get("pendingApprovals", []),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
            metadata=data.get("metadata", {}),
            version=data.get("version", 1),
        )


# =============================================================================
# In-Memory State Store
# =============================================================================


class InMemoryStateSync:
    """In-memory state synchronization (single-instance only)."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._subscribers: dict[str, list[Callable[[SessionState], None]]] = {}
        self._all_subscribers: list[Callable[[str, SessionState], None]] = []
        self._lock = asyncio.Lock()
        self._sub_lock = threading.Lock()

    async def get_session(self, session_id: str) -> SessionState | None:
        """Get session state."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def set_session(self, session_id: str, state: SessionState) -> None:
        """Set full session state."""
        async with self._lock:
            self._sessions[session_id] = state
        await self._notify(session_id, state)

    async def update_session(
        self,
        session_id: str,
        updates: dict[str, Any],
    ) -> SessionState:
        """Update specific fields of a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")

            # Apply updates
            state_dict = session.to_dict()
            state_dict.update(updates)
            state_dict["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state_dict["version"] = session.version + 1

            updated = SessionState.from_dict(state_dict)
            self._sessions[session_id] = updated

        await self._notify(session_id, updated)
        return updated

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                with self._sub_lock:
                    self._subscribers.pop(session_id, None)
                return True
            return False

    def subscribe(
        self,
        session_id: str,
        callback: Callable[[SessionState], None],
    ) -> Callable[[], None]:
        """Subscribe to session updates."""
        with self._sub_lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = []
            self._subscribers[session_id].append(callback)

        def unsubscribe() -> None:
            with self._sub_lock:
                if session_id in self._subscribers:
                    try:
                        self._subscribers[session_id].remove(callback)
                    except ValueError:
                        pass

        return unsubscribe

    def subscribe_all(
        self,
        callback: Callable[[str, SessionState], None],
    ) -> Callable[[], None]:
        """Subscribe to all session updates."""
        with self._sub_lock:
            self._all_subscribers.append(callback)

        def unsubscribe() -> None:
            with self._sub_lock:
                try:
                    self._all_subscribers.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    async def _notify(self, session_id: str, state: SessionState) -> None:
        """Notify subscribers of state change."""
        # Snapshot subscriber lists under lock, iterate outside
        with self._sub_lock:
            session_callbacks = list(self._subscribers.get(session_id, []))
            all_callbacks = list(self._all_subscribers)

        # Session-specific subscribers
        for callback in session_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")

        # All-session subscribers
        for callback in all_callbacks:
            try:
                callback(session_id, state)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")

    async def close(self) -> None:
        """Close the store."""
        async with self._lock:
            self._sessions.clear()
        with self._sub_lock:
            self._subscribers.clear()
            self._all_subscribers.clear()


# =============================================================================
# Redis State Store
# =============================================================================


class RedisStateSync:
    """Redis-backed state synchronization."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self.redis: Any = None
        self.pubsub: Any = None
        self._subscribers: dict[str, list[Callable[[SessionState], None]]] = {}
        self._all_subscribers: list[Callable[[str, SessionState], None]] = []
        self._listen_task: asyncio.Task | None = None
        self._key_prefix = "ag3nt:session:"
        self._channel_prefix = "ag3nt:updates:"

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            import redis.asyncio as redis

            self.redis = redis.from_url(self.redis_url)
            self.pubsub = self.redis.pubsub()

            # Subscribe to all session updates
            await self.pubsub.psubscribe(f"{self._channel_prefix}*")

            # Start listener
            self._listen_task = asyncio.create_task(self._listen())

            logger.info("Connected to Redis for state sync")
        except ImportError:
            raise ImportError(
                "redis package required for Redis state sync. "
                "Install with: pip install redis"
            )

    async def get_session(self, session_id: str) -> SessionState | None:
        """Get session state from Redis."""
        data = await self.redis.get(f"{self._key_prefix}{session_id}")
        if data:
            return SessionState.from_dict(json.loads(data))
        return None

    async def set_session(self, session_id: str, state: SessionState) -> None:
        """Set full session state in Redis."""
        await self.redis.set(
            f"{self._key_prefix}{session_id}",
            json.dumps(state.to_dict()),
        )
        await self._publish(session_id, state)

    async def update_session(
        self,
        session_id: str,
        updates: dict[str, Any],
    ) -> SessionState:
        """Update session state atomically."""
        # Get current state
        data = await self.redis.get(f"{self._key_prefix}{session_id}")
        if not data:
            raise ValueError(f"Session not found: {session_id}")

        state_dict = json.loads(data)
        state_dict.update(updates)
        state_dict["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state_dict["version"] = state_dict.get("version", 0) + 1

        await self.redis.set(
            f"{self._key_prefix}{session_id}",
            json.dumps(state_dict),
        )

        updated = SessionState.from_dict(state_dict)
        await self._publish(session_id, updated)

        return updated

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session from Redis."""
        result = await self.redis.delete(f"{self._key_prefix}{session_id}")
        return result > 0

    def subscribe(
        self,
        session_id: str,
        callback: Callable[[SessionState], None],
    ) -> Callable[[], None]:
        """Subscribe to session updates."""
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(callback)

        def unsubscribe() -> None:
            if session_id in self._subscribers:
                try:
                    self._subscribers[session_id].remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def subscribe_all(
        self,
        callback: Callable[[str, SessionState], None],
    ) -> Callable[[], None]:
        """Subscribe to all session updates."""
        self._all_subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._all_subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    async def _publish(self, session_id: str, state: SessionState) -> None:
        """Publish state update to Redis."""
        await self.redis.publish(
            f"{self._channel_prefix}{session_id}",
            json.dumps(state.to_dict()),
        )

    async def _listen(self) -> None:
        """Listen for Redis pub/sub messages."""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "pmessage":
                    try:
                        channel = message["channel"].decode()
                        session_id = channel.replace(self._channel_prefix, "")
                        data = json.loads(message["data"])
                        state = SessionState.from_dict(data)

                        # Notify local subscribers
                        for callback in self._subscribers.get(session_id, []):
                            try:
                                callback(state)
                            except Exception as e:
                                logger.error(f"Subscriber error: {e}")

                        for callback in self._all_subscribers:
                            try:
                                callback(session_id, state)
                            except Exception as e:
                                logger.error(f"Subscriber error: {e}")

                    except Exception as e:
                        logger.error(f"Message parse error: {e}")
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """Close Redis connections."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()

        if self.redis:
            await self.redis.close()


# =============================================================================
# Factory
# =============================================================================

_state_sync: InMemoryStateSync | RedisStateSync | None = None
_state_sync_lock = asyncio.Lock()


async def get_state_sync() -> InMemoryStateSync | RedisStateSync:
    """Get or create the state sync instance.

    Uses Redis if AG3NT_REDIS_URL is set, otherwise uses in-memory store.
    """
    global _state_sync

    if _state_sync is not None:
        return _state_sync

    async with _state_sync_lock:
        if _state_sync is not None:
            return _state_sync

        redis_url = os.environ.get("AG3NT_REDIS_URL")

        if redis_url:
            try:
                sync = RedisStateSync(redis_url)
                await sync.connect()
                _state_sync = sync
                logger.info("Using Redis state sync")
            except Exception as e:
                logger.warning(f"Redis failed, using in-memory: {e}")
                _state_sync = InMemoryStateSync()
        else:
            _state_sync = InMemoryStateSync()
            logger.info("Using in-memory state sync")

        return _state_sync


async def close_state_sync() -> None:
    """Close the state sync instance."""
    global _state_sync

    if _state_sync:
        await _state_sync.close()
        _state_sync = None


def is_using_redis() -> bool:
    """Check if using Redis backend."""
    return isinstance(_state_sync, RedisStateSync)
