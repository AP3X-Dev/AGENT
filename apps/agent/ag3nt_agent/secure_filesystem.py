"""Secure filesystem middleware wrapper for AG3NT.

This module provides a security layer on top of DeepAgents FilesystemMiddleware:
- Validates file operations against security rules before execution
- Logs all file operations for audit trail
- Blocks access to sensitive files and directories

Usage:
    from ag3nt_agent.secure_filesystem import SecureFilesystemMiddleware

    middleware = SecureFilesystemMiddleware(
        backend=backend,
        security_validator=FileSecurityValidator(),
        audit_logger=AuditLogger(),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from langchain_core.messages import ToolMessage

from ag3nt_agent.audit_logger import AuditLogger, get_audit_logger
from ag3nt_agent.file_security import FileSecurityValidator, FileValidationResult

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol


@dataclass
class SecureFilesystemMiddleware:
    """Middleware that wraps file operations with security validation and audit logging.

    This middleware intercepts file tool calls and:
    1. Validates the operation against security rules
    2. Blocks operations that violate security policies
    3. Logs all operations (successful and blocked) for audit

    Attributes:
        security_validator: Validator for file security rules.
        audit_logger: Logger for audit trail.
        session_id: Optional session ID for audit entries.
    """

    security_validator: FileSecurityValidator = field(
        default_factory=FileSecurityValidator
    )
    audit_logger: AuditLogger = field(default_factory=get_audit_logger)
    session_id: str | None = None

    def validate_and_log_read(
        self,
        path: str,
        file_size: int | None = None,
    ) -> FileValidationResult:
        """Validate and log a file read operation.

        Args:
            path: File path to read.
            file_size: Size of the file in bytes.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        result = self.security_validator.validate_read(path, file_size)

        self.audit_logger.log_file_operation(
            operation="read",
            path=path,
            size=file_size,
            success=result.is_safe,
            blocked=not result.is_safe,
            block_reason=result.reason if not result.is_safe else None,
            session_id=self.session_id,
        )

        return result

    def validate_and_log_write(
        self,
        path: str,
        content_size: int | None = None,
    ) -> FileValidationResult:
        """Validate and log a file write operation.

        Args:
            path: File path to write.
            content_size: Size of the content in bytes.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        result = self.security_validator.validate_write(path, content_size)

        self.audit_logger.log_file_operation(
            operation="write",
            path=path,
            size=content_size,
            success=result.is_safe,
            blocked=not result.is_safe,
            block_reason=result.reason if not result.is_safe else None,
            session_id=self.session_id,
        )

        return result

    def validate_and_log_edit(
        self,
        path: str,
    ) -> FileValidationResult:
        """Validate and log a file edit operation.

        Args:
            path: File path to edit.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        result = self.security_validator.validate_write(path)

        self.audit_logger.log_file_operation(
            operation="edit",
            path=path,
            success=result.is_safe,
            blocked=not result.is_safe,
            block_reason=result.reason if not result.is_safe else None,
            session_id=self.session_id,
        )

        return result

    def validate_and_log_delete(
        self,
        path: str,
    ) -> FileValidationResult:
        """Validate and log a file delete operation.

        Args:
            path: File path to delete.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        result = self.security_validator.validate_delete(path)

        self.audit_logger.log_file_operation(
            operation="delete",
            path=path,
            success=result.is_safe,
            blocked=not result.is_safe,
            block_reason=result.reason if not result.is_safe else None,
            session_id=self.session_id,
        )

        return result

    def validate_and_log_list(
        self,
        path: str,
    ) -> FileValidationResult:
        """Validate and log a directory list operation.

        Args:
            path: Directory path to list.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        result = self.security_validator.validate_list(path)

        self.audit_logger.log_file_operation(
            operation="list",
            path=path,
            success=result.is_safe,
            blocked=not result.is_safe,
            block_reason=result.reason if not result.is_safe else None,
            session_id=self.session_id,
        )

        return result

    def validate_and_log_glob(
        self,
        pattern: str,
    ) -> FileValidationResult:
        """Validate and log a glob operation.

        Args:
            pattern: Glob pattern to match.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        # Glob patterns are generally safe, but log them
        result = FileValidationResult.safe()

        self.audit_logger.log_file_operation(
            operation="glob",
            path=pattern,
            success=True,
            session_id=self.session_id,
        )

        return result

    def validate_and_log_grep(
        self,
        path: str,
        pattern: str,
    ) -> FileValidationResult:
        """Validate and log a grep operation.

        Args:
            path: File or directory path to search.
            pattern: Search pattern.

        Returns:
            Validation result indicating if the operation is allowed.
        """
        result = self.security_validator.validate_read(path)

        self.audit_logger.log_file_operation(
            operation="grep",
            path=path,
            success=result.is_safe,
            blocked=not result.is_safe,
            block_reason=result.reason if not result.is_safe else None,
            session_id=self.session_id,
        )

        return result

    def log_operation_success(
        self,
        operation: str,
        path: str,
        size: int | None = None,
    ) -> None:
        """Log a successful file operation (after execution).

        Args:
            operation: Type of operation.
            path: File path.
            size: Size of file/content.
        """
        self.audit_logger.log_file_operation(
            operation=operation,  # type: ignore
            path=path,
            size=size,
            success=True,
            session_id=self.session_id,
        )

    def log_operation_failure(
        self,
        operation: str,
        path: str,
        error: str,
    ) -> None:
        """Log a failed file operation.

        Args:
            operation: Type of operation.
            path: File path.
            error: Error message.
        """
        self.audit_logger.log_file_operation(
            operation=operation,  # type: ignore
            path=path,
            success=False,
            error=error,
            session_id=self.session_id,
        )

    @staticmethod
    def create_blocked_message(
        result: FileValidationResult,
        tool_call_id: str,
    ) -> ToolMessage:
        """Create a ToolMessage for a blocked operation.

        Args:
            result: The validation result.
            tool_call_id: The tool call ID.

        Returns:
            ToolMessage indicating the operation was blocked.
        """
        return ToolMessage(
            content=f"Security blocked: {result.reason}",
            tool_call_id=tool_call_id,
        )

