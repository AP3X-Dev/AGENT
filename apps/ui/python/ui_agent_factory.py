"""UI-specific agent factory for AG3NT.

This module provides `create_ui_agent()` which wraps the ag3nt_agent runtime
for use with the UI daemon.

The agent is created using the ag3nt_agent.deepagents_runtime module, which
provides a full-featured DeepAgents implementation with:
- Tool approval workflow (HITL)
- Memory system (AGENTS.md, MEMORY.md, daily logs)
- Skills system (bundled, global, workspace skills)
- Subagent system (Researcher, Coder)
- MCP integration

Usage:
    from ui_agent_factory import create_ui_agent

    agent, backend = create_ui_agent(
        model=model,
        assistant_id="agent",
        auto_approve=False,
        checkpointer=checkpointer,
    )
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.pregel import Pregel

# Add ag3nt_agent to the path
ag3nt_agent_path = Path(__file__).parent.parent.parent.parent / "apps" / "agent"
if str(ag3nt_agent_path) not in sys.path:
    sys.path.insert(0, str(ag3nt_agent_path))

logger = logging.getLogger(__name__)


class SimpleBackend:
    """Simple backend placeholder for compatibility."""

    def __init__(self):
        self.cwd = Path.cwd()

    async def close(self):
        pass


def create_ui_agent(
    model: BaseChatModel | None = None,
    assistant_id: str = "agent",
    tools: list[BaseTool] | None = None,
    auto_approve: bool = False,
    enable_web: bool = True,
    enable_utilities: bool = True,
    enable_deep_research: bool = True,
    enable_deep_web: bool = True,
    enable_registry: bool = False,
    checkpointer: BaseCheckpointSaver | None = None,
    **kwargs,
) -> tuple[Pregel, Any]:
    """Create a UI agent using the ag3nt_agent runtime.

    This is a simplified factory that wraps the ag3nt_agent.deepagents_runtime
    for use with the UI daemon.

    Args:
        model: Language model to use. If None, uses runtime default.
        assistant_id: Agent identifier (used for thread management).
        tools: Additional tools to include.
        auto_approve: If True, skip approval for risky tools.
        enable_web: Enable web browsing tools (default: True).
        enable_utilities: Enable utility tools (default: True).
        enable_deep_research: Enable deep research subagent (default: True).
        enable_deep_web: Enable deep web subagent (default: True).
        enable_registry: Enable registry subagent (default: False).
        checkpointer: Custom checkpointer for persistence.
        **kwargs: Additional arguments (ignored for compatibility).

    Returns:
        Tuple of (agent, backend) where agent is the compiled LangGraph agent
        and backend is a simple placeholder for compatibility.
    """
    # Set auto-approve environment variable
    if auto_approve:
        os.environ["AG3NT_AUTO_APPROVE"] = "true"
    else:
        os.environ["AG3NT_AUTO_APPROVE"] = "false"

    # Import the runtime (this triggers model creation and agent building)
    from ag3nt_agent.deepagents_runtime import get_agent, _build_agent

    # Get the agent
    # Note: We rebuild if checkpointer is provided to use custom persistence
    if checkpointer is not None:
        # Build a new agent with the provided checkpointer
        agent = _build_agent_with_checkpointer(checkpointer)
    else:
        agent = get_agent()

    # Create a simple backend for compatibility
    backend = SimpleBackend()

    return agent, backend


def _build_agent_with_checkpointer(checkpointer: BaseCheckpointSaver) -> Pregel:
    """Build an agent with a custom checkpointer.

    This rebuilds the agent with the provided checkpointer instead of
    the default MemorySaver.
    """
    from deepagents import create_deep_agent
    from ag3nt_agent.deepagents_runtime import (
        _create_model,
        _get_repo_root,
        _get_skill_sources,
        _build_backend,
        _get_memory_sources,
        _create_subagents,
        _get_interrupt_on_config,
        _load_mcp_tools,
        _get_summarization_config,
    )
    from ag3nt_agent.shell_middleware import ShellMiddleware
    from ag3nt_agent.planning_middleware import PlanningMiddleware
    from ag3nt_agent.skill_trigger_middleware import SkillTriggerMiddleware
    from ag3nt_agent.context_summarization import create_summarization_middleware
    from langchain.agents.middleware import TodoListMiddleware

    model = _create_model()
    repo_root = _get_repo_root()
    skill_sources = _get_skill_sources(repo_root)
    backend = _build_backend(repo_root)
    memory_sources = _get_memory_sources()
    subagents = _create_subagents()
    interrupt_on = _get_interrupt_on_config()
    mcp_tools = _load_mcp_tools()
    summarization_config = _get_summarization_config()

    # Build middleware stack
    middleware = [
        ShellMiddleware(),
        PlanningMiddleware(),
        SkillTriggerMiddleware(skill_sources=skill_sources),
        create_summarization_middleware(summarization_config),
        TodoListMiddleware(),
    ]

    # Create the agent with custom checkpointer
    agent = create_deep_agent(
        model=model,
        backend=backend,
        checkpointer=checkpointer,
        memory_sources=memory_sources,
        skill_sources=skill_sources,
        subagents=subagents,
        interrupt_on=interrupt_on,
        middleware=middleware,
        additional_tools=mcp_tools,
    )

    return agent
