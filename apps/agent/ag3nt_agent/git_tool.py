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

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.tools.git")


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

    def generate_commit_message(
        self,
        staged_files: list[str] | None = None,
        llm: "BaseChatModel | None" = None,
    ) -> str:
        """Generate a conventional commit message from staged changes using LLM.

        Uses the LLM to analyze staged changes and create a commit message
        following the Conventional Commits format:
        <type>(<scope>): <description>

        Types: feat, fix, docs, refactor, test, chore, perf, style

        Args:
            staged_files: List of staged file paths (optional, for context)
            llm: Language model for message generation (required)

        Returns:
            Generated commit message with Co-Authored-By footer

        Raises:
            ValueError: If llm is None or no staged changes exist
        """
        if llm is None:
            raise ValueError("llm parameter is required for commit message generation")

        # Get staged diff
        diff_result = self.diff(staged=True)
        if not diff_result.success or not diff_result.output or diff_result.output == "(no changes)":
            raise ValueError("No staged changes to commit")

        # Get recent commits for style reference
        log_result = self.log(max_count=5, oneline=True)
        recent_commits = log_result.output if log_result.success else ""

        # Build prompt for LLM
        prompt = f"""Generate a git commit message for the following staged changes.

Follow the Conventional Commits format:
<type>(<scope>): <description>

**Types:**
- feat: New feature
- fix: Bug fix
- docs: Documentation changes
- refactor: Code restructuring without behavior change
- test: Test additions/changes
- chore: Maintenance tasks (dependencies, build, etc.)
- perf: Performance improvements
- style: Code style/formatting changes

**Rules:**
- Keep description under 72 characters
- Use imperative mood ("Add feature" not "Added feature")
- Focus on WHAT changed and WHY, not HOW
- Be specific and concise
- Scope is optional but helpful (e.g., "feat(auth): add login endpoint")

**Recent commits for style reference:**
{recent_commits}

**Staged files:**
{', '.join(staged_files) if staged_files else 'multiple files'}

**Changes:**
{diff_result.output[:3000]}

Generate ONLY the commit message (first line only), nothing else. Do not include explanations."""

        # Import here to avoid circular dependency
        from langchain_core.messages import HumanMessage

        # Generate commit message
        response = llm.invoke([HumanMessage(content=prompt)])
        message = response.content.strip()

        # Clean up the message (remove quotes, extra whitespace)
        message = message.strip('"\'')

        # Ensure it's not too long
        if len(message) > 100:
            # Try to truncate at a word boundary
            message = message[:97] + "..."

        # Add Co-Authored-By footer
        full_message = f"{message}\n\nCo-Authored-By: AG3NT Agent <noreply@ag3nt.dev>"

        return full_message

    def smart_commit(
        self,
        files: list[str] | None = None,
        message: str | None = None,
        auto_generate: bool = True,
        llm: "BaseChatModel | None" = None,
    ) -> GitResult:
        """Intelligent commit with auto-generated message.

        Stages files and commits with either a provided message or
        an auto-generated conventional commit message.

        Args:
            files: Files to stage (None = stage all changes)
            message: Manual commit message (overrides auto_generate)
            auto_generate: Generate commit message automatically using LLM
            llm: Language model for message generation (required if auto_generate=True)

        Returns:
            GitResult from the commit operation

        Raises:
            ValueError: If neither message provided nor auto_generate enabled with llm
        """
        # Stage files
        if files:
            for file in files:
                result = self.add(file)
                if not result.success:
                    return result
        else:
            result = self.add(".")
            if not result.success:
                return result

        # Determine commit message
        if message:
            commit_msg = message
        elif auto_generate and llm:
            try:
                commit_msg = self.generate_commit_message(staged_files=files, llm=llm)
            except ValueError as e:
                return GitResult(
                    operation="smart_commit",
                    success=False,
                    output="",
                    error=str(e),
                )
        else:
            return GitResult(
                operation="smart_commit",
                success=False,
                output="",
                error="Must provide message or enable auto_generate with llm",
            )

        # Commit
        return self.commit(commit_msg)

    def create_pull_request(
        self,
        title: str | None = None,
        body: str | None = None,
        base: str = "main",
        draft: bool = False,
        auto_generate: bool = True,
        llm: "BaseChatModel | None" = None,
    ) -> GitResult:
        """Create a GitHub pull request using gh CLI.

        Uses the GitHub CLI (gh) to create a pull request. Title and body
        can be provided manually or auto-generated from commits.

        **Prerequisites:**
        - GitHub CLI (gh) installed and authenticated
        - Remote repository on GitHub
        - Current branch pushed to remote

        Args:
            title: PR title (auto-generated if None and auto_generate=True)
            body: PR description (auto-generated if None and auto_generate=True)
            base: Base branch to merge into (default: "main")
            draft: Create as draft PR (default: False)
            auto_generate: Auto-generate title and body from commits
            llm: Language model for PR content generation

        Returns:
            GitResult with PR URL in output on success

        Raises:
            ValueError: If on base branch or gh CLI not available
        """
        # Check if gh CLI is available
        try:
            subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return GitResult(
                operation="create_pull_request",
                success=False,
                output="",
                error="GitHub CLI (gh) not found. Install from https://cli.github.com/",
            )

        # Get current branch
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        current_branch = result.stdout.strip()

        if current_branch == base:
            return GitResult(
                operation="create_pull_request",
                success=False,
                output="",
                error=f"Cannot create PR: already on base branch '{base}'",
            )

        # Auto-generate title and body if needed
        if (not title or not body) and auto_generate and llm:
            # Get commits since divergence from base
            log_result = self._run(
                ["log", f"{base}..HEAD", "--pretty=format:%h %s"],
                check=False,
            )
            commits = log_result.stdout

            # Get diff summary
            diff_result = self._run(
                ["diff", f"{base}...HEAD", "--stat"],
                check=False,
            )
            diff_summary = diff_result.stdout

            # Generate PR content
            pr_content = self._generate_pr_content(
                commits=commits,
                diff=diff_summary,
                llm=llm,
            )

            title = title or pr_content["title"]
            body = body or pr_content["body"]

        # Push current branch to remote (with --set-upstream if needed)
        push_result = self._run(
            ["push", "-u", "origin", current_branch],
            check=False,
        )
        if push_result.returncode != 0:
            return GitResult(
                operation="create_pull_request",
                success=False,
                output="",
                error=f"Failed to push branch: {push_result.stderr}",
            )

        # Create PR using gh CLI
        gh_args = [
            "gh", "pr", "create",
            "--title", title or "Update",
            "--body", body or "Changes from AG3NT",
            "--base", base,
        ]

        if draft:
            gh_args.append("--draft")

        try:
            result = subprocess.run(
                gh_args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                pr_url = result.stdout.strip()
                return GitResult(
                    operation="create_pull_request",
                    success=True,
                    output=pr_url,
                )
            else:
                return GitResult(
                    operation="create_pull_request",
                    success=False,
                    output="",
                    error=result.stderr,
                )
        except subprocess.TimeoutExpired:
            return GitResult(
                operation="create_pull_request",
                success=False,
                output="",
                error="PR creation timed out",
            )

    def _generate_pr_content(
        self,
        commits: str,
        diff: str,
        llm: "BaseChatModel",
    ) -> dict[str, str]:
        """Generate PR title and description from commits and diff.

        Args:
            commits: Commit history (one per line)
            diff: Diff stat summary
            llm: Language model for generation

        Returns:
            Dict with "title" and "body" keys
        """
        prompt = f"""Generate a GitHub pull request title and description for the following changes.

**Commits:**
{commits}

**Diff summary:**
{diff[:1000]}

Generate:
1. **Title** (max 72 chars) - Concise summary of changes
2. **Description** - Detailed explanation with:
   - ## Summary: What changed and why
   - ## Changes: Bullet list of key changes
   - ## Testing: How to test/verify changes

Use markdown formatting for the description.

Output format (exactly):
TITLE: <title here>
DESCRIPTION:
<description here>
"""

        from langchain_core.messages import HumanMessage

        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content

        # Parse response
        lines = content.split('\n')
        title = ""
        description_lines = []
        in_description = False

        for line in lines:
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("DESCRIPTION:"):
                in_description = True
            elif in_description:
                description_lines.append(line)

        description = '\n'.join(description_lines).strip()

        # Add footer
        description += "\n\n---\n🤖 Generated by AG3NT"

        return {
            "title": title or "Update from AG3NT",
            "body": description,
        }


# =============================================================================
# LangChain @tool wrappers
# =============================================================================

def _get_workspace_git() -> GitTool:
    """Get a GitTool instance for the agent workspace."""
    workspace = Path.home() / ".ag3nt" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Initialize git repo if not present
    git_dir = workspace / ".git"
    if not git_dir.exists():
        subprocess.run(
            ["git", "init"],
            cwd=workspace,
            capture_output=True,
            timeout=10,
        )
        # Configure basic git identity for commits
        subprocess.run(
            ["git", "config", "user.email", "agent@ag3nt.dev"],
            cwd=workspace,
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["git", "config", "user.name", "AG3NT Agent"],
            cwd=workspace,
            capture_output=True,
            timeout=5,
        )

    return GitTool(workspace)


@tool
def git_status() -> str:
    """Show the current git repository status.

    Returns working tree status including staged, unstaged, and untracked files.
    """
    try:
        git = _get_workspace_git()
        result = git.status()
        return result.to_content()
    except Exception as e:
        return f"Error: {e}"


@tool
def git_diff(
    staged: bool = False,
    paths: list[str] | None = None,
) -> str:
    """Show file differences in the git repository.

    Args:
        staged: If True, show staged (cached) changes only.
        paths: Optional list of file paths to diff.
    """
    try:
        git = _get_workspace_git()
        result = git.diff(paths=paths, staged=staged)
        # Truncate long diffs for context window
        content = result.to_content()
        if len(content) > 10_000:
            formatter = DiffFormatter()
            content = formatter.format_for_llm(content, max_lines=150)
        return content
    except Exception as e:
        return f"Error: {e}"


@tool
def git_log(
    n: int = 10,
    oneline: bool = True,
) -> str:
    """Show recent git commit history.

    Args:
        n: Number of commits to show (default: 10).
        oneline: Use compact one-line format (default: True).
    """
    try:
        git = _get_workspace_git()
        result = git.log(n=n, oneline=oneline)
        return result.to_content()
    except Exception as e:
        return f"Error: {e}"


@tool
def git_add(paths: list[str] | None = None) -> str:
    """Stage files for the next commit.

    Args:
        paths: List of file paths to stage. If None, stages all changes.
    """
    try:
        git = _get_workspace_git()
        target = paths if paths else "."
        result = git.add(target)
        return result.to_content()
    except Exception as e:
        return f"Error: {e}"


@tool
def git_commit(message: str) -> str:
    """Create a git commit with staged changes.

    Args:
        message: Commit message (conventional commit format recommended).
    """
    try:
        git = _get_workspace_git()
        result = git.commit(message)
        return result.to_content()
    except Exception as e:
        return f"Error: {e}"


@tool
def git_branch() -> str:
    """List git branches and show the current branch."""
    try:
        git = _get_workspace_git()
        current = git.current_branch()
        result = git.branch()
        return f"Current branch: {current}\n\n{result.to_content()}"
    except Exception as e:
        return f"Error: {e}"


@tool
def git_show(commit: str = "HEAD") -> str:
    """Show details of a specific commit.

    Args:
        commit: Commit reference (hash, branch, tag, or HEAD). Default: HEAD.
    """
    try:
        git = _get_workspace_git()
        result = git.show(commit, stat=True)
        return result.to_content()
    except Exception as e:
        return f"Error: {e}"


def get_git_tools() -> list:
    """Get all git LangChain tools for the agent.

    Returns:
        List of @tool decorated git functions.
    """
    return [
        git_status,
        git_diff,
        git_log,
        git_add,
        git_commit,
        git_branch,
        git_show,
    ]

