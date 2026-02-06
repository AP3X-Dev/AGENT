"""Post-edit diagnostics hook for AG3NT.

After every file edit or write, this hook:
1. Notifies the LSP server of the file change
2. Collects LSP diagnostics (type errors, etc.)
3. Runs the appropriate linter (ruff, eslint, etc.)
4. Formats and returns combined diagnostics for the agent

This is the glue between the filesystem middleware and the LSP/lint systems.

Usage:
    from ag3nt_agent.post_edit_hook import get_post_edit_diagnostics

    # After a successful edit/write:
    diagnostics_text = await get_post_edit_diagnostics("/path/to/file.py", content)
    # Append diagnostics_text to the tool result message
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("ag3nt.post_edit")

# Maximum time to wait for combined diagnostics
_DIAGNOSTICS_TIMEOUT = 5.0


async def _get_lsp_diagnostics(file_path: str, content: str) -> str:
    """Get LSP diagnostics for a file after edit."""
    try:
        from ag3nt_agent.lsp.manager import LspManager

        manager = LspManager.get_instance()
        await manager.notify_file_changed(file_path, content)
        diagnostics = await manager.get_file_diagnostics(file_path, timeout=3.0)

        if not diagnostics:
            return ""

        return manager.format_diagnostics(diagnostics)
    except ImportError:
        logger.debug("LSP not available")
        return ""
    except Exception as e:
        logger.debug(f"LSP diagnostics failed: {e}")
        return ""


async def _get_lint_diagnostics(file_path: str) -> str:
    """Get linter diagnostics for a file after edit."""
    try:
        from ag3nt_agent.lint_runner import LintRunner

        runner = LintRunner.get_instance()
        result = await runner.lint_file(file_path)
        return LintRunner.format_issues(result)
    except ImportError:
        logger.debug("Lint runner not available")
        return ""
    except Exception as e:
        logger.debug(f"Lint diagnostics failed: {e}")
        return ""


async def get_post_edit_diagnostics(
    file_path: str,
    content: str | None = None,
    timeout: float = _DIAGNOSTICS_TIMEOUT,
) -> str:
    """Get combined LSP + lint diagnostics for a file after editing.

    This is the main entry point called after every edit_file or write_file.
    It runs LSP and lint checks concurrently and returns a formatted string
    to append to the tool result.

    Args:
        file_path: Absolute path to the edited file.
        content: New file content (used to notify LSP). If None, reads from disk.
        timeout: Maximum time to wait for all diagnostics.

    Returns:
        Formatted diagnostics string to append to tool result.
        Empty string if no issues found or diagnostics unavailable.
    """
    file_path = os.path.abspath(file_path)

    # Read content from disk if not provided
    if content is None:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            content = ""

    try:
        # Run LSP and lint concurrently
        lsp_task = asyncio.create_task(_get_lsp_diagnostics(file_path, content))
        lint_task = asyncio.create_task(_get_lint_diagnostics(file_path))

        done, pending = await asyncio.wait(
            [lsp_task, lint_task],
            timeout=timeout,
        )

        # Cancel any pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # Collect results
        parts: list[str] = []
        for task in done:
            try:
                result = task.result()
                if result:
                    parts.append(result)
            except Exception as e:
                logger.debug(f"Diagnostics task failed: {e}")

        return "".join(parts)

    except Exception as e:
        logger.debug(f"Post-edit diagnostics failed: {e}")
        return ""


def get_post_edit_diagnostics_sync(
    file_path: str,
    content: str | None = None,
    timeout: float = _DIAGNOSTICS_TIMEOUT,
) -> str:
    """Synchronous wrapper for get_post_edit_diagnostics.

    Tries to use the running event loop, falls back to asyncio.run().
    """
    try:
        loop = asyncio.get_running_loop()
        # We're inside an async context — schedule as a task
        future = asyncio.ensure_future(
            get_post_edit_diagnostics(file_path, content, timeout)
        )
        # Can't block here — return empty and let it run in background
        # This path shouldn't normally be hit since our tools are async
        return ""
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        try:
            return asyncio.run(
                get_post_edit_diagnostics(file_path, content, timeout)
            )
        except Exception:
            return ""


def hook_into_edit_result(
    original_message: str,
    file_path: str,
    content: str | None = None,
) -> str:
    """Enhance an edit/write result message with diagnostics.

    Call this after a successful edit or write to append diagnostics
    to the result message.

    Args:
        original_message: The original success message from the edit/write tool.
        file_path: Path to the edited file.
        content: New file content.

    Returns:
        Enhanced message with diagnostics appended, or original if no issues.
    """
    diagnostics = get_post_edit_diagnostics_sync(file_path, content)
    if diagnostics:
        return original_message + diagnostics
    return original_message
