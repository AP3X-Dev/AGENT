"""Unit tests for the file_tracker module (Sprint 2 — file staleness detection)."""

import os
import threading
import time

import pytest

from ag3nt_agent.file_tracker import (
    FileNotReadError,
    FileTracker,
    StaleFileError,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the FileTracker singleton before each test."""
    FileTracker._instance = None
    yield
    FileTracker._instance = None


@pytest.fixture()
def tracker() -> FileTracker:
    """Return a fresh FileTracker instance."""
    return FileTracker.get_instance()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileTracker:
    """Tests for the FileTracker singleton."""

    # 1 — record_read then assert_fresh succeeds
    def test_record_read_and_assert_fresh(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")

        tracker.record_read("s1", str(f))
        # Should not raise.
        tracker.assert_fresh("s1", str(f))

    # 2 — assert_fresh raises FileNotReadError when file was never read
    def test_assert_fresh_without_read(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "unread.txt"
        f.write_text("data")

        with pytest.raises(FileNotReadError):
            tracker.assert_fresh("s1", str(f))

    # 3 — modify file after read, assert_fresh raises StaleFileError
    def test_assert_fresh_stale_file(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "stale.txt"
        f.write_text("original")

        tracker.record_read("s1", str(f))

        # Ensure the mtime actually changes (some filesystems have 1-second
        # granularity, so we need a visible time difference).
        time.sleep(0.05)
        f.write_text("modified")
        # Force a different mtime by explicitly setting it.
        new_mtime = os.path.getmtime(str(f)) + 2
        os.utime(str(f), (new_mtime, new_mtime))

        with pytest.raises(StaleFileError):
            tracker.assert_fresh("s1", str(f))

    # 4 — after record_write, assert_fresh works
    def test_record_write_updates_mtime(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "written.txt"
        f.write_text("v1")

        tracker.record_read("s1", str(f))
        # Simulate an agent write: modify the file, then call record_write.
        f.write_text("v2")
        tracker.record_write("s1", str(f))

        # Should not raise — record_write updated the stored mtime.
        tracker.assert_fresh("s1", str(f))

    # 5 — is_fresh returns bool without raising
    def test_is_fresh_returns_bool(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "check.txt"
        f.write_text("data")

        # Not read yet — should be False, not raise.
        assert tracker.is_fresh("s1", str(f)) is False

        tracker.record_read("s1", str(f))
        assert tracker.is_fresh("s1", str(f)) is True

        # Make it stale.
        time.sleep(0.05)
        f.write_text("changed")
        new_mtime = os.path.getmtime(str(f)) + 2
        os.utime(str(f), (new_mtime, new_mtime))
        assert tracker.is_fresh("s1", str(f)) is False

    # 6 — invalidate removes tracking so assert_fresh raises FileNotReadError
    def test_invalidate_removes_tracking(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "inv.txt"
        f.write_text("data")

        tracker.record_read("s1", str(f))
        tracker.assert_fresh("s1", str(f))  # works

        tracker.invalidate("s1", str(f))

        with pytest.raises(FileNotReadError):
            tracker.assert_fresh("s1", str(f))

    # 7 — clear_session removes all tracking for that session
    def test_clear_session(self, tracker: FileTracker, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("a")
        f2.write_text("b")

        tracker.record_read("s1", str(f1))
        tracker.record_read("s1", str(f2))

        tracker.clear_session("s1")

        with pytest.raises(FileNotReadError):
            tracker.assert_fresh("s1", str(f1))
        with pytest.raises(FileNotReadError):
            tracker.assert_fresh("s1", str(f2))

    # 8 — acquire_write_lock provides mutual exclusion
    def test_write_lock(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "locked.txt"
        f.write_text("data")

        results: list[int] = []
        barrier = threading.Barrier(2, timeout=5)

        def writer(value: int):
            barrier.wait()
            with tracker.acquire_write_lock("s1", str(f)):
                # Simulate some work inside the critical section.
                results.append(value)
                time.sleep(0.05)
                results.append(value)

        t1 = threading.Thread(target=writer, args=(1,))
        t2 = threading.Thread(target=writer, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # With proper mutual exclusion the results should appear in pairs:
        # either [1, 1, 2, 2] or [2, 2, 1, 1] — never interleaved.
        assert len(results) == 4
        assert results[:2] == [results[0], results[0]]
        assert results[2:] == [results[2], results[2]]
        assert set(results) == {1, 2}

    # 9 — different session IDs don't interfere with each other
    def test_separate_sessions(self, tracker: FileTracker, tmp_path):
        f = tmp_path / "shared.txt"
        f.write_text("data")

        tracker.record_read("session-a", str(f))

        # session-b never read the file, so assert_fresh should fail.
        with pytest.raises(FileNotReadError):
            tracker.assert_fresh("session-b", str(f))

        # session-a should still be fine.
        tracker.assert_fresh("session-a", str(f))

        # Clearing session-a should not affect session-b's state (or lack thereof).
        tracker.record_read("session-b", str(f))
        tracker.clear_session("session-a")

        with pytest.raises(FileNotReadError):
            tracker.assert_fresh("session-a", str(f))

        # session-b is still tracked.
        tracker.assert_fresh("session-b", str(f))

    # 10 — get_instance returns the same singleton instance
    def test_singleton(self):
        inst1 = FileTracker.get_instance()
        inst2 = FileTracker.get_instance()
        assert inst1 is inst2
