"""Batch tool execution for AG3NT.

Executes multiple read-only tool calls concurrently using asyncio.gather,
reducing latency for independent operations like reading multiple files
or running multiple searches.

Usage:
    from ag3nt_agent.batch_tool import get_batch_tool

    tool = get_batch_tool()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.batch")

# Maximum concurrent tool calls in a single batch
MAX_BATCH_SIZE = 25

# Tools that are NOT allowed in batch (write/destructive/recursive)
DENIED_TOOLS = frozenset({
    "exec_command",
    "execute",
    "shell",
    "write_file",
    "edit_file",
    "delete_file",
    "apply_patch",
    "git_commit",
    "multi_edit",
    "batch",  # No recursion
    "ask_user",
})


def _resolve_tools() -> dict[str, Any]:
    """Build a name-to-callable mapping of available tools.

    Loads tools from the tool registry and maps them by name.

    Returns:
        Dict mapping tool name to tool callable.
    """
    try:
        from ag3nt_agent.tool_registry import load_tools
        tools = load_tools()
    except Exception:
        tools = []

    tool_map: dict[str, Any] = {}
    for t in tools:
        name = getattr(t, "name", None)
        if name:
            tool_map[name] = t
    return tool_map


async def _invoke_tool(
    tool_callable: Any,
    arguments: dict[str, Any],
) -> Any:
    """Invoke a single tool, handling both sync and async callables."""
    try:
        if asyncio.iscoroutinefunction(getattr(tool_callable, "ainvoke", None)):
            return await tool_callable.ainvoke(arguments)
        elif asyncio.iscoroutinefunction(tool_callable):
            return await tool_callable(**arguments)
        else:
            # Run sync tool in executor to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: tool_callable.invoke(arguments)
            )
    except Exception as e:
        return {"error": str(e)}


@tool
def batch(
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute multiple read-only tool calls concurrently.

    Runs up to 25 tool calls in parallel for faster results on independent
    operations. Only read-only tools are allowed (no file writes, shell
    execution, or destructive operations).

    **Experimental:** This tool is experimental and may change.

    Args:
        tool_calls: List of tool call specifications, each a dict with:
            - tool_name: Name of the tool to call (e.g., "grep_tool", "glob_tool")
            - arguments: Dict of arguments to pass to the tool

    Returns:
        Dictionary with:
            - results: Dict keyed by index (0, 1, ...) with per-call results
            - total: Number of tool calls executed
            - errors: Number of calls that returned errors

    Examples:
        # Read multiple files concurrently
        batch(tool_calls=[
            {"tool_name": "read_file", "arguments": {"path": "src/main.py"}},
            {"tool_name": "read_file", "arguments": {"path": "src/config.py"}},
        ])

        # Run multiple searches in parallel
        batch(tool_calls=[
            {"tool_name": "grep_tool", "arguments": {"pattern": "class.*Error"}},
            {"tool_name": "grep_tool", "arguments": {"pattern": "def handle_"}},
            {"tool_name": "glob_tool", "arguments": {"pattern": "*.py"}},
        ])
    """
    if not tool_calls:
        return {
            "results": {},
            "total": 0,
            "errors": 0,
            "error": "No tool calls provided",
        }

    if len(tool_calls) > MAX_BATCH_SIZE:
        return {
            "results": {},
            "total": 0,
            "errors": 0,
            "error": f"Too many tool calls ({len(tool_calls)}). Maximum is {MAX_BATCH_SIZE}.",
        }

    # Validate all calls before executing any
    for i, call in enumerate(tool_calls):
        name = call.get("tool_name", "")
        if not name:
            return {
                "results": {},
                "total": 0,
                "errors": 0,
                "error": f"Tool call at index {i} is missing 'tool_name'",
            }
        if name in DENIED_TOOLS:
            return {
                "results": {},
                "total": 0,
                "errors": 0,
                "error": f"Tool '{name}' is not allowed in batch (write/destructive/recursive tools are denied)",
            }

    # Resolve tool map
    tool_map = _resolve_tools()

    # Build coroutines
    async def _run_all() -> dict[str, Any]:
        tasks: list[asyncio.Task] = []

        for i, call in enumerate(tool_calls):
            name = call.get("tool_name", "")
            args = call.get("arguments", {})

            tool_fn = tool_map.get(name)
            if tool_fn is None:
                # Create a coroutine that returns an error
                async def _not_found(n=name):
                    return {"error": f"Tool '{n}' not found"}
                tasks.append(asyncio.create_task(_not_found()))
            else:
                tasks.append(asyncio.create_task(_invoke_tool(tool_fn, args)))

        return dict(enumerate(await asyncio.gather(*tasks, return_exceptions=True)))

    # Run the batch
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an async context — use nest_asyncio-style approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                raw_results = pool.submit(lambda: asyncio.run(_run_all())).result()
        else:
            raw_results = loop.run_until_complete(_run_all())
    except RuntimeError:
        raw_results = asyncio.run(_run_all())

    # Format results
    results: dict[str, Any] = {}
    error_count = 0

    for idx, result in raw_results.items():
        if isinstance(result, Exception):
            results[str(idx)] = {"status": "error", "error": str(result)}
            error_count += 1
        elif isinstance(result, dict) and "error" in result:
            results[str(idx)] = {"status": "error", **result}
            error_count += 1
        else:
            results[str(idx)] = {"status": "ok", "result": result}

    return {
        "results": results,
        "total": len(tool_calls),
        "errors": error_count,
    }


def get_batch_tool():
    """Get the batch execution tool for the agent.

    Returns:
        LangChain tool for batch execution
    """
    return batch
