"""Tests for the exec approval system.

Covers ExecApprovalResult, SafeBinDetector, ShellPipelineAnalyzer,
and ExecApprovalEvaluator with all decision paths.
"""

from __future__ import annotations

import pytest

from ag3nt_agent.exec_approval import (
    ExecApprovalEvaluator,
    ExecApprovalResult,
    SafeBinDetector,
    ShellPipelineAnalyzer,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset the singleton between tests."""
    ExecApprovalEvaluator._instance = None
    yield
    ExecApprovalEvaluator._instance = None


# ---------------------------------------------------------------------------
# ExecApprovalResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecApprovalResult:
    """Tests for the ExecApprovalResult frozen dataclass."""

    def test_allow_result(self):
        result = ExecApprovalResult("allow", "safe command")
        assert result.decision == "allow"
        assert result.reason == "safe command"
        assert result.matched_rule is None

    def test_deny_result_with_matched_rule(self):
        result = ExecApprovalResult("deny", "dangerous", matched_rule="deny:pattern")
        assert result.decision == "deny"
        assert result.reason == "dangerous"
        assert result.matched_rule == "deny:pattern"

    def test_ask_result(self):
        result = ExecApprovalResult("ask", "needs approval", matched_rule="default")
        assert result.decision == "ask"

    def test_frozen_cannot_assign(self):
        result = ExecApprovalResult("allow", "ok")
        with pytest.raises(AttributeError):
            result.decision = "deny"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SafeBinDetector
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSafeBinDetector:
    """Tests for the SafeBinDetector class."""

    def test_safe_bins_defaults(self):
        detector = SafeBinDetector()
        for cmd in ("ls", "cat", "grep", "find", "python", "pip", "npm", "node"):
            assert detector.is_safe(cmd), f"{cmd} should be safe"

    def test_unsafe_bin(self):
        detector = SafeBinDetector()
        assert not detector.is_safe("rm")
        assert not detector.is_safe("shutdown")
        assert not detector.is_safe("reboot")

    def test_extra_safe_bins(self):
        detector = SafeBinDetector(extra_safe={"mycustomtool", "anothertool"})
        assert detector.is_safe("mycustomtool")
        assert detector.is_safe("anothertool")
        # Original safe bins still present
        assert detector.is_safe("ls")

    def test_is_safe_git_safe_subcommands(self):
        detector = SafeBinDetector()
        for subcmd in ("status", "log", "diff", "branch", "show", "blame"):
            assert detector.is_safe_git(f"git {subcmd}"), f"git {subcmd} should be safe"

    def test_is_safe_git_unsafe_subcommand(self):
        detector = SafeBinDetector()
        assert not detector.is_safe_git("git push --force")
        assert not detector.is_safe_git("git reset --hard")
        assert not detector.is_safe_git("git clean -fd")

    def test_is_safe_git_skips_flags_without_args(self):
        detector = SafeBinDetector()
        # Flags like -C take an argument, so the path is consumed as the
        # "subcommand" by the current implementation.  Only bare flags that
        # don't carry a value are truly skipped.
        # With an argument the path is interpreted as the subcommand -> False
        assert not detector.is_safe_git("git -C /some/path status")

    def test_is_safe_git_flag_only_no_subcommand(self):
        detector = SafeBinDetector()
        # All remaining parts are flags -> returns False
        assert not detector.is_safe_git("git -C")

    def test_is_safe_git_non_git_command(self):
        detector = SafeBinDetector()
        assert not detector.is_safe_git("ls -la")
        assert not detector.is_safe_git("echo hello")

    def test_is_safe_git_empty(self):
        detector = SafeBinDetector()
        assert not detector.is_safe_git("")
        assert not detector.is_safe_git("git")

    def test_check_version_flag(self):
        detector = SafeBinDetector()
        assert detector.check_version_flag("python --version")
        assert detector.check_version_flag("node -v")
        assert detector.check_version_flag("gcc -V")
        assert detector.check_version_flag("cargo --help")
        assert detector.check_version_flag("rustc -h")

    def test_check_version_flag_too_many_parts(self):
        detector = SafeBinDetector()
        assert not detector.check_version_flag("python --version --extra")
        assert not detector.check_version_flag("python -v something")

    def test_check_version_flag_single_word(self):
        detector = SafeBinDetector()
        assert not detector.check_version_flag("python")

    def test_check_version_flag_wrong_flag(self):
        detector = SafeBinDetector()
        assert not detector.check_version_flag("python --foo")


# ---------------------------------------------------------------------------
# ShellPipelineAnalyzer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShellPipelineAnalyzer:
    """Tests for the ShellPipelineAnalyzer classmethod utilities."""

    def test_analyze_simple_command(self):
        result = ShellPipelineAnalyzer.analyze("ls -la")
        assert result == ["ls -la"]

    def test_analyze_pipe(self):
        result = ShellPipelineAnalyzer.analyze("grep foo | sort | uniq")
        assert result == ["grep foo", "sort", "uniq"]

    def test_analyze_chain_and(self):
        result = ShellPipelineAnalyzer.analyze("cd /tmp && ls")
        assert result == ["cd /tmp", "ls"]

    def test_analyze_chain_or(self):
        result = ShellPipelineAnalyzer.analyze("test -f foo || echo missing")
        assert result == ["test -f foo", "echo missing"]

    def test_analyze_semicolon(self):
        result = ShellPipelineAnalyzer.analyze("echo a; echo b")
        assert result == ["echo a", "echo b"]

    def test_analyze_mixed_chains_and_pipes(self):
        result = ShellPipelineAnalyzer.analyze("cat file | grep err && echo done")
        assert result == ["cat file", "grep err", "echo done"]

    def test_has_chains_true(self):
        assert ShellPipelineAnalyzer.has_chains("a && b")
        assert ShellPipelineAnalyzer.has_chains("a || b")
        assert ShellPipelineAnalyzer.has_chains("a ; b")

    def test_has_chains_false(self):
        assert not ShellPipelineAnalyzer.has_chains("ls -la")
        assert not ShellPipelineAnalyzer.has_chains("grep foo | sort")

    def test_extract_base_command_simple(self):
        assert ShellPipelineAnalyzer.extract_base_command("ls -la") == "ls"

    def test_extract_base_command_path(self):
        assert ShellPipelineAnalyzer.extract_base_command("/usr/bin/ls -la") == "ls"

    def test_extract_base_command_windows_path(self):
        assert ShellPipelineAnalyzer.extract_base_command("C:\\Windows\\cmd.exe /c") == "cmd.exe"

    def test_extract_base_command_env_prefix(self):
        assert ShellPipelineAnalyzer.extract_base_command("env FOO=bar python script.py") == "python"

    def test_extract_base_command_empty(self):
        assert ShellPipelineAnalyzer.extract_base_command("") == ""
        assert ShellPipelineAnalyzer.extract_base_command("   ") == ""


# ---------------------------------------------------------------------------
# ExecApprovalEvaluator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecApprovalEvaluator:
    """Tests for the ExecApprovalEvaluator with all decision paths."""

    def _make_evaluator(self, ask_mode: str = "auto") -> ExecApprovalEvaluator:
        """Create an evaluator with no config file."""
        return ExecApprovalEvaluator(
            config_path="/nonexistent/path/exec_policy.yaml",
            ask_mode=ask_mode,
        )

    # -- Empty command -> deny -----------------------------------------------

    def test_empty_command_deny(self):
        ev = self._make_evaluator()
        result = ev.evaluate("")
        assert result.decision == "deny"
        assert "Empty" in result.reason

    def test_whitespace_command_deny(self):
        ev = self._make_evaluator()
        result = ev.evaluate("   ")
        assert result.decision == "deny"

    # -- Deny patterns -------------------------------------------------------

    def test_deny_rm_rf(self):
        ev = self._make_evaluator()
        result = ev.evaluate("rm -rf /")
        assert result.decision == "deny"
        assert "Recursive force delete" in result.reason

    def test_deny_mkfs(self):
        ev = self._make_evaluator()
        result = ev.evaluate("mkfs.ext4 /dev/sda1")
        assert result.decision == "deny"
        assert "Filesystem format" in result.reason

    def test_deny_dd(self):
        ev = self._make_evaluator()
        result = ev.evaluate("dd if=/dev/zero of=/dev/sda")
        assert result.decision == "deny"
        assert "Disk overwrite" in result.reason

    def test_deny_fork_bomb(self):
        ev = self._make_evaluator()
        result = ev.evaluate(":() { :|:& };:")
        assert result.decision == "deny"
        assert "Fork bomb" in result.reason

    def test_deny_sudo_rm(self):
        ev = self._make_evaluator()
        result = ev.evaluate("sudo rm /etc/passwd")
        assert result.decision == "deny"
        assert "Sudo rm" in result.reason

    def test_deny_chmod_777_root(self):
        ev = self._make_evaluator()
        result = ev.evaluate("chmod 777 /")
        assert result.decision == "deny"
        assert "Dangerous chmod" in result.reason

    def test_deny_has_matched_rule(self):
        ev = self._make_evaluator()
        result = ev.evaluate("rm -rf /")
        assert result.matched_rule is not None
        assert result.matched_rule.startswith("deny:")

    # -- Deny patterns still checked even in never mode ---------------------

    def test_deny_overrides_never_mode(self):
        ev = self._make_evaluator(ask_mode="never")
        result = ev.evaluate("rm -rf /")
        assert result.decision == "deny"

    # -- ask_mode == "never" -> allow ----------------------------------------

    def test_never_mode_allows(self):
        ev = self._make_evaluator(ask_mode="never")
        result = ev.evaluate("some_unknown_command --flag")
        assert result.decision == "allow"
        assert result.matched_rule == "mode:never"

    # -- ask_mode == "always" -> ask -----------------------------------------

    def test_always_mode_asks(self):
        ev = self._make_evaluator(ask_mode="always")
        result = ev.evaluate("ls -la")
        assert result.decision == "ask"
        assert result.matched_rule == "mode:always"

    def test_always_mode_deny_still_wins(self):
        ev = self._make_evaluator(ask_mode="always")
        result = ev.evaluate("rm -rf /")
        assert result.decision == "deny"

    # -- Safe bins -> allow --------------------------------------------------

    def test_safe_single_command(self):
        ev = self._make_evaluator()
        result = ev.evaluate("ls -la")
        assert result.decision == "allow"
        assert result.matched_rule == "safe_bins"

    def test_safe_pipeline(self):
        ev = self._make_evaluator()
        result = ev.evaluate("cat file.txt | grep error | sort | uniq")
        assert result.decision == "allow"
        assert result.matched_rule == "safe_bins"

    def test_safe_chained(self):
        ev = self._make_evaluator()
        result = ev.evaluate("ls -la && cat README.md")
        assert result.decision == "allow"

    def test_safe_git_status(self):
        ev = self._make_evaluator()
        result = ev.evaluate("git status")
        assert result.decision == "allow"

    def test_safe_git_log(self):
        ev = self._make_evaluator()
        result = ev.evaluate("git log --oneline -10")
        assert result.decision == "allow"

    def test_safe_version_check(self):
        ev = self._make_evaluator()
        result = ev.evaluate("python --version")
        assert result.decision == "allow"

    def test_safe_help_flag(self):
        ev = self._make_evaluator()
        result = ev.evaluate("cargo --help")
        assert result.decision == "allow"

    def test_safe_command_with_path(self):
        ev = self._make_evaluator()
        result = ev.evaluate("/usr/bin/cat /etc/hostname")
        assert result.decision == "allow"

    # -- Unsafe / unknown -> ask (default) -----------------------------------

    def test_unknown_command_ask(self):
        ev = self._make_evaluator()
        result = ev.evaluate("some_random_binary --do-stuff")
        assert result.decision == "ask"
        assert result.matched_rule == "default"

    def test_unsafe_git_push_ask(self):
        ev = self._make_evaluator()
        result = ev.evaluate("git push origin main")
        assert result.decision == "ask"

    def test_mixed_safe_unsafe_pipeline_ask(self):
        ev = self._make_evaluator()
        result = ev.evaluate("cat file.txt | unknown_filter | sort")
        assert result.decision == "ask"

    # -- Singleton -----------------------------------------------------------

    def test_get_instance_singleton(self):
        inst1 = ExecApprovalEvaluator.get_instance()
        inst2 = ExecApprovalEvaluator.get_instance()
        assert inst1 is inst2

    # -- env prefix handling -------------------------------------------------

    def test_env_prefix_safe_command(self):
        ev = self._make_evaluator()
        result = ev.evaluate("env PYTHONPATH=/x python script.py")
        assert result.decision == "allow"
