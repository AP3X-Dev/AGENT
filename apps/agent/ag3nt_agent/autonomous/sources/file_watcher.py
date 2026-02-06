"""
File Watcher Event Source

Monitors filesystem for changes and emits events.
"""

import asyncio
import fnmatch
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from ..event_bus import Event, EventBus, EventPriority

logger = logging.getLogger(__name__)


class FileEventType(Enum):
    """Types of file events."""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class WatchConfig:
    """Configuration for a file watcher."""
    id: str
    path: str
    patterns: list[str] = field(default_factory=lambda: ["*"])
    events: list[str] = field(default_factory=lambda: ["created", "modified", "deleted"])
    recursive: bool = True
    debounce_seconds: float = 1.0
    ignore_patterns: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "WatchConfig":
        return cls(
            id=data["id"],
            path=data["path"],
            patterns=data.get("patterns", ["*"]),
            events=data.get("events", ["created", "modified", "deleted"]),
            recursive=data.get("recursive", True),
            debounce_seconds=data.get("debounce_seconds", 1.0),
            ignore_patterns=data.get("ignore_patterns", [])
        )


@dataclass
class FileState:
    """State of a file for change detection."""
    path: Path
    mtime: float
    size: int
    exists: bool


class FileWatcher:
    """
    Monitors filesystem for changes and emits events.

    Uses polling-based change detection (cross-platform).
    Emits events when files are created, modified, or deleted.
    """

    def __init__(self, event_bus: EventBus, poll_interval: float = 1.0):
        """
        Initialize the file watcher.

        Args:
            event_bus: Event bus to publish events to
            poll_interval: Seconds between filesystem polls
        """
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self._configs: dict[str, WatchConfig] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # File state tracking
        self._file_states: dict[str, dict[str, FileState]] = {}

        # Debouncing
        self._pending_events: dict[str, tuple[datetime, Event]] = {}

    async def start(self):
        """Start watching for file changes."""
        if self._running:
            return

        self._running = True

        # Initialize file states
        for config_id, config in self._configs.items():
            self._file_states[config_id] = self._scan_directory(config)

        # Start polling task
        self._task = asyncio.create_task(self._poll_loop())

        logger.info(f"File watcher started with {len(self._configs)} watchers")

    async def stop(self):
        """Stop watching for file changes."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("File watcher stopped")

    def add_watcher(self, config: WatchConfig):
        """
        Add a directory to watch.

        Args:
            config: Watcher configuration
        """
        self._configs[config.id] = config

        # Initialize state if already running
        if self._running:
            self._file_states[config.id] = self._scan_directory(config)

        logger.info(f"Added file watcher: {config.id} ({config.path})")

    def remove_watcher(self, config_id: str) -> bool:
        """
        Remove a watcher.

        Args:
            config_id: ID of watcher to remove

        Returns:
            True if removed, False if not found
        """
        if config_id not in self._configs:
            return False

        del self._configs[config_id]
        self._file_states.pop(config_id, None)

        logger.info(f"Removed file watcher: {config_id}")
        return True

    def _scan_directory(self, config: WatchConfig) -> dict[str, FileState]:
        """Scan a directory and return file states."""
        states = {}
        path = Path(config.path)

        if not path.exists():
            return states

        # Get all matching files
        if config.recursive:
            files = path.rglob("*")
        else:
            files = path.glob("*")

        for file_path in files:
            if not file_path.is_file():
                continue

            # Check patterns
            if not self._matches_patterns(file_path, config):
                continue

            # Check ignore patterns
            if self._matches_ignore(file_path, config):
                continue

            try:
                stat = file_path.stat()
                states[str(file_path)] = FileState(
                    path=file_path,
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                    exists=True
                )
            except OSError:
                continue

        return states

    def _matches_patterns(self, path: Path, config: WatchConfig) -> bool:
        """Check if a path matches any of the configured patterns."""
        name = path.name
        for pattern in config.patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def _matches_ignore(self, path: Path, config: WatchConfig) -> bool:
        """Check if a path matches any ignore patterns."""
        name = path.name
        full_path = str(path)

        for pattern in config.ignore_patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(full_path, pattern):
                return True
        return False

    async def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._check_all_watchers()
                await self._process_pending_events()
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in file watcher: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _check_all_watchers(self):
        """Check all configured watchers for changes."""
        for config_id, config in self._configs.items():
            try:
                await self._check_watcher(config_id, config)
            except Exception as e:
                logger.error(f"Error checking watcher {config_id}: {e}")

    async def _check_watcher(self, config_id: str, config: WatchConfig):
        """Check a single watcher for changes."""
        current_states = self._scan_directory(config)
        previous_states = self._file_states.get(config_id, {})

        # Find created files
        if "created" in config.events:
            for path, state in current_states.items():
                if path not in previous_states:
                    self._queue_event(config, path, FileEventType.CREATED)

        # Find modified files
        if "modified" in config.events:
            for path, state in current_states.items():
                if path in previous_states:
                    prev = previous_states[path]
                    if state.mtime != prev.mtime or state.size != prev.size:
                        self._queue_event(config, path, FileEventType.MODIFIED)

        # Find deleted files
        if "deleted" in config.events:
            for path in previous_states:
                if path not in current_states:
                    self._queue_event(config, path, FileEventType.DELETED)

        # Update states
        self._file_states[config_id] = current_states

    def _queue_event(self, config: WatchConfig, path: str, event_type: FileEventType):
        """Queue an event for debounced emission."""
        key = f"{config.id}:{path}:{event_type.value}"

        event = Event(
            event_type="file_change",
            source=f"file_watcher:{config.id}",
            payload={
                "watcher_id": config.id,
                "path": path,
                "event_type": event_type.value,
                "watch_path": config.path
            },
            priority=EventPriority.MEDIUM
        )

        emit_at = datetime.utcnow()
        self._pending_events[key] = (emit_at, event)

    async def _process_pending_events(self):
        """Process and emit debounced events."""
        now = datetime.utcnow()
        to_emit = []
        to_remove = []

        for key, (queued_at, event) in self._pending_events.items():
            config_id = event.payload.get("watcher_id")
            config = self._configs.get(config_id)

            if not config:
                to_remove.append(key)
                continue

            # Check if debounce period has passed
            elapsed = (now - queued_at).total_seconds()
            if elapsed >= config.debounce_seconds:
                to_emit.append(event)
                to_remove.append(key)

        # Emit events
        for event in to_emit:
            await self.event_bus.publish(event)
            logger.info(
                f"File event: {event.payload['event_type']} - {event.payload['path']}"
            )

        # Clean up
        for key in to_remove:
            del self._pending_events[key]

    def get_status(self) -> dict:
        """Get watcher status."""
        return {
            "running": self._running,
            "watcher_count": len(self._configs),
            "watchers": {
                config_id: {
                    "path": config.path,
                    "patterns": config.patterns,
                    "file_count": len(self._file_states.get(config_id, {}))
                }
                for config_id, config in self._configs.items()
            }
        }
