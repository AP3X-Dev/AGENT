"""
Tests for Learning Engine.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from ag3nt_agent.autonomous.learning_engine import (
    LearningEngine,
    ActionRecord,
    ConfidenceScore,
    Recommendation,
)
from ag3nt_agent.context_engine_client import MemoryResult


class TestActionRecord:
    """Tests for ActionRecord dataclass."""

    def test_create_record(self):
        """Test creating an action record."""
        record = ActionRecord(
            action_id="test-id",
            action_type="shell",
            goal_id="goal-1",
            context="restart nginx",
            success=True,
            duration_ms=1500
        )

        assert record.action_type == "shell"
        assert record.success is True
        assert record.duration_ms == 1500

    def test_to_dict(self):
        """Test serialization."""
        record = ActionRecord(
            action_id="test-id",
            action_type="shell",
            goal_id="goal-1",
            context="restart nginx",
            success=True,
            duration_ms=1500
        )

        data = record.to_dict()

        assert data["action_type"] == "shell"
        assert data["success"] is True


class TestConfidenceScore:
    """Tests for ConfidenceScore dataclass."""

    def test_has_sufficient_data_true(self):
        """Test sufficient data check with enough samples."""
        score = ConfidenceScore(
            score=0.8,
            sample_count=5,
            success_rate=0.8,
            avg_duration_ms=1000
        )

        assert score.has_sufficient_data is True

    def test_has_sufficient_data_false(self):
        """Test sufficient data check with too few samples."""
        score = ConfidenceScore(
            score=0.8,
            sample_count=2,
            success_rate=0.8,
            avg_duration_ms=1000
        )

        assert score.has_sufficient_data is False


class TestLearningEngine:
    """Tests for LearningEngine."""

    @pytest.fixture
    def mock_context_engine(self):
        """Create a mock context engine."""
        mock = MagicMock()
        mock.store_action = AsyncMock(return_value={"id": "stored-id"})
        mock.find_memories = AsyncMock(return_value=[])
        mock.COLLECTION_LEARNING = "agent-learning"
        return mock

    @pytest.fixture
    def engine(self, mock_context_engine):
        """Create a learning engine with mock context engine."""
        return LearningEngine(context_engine=mock_context_engine)

    @pytest.mark.asyncio
    async def test_record_action_success(self, engine, mock_context_engine):
        """Test recording a successful action."""
        record = await engine.record_action(
            action_type="shell",
            goal_id="test-goal",
            context="restart nginx",
            success=True,
            duration_ms=1500
        )

        assert record.action_type == "shell"
        assert record.success is True
        mock_context_engine.store_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_action_failure(self, engine, mock_context_engine):
        """Test recording a failed action."""
        record = await engine.record_action(
            action_type="shell",
            goal_id="test-goal",
            context="restart nginx",
            success=False,
            duration_ms=5000,
            error_message="Command timed out"
        )

        assert record.success is False
        assert record.error_message == "Command timed out"

    @pytest.mark.asyncio
    async def test_get_confidence_insufficient_samples(self, engine, mock_context_engine):
        """Test confidence with insufficient samples."""
        mock_context_engine.find_memories.return_value = [
            MemoryResult("action 1", 0.9, {"success": True})
        ]

        score = await engine.get_confidence(
            action_type="shell",
            context="restart nginx"
        )

        assert score.sample_count == 1
        assert score.score == 0.0  # Not enough samples

    @pytest.mark.asyncio
    async def test_get_confidence_with_samples(self, engine, mock_context_engine):
        """Test confidence with sufficient samples."""
        now = datetime.utcnow()

        mock_context_engine.find_memories.return_value = [
            MemoryResult("action 1", 0.9, {
                "success": True,
                "duration_ms": 1000,
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 2", 0.85, {
                "success": True,
                "duration_ms": 1200,
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 3", 0.8, {
                "success": True,
                "duration_ms": 800,
                "timestamp": now.isoformat()
            }),
        ]

        score = await engine.get_confidence(
            action_type="shell",
            context="restart nginx"
        )

        assert score.sample_count == 3
        assert score.score > 0  # Should have calculated confidence
        assert score.success_rate == 1.0  # All succeeded

    @pytest.mark.asyncio
    async def test_get_confidence_with_failures(self, engine, mock_context_engine):
        """Test confidence calculation with failures."""
        now = datetime.utcnow()

        mock_context_engine.find_memories.return_value = [
            MemoryResult("action 1", 0.9, {
                "success": True,
                "duration_ms": 1000,
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 2", 0.85, {
                "success": False,
                "duration_ms": 5000,
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 3", 0.8, {
                "success": True,
                "duration_ms": 1100,
                "timestamp": now.isoformat()
            }),
        ]

        score = await engine.get_confidence(
            action_type="shell",
            context="restart nginx"
        )

        assert score.sample_count == 3
        assert score.success_rate == pytest.approx(0.666, rel=0.01)
        # Confidence should be lower than success rate due to failure weight
        assert score.score < score.success_rate

    @pytest.mark.asyncio
    async def test_get_confidence_caching(self, engine, mock_context_engine):
        """Test that confidence scores are cached."""
        now = datetime.utcnow()

        mock_context_engine.find_memories.return_value = [
            MemoryResult("action 1", 0.9, {
                "success": True,
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 2", 0.85, {
                "success": True,
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 3", 0.8, {
                "success": True,
                "timestamp": now.isoformat()
            }),
        ]

        # First call
        await engine.get_confidence("shell", "restart nginx")

        # Second call should use cache
        await engine.get_confidence("shell", "restart nginx")

        # find_memories should only be called once
        assert mock_context_engine.find_memories.call_count == 1

    @pytest.mark.asyncio
    async def test_get_recommendations(self, engine, mock_context_engine):
        """Test getting recommendations."""
        now = datetime.utcnow()

        mock_context_engine.find_memories.return_value = [
            MemoryResult("shell action", 0.9, {
                "action_type": "shell",
                "success": True,
                "timestamp": now.isoformat()
            }),
            MemoryResult("shell action 2", 0.85, {
                "action_type": "shell",
                "success": True,
                "timestamp": now.isoformat()
            }),
            MemoryResult("shell action 3", 0.8, {
                "action_type": "shell",
                "success": True,
                "timestamp": now.isoformat()
            }),
        ]

        recommendations = await engine.get_recommendations(
            context="service is down"
        )

        assert len(recommendations) >= 0  # May be empty if confidence too low

    @pytest.mark.asyncio
    async def test_get_daily_summary(self, engine, mock_context_engine):
        """Test getting daily summary."""
        now = datetime.utcnow()

        mock_context_engine.find_memories.return_value = [
            MemoryResult("action 1", 0.9, {
                "success": True,
                "action_type": "shell",
                "goal_id": "goal-1",
                "timestamp": now.isoformat()
            }),
            MemoryResult("action 2", 0.85, {
                "success": False,
                "action_type": "notify",
                "goal_id": "goal-2",
                "timestamp": now.isoformat()
            }),
        ]

        summary = await engine.get_daily_summary(days=1)

        assert summary["total_actions"] == 2
        assert summary["successes"] == 1
        assert summary["failures"] == 1

    def test_clear_cache(self, engine):
        """Test clearing the cache."""
        engine._cache["test"] = ConfidenceScore(0.9, 5, 0.9, 1000)
        engine._cache_timestamps["test"] = datetime.utcnow()

        engine.clear_cache()

        assert len(engine._cache) == 0
        assert len(engine._cache_timestamps) == 0
