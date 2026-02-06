"""Unit tests for the revert module and revert_tools (Sprint 3 — session undo/revert)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ag3nt_agent.revert import (
    ActionRecord,
    RevertResult,
    RevertState,
    SessionRevert,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the SessionRevert singleton before each test."""
    SessionRevert._instance = None
    yield
    SessionRevert._instance = None


@pytest.fixture()
def revert() -> SessionRevert:
    """Return a fresh SessionRevert instance."""
    return SessionRevert.get_instance()


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Workspace directory for snapshot operations."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("print('hello')\n")
    return ws


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDataclasses:
    """Verify dataclass defaults and construction."""

    def test_action_record_defaults(self):
        rec = ActionRecord(
            tool_call_id="tc-1",
            snapshot_before="abc123",
            timestamp=1.0,
        )
        assert rec.files == []
        assert rec.tool_name == ""
        assert rec.label == ""

    def test_revert_state_defaults(self):
        state = RevertState()
        assert state.actions == []
        assert state.undo_stack == []
        assert state.last_revert_snapshot is None

    def test_revert_result_defaults(self):
        res = RevertResult(success=True, message="ok")
        assert res.files_changed == []
        assert res.snapshot_hash == ""


# ---------------------------------------------------------------------------
# SessionRevert core tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSessionRevertSingleton:
    """Singleton pattern validation."""

    def test_get_instance_returns_same_object(self):
        r1 = SessionRevert.get_instance()
        r2 = SessionRevert.get_instance()
        assert r1 is r2


@pytest.mark.unit
class TestRecordAction:
    """Tests for record_action."""

    def test_record_single_action(self, revert: SessionRevert):
        revert.record_action(
            session_id="s1",
            tool_call_id="tc-1",
            files=["foo.py"],
            snapshot_before="hash1",
            tool_name="edit_file",
            label="edit foo",
        )
        actions = revert.list_actions("s1")
        assert len(actions) == 1
        assert actions[0]["tool_call_id"] == "tc-1"
        assert actions[0]["tool_name"] == "edit_file"
        assert actions[0]["files"] == ["foo.py"]

    def test_record_multiple_actions(self, revert: SessionRevert):
        for i in range(3):
            revert.record_action(
                session_id="s1",
                tool_call_id=f"tc-{i}",
                snapshot_before=f"hash-{i}",
                tool_name="edit_file",
            )
        actions = revert.list_actions("s1")
        assert len(actions) == 3
        # Most recent first
        assert actions[0]["tool_call_id"] == "tc-2"

    def test_record_action_clears_undo_stack(self, revert: SessionRevert):
        state = revert._get_state("s1")
        state.undo_stack.append("some-hash")
        state.last_revert_snapshot = "some-hash"

        revert.record_action(
            session_id="s1",
            tool_call_id="tc-new",
            snapshot_before="hash-new",
        )
        assert state.undo_stack == []
        assert state.last_revert_snapshot is None

    def test_separate_sessions(self, revert: SessionRevert):
        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")
        revert.record_action(session_id="s2", tool_call_id="tc-2", snapshot_before="h2")

        assert len(revert.list_actions("s1")) == 1
        assert len(revert.list_actions("s2")) == 1
        assert revert.list_actions("s1")[0]["tool_call_id"] == "tc-1"
        assert revert.list_actions("s2")[0]["tool_call_id"] == "tc-2"


@pytest.mark.unit
class TestUndoLast:
    """Tests for undo_last."""

    def test_undo_with_no_actions(self, revert: SessionRevert):
        result = revert.undo_last("empty-session")
        assert result.success is False
        assert "Nothing to undo" in result.message

    def test_undo_last_calls_restore(self, revert: SessionRevert, workspace: Path):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "current-snap"
        mock_mgr.restore.return_value = ["main.py"]

        revert.record_action(
            session_id="s1",
            tool_call_id="tc-1",
            files=["main.py"],
            snapshot_before="before-hash",
            tool_name="edit_file",
        )

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.undo_last("s1", workspace_path=str(workspace))

        assert result.success is True
        assert "Undone" in result.message
        assert result.files_changed == ["main.py"]
        assert result.snapshot_hash == "before-hash"
        mock_mgr.restore.assert_called_once_with("before-hash")

    def test_undo_last_removes_action_from_history(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "snap"
        mock_mgr.restore.return_value = []

        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")
        revert.record_action(session_id="s1", tool_call_id="tc-2", snapshot_before="h2")

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            revert.undo_last("s1")

        actions = revert.list_actions("s1")
        assert len(actions) == 1
        assert actions[0]["tool_call_id"] == "tc-1"

    def test_undo_last_pushes_to_undo_stack(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "current-state"
        mock_mgr.restore.return_value = []

        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            revert.undo_last("s1")

        state = revert._get_state("s1")
        assert "current-state" in state.undo_stack

    def test_undo_last_restore_failure(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "snap"
        mock_mgr.restore.side_effect = RuntimeError("git exploded")

        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.undo_last("s1")

        assert result.success is False
        assert "failed" in result.message.lower()


@pytest.mark.unit
class TestRevertTo:
    """Tests for revert_to."""

    def test_revert_to_nonexistent_tool_call(self, revert: SessionRevert):
        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")
        result = revert.revert_to("s1", "tc-nonexistent")
        assert result.success is False
        assert "not found" in result.message

    def test_revert_to_specific_action(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "current"
        mock_mgr.restore.return_value = ["a.py", "b.py"]

        for i in range(4):
            revert.record_action(
                session_id="s1",
                tool_call_id=f"tc-{i}",
                snapshot_before=f"h-{i}",
                tool_name="edit_file",
            )

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.revert_to("s1", "tc-2")

        assert result.success is True
        assert "2 action(s)" in result.message
        assert result.snapshot_hash == "h-2"
        mock_mgr.restore.assert_called_once_with("h-2")

        # Actions tc-2 and tc-3 should be removed, tc-0 and tc-1 remain
        actions = revert.list_actions("s1")
        assert len(actions) == 2
        ids = [a["tool_call_id"] for a in actions]
        assert "tc-0" in ids
        assert "tc-1" in ids

    def test_revert_to_first_action(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "current"
        mock_mgr.restore.return_value = []

        for i in range(3):
            revert.record_action(
                session_id="s1",
                tool_call_id=f"tc-{i}",
                snapshot_before=f"h-{i}",
            )

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.revert_to("s1", "tc-0")

        assert result.success is True
        assert "3 action(s)" in result.message
        assert len(revert.list_actions("s1")) == 0

    def test_revert_to_failure(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "snap"
        mock_mgr.restore.side_effect = RuntimeError("boom")

        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.revert_to("s1", "tc-1")

        assert result.success is False


@pytest.mark.unit
class TestUnrevert:
    """Tests for unrevert."""

    def test_unrevert_with_empty_stack(self, revert: SessionRevert):
        result = revert.unrevert("s1")
        assert result.success is False
        assert "Nothing to unrevert" in result.message

    def test_unrevert_after_undo(self, revert: SessionRevert):
        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "pre-undo-snap"
        mock_mgr.restore.return_value = ["main.py"]

        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            revert.undo_last("s1")

        # Now unrevert
        mock_mgr.restore.return_value = ["main.py"]
        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.unrevert("s1")

        assert result.success is True
        assert "Unrevert complete" in result.message
        assert result.files_changed == ["main.py"]

    def test_unrevert_failure_preserves_stack(self, revert: SessionRevert):
        state = revert._get_state("s1")
        state.undo_stack.append("preserved-hash")

        mock_mgr = MagicMock()
        mock_mgr.restore.side_effect = RuntimeError("fail")

        with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
            result = revert.unrevert("s1")

        assert result.success is False
        # Hash should be back on the stack for retry
        assert "preserved-hash" in state.undo_stack


@pytest.mark.unit
class TestCanUndo:
    """Tests for can_undo and can_unrevert."""

    def test_can_undo_empty(self, revert: SessionRevert):
        assert revert.can_undo("s1") is False

    def test_can_undo_with_actions(self, revert: SessionRevert):
        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")
        assert revert.can_undo("s1") is True

    def test_can_unrevert_empty(self, revert: SessionRevert):
        assert revert.can_unrevert("s1") is False

    def test_can_unrevert_with_stack(self, revert: SessionRevert):
        state = revert._get_state("s1")
        state.undo_stack.append("hash")
        assert revert.can_unrevert("s1") is True


@pytest.mark.unit
class TestListActions:
    """Tests for list_actions."""

    def test_empty_session(self, revert: SessionRevert):
        assert revert.list_actions("s1") == []

    def test_list_actions_fields(self, revert: SessionRevert):
        revert.record_action(
            session_id="s1",
            tool_call_id="tc-1",
            files=["x.py"],
            snapshot_before="abcdef123456",
            tool_name="write_file",
            label="write x",
        )
        actions = revert.list_actions("s1")
        assert len(actions) == 1
        a = actions[0]
        assert a["tool_call_id"] == "tc-1"
        assert a["tool_name"] == "write_file"
        assert a["files"] == ["x.py"]
        assert a["label"] == "write x"
        assert a["snapshot"] == "abcdef123456"[:12]

    def test_list_actions_limit(self, revert: SessionRevert):
        for i in range(10):
            revert.record_action(
                session_id="s1",
                tool_call_id=f"tc-{i}",
                snapshot_before=f"h-{i:040d}",
            )
        limited = revert.list_actions("s1", n=3)
        assert len(limited) == 3
        assert limited[0]["tool_call_id"] == "tc-9"


@pytest.mark.unit
class TestClearSession:
    """Tests for clear_session."""

    def test_clear_removes_all_state(self, revert: SessionRevert):
        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")
        revert.record_action(session_id="s1", tool_call_id="tc-2", snapshot_before="h2")

        revert.clear_session("s1")

        assert revert.list_actions("s1") == []
        assert revert.can_undo("s1") is False

    def test_clear_does_not_affect_other_sessions(self, revert: SessionRevert):
        revert.record_action(session_id="s1", tool_call_id="tc-1", snapshot_before="h1")
        revert.record_action(session_id="s2", tool_call_id="tc-2", snapshot_before="h2")

        revert.clear_session("s1")

        assert len(revert.list_actions("s1")) == 0
        assert len(revert.list_actions("s2")) == 1


# ---------------------------------------------------------------------------
# Revert tools tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRevertTools:
    """Tests for the LangChain tool wrappers in revert_tools."""

    def test_get_revert_tools_returns_four(self):
        from ag3nt_agent.revert_tools import get_revert_tools
        tools = get_revert_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {"undo_last", "undo_to", "unrevert", "show_undo_history"}

    def test_undo_last_tool_no_actions(self):
        from ag3nt_agent.revert_tools import undo_last as undo_last_tool

        with patch.dict(os.environ, {"AG3NT_SESSION_ID": "test-session"}):
            result = undo_last_tool.invoke({})
        assert "Nothing to undo" in result

    def test_undo_to_tool_not_found(self):
        from ag3nt_agent.revert_tools import undo_to as undo_to_tool

        with patch.dict(os.environ, {"AG3NT_SESSION_ID": "test-session"}):
            result = undo_to_tool.invoke({"tool_call_id": "nonexistent"})
        assert "not found" in result

    def test_unrevert_tool_nothing(self):
        from ag3nt_agent.revert_tools import unrevert as unrevert_tool

        with patch.dict(os.environ, {"AG3NT_SESSION_ID": "test-session"}):
            result = unrevert_tool.invoke({})
        assert "Nothing to unrevert" in result

    def test_show_undo_history_empty(self):
        from ag3nt_agent.revert_tools import show_undo_history

        with patch.dict(os.environ, {"AG3NT_SESSION_ID": "test-session"}):
            result = show_undo_history.invoke({"n": 10})
        assert "No file-modifying actions" in result

    def test_show_undo_history_with_actions(self, revert: SessionRevert):
        from ag3nt_agent.revert_tools import show_undo_history

        revert.record_action(
            session_id="tool-test",
            tool_call_id="tc-42",
            files=["app.py"],
            snapshot_before="deadbeef1234",
            tool_name="edit_file",
            label="edit app",
        )

        with patch.dict(os.environ, {"AG3NT_SESSION_ID": "tool-test"}):
            result = show_undo_history.invoke({"n": 10})

        assert "tc-42" in result
        assert "edit_file" in result
        assert "app.py" in result

    def test_undo_last_tool_success(self, revert: SessionRevert):
        from ag3nt_agent.revert_tools import undo_last as undo_last_tool

        mock_mgr = MagicMock()
        mock_mgr.take_snapshot.return_value = "snap"
        mock_mgr.restore.return_value = ["changed.py"]

        revert.record_action(
            session_id="tool-sess",
            tool_call_id="tc-99",
            files=["changed.py"],
            snapshot_before="before-hash",
            tool_name="write_file",
        )

        with patch.dict(os.environ, {"AG3NT_SESSION_ID": "tool-sess"}):
            with patch("ag3nt_agent.revert.get_snapshot_manager", return_value=mock_mgr):
                result = undo_last_tool.invoke({})

        assert "Undone" in result
        assert "changed.py" in result
