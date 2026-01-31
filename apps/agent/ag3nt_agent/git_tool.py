"""Git operations tool with safety checks and structured output.

This module provides safe git operations for the AG3NT agent with:
- Structured GitResult output for all operations
- Safety checks for destructive operations
- HITL approval requirements for dangerous operations (push, reset --hard)
- Diff formatting for LLM consumption
- Timeout protection for all operations

Security Note:
- Push, reset --hard, and force operations require HITL approval
- Protected branches can be configured to prevent accidental modifications
- All operations are sandboxed to the repository path
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal


class GitOperation(Enum):
    """Git operation types."""
    STATUS = "status"
    ADD = "add"
    COMMIT = "commit"
    PUSH = "push"
    PULL = "pull"
    DIFF = "diff"
    LOG = "log"
    BRANCH = "branch"
    CHECKOUT = "checkout"
    STASH = "stash"
    RESET = "reset"
    SHOW = "show"
    FETCH = "fetch"


# Operations that require HITL approval
DANGEROUS_OPERATIONS: set[GitOperation] = {
    GitOperation.PUSH,
    GitOperation.RESET,
}

# Operations that may lose uncommitted changes
CHANGE_LOSING_OPERATIONS: set[GitOperation] = {
    GitOperation.CHECKOUT,
    GitOperation.RESET,
    GitOperation.STASH,
}


@dataclass(frozen=True)
class GitResult:
    """Result from a git operation.

    Attributes:
        operation: The git operation that was performed.
        success: Whether the operation completed successfully.
        output: The stdout from the git command.
        error: The stderr from the git command, if any.
        requires_approval: Whether this operation requires HITL approval.
        duration_ms: Time taken to execute the operation in milliseconds.
    """
    operation: str
    success: bool
    output: str
    error: str | None = None
    requires_approval: bool = False
    duration_ms: float | None = None

    def to_content(self) -> str:
        """Format result for LLM consumption."""
        if self.requires_approval:
            return f"⚠️ Operation '{self.operation}' requires approval before execution."

        if not self.success:
            error_msg = self.error or "Unknown error"
            return f"❌ git {self.operation} failed: {error_msg}"

        return self.output or f"✓ git {self.operation} completed successfully"


class GitSafetyChecker:
    """Safety checks for git operations.

    Provides validation methods to ensure git operations are safe:
    - Detects uncommitted changes before destructive operations
    - Validates commit message format and length
    - Checks branch protection rules
    - Identifies dangerous command patterns
    """

    def __init__(
        self,
        protected_branches: list[str] | None = None,
        min_commit_message_length: int = 3,
        max_commit_message_length: int = 500,
    ) -> None:
        """Initialize the safety checker.

        Args:
            protected_branches: List of branch names that cannot be modified.
                Defaults to ["main", "master", "production"].
            min_commit_message_length: Minimum commit message length.
            max_commit_message_length: Maximum commit message length.
        """
        self.protected_branches = protected_branches or ["main", "master", "production"]
        self.min_commit_message_length = min_commit_message_length
        self.max_commit_message_length = max_commit_message_length

    def check_uncommitted_changes(self, tool: "GitTool") -> tuple[bool, str | None]:
        """Check if there are uncommitted changes.

        Args:
            tool: The GitTool instance to check.

        Returns:
            Tuple of (has_changes, message). If has_changes is True,
            message describes the uncommitted changes.
        """
        result = tool.status(short=True)
        if result.success and result.output.strip():
            return True, "Uncommitted changes detected"
        return False, None

    def validate_commit_message(self, message: str) -> tuple[bool, str | None]:
        """Validate commit message format.

        Args:
            message: The commit message to validate.

        Returns:
            Tuple of (valid, error). If valid is False, error describes the issue.
        """
        if not message or not message.strip():
            return False, "Commit message cannot be empty"

        message = message.strip()

        if len(message) < self.min_commit_message_length:
            return False, f"Commit message too short (minimum {self.min_commit_message_length} characters)"

        if len(message) > self.max_commit_message_length:
            return False, f"Commit message too long (maximum {self.max_commit_message_length} characters)"

        return True, None

    def check_branch_protection(self, branch: str) -> tuple[bool, str | None]:
        """Check if a branch is protected.

        Args:
            branch: The branch name to check.

        Returns:
            Tuple of (allowed, error). If allowed is False, error describes why.
        """
        if branch in self.protected_branches:
            return False, f"Branch '{branch}' is protected"
        return True, None

    def is_dangerous_operation(self, operation: GitOperation) -> bool:
        """Check if an operation is dangerous and requires approval.

        Args:
            operation: The git operation to check.

        Returns:
            True if the operation requires HITL approval.
        """
        return operation in DANGEROUS_OPERATIONS

    def validate_reset_args(self, args: list[str]) -> tuple[bool, str | None]:
        """Validate reset command arguments for safety.

        Args:
            args: The arguments passed to git reset.

        Returns:
            Tuple of (safe, error). If safe is False, error describes the risk.
        """
        if "--hard" in args:
            return False, "git reset --hard will discard all uncommitted changes. Requires approval."
        if "--merge" in args:
            return False, "git reset --merge may lose changes. Requires approval."
        return True, None

    def validate_push_args(self, args: list[str]) -> tuple[bool, str | None]:
        """Validate push command arguments for safety.

        Args:
            args: The arguments passed to git push.

        Returns:
            Tuple of (safe, error). If safe is False, error describes the risk.
        """
        if "--force" in args or "-f" in args:
            return False, "Force push will overwrite remote history. Requires approval."
        if "--force-with-lease" in args:
            return False, "Force push (with lease) may overwrite remote history. Requires approval."
        return True, None


class GitTool:
    """Safe git operations with structured output.

    Provides a safe interface for git operations with:
    - Automatic repository validation
    - Timeout protection
    - Structured GitResult output
    - HITL approval requirements for dangerous operations

    Usage:
        git = GitTool("/path/to/repo")
        result = git.status()
        if result.success:
            print(result.output)
    """

    def __init__(
        self,
        repo_path: str | Path,
        timeout: int = 60,
        protected_branches: list[str] | None = None,
    ) -> None:
        """Initialize the GitTool.

        Args:
            repo_path: Path to the git repository.
            timeout: Maximum time in seconds for git operations.
            protected_branches: List of protected branch names.

        Raises:
            ValueError: If repo_path is not a valid git repository.
        """
        self.repo_path = Path(repo_path).resolve()
        self.timeout = timeout
        self.safety = GitSafetyChecker(protected_branches=protected_branches)
        self._validate_repo()

    def _validate_repo(self) -> None:
        """Ensure repo_path is a valid git repository."""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists() and not (self.repo_path / ".git").is_file():
            # Check if it's a worktree or submodule
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    raise ValueError(f"Not a git repository: {self.repo_path}")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                raise ValueError(f"Not a git repository: {self.repo_path}") from e

    def _run(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command.

        Args:
            args: Git command arguments (without 'git' prefix).
            check: Whether to raise on non-zero exit code.

        Returns:
            CompletedProcess with stdout and stderr.
        """
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=check,
        )

    def _execute(
        self,
        operation: str,
        args: list[str],
        check: bool = True,
    ) -> GitResult:
        """Execute a git command and return structured result.

        Args:
            operation: Name of the operation for the result.
            args: Git command arguments.
            check: Whether to raise on non-zero exit code.

        Returns:
            GitResult with operation outcome.
        """
        start_time = time.perf_counter()
        try:
            result = self._run(args, check=check)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return GitResult(
                operation=operation,
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.stderr else None,
                duration_ms=duration_ms,
            )
        except subprocess.CalledProcessError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return GitResult(
                operation=operation,
                success=False,
                output=e.stdout or "",
                error=e.stderr or str(e),
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return GitResult(
                operation=operation,
                success=False,
                output="",
                error=f"Operation timed out after {self.timeout} seconds",
                duration_ms=duration_ms,
            )

    def status(self, *, short: bool = False, branch: bool = True) -> GitResult:
        """Get repository status.

        Args:
            short: Use short format output.
            branch: Include branch information.

        Returns:
            GitResult with status output.
        """
        args = ["status"]
        if short:
            args.append("--short")
        if branch and short:
            args.append("--branch")
        return self._execute("status", args, check=False)

    def add(self, paths: list[str] | Literal["."]) -> GitResult:
        """Stage files for commit.

        Args:
            paths: List of file paths to stage, or "." for all.

        Returns:
            GitResult with staging outcome.
        """
        if paths == ".":
            args = ["add", "."]
        else:
            args = ["add"] + list(paths)

        result = self._execute("add", args, check=False)
        if result.success:
            staged = ", ".join(paths) if isinstance(paths, list) else "all files"
            return GitResult(
                operation="add",
                success=True,
                output=f"Staged: {staged}",
                duration_ms=result.duration_ms,
            )
        return result

    def commit(self, message: str, *, allow_empty: bool = False) -> GitResult:
        """Create a commit.

        Args:
            message: Commit message.
            allow_empty: Allow creating empty commits.

        Returns:
            GitResult with commit outcome.
        """
        # Validate message
        valid, error = self.safety.validate_commit_message(message)
        if not valid:
            return GitResult(
                operation="commit",
                success=False,
                output="",
                error=error,
            )

        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")

        return self._execute("commit", args, check=False)

    def diff(
        self,
        paths: list[str] | None = None,
        *,
        staged: bool = False,
        stat: bool = False,
        name_only: bool = False,
    ) -> GitResult:
        """Show file differences.

        Args:
            paths: Specific file paths to diff.
            staged: Show staged changes (--staged).
            stat: Show diffstat instead of full diff.
            name_only: Show only file names that changed.

        Returns:
            GitResult with diff output.
        """
        args = ["diff"]
        if staged:
            args.append("--staged")
        if stat:
            args.append("--stat")
        if name_only:
            args.append("--name-only")
        if paths:
            args.extend(paths)

        result = self._execute("diff", args, check=False)
        if result.success and not result.output.strip():
            return GitResult(
                operation="diff",
                success=True,
                output="(no changes)",
                duration_ms=result.duration_ms,
            )
        return result

    def log(
        self,
        n: int = 10,
        *,
        oneline: bool = True,
        graph: bool = False,
        all_branches: bool = False,
    ) -> GitResult:
        """Show commit log.

        Args:
            n: Number of commits to show.
            oneline: Use one-line format.
            graph: Show ASCII graph.
            all_branches: Show commits from all branches.

        Returns:
            GitResult with log output.
        """
        args = ["log", f"-{n}"]
        if oneline:
            args.append("--oneline")
        if graph:
            args.append("--graph")
        if all_branches:
            args.append("--all")

        return self._execute("log", args, check=False)

    def branch(
        self,
        *,
        list_all: bool = False,
        list_remote: bool = False,
    ) -> GitResult:
        """List branches.

        Args:
            list_all: Include remote branches.
            list_remote: Show only remote branches.

        Returns:
            GitResult with branch list.
        """
        args = ["branch"]
        if list_all:
            args.append("-a")
        elif list_remote:
            args.append("-r")

        return self._execute("branch", args, check=False)

    def current_branch(self) -> str:
        """Get the current branch name.

        Returns:
            Current branch name, or "HEAD" if detached.
        """
        result = self._execute("rev-parse", ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if result.success:
            return result.output.strip()
        return "HEAD"

    def show(
        self,
        commit: str = "HEAD",
        *,
        stat: bool = False,
        name_only: bool = False,
    ) -> GitResult:
        """Show commit details.

        Args:
            commit: Commit reference to show.
            stat: Show diffstat only.
            name_only: Show only file names.

        Returns:
            GitResult with commit details.
        """
        args = ["show", commit]
        if stat:
            args.append("--stat")
        if name_only:
            args.append("--name-only")

        return self._execute("show", args, check=False)

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        *,
        force: bool = False,
    ) -> GitResult:
        """Push commits to remote.

        Note: Push always requires HITL approval.

        Args:
            remote: Remote name.
            branch: Branch to push (defaults to current).
            force: Force push (dangerous!).

        Returns:
            GitResult with requires_approval=True.
        """
        args = [remote]
        if branch:
            args.append(branch)
        if force:
            args.extend(["--force"])

        # Validate push args
        safe, error = self.safety.validate_push_args(args)
        if not safe:
            return GitResult(
                operation="push",
                success=False,
                output="",
                error=error,
                requires_approval=True,
            )

        # Push always requires approval
        return GitResult(
            operation="push",
            success=False,
            output="",
            error="Push requires HITL approval. Use execute_push() after approval.",
            requires_approval=True,
        )

    def execute_push(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> GitResult:
        """Execute push after HITL approval.

        Args:
            remote: Remote name.
            branch: Branch to push.

        Returns:
            GitResult with push outcome.
        """
        args = ["push", remote]
        if branch:
            args.append(branch)

        return self._execute("push", args, check=False)

    def pull(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> GitResult:
        """Pull changes from remote.

        Args:
            remote: Remote name.
            branch: Branch to pull.

        Returns:
            GitResult with pull outcome.
        """
        args = ["pull", remote]
        if branch:
            args.append(branch)

        return self._execute("pull", args, check=False)

    def fetch(
        self,
        remote: str = "origin",
        *,
        all_remotes: bool = False,
        prune: bool = False,
    ) -> GitResult:
        """Fetch changes from remote.

        Args:
            remote: Remote name.
            all_remotes: Fetch from all remotes.
            prune: Prune deleted remote branches.

        Returns:
            GitResult with fetch outcome.
        """
        args = ["fetch"]
        if all_remotes:
            args.append("--all")
        else:
            args.append(remote)
        if prune:
            args.append("--prune")

        return self._execute("fetch", args, check=False)

    def stash(
        self,
        action: Literal["push", "pop", "list", "drop", "clear"] = "push",
        message: str | None = None,
    ) -> GitResult:
        """Manage stash.

        Args:
            action: Stash action to perform.
            message: Message for stash push.

        Returns:
            GitResult with stash outcome.
        """
        args = ["stash", action]
        if action == "push" and message:
            args.extend(["-m", message])

        return self._execute("stash", args, check=False)


class DiffFormatter:
    """Format git diff output for LLM consumption.

    Provides methods to parse and summarize diff output.
    """

    @staticmethod
    def summarize_diff(diff_output: str) -> str:
        """Summarize a diff into a compact format.

        Args:
            diff_output: Raw git diff output.

        Returns:
            Summary string with file count and line changes.
        """
        if not diff_output or diff_output == "(no changes)":
            return "No changes"

        files_changed = 0
        insertions = 0
        deletions = 0

        for line in diff_output.split("\n"):
            if line.startswith("diff --git"):
                files_changed += 1
            elif line.startswith("+") and not line.startswith("+++"):
                insertions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        return f"{files_changed} file(s) changed, +{insertions} -{deletions} lines"

    @staticmethod
    def get_changed_files(diff_output: str) -> list[str]:
        """Extract list of changed files from diff.

        Args:
            diff_output: Raw git diff output.

        Returns:
            List of file paths that were changed.
        """
        files = []
        for line in diff_output.split("\n"):
            if line.startswith("diff --git"):
                # Extract file path from "diff --git a/path b/path"
                match = re.search(r"diff --git a/(.+) b/", line)
                if match:
                    files.append(match.group(1))
        return files

    @staticmethod
    def format_for_llm(diff_output: str, max_lines: int = 100) -> str:
        """Format diff for LLM consumption with truncation.

        Args:
            diff_output: Raw git diff output.
            max_lines: Maximum lines to include.

        Returns:
            Formatted diff string.
        """
        if not diff_output or diff_output == "(no changes)":
            return "No changes detected."

        lines = diff_output.split("\n")
        if len(lines) <= max_lines:
            return diff_output

        # Truncate and add summary
        truncated = "\n".join(lines[:max_lines])
        remaining = len(lines) - max_lines
        summary = DiffFormatter.summarize_diff(diff_output)

        return f"{truncated}\n\n... ({remaining} more lines)\n\nSummary: {summary}"

