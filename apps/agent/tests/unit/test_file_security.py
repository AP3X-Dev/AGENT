"""Tests for file security validation module."""

import pytest

from ag3nt_agent.file_security import (
    BLOCKED_DIRECTORIES,
    BLOCKED_FILE_PATTERNS,
    MAX_READ_SIZE,
    MAX_WRITE_SIZE,
    FileSecurityValidator,
    FileValidationResult,
)


class TestFileValidationResult:
    """Tests for FileValidationResult dataclass."""

    def test_safe_factory(self):
        """Test creating a safe validation result."""
        result = FileValidationResult.safe()
        assert result.is_safe is True
        assert result.reason == ""
        assert result.matched_pattern is None
        assert result.severity == "info"

    def test_unsafe_factory(self):
        """Test creating an unsafe validation result."""
        result = FileValidationResult.unsafe(
            reason="Sensitive file blocked",
            pattern=r"\.env$",
            severity="critical",
        )
        assert result.is_safe is False
        assert result.reason == "Sensitive file blocked"
        assert result.matched_pattern == r"\.env$"
        assert result.severity == "critical"

    def test_immutable(self):
        """Test that FileValidationResult is immutable."""
        result = FileValidationResult.safe()
        with pytest.raises(Exception):  # FrozenInstanceError
            result.is_safe = False


class TestFileSecurityValidator:
    """Tests for FileSecurityValidator."""

    def test_default_initialization(self):
        """Test validator initializes with default patterns."""
        validator = FileSecurityValidator()
        assert len(validator.blocked_file_patterns) > 0
        assert len(validator.blocked_directories) > 0
        assert validator.max_read_size == MAX_READ_SIZE
        assert validator.max_write_size == MAX_WRITE_SIZE

    def test_custom_size_limits(self):
        """Test validator with custom size limits."""
        validator = FileSecurityValidator(
            max_read_size=1024,
            max_write_size=512,
        )
        assert validator.max_read_size == 1024
        assert validator.max_write_size == 512

    # Read validation tests
    @pytest.mark.parametrize("path", [
        ".env",
        "/path/to/.env",
        "config/.env.production",
        "secrets.json",
        "/app/secrets.yaml",
        "credentials.toml",
        "private.pem",
        "server.key",
        "id_rsa",
        "id_ed25519",
        ".aws/credentials",
    ])
    def test_blocks_sensitive_files_read(self, path):
        """Test that sensitive files are blocked for reading."""
        validator = FileSecurityValidator()
        result = validator.validate_read(path)
        assert result.is_safe is False, f"Should block read of: {path}"
        assert result.severity == "critical"

    @pytest.mark.parametrize("path", [
        "README.md",
        "src/main.py",
        "package.json",
        "config/settings.yaml",
        "docs/guide.txt",
        "tests/test_app.py",
    ])
    def test_allows_normal_files_read(self, path):
        """Test that normal files are allowed for reading."""
        validator = FileSecurityValidator()
        result = validator.validate_read(path)
        assert result.is_safe is True, f"Should allow read of: {path}"

    def test_blocks_large_files_read(self):
        """Test that files exceeding size limit are blocked."""
        validator = FileSecurityValidator(max_read_size=1024)
        result = validator.validate_read("large_file.txt", file_size=2048)
        assert result.is_safe is False
        assert "too large" in result.reason.lower()

    def test_allows_small_files_read(self):
        """Test that files within size limit are allowed."""
        validator = FileSecurityValidator(max_read_size=1024)
        result = validator.validate_read("small_file.txt", file_size=512)
        assert result.is_safe is True

    # Write validation tests
    @pytest.mark.parametrize("path", [
        ".env",
        "secrets.json",
        "private.key",
        "id_rsa",
    ])
    def test_blocks_sensitive_files_write(self, path):
        """Test that sensitive files are blocked for writing."""
        validator = FileSecurityValidator()
        result = validator.validate_write(path)
        assert result.is_safe is False, f"Should block write to: {path}"

    def test_blocks_large_content_write(self):
        """Test that content exceeding size limit is blocked."""
        validator = FileSecurityValidator(max_write_size=1024)
        result = validator.validate_write("output.txt", content_size=2048)
        assert result.is_safe is False
        assert "too large" in result.reason.lower()

    def test_allows_normal_files_write(self):
        """Test that normal files are allowed for writing."""
        validator = FileSecurityValidator()
        result = validator.validate_write("output.txt", content_size=100)
        assert result.is_safe is True

    # Directory validation tests
    @pytest.mark.parametrize("path", [
        ".git/objects/pack",
        ".git/hooks/pre-commit",
        "node_modules/.bin/eslint",
        "__pycache__/module.pyc",
        ".venv/lib/python3.12",
    ])
    def test_blocks_sensitive_directories(self, path):
        """Test that sensitive directories are blocked."""
        validator = FileSecurityValidator()
        result = validator.validate_list(path)
        assert result.is_safe is False, f"Should block access to: {path}"

    @pytest.mark.parametrize("path", [
        "src/",
        "tests/",
        "docs/",
        "config/",
    ])
    def test_allows_normal_directories(self, path):
        """Test that normal directories are allowed."""
        validator = FileSecurityValidator()
        result = validator.validate_list(path)
        assert result.is_safe is True, f"Should allow access to: {path}"

    # Delete validation tests
    def test_blocks_sensitive_files_delete(self):
        """Test that sensitive files are blocked for deletion."""
        validator = FileSecurityValidator()
        result = validator.validate_delete(".env")
        assert result.is_safe is False

    def test_allows_normal_files_delete(self):
        """Test that normal files are allowed for deletion."""
        validator = FileSecurityValidator()
        result = validator.validate_delete("temp_file.txt")
        assert result.is_safe is True

    # Custom pattern tests
    def test_add_blocked_pattern(self):
        """Test adding a custom blocked pattern."""
        validator = FileSecurityValidator()
        initial_count = len(validator.blocked_file_patterns)

        validator.add_blocked_pattern(r"\.custom$", "Custom file type")

        assert len(validator.blocked_file_patterns) == initial_count + 1
        result = validator.validate_read("config.custom")
        assert result.is_safe is False
        assert "custom file type" in result.reason.lower()

    # Extension allowlist tests
    def test_add_allowed_extension_with_dot(self):
        """Test adding extension with dot prefix."""
        validator = FileSecurityValidator()
        validator.add_allowed_extension(".py")
        assert ".py" in validator.allowed_extensions

    def test_add_allowed_extension_without_dot(self):
        """Test adding extension without dot prefix."""
        validator = FileSecurityValidator()
        validator.add_allowed_extension("txt")
        assert ".txt" in validator.allowed_extensions

    def test_add_allowed_extension_no_duplicates(self):
        """Test that duplicate extensions are not added."""
        validator = FileSecurityValidator()
        validator.add_allowed_extension(".py")
        validator.add_allowed_extension(".py")
        assert validator.allowed_extensions.count(".py") == 1

    def test_is_extension_allowed_no_allowlist(self):
        """Test extension check when no allowlist is set."""
        validator = FileSecurityValidator()
        assert validator.is_extension_allowed("file.any") is True

    def test_is_extension_allowed_in_list(self):
        """Test extension check when extension is allowed."""
        validator = FileSecurityValidator()
        validator.add_allowed_extension(".py")
        validator.add_allowed_extension(".txt")
        assert validator.is_extension_allowed("script.py") is True
        assert validator.is_extension_allowed("notes.txt") is True

    def test_is_extension_allowed_not_in_list(self):
        """Test extension check when extension is not allowed."""
        validator = FileSecurityValidator()
        validator.add_allowed_extension(".py")
        assert validator.is_extension_allowed("config.yaml") is False

    def test_is_extension_allowed_case_insensitive(self):
        """Test extension check is case insensitive."""
        validator = FileSecurityValidator()
        validator.add_allowed_extension(".PY")
        assert validator.is_extension_allowed("script.py") is True
        assert validator.is_extension_allowed("SCRIPT.PY") is True

    # Path normalization tests
    def test_normalizes_windows_paths(self):
        """Test that Windows paths are normalized for matching."""
        validator = FileSecurityValidator()
        result = validator.validate_read("C:\\Users\\user\\.env")
        assert result.is_safe is False

    def test_read_without_file_size(self):
        """Test read validation without file size."""
        validator = FileSecurityValidator()
        result = validator.validate_read("normal_file.txt")
        assert result.is_safe is True

    def test_write_without_content_size(self):
        """Test write validation without content size."""
        validator = FileSecurityValidator()
        result = validator.validate_write("output.txt")
        assert result.is_safe is True

