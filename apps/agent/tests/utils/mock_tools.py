"""Mock tool execution utilities for testing.

Provides MockToolExecutor and MockToolResult for testing tool middleware.
"""
from dataclasses import dataclass, field
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock


@dataclass
class MockToolResult:
    """Result from a mock tool execution."""
    success: bool = True
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MockToolExecutor:
    """Mock tool executor for testing tool middleware.
    
    Usage:
        executor = MockToolExecutor()
        executor.set_result("shell", MockToolResult(output="done"))
        result = await executor.execute("shell", {"command": "ls"})
    """
    
    def __init__(self) -> None:
        self._results: dict[str, MockToolResult] = {}
        self._default_result = MockToolResult(success=True, output="Mock output")
        self._call_history: list[dict[str, Any]] = []
        self._execute = AsyncMock(side_effect=self._get_result)
    
    def set_result(self, tool_name: str, result: MockToolResult) -> "MockToolExecutor":
        """Set the result for a specific tool."""
        self._results[tool_name] = result
        return self
    
    def set_error(self, tool_name: str, error: str) -> "MockToolExecutor":
        """Set an error result for a specific tool."""
        self._results[tool_name] = MockToolResult(
            success=False,
            error=error,
        )
        return self
    
    def set_default_result(self, result: MockToolResult) -> "MockToolExecutor":
        """Set the default result for tools without specific results."""
        self._default_result = result
        return self
    
    async def _get_result(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        **kwargs: Any,
    ) -> MockToolResult:
        """Get the result for a tool execution."""
        self._call_history.append({
            "tool_name": tool_name,
            "tool_input": tool_input,
            "kwargs": kwargs,
        })
        return self._results.get(tool_name, self._default_result)
    
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        **kwargs: Any,
    ) -> MockToolResult:
        """Execute a mock tool."""
        return await self._execute(tool_name, tool_input, **kwargs)
    
    @property
    def call_count(self) -> int:
        """Number of times execute was called."""
        return len(self._call_history)
    
    @property
    def last_call(self) -> dict[str, Any] | None:
        """Get the arguments from the last call."""
        return self._call_history[-1] if self._call_history else None
    
    def get_calls_for_tool(self, tool_name: str) -> list[dict[str, Any]]:
        """Get all calls for a specific tool."""
        return [c for c in self._call_history if c["tool_name"] == tool_name]
    
    def reset(self) -> None:
        """Reset the mock to initial state."""
        self._results = {}
        self._call_history = []
        self._execute.reset_mock()


def create_mock_tool_runtime(
    tool_call_id: str = "test-tool-call-001",
    context: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock tool runtime for middleware testing."""
    runtime = MagicMock()
    runtime.tool_call_id = tool_call_id
    runtime.context = context or {}
    runtime.session_id = "test-session-001"
    runtime.approved = True
    return runtime

