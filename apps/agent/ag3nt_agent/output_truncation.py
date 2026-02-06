"""Smart output truncation for AG3NT tool results.

When tool output exceeds configured thresholds, saves the full output to
disk and returns a truncated version with a pointer to the saved file.
This prevents context window waste on large outputs while preserving
full data for later inspection.

Usage:
    from ag3nt_agent.output_truncation import maybe_truncate, cleanup_old_outputs

    text, was_truncated, saved_path = maybe_truncate(output_text)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger("ag3nt.truncation")

# Defaults (can be overridden via agent_config)
_DEFAULT_MAX_LINES = 2000
_DEFAULT_MAX_BYTES = 50 * 1024  # 50KB
_DEFAULT_DIR = Path.home() / ".ag3nt" / "tool_output"


def _get_config() -> tuple[int, int, Path]:
    """Load truncation config from agent_config if available."""
    try:
        from ag3nt_agent.agent_config import (
            TRUNCATION_MAX_LINES,
            TRUNCATION_MAX_BYTES,
            TRUNCATION_DIR,
        )
        return TRUNCATION_MAX_LINES, TRUNCATION_MAX_BYTES, TRUNCATION_DIR
    except ImportError:
        return _DEFAULT_MAX_LINES, _DEFAULT_MAX_BYTES, _DEFAULT_DIR


def maybe_truncate(
    output: str,
    session_id: str | None = None,
    tool_call_id: str | None = None,
) -> tuple[str, bool, str | None]:
    """Truncate output if it exceeds configured thresholds.

    Args:
        output: The full output text.
        session_id: Optional session ID for organizing saved files.
        tool_call_id: Optional tool call ID for the filename.

    Returns:
        Tuple of (possibly_truncated_output, was_truncated, saved_file_path).
        If not truncated, returns (output, False, None).
    """
    if not output:
        return output, False, None

    max_lines, max_bytes, base_dir = _get_config()

    lines = output.splitlines(keepends=True)
    total_lines = len(lines)
    total_bytes = len(output.encode("utf-8", errors="replace"))

    needs_truncation = total_lines > max_lines or total_bytes > max_bytes

    if not needs_truncation:
        return output, False, None

    # Save full output to disk
    saved_path = _save_full_output(output, base_dir, session_id, tool_call_id)

    # Truncate: keep first portion up to limits
    truncated_lines: list[str] = []
    byte_count = 0
    for i, line in enumerate(lines):
        if i >= max_lines:
            break
        line_bytes = len(line.encode("utf-8", errors="replace"))
        if byte_count + line_bytes > max_bytes:
            break
        truncated_lines.append(line)
        byte_count += line_bytes

    kept_lines = len(truncated_lines)
    truncated_text = "".join(truncated_lines)

    note = (
        f"\n\n--- Output truncated ({total_lines} lines, "
        f"{total_bytes} bytes total). Full output saved to {saved_path}. "
        f"Use grep_tool or read_file with offset to examine specific sections. ---"
    )

    return truncated_text + note, True, str(saved_path)


def _save_full_output(
    output: str,
    base_dir: Path,
    session_id: str | None,
    tool_call_id: str | None,
) -> Path:
    """Save full output to a file on disk.

    Args:
        output: Full output text.
        base_dir: Base directory for output files.
        session_id: Optional session ID subdirectory.
        tool_call_id: Optional tool call ID for filename.

    Returns:
        Path to the saved file.
    """
    subdir = base_dir / (session_id or "default")
    subdir.mkdir(parents=True, exist_ok=True)

    filename = f"{tool_call_id or uuid.uuid4().hex[:12]}.txt"
    file_path = subdir / filename

    file_path.write_text(output, encoding="utf-8")
    logger.info("Full output saved to %s (%d bytes)", file_path, len(output))

    return file_path


def cleanup_old_outputs(max_age_hours: int = 24) -> int:
    """Delete output files older than max_age_hours.

    Args:
        max_age_hours: Maximum age in hours before deletion.

    Returns:
        Number of files deleted.
    """
    _, _, base_dir = _get_config()

    if not base_dir.exists():
        return 0

    cutoff = time.time() - (max_age_hours * 3600)
    deleted = 0

    for session_dir in base_dir.iterdir():
        if not session_dir.is_dir():
            continue

        for file_path in session_dir.iterdir():
            if not file_path.is_file():
                continue
            try:
                if file_path.stat().st_mtime < cutoff:
                    file_path.unlink()
                    deleted += 1
            except OSError:
                continue

        # Remove empty session dirs
        try:
            if session_dir.is_dir() and not any(session_dir.iterdir()):
                session_dir.rmdir()
        except OSError:
            pass

    if deleted:
        logger.info("Cleaned up %d old output files", deleted)

    return deleted
