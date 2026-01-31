"""File operation security validation for AG3NT.

This module provides security validation for file operations including:
- Sensitive file pattern detection (.env, *.pem, secrets.json, etc.)
- Size limits for read/write operations
- Blocked directory detection (.git/objects, node_modules/.bin, etc.)

Security Note:
This is a defense-in-depth layer. HITL approval remains the primary safety mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# Maximum file sizes (in bytes)
MAX_READ_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_WRITE_SIZE = 5 * 1024 * 1024  # 5 MB

# Sensitive file patterns that should be blocked
BLOCKED_FILE_PATTERNS: list[tuple[str, str]] = [
    # Environment and secrets files
    (r"\.env$", "Environment file with potential secrets"),
    (r"\.env\.[a-zA-Z0-9_]+$", "Environment file variant"),
    (r"secrets?\.(json|yaml|yml|toml)$", "Secrets configuration file"),
    (r"credentials?\.(json|yaml|yml|toml)$", "Credentials file"),
    # Private keys and certificates
    (r"\.pem$", "PEM certificate/key file"),
    (r"\.key$", "Private key file"),
    (r"\.p12$", "PKCS#12 certificate file"),
    (r"\.pfx$", "PFX certificate file"),
    (r"id_rsa", "SSH private key"),
    (r"id_ed25519", "SSH private key (Ed25519)"),
    (r"id_ecdsa", "SSH private key (ECDSA)"),
    (r"id_dsa", "SSH private key (DSA)"),
    # AWS and cloud credentials
    (r"\.aws/credentials$", "AWS credentials file"),
    (r"\.aws/config$", "AWS config file"),
    (r"gcloud.*\.json$", "Google Cloud credentials"),
    (r"service[-_]?account.*\.json$", "Service account credentials"),
    # Token and auth files
    (r"\.npmrc$", "NPM config with potential tokens"),
    (r"\.pypirc$", "PyPI config with potential tokens"),
    (r"\.netrc$", "Network credentials file"),
    (r"\.docker/config\.json$", "Docker config with potential tokens"),
    # Database files
    (r"\.sqlite3?$", "SQLite database file"),
    (r"\.db$", "Database file"),
]

# Blocked directory patterns
BLOCKED_DIRECTORIES: list[tuple[str, str]] = [
    # Git internals
    (r"\.git/objects", "Git object storage"),
    (r"\.git/hooks", "Git hooks directory"),
    (r"\.git/refs", "Git references"),
    # Package manager internals
    (r"node_modules/\.bin", "Node.js binary directory"),
    (r"node_modules/\.cache", "Node.js cache directory"),
    (r"__pycache__", "Python bytecode cache"),
    (r"\.pytest_cache", "Pytest cache"),
    (r"\.mypy_cache", "Mypy cache"),
    # Virtual environments
    (r"\.venv/", "Python virtual environment"),
    (r"venv/", "Python virtual environment"),
    (r"\.virtualenv/", "Python virtual environment"),
    # Build artifacts
    (r"dist/", "Distribution directory"),
    (r"build/", "Build directory"),
    (r"\.next/", "Next.js build directory"),
    # IDE and editor
    (r"\.idea/", "IntelliJ IDEA directory"),
    (r"\.vscode/", "VS Code directory"),
]


@dataclass(frozen=True)
class FileValidationResult:
    """Result of file security validation."""

    is_safe: bool
    reason: str = ""
    matched_pattern: str | None = None
    severity: Literal["info", "warning", "critical"] = "info"

    @classmethod
    def safe(cls) -> "FileValidationResult":
        """Create a safe validation result."""
        return cls(is_safe=True)

    @classmethod
    def unsafe(
        cls,
        reason: str,
        pattern: str | None = None,
        severity: Literal["info", "warning", "critical"] = "critical",
    ) -> "FileValidationResult":
        """Create an unsafe validation result."""
        return cls(
            is_safe=False,
            reason=reason,
            matched_pattern=pattern,
            severity=severity,
        )


@dataclass
class FileSecurityValidator:
    """Validates file operations for security compliance.

    Checks file paths against blocked patterns and enforces size limits.
    """

    max_read_size: int = MAX_READ_SIZE
    max_write_size: int = MAX_WRITE_SIZE
    blocked_file_patterns: list[tuple[str, str]] = field(default_factory=list)
    blocked_directories: list[tuple[str, str]] = field(default_factory=list)
    allowed_extensions: list[str] = field(default_factory=list)
    _compiled_file_patterns: list[tuple[re.Pattern, str]] = field(
        default_factory=list, repr=False
    )
    _compiled_dir_patterns: list[tuple[re.Pattern, str]] = field(
        default_factory=list, repr=False
    )

    def __post_init__(self) -> None:
        """Compile regex patterns for efficient matching."""
        # Use defaults if not provided
        if not self.blocked_file_patterns:
            self.blocked_file_patterns = list(BLOCKED_FILE_PATTERNS)
        if not self.blocked_directories:
            self.blocked_directories = list(BLOCKED_DIRECTORIES)

        # Compile file patterns
        self._compiled_file_patterns = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.blocked_file_patterns
        ]

        # Compile directory patterns
        self._compiled_dir_patterns = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.blocked_directories
        ]

    def validate_read(
        self, path: str, file_size: int | None = None
    ) -> FileValidationResult:
        """Validate a file read operation.

        Args:
            path: The file path to validate.
            file_size: Optional file size in bytes.

        Returns:
            FileValidationResult indicating if the read is safe.
        """
        # Check if path is blocked
        blocked_result = self._check_blocked_path(path)
        if not blocked_result.is_safe:
            return blocked_result

        # Check file size if provided
        if file_size is not None and file_size > self.max_read_size:
            return FileValidationResult.unsafe(
                f"File too large: {file_size:,} bytes (max: {self.max_read_size:,})",
                severity="warning",
            )

        return FileValidationResult.safe()

    def validate_write(
        self, path: str, content_size: int | None = None
    ) -> FileValidationResult:
        """Validate a file write operation.

        Args:
            path: The file path to validate.
            content_size: Optional content size in bytes.

        Returns:
            FileValidationResult indicating if the write is safe.
        """
        # Check if path is blocked
        blocked_result = self._check_blocked_path(path)
        if not blocked_result.is_safe:
            return blocked_result

        # Check content size if provided
        if content_size is not None and content_size > self.max_write_size:
            return FileValidationResult.unsafe(
                f"Content too large: {content_size:,} bytes (max: {self.max_write_size:,})",
                severity="warning",
            )

        return FileValidationResult.safe()

    def validate_delete(self, path: str) -> FileValidationResult:
        """Validate a file delete operation.

        Args:
            path: The file path to validate.

        Returns:
            FileValidationResult indicating if the delete is safe.
        """
        # Check if path is blocked (we don't want to delete sensitive files either)
        blocked_result = self._check_blocked_path(path)
        if not blocked_result.is_safe:
            return blocked_result

        return FileValidationResult.safe()

    def validate_list(self, path: str) -> FileValidationResult:
        """Validate a directory listing operation.

        Args:
            path: The directory path to validate.

        Returns:
            FileValidationResult indicating if the listing is safe.
        """
        # Check if directory is blocked
        for pattern, reason in self._compiled_dir_patterns:
            if pattern.search(path):
                return FileValidationResult.unsafe(
                    f"Access to blocked directory: {reason}",
                    pattern=pattern.pattern,
                    severity="warning",
                )

        return FileValidationResult.safe()

    def _check_blocked_path(self, path: str) -> FileValidationResult:
        """Check if a path matches any blocked pattern.

        Args:
            path: The file path to check.

        Returns:
            FileValidationResult indicating if the path is blocked.
        """
        # Normalize path for consistent matching
        normalized = path.replace("\\", "/")

        # Check blocked file patterns
        for pattern, reason in self._compiled_file_patterns:
            if pattern.search(normalized):
                return FileValidationResult.unsafe(
                    f"Access to sensitive file blocked: {reason}",
                    pattern=pattern.pattern,
                    severity="critical",
                )

        # Check blocked directory patterns
        for pattern, reason in self._compiled_dir_patterns:
            if pattern.search(normalized):
                return FileValidationResult.unsafe(
                    f"Access to blocked directory: {reason}",
                    pattern=pattern.pattern,
                    severity="warning",
                )

        return FileValidationResult.safe()

    def add_blocked_pattern(self, pattern: str, reason: str) -> None:
        """Add a custom blocked file pattern.

        Args:
            pattern: Regex pattern to block.
            reason: Human-readable reason for blocking.
        """
        self.blocked_file_patterns.append((pattern, reason))
        self._compiled_file_patterns.append(
            (re.compile(pattern, re.IGNORECASE), reason)
        )

    def add_allowed_extension(self, extension: str) -> None:
        """Add an allowed file extension (for future allowlist mode).

        Args:
            extension: File extension to allow (e.g., ".py", ".txt").
        """
        if not extension.startswith("."):
            extension = f".{extension}"
        if extension not in self.allowed_extensions:
            self.allowed_extensions.append(extension)

    def is_extension_allowed(self, path: str) -> bool:
        """Check if a file's extension is in the allowed list.

        Args:
            path: The file path to check.

        Returns:
            True if extension is allowed or no allowlist is set.
        """
        if not self.allowed_extensions:
            return True  # No allowlist means all extensions allowed

        path_obj = Path(path)
        return path_obj.suffix.lower() in [ext.lower() for ext in self.allowed_extensions]

