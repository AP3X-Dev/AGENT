"""Pre-compaction memory flush for AG3NT.

This module implements a silent agentic turn before context compaction
to persist important insights and learnings to long-term memory.

The memory flush extracts:
- Key decisions and their rationale
- User preferences discovered
- Important facts learned
- Successful solutions to problems

Usage:
    from ag3nt_agent.memory_flush import MemoryFlusher, get_memory_flusher

    flusher = get_memory_flusher()
    if flusher.should_flush(messages, token_count):
        result = await flusher.flush(messages)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Constants
MEMORY_DIR = Path.home() / ".ag3nt"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
DAILY_LOG_DIR = MEMORY_DIR / "memory"

# Default thresholds
DEFAULT_SOFT_THRESHOLD = 80000  # Tokens before flush
DEFAULT_RESERVE_TOKENS = 20000  # Reserve for continued operation
DEFAULT_FLUSH_BUFFER = 4000  # Buffer before threshold


@dataclass
class FlushConfig:
    """Configuration for memory flush.

    Attributes:
        enabled: Whether memory flush is enabled
        soft_threshold: Token count to trigger flush consideration
        reserve_tokens: Reserve tokens for continued operation
        flush_buffer: Additional buffer before threshold
        max_insights: Maximum insights to extract per flush
        extract_decisions: Extract key decisions
        extract_preferences: Extract user preferences
        extract_facts: Extract important facts
        extract_solutions: Extract successful solutions
    """

    enabled: bool = True
    soft_threshold: int = DEFAULT_SOFT_THRESHOLD
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS
    flush_buffer: int = DEFAULT_FLUSH_BUFFER
    max_insights: int = 10
    extract_decisions: bool = True
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_solutions: bool = True


@dataclass
class FlushResult:
    """Result of a memory flush operation.

    Attributes:
        flushed: Whether flush was performed
        insights_count: Number of insights extracted
        decisions: Extracted decisions
        preferences: Extracted user preferences
        facts: Extracted facts
        solutions: Extracted solutions
        timestamp: When flush occurred
    """

    flushed: bool
    insights_count: int = 0
    decisions: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class MemoryFlusher:
    """Pre-compaction memory flush handler.

    Extracts important insights from conversation before context
    compaction to persist them to long-term memory.
    """

    def __init__(self, config: FlushConfig | None = None) -> None:
        """Initialize the memory flusher.

        Args:
            config: Flush configuration (uses defaults if not provided)
        """
        self._config = config or FlushConfig()
        self._last_flush_timestamp: datetime | None = None
        self._flush_count = 0

    @property
    def config(self) -> FlushConfig:
        """Get the flush configuration."""
        return self._config

    def should_flush(self, token_count: int) -> bool:
        """Check if memory flush should be triggered.

        Args:
            token_count: Current conversation token count

        Returns:
            True if flush should be triggered
        """
        if not self._config.enabled:
            return False

        threshold = (
            self._config.soft_threshold
            - self._config.reserve_tokens
            - self._config.flush_buffer
        )
        return token_count >= threshold

    def _extract_decisions(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract key decisions from messages."""
        decisions = []
        patterns = [
            r"(?:I'?ve|I have) decided to ([^.]+)",
            r"(?:The|A) decision (?:is|was) to ([^.]+)",
            r"(?:We|I) (?:will|should) ([^.]+) because",
            r"Based on .*?, (?:I|we) (?:will|should) ([^.]+)",
        ]

        for msg in messages:
            content = str(msg.get("content", ""))
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                decisions.extend(matches[: self._config.max_insights])

        return decisions[: self._config.max_insights]

    def _extract_preferences(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract user preferences from messages."""
        preferences = []
        patterns = [
            r"(?:User|They|He|She) prefer[s]? ([^.]+)",
            r"(?:I|We) like ([^.]+) better",
            r"(?:Always|Usually) use ([^.]+)",
            r"(?:The|My|Their) preference is ([^.]+)",
        ]

        for msg in messages:
            content = str(msg.get("content", ""))
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                preferences.extend(matches[: self._config.max_insights])

        return preferences[: self._config.max_insights]

    def _extract_facts(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract important facts from messages."""
        facts = []
        patterns = [
            r"(?:Important|Key) fact: ([^.]+)",
            r"(?:Note|Remember) that ([^.]+)",
            r"(?:The|A) fact is that ([^.]+)",
            r"(?:It'?s|It is) important to (?:know|note) that ([^.]+)",
        ]

        for msg in messages:
            content = str(msg.get("content", ""))
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                facts.extend(matches[: self._config.max_insights])

        return facts[: self._config.max_insights]

    def _extract_solutions(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract successful solutions from messages."""
        solutions = []
        patterns = [
            r"(?:The|A) solution (?:is|was) to ([^.]+)",
            r"(?:Fixed|Resolved) by ([^.]+)",
            r"(?:This|That) worked: ([^.]+)",
            r"(?:Successfully|Finally) ([^.]+)",
        ]

        for msg in messages:
            content = str(msg.get("content", ""))
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                solutions.extend(matches[: self._config.max_insights])

        return solutions[: self._config.max_insights]

    def flush(self, messages: list[dict[str, Any]]) -> FlushResult:
        """Extract and persist insights from messages.

        Args:
            messages: Conversation messages to extract from

        Returns:
            FlushResult with extracted insights
        """
        if not self._config.enabled:
            return FlushResult(flushed=False)

        # Extract insights based on configuration
        decisions = []
        preferences = []
        facts = []
        solutions = []

        if self._config.extract_decisions:
            decisions = self._extract_decisions(messages)
        if self._config.extract_preferences:
            preferences = self._extract_preferences(messages)
        if self._config.extract_facts:
            facts = self._extract_facts(messages)
        if self._config.extract_solutions:
            solutions = self._extract_solutions(messages)

        total_insights = len(decisions) + len(preferences) + len(facts) + len(solutions)

        if total_insights == 0:
            logger.debug("No insights to flush to memory")
            return FlushResult(flushed=False)

        # Write insights to daily log
        self._write_to_memory(decisions, preferences, facts, solutions)

        self._last_flush_timestamp = datetime.now()
        self._flush_count += 1

        logger.info(f"Flushed {total_insights} insights to memory")

        return FlushResult(
            flushed=True,
            insights_count=total_insights,
            decisions=decisions,
            preferences=preferences,
            facts=facts,
            solutions=solutions,
        )

    def _write_to_memory(
        self,
        decisions: list[str],
        preferences: list[str],
        facts: list[str],
        solutions: list[str],
    ) -> None:
        """Write extracted insights to daily log file."""
        DAILY_LOG_DIR.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = DAILY_LOG_DIR / f"{today}.md"

        timestamp = datetime.now().strftime("%H:%M")
        lines = [f"\n## Auto-flush at {timestamp}\n"]

        if decisions:
            lines.append("\n### Decisions\n")
            for d in decisions:
                lines.append(f"- {d}\n")

        if preferences:
            lines.append("\n### User Preferences\n")
            for p in preferences:
                lines.append(f"- {p}\n")

        if facts:
            lines.append("\n### Key Facts\n")
            for f in facts:
                lines.append(f"- {f}\n")

        if solutions:
            lines.append("\n### Solutions\n")
            for s in solutions:
                lines.append(f"- {s}\n")

        with open(log_file, "a", encoding="utf-8") as f:
            f.writelines(lines)

        logger.debug(f"Wrote insights to {log_file}")

    def get_stats(self) -> dict[str, Any]:
        """Get flush statistics.

        Returns:
            Dict with flush count and last flush timestamp
        """
        return {
            "flush_count": self._flush_count,
            "last_flush": (
                self._last_flush_timestamp.isoformat()
                if self._last_flush_timestamp
                else None
            ),
            "enabled": self._config.enabled,
        }


# Preset configurations
FLUSH_DISABLED = FlushConfig(enabled=False)
FLUSH_CONSERVATIVE = FlushConfig(
    soft_threshold=100000,
    max_insights=5,
)
FLUSH_BALANCED = FlushConfig()
FLUSH_AGGRESSIVE = FlushConfig(
    soft_threshold=60000,
    max_insights=20,
)


# Global flusher instance
_memory_flusher: MemoryFlusher | None = None


def get_memory_flusher() -> MemoryFlusher:
    """Get the global memory flusher instance.

    Returns:
        Global MemoryFlusher instance
    """
    global _memory_flusher
    if _memory_flusher is None:
        _memory_flusher = MemoryFlusher()
    return _memory_flusher


def reset_memory_flusher() -> None:
    """Reset the global memory flusher (for testing)."""
    global _memory_flusher
    _memory_flusher = None

