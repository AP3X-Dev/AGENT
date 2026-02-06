"""Tests for batch tool execution."""

import pytest
from unittest.mock import patch, MagicMock

from ag3nt_agent.batch_tool import (
    batch,
    DENIED_TOOLS,
    MAX_BATCH_SIZE,
    _resolve_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_tool(name: str, return_value=None):
    """Create a mock LangChain tool."""
    mock = MagicMock()
    mock.name = name
    if return_value is None:
        return_value = {"data": f"result from {name}"}
    mock.invoke.return_value = return_value
    return mock


@pytest.fixture
def mock_tools():
    """Provide a set of mock tools and patch _resolve_tools."""
    tools = {
        "grep_tool": _make_mock_tool("grep_tool", {"matches": ["a.py"], "count": 1}),
        "glob_tool": _make_mock_tool("glob_tool", {"files": ["b.py"]}),
        "read_file": _make_mock_tool("read_file", {"content": "hello"}),
    }
    with patch("ag3nt_agent.batch_tool._resolve_tools", return_value=tools):
        yield tools


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------


class TestBatchBasic:
    """Basic batch execution scenarios."""

    def test_single_tool_call(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "hello"}},
            ],
        })
        assert result["total"] == 1
        assert result["errors"] == 0
        assert "0" in result["results"]
        assert result["results"]["0"]["status"] == "ok"

    def test_multiple_tool_calls(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "a"}},
                {"tool_name": "glob_tool", "arguments": {"pattern": "*.py"}},
                {"tool_name": "read_file", "arguments": {"path": "x.py"}},
            ],
        })
        assert result["total"] == 3
        assert result["errors"] == 0
        for i in range(3):
            assert result["results"][str(i)]["status"] == "ok"

    def test_tools_actually_invoked(self, mock_tools):
        batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "test"}},
            ],
        })
        mock_tools["grep_tool"].invoke.assert_called_once()


# ---------------------------------------------------------------------------
# Denied tools
# ---------------------------------------------------------------------------


class TestDeniedTools:
    """Write/destructive/recursive tools are denied."""

    @pytest.mark.parametrize("tool_name", [
        "exec_command",
        "write_file",
        "edit_file",
        "delete_file",
        "apply_patch",
        "git_commit",
        "multi_edit",
        "batch",
        "ask_user",
    ])
    def test_denied_tool_rejected(self, mock_tools, tool_name):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": tool_name, "arguments": {}},
            ],
        })
        assert "error" in result
        assert "not allowed" in result["error"]

    def test_recursive_batch_denied(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "batch", "arguments": {"tool_calls": []}},
            ],
        })
        assert "error" in result
        assert "not allowed" in result["error"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Individual errors don't fail the entire batch."""

    def test_unknown_tool_returns_error(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "nonexistent_tool", "arguments": {}},
            ],
        })
        assert result["total"] == 1
        assert result["errors"] == 1
        assert result["results"]["0"]["status"] == "error"
        assert "not found" in result["results"]["0"]["error"]

    def test_mixed_success_and_failure(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "ok"}},
                {"tool_name": "nonexistent", "arguments": {}},
            ],
        })
        assert result["total"] == 2
        assert result["errors"] == 1
        assert result["results"]["0"]["status"] == "ok"
        assert result["results"]["1"]["status"] == "error"

    def test_tool_raises_exception(self, mock_tools):
        mock_tools["grep_tool"].invoke.side_effect = RuntimeError("boom")
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "x"}},
            ],
        })
        assert result["total"] == 1
        assert result["errors"] == 1
        assert "error" in result["results"]["0"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Input validation."""

    def test_empty_tool_calls(self, mock_tools):
        result = batch.invoke({"tool_calls": []})
        assert "error" in result
        assert "No tool calls" in result["error"]

    def test_missing_tool_name(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [{"arguments": {"pattern": "x"}}],
        })
        assert "error" in result
        assert "missing" in result["error"].lower()

    def test_max_batch_size(self, mock_tools):
        calls = [{"tool_name": "grep_tool", "arguments": {}} for _ in range(MAX_BATCH_SIZE + 1)]
        result = batch.invoke({"tool_calls": calls})
        assert "error" in result
        assert "Too many" in result["error"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify configuration constants."""

    def test_max_batch_size(self):
        assert MAX_BATCH_SIZE == 25

    def test_denied_tools_has_core_set(self):
        assert "exec_command" in DENIED_TOOLS
        assert "write_file" in DENIED_TOOLS
        assert "edit_file" in DENIED_TOOLS
        assert "batch" in DENIED_TOOLS

    def test_denied_tools_immutable(self):
        assert isinstance(DENIED_TOOLS, frozenset)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestResultStructure:
    """Return value has expected fields."""

    def test_success_result_fields(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "x"}},
            ],
        })
        assert "results" in result
        assert "total" in result
        assert "errors" in result

    def test_per_call_result_fields(self, mock_tools):
        result = batch.invoke({
            "tool_calls": [
                {"tool_name": "grep_tool", "arguments": {"pattern": "x"}},
            ],
        })
        call_result = result["results"]["0"]
        assert "status" in call_result
        assert "result" in call_result
