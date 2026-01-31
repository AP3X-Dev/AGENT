"""Tests for shell command execution middleware."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from ag3nt_agent.shell_middleware import ShellMiddleware, ShellResult, SecurityLevel
from ag3nt_agent.shell_security import PathSandbox, ShellSecurityValidator
from langchain_core.tools.base import ToolException


class TestShellMiddleware:
    """Test suite for ShellMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = ShellMiddleware(
            workspace_root="/test/workspace",
            timeout=30.0,
            max_output_bytes=50000
        )

        assert middleware._workspace_root == "/test/workspace"
        assert middleware._timeout == 30.0
        assert middleware._max_output_bytes == 50000
        assert middleware._tool_name == "shell"
        assert len(middleware.tools) == 1

    def test_initialization_default_values(self):
        """Test middleware initialization with defaults."""
        middleware = ShellMiddleware(workspace_root="/test")

        assert middleware._timeout == 60.0
        assert middleware._max_output_bytes == 100_000

    def test_tool_metadata(self):
        """Test that shell tool has proper metadata."""
        middleware = ShellMiddleware(workspace_root="/test")
        tool = middleware.tools[0]

        assert tool.name == "shell"
        assert tool.description is not None
        assert "shell command" in tool.description.lower()
        assert "/test" in tool.description

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_run_command_success(self, mock_run):
        """Test successful command execution."""
        mock_result = MagicMock()
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("echo test", tool_call_id="test-id")

        assert result.content == "Command output"
        assert result.status == "success"
        assert result.tool_call_id == "test-id"
        mock_run.assert_called_once()

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_run_command_with_stderr(self, mock_run):
        """Test command execution with stderr output."""
        mock_result = MagicMock()
        mock_result.stdout = "Output"
        mock_result.stderr = "Warning message"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("test command", tool_call_id="test-id")

        assert "Output" in result.content
        assert "[stderr] Warning message" in result.content
        assert result.status == "success"

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_run_command_non_zero_exit(self, mock_run):
        """Test command execution with non-zero exit code."""
        mock_result = MagicMock()
        mock_result.stdout = "Error output"
        mock_result.stderr = ""
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("failing command", tool_call_id="test-id")

        assert "Error output" in result.content
        assert "Exit code: 1" in result.content
        assert result.status == "error"

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_run_command_timeout(self, mock_run):
        """Test command execution timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30.0)

        middleware = ShellMiddleware(workspace_root="/test", timeout=30.0)
        result = middleware._run_shell_command("slow command", tool_call_id="test-id")

        assert "timed out" in result.content.lower()
        assert "30.0 seconds" in result.content
        assert result.status == "error"

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_run_command_exception(self, mock_run):
        """Test command execution with exception."""
        mock_run.side_effect = Exception("Unexpected error")

        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("bad command", tool_call_id="test-id")

        assert "Error executing command" in result.content
        assert "Unexpected error" in result.content
        assert result.status == "error"

    def test_run_command_empty_string(self):
        """Test command execution with empty string."""
        middleware = ShellMiddleware(workspace_root="/test")

        with pytest.raises(ToolException) as exc_info:
            middleware._run_shell_command("", tool_call_id="test-id")

        assert "non-empty command string" in str(exc_info.value)

    def test_run_command_none(self):
        """Test command execution with None."""
        middleware = ShellMiddleware(workspace_root="/test")

        with pytest.raises(ToolException) as exc_info:
            middleware._run_shell_command(None, tool_call_id="test-id")

        assert "non-empty command string" in str(exc_info.value)

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_output_truncation(self, mock_run):
        """Test output truncation when exceeding max bytes."""
        long_output = "A" * 150000  # Longer than default max_output_bytes
        mock_result = MagicMock()
        mock_result.stdout = long_output
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test", max_output_bytes=100000)
        result = middleware._run_shell_command("command", tool_call_id="test-id")

        assert "Output truncated" in result.content
        assert "100000 bytes" in result.content
        assert len(result.content) < 150000

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_no_output(self, mock_run):
        """Test command with no output."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("silent command", tool_call_id="test-id")

        assert result.content == "<no output>"
        assert result.status == "success"

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_custom_environment(self, mock_run):
        """Test command execution with custom environment."""
        mock_result = MagicMock()
        mock_result.stdout = "Output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        custom_env = {"CUSTOM_VAR": "value"}
        middleware = ShellMiddleware(workspace_root="/test", env=custom_env)
        middleware._run_shell_command("echo $CUSTOM_VAR", tool_call_id="test-id")

        # Verify subprocess.run was called with custom env
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["env"] == custom_env

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_working_directory(self, mock_run):
        """Test that commands run in correct working directory."""
        mock_result = MagicMock()
        mock_result.stdout = "Output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/custom/workspace")
        middleware._run_shell_command("pwd", tool_call_id="test-id")

        # Verify subprocess.run was called with correct cwd
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/custom/workspace"



class TestShellResult:
    """Tests for ShellResult dataclass."""

    def test_success_property(self):
        """Test success property returns True for exit_code 0."""
        result = ShellResult(
            stdout="output",
            stderr="",
            exit_code=0,
            duration=0.5,
            truncated=False,
            command="echo test",
        )
        assert result.success is True

    def test_success_property_failure(self):
        """Test success property returns False for non-zero exit_code."""
        result = ShellResult(
            stdout="",
            stderr="error",
            exit_code=1,
            duration=0.5,
            truncated=False,
            command="bad command",
        )
        assert result.success is False

    def test_success_property_security_blocked(self):
        """Test success property returns False when security blocked."""
        result = ShellResult(
            stdout="",
            stderr="",
            exit_code=0,
            duration=0.0,
            truncated=False,
            command="rm -rf /",
            security_blocked=True,
            security_reason="Dangerous command",
        )
        assert result.success is False

    def test_output_property_combines_stdout_stderr(self):
        """Test output property combines stdout and stderr."""
        result = ShellResult(
            stdout="stdout line",
            stderr="stderr line",
            exit_code=0,
            duration=0.5,
            truncated=False,
        )
        output = result.output
        assert "stdout line" in output
        assert "[stderr] stderr line" in output

    def test_output_property_no_output(self):
        """Test output property returns placeholder for empty output."""
        result = ShellResult(
            stdout="",
            stderr="",
            exit_code=0,
            duration=0.5,
            truncated=False,
        )
        assert result.output == "<no output>"

    def test_to_content_security_blocked(self):
        """Test to_content for security blocked commands."""
        result = ShellResult(
            stdout="",
            stderr="",
            exit_code=-1,
            duration=0.0,
            truncated=False,
            security_blocked=True,
            security_reason="Dangerous pattern detected",
        )
        content = result.to_content()
        assert "Security blocked:" in content
        assert "Dangerous pattern detected" in content

    def test_to_content_truncated(self):
        """Test to_content includes truncation message."""
        result = ShellResult(
            stdout="A" * 1000,
            stderr="",
            exit_code=0,
            duration=0.5,
            truncated=True,
            truncated_at=1000,
        )
        content = result.to_content()
        assert "truncated" in content.lower()

    def test_to_content_with_exit_code(self):
        """Test to_content includes exit code for failures."""
        result = ShellResult(
            stdout="error output",
            stderr="",
            exit_code=127,
            duration=0.5,
            truncated=False,
        )
        content = result.to_content()
        assert "Exit code: 127" in content


class TestShellMiddlewareSecurityIntegration:
    """Tests for security integration in ShellMiddleware."""

    def test_initialization_with_security_level(self):
        """Test middleware initializes with security level."""
        middleware = ShellMiddleware(
            workspace_root="/test",
            security_level=SecurityLevel.STRICT,
        )
        assert middleware._security_level == SecurityLevel.STRICT

    def test_security_validator_accessible(self):
        """Test security validator is accessible via property."""
        middleware = ShellMiddleware(workspace_root="/test")
        assert isinstance(middleware.security_validator, ShellSecurityValidator)

    def test_path_sandbox_accessible(self):
        """Test path sandbox is accessible via property."""
        middleware = ShellMiddleware(workspace_root="/test")
        assert isinstance(middleware.path_sandbox, PathSandbox)

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_dangerous_command_blocked(self, mock_run):
        """Test dangerous commands are blocked before execution."""
        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("rm -rf /", tool_call_id="test-id")

        # Command should be blocked, subprocess.run should NOT be called
        mock_run.assert_not_called()
        assert "Security blocked" in result.content

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_safe_command_executed(self, mock_run):
        """Test safe commands are executed."""
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test")
        result = middleware._run_shell_command("echo hello", tool_call_id="test-id")

        mock_run.assert_called_once()
        assert result.status == "success"

    @patch('ag3nt_agent.shell_middleware.subprocess.run')
    def test_duration_tracked(self, mock_run):
        """Test execution duration is tracked."""
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        middleware = ShellMiddleware(workspace_root="/test")
        shell_result = middleware._execute_command("echo hello")

        assert shell_result.duration >= 0
        assert shell_result.command == "echo hello"

