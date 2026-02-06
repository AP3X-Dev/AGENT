"""Session-level undo/revert for AG3NT.

Tracks snapshots per session and tool call, enabling:
- Undo the last file-modifying action
- Revert to a specific point in the conversation
- Unrevert (re-apply reverted changes)

Usage:
    from ag3nt_agent.revert import SessionRevert

    revert = SessionRevert.get_instance()
    revert.record_action("session-1", "tc-42", "/path/to/file.py", snapshot_hash)

    # Undo the last action
    result = revert.undo_last("session-1")

    # Revert to a specific tool call
    result = revert.revert_to("session-1", "tc-40")

    # Re-apply what was undone
    result = revert.unrevert("session-1")
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ag3nt_agent.snapshot import SnapshotManager, get_snapshot_manager

logger = logging.getLogger("ag3nt.revert")


@dataclass
class ActionRecord:
    """Record of a file-modifying action within a session."""

    tool_call_id: str
    """ID of the tool call that made the change."""

    snapshot_before: str
    """Tree hash of the workspace state BEFORE this action."""

    timestamp: float
    """When this action was recorded."""

    files: list[str] = field(default_factory=list)
    """Files that were modified by this action."""

    tool_name: str = ""
    """Name of the tool (edit_file, write_file, apply_patch, etc.)."""

    label: str = ""
    """Human-readable description."""


@dataclass
class RevertState:
    """Per-session revert state."""

    actions: list[ActionRecord] = field(default_factory=list)
    """Ordered list of file-modifying actions."""

    undo_stack: list[str] = field(default_factory=list)
    """Stack of snapshot hashes taken before each undo (for unrevert)."""

    last_revert_snapshot: str | None = None
    """Snapshot taken just before the most recent revert (for unrevert)."""


@dataclass
class RevertResult:
    """Result of an undo/revert/unrevert operation."""

    success: bool
    """Whether the operation succeeded."""

    message: str
    """Human-readable result message."""

    files_changed: list[str] = field(default_factory=list)
    """Files that were modified by the operation."""

    snapshot_hash: str = ""
    """The snapshot that was restored."""


class SessionRevert:
    """Manages undo/revert operations per session.

    Coordinates with SnapshotManager to take and restore snapshots,
    maintaining a per-session history of file-modifying actions.
    """

    _instance: SessionRevert | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._sessions: dict[str, RevertState] = {}
        self._session_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SessionRevert:
        """Get the singleton SessionRevert instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_state(self, session_id: str) -> RevertState:
        """Get or create revert state for a session."""
        if session_id not in self._sessions:
            with self._session_lock:
                if session_id not in self._sessions:
                    self._sessions[session_id] = RevertState()
        return self._sessions[session_id]

    def record_action(
        self,
        session_id: str,
        tool_call_id: str,
        files: list[str] | None = None,
        snapshot_before: str = "",
        tool_name: str = "",
        label: str = "",
    ) -> None:
        """Record a file-modifying action.

        Called AFTER a snapshot has been taken but BEFORE the actual
        modification. The snapshot_before should be the tree hash
        returned by SnapshotManager.take_snapshot().

        Args:
            session_id: The session this action belongs to.
            tool_call_id: ID of the tool call making the change.
            files: List of file paths being modified.
            snapshot_before: Tree hash of the pre-modification state.
            tool_name: Name of the modifying tool.
            label: Human-readable description.
        """
        state = self._get_state(session_id)
        record = ActionRecord(
            tool_call_id=tool_call_id,
            snapshot_before=snapshot_before,
            timestamp=time.time(),
            files=files or [],
            tool_name=tool_name,
            label=label,
        )
        state.actions.append(record)

        # Clear undo stack since new actions invalidate previous undos
        state.undo_stack.clear()
        state.last_revert_snapshot = None

        logger.debug(
            "Recorded action: session=%s tc=%s tool=%s files=%s",
            session_id, tool_call_id, tool_name, files,
        )

    def undo_last(
        self,
        session_id: str,
        workspace_path: str | None = None,
    ) -> RevertResult:
        """Undo the most recent file-modifying action.

        Takes a snapshot of the current state (for unrevert), then
        restores the snapshot from before the last action.

        Args:
            session_id: Session to undo in.
            workspace_path: Workspace root for the snapshot manager.

        Returns:
            RevertResult with details of the operation.
        """
        state = self._get_state(session_id)

        if not state.actions:
            return RevertResult(
                success=False,
                message="Nothing to undo — no file-modifying actions recorded in this session.",
            )

        last_action = state.actions[-1]
        mgr = get_snapshot_manager(workspace_path)

        try:
            # Save current state so we can unrevert
            current_snapshot = mgr.take_snapshot(
                label=f"before undo of {last_action.tool_name} ({last_action.tool_call_id})",
            )
            state.undo_stack.append(current_snapshot)
            state.last_revert_snapshot = current_snapshot

            # Restore to the state before the last action
            changed = mgr.restore(last_action.snapshot_before)

            # Remove the undone action from history
            state.actions.pop()

            return RevertResult(
                success=True,
                message=(
                    f"Undone: {last_action.tool_name or 'action'} "
                    f"(tool call {last_action.tool_call_id}). "
                    f"{len(changed)} file(s) restored."
                ),
                files_changed=changed,
                snapshot_hash=last_action.snapshot_before,
            )

        except Exception as e:
            logger.error("Undo failed: %s", e)
            return RevertResult(
                success=False,
                message=f"Undo failed: {e}",
            )

    def revert_to(
        self,
        session_id: str,
        tool_call_id: str,
        workspace_path: str | None = None,
    ) -> RevertResult:
        """Revert workspace to the state before a specific tool call.

        Undoes all actions from the specified tool call onward.

        Args:
            session_id: Session to revert in.
            tool_call_id: Revert to the state before this tool call.
            workspace_path: Workspace root.

        Returns:
            RevertResult with details.
        """
        state = self._get_state(session_id)

        # Find the target action
        target_idx = None
        for i, action in enumerate(state.actions):
            if action.tool_call_id == tool_call_id:
                target_idx = i
                break

        if target_idx is None:
            return RevertResult(
                success=False,
                message=f"Tool call '{tool_call_id}' not found in session history.",
            )

        target_action = state.actions[target_idx]
        actions_to_undo = len(state.actions) - target_idx
        mgr = get_snapshot_manager(workspace_path)

        try:
            # Save current state for unrevert
            current_snapshot = mgr.take_snapshot(
                label=f"before revert to {tool_call_id}",
            )
            state.undo_stack.append(current_snapshot)
            state.last_revert_snapshot = current_snapshot

            # Restore to the state before the target action
            changed = mgr.restore(target_action.snapshot_before)

            # Remove all actions from target onward
            state.actions = state.actions[:target_idx]

            return RevertResult(
                success=True,
                message=(
                    f"Reverted {actions_to_undo} action(s) back to before "
                    f"{target_action.tool_name or 'action'} "
                    f"(tool call {tool_call_id}). "
                    f"{len(changed)} file(s) restored."
                ),
                files_changed=changed,
                snapshot_hash=target_action.snapshot_before,
            )

        except Exception as e:
            logger.error("Revert failed: %s", e)
            return RevertResult(
                success=False,
                message=f"Revert failed: {e}",
            )

    def unrevert(
        self,
        session_id: str,
        workspace_path: str | None = None,
    ) -> RevertResult:
        """Re-apply the most recently reverted changes.

        Restores the snapshot taken just before the last undo/revert.

        Args:
            session_id: Session to unrevert in.
            workspace_path: Workspace root.

        Returns:
            RevertResult with details.
        """
        state = self._get_state(session_id)

        if not state.undo_stack:
            return RevertResult(
                success=False,
                message="Nothing to unrevert — no previous undo/revert in this session.",
            )

        restore_hash = state.undo_stack.pop()
        mgr = get_snapshot_manager(workspace_path)

        try:
            changed = mgr.restore(restore_hash)
            state.last_revert_snapshot = None

            return RevertResult(
                success=True,
                message=f"Unrevert complete. {len(changed)} file(s) restored to post-change state.",
                files_changed=changed,
                snapshot_hash=restore_hash,
            )

        except Exception as e:
            logger.error("Unrevert failed: %s", e)
            # Put it back on the stack so they can try again
            state.undo_stack.append(restore_hash)
            return RevertResult(
                success=False,
                message=f"Unrevert failed: {e}",
            )

    def list_actions(
        self,
        session_id: str,
        n: int = 20,
    ) -> list[dict[str, Any]]:
        """List recent file-modifying actions for a session.

        Args:
            session_id: Session to list actions for.
            n: Maximum number of actions to return.

        Returns:
            List of action dicts, most recent first.
        """
        state = self._get_state(session_id)
        actions = list(reversed(state.actions[-n:]))
        return [
            {
                "tool_call_id": a.tool_call_id,
                "tool_name": a.tool_name,
                "files": a.files,
                "timestamp": a.timestamp,
                "label": a.label,
                "snapshot": a.snapshot_before[:12],
            }
            for a in actions
        ]

    def can_undo(self, session_id: str) -> bool:
        """Check if there are actions that can be undone."""
        state = self._get_state(session_id)
        return len(state.actions) > 0

    def can_unrevert(self, session_id: str) -> bool:
        """Check if there's a previous undo that can be re-applied."""
        state = self._get_state(session_id)
        return len(state.undo_stack) > 0

    def clear_session(self, session_id: str) -> None:
        """Clear all revert state for a session.

        Args:
            session_id: Session to clear.
        """
        with self._session_lock:
            self._sessions.pop(session_id, None)
        logger.debug("Cleared revert state for session %s", session_id)
