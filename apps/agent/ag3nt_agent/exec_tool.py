"""Full-featured shell execution tool for AG3NT.

Replaces basic execute/shell with support for:
- Foreground execution with output capture
- Background execution with session management
- PTY mode via pexpect (Unix) or subprocess fallback (Windows)
- Yield-to-background mode for long-running commands
- Security validation via ShellSecurityValidator
- Exec approval via ExecApprovalEvaluator

Usage:
    from ag3nt_agent.exec_tool import get_exec_tool

    tool = get_exec_tool()
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from ag3nt_agent.shell_security import ShellSecurityValidator, SecurityLevel

logger = logging.getLogger("ag3nt.exec")

# Output cap: 200KB max
MAX_OUTPUT_BYTES = 200 * 1024

# Default PTY dimensions
PTY_COLS = 120
PTY_ROWS = 30


@dataclass
class ExecSession:
    """Represents a running or finished background process session."""

    session_id: str
    command: str
    pid: int | None = None
    status: str = "running"  # running, finished, killed, error
    exit_code: int | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    output_buffer: str = ""
    _pending_offset: int = 0  # Track where last poll read up to
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _pexpect_child: Any = field(default=None, repr=False)
    _output_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _reader_thread: threading.Thread | None = field(default=None, repr=False)
    truncated: bool = False
    workdir: str | None = None
    use_pty: bool = False

    def append_output(self, data: str) -> None:
        """Append output data, respecting the output cap."""
        with self._output_lock:
            if len(self.output_buffer) >= MAX_OUTPUT_BYTES:
                self.truncated = True
                return
            remaining = MAX_OUTPUT_BYTES - len(self.output_buffer)
            if len(data) > remaining:
                self.output_buffer += data[:remaining]
                self.truncated = True
            else:
                self.output_buffer += data

    def get_pending_output(self) -> str:
        """Get output since last poll."""
        with self._output_lock:
            pending = self.output_buffer[self._pending_offset:]
            self._pending_offset = len(self.output_buffer)
            return pending

    def get_output_slice(self, offset: int = 0, limit: int | None = None) -> str:
        """Get line-based slice of output."""
        with self._output_lock:
            lines = self.output_buffer.split("\n")
            if limit is not None:
                sliced = lines[offset:offset + limit]
            else:
                sliced = lines[offset:]
            return "\n".join(sliced)

    def write_stdin(self, text: str) -> bool:
        """Write to process stdin."""
        if self._pexpect_child is not None:
            try:
                self._pexpect_child.send(text)
                return True
            except OSError:
                return False
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(text.encode())
                self._process.stdin.flush()
                return True
            except OSError:
                return False
        return False

    def send_keys(self, keys: str) -> bool:
        """Send named keys (mapped to escape sequences)."""
        key_map = {
            "Enter": "\n",
            "Tab": "\t",
            "Escape": "\x1b",
            "Ctrl-C": "\x03",
            "Ctrl-D": "\x04",
            "Ctrl-Z": "\x1a",
            "Ctrl-L": "\x0c",
            "Up": "\x1b[A",
            "Down": "\x1b[B",
            "Right": "\x1b[C",
            "Left": "\x1b[D",
            "Backspace": "\x7f",
            "Delete": "\x1b[3~",
        }
        seq = key_map.get(keys, keys)
        return self.write_stdin(seq)

    def kill(self) -> None:
        """Kill the process."""
        try:
            if self._pexpect_child is not None:
                import signal
                self._pexpect_child.kill(signal.SIGKILL)
            elif self._process:
                self._process.kill()
        except OSError:
            pass
        self.status = "killed"
        self.end_time = time.time()

    def clear_output(self) -> None:
        """Reset the output buffer."""
        with self._output_lock:
            self.output_buffer = ""
            self._pending_offset = 0
            self.truncated = False

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    def summary(self) -> dict[str, Any]:
        """Get a summary dict for listing."""
        return {
            "session_id": self.session_id,
            "command": self.command[:80] + ("..." if len(self.command) > 80 else ""),
            "status": self.status,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "duration": round(self.duration, 2),
            "output_bytes": len(self.output_buffer),
            "truncated": self.truncated,
        }


class ProcessRegistry:
    """Singleton registry for managing background process sessions."""

    _instance: ProcessRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._running: dict[str, ExecSession] = {}
        self._finished: dict[str, ExecSession] = {}
        self._registry_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ProcessRegistry:
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, session: ExecSession) -> None:
        """Register a new running session."""
        with self._registry_lock:
            self._running[session.session_id] = session

    def finish(self, session_id: str) -> None:
        """Move a session from running to finished."""
        with self._registry_lock:
            if session_id in self._running:
                session = self._running.pop(session_id)
                self._finished[session_id] = session

    def get(self, session_id: str) -> ExecSession | None:
        """Get a session by ID (running or finished).

        Also triggers auto-cleanup of stale finished sessions.
        """
        self._auto_cleanup()
        with self._registry_lock:
            return self._running.get(session_id) or self._finished.get(session_id)

    def _auto_cleanup(self) -> None:
        """Remove finished sessions older than PROCESS_MAX_AGE."""
        try:
            from ag3nt_agent.agent_config import PROCESS_MAX_AGE
            self.cleanup(max_age=PROCESS_MAX_AGE)
        except ImportError:
            self.cleanup()  # default 1 hour

    def remove(self, session_id: str) -> bool:
        """Remove a session from the registry."""
        with self._registry_lock:
            if session_id in self._running:
                del self._running[session_id]
                return True
            if session_id in self._finished:
                del self._finished[session_id]
                return True
            return False

    def list_all(self) -> list[dict[str, Any]]:
        """List all sessions (running + finished)."""
        with self._registry_lock:
            result = []
            for s in self._running.values():
                result.append(s.summary())
            for s in self._finished.values():
                result.append(s.summary())
            return result

    def cleanup(self, max_age: float = 3600.0) -> int:
        """Remove finished sessions older than max_age seconds."""
        now = time.time()
        removed = 0
        with self._registry_lock:
            to_remove = [
                sid for sid, s in self._finished.items()
                if s.end_time and (now - s.end_time) > max_age
            ]
            for sid in to_remove:
                del self._finished[sid]
                removed += 1
        return removed


def _get_workspace_dir() -> str:
    """Get the workspace directory for command execution."""
    user_data = Path.home() / ".ag3nt" / "workspace"
    user_data.mkdir(parents=True, exist_ok=True)
    return str(user_data)


def _run_foreground(
    command: str,
    workdir: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
    use_pty: bool = True,
) -> dict[str, Any]:
    """Run a command in the foreground and return results."""
    cwd = workdir or _get_workspace_dir()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    start = time.time()
    stdout_data = ""
    stderr_data = ""
    exit_code = -1
    truncated = False

    # Try PTY mode on Unix
    if use_pty and platform.system() != "Windows":
        try:
            import pexpect

            child = pexpect.spawn(
                "/bin/bash",
                ["-c", command],
                cwd=cwd,
                env=merged_env,
                timeout=timeout,
                encoding="utf-8",
                dimensions=(PTY_ROWS, PTY_COLS),
            )
            child.setecho(False)

            output_parts: list[str] = []
            total_bytes = 0
            try:
                while True:
                    try:
                        child.expect(r".+", timeout=timeout)
                        chunk = child.match.group(0)
                        if total_bytes + len(chunk) > MAX_OUTPUT_BYTES:
                            output_parts.append(chunk[: MAX_OUTPUT_BYTES - total_bytes])
                            truncated = True
                            break
                        output_parts.append(chunk)
                        total_bytes += len(chunk)
                    except pexpect.TIMEOUT:
                        child.kill(9)
                        output_parts.append("\n[TIMEOUT]")
                        break
            except pexpect.EOF:
                pass

            child.close()
            exit_code = child.exitstatus or 0
            stdout_data = "".join(output_parts)
            duration = time.time() - start

            return {
                "stdout": stdout_data,
                "stderr": "",
                "exit_code": exit_code,
                "duration": round(duration, 2),
                "truncated": truncated,
            }
        except ImportError:
            pass  # Fall through to subprocess

    # Subprocess fallback
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
        try:
            out_bytes, err_bytes = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out_bytes, err_bytes = proc.communicate()
            truncated = True

        stdout_data = out_bytes.decode("utf-8", errors="replace")
        stderr_data = err_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        if len(stdout_data) > MAX_OUTPUT_BYTES:
            stdout_data = stdout_data[:MAX_OUTPUT_BYTES]
            truncated = True
        if len(stderr_data) > MAX_OUTPUT_BYTES:
            stderr_data = stderr_data[:MAX_OUTPUT_BYTES]
            truncated = True

    except (OSError, subprocess.SubprocessError, ValueError) as e:
        stderr_data = f"Execution error: {e}"
        exit_code = -1

    duration = time.time() - start

    result = {
        "stdout": stdout_data,
        "stderr": stderr_data,
        "exit_code": exit_code,
        "duration": round(duration, 2),
        "truncated": truncated,
    }

    # Smart truncation: save large outputs to disk
    try:
        from ag3nt_agent.output_truncation import maybe_truncate

        if stdout_data:
            trunc_out, was_trunc, saved_path = maybe_truncate(stdout_data)
            if was_trunc:
                result["stdout"] = trunc_out
                result["truncated"] = True
                result["full_output_path"] = saved_path

        if stderr_data:
            trunc_err, was_trunc_err, saved_err = maybe_truncate(stderr_data)
            if was_trunc_err:
                result["stderr"] = trunc_err
                result["truncated"] = True
                if saved_err:
                    result["full_stderr_path"] = saved_err
    except ImportError:
        pass  # output_truncation not available

    return result


def _run_background(
    command: str,
    workdir: str | None = None,
    env: dict[str, str] | None = None,
    use_pty: bool = True,
) -> dict[str, Any]:
    """Start a command in the background and return session info."""
    cwd = workdir or _get_workspace_dir()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    session_id = str(uuid.uuid4())[:8]
    session = ExecSession(
        session_id=session_id,
        command=command,
        workdir=cwd,
        use_pty=use_pty,
    )

    registry = ProcessRegistry.get_instance()

    # Try PTY mode on Unix
    if use_pty and platform.system() != "Windows":
        try:
            import pexpect

            child = pexpect.spawn(
                "/bin/bash",
                ["-c", command],
                cwd=cwd,
                env=merged_env,
                encoding="utf-8",
                dimensions=(PTY_ROWS, PTY_COLS),
            )
            child.setecho(False)
            session._pexpect_child = child
            session.pid = child.pid

            def _reader() -> None:
                try:
                    while child.isalive():
                        try:
                            child.expect(r".+", timeout=1)
                            session.append_output(child.match.group(0))
                        except pexpect.TIMEOUT:
                            continue
                        except pexpect.EOF:
                            break
                except OSError:
                    pass
                finally:
                    child.close()
                    session.exit_code = child.exitstatus or 0
                    session.status = "finished"
                    session.end_time = time.time()
                    registry.finish(session_id)

            reader = threading.Thread(target=_reader, daemon=True)
            session._reader_thread = reader
            registry.register(session)
            reader.start()

            # Wait briefly for initial output
            time.sleep(0.3)

            return {
                "session_id": session_id,
                "status": "running",
                "pid": session.pid,
                "initial_output": session.get_pending_output(),
            }
        except ImportError:
            pass  # Fall through to subprocess

    # Subprocess fallback
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
        )
        session._process = proc
        session.pid = proc.pid

        def _reader() -> None:
            try:
                while True:
                    if proc.stdout is None:
                        break
                    line = proc.stdout.readline()
                    if not line:
                        break
                    session.append_output(line.decode("utf-8", errors="replace"))
            except OSError:
                pass
            finally:
                proc.wait()
                session.exit_code = proc.returncode
                session.status = "finished"
                session.end_time = time.time()
                registry.finish(session_id)

        reader = threading.Thread(target=_reader, daemon=True)
        session._reader_thread = reader
        registry.register(session)
        reader.start()

        # Wait briefly for initial output
        time.sleep(0.3)

    except (OSError, subprocess.SubprocessError, ValueError) as e:
        session.status = "error"
        session.append_output(f"Failed to start: {e}")
        session.end_time = time.time()
        registry.register(session)
        registry.finish(session_id)

    return {
        "session_id": session_id,
        "status": session.status,
        "pid": session.pid,
        "initial_output": session.get_pending_output(),
    }


@tool
def exec_command(
    command: str,
    workdir: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
    background: bool = False,
    pty: bool = True,
    yield_ms: int | None = None,
) -> dict[str, Any]:
    """Execute a shell command with full control over execution mode.

    Supports foreground execution (wait for completion), background execution
    (returns immediately with session_id for polling), and yield mode
    (runs synchronously for yield_ms then auto-backgrounds if still running).

    Args:
        command: The shell command to execute
        workdir: Working directory (default: ~/.ag3nt/workspace/)
        env: Additional environment variables to set
        timeout: Timeout in seconds for foreground mode (default: 120)
        background: If True, run in background and return session_id
        pty: If True, use PTY for terminal emulation (default: True)
        yield_ms: If set, run synchronously for this many ms then auto-background

    Returns:
        Foreground: {stdout, stderr, exit_code, duration, truncated}
        Background: {session_id, status, pid, initial_output}

    Examples:
        # Simple foreground command
        exec_command("ls -la")

        # Background a long-running process
        exec_command("npm run dev", background=True)

        # Yield mode: try for 5s, auto-background if still running
        exec_command("make build", yield_ms=5000)
    """
    if not command or not command.strip():
        return {"error": "Empty command", "exit_code": -1}

    # Security validation
    validator = ShellSecurityValidator(security_level=SecurityLevel.STANDARD)
    validation = validator.validate(command)
    if not validation.is_safe:
        return {
            "error": f"Command blocked: {validation.reason}",
            "severity": validation.severity,
            "exit_code": -1,
        }

    # Exec approval check
    try:
        from ag3nt_agent.exec_approval import ExecApprovalEvaluator
        evaluator = ExecApprovalEvaluator.get_instance()
        approval = evaluator.evaluate(command)
        if approval.decision == "deny":
            return {
                "error": f"Command denied: {approval.reason}",
                "matched_rule": approval.matched_rule,
                "exit_code": -1,
            }
        # If "ask", the HITL interrupt mechanism handles it via RISKY_TOOLS
    except ImportError:
        pass  # exec_approval not available yet

    logger.info(f"exec_command: command={command!r}, background={background}")

    # Yield mode: run sync for yield_ms, then auto-background
    if yield_ms is not None and not background:
        result = _run_foreground(
            command,
            workdir=workdir,
            env=env,
            timeout=yield_ms / 1000.0,
            use_pty=pty,
        )
        # If it timed out (truncated due to timeout), switch to background
        if result.get("truncated") and result.get("exit_code") != 0:
            logger.info(f"Yield timeout reached, switching to background: {command}")
            return _run_background(command, workdir=workdir, env=env, use_pty=pty)
        return result

    if background:
        return _run_background(command, workdir=workdir, env=env, use_pty=pty)

    return _run_foreground(
        command, workdir=workdir, env=env, timeout=timeout, use_pty=pty
    )


def get_exec_tool():
    """Get the exec_command tool for the agent.

    Returns:
        LangChain tool for shell execution
    """
    return exec_command
