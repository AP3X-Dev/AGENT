"""
Tests for Event Bus.
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from ag3nt_agent.autonomous.event_bus import (
    Event,
    EventBus,
    EventPriority,
    create_event,
)


class TestEvent:
    """Tests for Event dataclass."""

    def test_create_event_basic(self):
        """Test basic event creation."""
        event = Event(
            event_type="test_event",
            source="test_source",
            payload={"key": "value"}
        )

        assert event.event_type == "test_event"
        assert event.source == "test_source"
        assert event.payload == {"key": "value"}
        assert event.priority == EventPriority.MEDIUM
        assert event.event_id is not None
        assert event.dedup_key is not None

    def test_create_event_with_priority(self):
        """Test event creation with custom priority."""
        event = Event(
            event_type="critical_event",
            source="monitor",
            priority=EventPriority.CRITICAL
        )

        assert event.priority == EventPriority.CRITICAL

    def test_dedup_key_generation(self):
        """Test dedup key is consistent for same content."""
        event1 = Event(
            event_type="test",
            source="src",
            payload={"a": 1}
        )
        event2 = Event(
            event_type="test",
            source="src",
            payload={"a": 1}
        )

        assert event1.dedup_key == event2.dedup_key

    def test_dedup_key_different_for_different_content(self):
        """Test dedup key differs for different content."""
        event1 = Event(
            event_type="test",
            source="src",
            payload={"a": 1}
        )
        event2 = Event(
            event_type="test",
            source="src",
            payload={"a": 2}
        )

        assert event1.dedup_key != event2.dedup_key

    def test_to_dict(self):
        """Test event serialization."""
        event = Event(
            event_type="test",
            source="src",
            payload={"key": "value"}
        )

        data = event.to_dict()

        assert data["event_type"] == "test"
        assert data["source"] == "src"
        assert data["payload"] == {"key": "value"}
        assert "event_id" in data
        assert "timestamp" in data

    def test_from_dict(self):
        """Test event deserialization."""
        data = {
            "event_type": "test",
            "source": "src",
            "payload": {"key": "value"},
            "priority": "HIGH",
            "timestamp": datetime.utcnow().isoformat()
        }

        event = Event.from_dict(data)

        assert event.event_type == "test"
        assert event.source == "src"
        assert event.priority == EventPriority.HIGH


class TestEventBus:
    """Tests for EventBus."""

    @pytest.fixture
    def event_bus(self):
        """Create a test event bus."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_start_stop(self, event_bus):
        """Test starting and stopping the event bus."""
        await event_bus.start()
        assert event_bus.is_running

        await event_bus.stop()
        assert not event_bus.is_running

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus):
        """Test subscribing to and publishing events."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        event_bus.subscribe(handler)
        await event_bus.start()

        event = Event(event_type="test", source="src")
        await event_bus.publish(event)

        # Wait for processing
        await asyncio.sleep(0.1)

        assert len(received_events) == 1
        assert received_events[0].event_type == "test"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_subscribe_with_type_filter(self, event_bus):
        """Test subscribing to specific event types."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        event_bus.subscribe(handler, event_types={"type_a"})
        await event_bus.start()

        # Publish matching event
        await event_bus.publish(Event(event_type="type_a", source="src"))

        # Publish non-matching event
        await event_bus.publish(Event(event_type="type_b", source="src"))

        await asyncio.sleep(0.1)

        assert len(received_events) == 1
        assert received_events[0].event_type == "type_a"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus):
        """Test unsubscribing handlers."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        sub_id = event_bus.subscribe(handler)
        await event_bus.start()

        # Publish first event
        await event_bus.publish(Event(event_type="test", source="src"))
        await asyncio.sleep(0.1)

        # Unsubscribe
        result = event_bus.unsubscribe(sub_id)
        assert result is True

        # Publish second event
        await event_bus.publish(Event(event_type="test2", source="src"))
        await asyncio.sleep(0.1)

        # Should only have first event
        assert len(received_events) == 1

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_deduplication(self, event_bus):
        """Test event deduplication."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        event_bus.subscribe(handler)
        await event_bus.start()

        # Publish same event twice
        event = Event(event_type="test", source="src", payload={"key": "value"})
        await event_bus.publish(event)

        event2 = Event(event_type="test", source="src", payload={"key": "value"})
        result = await event_bus.publish(event2)

        await asyncio.sleep(0.1)

        # Second publish should be deduplicated
        assert result is False
        assert len(received_events) == 1

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_priority_ordering(self, event_bus):
        """Test that higher priority events are processed first."""
        received_events = []

        async def handler(event):
            received_events.append(event.priority)

        event_bus.subscribe(handler)

        # Publish events in reverse priority order
        await event_bus.publish(Event(event_type="low", source="src", priority=EventPriority.LOW))
        await event_bus.publish(Event(event_type="critical", source="src", priority=EventPriority.CRITICAL))
        await event_bus.publish(Event(event_type="medium", source="src", priority=EventPriority.MEDIUM))

        await event_bus.start()
        await asyncio.sleep(0.2)
        await event_bus.stop()

        # Critical should be first
        assert received_events[0] == EventPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, event_bus):
        """Test failed events go to DLQ."""
        async def failing_handler(event):
            raise ValueError("Handler failed")

        # Create event bus with shorter retry delay for faster tests
        fast_bus = EventBus(max_retries=2, retry_delay_seconds=0.1)
        fast_bus.subscribe(failing_handler)
        await fast_bus.start()

        await fast_bus.publish(Event(event_type="test", source="src"))
        await asyncio.sleep(0.5)  # Wait for retries (2 retries * 0.1s + processing)

        dlq = fast_bus.get_dlq()
        assert len(dlq) == 1
        assert "Handler failed" in dlq[0]["error"]

        await fast_bus.stop()

    @pytest.mark.asyncio
    async def test_get_metrics(self, event_bus):
        """Test metrics collection."""
        received = []

        async def handler(event):
            received.append(event)

        event_bus.subscribe(handler)
        await event_bus.start()

        await event_bus.publish(Event(event_type="test", source="src"))
        await asyncio.sleep(0.1)

        metrics = event_bus.get_metrics()

        assert metrics["events_received"] == 1
        assert metrics["events_processed"] == 1
        assert metrics["subscriptions"] == 1

        await event_bus.stop()


class TestCreateEvent:
    """Tests for create_event helper."""

    def test_create_event_simple(self):
        """Test simple event creation."""
        event = create_event("test_type", "test_source")

        assert event.event_type == "test_type"
        assert event.source == "test_source"
        assert event.priority == EventPriority.MEDIUM

    def test_create_event_with_all_params(self):
        """Test event creation with all parameters."""
        event = create_event(
            event_type="http_check",
            source="monitor",
            payload={"status": 500},
            priority=EventPriority.HIGH,
            custom_field="value"
        )

        assert event.event_type == "http_check"
        assert event.payload == {"status": 500}
        assert event.priority == EventPriority.HIGH
        assert event.metadata["custom_field"] == "value"
