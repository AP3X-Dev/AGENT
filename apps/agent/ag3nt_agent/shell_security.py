"""Shell security validation for AG3NT.

This module provides security validation for shell commands including:
- Dangerous pattern detection (rm -rf, fork bombs, etc.)
- Allowlist mode for restricted environments
- Path sandboxing to restrict file system access

Security Note:
This is a defense-in-depth layer. HITL approval remains the primary safety mechanism.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal


class SecurityLevel(Enum):
    """Security validation strictness levels."""

    PERMISSIVE = "permissive"  # Only block obviously dangerous commands
    STANDARD = "standard"  # Block dangerous + suspicious commands
    STRICT = "strict"  # Allowlist mode - only allow explicitly permitted commands


@dataclass(frozen=True)
class ValidationResult:
    """Result of security validation."""

    is_safe: bool
    reason: str = ""
    matched_pattern: str | None = None
    severity: Literal["info", "warning", "critical"] = "info"

    @classmethod
    def safe(cls) -> "ValidationResult":
        """Create a safe validation result."""
        return cls(is_safe=True)

    @classmethod
    def unsafe(
        cls,
        reason: str,
        pattern: str | None = None,
        severity: Literal["info", "warning", "critical"] = "critical",
    ) -> "ValidationResult":
        """Create an unsafe validation result."""
        return cls(
            is_safe=False,
            reason=reason,
            matched_pattern=pattern,
            severity=severity,
        )


# Dangerous command patterns - these are blocked in all modes
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Destructive file operations
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(-[a-zA-Z]*f[a-zA-Z]*\s+)?[/~]", "Destructive rm command targeting root or home"),
    (r"\brm\s+-[a-zA-Z]*rf", "Recursive force delete"),
    (r"\bmkfs\b", "Filesystem format command"),
    (r"\bdd\s+.*if=/dev/(zero|random|urandom)", "Disk overwrite with dd"),
    (r">\s*/dev/[sh]d[a-z]", "Direct disk write"),
    # Fork bombs and resource exhaustion
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;:", "Fork bomb detected"),
    (r"\bwhile\s+true\s*;\s*do", "Infinite loop pattern"),
    # Privilege escalation
    (r"\bsudo\s+", "Sudo command (requires explicit approval)"),
    (r"\bsu\s+-", "Switch user command"),
    (r"\bchmod\s+777\s+/", "Dangerous chmod on root"),
    (r"\bchown\s+.*\s+/", "Chown on root directory"),
    # Remote code execution
    (r"\bcurl\s+.*\|\s*(ba)?sh", "Piped curl to shell"),
    (r"\bwget\s+.*\|\s*(ba)?sh", "Piped wget to shell"),
    (r"\bcurl\s+.*\|\s*python", "Piped curl to python"),
    # Sensitive file access
    (r"/etc/shadow", "Access to shadow file"),
    (r"/etc/sudoers", "Access to sudoers file"),
    (r"~?/\.ssh/id_", "Access to SSH private keys"),
    # Environment manipulation
    (r"\bexport\s+PATH=", "PATH manipulation"),
    (r"\bexport\s+LD_PRELOAD", "LD_PRELOAD injection"),
    # Network attacks
    (r"\bnc\s+-[a-zA-Z]*l", "Netcat listener"),
    (r"\bnmap\b", "Network scanning"),
]

# Suspicious patterns - blocked in STANDARD and STRICT modes
SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
    (r"\beval\s+", "Eval command"),
    (r"\bexec\s+", "Exec command"),
    (r"\bsource\s+/dev/", "Sourcing from device"),
    (r"\bkill\s+-9\s+-1", "Kill all processes"),
    (r"\bpkill\s+-9", "Force kill processes"),
    (r"\bshutdown\b", "Shutdown command"),
    (r"\breboot\b", "Reboot command"),
    (r"\bhalt\b", "Halt command"),
    (r"\bpoweroff\b", "Poweroff command"),
    (r"\biptables\b", "Firewall manipulation"),
    (r"\bsystemctl\s+(stop|disable)", "Stopping system services"),
    (r">\s*/dev/null\s+2>&1\s*&", "Background with suppressed output"),
    (r"\bhistory\s+-c", "Clearing command history"),
]


@dataclass
class ShellSecurityValidator:
    """Validates shell commands for security risks.

    This validator checks commands against known dangerous patterns
    and can operate in different security levels.
    """

    security_level: SecurityLevel = SecurityLevel.STANDARD
    allowed_commands: list[str] = field(default_factory=list)
    blocked_patterns: list[tuple[str, str]] = field(default_factory=list)
    _compiled_dangerous: list[tuple[re.Pattern, str]] = field(
        default_factory=list, init=False, repr=False
    )
    _compiled_suspicious: list[tuple[re.Pattern, str]] = field(
        default_factory=list, init=False, repr=False
    )
    _compiled_blocked: list[tuple[re.Pattern, str]] = field(
        default_factory=list, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Compile regex patterns for efficient matching."""
        self._compiled_dangerous = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in DANGEROUS_PATTERNS
        ]
        self._compiled_suspicious = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in SUSPICIOUS_PATTERNS
        ]
        self._compiled_blocked = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.blocked_patterns
        ]

    def validate(self, command: str) -> ValidationResult:
        """Validate a shell command for security risks.

        Args:
            command: The shell command to validate.

        Returns:
            ValidationResult indicating if the command is safe to execute.
        """
        if not command or not command.strip():
            return ValidationResult.unsafe("Empty command", severity="warning")

        # In STRICT mode, only allow explicitly permitted commands
        if self.security_level == SecurityLevel.STRICT:
            return self._validate_strict(command)

        # Check dangerous patterns (blocked in all modes)
        for pattern, reason in self._compiled_dangerous:
            if pattern.search(command):
                return ValidationResult.unsafe(
                    reason, pattern=pattern.pattern, severity="critical"
                )

        # Check custom blocked patterns
        for pattern, reason in self._compiled_blocked:
            if pattern.search(command):
                return ValidationResult.unsafe(
                    reason, pattern=pattern.pattern, severity="critical"
                )

        # Check suspicious patterns (blocked in STANDARD and STRICT modes)
        if self.security_level in (SecurityLevel.STANDARD, SecurityLevel.STRICT):
            for pattern, reason in self._compiled_suspicious:
                if pattern.search(command):
                    return ValidationResult.unsafe(
                        reason, pattern=pattern.pattern, severity="warning"
                    )

        return ValidationResult.safe()

    def _validate_strict(self, command: str) -> ValidationResult:
        """Validate command in strict/allowlist mode.

        Args:
            command: The shell command to validate.

        Returns:
            ValidationResult - only safe if command matches allowlist.
        """
        # Extract the base command (first word)
        base_command = command.strip().split()[0] if command.strip() else ""

        # Check if base command is in allowlist
        if base_command in self.allowed_commands:
            # Still check for dangerous patterns even in allowlist
            for pattern, reason in self._compiled_dangerous:
                if pattern.search(command):
                    return ValidationResult.unsafe(
                        reason, pattern=pattern.pattern, severity="critical"
                    )
            return ValidationResult.safe()

        return ValidationResult.unsafe(
            f"Command '{base_command}' not in allowlist",
            severity="warning",
        )

    def add_allowed_command(self, command: str) -> None:
        """Add a command to the allowlist.

        Args:
            command: Base command name to allow (e.g., 'ls', 'cat', 'grep').
        """
        if command not in self.allowed_commands:
            self.allowed_commands.append(command)

    def add_blocked_pattern(self, pattern: str, reason: str) -> None:
        """Add a custom blocked pattern.

        Args:
            pattern: Regex pattern to block.
            reason: Human-readable reason for blocking.
        """
        self.blocked_patterns.append((pattern, reason))
        self._compiled_blocked.append(
            (re.compile(pattern, re.IGNORECASE), reason)
        )


@dataclass
class PathSandbox:
    """Restricts file system access to allowed directories.

    This sandbox validates that paths and commands stay within
    the configured allowed directories.
    """

    allowed_paths: list[Path] = field(default_factory=list)
    allow_home_access: bool = False
    allow_temp_access: bool = True

    def __post_init__(self) -> None:
        """Normalize allowed paths to absolute paths."""
        normalized = []
        for p in self.allowed_paths:
            path = Path(p).resolve()
            normalized.append(path)
        self.allowed_paths = normalized

        # Add temp directory if allowed
        if self.allow_temp_access:
            import tempfile
            self.allowed_paths.append(Path(tempfile.gettempdir()).resolve())

        # Add home directory if allowed
        if self.allow_home_access:
            self.allowed_paths.append(Path.home().resolve())

    def is_path_allowed(self, path: str | Path) -> bool:
        """Check if a path is within allowed directories.

        Args:
            path: Path to validate.

        Returns:
            True if path is within an allowed directory.
        """
        try:
            resolved = Path(path).resolve()
            return any(
                self._is_subpath(resolved, allowed)
                for allowed in self.allowed_paths
            )
        except (OSError, ValueError):
            return False

    def _is_subpath(self, path: Path, parent: Path) -> bool:
        """Check if path is a subpath of parent.

        Args:
            path: Path to check.
            parent: Potential parent path.

        Returns:
            True if path is under parent.
        """
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def validate_command_paths(self, command: str, cwd: str | Path) -> ValidationResult:
        """Validate that a command doesn't access paths outside the sandbox.

        Args:
            command: Shell command to validate.
            cwd: Current working directory for relative path resolution.

        Returns:
            ValidationResult indicating if paths are safe.
        """
        cwd_path = Path(cwd).resolve()

        # Check for path traversal attempts
        if ".." in command:
            # Extract potential paths and validate them
            parts = command.split()
            for part in parts:
                if ".." in part:
                    # Try to resolve the path
                    try:
                        if part.startswith("/"):
                            resolved = Path(part).resolve()
                        else:
                            resolved = (cwd_path / part).resolve()

                        if not self.is_path_allowed(resolved):
                            return ValidationResult.unsafe(
                                f"Path traversal outside sandbox: {part}",
                                severity="critical",
                            )
                    except (OSError, ValueError):
                        pass  # Invalid path, let the shell handle it

        # Check for absolute paths in command
        abs_path_pattern = re.compile(r'(?:^|\s)(/[^\s]+)')
        for match in abs_path_pattern.finditer(command):
            abs_path = match.group(1)
            # Skip common safe paths
            if abs_path in ("/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr"):
                continue
            if not self.is_path_allowed(abs_path):
                return ValidationResult.unsafe(
                    f"Absolute path outside sandbox: {abs_path}",
                    severity="warning",
                )

        return ValidationResult.safe()

    def add_allowed_path(self, path: str | Path) -> None:
        """Add a path to the allowed list.

        Args:
            path: Directory path to allow.
        """
        resolved = Path(path).resolve()
        if resolved not in self.allowed_paths:
            self.allowed_paths.append(resolved)


__all__ = [
    "SecurityLevel",
    "ValidationResult",
    "ShellSecurityValidator",
    "PathSandbox",
    "DANGEROUS_PATTERNS",
    "SUSPICIOUS_PATTERNS",
]
