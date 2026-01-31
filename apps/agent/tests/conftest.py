"""Shared pytest fixtures for AG3NT Agent tests.

This module provides common fixtures and utilities for testing the AG3NT agent.
Import these fixtures in your test files - they are automatically available.
"""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Temporary Directory Fixtures
# ============================================================================

@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory for file operations."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def temp_ag3nt_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary ~/.ag3nt directory and set AG3NT_HOME."""
    ag3nt_home = tmp_path / ".ag3nt"
    ag3nt_home.mkdir()
    monkeypatch.setenv("AG3NT_HOME", str(ag3nt_home))
    return ag3nt_home


@pytest.fixture
def sample_files(temp_workspace: Path) -> dict[str, Path]:
    """Create sample files for testing file operations."""
    files = {}
    
    # Create a text file
    text_file = temp_workspace / "sample.txt"
    text_file.write_text("Hello, World!\nThis is a test file.\n")
    files["text"] = text_file
    
    # Create a Python file
    py_file = temp_workspace / "sample.py"
    py_file.write_text('def hello():\n    return "Hello"\n')
    files["python"] = py_file
    
    # Create a nested directory with files
    nested = temp_workspace / "nested"
    nested.mkdir()
    nested_file = nested / "nested.txt"
    nested_file.write_text("Nested content\n")
    files["nested"] = nested_file
    
    return files


# ============================================================================
# Mock LLM Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_response():
    """Factory for creating mock LLM responses."""
    def _create(
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        stop_reason: str = "end_turn"
    ) -> MagicMock:
        response = MagicMock()
        response.content = content
        response.tool_calls = tool_calls or []
        response.stop_reason = stop_reason
        return response
    return _create


@pytest.fixture
def mock_anthropic_client(mock_llm_response) -> AsyncMock:
    """Mock Anthropic API client for testing."""
    client = AsyncMock()
    client.messages.create.return_value = mock_llm_response("Test response")
    return client


@pytest.fixture
def mock_openai_client(mock_llm_response) -> AsyncMock:
    """Mock OpenAI API client for testing."""
    client = AsyncMock()
    response = MagicMock()
    response.choices = [MagicMock(message=mock_llm_response("Test response"))]
    client.chat.completions.create.return_value = response
    return client


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def default_config() -> dict[str, Any]:
    """Default test configuration for the agent."""
    return {
        "model": {
            "provider": "anthropic",
            "name": "claude-sonnet-4-5-20250929",
        },
        "shell": {
            "timeout": 30,
            "max_output_bytes": 10000,
            "allowlist_mode": False,
        },
        "filesystem": {
            "tool_token_limit": 50000,
        },
        "security": {
            "blocked_patterns": [".env", "*.pem", "*.key"],
            "max_file_size": 10 * 1024 * 1024,  # 10MB
        },
    }


# ============================================================================
# Session Fixtures
# ============================================================================

@pytest.fixture
def test_session_id() -> str:
    """Generate a test session ID."""
    return "test-session-001"


@pytest.fixture
def mock_session() -> dict[str, Any]:
    """Create a mock session object."""
    return {
        "session_id": "test-session-001",
        "channel": "test",
        "user_id": "test-user",
        "created_at": "2026-01-29T00:00:00Z",
        "state": "active",
        "metadata": {},
    }


# ============================================================================
# Tool Execution Fixtures
# ============================================================================

@pytest.fixture
def mock_tool_runtime() -> MagicMock:
    """Mock tool runtime for testing middleware."""
    runtime = MagicMock()
    runtime.tool_call_id = "test-tool-call-001"
    runtime.context = {}
    return runtime


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove potentially interfering environment variables."""
    env_vars_to_remove = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "AG3NT_DEBUG",
    ]
    for var in env_vars_to_remove:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def test_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up test environment variables."""
    env = {
        "AG3NT_ENV": "test",
        "AG3NT_LOG_LEVEL": "DEBUG",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env

