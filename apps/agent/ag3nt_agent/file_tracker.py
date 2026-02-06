"""File staleness detection for AG3NT.

Tracks file read/write timestamps per session to prevent editing stale files.
If a file has been modified on disk since the agent last read it, edits are
blocked with a helpful error message telling the agent to re-read the file.

Usage:
    from ag3nt_agent.file_tracker import FileTracker

    tracker = FileTracker.get_instance()
    tracker.record_read("session-1", "/path/to/file.py")
    # ... later ...
    tracker.assert_fresh("session-1", "/path/to/file.py")  # raises if file changed on disk
    tracker.record_write("session-1", "/path/to/file.py")
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

logger = logging.getLogger("ag3nt.file_tracker")


class FileNotReadError(Exception):
    """Raised when an edit is attempted on a file that was never read in the session."""

    pass


class StaleFileError(Exception):
    """Raised when an edit is attempted on a file modified externally since last read."""

    pass


@dataclass
class FileRecord:
    """Tracks the read/write state of a single file within a session."""

    read_at: float  # time.time() when read
    mtime_at_read: float  # os.path.getmtime() when read
    written_at: float | None = None  # time.time() when last written


class FileTracker:
    """Singleton that tracks file read/write timestamps per session.

    Prevents editing files that have been modified externally since the agent
    last read them, avoiding silent data corruption.
    """

    _instance: FileTracker | None = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._tracking: dict[str, dict[str, FileRecord]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> FileTracker:
        """Return the singleton FileTracker instance, creating it if necessary."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    logger.debug("FileTracker singleton created")
        return cls._instance

    def record_read(self, session_id: str, file_path: str) -> None:
        """Record that the agent read a file, storing its current mtime.

        Args:
            session_id: The current session identifier.
            file_path: Absolute path to the file that was read.
        """
        file_path = os.path.normpath(file_path)
        mtime = os.path.getmtime(file_path)
        now = time.time()

        if session_id not in self._tracking:
            self._tracking[session_id] = {}

        self._tracking[session_id][file_path] = FileRecord(
            read_at=now,
            mtime_at_read=mtime,
        )
        logger.debug(
            "Recorded read: session=%s file=%s mtime=%f",
            session_id,
            file_path,
            mtime,
        )

    def record_write(self, session_id: str, file_path: str) -> None:
        """Record that the agent wrote/edited a file, updating the stored mtime.

        Args:
            session_id: The current session identifier.
            file_path: Absolute path to the file that was written.
        """
        file_path = os.path.normpath(file_path)
        mtime = os.path.getmtime(file_path)
        now = time.time()

        if session_id not in self._tracking:
            self._tracking[session_id] = {}

        record = self._tracking[session_id].get(file_path)
        if record is not None:
            record.mtime_at_read = mtime
            record.written_at = now
        else:
            self._tracking[session_id][file_path] = FileRecord(
                read_at=now,
                mtime_at_read=mtime,
                written_at=now,
            )

        logger.debug(
            "Recorded write: session=%s file=%s mtime=%f",
            session_id,
            file_path,
            mtime,
        )

    def assert_fresh(self, session_id: str, file_path: str) -> None:
        """Assert that a file has not been modified externally since last read.

        Must be called before editing a file. Raises if the file was never read
        in this session or if it has been modified on disk since the last read.

        Args:
            session_id: The current session identifier.
            file_path: Absolute path to the file to check.

        Raises:
            FileNotReadError: If the file was never read in this session.
            StaleFileError: If the file was modified externally since last read.
        """
        file_path = os.path.normpath(file_path)

        session_files = self._tracking.get(session_id)
        if session_files is None or file_path not in session_files:
            raise FileNotReadError(
                f"File '{file_path}' has not been read in this session. "
                "You must read a file before editing it."
            )

        record = session_files[file_path]
        current_mtime = os.path.getmtime(file_path)

        if current_mtime != record.mtime_at_read:
            raise StaleFileError(
                f"File '{file_path}' was modified externally since you last "
                f"read it (read at {record.read_at}, modified at "
                f"{current_mtime}). Read it again before editing."
            )

        logger.debug(
            "File is fresh: session=%s file=%s",
            session_id,
            file_path,
        )

    def is_fresh(self, session_id: str, file_path: str) -> bool:
        """Check whether a file is fresh without raising exceptions.

        Args:
            session_id: The current session identifier.
            file_path: Absolute path to the file to check.

        Returns:
            True if the file has been read and has not been modified externally
            since the last read; False otherwise.
        """
        try:
            self.assert_fresh(session_id, file_path)
            return True
        except (FileNotReadError, StaleFileError):
            return False

    def invalidate(self, session_id: str, file_path: str) -> None:
        """Remove tracking for a specific file in a session.

        Useful when a file watcher detects an external change and the cached
        record should be discarded.

        Args:
            session_id: The current session identifier.
            file_path: Absolute path to the file to invalidate.
        """
        file_path = os.path.normpath(file_path)
        session_files = self._tracking.get(session_id)
        if session_files is not None and file_path in session_files:
            del session_files[file_path]
            logger.debug(
                "Invalidated tracking: session=%s file=%s",
                session_id,
                file_path,
            )

    def invalidate_all_sessions(self, file_path: str) -> None:
        """Remove tracking for a file across ALL sessions.

        Called by the file watcher when an external change is detected and
        the watcher doesn't know which session triggered the change.

        Args:
            file_path: Absolute path to the file to invalidate everywhere.
        """
        file_path = os.path.normpath(file_path)
        for session_id in list(self._tracking.keys()):
            session_files = self._tracking.get(session_id)
            if session_files is not None and file_path in session_files:
                del session_files[file_path]
                logger.debug(
                    "Invalidated tracking (all sessions): session=%s file=%s",
                    session_id,
                    file_path,
                )

    def clear_session(self, session_id: str) -> None:
        """Remove all file tracking for a session.

        Args:
            session_id: The session identifier to clear.
        """
        if session_id in self._tracking:
            del self._tracking[session_id]
            logger.debug("Cleared session tracking: session=%s", session_id)

    @contextmanager
    def acquire_write_lock(
        self, session_id: str, file_path: str
    ) -> Iterator[None]:
        """Context manager that acquires a per-file lock to prevent concurrent edits.

        Locks are global (not session-scoped) so that two sessions cannot
        concurrently write to the same file.

        Args:
            session_id: The current session identifier (for logging).
            file_path: Absolute path to the file to lock.

        Yields:
            None once the lock is acquired.
        """
        file_path = os.path.normpath(file_path)

        with self._meta_lock:
            if file_path not in self._locks:
                self._locks[file_path] = threading.Lock()
            lock = self._locks[file_path]

        logger.debug(
            "Acquiring write lock: session=%s file=%s",
            session_id,
            file_path,
        )
        lock.acquire()
        try:
            logger.debug(
                "Write lock acquired: session=%s file=%s",
                session_id,
                file_path,
            )
            yield
        finally:
            lock.release()
            logger.debug(
                "Write lock released: session=%s file=%s",
                session_id,
                file_path,
            )
