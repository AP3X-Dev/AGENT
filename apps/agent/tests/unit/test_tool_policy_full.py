"""Additional unit tests for tool_policy.py to improve coverage.

Covers ToolPolicy, ToolPolicyManager, and TOOL_GROUPS/PROFILES that
the existing test_path_protection.py does not exercise.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ag3nt_agent.tool_policy import (
    PROFILES,
    TOOL_GROUPS,
    ToolPolicy,
    ToolPolicyManager,
)


# ------------------------------------------------------------------
# ToolPolicy
# ------------------------------------------------------------------


@pytest.mark.unit
class TestToolPolicy:
    def test_defaults(self):
        p = ToolPolicy()
        assert p.allow == []
        assert p.deny == []
        assert p.profile == "coding"

    def test_expand_groups_basic(self):
        p = ToolPolicy(allow=["group:fs"])
        expanded = p._expand_groups(p.allow)
        assert "read_file" in expanded
        assert "write_file" in expanded
        assert "glob_tool" in expanded

    def test_expand_groups_wildcard(self):
        p = ToolPolicy(allow=["*"])
        expanded = p._expand_groups(p.allow)
        assert "*" in expanded

    def test_expand_groups_plain_names(self):
        p = ToolPolicy(allow=["my_custom_tool"])
        expanded = p._expand_groups(p.allow)
        assert "my_custom_tool" in expanded

    def test_is_tool_allowed_wildcard(self):
        p = ToolPolicy(allow=["*"], deny=[])
        assert p.is_tool_allowed("anything") is True

    def test_deny_wins_over_allow(self):
        p = ToolPolicy(allow=["group:fs"], deny=["write_file"])
        assert p.is_tool_allowed("read_file") is True
        assert p.is_tool_allowed("write_file") is False

    def test_explicit_allow(self):
        p = ToolPolicy(allow=["ask_user"], deny=[])
        assert p.is_tool_allowed("ask_user") is True
        assert p.is_tool_allowed("unknown_tool") is False

    def test_no_allow_list_allows_all(self):
        p = ToolPolicy(allow=[], deny=[])
        assert p.is_tool_allowed("anything") is True

    def test_deny_with_group(self):
        p = ToolPolicy(allow=["*"], deny=["group:runtime"])
        assert p.is_tool_allowed("exec_command") is False
        assert p.is_tool_allowed("read_file") is True


# ------------------------------------------------------------------
# Profiles
# ------------------------------------------------------------------


@pytest.mark.unit
class TestProfiles:
    def test_all_profiles_exist(self):
        assert "minimal" in PROFILES
        assert "coding" in PROFILES
        assert "messaging" in PROFILES
        assert "full" in PROFILES

    def test_minimal_denies_runtime(self):
        p = ToolPolicy(**PROFILES["minimal"])
        assert p.is_tool_allowed("exec_command") is False

    def test_coding_allows_runtime(self):
        p = ToolPolicy(**PROFILES["coding"])
        assert p.is_tool_allowed("exec_command") is True

    def test_full_allows_everything(self):
        p = ToolPolicy(**PROFILES["full"])
        assert p.is_tool_allowed("anything_at_all") is True


# ------------------------------------------------------------------
# Tool groups
# ------------------------------------------------------------------


@pytest.mark.unit
class TestToolGroups:
    def test_all_groups_are_lists(self):
        for name, tools in TOOL_GROUPS.items():
            assert isinstance(tools, list), f"{name} should be a list"
            assert all(isinstance(t, str) for t in tools)

    def test_expected_groups_exist(self):
        assert "group:fs" in TOOL_GROUPS
        assert "group:runtime" in TOOL_GROUPS
        assert "group:web" in TOOL_GROUPS
        assert "group:memory" in TOOL_GROUPS
        assert "group:patch" in TOOL_GROUPS
        assert "group:revert" in TOOL_GROUPS


# ------------------------------------------------------------------
# ToolPolicyManager
# ------------------------------------------------------------------


@pytest.mark.unit
class TestToolPolicyManager:
    def test_default_policy_is_coding(self):
        mgr = ToolPolicyManager(config_path="/nonexistent/path.yaml")
        policy = mgr.load_policy()
        assert policy.profile == "coding"

    def test_cached_policy(self):
        mgr = ToolPolicyManager(config_path="/nonexistent/path.yaml")
        p1 = mgr.load_policy()
        p2 = mgr.load_policy()
        assert p1 is p2

    def test_env_override_profile(self):
        with patch.dict(os.environ, {"AG3NT_TOOL_PROFILE": "minimal"}, clear=False):
            mgr = ToolPolicyManager(config_path="/nonexistent/path.yaml")
            policy = mgr.load_policy()
            assert policy.profile == "minimal"

    def test_filter_tools_removes_denied(self):
        mgr = ToolPolicyManager(config_path="/nonexistent/path.yaml")

        class FakeTool:
            def __init__(self, name: str):
                self.name = name

        tools = [FakeTool("read_file"), FakeTool("exec_command"), FakeTool("ask_user")]
        # Default coding profile allows all these
        filtered = mgr.filter_tools(tools)
        assert len(filtered) == 3

    def test_filter_tools_with_minimal_profile(self):
        with patch.dict(os.environ, {"AG3NT_TOOL_PROFILE": "minimal"}, clear=False):
            mgr = ToolPolicyManager(config_path="/nonexistent/path.yaml")

            class FakeTool:
                def __init__(self, name: str):
                    self.name = name

            tools = [FakeTool("read_file"), FakeTool("exec_command"), FakeTool("ask_user")]
            filtered = mgr.filter_tools(tools)
            names = [t.name for t in filtered]
            assert "exec_command" not in names
            assert "read_file" in names
            assert "ask_user" in names

    def test_load_config_returns_none_for_missing_file(self):
        mgr = ToolPolicyManager(config_path="/nonexistent/path.yaml")
        assert mgr._load_config() is None

    def test_load_config_yaml(self, tmp_path: Path):
        config_file = tmp_path / "policy.yaml"
        config_file.write_text("profile: full\n")
        mgr = ToolPolicyManager(config_path=str(config_file))
        policy = mgr.load_policy()
        assert policy.profile == "full"

    def test_load_config_with_allow_deny(self, tmp_path: Path):
        config_file = tmp_path / "policy.yaml"
        config_file.write_text(
            "profile: custom\nallow:\n  - read_file\n  - ask_user\ndeny:\n  - exec_command\n"
        )
        mgr = ToolPolicyManager(config_path=str(config_file))
        policy = mgr.load_policy()
        assert policy.is_tool_allowed("read_file") is True
        assert policy.is_tool_allowed("exec_command") is False

    def test_load_config_invalid_yaml(self, tmp_path: Path):
        config_file = tmp_path / "policy.yaml"
        config_file.write_text("- not\n  a: valid\n    config: [")
        mgr = ToolPolicyManager(config_path=str(config_file))
        # Should fall back to default
        policy = mgr.load_policy()
        assert policy.profile == "coding"
