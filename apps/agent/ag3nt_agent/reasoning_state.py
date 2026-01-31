"""Structured Reasoning State for AG3NT.

This module provides periodic structured summarization of agent reasoning,
extracting key decision points, outcomes, and learnings for efficient
context preservation.

Features:
- Extraction of reasoning steps from conversation
- Structured format for decisions, actions, outcomes
- Periodic summarization based on message count or tokens
- Integration with memory system

Usage:
    from ag3nt_agent.reasoning_state import ReasoningStateSummarizer

    summarizer = ReasoningStateSummarizer()
    summary = summarizer.summarize_reasoning(messages)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

logger = logging.getLogger(__name__)

# Summarization settings
DEFAULT_INTERVAL_MESSAGES = 20  # Summarize every N messages
DEFAULT_INTERVAL_TOKENS = 5000  # Or every N tokens
MAX_REASONING_STEPS = 10  # Max steps to extract per interval


class ReasoningType(str, Enum):
    """Type of reasoning step."""

    DECISION = "decision"  # A choice or decision made
    ACTION = "action"  # An action taken (tool call)
    OBSERVATION = "observation"  # An observation from tool output
    CONCLUSION = "conclusion"  # A conclusion or learning
    QUESTION = "question"  # A question asked to clarify
    PLAN = "plan"  # A plan or strategy formulated


@dataclass
class ReasoningStep:
    """A single reasoning step extracted from conversation.

    Attributes:
        step_type: Type of reasoning (decision, action, etc.)
        content: The reasoning content
        tool_name: Tool used (if action type)
        timestamp: When this step occurred
        importance: Importance score (0-1)
    """

    step_type: ReasoningType
    content: str
    tool_name: str | None = None
    timestamp: str = ""
    importance: float = 0.5

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class ReasoningState:
    """Structured state of agent reasoning.

    Attributes:
        session_id: Session identifier
        steps: List of reasoning steps
        current_goal: Current goal being pursued
        completed_goals: List of completed goals
        pending_questions: Unanswered questions
        key_facts: Important facts discovered
        last_updated: Last update timestamp
    """

    session_id: str
    steps: list[ReasoningStep] = field(default_factory=list)
    current_goal: str | None = None
    completed_goals: list[str] = field(default_factory=list)
    pending_questions: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    last_updated: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now(UTC).isoformat()

    def to_summary(self) -> str:
        """Convert reasoning state to a compact summary string."""
        parts = []

        if self.current_goal:
            parts.append(f"Current Goal: {self.current_goal}")

        if self.completed_goals:
            parts.append(f"Completed: {', '.join(self.completed_goals[-3:])}")

        if self.key_facts:
            parts.append("Key Facts:")
            for fact in self.key_facts[-5:]:
                parts.append(f"  - {fact}")

        if self.steps:
            parts.append("Recent Reasoning:")
            for step in self.steps[-5:]:
                prefix = step.step_type.value.upper()
                parts.append(f"  [{prefix}] {step.content[:100]}")

        if self.pending_questions:
            parts.append(f"Pending: {', '.join(self.pending_questions[-2:])}")

        return "\n".join(parts)


class ReasoningStateSummarizer:
    """Extracts and summarizes structured reasoning from conversations."""

    def __init__(
        self,
        interval_messages: int = DEFAULT_INTERVAL_MESSAGES,
        interval_tokens: int = DEFAULT_INTERVAL_TOKENS,
        max_steps: int = MAX_REASONING_STEPS,
    ) -> None:
        """Initialize the reasoning state summarizer.

        Args:
            interval_messages: Summarize every N messages
            interval_tokens: Or every N tokens
            max_steps: Maximum reasoning steps per summary
        """
        self._interval_messages = interval_messages
        self._interval_tokens = interval_tokens
        self._max_steps = max_steps
        self._message_count = 0
        self._token_count = 0
        self._states: dict[str, ReasoningState] = {}

    def _should_summarize(self, messages: list[AnyMessage]) -> bool:
        """Check if summarization should be triggered."""
        msg_count = len(messages)
        token_count = count_tokens_approximately(messages)

        return (
            msg_count >= self._interval_messages
            or token_count >= self._interval_tokens
        )

    def _extract_goal_from_message(self, msg: HumanMessage) -> str | None:
        """Extract goal from a human message if present."""
        content = str(msg.content)
        # Look for explicit goal statements
        goal_patterns = [
            "i want to", "i need to", "please help me", "can you",
            "let's", "we need to", "the goal is", "objective:",
        ]
        content_lower = content.lower()
        for pattern in goal_patterns:
            if pattern in content_lower:
                # Return first sentence as goal
                sentences = content.split(".")
                if sentences:
                    return sentences[0].strip()[:200]
        return None

    def _extract_step_from_ai(self, msg: AIMessage) -> ReasoningStep | None:
        """Extract reasoning step from AI message."""
        content = str(msg.content) if msg.content else ""

        # Check for tool calls - these are actions
        if msg.tool_calls:
            tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
            return ReasoningStep(
                step_type=ReasoningType.ACTION,
                content=f"Called tools: {', '.join(tool_names)}",
                tool_name=tool_names[0] if tool_names else None,
            )

        # Check for decision language
        decision_markers = ["i'll", "i will", "let me", "i'm going to", "decided to"]
        content_lower = content.lower()
        for marker in decision_markers:
            if marker in content_lower:
                return ReasoningStep(
                    step_type=ReasoningType.DECISION,
                    content=content[:200],
                )

        # Check for conclusion language
        conclusion_markers = ["therefore", "in conclusion", "this means", "so the"]
        for marker in conclusion_markers:
            if marker in content_lower:
                return ReasoningStep(
                    step_type=ReasoningType.CONCLUSION,
                    content=content[:200],
                    importance=0.8,
                )

        return None

    def _extract_step_from_tool(self, msg: ToolMessage) -> ReasoningStep | None:
        """Extract reasoning step from tool message."""
        content = str(msg.content) if msg.content else ""
        tool_name = msg.name or "unknown"

        # Truncate large outputs
        if len(content) > 200:
            content = content[:200] + "..."

        return ReasoningStep(
            step_type=ReasoningType.OBSERVATION,
            content=f"[{tool_name}] {content}",
            tool_name=tool_name,
        )

    def extract_steps(
        self,
        messages: list[AnyMessage],
        session_id: str = "default",
    ) -> list[ReasoningStep]:
        """Extract reasoning steps from messages.

        Args:
            messages: List of messages to analyze
            session_id: Session identifier

        Returns:
            List of extracted reasoning steps
        """
        steps = []

        for msg in messages:
            step = None
            if isinstance(msg, HumanMessage):
                goal = self._extract_goal_from_message(msg)
                if goal:
                    step = ReasoningStep(
                        step_type=ReasoningType.PLAN,
                        content=goal,
                        importance=0.7,
                    )
            elif isinstance(msg, AIMessage):
                step = self._extract_step_from_ai(msg)
            elif isinstance(msg, ToolMessage):
                step = self._extract_step_from_tool(msg)

            if step:
                steps.append(step)

            if len(steps) >= self._max_steps:
                break

        return steps

    def get_or_create_state(self, session_id: str) -> ReasoningState:
        """Get existing state or create new one for session."""
        if session_id not in self._states:
            self._states[session_id] = ReasoningState(session_id=session_id)
        return self._states[session_id]

    def update_state(
        self,
        messages: list[AnyMessage],
        session_id: str = "default",
    ) -> ReasoningState:
        """Update reasoning state from messages.

        Args:
            messages: List of messages to analyze
            session_id: Session identifier

        Returns:
            Updated ReasoningState
        """
        state = self.get_or_create_state(session_id)

        # Extract new steps
        new_steps = self.extract_steps(messages, session_id)
        state.steps.extend(new_steps)

        # Trim to max steps
        if len(state.steps) > self._max_steps * 2:
            state.steps = state.steps[-self._max_steps:]

        # Extract goal from first human message if not set
        if not state.current_goal:
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    goal = self._extract_goal_from_message(msg)
                    if goal:
                        state.current_goal = goal
                        break

        state.last_updated = datetime.now(UTC).isoformat()
        return state

    def summarize_reasoning(
        self,
        messages: list[AnyMessage],
        session_id: str = "default",
    ) -> str:
        """Generate a structured reasoning summary.

        Args:
            messages: List of messages to analyze
            session_id: Session identifier

        Returns:
            Formatted reasoning summary string
        """
        state = self.update_state(messages, session_id)
        return state.to_summary()

    def should_summarize_and_update(
        self,
        messages: list[AnyMessage],
        session_id: str = "default",
    ) -> tuple[bool, str | None]:
        """Check if summarization needed and return summary if so.

        Args:
            messages: List of messages to analyze
            session_id: Session identifier

        Returns:
            Tuple of (should_summarize, summary_if_applicable)
        """
        if not self._should_summarize(messages):
            return False, None

        summary = self.summarize_reasoning(messages, session_id)
        return True, summary

    def clear_state(self, session_id: str) -> None:
        """Clear reasoning state for a session."""
        if session_id in self._states:
            del self._states[session_id]


# Global summarizer instance
_reasoning_summarizer: ReasoningStateSummarizer | None = None


def get_reasoning_summarizer() -> ReasoningStateSummarizer:
    """Get the global reasoning state summarizer."""
    global _reasoning_summarizer
    if _reasoning_summarizer is None:
        _reasoning_summarizer = ReasoningStateSummarizer()
    return _reasoning_summarizer


def reset_reasoning_summarizer() -> None:
    """Reset the global reasoning summarizer (for testing)."""
    global _reasoning_summarizer
    _reasoning_summarizer = None

