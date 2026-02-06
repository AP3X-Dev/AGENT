"""
Decision Engine for AG3NT Autonomous System

Evaluates whether to act autonomously or request approval based on:
- Risk level of the action
- Confidence from learning history
- Budget constraints
- User preferences
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .learning_engine import LearningEngine, ConfidenceScore
from .goal_manager import Goal, RiskLevel
from .event_bus import Event

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of decisions the engine can make."""
    ACT = "act"           # Execute autonomously
    ASK = "ask"           # Request approval
    DEFER = "defer"       # Defer to later
    ESCALATE = "escalate" # Escalate to higher authority
    REJECT = "reject"     # Reject the action


@dataclass
class Decision:
    """
    A decision made by the engine.

    Contains the decision type, reasoning, and supporting data.
    """
    decision_type: DecisionType
    goal: Goal
    event: Event
    confidence: ConfidenceScore
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)

    @property
    def should_execute(self) -> bool:
        """Check if this decision means the action should be executed."""
        return self.decision_type == DecisionType.ACT

    @property
    def needs_approval(self) -> bool:
        """Check if this decision requires human approval."""
        return self.decision_type == DecisionType.ASK

    def to_dict(self) -> dict:
        return {
            "decision_type": self.decision_type.value,
            "goal_id": self.goal.id,
            "goal_name": self.goal.name,
            "event_id": self.event.event_id,
            "confidence_score": self.confidence.score,
            "confidence_samples": self.confidence.sample_count,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class DecisionConfig:
    """Configuration for decision making."""
    # Confidence thresholds by risk level
    low_risk_threshold: float = 0.5
    medium_risk_threshold: float = 0.75
    high_risk_threshold: float = 0.9
    critical_risk_threshold: float = 1.0  # Always ask

    # Minimum samples required
    min_samples_required: int = 3

    # Auto-reject if confidence is too low
    reject_below_confidence: float = 0.1

    # Escalation thresholds
    escalate_after_failures: int = 3


class DecisionEngine:
    """
    Makes decisions about whether to act autonomously.

    The decision process:
    1. Get confidence score from learning engine
    2. Compare against goal's risk level threshold
    3. Check for special conditions (budget, failures, etc.)
    4. Return decision with explanation
    """

    def __init__(
        self,
        learning_engine: LearningEngine,
        config: Optional[DecisionConfig] = None
    ):
        """
        Initialize the decision engine.

        Args:
            learning_engine: Learning engine for confidence scores
            config: Decision configuration
        """
        self.learning = learning_engine
        self.config = config or DecisionConfig()

        # Track recent failures for escalation
        self._failure_counts: dict[str, int] = {}

    async def evaluate(self, goal: Goal, event: Event) -> Decision:
        """
        Evaluate whether to act on an event.

        Args:
            goal: The goal to potentially execute
            event: The triggering event

        Returns:
            Decision with type and reasoning
        """
        # Get confidence from learning engine
        context = self._build_context(goal, event)
        confidence = await self.learning.get_confidence(
            action_type=goal.action.type.value,
            context=context
        )

        # Check if goal requires approval
        if goal.requires_approval:
            return self._decide_ask(
                goal, event, confidence,
                "Goal is configured to always require approval"
            )

        # Check for insufficient data
        if confidence.sample_count < self.config.min_samples_required:
            return self._decide_ask(
                goal, event, confidence,
                f"Insufficient history ({confidence.sample_count} samples, "
                f"need {self.config.min_samples_required})"
            )

        # Check for very low confidence
        if confidence.score < self.config.reject_below_confidence:
            return self._decide_reject(
                goal, event, confidence,
                f"Confidence too low ({confidence.score:.0%})"
            )

        # Get threshold based on risk level
        threshold = self._get_threshold(goal.risk_level)

        # Also consider goal's explicit threshold
        effective_threshold = max(threshold, goal.confidence_threshold)

        # Check for escalation (too many failures)
        failure_count = self._failure_counts.get(goal.id, 0)
        if failure_count >= self.config.escalate_after_failures:
            return self._decide_escalate(
                goal, event, confidence,
                f"Too many recent failures ({failure_count})"
            )

        # Make the decision
        if confidence.score >= effective_threshold:
            return self._decide_act(
                goal, event, confidence,
                f"Confidence ({confidence.score:.0%}) meets threshold ({effective_threshold:.0%})"
            )
        else:
            return self._decide_ask(
                goal, event, confidence,
                f"Confidence ({confidence.score:.0%}) below threshold ({effective_threshold:.0%})"
            )

    def _build_context(self, goal: Goal, event: Event) -> str:
        """Build context string for confidence lookup."""
        parts = [
            f"Goal: {goal.name}",
            f"Event: {event.event_type} from {event.source}"
        ]

        # Add relevant payload details
        for key, value in event.payload.items():
            if isinstance(value, (str, int, float, bool)):
                parts.append(f"{key}: {value}")

        return " | ".join(parts)

    def _get_threshold(self, risk_level: RiskLevel) -> float:
        """Get confidence threshold for a risk level."""
        return {
            RiskLevel.LOW: self.config.low_risk_threshold,
            RiskLevel.MEDIUM: self.config.medium_risk_threshold,
            RiskLevel.HIGH: self.config.high_risk_threshold,
            RiskLevel.CRITICAL: self.config.critical_risk_threshold
        }[risk_level]

    def _decide_act(
        self,
        goal: Goal,
        event: Event,
        confidence: ConfidenceScore,
        reason: str
    ) -> Decision:
        """Create an ACT decision."""
        return Decision(
            decision_type=DecisionType.ACT,
            goal=goal,
            event=event,
            confidence=confidence,
            reason=reason,
            metadata={
                "risk_level": goal.risk_level.value,
                "threshold": self._get_threshold(goal.risk_level),
                "success_rate": confidence.success_rate
            }
        )

    def _decide_ask(
        self,
        goal: Goal,
        event: Event,
        confidence: ConfidenceScore,
        reason: str
    ) -> Decision:
        """Create an ASK decision."""
        return Decision(
            decision_type=DecisionType.ASK,
            goal=goal,
            event=event,
            confidence=confidence,
            reason=reason,
            metadata={
                "risk_level": goal.risk_level.value,
                "threshold": self._get_threshold(goal.risk_level),
                "recommendation": "approve" if confidence.score > 0.5 else "review"
            }
        )

    def _decide_defer(
        self,
        goal: Goal,
        event: Event,
        confidence: ConfidenceScore,
        reason: str
    ) -> Decision:
        """Create a DEFER decision."""
        return Decision(
            decision_type=DecisionType.DEFER,
            goal=goal,
            event=event,
            confidence=confidence,
            reason=reason
        )

    def _decide_escalate(
        self,
        goal: Goal,
        event: Event,
        confidence: ConfidenceScore,
        reason: str
    ) -> Decision:
        """Create an ESCALATE decision."""
        return Decision(
            decision_type=DecisionType.ESCALATE,
            goal=goal,
            event=event,
            confidence=confidence,
            reason=reason,
            metadata={
                "failure_count": self._failure_counts.get(goal.id, 0),
                "requires_senior_approval": True
            }
        )

    def _decide_reject(
        self,
        goal: Goal,
        event: Event,
        confidence: ConfidenceScore,
        reason: str
    ) -> Decision:
        """Create a REJECT decision."""
        return Decision(
            decision_type=DecisionType.REJECT,
            goal=goal,
            event=event,
            confidence=confidence,
            reason=reason
        )

    def record_outcome(self, goal_id: str, success: bool):
        """
        Record the outcome of an action for escalation tracking.

        Args:
            goal_id: The goal that was executed
            success: Whether the action succeeded
        """
        if success:
            # Reset failure count on success
            self._failure_counts[goal_id] = 0
        else:
            # Increment failure count
            self._failure_counts[goal_id] = self._failure_counts.get(goal_id, 0) + 1

    def reset_failures(self, goal_id: str):
        """Reset failure count for a goal."""
        self._failure_counts[goal_id] = 0

    def get_explanation(self, decision: Decision) -> str:
        """
        Generate a human-readable explanation for a decision.

        Args:
            decision: The decision to explain

        Returns:
            Formatted explanation string
        """
        lines = [
            f"**Decision: {decision.decision_type.value.upper()}**",
            f"",
            f"**Goal:** {decision.goal.name}",
            f"**Event:** {decision.event.event_type} from {decision.event.source}",
            f"**Risk Level:** {decision.goal.risk_level.value}",
            f"",
            f"**Confidence Analysis:**",
            f"  - Score: {decision.confidence.score:.0%}",
            f"  - Samples: {decision.confidence.sample_count}",
            f"  - Success Rate: {decision.confidence.success_rate:.0%}",
            f"",
            f"**Reason:** {decision.reason}"
        ]

        if decision.needs_approval:
            rec = decision.metadata.get("recommendation", "review")
            lines.extend([
                f"",
                f"**Recommendation:** {rec.title()}"
            ])

        return "\n".join(lines)


class DecisionAuditLog:
    """
    Audit log for tracking all decisions.

    Maintains a rolling log of decisions for compliance and debugging.
    """

    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self._log: list[Decision] = []

    def record(self, decision: Decision):
        """Record a decision to the audit log."""
        self._log.append(decision)

        # Trim if over limit
        if len(self._log) > self.max_entries:
            self._log = self._log[-self.max_entries:]

    def get_recent(self, limit: int = 100) -> list[Decision]:
        """Get recent decisions."""
        return self._log[-limit:]

    def get_by_goal(self, goal_id: str, limit: int = 100) -> list[Decision]:
        """Get decisions for a specific goal."""
        matching = [d for d in self._log if d.goal.id == goal_id]
        return matching[-limit:]

    def get_by_type(self, decision_type: DecisionType, limit: int = 100) -> list[Decision]:
        """Get decisions of a specific type."""
        matching = [d for d in self._log if d.decision_type == decision_type]
        return matching[-limit:]

    def get_stats(self) -> dict:
        """Get decision statistics."""
        total = len(self._log)
        if total == 0:
            return {"total": 0}

        by_type = {}
        for d in self._log:
            by_type[d.decision_type.value] = by_type.get(d.decision_type.value, 0) + 1

        return {
            "total": total,
            "by_type": by_type,
            "act_rate": by_type.get("act", 0) / total,
            "ask_rate": by_type.get("ask", 0) / total,
            "reject_rate": by_type.get("reject", 0) / total
        }
