"""DeepAgents runtime for AG3NT.

This module builds and manages the DeepAgents agent graph,
exposing a simple run_turn() interface for the worker.

Supported model providers:
- anthropic: Claude models (requires ANTHROPIC_API_KEY)
- openai: OpenAI models (requires OPENAI_API_KEY)
- openrouter: OpenRouter proxy (requires OPENROUTER_API_KEY)
- kimi: Moonshot AI models (requires KIMI_API_KEY)
- google: Google Gemini models (requires GOOGLE_API_KEY)

Environment variables:
- AG3NT_MODEL_PROVIDER: Model provider override (if unset, provider is auto-detected by available API keys)
- AG3NT_MODEL_NAME: Model name override (if unset, a provider-specific default is used)
- AG3NT_AUTO_APPROVE: Set to "true" to skip approval for risky tools (default: "false")
- AG3NT_MCP_SERVERS: JSON string with MCP server configuration (optional)
- OPENROUTER_API_KEY: Required when using OpenRouter
- KIMI_API_KEY: Required when using Kimi
- TAVILY_API_KEY: Optional, enables web search for research subagent

Tracing (LangSmith):
- LANGSMITH_API_KEY: LangSmith API key to enable tracing (get one at smith.langchain.com)
- LANGCHAIN_PROJECT: Project name in LangSmith dashboard (default: "ag3nt")
- AG3NT_TRACING_ENABLED: Explicit override to enable/disable ("true"/"false")

When tracing is enabled, all agent runs are logged to LangSmith with:
- Full trace of LLM calls, tool executions, and subagent delegations
- Token usage per call
- Latency metrics
- Error information for debugging

Skills System:
AG3NT loads skills from these locations (in priority order, last wins):
1. Bundled: {repo}/skills/ - shipped with AG3NT
2. Global: ~/.ag3nt/skills/ - user's personal skills
3. Workspace: ./skills/ - project-specific skills

Skills are SKILL.md files in folders. See skills/example-skill for the contract.

Memory System:
AG3NT persists memory to ~/.ag3nt/:
- AGENTS.md - Project context and agent identity
- MEMORY.md - Long-term facts about the user
- memory/ - Daily conversation logs (YYYY-MM-DD.md)
- vectors/ - FAISS index for semantic memory search

The `memory_search` tool provides semantic search over memory files.
Requires embeddings API (uses same key as chat model) and faiss-cpu.

Sub-Agent System:
AG3NT can spawn specialized sub-agents for complex tasks:
- Researcher: Web search and information gathering
- Coder: Code writing, analysis, and execution

MCP (Model Context Protocol) Integration:
AG3NT can load tools from external MCP servers. Configure servers via:
1. Environment variable: AG3NT_MCP_SERVERS (JSON string)
2. Config file: ~/.ag3nt/mcp_servers.json

Example config (follows Claude Desktop / MCP standard format):
{
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
        },
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": "ghp_..."}
        }
    }
}

Approval System:
AG3NT can pause before executing risky tools for human approval.
Risky tools include: execute, shell, write_file, edit_file, delete_file
Set AG3NT_AUTO_APPROVE=true to skip approval (power user mode).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from langchain.agents.middleware import TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from ag3nt_agent.context_summarization import (
    create_summarization_middleware,
    get_default_summarization_config,
)
from ag3nt_agent.shell_middleware import ShellMiddleware
from ag3nt_agent.skill_trigger_middleware import SkillTriggerMiddleware

# =============================================================================
# LANGCHAIN TRACING CONFIGURATION
# =============================================================================
# LangSmith tracing is enabled automatically if LANGSMITH_API_KEY is set.
# Additional env vars:
# - LANGCHAIN_PROJECT: Project name in LangSmith (default: "ag3nt")
# - LANGCHAIN_TRACING_V2: Set to "true" to enable (auto-enabled if API key present)
# - AG3NT_TRACING_ENABLED: Explicit override ("true"/"false") to enable/disable

def _configure_tracing() -> None:
    """Configure LangChain tracing if API key is available.

    This sets up LangSmith tracing for all agent runs, providing:
    - Detailed trace of all LLM calls and tool executions
    - Token usage tracking
    - Latency metrics
    - Debug information for failed runs
    """
    # Check for explicit override
    tracing_override = os.environ.get("AG3NT_TRACING_ENABLED", "").lower()
    if tracing_override == "false":
        logging.getLogger("ag3nt.tracing").info("Tracing explicitly disabled via AG3NT_TRACING_ENABLED=false")
        return

    # Check for LangSmith API key
    langsmith_api_key = os.environ.get("LANGSMITH_API_KEY")

    if langsmith_api_key or tracing_override == "true":
        # Enable LangChain tracing
        os.environ["LANGCHAIN_TRACING_V2"] = "true"

        # Set project name if not already set
        if not os.environ.get("LANGCHAIN_PROJECT"):
            os.environ["LANGCHAIN_PROJECT"] = "ag3nt"

        project = os.environ.get("LANGCHAIN_PROJECT", "ag3nt")
        logging.getLogger("ag3nt.tracing").info(
            f"LangSmith tracing enabled for project: {project}"
        )
    else:
        logging.getLogger("ag3nt.tracing").debug(
            "LangSmith tracing not configured (set LANGSMITH_API_KEY to enable)"
        )

# Initialize tracing on module load
_configure_tracing()

# Lazy import InterruptOnConfig from langchain middleware
try:
    from langchain.agents.middleware import InterruptOnConfig
except ImportError:
    InterruptOnConfig = dict  # Fallback type hint

# Lazy import to avoid import errors if DeepAgents is not installed
_agent: CompiledStateGraph | None = None

# Set up logging for approval events
logger = logging.getLogger("ag3nt.approval")

# =============================================================================
# RISKY TOOL DEFINITIONS
# =============================================================================

# Tools that require human approval before execution (Milestone 5)
RISKY_TOOLS = [
    "execute",        # Execute shell commands
    "shell",          # Run shell commands
    "write_file",     # Write/create files
    "edit_file",      # Modify existing files
    "delete_file",    # Delete files
]

# Tools that are potentially risky but may be allowed in trusted mode
POTENTIALLY_RISKY_TOOLS = [
    "fetch_url",      # Make network requests
    "web_search",     # Search the web
    "task",           # Delegate to subagent
]


def _is_auto_approve_enabled() -> bool:
    """Check if auto-approve mode is enabled.

    Returns:
        True if AG3NT_AUTO_APPROVE is set to "true"
    """
    return os.environ.get("AG3NT_AUTO_APPROVE", "false").lower() == "true"


def _format_tool_description(tool_call: dict, _state: Any = None, _runtime: Any = None) -> str:
    """Format a tool call for human-readable display.

    This function is used as a callback for langgraph's interrupt mechanism,
    which passes (tool_call, state, runtime). When called directly, only
    tool_call is required.

    Args:
        tool_call: The tool call dict with 'name' and 'args'
        _state: Agent state (unused, for callback compatibility)
        _runtime: Runtime instance (unused, for callback compatibility)

    Returns:
        Formatted description string
    """
    name = tool_call.get("name", "unknown")
    args = tool_call.get("args", {})

    if name == "execute":
        command = args.get("command", "N/A")
        return f"🖥️ Execute Command:\n```\n{command}\n```"
    elif name == "shell":
        command = args.get("command", "N/A")
        return f"🖥️ Shell Command:\n```\n{command}\n```"
    elif name == "write_file":
        path = args.get("file_path") or args.get("path", "N/A")
        content = args.get("content", "")
        preview = content[:200] + "..." if len(content) > 200 else content
        return f"📝 Write File: `{path}`\n```\n{preview}\n```"
    elif name == "edit_file":
        path = args.get("file_path") or args.get("path", "N/A")
        return f"✏️ Edit File: `{path}`"
    elif name == "delete_file":
        path = args.get("file_path") or args.get("path", "N/A")
        return f"🗑️ Delete File: `{path}`"
    else:
        return f"🔧 Tool: {name}\nArgs: {args}"


def _get_interrupt_on_config() -> dict[str, bool | dict]:
    """Build interrupt_on configuration for risky tools.

    Returns:
        Dict mapping tool names to interrupt configurations.
        Empty dict if auto-approve is enabled.
    """
    if _is_auto_approve_enabled():
        logger.info("Auto-approve mode enabled - risky tools will run without approval")
        return {}

    # Configure interrupt for each risky tool
    config: dict[str, bool | dict] = {}
    for tool_name in RISKY_TOOLS:
        config[tool_name] = {
            "allowed_decisions": ["approve", "reject"],
            "description": _format_tool_description,
        }

    logger.info(f"Approval required for tools: {', '.join(RISKY_TOOLS)}")
    return config


def _get_model_config() -> tuple[str, str]:
    """Get the model provider and name from environment.

    Returns:
        Tuple of (provider, model_name)
    """
    # Explicit overrides always win
    provider = os.environ.get("AG3NT_MODEL_PROVIDER")
    model = os.environ.get("AG3NT_MODEL_NAME")

    # If either is missing, choose sensible defaults.
    # Prefer OpenRouter when configured (single key, many models).
    if not provider:
        if os.environ.get("OPENROUTER_API_KEY"):
            provider = "openrouter"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("GOOGLE_API_KEY"):
            provider = "google"
        elif os.environ.get("KIMI_API_KEY"):
            provider = "kimi"
        else:
            # Historical default (keeps error messaging consistent elsewhere)
            provider = "anthropic"

    if not model:
        if provider == "openrouter":
            model = "moonshotai/kimi-k2-thinking"
        elif provider == "anthropic":
            model = "claude-sonnet-4-5-20250929"
        elif provider == "openai":
            model = "gpt-4o"
        elif provider == "google":
            model = "gemini-pro"
        elif provider == "kimi":
            model = "kimi-latest"
        else:
            model = "claude-sonnet-4-5-20250929"

    return provider, model


def _create_openrouter_model(model_name: str) -> BaseChatModel:
    """Create a ChatOpenAI instance configured for OpenRouter.

    Args:
        model_name: The model name (e.g., "anthropic/claude-3.5-sonnet", "openai/gpt-4o")

    Returns:
        ChatOpenAI instance configured for OpenRouter

    Raises:
        ValueError: If OPENROUTER_API_KEY is not set
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        msg = (
            "OPENROUTER_API_KEY environment variable is required when using OpenRouter. "
            "Get your API key from https://openrouter.ai/keys"
        )
        raise ValueError(msg)

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/ag3nt",  # Optional, for rankings
            "X-Title": "AG3NT",  # Optional, shows in rankings
        },
    )


def _create_kimi_model(model_name: str) -> BaseChatModel:
    """Create a ChatOpenAI instance configured for Kimi (Moonshot AI).

    Args:
        model_name: The model name (e.g., "moonshot-v1-128k", "moonshot-v1-32k", "kimi-latest")

    Returns:
        ChatOpenAI instance configured for Kimi

    Raises:
        ValueError: If KIMI_API_KEY is not set
    """
    api_key = os.environ.get("KIMI_API_KEY")
    if not api_key:
        msg = (
            "KIMI_API_KEY environment variable is required when using Kimi. "
            "Get your API key from https://platform.moonshot.cn/"
        )
        raise ValueError(msg)

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base="https://api.moonshot.cn/v1",
    )


def _create_model() -> BaseChatModel | str:
    """Create the appropriate model instance based on provider.

    Returns:
        Either a BaseChatModel instance (for OpenRouter, Kimi) or a string
        in "provider:model" format for LangChain's init_chat_model()

    Raises:
        ValueError: If required API keys are missing
    """
    provider, model_name = _get_model_config()

    # OpenRouter requires special handling with custom base URL
    if provider == "openrouter":
        return _create_openrouter_model(model_name)

    # Kimi (Moonshot AI) requires special handling with custom base URL
    if provider == "kimi":
        return _create_kimi_model(model_name)

    # For other providers, use the standard "provider:model" format
    # which will be handled by LangChain's init_chat_model()
    return f"{provider}:{model_name}"


def _get_global_skills_path() -> Path | None:
    """Get the global skills directory path if it exists.

    Returns:
        Path to ~/.ag3nt/skills/ if it exists, else None
    """
    global_skills = Path.home() / ".ag3nt" / "skills"
    if global_skills.exists() and global_skills.is_dir():
        return global_skills
    return None


def _get_user_data_path() -> Path:
    """Get or create the user data directory at ~/.ag3nt/.

    Creates the directory structure if it doesn't exist:
    - ~/.ag3nt/
    - ~/.ag3nt/memory/ (for daily logs)

    Returns:
        Path to ~/.ag3nt/
    """
    user_data = Path.home() / ".ag3nt"
    user_data.mkdir(parents=True, exist_ok=True)
    (user_data / "memory").mkdir(exist_ok=True)
    return user_data


def _get_memory_sources() -> list[str]:
    """Get the memory file sources for MemoryMiddleware.

    Returns paths relative to the CompositeBackend's /user-data/ route.

    Returns:
        List of memory source paths
    """
    # Ensure user data directory exists
    _get_user_data_path()

    return [
        "/user-data/AGENTS.md",  # Project context and identity
        "/user-data/MEMORY.md",  # Long-term facts
    ]


# =============================================================================
# MCP (MODEL CONTEXT PROTOCOL) INTEGRATION
# =============================================================================


def _load_mcp_config() -> dict | None:
    """Load MCP server configuration from config file or environment.

    MCP servers can be configured in two ways (priority order):
    1. Environment variable: AG3NT_MCP_SERVERS (JSON string)
    2. Config file: ~/.ag3nt/mcp_servers.json

    Config format follows the Claude Desktop / MCP standard:
    {
        "mcpServers": {
            "server-name": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
                "env": {"KEY": "value"}  # Optional
            }
        }
    }

    Returns:
        MCP configuration dict or None if not configured
    """
    import json

    # Check environment variable first
    mcp_env = os.environ.get("AG3NT_MCP_SERVERS")
    if mcp_env:
        try:
            config = json.loads(mcp_env)
            logger.info("Loaded MCP config from AG3NT_MCP_SERVERS environment variable")
            return config
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in AG3NT_MCP_SERVERS: {e}")
            return None

    # Check config file
    config_path = Path.home() / ".ag3nt" / "mcp_servers.json"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            logger.info(f"Loaded MCP config from {config_path}")
            return config
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load MCP config from {config_path}: {e}")
            return None

    return None


def _load_mcp_tools() -> list:
    """Load tools from configured MCP servers.

    Uses langchain-mcp-adapters to connect to MCP servers and convert
    their tools to LangChain-compatible tools.

    Returns:
        List of MCP tools (may be empty if no config or errors)
    """
    import asyncio

    config = _load_mcp_config()
    if not config or "mcpServers" not in config:
        return []

    servers = config["mcpServers"]
    if not servers:
        return []

    async def _async_load_mcp_tools() -> list:
        """Async implementation of MCP tool loading."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError:
            logger.warning(
                "langchain-mcp-adapters not installed. MCP tools unavailable. "
                "Install with: pip install langchain-mcp-adapters"
            )
            return []

        try:
            # Convert config to MultiServerMCPClient format
            # The library expects: {"server_name": {"command": ..., "args": ..., "env": ...}}
            server_params = {}
            for name, server_config in servers.items():
                # Allow UI/config tools to mark servers as disabled without removing them.
                if isinstance(server_config, dict) and server_config.get("enabled") is False:
                    logger.info("Skipping disabled MCP server: %s", name)
                    continue
                server_params[name] = {
                    "command": server_config.get("command"),
                    "args": server_config.get("args", []),
                    "env": server_config.get("env"),
                }

            logger.info(f"Connecting to {len(server_params)} MCP server(s): {list(server_params.keys())}")

            async with MultiServerMCPClient(server_params) as mcp_client:
                mcp_tools = mcp_client.get_tools()
                logger.info(f"Loaded {len(mcp_tools)} tool(s) from MCP servers")
                for tool in mcp_tools:
                    logger.debug(f"  - {tool.name}: {tool.description[:50] if tool.description else 'No description'}...")
                return mcp_tools

        except Exception as e:
            logger.error(f"Failed to load MCP tools: {e}")
            return []

    # Run async function synchronously
    try:
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, can't use asyncio.run
            # This shouldn't happen during agent build, but handle it
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _async_load_mcp_tools())
                return future.result(timeout=30)
        except RuntimeError:
            # No running loop, we can use asyncio.run
            return asyncio.run(_async_load_mcp_tools())
    except Exception as e:
        logger.error(f"Error loading MCP tools: {e}")
        return []


# Import the enhanced web search function from web_search module
from ag3nt_agent.web_search import internet_search as _internet_search_impl


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> dict:
    """Search the web for current information.

    Uses Tavily as primary provider with DuckDuckGo fallback.
    Includes caching and rate limiting for efficient API usage.

    Args:
        query: The search query (be specific and detailed)
        max_results: Number of results to return (default: 5)
        topic: "general" for most queries, "news" for current events, "finance" for financial data

    Returns:
        Search results with titles, URLs, content excerpts, and metadata.
    """
    return _internet_search_impl(query, max_results=max_results, topic=topic)


@tool
def fetch_url(
    url: str,
    timeout: int = 30,
) -> dict:
    """Fetch content from a URL and convert HTML to markdown format.

    Use this tool to read web page content. The HTML is automatically converted
    to clean markdown text for easy processing. After receiving the content,
    synthesize the relevant information to answer the user's question.

    Args:
        url: The URL to fetch (must be a valid HTTP/HTTPS URL)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dictionary containing:
        - success: Whether the request succeeded
        - url: The final URL after redirects
        - markdown_content: The page content converted to markdown
        - status_code: HTTP status code
        - content_length: Length of the markdown content
    """
    try:
        import requests
        from markdownify import markdownify

        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AG3NT/1.0; +https://github.com/ag3nt)"
            },
        )
        response.raise_for_status()

        # Convert HTML content to markdown
        markdown_content = markdownify(response.text)

        # Truncate if too long (100KB limit)
        max_length = 100_000
        if len(markdown_content) > max_length:
            markdown_content = markdown_content[:max_length]
            markdown_content += f"\n\n... Content truncated at {max_length} characters."

        return {
            "success": True,
            "url": str(response.url),
            "markdown_content": markdown_content,
            "status_code": response.status_code,
            "content_length": len(markdown_content),
        }
    except ImportError as e:
        return {
            "error": f"Missing dependency: {e}",
            "suggestion": "Install with: pip install requests markdownify",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Fetch URL error: {e!s}",
            "url": url,
        }


# Gateway URL for scheduler API
GATEWAY_URL = os.environ.get("AG3NT_GATEWAY_URL", "http://127.0.0.1:18789")


@tool
def schedule_reminder(
    message: str,
    when: str,
    channel: str | None = None,
) -> dict:
    """Schedule a one-shot reminder to be sent at a specific time.

    Use this tool when the user asks you to remind them about something
    at a specific time or after a duration.

    Args:
        message: The reminder message (what to remind the user about)
        when: When to send the reminder. Can be:
              - Relative time: "in 10 minutes", "in 1 hour", "in 2 days"
              - ISO datetime: "2025-01-27T15:30:00"
        channel: Optional target channel type (e.g., "telegram", "discord")

    Returns:
        Result with job_id if successful, or error message if failed.

    Examples:
        schedule_reminder("Call Alice", "in 30 minutes")
        schedule_reminder("Team meeting", "2025-01-27T14:00:00")
    """
    import requests

    try:
        # Parse relative time to milliseconds if needed
        when_value: str | int = when
        match = re.match(r"^in\s+(\d+)\s+(second|minute|hour|day)s?$", when, re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            multipliers = {"second": 1000, "minute": 60_000, "hour": 3_600_000, "day": 86_400_000}
            when_value = amount * multipliers.get(unit, 60_000)

        response = requests.post(
            f"{GATEWAY_URL}/api/scheduler/reminder",
            json={
                "when": when_value,
                "message": message,
                "channelTarget": channel,
            },
            timeout=10,
        )

        if response.ok:
            data = response.json()
            return {
                "success": True,
                "job_id": data.get("jobId"),
                "message": f"Reminder scheduled: '{message}'",
            }
        else:
            return {
                "success": False,
                "error": f"Gateway returned {response.status_code}: {response.text}",
            }
    except requests.RequestException as e:
        return {
            "success": False,
            "error": f"Failed to connect to Gateway: {e}",
            "suggestion": "Make sure the AG3NT Gateway is running on port 18789",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to schedule reminder: {e}"}


def _create_subagents() -> list[dict]:
    """Create the sub-agent specifications using SubagentRegistry.

    Returns:
        List of SubAgent dicts for all registered subagents.

    The subagent configurations are managed by SubagentRegistry which supports:
    - Builtin subagents (8 predefined types)
    - Plugin-registered subagents
    - User-defined subagents from config files (~/.ag3nt/subagents/)

    Configurations are converted to the dict format expected by DeepAgents SubAgentMiddleware.
    """
    from ag3nt_agent.subagent_registry import SubagentRegistry

    # Get registry and load user-defined configs from ~/.ag3nt/subagents/
    registry = SubagentRegistry.get_instance()
    user_data_path = _get_user_data_path()
    loaded = registry.load_user_configs(user_data_path)
    if loaded > 0:
        logger.info("Loaded %d user-defined subagents from %s/subagents/", loaded, user_data_path)

    # Map tool names to actual tool functions
    # This maps the string tool names in SubagentConfig.tools to actual callable tools
    tool_map: dict = {
        # Research tools
        "internet_search": internet_search,
        "fetch_url": fetch_url,
        # File tools are provided by DeepAgents backend (use empty list = default tools)
        # These are placeholders that signal we need default tools
        "read_file": None,  # Default tool
        "write_file": None,  # Default tool
        "edit_file": None,  # Default tool
        "shell": None,  # Default tool (shell middleware)
        # Git tools - will be added when implemented
        "git_status": None,
        "git_diff": None,
        "git_log": None,
        # Planning tools - will be added when implemented
        "write_todos": None,
        "read_todos": None,
        "update_todo": None,
        # Memory tools
        "memory_search": None,
    }

    # Try to load additional tools that may be available
    try:
        from ag3nt_agent.memory_search import get_memory_search_tool
        tool_map["memory_search"] = get_memory_search_tool()
    except ImportError:
        pass

    subagents = []
    for config in registry.list_all():
        # Convert tool names to actual tool functions
        tools = []
        uses_default_tools = False

        for tool_name in config.tools:
            if tool_name in tool_map:
                tool_func = tool_map[tool_name]
                if tool_func is not None:
                    tools.append(tool_func)
                else:
                    # None means use default tools (filesystem, shell)
                    uses_default_tools = True
            else:
                logger.warning(f"Unknown tool '{tool_name}' in subagent '{config.name}'")

        # If any tool was None (default tool), use empty list to get default tools
        if uses_default_tools and not tools:
            tools = []  # Empty = default tools from DeepAgents

        subagent_dict = {
            "name": config.name,
            "description": config.description,
            "system_prompt": config.system_prompt,
            "tools": tools,
        }
        subagents.append(subagent_dict)

    logger.info("Created %d subagents from registry", len(subagents))
    return subagents


def _get_skill_sources(root_dir: Path) -> list[str]:
    """Discover skill source paths in priority order (last wins).

    AG3NT skill priority (later sources override earlier):
    1. Bundled: {repo}/skills/ - shipped with AG3NT
    2. Global: ~/.ag3nt/skills/ - user's personal skills (via /global-skills/ route)
    3. Workspace: ./.ag3nt/skills/ - project-specific skills

    Args:
        root_dir: The root directory (repo root or cwd)

    Returns:
        List of POSIX-style skill source paths for SkillsMiddleware.
        Note: /global-skills/ is a virtual path routed via CompositeBackend.
    """
    sources: list[str] = []

    # 1. Bundled skills (lowest priority) - repo's skills/ directory
    bundled = root_dir / "skills"
    if bundled.exists() and bundled.is_dir():
        sources.append("/skills/")

    # 2. Global skills (medium priority) - ~/.ag3nt/skills/
    # Accessed via /global-skills/ virtual route in CompositeBackend
    if _get_global_skills_path() is not None:
        sources.append("/global-skills/")

    # 3. Workspace skills (highest priority) - ./.ag3nt/skills/
    # If the workspace has a separate .ag3nt/skills folder, add it
    ag3nt_skills = root_dir / ".ag3nt" / "skills"
    if ag3nt_skills.exists() and ag3nt_skills.is_dir():
        sources.append("/.ag3nt/skills/")

    return sources


def _get_repo_root() -> Path:
    """Get the repository root directory.

    Returns:
        Path to the repo root (where skills/ directory is located)
    """
    # Start from this file and go up to find the repo root
    # This file is at: apps/agent/ag3nt_agent/deepagents_runtime.py
    # Repo root is 4 levels up
    current = Path(__file__).resolve()
    repo_root = current.parent.parent.parent.parent

    # Verify we found the right place by checking for skills/ directory
    if (repo_root / "skills").exists():
        return repo_root

    # Fallback to cwd if structure doesn't match
    return Path.cwd()


def _build_backend(repo_root: Path):
    """Build the backend for DeepAgents with multi-root support.

    Uses CompositeBackend to route:
    - /global-skills/ -> ~/.ag3nt/skills/ (user's global skills)
    - /user-data/ -> ~/.ag3nt/ (memory files and user data)

    Args:
        repo_root: The repository root directory

    Returns:
        Backend configured for file operations, skill discovery, and memory
    """
    from deepagents.backends.composite import CompositeBackend
    from deepagents.backends.filesystem import FilesystemBackend

    # Create default backend rooted at repo for bundled + workspace skills
    default_backend = FilesystemBackend(root_dir=repo_root, virtual_mode=False)

    # Build routes for CompositeBackend
    routes: dict = {}

    # Route for user data (memory, AGENTS.md, etc.) at ~/.ag3nt/
    user_data_path = _get_user_data_path()
    user_data_backend = FilesystemBackend(root_dir=user_data_path, virtual_mode=False)
    routes["/user-data/"] = user_data_backend

    # Route for workspace at ~/.ag3nt/workspace/ (agent's working directory)
    # NOTE: virtual_mode=True is required so paths like /RE/scripts.md (after stripping
    # /workspace/ prefix) are resolved relative to workspace_path, not as absolute paths.
    workspace_path = user_data_path / "workspace"
    workspace_path.mkdir(exist_ok=True)
    workspace_backend = FilesystemBackend(root_dir=workspace_path, virtual_mode=True)
    routes["/workspace/"] = workspace_backend

    # Route for global skills at ~/.ag3nt/skills/ (if exists)
    global_skills_path = _get_global_skills_path()
    if global_skills_path is not None:
        global_backend = FilesystemBackend(root_dir=global_skills_path, virtual_mode=False)
        routes["/global-skills/"] = global_backend

    # Always use CompositeBackend to ensure user-data route is available
    return CompositeBackend(
        default=default_backend,
        routes=routes,
    )


def _build_agent() -> CompiledStateGraph:
    """Build and return the DeepAgents agent graph.

    Returns:
        Configured DeepAgents graph

    Raises:
        ValueError: If required API keys are missing for the selected provider
    """
    from deepagents import create_deep_agent
    from langgraph.checkpoint.memory import MemorySaver

    model = _create_model()

    # Get repo root for skill discovery and file operations
    repo_root = _get_repo_root()

    # Discover available skill sources
    skill_sources = _get_skill_sources(repo_root)

    # Create backend with multi-root support (skills + user data)
    backend = _build_backend(repo_root)

    # Get memory sources (AGENTS.md, MEMORY.md)
    memory_sources = _get_memory_sources()

    # Create sub-agents (Researcher, Coder)
    subagents = _create_subagents()

    # Get interrupt_on configuration for risky tools
    interrupt_on = _get_interrupt_on_config()

    # Create checkpointer for session state (required for interrupt/resume)
    checkpointer = MemorySaver()

    # Create shell middleware for command execution
    # Uses ~/.ag3nt/workspace/ as the working directory
    workspace_path = _get_user_data_path() / "workspace"
    workspace_path.mkdir(exist_ok=True)
    shell_middleware = ShellMiddleware(
        workspace_root=str(workspace_path),
        timeout=60.0,  # 60 second timeout
        max_output_bytes=100_000,  # 100KB output limit
    )

    # Create summarization middleware for context auto-summarization
    # This offloads full history to backend before summarizing to prevent context overflow
    summarization_config = get_default_summarization_config()
    summarization_middleware = create_summarization_middleware(
        config=summarization_config,
        backend=backend,
    )
    if summarization_middleware:
        logger.info(
            f"Summarization middleware enabled: trigger={summarization_config.trigger.description}"
        )

    # Load MCP tools from configured servers
    mcp_tools = _load_mcp_tools()

    # Load memory tools
    memory_tools = []
    try:
        from ag3nt_agent.memory_search import get_memory_search_tool

        memory_tools.append(get_memory_search_tool())
        logger.info("Memory search tool loaded")
    except ImportError as e:
        logger.warning(f"Memory search tool not available: {e}")

    try:
        from ag3nt_agent.memory_summarizer import get_summarize_memory_tool

        memory_tools.append(get_summarize_memory_tool())
        logger.info("Memory summarization tool loaded")
    except ImportError as e:
        logger.warning(f"Memory summarization tool not available: {e}")

    # Load node action tool
    try:
        from ag3nt_agent.node_action_tool import get_node_action_tool
        node_action_tool = get_node_action_tool()
        logger.info("Node action tool loaded")
    except ImportError as e:
        logger.warning(f"Node action tool not available: {e}")
        node_action_tool = None

    # Load skill execution tool
    try:
        from ag3nt_agent.skill_executor import run_skill
        skill_tools = [run_skill]
        logger.info("Skill execution tool loaded")
    except ImportError as e:
        logger.warning(f"Skill execution tool not available: {e}")
        skill_tools = []

    # Load browser control tools
    try:
        from ag3nt_agent.browser_tool import get_browser_tools
        browser_tools = get_browser_tools()
        logger.info(f"Browser control tools loaded ({len(browser_tools)} tools)")
    except ImportError as e:
        logger.warning(f"Browser control tools not available: {e}")
        browser_tools = []

    # Load deep reasoning tool
    reasoning_tools = []
    try:
        from ag3nt_agent.deep_reasoning import get_deep_reasoning_tool
        reasoning_tools = [get_deep_reasoning_tool()]
        logger.info("Deep reasoning tool loaded")
    except ImportError as e:
        logger.warning(f"Deep reasoning tool not available: {e}")

    # Combine custom AG3NT tools with MCP tools, memory tools, skill tools, browser tools, and reasoning tools
    all_tools = [internet_search, fetch_url, schedule_reminder] + mcp_tools + memory_tools + skill_tools + browser_tools + reasoning_tools
    if node_action_tool:
        all_tools.append(node_action_tool)
    if mcp_tools:
        logger.info(f"Agent initialized with {len(mcp_tools)} MCP tool(s)")

    # System prompt with planning, memory, sub-agents, skills, and security
    system_prompt = """You are AG3NT (AP3X), a helpful AI assistant with advanced capabilities.

## File System

**IMPORTANT**: Use virtual paths starting with `/` for all file operations:
- `/workspace/` - Your main working directory for creating files
- `/skills/` - Available skills (read-only)
- `/user-data/` - Persistent user data and memory

Examples:
- To create a file: `/workspace/my_project/file.txt`
- To read a skill: `/skills/example-skill/SKILL.md`

**Never use Windows paths** like `C:\\Users\\...` - they are not supported.

## Planning

For complex tasks with multiple steps, use the `write_todos` tool to:
- Break down the task into clear, actionable steps before starting
- Track your progress by marking items as completed
- Add new items as you discover additional requirements
- This ensures nothing is missed and provides visibility into your work

Use planning for tasks that involve:
- Multiple distinct operations or file changes
- Research followed by action
- Multi-step workflows or processes

## Sub-Agents

You can delegate complex subtasks to specialized agents using the `task` tool:
- **researcher**: Web search and information gathering. Use PROACTIVELY when you need current information, news, statistics, or when answering questions about recent events.
- **coder**: Code writing, analysis, and execution. Use for focused programming tasks.

Sub-agents work in isolation with their own context, then return a synthesized report.
This keeps your context clean and allows deep work on specific subtasks.

## Memory

You have persistent memory stored in files. Use the `memory_search` tool to recall information:
- User preferences and past interactions
- Project context from AGENTS.md
- Relevant facts from MEMORY.md
- Daily conversation logs

This is semantic search - describe what you're looking for naturally, like:
"user's coding style preferences" or "project requirements discussed last week"

## Skills

You have access to skills - modular capabilities that provide specialized knowledge.
Check available skills when the user's request might match a skill's domain.

## Browser Control

You have web automation capabilities through browser tools:
- `browser_navigate(url)` - Navigate to a URL
- `browser_screenshot(full_page, save_path)` - Capture screenshots
- `browser_click(selector)` - Click elements (CSS selectors or text="...")
- `browser_fill(selector, text)` - Fill form fields
- `browser_get_content(selector)` - Extract text from page or element
- `browser_wait_for(selector, state)` - Wait for elements to appear/disappear
- `browser_close()` - Close browser when done

Use these for:
- Web scraping and data extraction
- Form automation and testing
- Taking screenshots for documentation
- Monitoring web pages

The browser runs headless (no visible window). Always close it when done to free resources.

## Security and Permissions

Some tools require human approval before execution. These include:
- `execute` / `shell` - Running shell commands or scripts
- `write_file` / `edit_file` - Writing or modifying files
- `delete_file` - Deleting files

When your execution is paused for approval, the user will see a description of the
action you're attempting. Wait patiently for their decision.

Skills may also declare `required_permissions` in their YAML frontmatter. When using a skill:
1. **Check permissions**: Read the skill's `required_permissions` field before executing
2. **Note sensitive actions**: When a skill requires sensitive permissions, acknowledge this
3. **Proceed with care**: Be conservative with destructive actions

Be concise and helpful."""

    # Build middleware list
    # Note: create_deep_agent already adds TodoListMiddleware internally
    # so we only add AG3NT-specific middleware here to avoid duplicates
    middleware_list = [
        shell_middleware,  # Shell execution capability
        SkillTriggerMiddleware(),  # Skill trigger matching
    ]

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        skills=skill_sources if skill_sources else None,
        memory=memory_sources if memory_sources else None,
        subagents=subagents if subagents else None,
        tools=all_tools,  # Custom AG3NT tools + MCP tools
        middleware=middleware_list,
        backend=backend,
        interrupt_on=interrupt_on if interrupt_on else None,
        checkpointer=checkpointer,
        # Use AG3NT's MonitoredSummarizationMiddleware instead of the default
        # This provides monitoring/metrics for summarization events
        summarization_middleware=summarization_middleware,
    )
    return agent


def get_agent() -> CompiledStateGraph:
    """Get or create the singleton agent instance."""
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


def _extract_interrupt_info(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract interrupt information from agent result.

    Args:
        result: The result from agent.invoke()

    Returns:
        Dict with interrupt details or None if no interrupt
    """
    if "__interrupt__" not in result:
        return None

    interrupts = result["__interrupt__"]
    if not interrupts:
        return None

    # Get the first interrupt
    interrupt = interrupts[0]
    interrupt_id = interrupt.id
    interrupt_value = interrupt.value

    # Extract action requests and review configs
    action_requests = interrupt_value.get("action_requests", [])
    review_configs = interrupt_value.get("review_configs", [])

    # Format pending actions for display
    pending_actions = []
    for action in action_requests:
        tool_name = action.get("name", "unknown")
        tool_args = action.get("args", {})
        description = _format_tool_description({"name": tool_name, "args": tool_args})
        pending_actions.append({
            "tool_name": tool_name,
            "args": tool_args,
            "description": description,
        })

    logger.info(f"Interrupt detected: {len(pending_actions)} actions pending approval")
    for action in pending_actions:
        logger.info(f"  - {action['tool_name']}: {action['args']}")

    return {
        "interrupt_id": interrupt_id,
        "pending_actions": pending_actions,
        "action_count": len(pending_actions),
    }


def _extract_response(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Extract response text and events from agent result.

    Args:
        result: The result from agent.invoke()

    Returns:
        Tuple of (response_text, events)
    """
    response_messages = result.get("messages", [])
    events: list[dict[str, Any]] = []
    response_text = ""

    for msg in reversed(response_messages):
        if isinstance(msg, AIMessage):
            # Extract text content
            if isinstance(msg.content, str):
                response_text = msg.content
            elif isinstance(msg.content, list):
                # Handle content blocks
                text_parts = []
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                response_text = "\n".join(text_parts)

            # Extract tool calls as events
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    events.append({
                        "tool_name": tc.get("name", "unknown"),
                        "input": tc.get("args", {}),
                        "status": "completed",
                    })
            break

    return response_text or "No response generated.", events


def _extract_usage_info(result: dict[str, Any]) -> dict[str, Any]:
    """Extract token usage information from agent result.

    This aggregates usage across all LLM calls in the turn,
    which is then reported to the Gateway for tracking.

    Args:
        result: The agent's result dictionary containing messages

    Returns:
        Dict with usage info: input_tokens, output_tokens, model, provider
    """
    provider, model_name = _get_model_config()
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "model": model_name,
        "provider": provider,
    }

    messages = result.get("messages", [])

    for msg in messages:
        # LangChain messages may have usage_metadata or response_metadata
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            meta = msg.usage_metadata
            usage["input_tokens"] += meta.get("input_tokens", 0)
            usage["output_tokens"] += meta.get("output_tokens", 0)
        elif hasattr(msg, "response_metadata") and msg.response_metadata:
            meta = msg.response_metadata
            if "usage" in meta:
                u = meta["usage"]
                usage["input_tokens"] += u.get("input_tokens", u.get("prompt_tokens", 0))
                usage["output_tokens"] += u.get("output_tokens", u.get("completion_tokens", 0))

    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage


def run_turn(
    session_id: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a single turn of conversation with the agent.

    Args:
        session_id: Unique identifier for the session/conversation.
        text: The user's input text.
        metadata: Optional metadata for the turn.

    Returns:
        A dict containing:
            - session_id: The session ID
            - text: The agent's response text
            - events: List of tool call events (if any)
            - interrupt: Dict with interrupt details (if paused for approval)
    """
    agent = get_agent()

    # Set session context for deep reasoning tool
    try:
        from ag3nt_agent.deep_reasoning import set_current_session_id
        set_current_session_id(session_id)
    except ImportError:
        pass

    # Build the input messages
    messages = [HumanMessage(content=text)]

    # Configure the run with session-specific thread_id for checkpointing
    config = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    # Invoke the agent
    try:
        result = agent.invoke({"messages": messages}, config=config)
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return {
            "session_id": session_id,
            "text": f"Error: {e!s}",
            "events": [],
        }

    # Check for interrupt (approval required)
    interrupt_info = _extract_interrupt_info(result)
    if interrupt_info:
        # Format the pending actions for the user
        action_text = "\n\n".join(
            action["description"] for action in interrupt_info["pending_actions"]
        )
        return {
            "session_id": session_id,
            "text": f"⏸️ **Approval Required**\n\nI need your permission to proceed with the following action(s):\n\n{action_text}\n\nReply with **approve** or **reject**.",
            "events": [],
            "interrupt": interrupt_info,
        }

    # Extract response
    response_text, events = _extract_response(result)

    # Extract usage information from response metadata
    usage = _extract_usage_info(result)

    return {
        "session_id": session_id,
        "text": response_text,
        "events": events,
        "usage": usage,
    }


def resume_turn(
    session_id: str,
    decisions: list[dict[str, str]],
) -> dict[str, Any]:
    """Resume an interrupted turn after user approval/rejection.

    Args:
        session_id: The session ID of the interrupted turn.
        decisions: List of decisions, each with {"type": "approve"} or {"type": "reject"}

    Returns:
        A dict containing:
            - session_id: The session ID
            - text: The agent's response text
            - events: List of tool call events (if any)
            - interrupt: Dict with interrupt details (if another approval is needed)
    """
    agent = get_agent()

    # Log the decision
    decision_types = [d.get("type", "unknown") for d in decisions]
    logger.info(f"Resuming session {session_id} with decisions: {decision_types}")

    # Configure the run with session-specific thread_id
    config = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    # Resume with the decisions
    try:
        result = agent.invoke(
            Command(resume={"decisions": decisions}),
            config=config,
        )
    except Exception as e:
        logger.error(f"Resume error: {e}")
        return {
            "session_id": session_id,
            "text": f"Error resuming: {e!s}",
            "events": [],
        }

    # Check for another interrupt
    interrupt_info = _extract_interrupt_info(result)
    if interrupt_info:
        action_text = "\n\n".join(
            action["description"] for action in interrupt_info["pending_actions"]
        )
        return {
            "session_id": session_id,
            "text": f"⏸️ **Approval Required**\n\nI need your permission to proceed with the following action(s):\n\n{action_text}\n\nReply with **approve** or **reject**.",
            "events": [],
            "interrupt": interrupt_info,
        }

    # Extract response
    response_text, events = _extract_response(result)

    # Extract usage information from response metadata
    usage = _extract_usage_info(result)

    return {
        "session_id": session_id,
        "text": response_text,
        "events": events,
        "usage": usage,
    }
