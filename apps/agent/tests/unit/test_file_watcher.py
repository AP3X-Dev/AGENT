"""Unit tests for the FileWatcher singleton."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure a clean FileWatcher singleton for every test."""
    from ag3nt_agent.file_watcher import FileWatcher

    FileWatcher.reset_instance()
    yield
    FileWatcher.reset_instance()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ------------------------------------------------------------------
# Singleton tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_singleton_returns_same_instance():
    from ag3nt_agent.file_watcher import FileWatcher

    a = FileWatcher.get_instance()
    b = FileWatcher.get_instance()
    assert a is b


@pytest.mark.unit
def test_reset_instance_clears_singleton():
    from ag3nt_agent.file_watcher import FileWatcher

    inst = FileWatcher.get_instance()
    FileWatcher.reset_instance()
    assert FileWatcher._instance is None
    new_inst = FileWatcher.get_instance()
    assert new_inst is not inst


@pytest.mark.unit
def test_singleton_thread_safety():
    from ag3nt_agent.file_watcher import FileWatcher

    instances: list[FileWatcher] = []
    barrier = threading.Barrier(4)

    def get():
        barrier.wait()
        instances.append(FileWatcher.get_instance())

    threads = [threading.Thread(target=get) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(id(i) for i in instances)) == 1


# ------------------------------------------------------------------
# Lifecycle tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_start_and_stop(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    watcher.start(str(workspace))
    assert watcher.is_running
    watcher.stop()
    assert not watcher.is_running


@pytest.mark.unit
def test_start_same_path_is_noop(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    watcher.start(str(workspace))
    observer1 = watcher._observer
    watcher.start(str(workspace))
    assert watcher._observer is observer1  # same observer reused
    watcher.stop()


@pytest.mark.unit
def test_start_different_path_restarts(workspace: Path, tmp_path: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    ws2 = tmp_path / "workspace2"
    ws2.mkdir()

    watcher = FileWatcher.get_instance()
    watcher.start(str(workspace))
    observer1 = watcher._observer
    watcher.start(str(ws2))
    assert watcher._observer is not observer1
    watcher.stop()


# ------------------------------------------------------------------
# Callback tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_file_create_triggers_callback(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    events: list[tuple[str, str]] = []
    event_ready = threading.Event()

    def cb(path, etype):
        events.append((path, etype))
        event_ready.set()

    watcher.on_change(cb)
    watcher.start(str(workspace), debounce_seconds=0.01)

    # Create a file
    test_file = workspace / "hello.txt"
    test_file.write_text("hello")

    assert event_ready.wait(timeout=5)
    assert len(events) >= 1
    assert any("hello.txt" in e[0] for e in events)
    watcher.stop()


@pytest.mark.unit
def test_file_delete_triggers_callback(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    # Create file first
    test_file = workspace / "to_delete.txt"
    test_file.write_text("bye")

    watcher = FileWatcher.get_instance()
    events: list[tuple[str, str]] = []
    event_ready = threading.Event()

    def cb(path, etype):
        events.append((path, etype))
        if etype == "deleted":
            event_ready.set()

    watcher.on_change(cb)
    watcher.start(str(workspace), debounce_seconds=0.01)

    # Small delay so the watcher sees the initial state
    time.sleep(0.1)

    test_file.unlink()

    assert event_ready.wait(timeout=5)
    assert any(e[1] == "deleted" for e in events)
    watcher.stop()


@pytest.mark.unit
def test_multiple_callbacks_all_fire(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    results_a: list[str] = []
    results_b: list[str] = []
    done = threading.Event()

    def cb_a(path, etype):
        results_a.append(path)
        done.set()

    def cb_b(path, etype):
        results_b.append(path)

    watcher.on_change(cb_a)
    watcher.on_change(cb_b)
    watcher.start(str(workspace), debounce_seconds=0.01)

    (workspace / "multi.txt").write_text("data")
    assert done.wait(timeout=5)
    time.sleep(0.1)  # let second callback fire

    assert len(results_a) >= 1
    assert len(results_b) >= 1
    watcher.stop()


@pytest.mark.unit
def test_remove_callback(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    results: list[str] = []

    def cb(path, etype):
        results.append(path)

    watcher.on_change(cb)
    watcher.remove_callback(cb)

    # Should not crash
    watcher._dispatch("/fake/path", "created")
    assert len(results) == 0


@pytest.mark.unit
def test_remove_nonexistent_callback_is_noop():
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    watcher.remove_callback(lambda p, e: None)  # Should not raise


# ------------------------------------------------------------------
# Ignore logic tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_ignored_dirs_skipped():
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    assert watcher._should_ignore("/project/.git/objects/abc")
    assert watcher._should_ignore("/project/node_modules/lodash/index.js")
    assert watcher._should_ignore("/project/__pycache__/foo.pyc")
    assert watcher._should_ignore("/project/.venv/lib/python3.12/site.py")
    assert not watcher._should_ignore("/project/src/app.py")


@pytest.mark.unit
def test_gitignore_patterns_respected(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    # Write a .gitignore
    (workspace / ".gitignore").write_text("*.log\nbuild/\n")

    watcher = FileWatcher.get_instance()
    watcher.start(str(workspace), debounce_seconds=0.01)

    assert watcher._should_ignore(str(workspace / "debug.log"))
    assert watcher._should_ignore(str(workspace / "build" / "output.js"))
    assert not watcher._should_ignore(str(workspace / "src" / "main.py"))
    watcher.stop()


@pytest.mark.unit
def test_gitignore_missing_is_fine(workspace: Path):
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    watcher.start(str(workspace), debounce_seconds=0.01)

    assert watcher._gitignore_spec is None
    assert not watcher._should_ignore(str(workspace / "src" / "app.py"))
    watcher.stop()


# ------------------------------------------------------------------
# Debounce tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_debounce_collapses_rapid_changes():
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()
    watcher._debounce_seconds = 0.15

    results: list[tuple[str, str]] = []
    done = threading.Event()

    def cb(path, etype):
        results.append((path, etype))
        done.set()

    watcher.on_change(cb)

    # Fire 5 rapid events on the same file
    for _ in range(5):
        watcher._handle_event("/project/file.py", "modified")
        time.sleep(0.02)

    # Wait for debounce to fire
    assert done.wait(timeout=2)
    time.sleep(0.3)

    # Should have collapsed into 1 callback
    assert len(results) == 1


# ------------------------------------------------------------------
# Error handling tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_callback_exception_does_not_crash_watcher():
    from ag3nt_agent.file_watcher import FileWatcher

    watcher = FileWatcher.get_instance()

    good_results: list[str] = []

    def bad_cb(path, etype):
        raise RuntimeError("boom")

    def good_cb(path, etype):
        good_results.append(path)

    watcher.on_change(bad_cb)
    watcher.on_change(good_cb)

    # Dispatch directly (bypasses debounce for isolation)
    watcher._dispatch("/fake/file.py", "modified")

    assert len(good_results) == 1
