"""Unit tests for PathProtection in tool_policy.py."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure a clean PathProtection singleton for every test."""
    from ag3nt_agent.tool_policy import PathProtection

    PathProtection.reset_instance()
    yield
    PathProtection.reset_instance()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ------------------------------------------------------------------
# Singleton tests
# ------------------------------------------------------------------


@pytest.mark.unit
def test_singleton_returns_same_instance():
    from ag3nt_agent.tool_policy import PathProtection

    a = PathProtection.get_instance()
    b = PathProtection.get_instance()
    assert a is b


@pytest.mark.unit
def test_reset_clears_singleton():
    from ag3nt_agent.tool_policy import PathProtection

    inst = PathProtection.get_instance()
    PathProtection.reset_instance()
    new_inst = PathProtection.get_instance()
    assert new_inst is not inst


# ------------------------------------------------------------------
# is_within_workspace
# ------------------------------------------------------------------


@pytest.mark.unit
def test_within_workspace_allowed(workspace: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    assert pp.is_within_workspace(str(workspace / "src" / "app.py"))
    assert pp.is_within_workspace(str(workspace / "README.md"))


@pytest.mark.unit
def test_workspace_root_itself_is_allowed(workspace: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    assert pp.is_within_workspace(str(workspace))


@pytest.mark.unit
def test_outside_workspace_not_within(workspace: Path, tmp_path: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    outside = tmp_path / "other" / "file.py"
    assert not pp.is_within_workspace(str(outside))


@pytest.mark.unit
def test_prefix_attack_rejected(workspace: Path, tmp_path: Path):
    """A path like /workspace2 should NOT match /workspace."""
    from ag3nt_agent.tool_policy import PathProtection

    trick = Path(str(workspace) + "2")
    trick.mkdir(exist_ok=True)

    pp = PathProtection.get_instance(str(workspace))
    assert not pp.is_within_workspace(str(trick / "evil.py"))


# ------------------------------------------------------------------
# check_path
# ------------------------------------------------------------------


@pytest.mark.unit
def test_check_path_inside_workspace(workspace: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    allowed, msg = pp.check_path(str(workspace / "ok.py"), "s1")
    assert allowed is True
    assert msg == ""


@pytest.mark.unit
def test_check_path_outside_workspace_blocked(workspace: Path, tmp_path: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    outside = str(tmp_path / "secrets" / "key.pem")
    allowed, msg = pp.check_path(outside, "s1", operation="read")
    assert allowed is False
    assert "outside" in msg.lower()


@pytest.mark.unit
def test_approval_cached_per_directory(workspace: Path, tmp_path: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    outside_file = str(tmp_path / "data" / "report.csv")

    # First check → blocked
    allowed, _ = pp.check_path(outside_file, "s1")
    assert allowed is False

    # Record approval
    pp.record_approval("s1", outside_file, approved=True)

    # Second check → allowed
    allowed, msg = pp.check_path(outside_file, "s1")
    assert allowed is True
    assert msg == ""


@pytest.mark.unit
def test_denial_cached(workspace: Path, tmp_path: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    outside_file = str(tmp_path / "secrets" / "key.pem")

    pp.record_approval("s1", outside_file, approved=False)
    allowed, msg = pp.check_path(outside_file, "s1")
    assert allowed is False
    assert "denied" in msg.lower()


@pytest.mark.unit
def test_separate_sessions_have_separate_caches(workspace: Path, tmp_path: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    outside_file = str(tmp_path / "shared" / "data.csv")

    # Approve for session 1
    pp.record_approval("s1", outside_file, approved=True)

    # Session 2 should still be blocked
    allowed, _ = pp.check_path(outside_file, "s2")
    assert allowed is False


@pytest.mark.unit
def test_clear_session_removes_approvals(workspace: Path, tmp_path: Path):
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance(str(workspace))
    outside_file = str(tmp_path / "data" / "file.txt")

    pp.record_approval("s1", outside_file, approved=True)
    pp.clear_session("s1")

    allowed, _ = pp.check_path(outside_file, "s1")
    assert allowed is False


# ------------------------------------------------------------------
# No workspace configured → allow all
# ------------------------------------------------------------------


@pytest.mark.unit
def test_no_workspace_allows_all():
    from ag3nt_agent.tool_policy import PathProtection

    pp = PathProtection.get_instance()
    assert pp.is_within_workspace("/any/path/at/all.py")
    allowed, msg = pp.check_path("/whatever.py", "s1")
    assert allowed is True


# ------------------------------------------------------------------
# is_write_operation
# ------------------------------------------------------------------


@pytest.mark.unit
def test_is_write_operation():
    from ag3nt_agent.tool_policy import PathProtection

    assert PathProtection.is_write_operation("write_file")
    assert PathProtection.is_write_operation("edit_file")
    assert PathProtection.is_write_operation("multi_edit")
    assert PathProtection.is_write_operation("apply_patch")
    assert not PathProtection.is_write_operation("read_file")
    assert not PathProtection.is_write_operation("glob_tool")
    assert not PathProtection.is_write_operation("grep_tool")
