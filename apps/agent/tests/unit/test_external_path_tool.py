"""Tests for external path access tool."""

import os
import pytest

from ag3nt_agent.external_path_tool import (
    EXTERNAL_ACCESS_TOOL,
    check_and_request_external_access,
    format_external_access_request,
    get_external_access_tools,
    request_external_access,
)
from ag3nt_agent.tool_policy import PathProtection


class TestExternalAccessTool:
    """Tests for the request_external_access tool."""

    @pytest.fixture(autouse=True)
    def reset_path_protection(self):
        """Reset PathProtection singleton before each test."""
        PathProtection.reset_instance()
        yield
        PathProtection.reset_instance()

    def test_tool_name_constant(self):
        """Test tool name constant is correct."""
        assert EXTERNAL_ACCESS_TOOL == "request_external_access"

    def test_get_external_access_tools_returns_list(self):
        """Test that get_external_access_tools returns a list."""
        tools = get_external_access_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0].name == "request_external_access"

    def test_check_and_request_no_workspace(self):
        """Test that access is allowed when no workspace is set."""
        allowed, msg = check_and_request_external_access(
            "/some/path/file.txt",
            session_id="test-session",
        )
        assert allowed is True
        assert msg is None

    def test_check_and_request_within_workspace(self):
        """Test that access is allowed for paths within workspace."""
        protection = PathProtection.get_instance("/workspace")

        allowed, msg = check_and_request_external_access(
            "/workspace/subdir/file.txt",
            session_id="test-session",
        )
        assert allowed is True
        assert msg is None

    def test_check_and_request_external_path(self):
        """Test that external paths require approval."""
        protection = PathProtection.get_instance("/workspace")

        allowed, msg = check_and_request_external_access(
            "/other/path/file.txt",
            session_id="test-session",
            operation="read",
        )
        assert allowed is False
        assert msg is not None
        assert "outside" in msg.lower() or "workspace" in msg.lower()

    def test_check_and_request_approved_path(self):
        """Test that previously approved paths are allowed."""
        protection = PathProtection.get_instance("/workspace")

        # Record approval
        protection.record_approval("test-session", "/external/dir/file.txt", True)

        # Now check should pass
        allowed, msg = check_and_request_external_access(
            "/external/dir/another.txt",  # Same directory
            session_id="test-session",
        )
        assert allowed is True
        assert msg is None


class TestFormatExternalAccessRequest:
    """Tests for the format_external_access_request function."""

    @pytest.fixture(autouse=True)
    def setup_protection(self):
        """Set up PathProtection with a workspace."""
        PathProtection.reset_instance()
        PathProtection.get_instance("/workspace")
        yield
        PathProtection.reset_instance()

    def test_format_request_basic(self):
        """Test basic request formatting."""
        tool_call = {
            "args": {
                "path": "/external/path/file.txt",
                "operation": "read",
            }
        }

        result = format_external_access_request(tool_call)

        assert "External Path Access Request" in result
        # Path may be normalized differently on Windows vs Unix
        assert "external" in result.lower()
        assert "file.txt" in result
        assert "read" in result
        assert "workspace" in result.lower()

    def test_format_request_with_reason(self):
        """Test request formatting with reason."""
        tool_call = {
            "args": {
                "path": "/some/file.txt",
                "operation": "write",
                "reason": "User wants to save data",
            }
        }

        result = format_external_access_request(tool_call)

        assert "User wants to save data" in result

    def test_format_request_shows_workspace(self):
        """Test that workspace path is shown."""
        tool_call = {
            "args": {
                "path": "/external/file.txt",
                "operation": "read",
            }
        }

        result = format_external_access_request(tool_call)

        # Workspace is shown (may be normalized on Windows)
        assert "workspace" in result.lower()


class TestRequestExternalAccessTool:
    """Tests for the request_external_access tool function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up for each test."""
        PathProtection.reset_instance()
        # Set up a mock session ID
        os.environ["AG3NT_CURRENT_SESSION"] = "test-session-123"
        yield
        PathProtection.reset_instance()
        os.environ.pop("AG3NT_CURRENT_SESSION", None)

    def test_tool_invocation_within_workspace(self):
        """Test tool returns approved for workspace paths."""
        PathProtection.get_instance("/workspace")

        result = request_external_access.invoke({
            "path": "/workspace/file.txt",
            "operation": "read",
            "reason": "test",
        })

        assert "approved" in result.lower()
        assert "workspace" in result.lower()

    def test_tool_records_approval(self):
        """Test that tool records approval after HITL."""
        PathProtection.get_instance("/workspace")

        # Simulate tool being called after HITL approval
        result = request_external_access.invoke({
            "path": "/external/dir/file.txt",
            "operation": "write",
            "reason": "User requested",
        })

        assert "approved" in result.lower()

        # Verify approval was recorded
        protection = PathProtection.get_instance()
        allowed, _ = protection.check_path(
            "/external/dir/another.txt",  # Same directory
            "test-session-123",
        )
        assert allowed is True
