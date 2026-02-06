"""Unit tests for validation_gates module."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ag3nt_agent.validation_gates import (
    ValidationGateRunner,
    ValidationLevel,
    ValidationResult,
)


# ------------------------------------------------------------------
# ValidationLevel enum
# ------------------------------------------------------------------


@pytest.mark.unit
class TestValidationLevel:
    def test_values(self):
        assert ValidationLevel.SYNTAX == 1
        assert ValidationLevel.UNIT_TEST == 2
        assert ValidationLevel.INTEGRATION == 3

    def test_ordering(self):
        assert ValidationLevel.SYNTAX < ValidationLevel.UNIT_TEST
        assert ValidationLevel.UNIT_TEST < ValidationLevel.INTEGRATION


# ------------------------------------------------------------------
# ValidationResult
# ------------------------------------------------------------------


@pytest.mark.unit
class TestValidationResult:
    def test_defaults(self):
        r = ValidationResult(level=1, passed=True)
        assert r.level == 1
        assert r.passed is True
        assert r.details == ""
        assert r.issues_count == 0
        assert r.fixed_count == 0

    def test_all_fields(self):
        r = ValidationResult(
            level=2, passed=False,
            details="2 tests failed", issues_count=2, fixed_count=0,
        )
        assert r.passed is False
        assert r.issues_count == 2


# ------------------------------------------------------------------
# ValidationGateRunner
# ------------------------------------------------------------------


@pytest.mark.unit
class TestValidationGateRunner:
    @pytest.fixture
    def runner(self):
        return ValidationGateRunner(workspace_root="/tmp/test")

    # -- Syntax gate --

    @pytest.mark.asyncio
    async def test_syntax_gate_no_files(self, runner):
        result = await runner.run_gate(ValidationLevel.SYNTAX, files_modified=[])
        assert result.passed is True
        assert "No files" in result.details

    @pytest.mark.asyncio
    async def test_syntax_gate_lint_not_available(self, runner):
        with patch.dict("sys.modules", {"ag3nt_agent.lint_runner": None}):
            # Force reimport failure
            runner_fresh = ValidationGateRunner()
            result = await runner_fresh._run_syntax_check(["file.py"])
            # Should handle ImportError gracefully
            assert result.level == ValidationLevel.SYNTAX

    @pytest.mark.asyncio
    async def test_syntax_gate_with_lint_results(self, runner):
        """Test syntax gate with mocked lint results."""
        mock_lint_result = MagicMock()
        mock_lint_result.error = None
        mock_lint_result.issues = []
        mock_lint_result.file = "test.py"

        with patch("ag3nt_agent.validation_gates.LintRunner", create=True) as mock_cls:
            # We need to patch the import inside the method
            mock_instance = MagicMock()
            mock_instance.lint_files = AsyncMock(return_value=[mock_lint_result])
            mock_cls.get_instance.return_value = mock_instance
            mock_cls.format_issues.return_value = ""

            with patch("ag3nt_agent.lint_runner.LintRunner", mock_cls):
                result = await runner._run_syntax_check(["test.py"])
                assert result.level == ValidationLevel.SYNTAX

    # -- Unit test gate --

    @pytest.mark.asyncio
    async def test_unit_test_gate_no_commands(self, runner):
        result = await runner.run_gate(ValidationLevel.UNIT_TEST, test_commands=[])
        assert result.passed is True
        assert "No test commands" in result.details

    @pytest.mark.asyncio
    async def test_unit_test_gate_passing(self, runner):
        """Test unit test gate with a command that succeeds."""
        with patch("asyncio.create_subprocess_shell") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"OK", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            result = await runner.run_gate(
                ValidationLevel.UNIT_TEST,
                test_commands=["echo test"],
            )
            assert result.passed is True
            assert "PASS" in result.details

    @pytest.mark.asyncio
    async def test_unit_test_gate_failing(self, runner):
        """Test unit test gate with a command that fails."""
        with patch("asyncio.create_subprocess_shell") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"FAILED", b"error output"))
            proc.returncode = 1
            mock_proc.return_value = proc

            result = await runner.run_gate(
                ValidationLevel.UNIT_TEST,
                test_commands=["pytest failing_test.py"],
            )
            assert result.passed is False
            assert result.issues_count == 1
            assert "FAIL" in result.details

    # -- Integration test gate --

    @pytest.mark.asyncio
    async def test_integration_gate_no_commands(self, runner):
        result = await runner.run_gate(ValidationLevel.INTEGRATION, test_commands=[])
        assert result.passed is True
        assert "No integration test commands" in result.details

    @pytest.mark.asyncio
    async def test_integration_gate_passing(self, runner):
        with patch("asyncio.create_subprocess_shell") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"OK", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            result = await runner.run_gate(
                ValidationLevel.INTEGRATION,
                test_commands=["npm test"],
            )
            assert result.passed is True

    # -- Unknown level --

    @pytest.mark.asyncio
    async def test_unknown_level_skipped(self, runner):
        result = await runner.run_gate(99)
        assert result.passed is True
        assert "Unknown" in result.details

    # -- Multiple commands --

    @pytest.mark.asyncio
    async def test_multiple_commands_all_pass(self, runner):
        with patch("asyncio.create_subprocess_shell") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"OK", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            result = await runner.run_gate(
                ValidationLevel.UNIT_TEST,
                test_commands=["test1", "test2", "test3"],
            )
            assert result.passed is True
            assert result.issues_count == 0

    @pytest.mark.asyncio
    async def test_multiple_commands_one_fails(self, runner):
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            if call_count == 2:
                proc.communicate = AsyncMock(return_value=(b"FAIL", b""))
                proc.returncode = 1
            else:
                proc.communicate = AsyncMock(return_value=(b"OK", b""))
                proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_shell", side_effect=side_effect):
            result = await runner.run_gate(
                ValidationLevel.UNIT_TEST,
                test_commands=["test1", "test2", "test3"],
            )
            assert result.passed is False
            assert result.issues_count == 1


# ------------------------------------------------------------------
# Format result
# ------------------------------------------------------------------


@pytest.mark.unit
class TestFormatResult:
    def test_format_passed(self):
        result = ValidationResult(level=1, passed=True, details="All good")
        text = ValidationGateRunner.format_result(result)
        assert "SYNTAX" in text
        assert "PASSED" in text

    def test_format_failed_with_issues(self):
        result = ValidationResult(
            level=2, passed=False,
            details="2 tests failed", issues_count=2,
        )
        text = ValidationGateRunner.format_result(result)
        assert "UNIT_TEST" in text
        assert "FAILED" in text
        assert "2 issue(s)" in text

    def test_format_unknown_level(self):
        result = ValidationResult(level=99, passed=True)
        text = ValidationGateRunner.format_result(result)
        assert "LEVEL_99" in text
