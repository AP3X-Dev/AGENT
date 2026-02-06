"""Unit tests for tool_registry module."""

import pytest
from unittest.mock import patch, MagicMock

from ag3nt_agent.tool_registry import TOOL_REGISTRY, load_tools


class TestToolRegistry:
    """Tests for TOOL_REGISTRY constant."""

    def test_registry_is_list(self):
        """Test that TOOL_REGISTRY is a list."""
        assert isinstance(TOOL_REGISTRY, list)

    def test_registry_entries_are_tuples(self):
        """Test that each entry is a 3-tuple."""
        for entry in TOOL_REGISTRY:
            assert isinstance(entry, tuple)
            assert len(entry) == 3

    def test_registry_entry_types(self):
        """Test that each entry has (str, str, str)."""
        for name, module_path, func_name in TOOL_REGISTRY:
            assert isinstance(name, str)
            assert isinstance(module_path, str)
            assert isinstance(func_name, str)

    def test_registry_has_expected_entries(self):
        """Test that critical tools are registered."""
        names = {entry[0] for entry in TOOL_REGISTRY}
        expected = {
            "memory_search",
            "glob",
            "grep",
            "exec_command",
            "process",
            "apply_patch",
            "git",
            "planning",
            "sessions",
        }
        for name in expected:
            assert name in names, f"Missing registry entry: {name}"

    def test_git_entry(self):
        """Test git tool registry entry."""
        git_entries = [(n, m, f) for n, m, f in TOOL_REGISTRY if n == "git"]
        assert len(git_entries) == 1
        _, module_path, func_name = git_entries[0]
        assert module_path == "ag3nt_agent.git_tool"
        assert func_name == "get_git_tools"

    def test_planning_entry(self):
        """Test planning tool registry entry."""
        entries = [(n, m, f) for n, m, f in TOOL_REGISTRY if n == "planning"]
        assert len(entries) == 1
        _, module_path, func_name = entries[0]
        assert module_path == "ag3nt_agent.planning_tools"
        assert func_name == "get_planning_tools"

    def test_sessions_entry(self):
        """Test sessions tool registry entry."""
        entries = [(n, m, f) for n, m, f in TOOL_REGISTRY if n == "sessions"]
        assert len(entries) == 1
        _, module_path, func_name = entries[0]
        assert module_path == "ag3nt_agent.session_tools"
        assert func_name == "get_session_tools"


class TestLoadTools:
    """Tests for load_tools function."""

    def test_load_tools_returns_list(self):
        """Test that load_tools returns a list."""
        # Use a minimal registry to avoid import issues
        tools = load_tools(registry=[])
        assert isinstance(tools, list)
        assert len(tools) == 0

    def test_load_tools_handles_import_error(self):
        """Test that load_tools gracefully handles ImportError."""
        registry = [("bad_tool", "nonexistent.module", "get_tool")]
        tools = load_tools(registry=registry)
        assert isinstance(tools, list)
        assert len(tools) == 0

    def test_load_tools_with_list_result(self):
        """Test that load_tools flattens list results."""
        mock_tool_1 = MagicMock()
        mock_tool_2 = MagicMock()
        result_list = [mock_tool_1, mock_tool_2]

        mock_getter = MagicMock(return_value=result_list)
        # Remove 'name' attr so load_tools treats it as callable (not a tool)
        del mock_getter.name

        mock_module = MagicMock()
        mock_module.get_tools = mock_getter

        with patch("importlib.import_module", return_value=mock_module):
            tools = load_tools(registry=[("test", "test.module", "get_tools")])
            assert len(tools) == 2

    def test_load_tools_with_single_result(self):
        """Test that load_tools appends single tool results."""
        mock_tool = MagicMock()

        mock_getter = MagicMock(return_value=mock_tool)
        # Remove 'name' attr so load_tools treats it as callable (not a tool)
        del mock_getter.name

        mock_module = MagicMock()
        mock_module.get_tool = mock_getter

        with patch("importlib.import_module", return_value=mock_module):
            tools = load_tools(registry=[("test", "test.module", "get_tool")])
            assert len(tools) == 1

    def test_load_tools_with_policy_filter(self):
        """Test that tool policy filters denied tools."""
        mock_policy = MagicMock()
        mock_policy.is_allowed.return_value = False

        # Even with a valid registry entry, denied tools should be skipped
        tools = load_tools(
            registry=[("denied_tool", "ag3nt_agent.git_tool", "get_git_tools")],
            tool_policy=mock_policy,
        )
        assert len(tools) == 0
        mock_policy.is_allowed.assert_called_once_with("denied_tool")

    def test_load_git_tools_from_registry(self):
        """Test that git tools load successfully from registry."""
        registry = [("git", "ag3nt_agent.git_tool", "get_git_tools")]
        tools = load_tools(registry=registry)
        assert len(tools) == 7
        tool_names = {t.name for t in tools}
        assert "git_status" in tool_names
        assert "git_diff" in tool_names

    def test_load_planning_tools_from_registry(self):
        """Test that planning tools load successfully from registry."""
        registry = [("planning", "ag3nt_agent.planning_tools", "get_planning_tools")]
        tools = load_tools(registry=registry)
        assert len(tools) == 3
        tool_names = {t.name for t in tools}
        assert "write_todos" in tool_names

    def test_load_session_tools_from_registry(self):
        """Test that session tools load successfully from registry."""
        registry = [("sessions", "ag3nt_agent.session_tools", "get_session_tools")]
        tools = load_tools(registry=registry)
        assert len(tools) == 3
        tool_names = {t.name for t in tools}
        assert "sessions_list" in tool_names
