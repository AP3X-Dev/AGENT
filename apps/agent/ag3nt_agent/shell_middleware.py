"""Shell middleware that exposes a shell tool to AG3NT.

This middleware provides shell command execution capability to the agent.
Commands run in the workspace directory with configurable timeout and output limits.

Security Note:
- Security validation layer blocks dangerous patterns (rm -rf, fork bombs, etc.)
- Path sandboxing restricts operations to allowed directories
- HITL (Human-in-the-Loop) approval remains the primary safety mechanism.
- The `shell` tool should be configured in `interrupt_on` to require user approval.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langchain_core.tools.base import ToolException

from ag3nt_agent.shell_security import (
    PathSandbox,
    SecurityLevel,
    ShellSecurityValidator,
    ValidationResult,
)

try:
    from ag3nt_agent.exec_approval import ExecApprovalEvaluator
    _EXEC_APPROVAL_AVAILABLE = True
except ImportError:
    _EXEC_APPROVAL_AVAILABLE = False


@dataclass(frozen=True)
class ShellResult:
    """Structured result from shell command execution.

    Attributes:
        stdout: Standard output from the command.
        stderr: Standard error from the command.
        exit_code: Process exit code (0 = success).
        duration: Execution time in seconds.
        truncated: Whether output was truncated.
        truncated_at: Byte position where output was truncated, if applicable.
        command: The executed command.
        security_blocked: Whether the command was blocked by security validation.
        security_reason: Reason for security block, if applicable.
    """

    stdout: str
    stderr: str
    exit_code: int
    duration: float
    truncated: bool
    truncated_at: int | None = None
    command: str = ""
    security_blocked: bool = False
    security_reason: str = ""

    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.exit_code == 0 and not self.security_blocked

    @property
    def output(self) -> str:
        """Get combined output (stdout + stderr)."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            for line in self.stderr.strip().split("\n"):
                parts.append(f"[stderr] {line}")
        return "\n".join(parts) if parts else "<no output>"

    def to_content(self) -> str:
        """Convert result to ToolMessage content string."""
        if self.security_blocked:
            return f"Security blocked: {self.security_reason}"

        content = self.output

        if self.truncated and self.truncated_at is not None:
            content += f"\n\n... Output truncated at {self.truncated_at} bytes."

        if self.exit_code != 0:
            content = f"{content.rstrip()}\n\nExit code: {self.exit_code}"

        return content


class ShellMiddleware(AgentMiddleware[AgentState, Any]):
    """Provide shell access to agents via a `shell` tool.

    This middleware adds a shell command execution capability to the agent.
    Commands are executed directly on the host machine using subprocess.

    Security:
    - Security validation blocks dangerous patterns (rm -rf, fork bombs, etc.)
    - Path sandboxing restricts operations to allowed directories
    - Use `interrupt_on={"shell": True}` for HITL approval
    - Timeout prevents runaway processes
    - Output is truncated to prevent memory issues
    """

    def __init__(
        self,
        *,
        workspace_root: str,
        timeout: float = 60.0,
        max_output_bytes: int = 100_000,
        env: dict[str, str] | None = None,
        security_level: SecurityLevel = SecurityLevel.STANDARD,
        enable_path_sandbox: bool = True,
        allowed_paths: list[str | Path] | None = None,
    ) -> None:
        """Initialize the ShellMiddleware.

        Args:
            workspace_root: Working directory for shell commands.
            timeout: Maximum time in seconds to wait for command completion.
                Defaults to 60 seconds.
            max_output_bytes: Maximum number of bytes to capture from command output.
                Defaults to 100,000 bytes.
            env: Environment variables to pass to the subprocess. If None,
                uses the current process's environment. Defaults to None.
            security_level: Security validation strictness level.
                Defaults to STANDARD (blocks dangerous and suspicious commands).
            enable_path_sandbox: Whether to enforce path sandboxing.
                Defaults to True.
            allowed_paths: Additional paths to allow in the sandbox.
                Workspace root is always allowed. Defaults to None.
        """
        super().__init__()
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._tool_name = "shell"
        self._env = env if env is not None else os.environ.copy()
        self._workspace_root = workspace_root
        self._security_level = security_level
        self._enable_path_sandbox = enable_path_sandbox

        # Initialize security validator
        self._security_validator = ShellSecurityValidator(
            security_level=security_level
        )

        # Initialize path sandbox with workspace root
        sandbox_paths = [Path(workspace_root)]
        if allowed_paths:
            sandbox_paths.extend(Path(p) for p in allowed_paths)

        self._path_sandbox = PathSandbox(
            allowed_paths=sandbox_paths,
            allow_temp_access=True,
            allow_home_access=False,
        )

        # Build description with working directory information
        description = (
            f"Execute a shell command on the host machine. Commands run in "
            f"the working directory: {workspace_root}. Each command runs in a fresh shell "
            f"environment. Output is truncated if it exceeds {max_output_bytes} bytes. "
            f"Commands timeout after {timeout} seconds. "
            f"Security level: {security_level.value}."
        )

        @tool(self._tool_name, description=description)
        def shell_tool(
            command: str,
            runtime: ToolRuntime[None, AgentState],
        ) -> ToolMessage | str:
            """Execute a shell command.

            Args:
                command: The shell command to execute.
                runtime: The tool runtime context.
            """
            return self._run_shell_command(command, tool_call_id=runtime.tool_call_id)

        self._shell_tool = shell_tool
        self.tools = [self._shell_tool]

    def _run_shell_command(
        self,
        command: str,
        *,
        tool_call_id: str | None,
    ) -> ToolMessage | str:
        """Execute a shell command and return the result.

        Args:
            command: The shell command to execute.
            tool_call_id: The tool call ID for creating a ToolMessage.

        Returns:
            A ToolMessage with the command output or an error message.
        """
        if not command or not isinstance(command, str):
            msg = "Shell tool expects a non-empty command string."
            raise ToolException(msg)

        # Run the internal execution and get structured result
        shell_result = self._execute_command(command)

        # Convert to ToolMessage for compatibility
        status = "success" if shell_result.success else "error"

        return ToolMessage(
            content=shell_result.to_content(),
            tool_call_id=tool_call_id,
            name=self._tool_name,
            status=status,
        )

    def _execute_command(self, command: str) -> ShellResult:
        """Execute a shell command and return a structured result.

        This internal method performs security validation, path sandboxing,
        and command execution with duration tracking.

        Args:
            command: The shell command to execute.

        Returns:
            ShellResult with detailed execution information.
        """
        start_time = time.perf_counter()

        # Exec approval evaluation (granular allow/deny)
        if _EXEC_APPROVAL_AVAILABLE:
            try:
                evaluator = ExecApprovalEvaluator.get_instance()
                approval = evaluator.evaluate(command)
                if approval.decision == "deny":
                    return ShellResult(
                        stdout="",
                        stderr="",
                        exit_code=-1,
                        duration=time.perf_counter() - start_time,
                        truncated=False,
                        command=command,
                        security_blocked=True,
                        security_reason=f"Exec policy denied: {approval.reason}",
                    )
            except Exception:
                pass  # Fall through to existing security validation

        # Security validation
        security_result = self._security_validator.validate(command)
        if not security_result.is_safe:
            return ShellResult(
                stdout="",
                stderr="",
                exit_code=-1,
                duration=time.perf_counter() - start_time,
                truncated=False,
                command=command,
                security_blocked=True,
                security_reason=security_result.reason,
            )

        # Path sandbox validation
        if self._enable_path_sandbox:
            path_result = self._path_sandbox.validate_command_paths(
                command, self._workspace_root
            )
            if not path_result.is_safe:
                return ShellResult(
                    stdout="",
                    stderr="",
                    exit_code=-1,
                    duration=time.perf_counter() - start_time,
                    truncated=False,
                    command=command,
                    security_blocked=True,
                    security_reason=f"Path sandbox: {path_result.reason}",
                )

        # Execute the command
        try:
            result = subprocess.run(
                command,
                check=False,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=self._env,
                cwd=self._workspace_root,
            )

            duration = time.perf_counter() - start_time
            stdout = result.stdout
            stderr = result.stderr

            # Check for truncation
            combined_length = len(stdout) + len(stderr)
            truncated = combined_length > self._max_output_bytes

            if truncated:
                # Truncate proportionally
                if len(stdout) > self._max_output_bytes:
                    stdout = stdout[: self._max_output_bytes]
                remaining = self._max_output_bytes - len(stdout)
                if remaining > 0 and len(stderr) > remaining:
                    stderr = stderr[:remaining]

            return ShellResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                duration=duration,
                truncated=truncated,
                truncated_at=self._max_output_bytes if truncated else None,
                command=command,
            )

        except subprocess.TimeoutExpired:
            return ShellResult(
                stdout="",
                stderr=f"Error: Command timed out after {self._timeout:.1f} seconds.",
                exit_code=-1,
                duration=self._timeout,
                truncated=False,
                command=command,
            )
        except Exception as e:
            return ShellResult(
                stdout="",
                stderr=f"Error executing command: {e}",
                exit_code=-1,
                duration=time.perf_counter() - start_time,
                truncated=False,
                command=command,
            )

    @property
    def security_validator(self) -> ShellSecurityValidator:
        """Get the security validator for configuration."""
        return self._security_validator

    @property
    def path_sandbox(self) -> PathSandbox:
        """Get the path sandbox for configuration."""
        return self._path_sandbox


__all__ = ["ShellMiddleware", "ShellResult", "SecurityLevel"]

