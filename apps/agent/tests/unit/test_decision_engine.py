"""
Tests for Decision Engine.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from ag3nt_agent.autonomous.decision_engine import (
    DecisionEngine,
    DecisionConfig,
    Decision,
    DecisionType,
    DecisionAuditLog,
)
from ag3nt_agent.autonomous.goal_manager import (
    Goal,
    Trigger,
    Action,
    ActionType,
    RiskLevel,
    Limits,
)
from ag3nt_agent.autonomous.event_bus import Event
from ag3nt_agent.autonomous.learning_engine import ConfidenceScore


class TestDecisionType:
    """Tests for DecisionType enum."""

    def test_decision_types(self):
        """Test all decision types exist."""
        assert DecisionType.ACT.value == "act"
        assert DecisionType.ASK.value == "ask"
        assert DecisionType.DEFER.value == "defer"
        assert DecisionType.ESCALATE.value == "escalate"
        assert DecisionType.REJECT.value == "reject"


class TestDecision:
    """Tests for Decision dataclass."""

    @pytest.fixture
    def sample_goal(self):
        """Create a sample goal."""
        return Goal(
            id="test-goal",
            name="Test Goal",
            description="A test goal",
            trigger=Trigger(event_type="test"),
            action=Action(type=ActionType.SHELL, command="echo test"),
            risk_level=RiskLevel.MEDIUM
        )

    @pytest.fixture
    def sample_event(self):
        """Create a sample event."""
        return Event(event_type="test", source="test")

    @pytest.fixture
    def sample_confidence(self):
        """Create a sample confidence score."""
        return ConfidenceScore(
            score=0.8,
            sample_count=10,
            success_rate=0.85,
            avg_duration_ms=1500
        )

    def test_should_execute_act(self, sample_goal, sample_event, sample_confidence):
        """Test should_execute for ACT decision."""
        decision = Decision(
            decision_type=DecisionType.ACT,
            goal=sample_goal,
            event=sample_event,
            confidence=sample_confidence,
            reason="Confidence met threshold"
        )

        assert decision.should_execute is True
        assert decision.needs_approval is False

    def test_needs_approval_ask(self, sample_goal, sample_event, sample_confidence):
        """Test needs_approval for ASK decision."""
        decision = Decision(
            decision_type=DecisionType.ASK,
            goal=sample_goal,
            event=sample_event,
            confidence=sample_confidence,
            reason="Confidence below threshold"
        )

        assert decision.should_execute is False
        assert decision.needs_approval is True

    def test_to_dict(self, sample_goal, sample_event, sample_confidence):
        """Test decision serialization."""
        decision = Decision(
            decision_type=DecisionType.ACT,
            goal=sample_goal,
            event=sample_event,
            confidence=sample_confidence,
            reason="Test reason"
        )

        data = decision.to_dict()

        assert data["decision_type"] == "act"
        assert data["goal_id"] == "test-goal"
        assert data["reason"] == "Test reason"


class TestDecisionConfig:
    """Tests for DecisionConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DecisionConfig()

        assert config.low_risk_threshold == 0.5
        assert config.medium_risk_threshold == 0.75
        assert config.high_risk_threshold == 0.9
        assert config.critical_risk_threshold == 1.0
        assert config.min_samples_required == 3

    def test_custom_values(self):
        """Test custom configuration values."""
        config = DecisionConfig(
            low_risk_threshold=0.6,
            min_samples_required=5
        )

        assert config.low_risk_threshold == 0.6
        assert config.min_samples_required == 5


class TestDecisionEngine:
    """Tests for DecisionEngine."""

    @pytest.fixture
    def mock_learning_engine(self):
        """Create a mock learning engine."""
        mock = MagicMock()
        mock.get_confidence = AsyncMock()
        return mock

    @pytest.fixture
    def engine(self, mock_learning_engine):
        """Create a decision engine."""
        return DecisionEngine(mock_learning_engine)

    @pytest.fixture
    def low_risk_goal(self):
        """Create a low risk goal."""
        return Goal(
            id="low-risk",
            name="Low Risk Goal",
            description="A low risk goal",
            trigger=Trigger(event_type="test"),
            action=Action(type=ActionType.NOTIFY, message="test"),
            risk_level=RiskLevel.LOW,
            confidence_threshold=0.5
        )

    @pytest.fixture
    def high_risk_goal(self):
        """Create a high risk goal."""
        return Goal(
            id="high-risk",
            name="High Risk Goal",
            description="A high risk goal",
            trigger=Trigger(event_type="test"),
            action=Action(type=ActionType.SHELL, command="rm -rf temp"),
            risk_level=RiskLevel.HIGH,
            confidence_threshold=0.9
        )

    @pytest.fixture
    def approval_required_goal(self):
        """Create a goal that always requires approval."""
        return Goal(
            id="approval-required",
            name="Approval Required Goal",
            description="Always needs approval",
            trigger=Trigger(event_type="test"),
            action=Action(type=ActionType.SHELL, command="echo test"),
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True
        )

    @pytest.fixture
    def sample_event(self):
        """Create a sample event."""
        return Event(event_type="test", source="test")

    @pytest.mark.asyncio
    async def test_evaluate_act_high_confidence(
        self, engine, mock_learning_engine, low_risk_goal, sample_event
    ):
        """Test ACT decision with high confidence."""
        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=0.9,
            sample_count=20,
            success_rate=0.9,
            avg_duration_ms=1000
        )

        decision = await engine.evaluate(low_risk_goal, sample_event)

        assert decision.decision_type == DecisionType.ACT

    @pytest.mark.asyncio
    async def test_evaluate_ask_low_confidence(
        self, engine, mock_learning_engine, low_risk_goal, sample_event
    ):
        """Test ASK decision with low confidence."""
        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=0.3,
            sample_count=20,
            success_rate=0.3,
            avg_duration_ms=1000
        )

        decision = await engine.evaluate(low_risk_goal, sample_event)

        assert decision.decision_type == DecisionType.ASK

    @pytest.mark.asyncio
    async def test_evaluate_ask_insufficient_samples(
        self, engine, mock_learning_engine, low_risk_goal, sample_event
    ):
        """Test ASK decision with insufficient samples."""
        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=0.9,
            sample_count=1,  # Below min_samples_required
            success_rate=1.0,
            avg_duration_ms=1000
        )

        decision = await engine.evaluate(low_risk_goal, sample_event)

        assert decision.decision_type == DecisionType.ASK
        assert "Insufficient history" in decision.reason

    @pytest.mark.asyncio
    async def test_evaluate_requires_approval(
        self, engine, mock_learning_engine, approval_required_goal, sample_event
    ):
        """Test ASK decision when goal requires approval."""
        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=1.0,
            sample_count=100,
            success_rate=1.0,
            avg_duration_ms=1000
        )

        decision = await engine.evaluate(approval_required_goal, sample_event)

        assert decision.decision_type == DecisionType.ASK
        assert "always require approval" in decision.reason

    @pytest.mark.asyncio
    async def test_evaluate_high_risk_needs_high_confidence(
        self, engine, mock_learning_engine, high_risk_goal, sample_event
    ):
        """Test that high risk goals need higher confidence."""
        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=0.7,  # Good but not enough for high risk
            sample_count=20,
            success_rate=0.7,
            avg_duration_ms=1000
        )

        decision = await engine.evaluate(high_risk_goal, sample_event)

        assert decision.decision_type == DecisionType.ASK

    @pytest.mark.asyncio
    async def test_evaluate_reject_very_low_confidence(
        self, engine, mock_learning_engine, low_risk_goal, sample_event
    ):
        """Test REJECT decision with very low confidence."""
        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=0.05,  # Below reject threshold
            sample_count=20,
            success_rate=0.05,
            avg_duration_ms=5000
        )

        decision = await engine.evaluate(low_risk_goal, sample_event)

        assert decision.decision_type == DecisionType.REJECT

    @pytest.mark.asyncio
    async def test_evaluate_escalate_after_failures(
        self, engine, mock_learning_engine, low_risk_goal, sample_event
    ):
        """Test ESCALATE decision after multiple failures."""
        # Record failures
        for _ in range(3):
            engine.record_outcome(low_risk_goal.id, success=False)

        mock_learning_engine.get_confidence.return_value = ConfidenceScore(
            score=0.8,
            sample_count=20,
            success_rate=0.8,
            avg_duration_ms=1000
        )

        decision = await engine.evaluate(low_risk_goal, sample_event)

        assert decision.decision_type == DecisionType.ESCALATE

    def test_record_outcome_success(self, engine):
        """Test recording successful outcome resets failures."""
        engine._failure_counts["goal-1"] = 2
        engine.record_outcome("goal-1", success=True)

        assert engine._failure_counts["goal-1"] == 0

    def test_record_outcome_failure(self, engine):
        """Test recording failure increments counter."""
        engine.record_outcome("goal-1", success=False)
        engine.record_outcome("goal-1", success=False)

        assert engine._failure_counts["goal-1"] == 2

    @pytest.mark.asyncio
    async def test_get_explanation(
        self, engine, mock_learning_engine, low_risk_goal, sample_event
    ):
        """Test generating explanation for decision."""
        confidence = ConfidenceScore(
            score=0.8,
            sample_count=20,
            success_rate=0.85,
            avg_duration_ms=1000
        )

        decision = Decision(
            decision_type=DecisionType.ACT,
            goal=low_risk_goal,
            event=sample_event,
            confidence=confidence,
            reason="Test reason"
        )

        explanation = engine.get_explanation(decision)

        assert "ACT" in explanation
        assert "Low Risk Goal" in explanation
        assert "80%" in explanation  # Confidence score


class TestDecisionAuditLog:
    """Tests for DecisionAuditLog."""

    @pytest.fixture
    def sample_decision(self):
        """Create a sample decision."""
        goal = Goal(
            id="test-goal",
            name="Test Goal",
            description="Test",
            trigger=Trigger(event_type="test"),
            action=Action(type=ActionType.SHELL, command="echo test")
        )
        event = Event(event_type="test", source="test")
        confidence = ConfidenceScore(0.8, 10, 0.8, 1000)

        return Decision(
            decision_type=DecisionType.ACT,
            goal=goal,
            event=event,
            confidence=confidence,
            reason="Test"
        )

    def test_record_and_get_recent(self, sample_decision):
        """Test recording and retrieving decisions."""
        log = DecisionAuditLog()

        log.record(sample_decision)
        log.record(sample_decision)

        recent = log.get_recent(limit=10)

        assert len(recent) == 2

    def test_get_by_goal(self, sample_decision):
        """Test filtering by goal."""
        log = DecisionAuditLog()
        log.record(sample_decision)

        results = log.get_by_goal("test-goal")

        assert len(results) == 1

    def test_get_by_type(self, sample_decision):
        """Test filtering by type."""
        log = DecisionAuditLog()
        log.record(sample_decision)

        results = log.get_by_type(DecisionType.ACT)

        assert len(results) == 1

    def test_get_stats(self, sample_decision):
        """Test statistics calculation."""
        log = DecisionAuditLog()
        log.record(sample_decision)

        stats = log.get_stats()

        assert stats["total"] == 1
        assert stats["act_rate"] == 1.0

    def test_max_entries_trim(self):
        """Test that log is trimmed when over max entries."""
        log = DecisionAuditLog(max_entries=5)

        goal = Goal(
            id="test",
            name="Test",
            description="Test",
            trigger=Trigger(event_type="test"),
            action=Action(type=ActionType.SHELL, command="echo test")
        )
        event = Event(event_type="test", source="test")
        confidence = ConfidenceScore(0.8, 10, 0.8, 1000)

        for i in range(10):
            decision = Decision(
                decision_type=DecisionType.ACT,
                goal=goal,
                event=event,
                confidence=confidence,
                reason=f"Test {i}"
            )
            log.record(decision)

        assert len(log._log) == 5
