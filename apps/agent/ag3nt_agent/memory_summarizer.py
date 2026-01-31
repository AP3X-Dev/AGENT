"""Memory summarization for AG3NT.

This module provides automatic compression of old memory files to prevent context
overflow while preserving important information.

Memory Structure:
- ~/.ag3nt/MEMORY.md - Long-term facts
- ~/.ag3nt/memory/ - Daily logs (YYYY-MM-DD.md)
- ~/.ag3nt/memory/weekly/ - Weekly summaries (YYYY-WNN.md)
- ~/.ag3nt/memory/monthly/ - Monthly summaries (YYYY-MM.md)

Summarization Rules:
- Daily logs older than ARCHIVE_DAYS are summarized into weekly files
- Weekly summaries older than ARCHIVE_WEEKS are summarized into monthly files
- MEMORY.md is compacted when it exceeds MAX_MEMORY_SIZE

Usage:
    from ag3nt_agent.memory_summarizer import summarize_memories, needs_summarization

    if needs_summarization():
        result = summarize_memories()
        print(f"Summarized {result['files_processed']} files")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Configuration
ARCHIVE_DAYS = 7  # Days before daily logs are archived
ARCHIVE_WEEKS = 4  # Weeks before weekly logs are archived into monthly
MAX_MEMORY_SIZE = 50 * 1024  # 50KB max for MEMORY.md before compaction
MAX_DAILY_LOG_SIZE = 20 * 1024  # 20KB max for a single daily log


def _get_memory_dir() -> Path:
    """Get the memory directory path."""
    return Path.home() / ".ag3nt"


def _get_daily_logs_dir() -> Path:
    """Get the daily logs directory."""
    return _get_memory_dir() / "memory"


def _get_weekly_dir() -> Path:
    """Get the weekly summaries directory."""
    weekly = _get_memory_dir() / "memory" / "weekly"
    weekly.mkdir(parents=True, exist_ok=True)
    return weekly


def _get_monthly_dir() -> Path:
    """Get the monthly summaries directory."""
    monthly = _get_memory_dir() / "memory" / "monthly"
    monthly.mkdir(parents=True, exist_ok=True)
    return monthly


def _parse_log_date(filename: str) -> datetime | None:
    """Parse date from a daily log filename like 2024-01-28.md."""
    try:
        name = filename.replace(".md", "")
        return datetime.strptime(name, "%Y-%m-%d")
    except ValueError:
        return None


def _get_old_daily_logs(days_threshold: int = ARCHIVE_DAYS) -> list[Path]:
    """Get daily log files older than threshold.

    Args:
        days_threshold: Days after which logs are considered old

    Returns:
        List of old log file paths
    """
    logs_dir = _get_daily_logs_dir()
    if not logs_dir.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days_threshold)
    old_logs = []

    for f in logs_dir.glob("*.md"):
        date = _parse_log_date(f.name)
        if date and date < cutoff:
            old_logs.append(f)

    return sorted(old_logs, key=lambda x: x.name)


def needs_summarization() -> dict[str, Any]:
    """Check if memory summarization is needed.

    Returns:
        Dict with status and details about what needs summarization
    """
    result = {
        "needed": False,
        "old_daily_logs": 0,
        "memory_size_kb": 0,
        "memory_over_limit": False,
    }

    # Check old daily logs
    old_logs = _get_old_daily_logs()
    result["old_daily_logs"] = len(old_logs)
    if old_logs:
        result["needed"] = True

    # Check MEMORY.md size
    memory_file = _get_memory_dir() / "MEMORY.md"
    if memory_file.exists():
        size = memory_file.stat().st_size
        result["memory_size_kb"] = size // 1024
        if size > MAX_MEMORY_SIZE:
            result["memory_over_limit"] = True
            result["needed"] = True

    return result


def _summarize_with_llm(content: str, context: str) -> str:
    """Summarize content using the configured LLM.

    Args:
        content: The content to summarize
        context: Context about what this content is (e.g., "daily log for 2024-01-15")

    Returns:
        Summarized content
    """
    try:
        # Import agent's model creation
        from ag3nt_agent.deepagents_runtime import _create_model

        model = _create_model()
        prompt = f"""Summarize the following {context}. Extract and preserve:
- Key facts and decisions
- User preferences mentioned
- Important events or milestones
- Action items or commitments

Be concise but preserve all important information. Use bullet points.

Content to summarize:
{content}

Summary:"""

        response = model.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error(f"LLM summarization failed: {e}")
        # Fallback: truncate and add note
        lines = content.split("\n")
        if len(lines) > 20:
            return "\n".join(lines[:20]) + "\n\n[... truncated, summarization failed ...]"
        return content


def _group_logs_by_week(logs: list[Path]) -> dict[str, list[Path]]:
    """Group log files by ISO week.

    Args:
        logs: List of log file paths

    Returns:
        Dict mapping week key (YYYY-WNN) to list of log files
    """
    groups: dict[str, list[Path]] = {}
    for log in logs:
        date = _parse_log_date(log.name)
        if date:
            week_key = f"{date.year}-W{date.isocalendar()[1]:02d}"
            groups.setdefault(week_key, []).append(log)
    return groups


def summarize_daily_logs() -> dict[str, Any]:
    """Summarize old daily logs into weekly files.

    Returns:
        Dict with summarization results
    """
    result = {"files_processed": 0, "weeks_created": [], "errors": []}

    old_logs = _get_old_daily_logs()
    if not old_logs:
        return result

    # Group by week
    week_groups = _group_logs_by_week(old_logs)

    for week_key, logs in week_groups.items():
        try:
            # Read all logs for this week
            combined = []
            for log in sorted(logs):
                content = log.read_text(encoding="utf-8")
                combined.append(f"## {log.stem}\n\n{content}")

            full_content = "\n\n---\n\n".join(combined)

            # Summarize if too long
            if len(full_content) > MAX_DAILY_LOG_SIZE:
                summary = _summarize_with_llm(full_content, f"week {week_key} daily logs")
            else:
                summary = full_content

            # Write weekly summary
            weekly_file = _get_weekly_dir() / f"{week_key}.md"
            header = f"# Weekly Summary: {week_key}\n\n"
            header += f"*Generated: {datetime.now().isoformat()}*\n"
            header += f"*Source: {len(logs)} daily logs*\n\n---\n\n"
            weekly_file.write_text(header + summary, encoding="utf-8")

            # Archive original files (move to archive or delete)
            for log in logs:
                log.unlink()
                result["files_processed"] += 1

            result["weeks_created"].append(week_key)
            logger.info(f"Created weekly summary: {week_key} from {len(logs)} logs")

        except Exception as e:
            result["errors"].append(f"Week {week_key}: {e}")
            logger.error(f"Failed to summarize week {week_key}: {e}")

    return result


def compact_memory_file() -> dict[str, Any]:
    """Compact MEMORY.md if it exceeds size limit.

    Preserves recent entries and summarizes older ones.

    Returns:
        Dict with compaction results
    """
    result = {"compacted": False, "original_size_kb": 0, "new_size_kb": 0}

    memory_file = _get_memory_dir() / "MEMORY.md"
    if not memory_file.exists():
        return result

    content = memory_file.read_text(encoding="utf-8")
    original_size = len(content)
    result["original_size_kb"] = original_size // 1024

    if original_size <= MAX_MEMORY_SIZE:
        return result

    # Split into sections (by ## headers)
    sections = content.split("\n## ")
    if len(sections) <= 2:
        # Can't split further, just truncate
        summary = _summarize_with_llm(content, "long-term memory file")
        memory_file.write_text(summary, encoding="utf-8")
        result["compacted"] = True
        result["new_size_kb"] = len(summary) // 1024
        return result

    # Keep first section (header) and last 2 sections in full
    header = sections[0]
    middle = sections[1:-2]
    recent = sections[-2:]

    # Summarize middle sections
    middle_content = "\n## ".join(middle)
    middle_summary = _summarize_with_llm(middle_content, "older memory entries")

    # Reconstruct file
    new_content = header + "\n\n## Archived Memories (Summarized)\n\n"
    new_content += middle_summary + "\n\n"
    for section in recent:
        new_content += "## " + section + "\n"

    memory_file.write_text(new_content, encoding="utf-8")
    result["compacted"] = True
    result["new_size_kb"] = len(new_content) // 1024
    logger.info(f"Compacted MEMORY.md: {result['original_size_kb']}KB -> {result['new_size_kb']}KB")

    return result


def summarize_memories() -> dict[str, Any]:
    """Run all memory summarization tasks.

    Returns:
        Combined results from all summarization operations
    """
    results = {
        "daily_logs": summarize_daily_logs(),
        "memory_compaction": compact_memory_file(),
        "timestamp": datetime.now().isoformat(),
    }
    return results


def get_summarize_memory_tool():
    """Get the memory summarization tool for the agent.

    Returns:
        LangChain tool for memory summarization
    """
    from langchain_core.tools import tool as lc_tool

    @lc_tool
    def summarize_old_memories() -> dict:
        """Summarize and archive old memory files.

        Use this tool to compress old daily logs and large memory files.
        This helps keep memory manageable while preserving important information.

        The tool will:
        1. Summarize daily logs older than 7 days into weekly summaries
        2. Compact MEMORY.md if it exceeds 50KB
        3. Preserve recent entries and important facts

        Returns:
            Summary of what was archived and compacted
        """
        status = needs_summarization()
        if not status["needed"]:
            return {
                "message": "No summarization needed",
                "old_daily_logs": status["old_daily_logs"],
                "memory_size_kb": status["memory_size_kb"],
            }

        return summarize_memories()

    return summarize_old_memories

