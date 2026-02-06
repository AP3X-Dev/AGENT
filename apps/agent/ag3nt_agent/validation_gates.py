"""Validation gates for blueprint task execution.

Runs automated checks between tasks during blueprint execution:
- Level 1 (SYNTAX): Lint/format checks via ``LintRunner``
- Level 2 (UNIT_TEST): Unit test commands via subprocess
- Level 3 (INTEGRATION): Integration test commands via subprocess

Usage:
    from ag3nt_agent.validation_gates import ValidationGateRunner, ValidationLevel

    runner = ValidationGateRunner()
    result = await runner.run_gate(
        ValidationLevel.SYNTAX,
        files_modified=["src/auth.py"],
    )
    print(runner.format_result(result))
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("ag3nt.validation_gates")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ValidationLevel(IntEnum):
    """Validation gate severity levels."""

    SYNTAX = 1
    UNIT_TEST = 2
    INTEGRATION = 3


@dataclass
class ValidationResult:
    """Outcome of a validation gate run."""

    level: int
    passed: bool
    details: str = ""
    issues_count: int = 0
    fixed_count: int = 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_DEFAULT_UNIT_TIMEOUT = 60.0
_DEFAULT_INTEGRATION_TIMEOUT = 120.0


class ValidationGateRunner:
    """Run validation gates between blueprint tasks.

    Args:
        workspace_root: Root directory for running commands.
    """

    def __init__(self, workspace_root: str | None = None):
        self._workspace_root = workspace_root

    async def run_gate(
        self,
        level: ValidationLevel | int,
        files_modified: list[str] | None = None,
        test_commands: list[str] | None = None,
    ) -> ValidationResult:
        """Run a validation gate.

        Args:
            level: Gate level (SYNTAX, UNIT_TEST, INTEGRATION).
            files_modified: List of files that were changed.
            test_commands: Custom test commands to run.

        Returns:
            ``ValidationResult`` with outcome.
        """
        level_val = int(level)

        if level_val == ValidationLevel.SYNTAX:
            return await self._run_syntax_check(files_modified or [])
        elif level_val == ValidationLevel.UNIT_TEST:
            return await self._run_unit_tests(test_commands or [])
        elif level_val == ValidationLevel.INTEGRATION:
            return await self._run_integration_tests(test_commands or [])
        else:
            return ValidationResult(
                level=level_val, passed=True,
                details=f"Unknown validation level {level_val}, skipping.",
            )

    # -- Level 1: Syntax/Lint -----------------------------------------------

    async def _run_syntax_check(self, files: list[str]) -> ValidationResult:
        """Run lint checks on modified files."""
        if not files:
            return ValidationResult(
                level=ValidationLevel.SYNTAX, passed=True,
                details="No files to check.",
            )

        try:
            from ag3nt_agent.lint_runner import LintRunner

            runner = LintRunner.get_instance(self._workspace_root)
            results = await runner.lint_files(files)

            total_issues = 0
            error_count = 0
            details_parts: list[str] = []

            for result in results:
                if result.error:
                    details_parts.append(f"{result.file}: {result.error}")
                    continue
                for issue in result.issues:
                    total_issues += 1
                    if issue.severity == "error":
                        error_count += 1

                formatted = LintRunner.format_issues(result)
                if formatted:
                    details_parts.append(formatted)

            passed = error_count == 0
            return ValidationResult(
                level=ValidationLevel.SYNTAX,
                passed=passed,
                details="\n".join(details_parts) if details_parts else "All checks passed.",
                issues_count=total_issues,
            )
        except ImportError:
            logger.debug("LintRunner not available, skipping syntax gate")
            return ValidationResult(
                level=ValidationLevel.SYNTAX, passed=True,
                details="Lint runner not available, gate skipped.",
            )
        except Exception as exc:
            logger.warning("Syntax check failed: %s", exc)
            return ValidationResult(
                level=ValidationLevel.SYNTAX, passed=False,
                details=f"Syntax check error: {exc}",
            )

    # -- Level 2: Unit Tests -------------------------------------------------

    async def _run_unit_tests(self, test_commands: list[str]) -> ValidationResult:
        """Run unit test commands."""
        if not test_commands:
            return ValidationResult(
                level=ValidationLevel.UNIT_TEST, passed=True,
                details="No test commands configured, gate skipped.",
            )
        return await self._run_test_commands(
            test_commands,
            level=ValidationLevel.UNIT_TEST,
            timeout=_DEFAULT_UNIT_TIMEOUT,
        )

    # -- Level 3: Integration Tests ------------------------------------------

    async def _run_integration_tests(self, test_commands: list[str]) -> ValidationResult:
        """Run integration test commands."""
        if not test_commands:
            return ValidationResult(
                level=ValidationLevel.INTEGRATION, passed=True,
                details="No integration test commands configured, gate skipped.",
            )
        return await self._run_test_commands(
            test_commands,
            level=ValidationLevel.INTEGRATION,
            timeout=_DEFAULT_INTEGRATION_TIMEOUT,
        )

    # -- Shared test runner --------------------------------------------------

    async def _run_test_commands(
        self,
        commands: list[str],
        level: ValidationLevel,
        timeout: float,
    ) -> ValidationResult:
        """Run a list of test commands and aggregate results."""
        all_passed = True
        details_parts: list[str] = []
        total_issues = 0

        for cmd in commands:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self._workspace_root,
                )
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    all_passed = False
                    total_issues += 1
                    details_parts.append(f"TIMEOUT ({timeout}s): {cmd}")
                    continue

                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                returncode = proc.returncode

                if returncode != 0:
                    all_passed = False
                    total_issues += 1
                    output = (stdout + "\n" + stderr).strip()
                    # Truncate long output
                    if len(output) > 2000:
                        output = output[:2000] + "\n... (truncated)"
                    details_parts.append(f"FAIL (exit {returncode}): {cmd}\n{output}")
                else:
                    details_parts.append(f"PASS: {cmd}")

            except Exception as exc:
                all_passed = False
                total_issues += 1
                details_parts.append(f"ERROR: {cmd} — {exc}")

        return ValidationResult(
            level=level,
            passed=all_passed,
            details="\n".join(details_parts),
            issues_count=total_issues,
        )

    # -- Formatting ----------------------------------------------------------

    @staticmethod
    def format_result(result: ValidationResult) -> str:
        """Format a validation result as human-readable text."""
        try:
            level_name = ValidationLevel(result.level).name
        except ValueError:
            level_name = f"LEVEL_{result.level}"

        status = "PASSED" if result.passed else "FAILED"
        header = f"Validation Gate [{level_name}]: {status}"

        if result.issues_count:
            header += f" ({result.issues_count} issue(s))"

        parts = [header]
        if result.details:
            parts.append(result.details)
        return "\n".join(parts)
