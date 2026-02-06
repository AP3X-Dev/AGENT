"""Git-based snapshot manager for AG3NT workspace undo/redo.

Maintains a shadow git repository at ~/.ag3nt/snapshots/<project-hash>/
to track workspace state independently of the user's own git history.

Each snapshot captures the full file tree at a point in time using
git plumbing commands (write-tree, read-tree, checkout-index).

Usage:
    from ag3nt_agent.snapshot import SnapshotManager

    mgr = SnapshotManager("/path/to/workspace")
    tree_hash = mgr.take_snapshot("before editing foo.py")
    # ... agent makes changes ...
    mgr.restore(tree_hash)
    diff_text = mgr.diff(tree_hash)
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("ag3nt.snapshot")

# Auto-cleanup: prune snapshots older than this (seconds)
_PRUNE_AGE_SECONDS = 7 * 24 * 3600  # 7 days

# Maximum number of snapshots to keep before pruning
_MAX_SNAPSHOTS = 500

# Git command timeout
_GIT_TIMEOUT = 30


@dataclass
class SnapshotInfo:
    """Metadata for a single snapshot."""

    tree_hash: str
    """Git tree object hash."""

    timestamp: float
    """Unix timestamp when the snapshot was taken."""

    label: str
    """Human-readable description of what triggered the snapshot."""

    files_changed: list[str] = field(default_factory=list)
    """List of files that were about to be modified (context)."""


class SnapshotManager:
    """Manages workspace snapshots using a shadow git repository.

    The shadow repo is completely separate from any user git repo.
    It uses git plumbing commands (not porcelain) to avoid interfering
    with the user's git state.

    Args:
        workspace_path: Absolute path to the workspace/project root.
        snapshots_root: Override for the snapshots base directory.
                        Defaults to ~/.ag3nt/snapshots/
    """

    def __init__(
        self,
        workspace_path: str | Path,
        snapshots_root: str | Path | None = None,
    ) -> None:
        self.workspace_path = Path(workspace_path).resolve()
        if not self.workspace_path.is_dir():
            raise ValueError(f"Workspace path does not exist: {self.workspace_path}")

        # Compute a stable hash for this workspace
        workspace_hash = hashlib.sha256(
            str(self.workspace_path).encode()
        ).hexdigest()[:16]

        base = Path(snapshots_root) if snapshots_root else Path.home() / ".ag3nt" / "snapshots"
        self.shadow_repo = base / workspace_hash
        self._snapshots: list[SnapshotInfo] = []
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize the shadow git repo if needed."""
        if self._initialized:
            return

        self.shadow_repo.mkdir(parents=True, exist_ok=True)
        git_dir = self.shadow_repo / ".git"

        if not git_dir.exists():
            self._run_git(["init"], cwd=self.shadow_repo)
            self._run_git(
                ["config", "user.email", "snapshots@ag3nt.dev"],
                cwd=self.shadow_repo,
            )
            self._run_git(
                ["config", "user.name", "AG3NT Snapshots"],
                cwd=self.shadow_repo,
            )
            # Create an initial empty commit so we always have a HEAD
            self._run_git(
                ["commit", "--allow-empty", "-m", "snapshot repo initialized"],
                cwd=self.shadow_repo,
            )
            logger.info("Initialized shadow snapshot repo at %s", self.shadow_repo)

        self._initialized = True

    def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
        env_extra: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command with the shadow repo's GIT_DIR.

        Args:
            args: Git arguments (without 'git' prefix).
            cwd: Working directory. Defaults to workspace_path.
            env_extra: Extra environment variables to set.
            check: Raise on non-zero exit.

        Returns:
            CompletedProcess result.
        """
        env = os.environ.copy()
        # Point git at the shadow repo, but work in the workspace
        env["GIT_DIR"] = str(self.shadow_repo / ".git")
        env["GIT_WORK_TREE"] = str(self.workspace_path)
        if env_extra:
            env.update(env_extra)

        effective_cwd = str(cwd or self.workspace_path)
        return subprocess.run(
            ["git"] + args,
            cwd=effective_cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=check,
            env=env,
        )

    def take_snapshot(
        self,
        label: str = "",
        files: list[str] | None = None,
    ) -> str:
        """Capture the current workspace state as a snapshot.

        Uses git plumbing: add + write-tree to create a tree object
        without actually making a commit (fast, no reflog noise).

        Args:
            label: Human-readable label for this snapshot.
            files: Optional list of specific files being modified
                   (stored as context in the snapshot metadata).

        Returns:
            The git tree hash identifying this snapshot.
        """
        self._ensure_initialized()

        try:
            # Stage everything in the workspace into the shadow index
            self._run_git(["add", "-A", "--force"])

            # Write the index as a tree object
            result = self._run_git(["write-tree"])
            tree_hash = result.stdout.strip()

            if not tree_hash:
                raise RuntimeError("git write-tree returned empty hash")

            # Also create a commit pointing to this tree for easier gc
            commit_msg = label or f"snapshot at {time.strftime('%Y-%m-%d %H:%M:%S')}"
            self._run_git([
                "commit", "--allow-empty", "-m", commit_msg,
            ], check=False)  # may fail if nothing changed, that's fine

            info = SnapshotInfo(
                tree_hash=tree_hash,
                timestamp=time.time(),
                label=label,
                files_changed=files or [],
            )
            self._snapshots.append(info)

            # Auto-prune if we have too many
            if len(self._snapshots) > _MAX_SNAPSHOTS:
                self._prune_old()

            logger.debug(
                "Snapshot taken: %s (label=%s, files=%s)",
                tree_hash[:12], label, files,
            )
            return tree_hash

        except subprocess.CalledProcessError as e:
            logger.error("Failed to take snapshot: %s\n%s", e, e.stderr)
            raise RuntimeError(f"Snapshot failed: {e.stderr}") from e
        except subprocess.TimeoutExpired:
            logger.error("Snapshot timed out after %ds", _GIT_TIMEOUT)
            raise RuntimeError("Snapshot timed out")

    def restore(self, tree_hash: str) -> list[str]:
        """Restore the workspace to a previous snapshot.

        Takes a new snapshot of the current state first (for unrevert),
        then restores the target tree.

        Args:
            tree_hash: The tree hash from a previous take_snapshot() call.

        Returns:
            List of files that were changed by the restore.
        """
        self._ensure_initialized()

        try:
            # First, get the list of changes
            changed = self._diff_tree_to_workspace(tree_hash)

            # Read the target tree into the index
            self._run_git(["read-tree", tree_hash])

            # Checkout the index into the workspace, forcing overwrite
            self._run_git([
                "checkout-index", "-f", "-a",
                "--prefix=",
            ], env_extra={"GIT_WORK_TREE": str(self.workspace_path)})

            # Clean up files that exist in workspace but not in the snapshot
            # by doing a diff and removing extras
            self._clean_extra_files(tree_hash)

            logger.info(
                "Restored snapshot %s (%d files changed)",
                tree_hash[:12], len(changed),
            )
            return changed

        except subprocess.CalledProcessError as e:
            logger.error("Failed to restore snapshot %s: %s", tree_hash[:12], e.stderr)
            raise RuntimeError(f"Restore failed: {e.stderr}") from e

    def diff(self, tree_hash: str) -> str:
        """Show changes between a snapshot and the current workspace.

        Args:
            tree_hash: The tree hash to compare against.

        Returns:
            Git diff output as a string.
        """
        self._ensure_initialized()

        try:
            # Stage current state to compare
            self._run_git(["add", "-A", "--force"])
            current_tree = self._run_git(["write-tree"]).stdout.strip()

            # Diff between the snapshot tree and current tree
            result = self._run_git(
                ["diff-tree", "-p", "--stat", tree_hash, current_tree],
                check=False,
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            return f"Error computing diff: {e.stderr}"

    def diff_summary(self, tree_hash: str) -> str:
        """Show a short summary of changes since a snapshot.

        Args:
            tree_hash: The tree hash to compare against.

        Returns:
            Stat-only diff output.
        """
        self._ensure_initialized()

        try:
            self._run_git(["add", "-A", "--force"])
            current_tree = self._run_git(["write-tree"]).stdout.strip()

            result = self._run_git(
                ["diff-tree", "--stat", tree_hash, current_tree],
                check=False,
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            return f"Error computing diff: {e.stderr}"

    def list_snapshots(self, n: int = 20) -> list[SnapshotInfo]:
        """List recent snapshots.

        Args:
            n: Maximum number of snapshots to return.

        Returns:
            List of SnapshotInfo, most recent first.
        """
        return list(reversed(self._snapshots[-n:]))

    def get_snapshot(self, tree_hash: str) -> SnapshotInfo | None:
        """Look up a snapshot by its tree hash.

        Args:
            tree_hash: Full or prefix of the tree hash.

        Returns:
            SnapshotInfo if found, None otherwise.
        """
        for info in reversed(self._snapshots):
            if info.tree_hash.startswith(tree_hash):
                return info
        return None

    def _diff_tree_to_workspace(self, tree_hash: str) -> list[str]:
        """Get list of files that differ between a tree and the workspace."""
        try:
            self._run_git(["add", "-A", "--force"])
            current_tree = self._run_git(["write-tree"]).stdout.strip()

            result = self._run_git(
                ["diff-tree", "--name-only", "-r", tree_hash, current_tree],
                check=False,
            )
            files = [f for f in result.stdout.strip().split("\n") if f]
            return files
        except subprocess.CalledProcessError:
            return []

    def _clean_extra_files(self, tree_hash: str) -> None:
        """Remove workspace files not present in the snapshot tree."""
        try:
            # List files in the target tree
            result = self._run_git(["ls-tree", "-r", "--name-only", tree_hash])
            tree_files = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

            # List files currently tracked
            self._run_git(["add", "-A", "--force"])
            result = self._run_git(["ls-files"])
            current_files = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

            # Files in workspace but not in snapshot
            extra_files = current_files - tree_files
            for f in extra_files:
                fpath = self.workspace_path / f
                if fpath.exists() and fpath.is_file():
                    fpath.unlink()
                    logger.debug("Removed extra file: %s", f)

        except subprocess.CalledProcessError as e:
            logger.debug("Clean extra files failed: %s", e.stderr)

    def _prune_old(self) -> None:
        """Remove snapshots older than the retention period."""
        cutoff = time.time() - _PRUNE_AGE_SECONDS
        before = len(self._snapshots)
        self._snapshots = [s for s in self._snapshots if s.timestamp > cutoff]
        pruned = before - len(self._snapshots)
        if pruned:
            logger.info("Pruned %d old snapshots", pruned)

        # Run git gc in the shadow repo (best-effort)
        try:
            self._run_git(["gc", "--auto", "--quiet"], check=False)
        except Exception:
            pass

    def gc(self) -> None:
        """Run garbage collection on the shadow repo."""
        self._ensure_initialized()
        try:
            self._run_git(["gc", "--aggressive", "--quiet"], check=False)
            self._prune_old()
            logger.info("Snapshot garbage collection complete")
        except Exception as e:
            logger.warning("Snapshot GC failed: %s", e)


# ---------------------------------------------------------------------------
# Singleton access (one manager per workspace)
# ---------------------------------------------------------------------------

_managers: dict[str, SnapshotManager] = {}


def get_snapshot_manager(workspace_path: str | Path | None = None) -> SnapshotManager:
    """Get or create a SnapshotManager for the given workspace.

    Args:
        workspace_path: Workspace root. Defaults to ~/.ag3nt/workspace.

    Returns:
        SnapshotManager instance.
    """
    if workspace_path is None:
        workspace_path = Path.home() / ".ag3nt" / "workspace"

    key = str(Path(workspace_path).resolve())
    if key not in _managers:
        _managers[key] = SnapshotManager(workspace_path)
    return _managers[key]
