"""Context auto-summarization for AG3NT.

This module provides automatic summarization of conversation context to prevent
context window overflow while preserving important information.

Features:
- Configurable trigger thresholds (tokens, messages, context fraction)
- History offloading to backend before summarization
- Summarization monitoring with metrics tracking
- Integration with DeepAgents SummarizationMiddleware

Usage:
    from ag3nt_agent.context_summarization import (
        create_summarization_middleware,
        SummarizationConfig,
        SummarizationMonitor,
    )

    config = SummarizationConfig(
        trigger_fraction=0.85,
        keep_messages=20,
    )
    middleware = create_summarization_middleware(config, backend)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AnyMessage
from langchain_core.messages.utils import count_tokens_approximately

if TYPE_CHECKING:
    from deepagents.backends.protocol import BACKEND_TYPES
    from deepagents.middleware.summarization import SummarizationMiddleware

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    """Type of summarization trigger."""

    TOKENS = "tokens"  # Trigger at token count threshold
    MESSAGES = "messages"  # Trigger at message count threshold
    FRACTION = "fraction"  # Trigger at context window fraction


@dataclass
class SummarizationTrigger:
    """Configuration for when to trigger summarization.

    Supports multiple trigger types that can be combined:
    - tokens: Absolute token count threshold
    - messages: Message count threshold
    - fraction: Fraction of context window (0.0-1.0)

    Attributes:
        trigger_type: Type of trigger (tokens, messages, or fraction)
        threshold: The threshold value for the trigger
        description: Human-readable description of the trigger
    """

    trigger_type: TriggerType
    threshold: float | int
    description: str = ""

    def __post_init__(self) -> None:
        """Validate trigger configuration."""
        if self.trigger_type == TriggerType.FRACTION:
            if not 0.0 < self.threshold <= 1.0:
                raise ValueError(f"Fraction threshold must be between 0 and 1, got {self.threshold}")
        elif self.trigger_type == TriggerType.TOKENS:
            if self.threshold < 100:
                raise ValueError(f"Token threshold must be at least 100, got {self.threshold}")
        elif self.trigger_type == TriggerType.MESSAGES:
            if self.threshold < 2:
                raise ValueError(f"Message threshold must be at least 2, got {self.threshold}")

        if not self.description:
            self.description = f"Trigger at {self.threshold} {self.trigger_type.value}"

    def to_context_size(self) -> tuple[str, float | int]:
        """Convert to DeepAgents ContextSize tuple format.

        Returns:
            Tuple of (type_string, threshold_value)
        """
        return (self.trigger_type.value, self.threshold)


# Preset triggers for common use cases
TRIGGER_CONSERVATIVE = SummarizationTrigger(
    trigger_type=TriggerType.FRACTION,
    threshold=0.90,
    description="Conservative: trigger at 90% context window",
)

TRIGGER_BALANCED = SummarizationTrigger(
    trigger_type=TriggerType.FRACTION,
    threshold=0.80,
    description="Balanced: trigger at 80% context window",
)

TRIGGER_AGGRESSIVE = SummarizationTrigger(
    trigger_type=TriggerType.FRACTION,
    threshold=0.65,
    description="Aggressive: trigger at 65% context window",
)

TRIGGER_MESSAGE_BASED = SummarizationTrigger(
    trigger_type=TriggerType.MESSAGES,
    threshold=50,
    description="Message-based: trigger at 50 messages",
)

TRIGGER_TOKEN_BASED = SummarizationTrigger(
    trigger_type=TriggerType.TOKENS,
    threshold=100000,
    description="Token-based: trigger at 100K tokens",
)


@dataclass
class RetentionPolicy:
    """Configuration for what to keep after summarization.

    Attributes:
        policy_type: Type of retention (messages, tokens, or fraction)
        value: The retention value
    """

    policy_type: TriggerType
    value: float | int

    def __post_init__(self) -> None:
        """Validate retention configuration."""
        if self.policy_type == TriggerType.FRACTION:
            if not 0.0 < self.value < 1.0:
                raise ValueError(f"Retention fraction must be between 0 and 1, got {self.value}")
        elif self.policy_type == TriggerType.MESSAGES:
            if self.value < 1:
                raise ValueError(f"Must retain at least 1 message, got {self.value}")

    def to_context_size(self) -> tuple[str, float | int]:
        """Convert to DeepAgents ContextSize tuple format."""
        return (self.policy_type.value, self.value)


# Preset retention policies
RETAIN_MINIMAL = RetentionPolicy(TriggerType.MESSAGES, 10)
RETAIN_STANDARD = RetentionPolicy(TriggerType.MESSAGES, 20)
RETAIN_EXTENDED = RetentionPolicy(TriggerType.MESSAGES, 40)
RETAIN_FRACTION = RetentionPolicy(TriggerType.FRACTION, 0.15)


@dataclass
class SummarizationConfig:
    """Configuration for context auto-summarization.

    Provides a high-level configuration interface for AG3NT's summarization
    behavior, wrapping the DeepAgents SummarizationMiddleware.

    Attributes:
        trigger: When to trigger summarization
        retention: What to keep after summarization
        model: Model to use for summarization (defaults to agent's model)
        history_path_prefix: Path prefix for storing conversation history
        truncate_tool_args: Whether to truncate large tool arguments
        max_arg_length: Maximum length for tool arguments before truncation
        enabled: Whether summarization is enabled
    """

    trigger: SummarizationTrigger = field(default_factory=lambda: TRIGGER_BALANCED)
    retention: RetentionPolicy = field(default_factory=lambda: RETAIN_STANDARD)
    model: str | None = None  # None = use agent's model
    history_path_prefix: str = "/conversation_history"
    truncate_tool_args: bool = True
    max_arg_length: int = 2000
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_arg_length < 100:
            raise ValueError(f"max_arg_length must be at least 100, got {self.max_arg_length}")


# Preset configurations
CONFIG_DISABLED = SummarizationConfig(enabled=False)

CONFIG_CONSERVATIVE = SummarizationConfig(
    trigger=TRIGGER_CONSERVATIVE,
    retention=RETAIN_EXTENDED,
)

CONFIG_BALANCED = SummarizationConfig(
    trigger=TRIGGER_BALANCED,
    retention=RETAIN_STANDARD,
)

CONFIG_AGGRESSIVE = SummarizationConfig(
    trigger=TRIGGER_AGGRESSIVE,
    retention=RETAIN_MINIMAL,
)


@dataclass
class SummarizationEvent:
    """Record of a summarization event.

    Attributes:
        timestamp: When the summarization occurred
        session_id: Session that was summarized
        messages_before: Number of messages before summarization
        messages_after: Number of messages after summarization
        tokens_before: Token count before summarization
        tokens_after: Token count after summarization
        compression_ratio: Ratio of tokens reduced (0.0-1.0)
        duration_ms: Time taken for summarization in milliseconds
        history_path: Path where history was offloaded
        success: Whether summarization succeeded
        error: Error message if failed
    """

    timestamp: datetime
    session_id: str
    messages_before: int
    messages_after: int
    tokens_before: int
    tokens_after: int
    compression_ratio: float
    duration_ms: float
    history_path: str | None = None
    success: bool = True
    error: str | None = None


class SummarizationMonitor:
    """Monitor for tracking summarization performance and metrics.

    Provides observability into summarization behavior including:
    - Event history
    - Compression statistics
    - Performance metrics
    - Callback support for external monitoring

    Usage:
        monitor = SummarizationMonitor()
        monitor.on_event(lambda e: print(f"Summarized: {e.compression_ratio:.1%}"))

        # Record an event
        monitor.record_event(event)

        # Get statistics
        stats = monitor.get_statistics()
    """

    def __init__(self, max_events: int = 100) -> None:
        """Initialize the monitor.

        Args:
            max_events: Maximum number of events to keep in history
        """
        self._events: list[SummarizationEvent] = []
        self._max_events = max_events
        self._callbacks: list[Callable[[SummarizationEvent], None]] = []
        self._total_tokens_saved: int = 0
        self._total_summarizations: int = 0
        self._failed_summarizations: int = 0

    def on_event(self, callback: Callable[[SummarizationEvent], None]) -> None:
        """Register a callback for summarization events.

        Args:
            callback: Function to call when a summarization event occurs
        """
        self._callbacks.append(callback)

    def record_event(self, event: SummarizationEvent) -> None:
        """Record a summarization event.

        Args:
            event: The summarization event to record
        """
        self._events.append(event)
        self._total_summarizations += 1

        if event.success:
            self._total_tokens_saved += event.tokens_before - event.tokens_after
        else:
            self._failed_summarizations += 1

        # Trim old events
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"Summarization callback error: {e}")

    def record_summarization(
        self,
        session_id: str,
        messages_before: int,
        messages_after: int,
        tokens_before: int,
        tokens_after: int,
        duration_ms: float,
        history_path: str | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> SummarizationEvent:
        """Convenience method to record a summarization.

        Args:
            session_id: Session that was summarized
            messages_before: Number of messages before
            messages_after: Number of messages after
            tokens_before: Token count before
            tokens_after: Token count after
            duration_ms: Time taken in milliseconds
            history_path: Path where history was offloaded
            success: Whether summarization succeeded
            error: Error message if failed

        Returns:
            The recorded event
        """
        compression_ratio = 1.0 - (tokens_after / tokens_before) if tokens_before > 0 else 0.0

        event = SummarizationEvent(
            timestamp=datetime.now(),
            session_id=session_id,
            messages_before=messages_before,
            messages_after=messages_after,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            compression_ratio=compression_ratio,
            duration_ms=duration_ms,
            history_path=history_path,
            success=success,
            error=error,
        )
        self.record_event(event)
        return event

    def get_events(self, session_id: str | None = None) -> list[SummarizationEvent]:
        """Get recorded events, optionally filtered by session.

        Args:
            session_id: Optional session ID to filter by

        Returns:
            List of summarization events
        """
        if session_id is None:
            return list(self._events)
        return [e for e in self._events if e.session_id == session_id]

    def get_statistics(self) -> dict[str, Any]:
        """Get summarization statistics.

        Returns:
            Dict with statistics including:
            - total_summarizations: Total number of summarizations
            - successful_summarizations: Number of successful summarizations
            - failed_summarizations: Number of failed summarizations
            - total_tokens_saved: Total tokens saved across all summarizations
            - average_compression_ratio: Average compression ratio
            - average_duration_ms: Average summarization duration
        """
        successful_events = [e for e in self._events if e.success]

        avg_compression = 0.0
        avg_duration = 0.0
        if successful_events:
            avg_compression = sum(e.compression_ratio for e in successful_events) / len(successful_events)
            avg_duration = sum(e.duration_ms for e in successful_events) / len(successful_events)

        return {
            "total_summarizations": self._total_summarizations,
            "successful_summarizations": self._total_summarizations - self._failed_summarizations,
            "failed_summarizations": self._failed_summarizations,
            "total_tokens_saved": self._total_tokens_saved,
            "average_compression_ratio": avg_compression,
            "average_duration_ms": avg_duration,
            "events_in_history": len(self._events),
        }

    def clear(self) -> None:
        """Clear all recorded events and reset statistics."""
        self._events.clear()
        self._total_tokens_saved = 0
        self._total_summarizations = 0
        self._failed_summarizations = 0


class MonitoredSummarizationMiddleware(AgentMiddleware):
    """Wrapper that adds monitoring to SummarizationMiddleware.

    This wrapper intercepts calls to the underlying middleware and records
    summarization events to the global monitor for observability.

    Inherits from AgentMiddleware to satisfy langchain's class-level attribute
    checks. Only overrides `before_model` for monitoring - all other methods
    inherit from AgentMiddleware base class so the framework knows we don't
    intercept model/tool calls.
    """

    def __init__(
        self,
        middleware: SummarizationMiddleware,
        monitor: SummarizationMonitor | None = None,
    ) -> None:
        """Initialize the monitored wrapper.

        Args:
            middleware: The underlying SummarizationMiddleware
            monitor: Optional monitor instance (uses global if not provided)
        """
        self._middleware = middleware
        self._monitor = monitor
        self._last_message_count: dict[str, int] = {}
        self._last_token_count: dict[str, int] = {}

    @property
    def monitor(self) -> SummarizationMonitor:
        """Get the monitor instance."""
        if self._monitor is None:
            self._monitor = get_summarization_monitor()
        return self._monitor

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Intercept before_model to track summarization.

        Args:
            state: Agent state from DeepAgents
            runtime: DeepAgents runtime

        Returns:
            Modified state dict if summarization occurred, None otherwise
        """
        # Get thread ID for session tracking
        thread_id = getattr(state, "thread_id", None) or "default"

        # Record current state before middleware processes
        messages = getattr(state, "messages", [])
        messages_before = len(messages) if messages else 0
        tokens_before = count_tokens_approximately(messages) if messages else 0

        # Store for comparison after
        self._last_message_count[thread_id] = messages_before
        self._last_token_count[thread_id] = tokens_before

        # Call the underlying middleware
        start_time = time.time()
        try:
            result = self._middleware.before_model(state, runtime)
        except Exception as e:
            # Record failed summarization
            duration_ms = (time.time() - start_time) * 1000
            self.monitor.record_summarization(
                session_id=thread_id,
                messages_before=messages_before,
                messages_after=messages_before,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )
            raise

        # Check if summarization occurred by examining the result
        if result is not None and "messages" in result:
            duration_ms = (time.time() - start_time) * 1000
            new_messages = result["messages"]
            messages_after = len(new_messages) if new_messages else 0
            tokens_after = count_tokens_approximately(new_messages) if new_messages else 0

            # Only record if summarization actually reduced the message count
            if messages_after < messages_before:
                # Get history path from middleware if available
                history_path = getattr(self._middleware, "_last_history_path", None)

                self.monitor.record_summarization(
                    session_id=thread_id,
                    messages_before=messages_before,
                    messages_after=messages_after,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    duration_ms=duration_ms,
                    history_path=history_path,
                    success=True,
                )

                logger.info(
                    f"Summarization recorded: {messages_before} -> {messages_after} messages, "
                    f"{tokens_before} -> {tokens_after} tokens "
                    f"({(1 - tokens_after / tokens_before) * 100:.1f}% reduction)"
                )

        return result

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Pass through to underlying middleware."""
        return self._middleware.after_model(state, runtime)

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Pass through to underlying middleware."""
        return self._middleware.before_agent(state, runtime)

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Pass through to underlying middleware."""
        return self._middleware.after_agent(state, runtime)

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async pass through to underlying middleware."""
        return await self._middleware.abefore_model(state, runtime)

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async pass through to underlying middleware."""
        return await self._middleware.aafter_model(state, runtime)

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async pass through to underlying middleware."""
        return await self._middleware.abefore_agent(state, runtime)

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async pass through to underlying middleware."""
        return await self._middleware.aafter_agent(state, runtime)

    # Note: wrap_tool_call, awrap_tool_call, wrap_model_call, awrap_model_call
    # are NOT implemented here. SummarizationMiddleware doesn't override these
    # methods - it only uses before_model/after_model hooks. The base AgentMiddleware
    # raises NotImplementedError for these, which tells the framework we don't
    # intercept model/tool calls. We let __getattr__ handle delegation for
    # any other attributes the framework might check.

    @property
    def name(self) -> str:
        """Get the middleware name."""
        return getattr(self._middleware, 'name', 'monitored_summarization')

    @property
    def state_schema(self) -> Any:
        """Get the state schema from underlying middleware."""
        return getattr(self._middleware, 'state_schema', None)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to underlying middleware."""
        return getattr(self._middleware, name)


def create_summarization_middleware(
    config: SummarizationConfig,
    backend: BACKEND_TYPES,
    model: str | None = None,
    monitor: SummarizationMonitor | None = None,
) -> MonitoredSummarizationMiddleware | None:
    """Create a configured and monitored SummarizationMiddleware instance.

    Factory function that creates a DeepAgents SummarizationMiddleware
    with AG3NT-specific configuration and monitoring.

    Args:
        config: Summarization configuration
        backend: Backend for storing conversation history
        model: Model to use for summarization (overrides config.model)
        monitor: Optional monitor for tracking events (uses global if not provided)

    Returns:
        Configured MonitoredSummarizationMiddleware, or None if disabled

    Example:
        config = SummarizationConfig(
            trigger=TRIGGER_BALANCED,
            retention=RETAIN_STANDARD,
        )
        middleware = create_summarization_middleware(config, backend)
    """
    if not config.enabled:
        return None

    from deepagents.middleware.summarization import SummarizationMiddleware, TruncateArgsSettings

    # Determine model to use
    summarization_model = model or config.model
    if summarization_model is None:
        # Default to a fast, cheap model for summarization
        summarization_model = "gpt-4o-mini"

    # Build truncate args settings if enabled
    truncate_settings: TruncateArgsSettings | None = None
    if config.truncate_tool_args:
        truncate_settings = {
            "trigger": ("messages", 30),  # Start truncating at 30 messages
            "keep": config.retention.to_context_size(),
            "max_length": config.max_arg_length,
            "truncation_text": "...(argument truncated)",
        }

    base_middleware = SummarizationMiddleware(
        model=summarization_model,
        backend=backend,
        trigger=config.trigger.to_context_size(),
        keep=config.retention.to_context_size(),
        token_counter=count_tokens_approximately,
        history_path_prefix=config.history_path_prefix,
        truncate_args_settings=truncate_settings,
    )

    # Wrap with monitoring
    middleware = MonitoredSummarizationMiddleware(base_middleware, monitor)

    logger.info(
        f"Created MonitoredSummarizationMiddleware: trigger={config.trigger.description}, "
        f"retention={config.retention.value} {config.retention.policy_type.value}"
    )

    return middleware


def get_default_summarization_config() -> SummarizationConfig:
    """Get the default summarization configuration for AG3NT.

    Returns:
        Default SummarizationConfig (balanced settings)
    """
    return CONFIG_BALANCED


# Global monitor instance for tracking summarization across sessions
_global_monitor: SummarizationMonitor | None = None


def get_summarization_monitor() -> SummarizationMonitor:
    """Get the global summarization monitor instance.

    Returns:
        The global SummarizationMonitor instance
    """
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = SummarizationMonitor()
    return _global_monitor


def get_summarization_statistics() -> dict[str, Any]:
    """Get summarization statistics from the global monitor.

    Convenience function for observability dashboards and logging.

    Returns:
        Dict with statistics including:
        - total_summarizations: Total number of summarizations
        - successful_summarizations: Number of successful summarizations
        - failed_summarizations: Number of failed summarizations
        - total_tokens_saved: Total tokens saved across all summarizations
        - average_compression_ratio: Average compression ratio
        - average_duration_ms: Average summarization duration
    """
    return get_summarization_monitor().get_statistics()


def reset_summarization_monitor() -> None:
    """Reset the global summarization monitor.

    Clears all recorded events and resets statistics.
    Useful for testing or when starting a new monitoring period.
    """
    global _global_monitor
    if _global_monitor is not None:
        _global_monitor.clear()
    _global_monitor = None


# ============================================================================
# Context Auto-Pruning
# ============================================================================


@dataclass
class PruningConfig:
    """Configuration for context auto-pruning.

    Attributes:
        enabled: Whether auto-pruning is enabled
        token_threshold: Token count to trigger pruning
        message_threshold: Message count to trigger pruning
        prune_tool_outputs: Whether to prune tool message contents
        prune_ratio: Ratio of old messages to prune (0.0-1.0)
        keep_system: Always keep system messages
        keep_recent_messages: Number of recent messages to never prune
        max_tool_output_age: Max age (in messages) before tool outputs are pruned
    """

    enabled: bool = True
    token_threshold: int = 80000
    message_threshold: int = 100
    prune_tool_outputs: bool = True
    prune_ratio: float = 0.3
    keep_system: bool = True
    keep_recent_messages: int = 20
    max_tool_output_age: int = 30

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0.0 < self.prune_ratio < 1.0:
            raise ValueError(f"prune_ratio must be between 0 and 1, got {self.prune_ratio}")
        if self.keep_recent_messages < 1:
            raise ValueError("keep_recent_messages must be at least 1")


PRUNING_DISABLED = PruningConfig(enabled=False)
PRUNING_CONSERVATIVE = PruningConfig(prune_ratio=0.2, keep_recent_messages=30)
PRUNING_BALANCED = PruningConfig(prune_ratio=0.3, keep_recent_messages=20)
PRUNING_AGGRESSIVE = PruningConfig(prune_ratio=0.5, keep_recent_messages=10)


@dataclass
class PruningResult:
    """Result of a pruning operation.

    Attributes:
        pruned: Whether pruning was performed
        messages_before: Message count before pruning
        messages_after: Message count after pruning
        tokens_before: Token count before pruning
        tokens_after: Token count after pruning
        tool_outputs_truncated: Number of tool outputs truncated
    """

    pruned: bool
    messages_before: int
    messages_after: int
    tokens_before: int
    tokens_after: int
    tool_outputs_truncated: int = 0


class ContextAutoPruner:
    """Automatically prunes context on overflow.

    Reduces context size by pruning old tool outputs and less important
    messages when token/message thresholds are exceeded.
    """

    def __init__(self, config: PruningConfig | None = None) -> None:
        """Initialize the auto-pruner.

        Args:
            config: Pruning configuration (uses balanced defaults if not provided)
        """
        self._config = config or PRUNING_BALANCED

    @property
    def config(self) -> PruningConfig:
        """Get the pruning configuration."""
        return self._config

    def _should_prune(self, messages: list[AnyMessage]) -> bool:
        """Check if pruning should be triggered."""
        if not self._config.enabled:
            return False

        msg_count = len(messages)
        if msg_count >= self._config.message_threshold:
            return True

        token_count = count_tokens_approximately(messages)
        return token_count >= self._config.token_threshold

    def _truncate_tool_output(self, content: str, max_length: int = 200) -> str:
        """Truncate tool output content."""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "\n[... output truncated for context efficiency ...]"

    def prune_messages(
        self,
        messages: list[AnyMessage],
    ) -> tuple[list[AnyMessage], PruningResult]:
        """Prune messages if thresholds are exceeded.

        Args:
            messages: List of messages to potentially prune

        Returns:
            Tuple of (pruned_messages, PruningResult)
        """
        from langchain_core.messages import SystemMessage, ToolMessage

        messages_before = len(messages)
        tokens_before = count_tokens_approximately(messages)

        if not self._should_prune(messages):
            return messages, PruningResult(
                pruned=False,
                messages_before=messages_before,
                messages_after=messages_before,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
            )

        # Separate messages into categories
        system_msgs = []
        recent_msgs = []
        old_msgs = []

        recent_cutoff = len(messages) - self._config.keep_recent_messages

        for i, msg in enumerate(messages):
            if self._config.keep_system and isinstance(msg, SystemMessage):
                system_msgs.append(msg)
            elif i >= recent_cutoff:
                recent_msgs.append(msg)
            else:
                old_msgs.append(msg)

        # Prune old messages
        prune_count = int(len(old_msgs) * self._config.prune_ratio)
        kept_old_msgs = old_msgs[prune_count:]

        # Truncate old tool outputs
        tool_outputs_truncated = 0
        tool_output_cutoff = len(messages) - self._config.max_tool_output_age

        processed_old = []
        for i, msg in enumerate(kept_old_msgs):
            if (
                self._config.prune_tool_outputs
                and isinstance(msg, ToolMessage)
                and i < tool_output_cutoff
            ):
                content = str(msg.content) if msg.content else ""
                if len(content) > 200:
                    truncated_content = self._truncate_tool_output(content)
                    msg = ToolMessage(
                        content=truncated_content,
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                        additional_kwargs=msg.additional_kwargs,
                    )
                    tool_outputs_truncated += 1
            processed_old.append(msg)

        # Combine messages
        pruned_messages = system_msgs + processed_old + recent_msgs

        messages_after = len(pruned_messages)
        tokens_after = count_tokens_approximately(pruned_messages)

        logger.info(
            f"Pruned context: {messages_before} -> {messages_after} messages, "
            f"{tokens_before} -> {tokens_after} tokens"
        )

        return pruned_messages, PruningResult(
            pruned=True,
            messages_before=messages_before,
            messages_after=messages_after,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tool_outputs_truncated=tool_outputs_truncated,
        )


# Global auto-pruner instance
_auto_pruner: ContextAutoPruner | None = None


def get_auto_pruner() -> ContextAutoPruner:
    """Get the global context auto-pruner."""
    global _auto_pruner
    if _auto_pruner is None:
        _auto_pruner = ContextAutoPruner()
    return _auto_pruner


def reset_auto_pruner() -> None:
    """Reset the global auto-pruner (for testing)."""
    global _auto_pruner
    _auto_pruner = None


# ============================================================================
# Progressive Summarization
# ============================================================================


@dataclass
class ProgressiveConfig:
    """Configuration for progressive summarization.

    Attributes:
        enabled: Whether progressive summarization is enabled
        max_chunk_tokens: Maximum tokens per summarization chunk
        min_chunk_messages: Minimum messages per chunk
        merge_summaries: Whether to merge chunk summaries
        preserve_tool_results: Preserve recent tool results
        summary_target_ratio: Target compression ratio (0.1-0.5)
    """

    enabled: bool = True
    max_chunk_tokens: int = 20000
    min_chunk_messages: int = 10
    merge_summaries: bool = True
    preserve_tool_results: bool = True
    summary_target_ratio: float = 0.25

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0.1 <= self.summary_target_ratio <= 0.5:
            raise ValueError(
                f"summary_target_ratio must be between 0.1 and 0.5, got {self.summary_target_ratio}"
            )


PROGRESSIVE_DISABLED = ProgressiveConfig(enabled=False)
PROGRESSIVE_CONSERVATIVE = ProgressiveConfig(max_chunk_tokens=30000, summary_target_ratio=0.35)
PROGRESSIVE_BALANCED = ProgressiveConfig()
PROGRESSIVE_AGGRESSIVE = ProgressiveConfig(max_chunk_tokens=15000, summary_target_ratio=0.15)


@dataclass
class SummaryChunk:
    """A chunk of messages for summarization.

    Attributes:
        messages: Messages in this chunk
        start_idx: Starting index in original message list
        end_idx: Ending index in original message list
        token_count: Approximate token count
        summary: Generated summary (if available)
    """

    messages: list[AnyMessage]
    start_idx: int
    end_idx: int
    token_count: int
    summary: str | None = None


@dataclass
class ProgressiveResult:
    """Result of progressive summarization.

    Attributes:
        summarized: Whether summarization was performed
        chunks_processed: Number of chunks processed
        tokens_before: Token count before summarization
        tokens_after: Token count after summarization
        compression_ratio: Achieved compression ratio
        summaries: List of generated summaries
    """

    summarized: bool
    chunks_processed: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    compression_ratio: float = 1.0
    summaries: list[str] = field(default_factory=list)


class ProgressiveSummarizer:
    """Multi-stage progressive summarizer for large message histories.

    Splits large message histories into chunks, summarizes each chunk,
    then optionally merges summaries for a final condensed summary.
    """

    def __init__(self, config: ProgressiveConfig | None = None) -> None:
        """Initialize the progressive summarizer.

        Args:
            config: Configuration (uses balanced defaults if not provided)
        """
        self._config = config or PROGRESSIVE_BALANCED

    @property
    def config(self) -> ProgressiveConfig:
        """Get the configuration."""
        return self._config

    def split_into_chunks(self, messages: list[AnyMessage]) -> list[SummaryChunk]:
        """Split messages into chunks for summarization.

        Args:
            messages: List of messages to split

        Returns:
            List of SummaryChunk objects
        """
        from langchain_core.messages import SystemMessage

        chunks: list[SummaryChunk] = []
        current_chunk: list[AnyMessage] = []
        current_tokens = 0
        chunk_start = 0

        for i, msg in enumerate(messages):
            # Skip system messages (handled separately)
            if isinstance(msg, SystemMessage):
                continue

            msg_tokens = count_tokens_approximately([msg])

            # Check if adding this message would exceed chunk limit
            if (
                current_tokens + msg_tokens > self._config.max_chunk_tokens
                and len(current_chunk) >= self._config.min_chunk_messages
            ):
                # Save current chunk
                chunks.append(
                    SummaryChunk(
                        messages=current_chunk.copy(),
                        start_idx=chunk_start,
                        end_idx=i - 1,
                        token_count=current_tokens,
                    )
                )
                current_chunk = []
                current_tokens = 0
                chunk_start = i

            current_chunk.append(msg)
            current_tokens += msg_tokens

        # Add remaining messages as final chunk
        if current_chunk:
            chunks.append(
                SummaryChunk(
                    messages=current_chunk,
                    start_idx=chunk_start,
                    end_idx=len(messages) - 1,
                    token_count=current_tokens,
                )
            )

        return chunks

    def summarize_chunk(
        self,
        chunk: SummaryChunk,
        summarize_fn: Callable[[list[AnyMessage]], str],
    ) -> str:
        """Summarize a single chunk.

        Args:
            chunk: Chunk to summarize
            summarize_fn: Function to generate summary from messages

        Returns:
            Generated summary text
        """
        summary = summarize_fn(chunk.messages)
        chunk.summary = summary
        return summary

    def merge_summaries(
        self,
        summaries: list[str],
        merge_fn: Callable[[list[str]], str] | None = None,
    ) -> str:
        """Merge multiple chunk summaries into a final summary.

        Args:
            summaries: List of chunk summaries to merge
            merge_fn: Optional function to merge summaries (default: join with separators)

        Returns:
            Merged summary text
        """
        if not summaries:
            return ""

        if len(summaries) == 1:
            return summaries[0]

        if merge_fn is not None:
            return merge_fn(summaries)

        # Default merge: join with section separators
        merged_parts = []
        for i, summary in enumerate(summaries, 1):
            if len(summaries) > 1:
                merged_parts.append(f"[Part {i}/{len(summaries)}]\n{summary}")
            else:
                merged_parts.append(summary)

        return "\n\n---\n\n".join(merged_parts)

    def summarize(
        self,
        messages: list[AnyMessage],
        summarize_fn: Callable[[list[AnyMessage]], str],
        merge_fn: Callable[[list[str]], str] | None = None,
    ) -> ProgressiveResult:
        """Perform progressive summarization on messages.

        This is the main entry point for progressive summarization.
        It splits messages into chunks, summarizes each chunk, and
        optionally merges the summaries.

        Args:
            messages: List of messages to summarize
            summarize_fn: Function to summarize a list of messages
            merge_fn: Optional function to merge summaries

        Returns:
            ProgressiveResult with summarization details
        """
        if not self._config.enabled:
            return ProgressiveResult(summarized=False)

        tokens_before = count_tokens_approximately(messages)

        # Split messages into chunks
        chunks = self.split_into_chunks(messages)

        if not chunks:
            return ProgressiveResult(summarized=False, tokens_before=tokens_before)

        # If only one small chunk, may not need progressive summarization
        if len(chunks) == 1 and chunks[0].token_count < self._config.max_chunk_tokens // 2:
            logger.debug("Messages too small for progressive summarization")
            return ProgressiveResult(summarized=False, tokens_before=tokens_before)

        logger.info(f"Progressive summarization: {len(chunks)} chunks, {tokens_before} tokens")

        # Summarize each chunk
        summaries: list[str] = []
        for i, chunk in enumerate(chunks):
            try:
                summary = self.summarize_chunk(chunk, summarize_fn)
                summaries.append(summary)
                logger.debug(
                    f"Chunk {i + 1}/{len(chunks)}: {chunk.token_count} tokens -> "
                    f"{count_tokens_approximately([summary])} tokens"
                )
            except Exception as e:
                logger.error(f"Failed to summarize chunk {i + 1}: {e}")
                # Use placeholder for failed chunks
                summaries.append(f"[Summary unavailable for messages {chunk.start_idx}-{chunk.end_idx}]")

        # Merge summaries if configured
        if self._config.merge_summaries and len(summaries) > 1:
            final_summary = self.merge_summaries(summaries, merge_fn)
            tokens_after = count_tokens_approximately([final_summary])
        else:
            tokens_after = sum(count_tokens_approximately([s]) for s in summaries)

        compression_ratio = tokens_after / tokens_before if tokens_before > 0 else 1.0

        logger.info(
            f"Progressive summarization complete: {tokens_before} -> {tokens_after} tokens "
            f"({compression_ratio:.1%} of original)"
        )

        return ProgressiveResult(
            summarized=True,
            chunks_processed=len(chunks),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            compression_ratio=compression_ratio,
            summaries=summaries,
        )

    def get_preserved_messages(
        self,
        messages: list[AnyMessage],
        preserve_count: int = 5,
    ) -> tuple[list[AnyMessage], list[AnyMessage]]:
        """Split messages into those to summarize and those to preserve.

        Args:
            messages: All messages
            preserve_count: Number of recent messages to preserve

        Returns:
            Tuple of (messages_to_summarize, messages_to_preserve)
        """
        from langchain_core.messages import SystemMessage, ToolMessage

        # Always preserve system messages
        system_messages = [m for m in messages if isinstance(m, SystemMessage)]
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]

        if len(non_system) <= preserve_count:
            return [], messages

        to_summarize = non_system[:-preserve_count]
        to_preserve = system_messages + non_system[-preserve_count:]

        # If preserving tool results, also keep recent tool messages
        if self._config.preserve_tool_results:
            recent_tool_msgs = [m for m in to_summarize if isinstance(m, ToolMessage)][-3:]
            if recent_tool_msgs:
                to_summarize = [m for m in to_summarize if m not in recent_tool_msgs]
                to_preserve = system_messages + recent_tool_msgs + non_system[-preserve_count:]

        return to_summarize, to_preserve


# Global progressive summarizer instance
_progressive_summarizer: ProgressiveSummarizer | None = None


def get_progressive_summarizer() -> ProgressiveSummarizer:
    """Get the global progressive summarizer instance.

    Returns:
        Global ProgressiveSummarizer instance
    """
    global _progressive_summarizer
    if _progressive_summarizer is None:
        _progressive_summarizer = ProgressiveSummarizer()
    return _progressive_summarizer


def reset_progressive_summarizer() -> None:
    """Reset the global progressive summarizer (for testing)."""
    global _progressive_summarizer
    _progressive_summarizer = None
