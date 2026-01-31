"""Tests for secure filesystem middleware."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ag3nt_agent.audit_logger import AuditLogger
from ag3nt_agent.file_security import FileSecurityValidator
from ag3nt_agent.secure_filesystem import SecureFilesystemMiddleware


class TestSecureFilesystemMiddleware:
    """Tests for SecureFilesystemMiddleware."""

    @pytest.fixture
    def temp_log_file(self):
        """Create a temporary log file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".log") as f:
            yield Path(f.name)
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def middleware(self, temp_log_file):
        """Create middleware with temp audit log."""
        return SecureFilesystemMiddleware(
            security_validator=FileSecurityValidator(),
            audit_logger=AuditLogger(log_file=temp_log_file),
            session_id="test-session",
        )

    def test_initialization(self, middleware):
        """Test middleware initialization."""
        assert middleware.security_validator is not None
        assert middleware.audit_logger is not None
        assert middleware.session_id == "test-session"

    def test_default_initialization(self):
        """Test middleware with defaults."""
        middleware = SecureFilesystemMiddleware()
        assert middleware.security_validator is not None
        assert middleware.audit_logger is not None
        assert middleware.session_id is None

    # Read validation tests
    def test_validate_and_log_read_allowed(self, middleware):
        """Test read validation for allowed file."""
        result = middleware.validate_and_log_read("/test/normal.txt", file_size=100)
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 1
        assert entries[0]["operation"] == "read"
        assert entries[0]["path"] == "/test/normal.txt"
        assert entries[0]["blocked"] is False

    def test_validate_and_log_read_blocked(self, middleware):
        """Test read validation for blocked file."""
        result = middleware.validate_and_log_read("/secrets/.env")
        assert result.is_safe is False

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 1
        assert entries[0]["blocked"] is True
        assert entries[0]["block_reason"] is not None

    # Write validation tests
    def test_validate_and_log_write_allowed(self, middleware):
        """Test write validation for allowed file."""
        result = middleware.validate_and_log_write("/test/output.txt", content_size=50)
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 1
        assert entries[0]["operation"] == "write"
        assert entries[0]["blocked"] is False

    def test_validate_and_log_write_blocked(self, middleware):
        """Test write validation for blocked file."""
        result = middleware.validate_and_log_write("secrets.json", content_size=100)
        assert result.is_safe is False

        entries = middleware.audit_logger.read_entries()
        assert entries[0]["blocked"] is True

    # Edit validation tests
    def test_validate_and_log_edit_allowed(self, middleware):
        """Test edit validation for allowed file."""
        result = middleware.validate_and_log_edit("/test/config.yaml")
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert entries[0]["operation"] == "edit"

    def test_validate_and_log_edit_blocked(self, middleware):
        """Test edit validation for blocked file."""
        result = middleware.validate_and_log_edit(".env.production")
        assert result.is_safe is False

    # Delete validation tests
    def test_validate_and_log_delete_allowed(self, middleware):
        """Test delete validation for allowed file."""
        result = middleware.validate_and_log_delete("/tmp/temp.txt")
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert entries[0]["operation"] == "delete"

    def test_validate_and_log_delete_blocked(self, middleware):
        """Test delete validation for blocked file."""
        result = middleware.validate_and_log_delete("private.pem")
        assert result.is_safe is False

    # List validation tests
    def test_validate_and_log_list_allowed(self, middleware):
        """Test list validation for allowed directory."""
        result = middleware.validate_and_log_list("/test/src/")
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert entries[0]["operation"] == "list"

    def test_validate_and_log_list_blocked(self, middleware):
        """Test list validation for blocked directory."""
        result = middleware.validate_and_log_list(".git/objects/")
        assert result.is_safe is False

    # Glob validation tests
    def test_validate_and_log_glob(self, middleware):
        """Test glob validation (always allowed)."""
        result = middleware.validate_and_log_glob("**/*.py")
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert entries[0]["operation"] == "glob"
        assert entries[0]["path"] == "**/*.py"

    # Grep validation tests
    def test_validate_and_log_grep_allowed(self, middleware):
        """Test grep validation for allowed path."""
        result = middleware.validate_and_log_grep("/test/src/", "TODO")
        assert result.is_safe is True

        entries = middleware.audit_logger.read_entries()
        assert entries[0]["operation"] == "grep"

    def test_validate_and_log_grep_blocked(self, middleware):
        """Test grep validation for blocked path."""
        result = middleware.validate_and_log_grep("secrets.json", "password")
        assert result.is_safe is False

    # Success/failure logging tests
    def test_log_operation_success(self, middleware):
        """Test logging a successful operation."""
        middleware.log_operation_success("read", "/test/file.txt", size=1024)

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 1
        assert entries[0]["success"] is True
        assert entries[0]["size"] == 1024

    def test_log_operation_failure(self, middleware):
        """Test logging a failed operation."""
        middleware.log_operation_failure("write", "/test/file.txt", "Permission denied")

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error"] == "Permission denied"

    # create_blocked_message tests
    def test_create_blocked_message(self):
        """Test creating a blocked ToolMessage."""
        from ag3nt_agent.file_security import FileValidationResult

        result = FileValidationResult.unsafe(
            reason="Access to sensitive file blocked",
            pattern=r"\.env",
        )
        message = SecureFilesystemMiddleware.create_blocked_message(
            result, tool_call_id="call-123"
        )
        assert message.tool_call_id == "call-123"
        assert "blocked" in message.content.lower()
        assert "sensitive file" in message.content.lower()

    # Session ID propagation tests
    def test_session_id_in_audit_entries(self, middleware):
        """Test that session ID is included in audit entries."""
        middleware.validate_and_log_read("/test/file.txt")
        middleware.validate_and_log_write("/test/out.txt")
        middleware.validate_and_log_delete("/test/temp.txt")

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 3
        for entry in entries:
            assert entry.get("session_id") == "test-session"

    # Integration test - full flow
    def test_full_validation_flow(self, middleware):
        """Test a complete validation flow with multiple operations."""
        # Allowed operations
        assert middleware.validate_and_log_read("/src/main.py").is_safe is True
        assert middleware.validate_and_log_write("/out/result.txt", 100).is_safe is True
        assert middleware.validate_and_log_list("/docs/").is_safe is True

        # Blocked operations
        assert middleware.validate_and_log_read(".env").is_safe is False
        assert middleware.validate_and_log_write("secrets.json").is_safe is False
        assert middleware.validate_and_log_list(".git/objects/").is_safe is False

        entries = middleware.audit_logger.read_entries()
        assert len(entries) == 6

        blocked_entries = [e for e in entries if e.get("blocked")]
        assert len(blocked_entries) == 3

