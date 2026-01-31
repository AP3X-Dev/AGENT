"""Audit logging for file and shell operations in AG3NT.

This module provides structured audit logging for security-sensitive operations:
- File operations (read, write, edit, delete, list, glob, grep)
- Shell command executions
- Security validation events

Logs are written in JSON Lines format for easy parsing and analysis.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger("ag3nt.audit")


def _get_default_log_path() -> Path:
    """Get the default audit log path."""
    return Path.home() / ".ag3nt" / "audit.log"


@dataclass(frozen=True)
class FileAuditEntry:
    """Audit entry for file operations."""

    timestamp: str
    type: Literal["file"] = "file"
    operation: Literal["read", "write", "edit", "delete", "list", "glob", "grep"] = "read"
    path: str = ""
    size: int | None = None
    success: bool = True
    error: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    blocked: bool = False
    block_reason: str | None = None


@dataclass(frozen=True)
class ShellAuditEntry:
    """Audit entry for shell operations."""

    timestamp: str
    type: Literal["shell"] = "shell"
    command: str = ""
    exit_code: int | None = None
    duration_ms: float | None = None
    success: bool = True
    error: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    blocked: bool = False
    block_reason: str | None = None


@dataclass
class AuditLogger:
    """Logs all file and shell operations for audit trail.

    Thread-safe logger that writes entries in JSON Lines format.
    """

    log_file: Path = field(default_factory=_get_default_log_path)
    enabled: bool = True
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        """Ensure log directory exists."""
        if self.enabled:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_file_operation(
        self,
        operation: Literal["read", "write", "edit", "delete", "list", "glob", "grep"],
        path: str,
        *,
        size: int | None = None,
        success: bool = True,
        error: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        blocked: bool = False,
        block_reason: str | None = None,
    ) -> FileAuditEntry:
        """Log a file operation.

        Args:
            operation: Type of file operation.
            path: File path being operated on.
            size: Size of file/content in bytes.
            success: Whether the operation succeeded.
            error: Error message if operation failed.
            session_id: Session identifier for traceability.
            user_id: User identifier for traceability.
            blocked: Whether the operation was blocked by security.
            block_reason: Reason for blocking.

        Returns:
            The created audit entry.
        """
        entry = FileAuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation=operation,
            path=path,
            size=size,
            success=success,
            error=error,
            session_id=session_id,
            user_id=user_id,
            blocked=blocked,
            block_reason=block_reason,
        )
        self._write_entry(entry)
        return entry

    def log_shell_operation(
        self,
        command: str,
        *,
        exit_code: int | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        error: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        blocked: bool = False,
        block_reason: str | None = None,
    ) -> ShellAuditEntry:
        """Log a shell operation.

        Args:
            command: Shell command executed.
            exit_code: Command exit code.
            duration_ms: Execution duration in milliseconds.
            success: Whether the operation succeeded.
            error: Error message if operation failed.
            session_id: Session identifier for traceability.
            user_id: User identifier for traceability.
            blocked: Whether the operation was blocked by security.
            block_reason: Reason for blocking.

        Returns:
            The created audit entry.
        """
        entry = ShellAuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            command=command,
            exit_code=exit_code,
            duration_ms=duration_ms,
            success=success,
            error=error,
            session_id=session_id,
            user_id=user_id,
            blocked=blocked,
            block_reason=block_reason,
        )
        self._write_entry(entry)
        return entry

    def _write_entry(self, entry: FileAuditEntry | ShellAuditEntry) -> None:
        """Write an audit entry to the log file.

        Thread-safe write operation.

        Args:
            entry: The audit entry to write.
        """
        if not self.enabled:
            return

        entry_dict = asdict(entry)
        # Remove None values for cleaner logs
        entry_dict = {k: v for k, v in entry_dict.items() if v is not None}

        try:
            with self._lock:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry_dict) + "\n")

            # Also log to Python logger for real-time monitoring
            log_msg = f"Audit: {entry.type} "
            if isinstance(entry, FileAuditEntry):
                log_msg += f"{entry.operation} {entry.path}"
            else:
                # Truncate command for logging
                cmd_preview = entry.command[:50] + "..." if len(entry.command) > 50 else entry.command
                log_msg += f"command: {cmd_preview}"

            if entry.blocked:
                logger.warning(f"{log_msg} [BLOCKED: {entry.block_reason}]")
            elif not entry.success:
                logger.warning(f"{log_msg} [FAILED: {entry.error}]")
            else:
                logger.debug(log_msg)

        except OSError as e:
            logger.error(f"Failed to write audit log: {e}")

    def read_entries(
        self,
        *,
        entry_type: Literal["file", "shell", "all"] = "all",
        limit: int | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        """Read audit entries from the log file.

        Args:
            entry_type: Filter by entry type.
            limit: Maximum number of entries to return (most recent first).
            session_id: Filter by session ID.

        Returns:
            List of audit entries as dictionaries.
        """
        if not self.log_file.exists():
            return []

        entries = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Apply filters
                        if entry_type != "all" and entry.get("type") != entry_type:
                            continue
                        if session_id and entry.get("session_id") != session_id:
                            continue
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue

            # Return most recent entries first
            entries.reverse()
            if limit:
                entries = entries[:limit]

        except OSError as e:
            logger.error(f"Failed to read audit log: {e}")

        return entries

    def clear(self) -> bool:
        """Clear the audit log file.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._lock:
                if self.log_file.exists():
                    self.log_file.unlink()
            return True
        except OSError as e:
            logger.error(f"Failed to clear audit log: {e}")
            return False

    def get_stats(self) -> dict:
        """Get statistics about the audit log.

        Returns:
            Dictionary with log statistics.
        """
        entries = self.read_entries()

        file_ops = [e for e in entries if e.get("type") == "file"]
        shell_ops = [e for e in entries if e.get("type") == "shell"]

        return {
            "total_entries": len(entries),
            "file_operations": len(file_ops),
            "shell_operations": len(shell_ops),
            "blocked_operations": sum(1 for e in entries if e.get("blocked")),
            "failed_operations": sum(1 for e in entries if not e.get("success", True)),
            "log_file": str(self.log_file),
            "log_size_bytes": self.log_file.stat().st_size if self.log_file.exists() else 0,
        }


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger

