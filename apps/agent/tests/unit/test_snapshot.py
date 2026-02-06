"""Unit tests for the snapshot module (Sprint 3 — git-based workspace snapshots)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ag3nt_agent.snapshot import (
    SnapshotInfo,
    SnapshotManager,
    get_snapshot_manager,
    _managers,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the module-level singleton cache between tests."""
    _managers.clear()
    yield
    _managers.clear()


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory with a sample file."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.py").write_text("print('hello')\n")
    return ws


@pytest.fixture()
def snapshot_root(tmp_path: Path) -> Path:
    """Separate tmp directory for the shadow repo."""
    root = tmp_path / "snapshots"
    root.mkdir()
    return root


@pytest.fixture()
def mgr(workspace: Path, snapshot_root: Path) -> SnapshotManager:
    """Return a SnapshotManager wired to temp directories."""
    return SnapshotManager(workspace, snapshots_root=snapshot_root)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSnapshotInfo:
    """Verify the SnapshotInfo dataclass defaults."""

    def test_defaults(self):
        info = SnapshotInfo(tree_hash="abc123", timestamp=1.0, label="test")
        assert info.tree_hash == "abc123"
        assert info.timestamp == 1.0
        assert info.label == "test"
        assert info.files_changed == []

    def test_with_files(self):
        info = SnapshotInfo(
            tree_hash="def456",
            timestamp=2.0,
            label="edit",
            files_changed=["a.py", "b.py"],
        )
        assert info.files_changed == ["a.py", "b.py"]


@pytest.mark.unit
class TestSnapshotManagerInit:
    """Constructor / initialisation edge cases."""

    def test_invalid_workspace_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="does not exist"):
            SnapshotManager(tmp_path / "nonexistent")

    def test_workspace_hash_is_stable(self, workspace: Path, snapshot_root: Path):
        m1 = SnapshotManager(workspace, snapshots_root=snapshot_root)
        m2 = SnapshotManager(workspace, snapshots_root=snapshot_root)
        assert m1.shadow_repo == m2.shadow_repo

    def test_different_workspaces_get_different_repos(
        self, tmp_path: Path, snapshot_root: Path
    ):
        ws1 = tmp_path / "ws1"
        ws2 = tmp_path / "ws2"
        ws1.mkdir()
        ws2.mkdir()
        m1 = SnapshotManager(ws1, snapshots_root=snapshot_root)
        m2 = SnapshotManager(ws2, snapshots_root=snapshot_root)
        assert m1.shadow_repo != m2.shadow_repo


@pytest.mark.unit
class TestSnapshotManagerCore:
    """Core snapshot/restore/diff flow (requires git on PATH)."""

    def test_take_snapshot_returns_hash(self, mgr: SnapshotManager):
        tree_hash = mgr.take_snapshot(label="initial")
        assert isinstance(tree_hash, str)
        assert len(tree_hash) >= 7  # short git hash minimum

    def test_take_snapshot_stores_info(self, mgr: SnapshotManager):
        tree_hash = mgr.take_snapshot(label="snap1", files=["hello.py"])
        snapshots = mgr.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].tree_hash == tree_hash
        assert snapshots[0].label == "snap1"
        assert snapshots[0].files_changed == ["hello.py"]

    def test_take_snapshot_empty_label(self, mgr: SnapshotManager):
        tree_hash = mgr.take_snapshot()
        assert tree_hash  # still returns a valid hash

    def test_multiple_snapshots(self, mgr: SnapshotManager, workspace: Path):
        h1 = mgr.take_snapshot(label="v1")
        (workspace / "hello.py").write_text("print('v2')\n")
        h2 = mgr.take_snapshot(label="v2")
        assert h1 != h2
        assert len(mgr.list_snapshots()) == 2

    def test_restore_reverts_file_content(self, mgr: SnapshotManager, workspace: Path):
        h1 = mgr.take_snapshot(label="before edit")
        original = (workspace / "hello.py").read_text()

        (workspace / "hello.py").write_text("print('changed')\n")
        assert (workspace / "hello.py").read_text() != original

        mgr.restore(h1)
        assert (workspace / "hello.py").read_text() == original

    def test_restore_returns_changed_files(
        self, mgr: SnapshotManager, workspace: Path
    ):
        h1 = mgr.take_snapshot(label="baseline")
        (workspace / "hello.py").write_text("modified\n")
        mgr.take_snapshot(label="after edit")

        changed = mgr.restore(h1)
        assert isinstance(changed, list)
        # hello.py should be among the changed files
        assert any("hello" in f for f in changed)

    def test_restore_removes_new_files(self, mgr: SnapshotManager, workspace: Path):
        h1 = mgr.take_snapshot(label="before new file")
        new_file = workspace / "extra.py"
        new_file.write_text("extra\n")
        assert new_file.exists()

        mgr.restore(h1)
        assert not new_file.exists()

    def test_diff_shows_changes(self, mgr: SnapshotManager, workspace: Path):
        h1 = mgr.take_snapshot(label="base")
        (workspace / "hello.py").write_text("print('different')\n")

        diff_output = mgr.diff(h1)
        assert isinstance(diff_output, str)
        # The diff should mention the changed file
        assert "hello" in diff_output or len(diff_output) > 0

    def test_diff_summary(self, mgr: SnapshotManager, workspace: Path):
        h1 = mgr.take_snapshot(label="base")
        (workspace / "hello.py").write_text("print('summary test')\n")

        summary = mgr.diff_summary(h1)
        assert isinstance(summary, str)


@pytest.mark.unit
class TestSnapshotManagerLookup:
    """Snapshot listing and lookup."""

    def test_list_snapshots_ordering(self, mgr: SnapshotManager, workspace: Path):
        mgr.take_snapshot(label="first")
        (workspace / "hello.py").write_text("v2\n")
        mgr.take_snapshot(label="second")

        snapshots = mgr.list_snapshots()
        # Most recent first
        assert snapshots[0].label == "second"
        assert snapshots[1].label == "first"

    def test_list_snapshots_limit(self, mgr: SnapshotManager, workspace: Path):
        for i in range(5):
            (workspace / "hello.py").write_text(f"v{i}\n")
            mgr.take_snapshot(label=f"snap-{i}")

        limited = mgr.list_snapshots(n=3)
        assert len(limited) == 3
        assert limited[0].label == "snap-4"

    def test_get_snapshot_by_hash(self, mgr: SnapshotManager):
        tree_hash = mgr.take_snapshot(label="findme")
        found = mgr.get_snapshot(tree_hash)
        assert found is not None
        assert found.label == "findme"

    def test_get_snapshot_by_prefix(self, mgr: SnapshotManager):
        tree_hash = mgr.take_snapshot(label="prefix-test")
        found = mgr.get_snapshot(tree_hash[:8])
        assert found is not None
        assert found.tree_hash == tree_hash

    def test_get_snapshot_not_found(self, mgr: SnapshotManager):
        assert mgr.get_snapshot("nonexistent") is None


@pytest.mark.unit
class TestSnapshotManagerPruning:
    """Auto-pruning of old snapshots."""

    def test_prune_old_removes_expired(self, mgr: SnapshotManager):
        # Manually insert an "old" snapshot
        import time as _time

        old_info = SnapshotInfo(
            tree_hash="oldoldold",
            timestamp=_time.time() - (8 * 24 * 3600),  # 8 days ago
            label="ancient",
        )
        mgr._snapshots.append(old_info)
        mgr.take_snapshot(label="recent")

        # Prune should remove the old one
        mgr._prune_old()
        labels = [s.label for s in mgr._snapshots]
        assert "ancient" not in labels
        assert "recent" in labels


@pytest.mark.unit
class TestSnapshotManagerErrors:
    """Error handling paths."""

    def test_take_snapshot_git_failure(self, mgr: SnapshotManager):
        mgr._ensure_initialized()
        with patch.object(mgr, "_run_git", side_effect=subprocess.CalledProcessError(
            1, "git", stderr="simulated failure"
        )):
            with pytest.raises(RuntimeError, match="Snapshot failed"):
                mgr.take_snapshot(label="fail")

    def test_take_snapshot_timeout(self, mgr: SnapshotManager):
        mgr._ensure_initialized()
        with patch.object(mgr, "_run_git", side_effect=subprocess.TimeoutExpired(
            "git", 30
        )):
            with pytest.raises(RuntimeError, match="timed out"):
                mgr.take_snapshot(label="timeout")

    def test_restore_git_failure(self, mgr: SnapshotManager):
        mgr._ensure_initialized()
        with patch.object(mgr, "_run_git", side_effect=subprocess.CalledProcessError(
            1, "git", stderr="restore error"
        )):
            with pytest.raises(RuntimeError, match="Restore failed"):
                mgr.restore("deadbeef")


@pytest.mark.unit
class TestGetSnapshotManager:
    """Singleton factory tests."""

    def test_returns_same_instance(self, workspace: Path, snapshot_root: Path):
        # We need to mock the default so it doesn't try to use ~/.ag3nt
        m1 = get_snapshot_manager(workspace)
        m2 = get_snapshot_manager(workspace)
        assert m1 is m2

    def test_different_paths_different_instances(self, tmp_path: Path):
        ws1 = tmp_path / "a"
        ws2 = tmp_path / "b"
        ws1.mkdir()
        ws2.mkdir()
        m1 = get_snapshot_manager(ws1)
        m2 = get_snapshot_manager(ws2)
        assert m1 is not m2
