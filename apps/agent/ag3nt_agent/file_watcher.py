"""File system watcher for AG3NT.

Monitors workspace for external file changes and notifies registered callbacks.
Uses the ``watchdog`` library for cross-platform filesystem events with per-file
debouncing so that rapid saves collapse into a single notification.

Usage:
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    watcher.start("/path/to/workspace")
    watcher.on_change(lambda path, event: print(f"{event}: {path}"))
    # ... later ...
    watcher.stop()
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable, ClassVar

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger("ag3nt.file_watcher")

# Default debounce interval in seconds
_DEFAULT_DEBOUNCE_SECONDS = 0.1

# Directories to always ignore
_IGNORE_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
    ".eggs",
    ".next",
    ".turbo",
}

ChangeCallback = Callable[[str, str], None]


class FileWatcher:
    """Singleton file-system watcher with debouncing and gitignore support.

    Watches a workspace directory for file create/modify/delete events and
    dispatches notifications to registered callbacks.  Rapid changes to the
    same file within the debounce window are collapsed into a single callback.
    """

    _instance: ClassVar[FileWatcher | None] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._observer: Observer | None = None
        self._callbacks: list[ChangeCallback] = []
        self._callbacks_lock = threading.Lock()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._debounce_lock = threading.Lock()
        self._debounce_seconds = _DEFAULT_DEBOUNCE_SECONDS
        self._workspace_path: str | None = None
        self._gitignore_spec: object | None = None  # pathspec.PathSpec

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> FileWatcher:
        """Return the singleton ``FileWatcher``, creating it if needed."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    logger.debug("FileWatcher singleton created")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Destroy the singleton (for testing)."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None
                logger.debug("FileWatcher singleton reset")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, workspace_path: str, debounce_seconds: float | None = None) -> None:
        """Start watching *workspace_path* recursively.

        If the watcher is already running for the same path, this is a no-op.
        If it's running for a different path, it is stopped first.
        """
        workspace_path = os.path.normpath(workspace_path)

        if debounce_seconds is not None:
            self._debounce_seconds = debounce_seconds

        if self._observer is not None:
            if self._workspace_path == workspace_path:
                logger.debug("FileWatcher already running for %s", workspace_path)
                return
            self.stop()

        self._workspace_path = workspace_path
        self._gitignore_spec = self._load_gitignore(workspace_path)

        handler = _WatchHandler(self)
        self._observer = Observer()
        self._observer.daemon = True
        self._observer.schedule(handler, workspace_path, recursive=True)
        self._observer.start()
        logger.info("FileWatcher started for %s", workspace_path)

    def stop(self) -> None:
        """Stop watching and cancel pending debounce timers."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("FileWatcher stopped")

        with self._debounce_lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, callback: ChangeCallback) -> None:
        """Register a callback ``(file_path, event_type) -> None``."""
        with self._callbacks_lock:
            self._callbacks.append(callback)

    def remove_callback(self, callback: ChangeCallback) -> None:
        """Unregister a previously registered callback."""
        with self._callbacks_lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Internal: event handling
    # ------------------------------------------------------------------

    def _handle_event(self, file_path: str, event_type: str) -> None:
        """Debounce and dispatch a file-change event."""
        if self._should_ignore(file_path):
            return

        with self._debounce_lock:
            existing = self._debounce_timers.get(file_path)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(
                self._debounce_seconds,
                self._dispatch,
                args=(file_path, event_type),
            )
            timer.daemon = True
            self._debounce_timers[file_path] = timer
            timer.start()

    def _dispatch(self, file_path: str, event_type: str) -> None:
        """Fire all registered callbacks for a change event."""
        with self._debounce_lock:
            self._debounce_timers.pop(file_path, None)

        with self._callbacks_lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(file_path, event_type)
            except Exception:
                logger.exception(
                    "Exception in file-watcher callback for %s (%s)",
                    file_path,
                    event_type,
                )

    # ------------------------------------------------------------------
    # Ignore logic
    # ------------------------------------------------------------------

    def _should_ignore(self, file_path: str) -> bool:
        """Return True if *file_path* should be silently ignored."""
        parts = Path(file_path).parts
        for part in parts:
            if part in _IGNORE_DIRS:
                return True

        # Check gitignore patterns
        if self._gitignore_spec is not None and self._workspace_path is not None:
            try:
                rel = os.path.relpath(file_path, self._workspace_path)
                if self._gitignore_spec.match_file(rel):  # type: ignore[union-attr]
                    return True
            except (ValueError, TypeError):
                pass

        return False

    @staticmethod
    def _load_gitignore(workspace_path: str) -> object | None:
        """Parse ``.gitignore`` in *workspace_path* using ``pathspec``."""
        gitignore = os.path.join(workspace_path, ".gitignore")
        if not os.path.isfile(gitignore):
            return None
        try:
            import pathspec

            with open(gitignore, "r", encoding="utf-8") as f:
                return pathspec.PathSpec.from_lines("gitwildmatch", f)
        except ImportError:
            logger.debug("pathspec not installed — gitignore support disabled")
            return None
        except Exception:
            logger.exception("Failed to parse .gitignore")
            return None


class _WatchHandler(FileSystemEventHandler):
    """Watchdog event handler that forwards file events to ``FileWatcher``."""

    def __init__(self, watcher: FileWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher._handle_event(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher._handle_event(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher._handle_event(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher._handle_event(event.src_path, "deleted")
            if hasattr(event, "dest_path"):
                self._watcher._handle_event(event.dest_path, "created")
