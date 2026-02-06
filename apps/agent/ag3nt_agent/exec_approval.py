"""Granular exec approval with allowlists and safe binary detection for AG3NT.

Provides fine-grained control over which shell commands can execute automatically
versus which require human-in-the-loop (HITL) approval.

Components:
    - SafeBinDetector: Identifies read-only/safe commands
    - ShellPipelineAnalyzer: Splits and analyzes command pipelines
    - ExecApprovalEvaluator: Main evaluator combining all checks

Configuration loaded from ~/.ag3nt/exec_policy.yaml.

Usage:
    from ag3nt_agent.exec_approval import ExecApprovalEvaluator

    evaluator = ExecApprovalEvaluator.get_instance()
    result = evaluator.evaluate("ls -la")
    # result.decision == "allow"
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("ag3nt.exec_approval")


@dataclass(frozen=True)
class ExecApprovalResult:
    """Result of exec approval evaluation."""

    decision: Literal["allow", "ask", "deny"]
    reason: str
    matched_rule: str | None = None


# Safe read-only binaries that can execute without approval
SAFE_BINS: set[str] = {
    # File listing and info
    "ls", "dir", "stat", "file", "wc", "du", "df",
    # File reading (non-destructive)
    "cat", "head", "tail", "less", "more", "bat",
    # Search and pattern matching
    "grep", "egrep", "fgrep", "rg", "ag", "ack",
    "find", "fd", "locate", "which", "whereis", "type",
    # Text processing (read-only)
    "sort", "uniq", "cut", "tr", "awk", "sed",
    "diff", "comm", "jq", "yq", "xq",
    # System info
    "echo", "printf", "date", "cal",
    "uname", "hostname", "whoami", "id",
    "pwd", "env", "printenv",
    "uptime", "free", "top", "htop",
    "ps", "pgrep",
    # Network info (read-only)
    "ping", "dig", "nslookup", "host",
    "curl", "wget",  # Allowed for reading, blocked patterns handle dangerous uses
    # Development tools (read-only operations)
    "python", "python3", "node", "ruby", "perl",
    "pip", "npm", "yarn", "pnpm", "cargo", "go",
    "make", "cmake",
    # Version checks
    "java", "javac", "dotnet", "rustc", "gcc", "g++",
}

# Safe git subcommands (read-only operations)
SAFE_GIT_SUBCOMMANDS: set[str] = {
    "status", "log", "diff", "branch", "tag",
    "show", "stash", "remote", "config",
    "ls-files", "ls-tree", "rev-parse", "describe",
    "blame", "shortlog", "reflog",
}

# Dangerous patterns that should always be denied
DENY_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f", "Recursive force delete"),
    (r"\bmkfs\b", "Filesystem format"),
    (r"\bdd\s+.*if=/dev/(zero|random)", "Disk overwrite"),
    (r":\(\)\s*\{", "Fork bomb"),
    (r"\bsudo\s+rm\b", "Sudo rm"),
    (r">\s*/dev/[sh]d[a-z]", "Direct disk write"),
    (r"\bchmod\s+777\s+/", "Dangerous chmod on root"),
]


class SafeBinDetector:
    """Detects if a command uses only safe read-only binaries."""

    def __init__(self, extra_safe: set[str] | None = None) -> None:
        self._safe = SAFE_BINS.copy()
        if extra_safe:
            self._safe.update(extra_safe)

    def is_safe(self, cmd: str) -> bool:
        """Check if a command uses only safe binaries.

        Args:
            cmd: The base command (first word)

        Returns:
            True if the command is considered safe
        """
        return cmd in self._safe

    def is_safe_git(self, full_command: str) -> bool:
        """Check if a git command uses only safe subcommands.

        Args:
            full_command: The full git command string

        Returns:
            True if the git subcommand is safe
        """
        parts = full_command.strip().split()
        if not parts or parts[0] != "git":
            return False

        # Find the subcommand (skip flags like -C)
        for i, part in enumerate(parts[1:], 1):
            if not part.startswith("-"):
                return part in SAFE_GIT_SUBCOMMANDS
            # Skip flag arguments
            if part in ("-C", "--git-dir", "--work-tree"):
                continue

        return False

    def check_version_flag(self, full_command: str) -> bool:
        """Check if command is just a version check.

        Args:
            full_command: The full command string

        Returns:
            True if it's a version check (--version, -V, -v)
        """
        parts = full_command.strip().split()
        if len(parts) == 2 and parts[1] in ("--version", "-V", "-v", "--help", "-h"):
            return True
        return False


class ShellPipelineAnalyzer:
    """Analyze shell command pipelines and chains."""

    # Operators that chain commands
    _CHAIN_OPS = re.compile(r"\s*(?:&&|\|\||;)\s*")
    # Pipe operator
    _PIPE_OP = re.compile(r"\s*\|\s*")

    @classmethod
    def analyze(cls, command: str) -> list[str]:
        """Split a command into its pipeline/chain components.

        Args:
            command: Full shell command string

        Returns:
            List of individual commands in the pipeline/chain
        """
        # First split on chain operators (&&, ||, ;)
        chain_parts = cls._CHAIN_OPS.split(command)

        # Then split each part on pipes
        all_commands: list[str] = []
        for part in chain_parts:
            pipe_parts = cls._PIPE_OP.split(part.strip())
            all_commands.extend(p.strip() for p in pipe_parts if p.strip())

        return all_commands

    @classmethod
    def has_chains(cls, command: str) -> bool:
        """Check if command contains chain operators.

        Args:
            command: Shell command to check

        Returns:
            True if command contains &&, ||, or ;
        """
        return bool(cls._CHAIN_OPS.search(command))

    @classmethod
    def extract_base_command(cls, command: str) -> str:
        """Extract the base binary name from a command.

        Handles paths, env prefixes, and common wrappers.

        Args:
            command: Full command string

        Returns:
            The base command/binary name
        """
        parts = command.strip().split()
        if not parts:
            return ""

        cmd = parts[0]

        # Handle env prefix: `env VAR=val command`
        if cmd == "env" and len(parts) > 1:
            for part in parts[1:]:
                if "=" not in part:
                    cmd = part
                    break

        # Handle path: /usr/bin/ls -> ls
        if "/" in cmd:
            cmd = cmd.rsplit("/", 1)[-1]
        if "\\" in cmd:
            cmd = cmd.rsplit("\\", 1)[-1]

        return cmd


class ExecApprovalEvaluator:
    """Main evaluator for exec command approval.

    Combines safe bin detection, pipeline analysis, and deny patterns
    to make allow/ask/deny decisions.
    """

    _instance: ExecApprovalEvaluator | None = None
    _lock = threading.Lock()

    def __init__(
        self,
        config_path: str | None = None,
        ask_mode: Literal["always", "never", "auto"] = "auto",
    ) -> None:
        self._config_path = config_path or str(
            Path.home() / ".ag3nt" / "exec_policy.yaml"
        )
        self._ask_mode = ask_mode
        self._safe_detector = SafeBinDetector()
        self._allowlist_patterns: list[str] = []
        self._deny_patterns: list[tuple[re.Pattern, str]] = [
            (re.compile(p, re.IGNORECASE), reason)
            for p, reason in DENY_PATTERNS
        ]
        self._load_config()

    @classmethod
    def get_instance(cls) -> ExecApprovalEvaluator:
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        config_path = Path(self._config_path)
        if not config_path.exists():
            return

        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                return

            self._ask_mode = config.get("ask_mode", self._ask_mode)

            # Load allowlist patterns
            allowlist = config.get("allowlist", [])
            if isinstance(allowlist, list):
                self._allowlist_patterns = allowlist

            # Load extra safe bins
            extra_safe = config.get("safe_bins", [])
            if isinstance(extra_safe, list):
                self._safe_detector = SafeBinDetector(extra_safe=set(extra_safe))

            # Load additional deny patterns
            extra_deny = config.get("deny_patterns", [])
            if isinstance(extra_deny, list):
                for item in extra_deny:
                    if isinstance(item, dict):
                        pattern = item.get("pattern", "")
                        reason = item.get("reason", "Custom deny pattern")
                        self._deny_patterns.append(
                            (re.compile(pattern, re.IGNORECASE), reason)
                        )

        except ImportError:
            logger.debug("PyYAML not installed, using defaults")
        except Exception as e:
            logger.warning(f"Failed to load exec policy config: {e}")

    def evaluate(self, command: str) -> ExecApprovalResult:
        """Evaluate a command for approval.

        Decision logic:
        1. Check deny patterns -> deny
        2. If ask_mode == "never" -> allow
        3. If ask_mode == "always" -> ask
        4. Check allowlist patterns -> allow if matched
        5. Check safe bins -> allow if safe
        6. Check version flags -> allow
        7. Check safe git subcommands -> allow
        8. Default -> ask (requires HITL approval)

        Args:
            command: The shell command to evaluate

        Returns:
            ExecApprovalResult with decision, reason, and matched rule
        """
        if not command or not command.strip():
            return ExecApprovalResult("deny", "Empty command")

        # Step 1: Check deny patterns
        for pattern, reason in self._deny_patterns:
            if pattern.search(command):
                return ExecApprovalResult(
                    "deny", reason, matched_rule=f"deny:{pattern.pattern}"
                )

        # Step 2: Ask mode overrides
        if self._ask_mode == "never":
            return ExecApprovalResult(
                "allow", "Ask mode is 'never'", matched_rule="mode:never"
            )

        if self._ask_mode == "always":
            return ExecApprovalResult(
                "ask", "Ask mode is 'always'", matched_rule="mode:always"
            )

        # Step 3: Check allowlist patterns (glob matching)
        if self._check_allowlist(command):
            return ExecApprovalResult(
                "allow", "Matched allowlist pattern", matched_rule="allowlist"
            )

        # Step 4: Analyze pipeline
        commands = ShellPipelineAnalyzer.analyze(command)

        # For chained commands, require approval if any component is unsafe
        all_safe = True
        for cmd_part in commands:
            base_cmd = ShellPipelineAnalyzer.extract_base_command(cmd_part)

            # Check version flags
            if self._safe_detector.check_version_flag(cmd_part):
                continue

            # Check safe git subcommands
            if base_cmd == "git" and self._safe_detector.is_safe_git(cmd_part):
                continue

            # Check safe bins
            if self._safe_detector.is_safe(base_cmd):
                continue

            all_safe = False
            break

        if all_safe:
            return ExecApprovalResult(
                "allow",
                "All commands use safe binaries",
                matched_rule="safe_bins",
            )

        # Default: ask for approval
        return ExecApprovalResult(
            "ask",
            f"Command requires approval: {command[:60]}",
            matched_rule="default",
        )

    def _check_allowlist(self, command: str) -> bool:
        """Check if command matches any allowlist pattern.

        Args:
            command: The command to check

        Returns:
            True if matched
        """
        import fnmatch

        base_cmd = ShellPipelineAnalyzer.extract_base_command(command)

        for pattern in self._allowlist_patterns:
            # Try matching against base command name
            if fnmatch.fnmatch(base_cmd, pattern):
                return True

            # Try matching against resolved path
            resolved = shutil.which(base_cmd)
            if resolved and fnmatch.fnmatch(resolved, pattern):
                return True

        return False
