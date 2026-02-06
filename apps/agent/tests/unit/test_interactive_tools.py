"""Unit tests for interactive_tools.py."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_ask_user_returns_pending():
    from ag3nt_agent.interactive_tools import ask_user
    result = ask_user.invoke({"question": "Pick one", "options": ["A", "B"]})
    assert isinstance(result, str)
    assert "pending" in result.lower() or "resume" in result.lower()


@pytest.mark.unit
def test_ask_user_no_options():
    from ag3nt_agent.interactive_tools import ask_user
    result = ask_user.invoke({"question": "What is your name?"})
    assert isinstance(result, str)


@pytest.mark.unit
def test_get_interactive_tools():
    from ag3nt_agent.interactive_tools import get_interactive_tools
    tools = get_interactive_tools()
    assert isinstance(tools, list)
    assert len(tools) == 1
    assert tools[0].name == "ask_user"
