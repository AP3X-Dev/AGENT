"""Unit tests for git_tool module.

Tests cover:
- GitResult dataclass and to_content() method
- GitSafetyChecker validation methods
- GitTool git operations with mocked subprocess
- DiffFormatter formatting utilities
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ag3nt_agent.git_tool import (
    CHANGE_LOSING_OPERATIONS,
    DANGEROUS_OPERATIONS,
    DiffFormatter,
    GitOperation,
    GitResult,
    GitSafetyChecker,
    GitTool,
    get_git_tools,
    git_status,
    git_diff,
    git_log,
    git_add,
    git_commit,
    git_branch,
    git_show,
)


# ============================================================================
# GitResult Tests
# ============================================================================


class TestGitResult:
    """Tests for GitResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = GitResult(
            operation="status",
            success=True,
            output="On branch main",
        )
        assert result.operation == "status"
        assert result.success is True
        assert result.output == "On branch main"
        assert result.error is None
        assert result.requires_approval is False
        assert result.duration_ms is None

    def test_create_failure_result(self):
        """Test creating a failure result."""
        result = GitResult(
            operation="commit",
            success=False,
            output="",
            error="nothing to commit",
        )
        assert result.success is False
        assert result.error == "nothing to commit"

    def test_create_approval_required_result(self):
        """Test creating a result requiring approval."""
        result = GitResult(
            operation="push",
            success=False,
            output="",
            requires_approval=True,
        )
        assert result.requires_approval is True

    def test_to_content_success(self):
        """Test to_content for successful operation."""
        result = GitResult(
            operation="status",
            success=True,
            output="On branch main\nnothing to commit",
        )
        assert result.to_content() == "On branch main\nnothing to commit"

    def test_to_content_success_empty_output(self):
        """Test to_content for successful operation with empty output."""
        result = GitResult(
            operation="add",
            success=True,
            output="",
        )
        assert result.to_content() == "✓ git add completed successfully"

    def test_to_content_failure(self):
        """Test to_content for failed operation."""
        result = GitResult(
            operation="commit",
            success=False,
            output="",
            error="nothing to commit",
        )
        assert "❌ git commit failed" in result.to_content()
        assert "nothing to commit" in result.to_content()

    def test_to_content_failure_no_error(self):
        """Test to_content for failed operation with no error message."""
        result = GitResult(
            operation="push",
            success=False,
            output="",
        )
        assert "Unknown error" in result.to_content()

    def test_to_content_requires_approval(self):
        """Test to_content for operation requiring approval."""
        result = GitResult(
            operation="push",
            success=False,
            output="",
            requires_approval=True,
        )
        assert "⚠️" in result.to_content()
        assert "requires approval" in result.to_content()

    def test_result_is_frozen(self):
        """Test that GitResult is immutable."""
        result = GitResult(operation="status", success=True, output="test")
        with pytest.raises(Exception):  # FrozenInstanceError
            result.success = False


# ============================================================================
# GitOperation and Constants Tests
# ============================================================================


class TestGitOperationConstants:
    """Tests for GitOperation enum and constants."""

    def test_all_operations_exist(self):
        """Test all expected operations are defined."""
        expected = [
            "STATUS", "ADD", "COMMIT", "PUSH", "PULL",
            "DIFF", "LOG", "BRANCH", "CHECKOUT", "STASH",
            "RESET", "SHOW", "FETCH",
        ]
        for op in expected:
            assert hasattr(GitOperation, op)

    def test_dangerous_operations(self):
        """Test dangerous operations are correctly defined."""
        assert GitOperation.PUSH in DANGEROUS_OPERATIONS
        assert GitOperation.RESET in DANGEROUS_OPERATIONS
        assert GitOperation.STATUS not in DANGEROUS_OPERATIONS
        assert GitOperation.COMMIT not in DANGEROUS_OPERATIONS

    def test_change_losing_operations(self):
        """Test change-losing operations are correctly defined."""
        assert GitOperation.CHECKOUT in CHANGE_LOSING_OPERATIONS
        assert GitOperation.RESET in CHANGE_LOSING_OPERATIONS
        assert GitOperation.STASH in CHANGE_LOSING_OPERATIONS
        assert GitOperation.STATUS not in CHANGE_LOSING_OPERATIONS


# ============================================================================
# GitSafetyChecker Tests
# ============================================================================


class TestGitSafetyChecker:
    """Tests for GitSafetyChecker class."""

    def test_init_default_protected_branches(self):
        """Test default protected branches."""
        checker = GitSafetyChecker()
        assert "main" in checker.protected_branches
        assert "master" in checker.protected_branches
        assert "production" in checker.protected_branches

    def test_init_custom_protected_branches(self):
        """Test custom protected branches."""
        checker = GitSafetyChecker(protected_branches=["develop", "release"])
        assert "develop" in checker.protected_branches
        assert "release" in checker.protected_branches
        assert "main" not in checker.protected_branches

    def test_init_custom_message_lengths(self):
        """Test custom commit message length limits."""
        checker = GitSafetyChecker(
            min_commit_message_length=10,
            max_commit_message_length=100,
        )
        assert checker.min_commit_message_length == 10
        assert checker.max_commit_message_length == 100

    # validate_commit_message tests
    def test_validate_commit_message_valid(self):
        """Test valid commit message."""
        checker = GitSafetyChecker()
        valid, error = checker.validate_commit_message("feat: add new feature")
        assert valid is True
        assert error is None

    def test_validate_commit_message_empty(self):
        """Test empty commit message."""
        checker = GitSafetyChecker()
        valid, error = checker.validate_commit_message("")
        assert valid is False
        assert "empty" in error.lower()

    def test_validate_commit_message_whitespace_only(self):
        """Test whitespace-only commit message."""
        checker = GitSafetyChecker()
        valid, error = checker.validate_commit_message("   ")
        assert valid is False
        assert "empty" in error.lower()

    def test_validate_commit_message_too_short(self):
        """Test commit message that's too short."""
        checker = GitSafetyChecker(min_commit_message_length=5)
        valid, error = checker.validate_commit_message("ab")
        assert valid is False
        assert "short" in error.lower()

    def test_validate_commit_message_too_long(self):
        """Test commit message that's too long."""
        checker = GitSafetyChecker(max_commit_message_length=10)
        valid, error = checker.validate_commit_message("x" * 20)
        assert valid is False
        assert "long" in error.lower()

    # check_branch_protection tests
    def test_check_branch_protection_protected(self):
        """Test protected branch detection."""
        checker = GitSafetyChecker()
        allowed, error = checker.check_branch_protection("main")
        assert allowed is False
        assert "protected" in error.lower()

    def test_check_branch_protection_allowed(self):
        """Test allowed branch."""
        checker = GitSafetyChecker()
        allowed, error = checker.check_branch_protection("feature/new-feature")
        assert allowed is True
        assert error is None

    # is_dangerous_operation tests
    def test_is_dangerous_operation_push(self):
        """Test push is dangerous."""
        checker = GitSafetyChecker()
        assert checker.is_dangerous_operation(GitOperation.PUSH) is True

    def test_is_dangerous_operation_reset(self):
        """Test reset is dangerous."""
        checker = GitSafetyChecker()
        assert checker.is_dangerous_operation(GitOperation.RESET) is True

    def test_is_dangerous_operation_status(self):
        """Test status is not dangerous."""
        checker = GitSafetyChecker()
        assert checker.is_dangerous_operation(GitOperation.STATUS) is False

    # validate_reset_args tests
    def test_validate_reset_args_hard(self):
        """Test reset --hard is blocked."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_reset_args(["--hard", "HEAD~1"])
        assert safe is False
        assert "hard" in error.lower()

    def test_validate_reset_args_merge(self):
        """Test reset --merge is blocked."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_reset_args(["--merge"])
        assert safe is False
        assert "merge" in error.lower()

    def test_validate_reset_args_soft(self):
        """Test reset --soft is allowed."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_reset_args(["--soft", "HEAD~1"])
        assert safe is True
        assert error is None

    # validate_push_args tests
    def test_validate_push_args_force(self):
        """Test push --force is blocked."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_push_args(["origin", "main", "--force"])
        assert safe is False
        assert "force" in error.lower()

    def test_validate_push_args_force_short(self):
        """Test push -f is blocked."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_push_args(["origin", "-f"])
        assert safe is False
        assert "force" in error.lower()

    def test_validate_push_args_force_with_lease(self):
        """Test push --force-with-lease is blocked."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_push_args(["origin", "--force-with-lease"])
        assert safe is False
        assert "force" in error.lower()

    def test_validate_push_args_normal(self):
        """Test normal push is allowed."""
        checker = GitSafetyChecker()
        safe, error = checker.validate_push_args(["origin", "main"])
        assert safe is True
        assert error is None

    # check_uncommitted_changes tests
    def test_check_uncommitted_changes_has_changes(self):
        """Test detection of uncommitted changes."""
        checker = GitSafetyChecker()
        mock_tool = MagicMock()
        mock_tool.status.return_value = GitResult(
            operation="status",
            success=True,
            output="M file.txt",
        )
        has_changes, msg = checker.check_uncommitted_changes(mock_tool)
        assert has_changes is True
        assert msg is not None

    def test_check_uncommitted_changes_clean(self):
        """Test clean working directory."""
        checker = GitSafetyChecker()
        mock_tool = MagicMock()
        mock_tool.status.return_value = GitResult(
            operation="status",
            success=True,
            output="",
        )
        has_changes, msg = checker.check_uncommitted_changes(mock_tool)
        assert has_changes is False
        assert msg is None


# ============================================================================
# GitTool Tests
# ============================================================================


class TestGitToolInit:
    """Tests for GitTool initialization."""

    @patch("subprocess.run")
    def test_init_with_git_dir(self, mock_run, tmp_path):
        """Test initialization with valid .git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        tool = GitTool(tmp_path)
        assert tool.repo_path == tmp_path.resolve()
        assert tool.timeout == 60

    @patch("subprocess.run")
    def test_init_with_worktree(self, mock_run, tmp_path):
        """Test initialization with worktree (no .git dir, but git command works)."""
        mock_run.return_value = MagicMock(returncode=0, stdout=".git")
        tool = GitTool(tmp_path)
        assert tool.repo_path == tmp_path.resolve()

    def test_init_invalid_repo(self, tmp_path):
        """Test initialization with invalid repository."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr="not a git repo")
            with pytest.raises(ValueError, match="Not a git repository"):
                GitTool(tmp_path)

    def test_init_timeout_expired(self, tmp_path):
        """Test initialization when git command times out."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
            with pytest.raises(ValueError, match="Not a git repository"):
                GitTool(tmp_path)

    @patch("subprocess.run")
    def test_init_custom_timeout(self, mock_run, tmp_path):
        """Test initialization with custom timeout."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        tool = GitTool(tmp_path, timeout=120)
        assert tool.timeout == 120

    @patch("subprocess.run")
    def test_init_custom_protected_branches(self, mock_run, tmp_path):
        """Test initialization with custom protected branches."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        tool = GitTool(tmp_path, protected_branches=["develop"])
        assert "develop" in tool.safety.protected_branches


class TestGitToolOperations:
    """Tests for GitTool operations."""

    @pytest.fixture
    def git_tool(self, tmp_path):
        """Create a GitTool instance with mocked validation."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        return GitTool(tmp_path)

    # status tests
    @patch("subprocess.run")
    def test_status_success(self, mock_run, git_tool):
        """Test successful status command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="On branch main\nnothing to commit",
            stderr="",
        )
        result = git_tool.status()
        assert result.success is True
        assert "On branch main" in result.output
        assert result.duration_ms is not None

    @patch("subprocess.run")
    def test_status_short(self, mock_run, git_tool):
        """Test status with short format."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="M file.txt",
            stderr="",
        )
        result = git_tool.status(short=True)
        assert result.success is True
        # Verify --short was passed
        call_args = mock_run.call_args[0][0]
        assert "--short" in call_args

    @patch("subprocess.run")
    def test_status_short_with_branch(self, mock_run, git_tool):
        """Test status with short and branch options."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="## main\nM file.txt",
            stderr="",
        )
        result = git_tool.status(short=True, branch=True)
        assert result.success is True
        call_args = mock_run.call_args[0][0]
        assert "--short" in call_args
        assert "--branch" in call_args

    # add tests
    @patch("subprocess.run")
    def test_add_single_file(self, mock_run, git_tool):
        """Test staging a single file."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = git_tool.add(["file.txt"])
        assert result.success is True
        assert "Staged" in result.output

    @patch("subprocess.run")
    def test_add_multiple_files(self, mock_run, git_tool):
        """Test staging multiple files."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = git_tool.add(["file1.txt", "file2.txt"])
        assert result.success is True

    @patch("subprocess.run")
    def test_add_all(self, mock_run, git_tool):
        """Test staging all files."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = git_tool.add(".")
        assert result.success is True
        assert "all files" in result.output

    @patch("subprocess.run")
    def test_add_failure(self, mock_run, git_tool):
        """Test add failure."""
        mock_run.return_value = MagicMock(
            returncode=128,
            stdout="",
            stderr="pathspec 'nonexistent' did not match",
        )
        result = git_tool.add(["nonexistent"])
        assert result.success is False

    # commit tests
    @patch("subprocess.run")
    def test_commit_success(self, mock_run, git_tool):
        """Test successful commit."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[main abc1234] feat: add feature",
            stderr="",
        )
        result = git_tool.commit("feat: add feature")
        assert result.success is True

    @patch("subprocess.run")
    def test_commit_allow_empty(self, mock_run, git_tool):
        """Test commit with allow_empty."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[main abc1234] empty commit",
            stderr="",
        )
        result = git_tool.commit("empty commit", allow_empty=True)
        assert result.success is True
        call_args = mock_run.call_args[0][0]
        assert "--allow-empty" in call_args

    def test_commit_empty_message(self, git_tool):
        """Test commit with empty message fails validation."""
        result = git_tool.commit("")
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_commit_short_message(self, git_tool):
        """Test commit with too-short message fails validation."""
        result = git_tool.commit("ab")
        assert result.success is False
        assert "short" in result.error.lower()

    # diff tests
    @patch("subprocess.run")
    def test_diff_no_changes(self, mock_run, git_tool):
        """Test diff with no changes."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = git_tool.diff()
        assert result.success is True
        assert "(no changes)" in result.output

    @patch("subprocess.run")
    def test_diff_with_changes(self, mock_run, git_tool):
        """Test diff with changes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="diff --git a/file.txt b/file.txt\n+new line",
            stderr="",
        )
        result = git_tool.diff()
        assert result.success is True
        assert "diff --git" in result.output

    @patch("subprocess.run")
    def test_diff_staged(self, mock_run, git_tool):
        """Test diff with staged option."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.diff(staged=True)
        call_args = mock_run.call_args[0][0]
        assert "--staged" in call_args

    @patch("subprocess.run")
    def test_diff_stat(self, mock_run, git_tool):
        """Test diff with stat option."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.diff(stat=True)
        call_args = mock_run.call_args[0][0]
        assert "--stat" in call_args

    @patch("subprocess.run")
    def test_diff_name_only(self, mock_run, git_tool):
        """Test diff with name_only option."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.diff(name_only=True)
        call_args = mock_run.call_args[0][0]
        assert "--name-only" in call_args

    @patch("subprocess.run")
    def test_diff_paths(self, mock_run, git_tool):
        """Test diff with specific paths."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.diff(paths=["src/", "tests/"])
        call_args = mock_run.call_args[0][0]
        assert "src/" in call_args
        assert "tests/" in call_args

    # log tests
    @patch("subprocess.run")
    def test_log_default(self, mock_run, git_tool):
        """Test log with default options."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1234 Initial commit",
            stderr="",
        )
        result = git_tool.log()
        assert result.success is True
        call_args = mock_run.call_args[0][0]
        assert "-10" in call_args
        assert "--oneline" in call_args

    @patch("subprocess.run")
    def test_log_custom_count(self, mock_run, git_tool):
        """Test log with custom count."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.log(n=5)
        call_args = mock_run.call_args[0][0]
        assert "-5" in call_args

    @patch("subprocess.run")
    def test_log_with_graph(self, mock_run, git_tool):
        """Test log with graph option."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.log(graph=True)
        call_args = mock_run.call_args[0][0]
        assert "--graph" in call_args

    @patch("subprocess.run")
    def test_log_all_branches(self, mock_run, git_tool):
        """Test log with all branches."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.log(all_branches=True)
        call_args = mock_run.call_args[0][0]
        assert "--all" in call_args

    # branch tests
    @patch("subprocess.run")
    def test_branch_list(self, mock_run, git_tool):
        """Test branch listing."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="* main\n  feature",
            stderr="",
        )
        result = git_tool.branch()
        assert result.success is True
        assert "main" in result.output

    @patch("subprocess.run")
    def test_branch_list_all(self, mock_run, git_tool):
        """Test branch listing with all option."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.branch(list_all=True)
        call_args = mock_run.call_args[0][0]
        assert "-a" in call_args

    @patch("subprocess.run")
    def test_branch_list_remote(self, mock_run, git_tool):
        """Test branch listing with remote only."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.branch(list_remote=True)
        call_args = mock_run.call_args[0][0]
        assert "-r" in call_args

    # current_branch tests
    @patch("subprocess.run")
    def test_current_branch_success(self, mock_run, git_tool):
        """Test getting current branch."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="main\n",
            stderr="",
        )
        branch = git_tool.current_branch()
        assert branch == "main"

    @patch("subprocess.run")
    def test_current_branch_detached(self, mock_run, git_tool):
        """Test current branch when detached HEAD."""
        mock_run.return_value = MagicMock(
            returncode=128,
            stdout="",
            stderr="HEAD is not a symbolic ref",
        )
        branch = git_tool.current_branch()
        assert branch == "HEAD"

    # show tests
    @patch("subprocess.run")
    def test_show_default(self, mock_run, git_tool):
        """Test show with default options."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="commit abc1234\nAuthor: Test",
            stderr="",
        )
        result = git_tool.show()
        assert result.success is True
        call_args = mock_run.call_args[0][0]
        assert "show" in call_args
        assert "HEAD" in call_args

    @patch("subprocess.run")
    def test_show_specific_commit(self, mock_run, git_tool):
        """Test show with specific commit."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.show("abc1234")
        call_args = mock_run.call_args[0][0]
        assert "abc1234" in call_args

    @patch("subprocess.run")
    def test_show_stat(self, mock_run, git_tool):
        """Test show with stat option."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.show(stat=True)
        call_args = mock_run.call_args[0][0]
        assert "--stat" in call_args

    # push tests
    def test_push_requires_approval(self, git_tool):
        """Test push always requires approval."""
        result = git_tool.push()
        assert result.requires_approval is True
        assert result.success is False

    def test_push_with_branch(self, git_tool):
        """Test push with branch specification."""
        result = git_tool.push("origin", "main")
        assert result.requires_approval is True

    def test_push_force_blocked(self, git_tool):
        """Test force push is blocked."""
        result = git_tool.push(force=True)
        assert result.requires_approval is True
        assert "force" in result.error.lower()

    # execute_push tests
    @patch("subprocess.run")
    def test_execute_push_success(self, mock_run, git_tool):
        """Test execute_push after approval."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Everything up-to-date",
            stderr="",
        )
        result = git_tool.execute_push()
        assert result.success is True

    @patch("subprocess.run")
    def test_execute_push_with_branch(self, mock_run, git_tool):
        """Test execute_push with branch."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.execute_push("origin", "main")
        call_args = mock_run.call_args[0][0]
        assert "push" in call_args
        assert "origin" in call_args
        assert "main" in call_args

    # pull tests
    @patch("subprocess.run")
    def test_pull_success(self, mock_run, git_tool):
        """Test successful pull."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Already up to date.",
            stderr="",
        )
        result = git_tool.pull()
        assert result.success is True

    @patch("subprocess.run")
    def test_pull_with_branch(self, mock_run, git_tool):
        """Test pull with branch."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.pull("origin", "main")
        call_args = mock_run.call_args[0][0]
        assert "pull" in call_args
        assert "origin" in call_args
        assert "main" in call_args

    # fetch tests
    @patch("subprocess.run")
    def test_fetch_success(self, mock_run, git_tool):
        """Test successful fetch."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = git_tool.fetch()
        assert result.success is True

    @patch("subprocess.run")
    def test_fetch_all_remotes(self, mock_run, git_tool):
        """Test fetch all remotes."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.fetch(all_remotes=True)
        call_args = mock_run.call_args[0][0]
        assert "--all" in call_args

    @patch("subprocess.run")
    def test_fetch_prune(self, mock_run, git_tool):
        """Test fetch with prune."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.fetch(prune=True)
        call_args = mock_run.call_args[0][0]
        assert "--prune" in call_args

    # stash tests
    @patch("subprocess.run")
    def test_stash_push(self, mock_run, git_tool):
        """Test stash push."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = git_tool.stash()
        assert result.success is True
        call_args = mock_run.call_args[0][0]
        assert "stash" in call_args
        assert "push" in call_args

    @patch("subprocess.run")
    def test_stash_push_with_message(self, mock_run, git_tool):
        """Test stash push with message."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.stash(message="WIP: testing")
        call_args = mock_run.call_args[0][0]
        assert "-m" in call_args
        assert "WIP: testing" in call_args

    @patch("subprocess.run")
    def test_stash_pop(self, mock_run, git_tool):
        """Test stash pop."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.stash("pop")
        call_args = mock_run.call_args[0][0]
        assert "pop" in call_args

    @patch("subprocess.run")
    def test_stash_list(self, mock_run, git_tool):
        """Test stash list."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        git_tool.stash("list")
        call_args = mock_run.call_args[0][0]
        assert "list" in call_args

    # timeout tests
    @patch("subprocess.run")
    def test_timeout_handling(self, mock_run, git_tool):
        """Test timeout is properly handled."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=60)
        result = git_tool.status()
        assert result.success is False
        assert "timed out" in result.error.lower()

    # CalledProcessError tests
    @patch("subprocess.run")
    def test_called_process_error_handling(self, mock_run, git_tool):
        """Test CalledProcessError is properly handled."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "status"],
            output="",
            stderr="fatal error",
        )
        result = git_tool._execute("status", ["status"])
        assert result.success is False
        assert result.error is not None


# ============================================================================
# DiffFormatter Tests
# ============================================================================


class TestDiffFormatter:
    """Tests for DiffFormatter class."""

    # summarize_diff tests
    def test_summarize_diff_no_changes(self):
        """Test summarizing empty diff."""
        summary = DiffFormatter.summarize_diff("")
        assert summary == "No changes"

    def test_summarize_diff_no_changes_marker(self):
        """Test summarizing '(no changes)' marker."""
        summary = DiffFormatter.summarize_diff("(no changes)")
        assert summary == "No changes"

    def test_summarize_diff_with_changes(self):
        """Test summarizing diff with changes."""
        diff = """diff --git a/file.txt b/file.txt
index abc1234..def5678 100644
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,4 @@
 line1
+new line
-removed line
 line3"""
        summary = DiffFormatter.summarize_diff(diff)
        assert "1 file(s) changed" in summary
        assert "+1" in summary
        assert "-1" in summary

    def test_summarize_diff_multiple_files(self):
        """Test summarizing diff with multiple files."""
        diff = """diff --git a/file1.txt b/file1.txt
+new line
diff --git a/file2.txt b/file2.txt
+another line
-old line"""
        summary = DiffFormatter.summarize_diff(diff)
        assert "2 file(s) changed" in summary

    # get_changed_files tests
    def test_get_changed_files_empty(self):
        """Test getting files from empty diff."""
        files = DiffFormatter.get_changed_files("")
        assert files == []

    def test_get_changed_files_single(self):
        """Test getting single changed file."""
        diff = """diff --git a/src/main.py b/src/main.py
index abc1234..def5678 100644"""
        files = DiffFormatter.get_changed_files(diff)
        assert len(files) == 1
        assert "src/main.py" in files

    def test_get_changed_files_multiple(self):
        """Test getting multiple changed files."""
        diff = """diff --git a/file1.txt b/file1.txt
+line
diff --git a/src/app.py b/src/app.py
+line
diff --git a/tests/test_app.py b/tests/test_app.py
-line"""
        files = DiffFormatter.get_changed_files(diff)
        assert len(files) == 3
        assert "file1.txt" in files
        assert "src/app.py" in files
        assert "tests/test_app.py" in files

    # format_for_llm tests
    def test_format_for_llm_no_changes(self):
        """Test formatting empty diff."""
        formatted = DiffFormatter.format_for_llm("")
        assert formatted == "No changes detected."

    def test_format_for_llm_no_changes_marker(self):
        """Test formatting '(no changes)' marker."""
        formatted = DiffFormatter.format_for_llm("(no changes)")
        assert formatted == "No changes detected."

    def test_format_for_llm_short(self):
        """Test formatting short diff (under max_lines)."""
        diff = "line1\nline2\nline3"
        formatted = DiffFormatter.format_for_llm(diff)
        assert formatted == diff

    def test_format_for_llm_truncated(self):
        """Test formatting long diff with truncation."""
        # Create diff with more lines than max_lines
        lines = [f"line{i}" for i in range(150)]
        diff = "\n".join(lines)
        formatted = DiffFormatter.format_for_llm(diff, max_lines=50)

        # Should have truncation message
        assert "..." in formatted
        assert "more lines" in formatted
        assert "Summary:" in formatted

    def test_format_for_llm_custom_max_lines(self):
        """Test formatting with custom max_lines."""
        lines = [f"line{i}" for i in range(20)]
        diff = "\n".join(lines)
        formatted = DiffFormatter.format_for_llm(diff, max_lines=10)

        assert "10 more lines" in formatted


# ============================================================================
# @tool Wrapper Tests
# ============================================================================


class TestGetGitTools:
    """Tests for get_git_tools() factory function."""

    def test_returns_list(self):
        """Test that get_git_tools returns a list."""
        tools = get_git_tools()
        assert isinstance(tools, list)

    def test_returns_seven_tools(self):
        """Test that get_git_tools returns exactly 7 tools."""
        tools = get_git_tools()
        assert len(tools) == 7

    def test_tool_names(self):
        """Test that all expected tools are present."""
        tools = get_git_tools()
        tool_names = {t.name for t in tools}
        expected = {"git_status", "git_diff", "git_log", "git_add", "git_commit", "git_branch", "git_show"}
        assert tool_names == expected

    def test_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        tools = get_git_tools()
        for t in tools:
            assert t.description, f"Tool {t.name} has no description"


class TestGitToolWrappers:
    """Tests for @tool decorated git wrapper functions."""

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_status_success(self, mock_get_git):
        """Test git_status tool returns status output."""
        mock_git = MagicMock()
        mock_git.status.return_value = GitResult(
            operation="status",
            success=True,
            output="On branch main\nnothing to commit",
        )
        mock_get_git.return_value = mock_git

        result = git_status.invoke({})
        assert "On branch main" in result

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_status_error(self, mock_get_git):
        """Test git_status handles errors."""
        mock_get_git.side_effect = Exception("not a git repo")
        result = git_status.invoke({})
        assert "Error" in result

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_diff_no_changes(self, mock_get_git):
        """Test git_diff with no changes."""
        mock_git = MagicMock()
        mock_git.diff.return_value = GitResult(
            operation="diff",
            success=True,
            output="(no changes)",
        )
        mock_get_git.return_value = mock_git

        result = git_diff.invoke({})
        assert "(no changes)" in result

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_diff_staged(self, mock_get_git):
        """Test git_diff with staged=True."""
        mock_git = MagicMock()
        mock_git.diff.return_value = GitResult(
            operation="diff",
            success=True,
            output="+new line",
        )
        mock_get_git.return_value = mock_git

        result = git_diff.invoke({"staged": True})
        mock_git.diff.assert_called_once_with(paths=None, staged=True)

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_log_default(self, mock_get_git):
        """Test git_log with default args."""
        mock_git = MagicMock()
        mock_git.log.return_value = GitResult(
            operation="log",
            success=True,
            output="abc1234 Initial commit",
        )
        mock_get_git.return_value = mock_git

        result = git_log.invoke({})
        assert "abc1234" in result
        mock_git.log.assert_called_once_with(n=10, oneline=True)

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_add_all(self, mock_get_git):
        """Test git_add with no paths (stage all)."""
        mock_git = MagicMock()
        mock_git.add.return_value = GitResult(
            operation="add",
            success=True,
            output="Staged: all files",
        )
        mock_get_git.return_value = mock_git

        result = git_add.invoke({})
        assert "Staged" in result

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_commit_success(self, mock_get_git):
        """Test git_commit with valid message."""
        mock_git = MagicMock()
        mock_git.commit.return_value = GitResult(
            operation="commit",
            success=True,
            output="[main abc1234] feat: add feature",
        )
        mock_get_git.return_value = mock_git

        result = git_commit.invoke({"message": "feat: add feature"})
        assert "abc1234" in result

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_branch_shows_current(self, mock_get_git):
        """Test git_branch shows current branch."""
        mock_git = MagicMock()
        mock_git.current_branch.return_value = "main"
        mock_git.branch.return_value = GitResult(
            operation="branch",
            success=True,
            output="* main\n  feature",
        )
        mock_get_git.return_value = mock_git

        result = git_branch.invoke({})
        assert "Current branch: main" in result

    @patch("ag3nt_agent.git_tool._get_workspace_git")
    def test_git_show_default(self, mock_get_git):
        """Test git_show with default (HEAD)."""
        mock_git = MagicMock()
        mock_git.show.return_value = GitResult(
            operation="show",
            success=True,
            output="commit abc1234\nAuthor: Test",
        )
        mock_get_git.return_value = mock_git

        result = git_show.invoke({})
        assert "abc1234" in result
        mock_git.show.assert_called_once_with("HEAD", stat=True)

