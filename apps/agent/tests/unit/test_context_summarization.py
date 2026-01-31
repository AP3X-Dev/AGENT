"""Unit tests for context auto-summarization module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ag3nt_agent.context_summarization import (
    CONFIG_AGGRESSIVE,
    CONFIG_BALANCED,
    CONFIG_CONSERVATIVE,
    CONFIG_DISABLED,
    RETAIN_EXTENDED,
    RETAIN_FRACTION,
    RETAIN_MINIMAL,
    RETAIN_STANDARD,
    TRIGGER_AGGRESSIVE,
    TRIGGER_BALANCED,
    TRIGGER_CONSERVATIVE,
    TRIGGER_MESSAGE_BASED,
    TRIGGER_TOKEN_BASED,
    MonitoredSummarizationMiddleware,
    RetentionPolicy,
    SummarizationConfig,
    SummarizationEvent,
    SummarizationMonitor,
    SummarizationTrigger,
    TriggerType,
    create_summarization_middleware,
    get_default_summarization_config,
    get_summarization_monitor,
    get_summarization_statistics,
    reset_summarization_monitor,
)


# =============================================================================
# TriggerType Tests
# =============================================================================


class TestTriggerType:
    """Tests for TriggerType enum."""

    def test_trigger_type_values(self):
        """Test trigger type enum values."""
        assert TriggerType.TOKENS.value == "tokens"
        assert TriggerType.MESSAGES.value == "messages"
        assert TriggerType.FRACTION.value == "fraction"

    def test_trigger_type_is_str_enum(self):
        """Test that TriggerType is a string enum."""
        assert isinstance(TriggerType.TOKENS, str)
        assert TriggerType.TOKENS == "tokens"


# =============================================================================
# SummarizationTrigger Tests
# =============================================================================


class TestSummarizationTrigger:
    """Tests for SummarizationTrigger dataclass."""

    def test_fraction_trigger_valid(self):
        """Test valid fraction trigger."""
        trigger = SummarizationTrigger(TriggerType.FRACTION, 0.85)
        assert trigger.trigger_type == TriggerType.FRACTION
        assert trigger.threshold == 0.85
        assert "0.85" in trigger.description

    def test_fraction_trigger_validation_too_low(self):
        """Test fraction trigger validation - too low."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            SummarizationTrigger(TriggerType.FRACTION, 0.0)

    def test_fraction_trigger_validation_too_high(self):
        """Test fraction trigger validation - too high."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            SummarizationTrigger(TriggerType.FRACTION, 1.5)

    def test_token_trigger_valid(self):
        """Test valid token trigger."""
        trigger = SummarizationTrigger(TriggerType.TOKENS, 50000)
        assert trigger.trigger_type == TriggerType.TOKENS
        assert trigger.threshold == 50000

    def test_token_trigger_validation_too_low(self):
        """Test token trigger validation - too low."""
        with pytest.raises(ValueError, match="at least 100"):
            SummarizationTrigger(TriggerType.TOKENS, 50)

    def test_message_trigger_valid(self):
        """Test valid message trigger."""
        trigger = SummarizationTrigger(TriggerType.MESSAGES, 30)
        assert trigger.trigger_type == TriggerType.MESSAGES
        assert trigger.threshold == 30

    def test_message_trigger_validation_too_low(self):
        """Test message trigger validation - too low."""
        with pytest.raises(ValueError, match="at least 2"):
            SummarizationTrigger(TriggerType.MESSAGES, 1)

    def test_to_context_size(self):
        """Test conversion to DeepAgents ContextSize format."""
        trigger = SummarizationTrigger(TriggerType.FRACTION, 0.80)
        result = trigger.to_context_size()
        assert result == ("fraction", 0.80)

    def test_custom_description(self):
        """Test custom description."""
        trigger = SummarizationTrigger(
            TriggerType.MESSAGES,
            50,
            description="Custom trigger"
        )
        assert trigger.description == "Custom trigger"


# =============================================================================
# Preset Triggers Tests
# =============================================================================


class TestPresetTriggers:
    """Tests for preset trigger configurations."""

    def test_trigger_conservative(self):
        """Test conservative trigger preset."""
        assert TRIGGER_CONSERVATIVE.trigger_type == TriggerType.FRACTION
        assert TRIGGER_CONSERVATIVE.threshold == 0.90

    def test_trigger_balanced(self):
        """Test balanced trigger preset."""
        assert TRIGGER_BALANCED.trigger_type == TriggerType.FRACTION
        assert TRIGGER_BALANCED.threshold == 0.80

    def test_trigger_aggressive(self):
        """Test aggressive trigger preset."""
        assert TRIGGER_AGGRESSIVE.trigger_type == TriggerType.FRACTION
        assert TRIGGER_AGGRESSIVE.threshold == 0.65

    def test_trigger_message_based(self):
        """Test message-based trigger preset."""
        assert TRIGGER_MESSAGE_BASED.trigger_type == TriggerType.MESSAGES
        assert TRIGGER_MESSAGE_BASED.threshold == 50

    def test_trigger_token_based(self):
        """Test token-based trigger preset."""
        assert TRIGGER_TOKEN_BASED.trigger_type == TriggerType.TOKENS
        assert TRIGGER_TOKEN_BASED.threshold == 100000


# =============================================================================
# RetentionPolicy Tests
# =============================================================================


class TestRetentionPolicy:
    """Tests for RetentionPolicy dataclass."""

    def test_message_retention_valid(self):
        """Test valid message retention."""
        policy = RetentionPolicy(TriggerType.MESSAGES, 20)
        assert policy.policy_type == TriggerType.MESSAGES
        assert policy.value == 20

    def test_message_retention_validation_too_low(self):
        """Test message retention validation - too low."""
        with pytest.raises(ValueError, match="at least 1"):
            RetentionPolicy(TriggerType.MESSAGES, 0)

    def test_fraction_retention_valid(self):
        """Test valid fraction retention."""
        policy = RetentionPolicy(TriggerType.FRACTION, 0.15)
        assert policy.policy_type == TriggerType.FRACTION
        assert policy.value == 0.15

    def test_fraction_retention_validation_too_low(self):
        """Test fraction retention validation - too low."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            RetentionPolicy(TriggerType.FRACTION, 0.0)

    def test_fraction_retention_validation_too_high(self):
        """Test fraction retention validation - too high."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            RetentionPolicy(TriggerType.FRACTION, 1.0)

    def test_to_context_size(self):
        """Test conversion to DeepAgents ContextSize format."""
        policy = RetentionPolicy(TriggerType.MESSAGES, 20)
        result = policy.to_context_size()
        assert result == ("messages", 20)


class TestPresetRetentionPolicies:
    """Tests for preset retention policies."""

    def test_retain_minimal(self):
        """Test minimal retention preset."""
        assert RETAIN_MINIMAL.policy_type == TriggerType.MESSAGES
        assert RETAIN_MINIMAL.value == 10

    def test_retain_standard(self):
        """Test standard retention preset."""
        assert RETAIN_STANDARD.policy_type == TriggerType.MESSAGES
        assert RETAIN_STANDARD.value == 20

    def test_retain_extended(self):
        """Test extended retention preset."""
        assert RETAIN_EXTENDED.policy_type == TriggerType.MESSAGES
        assert RETAIN_EXTENDED.value == 40

    def test_retain_fraction(self):
        """Test fraction retention preset."""
        assert RETAIN_FRACTION.policy_type == TriggerType.FRACTION
        assert RETAIN_FRACTION.value == 0.15


# =============================================================================
# SummarizationConfig Tests
# =============================================================================


class TestSummarizationConfig:
    """Tests for SummarizationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SummarizationConfig()
        assert config.trigger == TRIGGER_BALANCED
        assert config.retention == RETAIN_STANDARD
        assert config.model is None
        assert config.history_path_prefix == "/conversation_history"
        assert config.truncate_tool_args is True
        assert config.max_arg_length == 2000
        assert config.enabled is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = SummarizationConfig(
            trigger=TRIGGER_AGGRESSIVE,
            retention=RETAIN_MINIMAL,
            model="gpt-4o-mini",
            max_arg_length=1000,
        )
        assert config.trigger == TRIGGER_AGGRESSIVE
        assert config.retention == RETAIN_MINIMAL
        assert config.model == "gpt-4o-mini"
        assert config.max_arg_length == 1000

    def test_max_arg_length_validation(self):
        """Test max_arg_length validation."""
        with pytest.raises(ValueError, match="at least 100"):
            SummarizationConfig(max_arg_length=50)

    def test_disabled_config(self):
        """Test disabled configuration."""
        config = SummarizationConfig(enabled=False)
        assert config.enabled is False


class TestPresetConfigs:
    """Tests for preset configurations."""

    def test_config_disabled(self):
        """Test disabled config preset."""
        assert CONFIG_DISABLED.enabled is False

    def test_config_conservative(self):
        """Test conservative config preset."""
        assert CONFIG_CONSERVATIVE.trigger == TRIGGER_CONSERVATIVE
        assert CONFIG_CONSERVATIVE.retention == RETAIN_EXTENDED
        assert CONFIG_CONSERVATIVE.enabled is True

    def test_config_balanced(self):
        """Test balanced config preset."""
        assert CONFIG_BALANCED.trigger == TRIGGER_BALANCED
        assert CONFIG_BALANCED.retention == RETAIN_STANDARD
        assert CONFIG_BALANCED.enabled is True

    def test_config_aggressive(self):
        """Test aggressive config preset."""
        assert CONFIG_AGGRESSIVE.trigger == TRIGGER_AGGRESSIVE
        assert CONFIG_AGGRESSIVE.retention == RETAIN_MINIMAL
        assert CONFIG_AGGRESSIVE.enabled is True


# =============================================================================
# SummarizationEvent Tests
# =============================================================================


class TestSummarizationEvent:
    """Tests for SummarizationEvent dataclass."""

    def test_event_creation(self):
        """Test event creation with all fields."""
        event = SummarizationEvent(
            timestamp=datetime.now(),
            session_id="test-session",
            messages_before=100,
            messages_after=25,
            tokens_before=50000,
            tokens_after=12500,
            compression_ratio=0.75,
            duration_ms=1500.5,
            history_path="/conversation_history/test.md",
            success=True,
            error=None,
        )
        assert event.session_id == "test-session"
        assert event.messages_before == 100
        assert event.messages_after == 25
        assert event.compression_ratio == 0.75
        assert event.success is True

    def test_event_with_error(self):
        """Test event creation with error."""
        event = SummarizationEvent(
            timestamp=datetime.now(),
            session_id="test-session",
            messages_before=100,
            messages_after=100,
            tokens_before=50000,
            tokens_after=50000,
            compression_ratio=0.0,
            duration_ms=100.0,
            success=False,
            error="Summarization failed: model error",
        )
        assert event.success is False
        assert event.error == "Summarization failed: model error"


# =============================================================================
# SummarizationMonitor Tests
# =============================================================================


class TestSummarizationMonitor:
    """Tests for SummarizationMonitor class."""

    def test_monitor_creation(self):
        """Test monitor creation."""
        monitor = SummarizationMonitor()
        assert monitor.get_statistics()["total_summarizations"] == 0

    def test_monitor_with_max_events(self):
        """Test monitor with custom max events."""
        monitor = SummarizationMonitor(max_events=10)
        assert len(monitor.get_events()) == 0

    def test_record_event(self):
        """Test recording an event."""
        monitor = SummarizationMonitor()
        event = SummarizationEvent(
            timestamp=datetime.now(),
            session_id="test",
            messages_before=50,
            messages_after=20,
            tokens_before=25000,
            tokens_after=10000,
            compression_ratio=0.6,
            duration_ms=500.0,
        )
        monitor.record_event(event)

        stats = monitor.get_statistics()
        assert stats["total_summarizations"] == 1
        assert stats["successful_summarizations"] == 1
        assert stats["total_tokens_saved"] == 15000

    def test_record_summarization(self):
        """Test convenience method for recording."""
        monitor = SummarizationMonitor()
        event = monitor.record_summarization(
            session_id="test",
            messages_before=100,
            messages_after=20,
            tokens_before=50000,
            tokens_after=10000,
            duration_ms=1000.0,
        )

        assert event.compression_ratio == 0.8
        assert monitor.get_statistics()["total_summarizations"] == 1

    def test_record_failed_summarization(self):
        """Test recording failed summarization."""
        monitor = SummarizationMonitor()
        monitor.record_summarization(
            session_id="test",
            messages_before=100,
            messages_after=100,
            tokens_before=50000,
            tokens_after=50000,
            duration_ms=100.0,
            success=False,
            error="Test error",
        )

        stats = monitor.get_statistics()
        assert stats["failed_summarizations"] == 1
        assert stats["total_tokens_saved"] == 0

    def test_get_events_by_session(self):
        """Test filtering events by session."""
        monitor = SummarizationMonitor()
        monitor.record_summarization("session1", 50, 20, 25000, 10000, 500.0)
        monitor.record_summarization("session2", 60, 25, 30000, 12500, 600.0)
        monitor.record_summarization("session1", 70, 30, 35000, 15000, 700.0)

        session1_events = monitor.get_events("session1")
        assert len(session1_events) == 2

        session2_events = monitor.get_events("session2")
        assert len(session2_events) == 1

    def test_max_events_trimming(self):
        """Test that old events are trimmed."""
        monitor = SummarizationMonitor(max_events=5)

        for i in range(10):
            monitor.record_summarization(f"session-{i}", 50, 20, 25000, 10000, 500.0)

        events = monitor.get_events()
        assert len(events) == 5
        # Should keep the last 5
        assert events[0].session_id == "session-5"

    def test_on_event_callback(self):
        """Test event callback registration."""
        monitor = SummarizationMonitor()
        callback_events = []

        def callback(event):
            callback_events.append(event)

        monitor.on_event(callback)
        monitor.record_summarization("test", 50, 20, 25000, 10000, 500.0)

        assert len(callback_events) == 1
        assert callback_events[0].session_id == "test"

    def test_on_event_callback_error_handling(self):
        """Test that callback errors don't break recording."""
        monitor = SummarizationMonitor()

        def failing_callback(event):
            raise RuntimeError("Callback error")

        monitor.on_event(failing_callback)
        # Should not raise
        monitor.record_summarization("test", 50, 20, 25000, 10000, 500.0)
        assert monitor.get_statistics()["total_summarizations"] == 1

    def test_get_statistics(self):
        """Test statistics calculation."""
        monitor = SummarizationMonitor()
        monitor.record_summarization("s1", 100, 25, 50000, 12500, 1000.0)
        monitor.record_summarization("s2", 80, 20, 40000, 10000, 800.0)

        stats = monitor.get_statistics()
        assert stats["total_summarizations"] == 2
        assert stats["successful_summarizations"] == 2
        assert stats["failed_summarizations"] == 0
        assert stats["total_tokens_saved"] == 67500  # 37500 + 30000
        assert stats["average_compression_ratio"] == 0.75
        assert stats["average_duration_ms"] == 900.0

    def test_clear(self):
        """Test clearing monitor."""
        monitor = SummarizationMonitor()
        monitor.record_summarization("test", 50, 20, 25000, 10000, 500.0)

        monitor.clear()

        stats = monitor.get_statistics()
        assert stats["total_summarizations"] == 0
        assert stats["total_tokens_saved"] == 0
        assert len(monitor.get_events()) == 0


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateSummarizationMiddleware:
    """Tests for create_summarization_middleware factory function."""

    def test_disabled_config_returns_none(self):
        """Test that disabled config returns None."""
        config = CONFIG_DISABLED
        backend = MagicMock()
        result = create_summarization_middleware(config, backend)
        assert result is None

    @patch("deepagents.middleware.summarization.SummarizationMiddleware")
    def test_creates_middleware_with_defaults(self, mock_middleware_class):
        """Test middleware creation with default settings."""
        mock_middleware = MagicMock()
        mock_middleware_class.return_value = mock_middleware

        config = SummarizationConfig()
        backend = MagicMock()
        result = create_summarization_middleware(config, backend)

        assert result is not None
        assert isinstance(result, MonitoredSummarizationMiddleware)
        mock_middleware_class.assert_called_once()

    @patch("deepagents.middleware.summarization.SummarizationMiddleware")
    def test_creates_middleware_with_custom_model(self, mock_middleware_class):
        """Test middleware creation with custom model."""
        mock_middleware_class.return_value = MagicMock()

        config = SummarizationConfig(model="claude-3-haiku-20240307")
        backend = MagicMock()
        create_summarization_middleware(config, backend)

        # Check model was passed correctly
        call_kwargs = mock_middleware_class.call_args[1]
        assert call_kwargs["model"] == "claude-3-haiku-20240307"

    @patch("deepagents.middleware.summarization.SummarizationMiddleware")
    def test_creates_middleware_with_model_override(self, mock_middleware_class):
        """Test middleware creation with model override."""
        mock_middleware_class.return_value = MagicMock()

        config = SummarizationConfig(model="claude-3-haiku-20240307")
        backend = MagicMock()
        create_summarization_middleware(config, backend, model="gpt-4o")

        # Override should take precedence
        call_kwargs = mock_middleware_class.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    @patch("deepagents.middleware.summarization.SummarizationMiddleware")
    def test_truncate_args_disabled(self, mock_middleware_class):
        """Test middleware with truncate_tool_args disabled."""
        mock_middleware_class.return_value = MagicMock()

        config = SummarizationConfig(truncate_tool_args=False)
        backend = MagicMock()
        create_summarization_middleware(config, backend)

        call_kwargs = mock_middleware_class.call_args[1]
        assert call_kwargs["truncate_args_settings"] is None


# =============================================================================
# MonitoredSummarizationMiddleware Tests
# =============================================================================


class TestMonitoredSummarizationMiddleware:
    """Tests for MonitoredSummarizationMiddleware wrapper."""

    def test_wrapper_creation(self):
        """Test wrapper creation."""
        mock_middleware = MagicMock()
        monitor = SummarizationMonitor()
        wrapper = MonitoredSummarizationMiddleware(mock_middleware, monitor)

        assert wrapper._middleware == mock_middleware
        assert wrapper._monitor == monitor

    def test_wrapper_uses_global_monitor_if_none(self):
        """Test wrapper uses global monitor if none provided."""
        reset_summarization_monitor()
        mock_middleware = MagicMock()
        wrapper = MonitoredSummarizationMiddleware(mock_middleware, None)

        # Accessing monitor property should create global
        monitor = wrapper.monitor
        assert monitor is not None
        assert monitor == get_summarization_monitor()

    def test_delegate_attribute_access(self):
        """Test attribute delegation to underlying middleware."""
        mock_middleware = MagicMock()
        mock_middleware.some_attribute = "test_value"

        wrapper = MonitoredSummarizationMiddleware(mock_middleware)
        assert wrapper.some_attribute == "test_value"

    def test_after_model_passthrough(self):
        """Test after_model passes through to underlying middleware."""
        mock_middleware = MagicMock()
        mock_middleware.after_model.return_value = {"key": "value"}

        wrapper = MonitoredSummarizationMiddleware(mock_middleware)
        result = wrapper.after_model(MagicMock(), MagicMock())

        mock_middleware.after_model.assert_called_once()
        assert result == {"key": "value"}

    def test_before_model_no_summarization(self):
        """Test before_model when no summarization occurs."""
        mock_middleware = MagicMock()
        mock_middleware.before_model.return_value = None

        monitor = SummarizationMonitor()
        wrapper = MonitoredSummarizationMiddleware(mock_middleware, monitor)

        mock_state = MagicMock()
        mock_state.messages = []
        mock_state.thread_id = "test-thread"

        result = wrapper.before_model(mock_state, MagicMock())

        assert result is None
        assert monitor.get_statistics()["total_summarizations"] == 0

    def test_before_model_with_summarization(self):
        """Test before_model when summarization occurs."""
        from langchain_core.messages import HumanMessage

        mock_middleware = MagicMock()
        # Simulate summarization result with fewer messages
        new_messages = [HumanMessage(content="Summary of conversation")]
        mock_middleware.before_model.return_value = {"messages": new_messages}

        monitor = SummarizationMonitor()
        wrapper = MonitoredSummarizationMiddleware(mock_middleware, monitor)

        mock_state = MagicMock()
        original_messages = [HumanMessage(content=f"Message {i}") for i in range(50)]
        mock_state.messages = original_messages
        mock_state.thread_id = "test-thread"

        result = wrapper.before_model(mock_state, MagicMock())

        assert result == {"messages": new_messages}
        stats = monitor.get_statistics()
        assert stats["total_summarizations"] == 1
        assert stats["successful_summarizations"] == 1

    def test_before_model_with_exception(self):
        """Test before_model records failure on exception."""
        mock_middleware = MagicMock()
        mock_middleware.before_model.side_effect = RuntimeError("Model error")

        monitor = SummarizationMonitor()
        wrapper = MonitoredSummarizationMiddleware(mock_middleware, monitor)

        mock_state = MagicMock()
        mock_state.messages = []
        mock_state.thread_id = "test-thread"

        with pytest.raises(RuntimeError):
            wrapper.before_model(mock_state, MagicMock())

        stats = monitor.get_statistics()
        assert stats["total_summarizations"] == 1
        assert stats["failed_summarizations"] == 1

    def test_before_model_no_thread_id(self):
        """Test before_model uses default thread ID if not available."""
        mock_middleware = MagicMock()
        mock_middleware.before_model.return_value = None

        monitor = SummarizationMonitor()
        wrapper = MonitoredSummarizationMiddleware(mock_middleware, monitor)

        mock_state = MagicMock(spec=[])  # No attributes
        mock_state.messages = []

        result = wrapper.before_model(mock_state, MagicMock())

        assert result is None
        # Should use "default" as thread_id


# =============================================================================
# Global Helper Function Tests
# =============================================================================


class TestGlobalHelpers:
    """Tests for global helper functions."""

    def test_get_default_summarization_config(self):
        """Test getting default config."""
        config = get_default_summarization_config()
        assert config == CONFIG_BALANCED

    def test_get_summarization_monitor_singleton(self):
        """Test that get_summarization_monitor returns singleton."""
        reset_summarization_monitor()
        monitor1 = get_summarization_monitor()
        monitor2 = get_summarization_monitor()
        assert monitor1 is monitor2

    def test_get_summarization_statistics(self):
        """Test get_summarization_statistics convenience function."""
        reset_summarization_monitor()
        stats = get_summarization_statistics()
        assert stats["total_summarizations"] == 0

    def test_reset_summarization_monitor(self):
        """Test resetting the global monitor."""
        monitor1 = get_summarization_monitor()
        monitor1.record_summarization("test", 50, 20, 25000, 10000, 500.0)

        reset_summarization_monitor()

        monitor2 = get_summarization_monitor()
        assert monitor1 is not monitor2
        assert monitor2.get_statistics()["total_summarizations"] == 0

