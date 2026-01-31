"""Mock LLM classes for testing agent interactions.

Provides MockLLM that can simulate various LLM responses without API calls.
"""
from dataclasses import dataclass, field
from typing import Any, Callable
from unittest.mock import AsyncMock


@dataclass
class MockLLMResponse:
    """Simulated LLM response."""
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = "mock-model"
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 100,
        "output_tokens": 50,
    })


class MockLLM:
    """Mock LLM client for testing.
    
    Usage:
        mock_llm = MockLLM()
        mock_llm.set_response("Hello!")
        response = await mock_llm.generate("Hi")
        assert response.content == "Hello!"
    """
    
    def __init__(self) -> None:
        self._responses: list[MockLLMResponse] = []
        self._response_index = 0
        self._call_history: list[dict[str, Any]] = []
        self._generate = AsyncMock(side_effect=self._get_response)
    
    def set_response(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        stop_reason: str = "end_turn",
    ) -> "MockLLM":
        """Set a single response for the next call."""
        self._responses = [MockLLMResponse(
            content=content,
            tool_calls=tool_calls or [],
            stop_reason=stop_reason,
        )]
        self._response_index = 0
        return self
    
    def set_responses(self, responses: list[MockLLMResponse]) -> "MockLLM":
        """Set multiple responses for sequential calls."""
        self._responses = responses
        self._response_index = 0
        return self
    
    def set_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str = "test-tool-001",
    ) -> "MockLLM":
        """Set a response that includes a tool call."""
        self._responses = [MockLLMResponse(
            content="",
            tool_calls=[{
                "id": tool_use_id,
                "name": tool_name,
                "input": tool_input,
            }],
            stop_reason="tool_use",
        )]
        self._response_index = 0
        return self
    
    async def _get_response(self, *args: Any, **kwargs: Any) -> MockLLMResponse:
        """Get the next response in the sequence."""
        self._call_history.append({"args": args, "kwargs": kwargs})
        
        if not self._responses:
            return MockLLMResponse(content="Default mock response")
        
        response = self._responses[self._response_index]
        if self._response_index < len(self._responses) - 1:
            self._response_index += 1
        return response
    
    async def generate(self, *args: Any, **kwargs: Any) -> MockLLMResponse:
        """Generate a mock LLM response."""
        return await self._generate(*args, **kwargs)
    
    @property
    def call_count(self) -> int:
        """Number of times generate was called."""
        return len(self._call_history)
    
    @property
    def last_call(self) -> dict[str, Any] | None:
        """Get the arguments from the last call."""
        return self._call_history[-1] if self._call_history else None
    
    def reset(self) -> None:
        """Reset the mock to initial state."""
        self._responses = []
        self._response_index = 0
        self._call_history = []
        self._generate.reset_mock()


def create_mock_response(
    content: str = "Test response",
    tool_calls: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
) -> MockLLMResponse:
    """Factory function to create a MockLLMResponse."""
    return MockLLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        stop_reason=stop_reason,
    )

