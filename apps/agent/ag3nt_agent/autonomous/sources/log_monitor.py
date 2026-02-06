"""
Log Monitor Event Source

Monitors log files for patterns and emits events.
"""

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..event_bus import Event, EventBus, EventPriority

logger = logging.getLogger(__name__)


@dataclass
class LogMonitorConfig:
    """Configuration for a log monitor."""
    id: str
    path: str
    patterns: list[str]
    window_seconds: int = 60
    threshold_count: int = 1
    priority: EventPriority = EventPriority.HIGH

    @classmethod
    def from_dict(cls, data: dict) -> "LogMonitorConfig":
        priority_str = data.get("priority", "HIGH")
        priority = getattr(EventPriority, priority_str.upper(), EventPriority.HIGH)

        return cls(
            id=data["id"],
            path=data["path"],
            patterns=data["patterns"],
            window_seconds=data.get("window_seconds", 60),
            threshold_count=data.get("threshold_count", 1),
            priority=priority
        )


@dataclass
class LogMatch:
    """A pattern match in a log file."""
    pattern: str
    line: str
    line_number: int
    timestamp: datetime


class LogMonitor:
    """
    Monitors log files for patterns and emits events.

    Features:
    - Tails log files for new lines
    - Pattern matching with regex support
    - Threshold-based alerting (N matches in M seconds)
    - Deduplication of repeated alerts
    """

    def __init__(self, event_bus: EventBus, poll_interval: float = 1.0):
        """
        Initialize the log monitor.

        Args:
            event_bus: Event bus to publish events to
            poll_interval: Seconds between log file polls
        """
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self._configs: dict[str, LogMonitorConfig] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # File tracking
        self._file_positions: dict[str, int] = {}

        # Match tracking for threshold detection
        self._recent_matches: dict[str, deque] = {}

        # Compiled regex patterns
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}

    async def start(self):
        """Start monitoring log files."""
        if self._running:
            return

        self._running = True

        # Initialize file positions
        for config in self._configs.values():
            self._init_file_position(config)

        # Start polling task
        self._task = asyncio.create_task(self._poll_loop())

        logger.info(f"Log monitor started with {len(self._configs)} monitors")

    async def stop(self):
        """Stop monitoring log files."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Log monitor stopped")

    def add_monitor(self, config: LogMonitorConfig):
        """
        Add a log file to monitor.

        Args:
            config: Monitor configuration
        """
        self._configs[config.id] = config

        # Compile patterns
        compiled = []
        for pattern in config.patterns:
            if pattern.startswith("regex:"):
                compiled.append(re.compile(pattern[6:]))
            else:
                compiled.append(re.compile(re.escape(pattern)))
        self._compiled_patterns[config.id] = compiled

        # Initialize match tracking
        self._recent_matches[config.id] = deque()

        # Initialize file position if running
        if self._running:
            self._init_file_position(config)

        logger.info(f"Added log monitor: {config.id} ({config.path})")

    def remove_monitor(self, config_id: str) -> bool:
        """
        Remove a log monitor.

        Args:
            config_id: ID of monitor to remove

        Returns:
            True if removed, False if not found
        """
        if config_id not in self._configs:
            return False

        config = self._configs[config_id]
        del self._configs[config_id]
        self._file_positions.pop(config.path, None)
        self._recent_matches.pop(config_id, None)
        self._compiled_patterns.pop(config_id, None)

        logger.info(f"Removed log monitor: {config_id}")
        return True

    def _init_file_position(self, config: LogMonitorConfig):
        """Initialize file position to end of file."""
        path = Path(config.path)
        if path.exists():
            self._file_positions[config.path] = path.stat().st_size
        else:
            self._file_positions[config.path] = 0

    async def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._check_all_logs()
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in log monitor: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _check_all_logs(self):
        """Check all configured log files."""
        for config in self._configs.values():
            try:
                await self._check_log(config)
            except Exception as e:
                logger.error(f"Error checking log {config.id}: {e}")

    async def _check_log(self, config: LogMonitorConfig):
        """Check a single log file for new content."""
        path = Path(config.path)

        if not path.exists():
            return

        current_size = path.stat().st_size
        last_position = self._file_positions.get(config.path, 0)

        # Handle log rotation (file got smaller)
        if current_size < last_position:
            last_position = 0

        # No new content
        if current_size == last_position:
            return

        # Read new content
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(last_position)
                new_content = f.read()
                self._file_positions[config.path] = f.tell()

        except IOError as e:
            logger.warning(f"Could not read {config.path}: {e}")
            return

        # Process new lines
        line_number = sum(1 for _ in open(path, 'r', encoding='utf-8', errors='replace'))
        lines_read = 0

        for line in new_content.splitlines():
            lines_read += 1
            await self._check_line(config, line, line_number - len(new_content.splitlines()) + lines_read)

    async def _check_line(self, config: LogMonitorConfig, line: str, line_number: int):
        """Check a single line against patterns."""
        patterns = self._compiled_patterns.get(config.id, [])

        for i, pattern in enumerate(patterns):
            if pattern.search(line):
                match = LogMatch(
                    pattern=config.patterns[i],
                    line=line,
                    line_number=line_number,
                    timestamp=datetime.utcnow()
                )

                await self._record_match(config, match)
                break  # Only match once per line

    async def _record_match(self, config: LogMonitorConfig, match: LogMatch):
        """Record a match and check threshold."""
        matches = self._recent_matches[config.id]

        # Add new match
        matches.append(match)

        # Clean old matches outside window
        cutoff = datetime.utcnow() - timedelta(seconds=config.window_seconds)
        while matches and matches[0].timestamp < cutoff:
            matches.popleft()

        # Check threshold
        if len(matches) >= config.threshold_count:
            await self._emit_event(config, list(matches))

            # Clear matches to prevent duplicate events
            matches.clear()

    async def _emit_event(self, config: LogMonitorConfig, matches: list[LogMatch]):
        """Emit a log pattern event."""
        # Build event payload
        sample_lines = [m.line for m in matches[:5]]  # First 5 matches

        event = Event(
            event_type="log_pattern",
            source=f"log_monitor:{config.id}",
            payload={
                "monitor_id": config.id,
                "path": config.path,
                "match_count": len(matches),
                "patterns_matched": list(set(m.pattern for m in matches)),
                "sample_lines": sample_lines,
                "window_seconds": config.window_seconds
            },
            priority=config.priority
        )

        await self.event_bus.publish(event)

        logger.info(
            f"Log pattern event: {config.id} - "
            f"{len(matches)} matches in {config.window_seconds}s"
        )

    def get_status(self) -> dict:
        """Get monitor status."""
        return {
            "running": self._running,
            "monitor_count": len(self._configs),
            "monitors": {
                config_id: {
                    "path": config.path,
                    "patterns": config.patterns,
                    "recent_matches": len(self._recent_matches.get(config_id, []))
                }
                for config_id, config in self._configs.items()
            }
        }
