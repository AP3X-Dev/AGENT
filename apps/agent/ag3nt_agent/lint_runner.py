"""Lint runner for AG3NT.

Runs language-appropriate linters on files after edits and returns
diagnostics. Works alongside LSP diagnostics to provide comprehensive
code quality feedback.

Supported linters:
- Python: ruff (preferred), flake8 fallback
- TypeScript/JavaScript: eslint
- Go: golangci-lint, go vet fallback
- Rust: cargo clippy
- Ruby: rubocop
- PHP: phpstan
- CSS/SCSS: stylelint
- Shell: shellcheck
- Custom: user-configured via ~/.ag3nt/lint.yaml

Usage:
    from ag3nt_agent.lint_runner import LintRunner

    runner = LintRunner.get_instance()
    issues = await runner.lint_file("/path/to/file.py")
    summary = runner.format_issues(issues)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("ag3nt.lint")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Severity = Literal["error", "warning", "info", "hint"]


@dataclass
class LintIssue:
    """A single lint diagnostic."""

    file: str
    line: int
    column: int
    severity: Severity
    message: str
    rule: str | None = None
    source: str = ""  # linter name


@dataclass
class LintResult:
    """Result of running a linter on a file."""

    file: str
    issues: list[LintIssue] = field(default_factory=list)
    error: str | None = None
    linter: str = ""


# ---------------------------------------------------------------------------
# Linter definitions
# ---------------------------------------------------------------------------

@dataclass
class LinterConfig:
    """Configuration for a specific linter."""

    name: str
    command: list[str]  # Base command (file path appended)
    extensions: list[str]  # File extensions this linter handles
    parse_output: str  # Parser type: "json", "ruff", "eslint", "golangci", "shellcheck", "line"
    check_binary: str  # Binary to check with shutil.which
    install_hint: str = ""  # How to install
    args_before_file: list[str] = field(default_factory=list)  # Extra args before file path
    working_dir_mode: str = "file"  # "file" = file's parent, "workspace" = workspace root
    timeout: float = 30.0


# Built-in linter configurations
LINTERS: list[LinterConfig] = [
    # Python — ruff (preferred)
    LinterConfig(
        name="ruff",
        command=["ruff", "check", "--output-format=json", "--no-fix"],
        extensions=[".py", ".pyi"],
        parse_output="ruff",
        check_binary="ruff",
        install_hint="pip install ruff",
    ),
    # Python — flake8 (fallback)
    LinterConfig(
        name="flake8",
        command=["flake8", "--format=json"],
        extensions=[".py", ".pyi"],
        parse_output="flake8",
        check_binary="flake8",
        install_hint="pip install flake8",
    ),
    # TypeScript/JavaScript — eslint
    LinterConfig(
        name="eslint",
        command=["npx", "eslint", "--format=json", "--no-error-on-unmatched-pattern"],
        extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
        parse_output="eslint",
        check_binary="npx",
        install_hint="npm install eslint",
        working_dir_mode="workspace",
    ),
    # Go — golangci-lint
    LinterConfig(
        name="golangci-lint",
        command=["golangci-lint", "run", "--out-format=json"],
        extensions=[".go"],
        parse_output="golangci",
        check_binary="golangci-lint",
        install_hint="go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest",
        working_dir_mode="workspace",
    ),
    # Go — go vet (fallback)
    LinterConfig(
        name="go-vet",
        command=["go", "vet", "-json"],
        extensions=[".go"],
        parse_output="line",
        check_binary="go",
        working_dir_mode="workspace",
    ),
    # Rust — cargo clippy
    LinterConfig(
        name="clippy",
        command=["cargo", "clippy", "--message-format=json", "--quiet"],
        extensions=[".rs"],
        parse_output="cargo",
        check_binary="cargo",
        working_dir_mode="workspace",
    ),
    # Shell — shellcheck
    LinterConfig(
        name="shellcheck",
        command=["shellcheck", "--format=json"],
        extensions=[".sh", ".bash"],
        parse_output="shellcheck",
        check_binary="shellcheck",
        install_hint="apt install shellcheck / brew install shellcheck",
    ),
    # CSS/SCSS — stylelint
    LinterConfig(
        name="stylelint",
        command=["npx", "stylelint", "--formatter=json"],
        extensions=[".css", ".scss", ".less"],
        parse_output="stylelint",
        check_binary="npx",
        install_hint="npm install stylelint",
        working_dir_mode="workspace",
    ),
    # Ruby — rubocop
    LinterConfig(
        name="rubocop",
        command=["rubocop", "--format=json", "--no-color"],
        extensions=[".rb", ".rake"],
        parse_output="rubocop",
        check_binary="rubocop",
        install_hint="gem install rubocop",
    ),
    # PHP — phpstan
    LinterConfig(
        name="phpstan",
        command=["phpstan", "analyse", "--error-format=json", "--no-progress"],
        extensions=[".php"],
        parse_output="phpstan",
        check_binary="phpstan",
        install_hint="composer require --dev phpstan/phpstan",
        working_dir_mode="workspace",
    ),
]


# ---------------------------------------------------------------------------
# Output parsers
# ---------------------------------------------------------------------------

def _severity_from_int(level: int) -> Severity:
    """Convert numeric severity (1=error, 2=warning) to string."""
    if level <= 1:
        return "error"
    if level == 2:
        return "warning"
    return "info"


def _parse_ruff(output: str, file_path: str) -> list[LintIssue]:
    """Parse ruff JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    for item in data if isinstance(data, list) else []:
        issues.append(LintIssue(
            file=item.get("filename", file_path),
            line=item.get("location", {}).get("row", 0),
            column=item.get("location", {}).get("column", 0),
            severity="error" if item.get("fix") is None else "warning",
            message=item.get("message", ""),
            rule=item.get("code"),
            source="ruff",
        ))
    return issues


def _parse_flake8(output: str, file_path: str) -> list[LintIssue]:
    """Parse flake8 JSON output (or line output as fallback)."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        # Try line-by-line parsing: file:line:col: CODE message
        return _parse_line_output(output, file_path, "flake8")
    issues: list[LintIssue] = []
    # flake8 JSON format: {filename: [{col, line, message, code, ...}]}
    if isinstance(data, dict):
        for fname, items in data.items():
            for item in items if isinstance(items, list) else []:
                issues.append(LintIssue(
                    file=fname,
                    line=item.get("line_number", item.get("line", 0)),
                    column=item.get("column_number", item.get("col", 0)),
                    severity="warning" if str(item.get("code", "")).startswith("W") else "error",
                    message=item.get("text", item.get("message", "")),
                    rule=item.get("code"),
                    source="flake8",
                ))
    return issues


def _parse_eslint(output: str, file_path: str) -> list[LintIssue]:
    """Parse eslint JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    for file_result in data if isinstance(data, list) else []:
        fname = file_result.get("filePath", file_path)
        for msg in file_result.get("messages", []):
            issues.append(LintIssue(
                file=fname,
                line=msg.get("line", 0),
                column=msg.get("column", 0),
                severity=_severity_from_int(msg.get("severity", 1)),
                message=msg.get("message", ""),
                rule=msg.get("ruleId"),
                source="eslint",
            ))
    return issues


def _parse_golangci(output: str, file_path: str) -> list[LintIssue]:
    """Parse golangci-lint JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    for item in data.get("Issues", []) if isinstance(data, dict) else []:
        pos = item.get("Pos", {})
        issues.append(LintIssue(
            file=pos.get("Filename", file_path),
            line=pos.get("Line", 0),
            column=pos.get("Column", 0),
            severity=item.get("Severity", "warning"),
            message=item.get("Text", ""),
            rule=item.get("FromLinter"),
            source="golangci-lint",
        ))
    return issues


def _parse_shellcheck(output: str, file_path: str) -> list[LintIssue]:
    """Parse shellcheck JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    for item in data if isinstance(data, list) else []:
        level = item.get("level", "warning")
        severity: Severity = "error" if level == "error" else "warning" if level == "warning" else "info"
        issues.append(LintIssue(
            file=item.get("file", file_path),
            line=item.get("line", 0),
            column=item.get("column", 0),
            severity=severity,
            message=item.get("message", ""),
            rule=f"SC{item.get('code', '')}" if item.get("code") else None,
            source="shellcheck",
        ))
    return issues


def _parse_cargo(output: str, file_path: str) -> list[LintIssue]:
    """Parse cargo clippy JSON message output (one JSON object per line)."""
    issues: list[LintIssue] = []
    for line in output.strip().splitlines():
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        msg = data.get("message")
        if not msg or not isinstance(msg, dict):
            continue
        level = msg.get("level", "warning")
        severity: Severity = "error" if level == "error" else "warning"
        spans = msg.get("spans", [])
        primary = next((s for s in spans if s.get("is_primary")), spans[0] if spans else {})
        issues.append(LintIssue(
            file=primary.get("file_name", file_path),
            line=primary.get("line_start", 0),
            column=primary.get("column_start", 0),
            severity=severity,
            message=msg.get("message", ""),
            rule=msg.get("code", {}).get("code") if isinstance(msg.get("code"), dict) else None,
            source="clippy",
        ))
    return issues


def _parse_stylelint(output: str, file_path: str) -> list[LintIssue]:
    """Parse stylelint JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    for file_result in data if isinstance(data, list) else []:
        fname = file_result.get("source", file_path)
        for w in file_result.get("warnings", []):
            issues.append(LintIssue(
                file=fname,
                line=w.get("line", 0),
                column=w.get("column", 0),
                severity=w.get("severity", "warning"),
                message=w.get("text", ""),
                rule=w.get("rule"),
                source="stylelint",
            ))
    return issues


def _parse_rubocop(output: str, file_path: str) -> list[LintIssue]:
    """Parse rubocop JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    for file_result in data.get("files", []) if isinstance(data, dict) else []:
        fname = file_result.get("path", file_path)
        for offense in file_result.get("offenses", []):
            sev = offense.get("severity", "warning")
            severity: Severity = "error" if sev in ("error", "fatal") else "warning"
            loc = offense.get("location", {})
            issues.append(LintIssue(
                file=fname,
                line=loc.get("start_line", loc.get("line", 0)),
                column=loc.get("start_column", loc.get("column", 0)),
                severity=severity,
                message=offense.get("message", ""),
                rule=offense.get("cop_name"),
                source="rubocop",
            ))
    return issues


def _parse_phpstan(output: str, file_path: str) -> list[LintIssue]:
    """Parse phpstan JSON output."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    issues: list[LintIssue] = []
    file_errors = data.get("files", {}) if isinstance(data, dict) else {}
    for fname, info in file_errors.items():
        for msg in info.get("messages", []) if isinstance(info, dict) else []:
            issues.append(LintIssue(
                file=fname,
                line=msg.get("line", 0),
                column=0,
                severity="error",
                message=msg.get("message", ""),
                source="phpstan",
            ))
    return issues


def _parse_line_output(output: str, file_path: str, source: str) -> list[LintIssue]:
    """Fallback parser for file:line:col: message format."""
    import re
    issues: list[LintIssue] = []
    pattern = re.compile(r"^(.+?):(\d+):(\d+):\s*(\w+)?\s*(.+)$")
    for line in output.strip().splitlines():
        m = pattern.match(line.strip())
        if m:
            sev_str = (m.group(4) or "warning").lower()
            severity: Severity = "error" if "error" in sev_str else "warning"
            issues.append(LintIssue(
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity=severity,
                message=m.group(5).strip(),
                source=source,
            ))
    return issues


PARSERS: dict[str, Any] = {
    "ruff": _parse_ruff,
    "flake8": _parse_flake8,
    "eslint": _parse_eslint,
    "golangci": _parse_golangci,
    "shellcheck": _parse_shellcheck,
    "cargo": _parse_cargo,
    "stylelint": _parse_stylelint,
    "rubocop": _parse_rubocop,
    "phpstan": _parse_phpstan,
    "line": _parse_line_output,
}


# ---------------------------------------------------------------------------
# Lint Runner
# ---------------------------------------------------------------------------

class LintRunner:
    """Runs linters on files and returns structured diagnostics.

    Singleton. Auto-detects the appropriate linter based on file extension.
    Prefers the first available linter for each language.
    """

    _instance: LintRunner | None = None

    def __init__(self, workspace_root: str | None = None) -> None:
        self._workspace_root = workspace_root or os.getcwd()
        self._available_cache: dict[str, bool] = {}
        self._custom_commands: dict[str, list[str]] = {}
        self._load_custom_config()

    @classmethod
    def get_instance(cls, workspace_root: str | None = None) -> LintRunner:
        """Get or create the singleton LintRunner."""
        if cls._instance is None:
            cls._instance = cls(workspace_root)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def _load_custom_config(self) -> None:
        """Load custom lint config from ~/.ag3nt/lint.yaml if present."""
        config_path = Path.home() / ".ag3nt" / "lint.yaml"
        if not config_path.exists():
            return
        try:
            # Use json fallback if yaml not available
            import yaml  # type: ignore
            with open(config_path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                for ext, cmd in data.get("commands", {}).items():
                    if isinstance(cmd, list):
                        self._custom_commands[ext] = cmd
                    elif isinstance(cmd, str):
                        self._custom_commands[ext] = cmd.split()
            logger.info(f"Loaded custom lint config: {list(self._custom_commands.keys())}")
        except ImportError:
            logger.debug("yaml not available, skipping custom lint config")
        except Exception as e:
            logger.warning(f"Failed to load lint config: {e}")

    def _is_available(self, binary: str) -> bool:
        """Check if a binary is available on PATH (cached)."""
        if binary not in self._available_cache:
            self._available_cache[binary] = shutil.which(binary) is not None
        return self._available_cache[binary]

    def find_linter(self, file_path: str) -> LinterConfig | None:
        """Find the best available linter for a file."""
        ext = Path(file_path).suffix.lower()
        for linter in LINTERS:
            if ext in linter.extensions and self._is_available(linter.check_binary):
                return linter
        return None

    def find_all_linters(self, file_path: str) -> list[LinterConfig]:
        """Find all available linters for a file."""
        ext = Path(file_path).suffix.lower()
        return [l for l in LINTERS if ext in l.extensions and self._is_available(l.check_binary)]

    async def lint_file(self, file_path: str) -> LintResult:
        """Run the appropriate linter on a file.

        Args:
            file_path: Absolute path to the file to lint.

        Returns:
            LintResult with issues found, or error if linter failed.
        """
        file_path = os.path.abspath(file_path)
        ext = Path(file_path).suffix.lower()

        # Check for custom command first
        if ext in self._custom_commands:
            return await self._run_custom(file_path, ext)

        linter = self.find_linter(file_path)
        if linter is None:
            return LintResult(file=file_path, linter="none", error=None)

        return await self._run_linter(file_path, linter)

    async def lint_files(self, file_paths: list[str]) -> list[LintResult]:
        """Run linters on multiple files concurrently."""
        tasks = [self.lint_file(fp) for fp in file_paths]
        return await asyncio.gather(*tasks)

    async def _run_linter(self, file_path: str, linter: LinterConfig) -> LintResult:
        """Execute a linter and parse its output."""
        cmd = list(linter.command) + linter.args_before_file + [file_path]

        if linter.working_dir_mode == "workspace":
            cwd = self._workspace_root
        else:
            cwd = str(Path(file_path).parent)

        logger.debug(f"Running {linter.name}: {' '.join(cmd)} in {cwd}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=linter.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return LintResult(
                    file=file_path,
                    linter=linter.name,
                    error=f"Linter timed out after {linter.timeout}s",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Many linters use non-zero exit code to indicate issues found
            # (not necessarily an error in the linter itself)
            parser = PARSERS.get(linter.parse_output, _parse_line_output)
            issues = parser(stdout, file_path)

            # If no issues parsed from stdout, try stderr
            if not issues and stderr.strip() and proc.returncode not in (0, 1):
                return LintResult(
                    file=file_path,
                    linter=linter.name,
                    error=f"Linter error: {stderr[:500]}",
                )

            return LintResult(
                file=file_path,
                issues=issues,
                linter=linter.name,
            )

        except FileNotFoundError:
            self._available_cache[linter.check_binary] = False
            return LintResult(
                file=file_path,
                linter=linter.name,
                error=f"{linter.name} not found. Install with: {linter.install_hint}",
            )
        except Exception as e:
            logger.error(f"Linter {linter.name} failed: {e}")
            return LintResult(
                file=file_path,
                linter=linter.name,
                error=str(e),
            )

    async def _run_custom(self, file_path: str, ext: str) -> LintResult:
        """Run a user-configured custom lint command."""
        cmd = self._custom_commands[ext] + [file_path]
        cwd = str(Path(file_path).parent)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=30.0,
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            issues = _parse_line_output(stdout, file_path, "custom")
            return LintResult(file=file_path, issues=issues, linter="custom")
        except Exception as e:
            return LintResult(file=file_path, linter="custom", error=str(e))

    @staticmethod
    def format_issues(result: LintResult, max_issues: int = 20) -> str:
        """Format lint results as a human-readable string for tool output.

        Args:
            result: LintResult from lint_file().
            max_issues: Maximum number of issues to include.

        Returns:
            Formatted string, or empty string if no issues.
        """
        if result.error:
            return f"\n\nLint ({result.linter}): {result.error}"

        if not result.issues:
            return ""

        lines: list[str] = []
        lines.append(f"\n\nLint ({result.linter}): {len(result.issues)} issue(s)")

        error_count = sum(1 for i in result.issues if i.severity == "error")
        warn_count = sum(1 for i in result.issues if i.severity == "warning")
        if error_count or warn_count:
            parts = []
            if error_count:
                parts.append(f"{error_count} error(s)")
            if warn_count:
                parts.append(f"{warn_count} warning(s)")
            lines[0] += f" [{', '.join(parts)}]"

        for issue in result.issues[:max_issues]:
            rule_str = f" [{issue.rule}]" if issue.rule else ""
            lines.append(f"  {issue.severity} line {issue.line}: {issue.message}{rule_str}")

        remaining = len(result.issues) - max_issues
        if remaining > 0:
            lines.append(f"  ... and {remaining} more issue(s)")

        return "\n".join(lines)

    @staticmethod
    def format_multiple(results: list[LintResult], max_issues: int = 20) -> str:
        """Format multiple lint results."""
        parts = [LintRunner.format_issues(r, max_issues) for r in results]
        return "".join(p for p in parts if p)
