"""Test data generators for AG3NT Agent tests.

Provides factories for creating test data like sessions, messages, etc.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class DataGenerator:
    """Factory for generating test data.

    Usage:
        gen = DataGenerator()
        session = gen.session()
        message = gen.message(session_id=session["session_id"])
    """

    def __init__(self, seed: str = "test") -> None:
        self._seed = seed
        self._counter = 0

    def _next_id(self) -> str:
        """Generate a unique ID."""
        self._counter += 1
        return f"{self._seed}-{self._counter:04d}"

    def session(
        self,
        session_id: str | None = None,
        channel: str = "test",
        user_id: str = "test-user",
        state: str = "active",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a test session."""
        return {
            "session_id": session_id or f"session-{self._next_id()}",
            "channel": channel,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state": state,
            "metadata": kwargs.get("metadata", {}),
            **kwargs,
        }

    def message(
        self,
        session_id: str | None = None,
        role: str = "user",
        content: str = "Test message",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a test message."""
        return {
            "message_id": f"msg-{self._next_id()}",
            "session_id": session_id or f"session-{self._next_id()}",
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }

    def tool_call(
        self,
        tool_name: str = "test_tool",
        tool_input: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a test tool call."""
        return {
            "id": f"tool-{self._next_id()}",
            "name": tool_name,
            "input": tool_input or {},
            **kwargs,
        }

    def approval_request(
        self,
        session_id: str | None = None,
        tool_name: str = "shell",
        tool_input: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a test approval request."""
        return {
            "approval_id": f"approval-{self._next_id()}",
            "session_id": session_id or f"session-{self._next_id()}",
            "tool_name": tool_name,
            "tool_input": tool_input or {"command": "ls"},
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }

    def skill(
        self,
        name: str = "test-skill",
        description: str = "A test skill",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a test skill."""
        return {
            "skill_id": f"skill-{self._next_id()}",
            "name": name,
            "description": description,
            "content": kwargs.get("content", "# Test Skill\n\nThis is a test skill."),
            "tags": kwargs.get("tags", ["test"]),
            **kwargs,
        }

    def config(self, **overrides: Any) -> dict[str, Any]:
        """Generate a test configuration."""
        base = {
            "model": {
                "provider": "anthropic",
                "name": "claude-sonnet-4-5-20250929",
            },
            "shell": {
                "timeout": 30,
                "max_output_bytes": 10000,
            },
            "filesystem": {
                "tool_token_limit": 50000,
            },
        }
        # Deep merge overrides
        for key, value in overrides.items():
            if isinstance(value, dict) and key in base:
                base[key].update(value)
            else:
                base[key] = value
        return base

    def reset(self) -> None:
        """Reset the counter."""
        self._counter = 0

