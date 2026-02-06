"""
Learning Engine for AG3NT Autonomous System

Tracks action outcomes and builds confidence scores using
Context-Engine's semantic memory for intelligent learning.

Key features:
- Semantic similarity-based confidence calculation
- Cross-session and cross-agent learning
- Action history with rich metadata
- Recommendation generation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..context_engine_client import (
    ContextEngineClient,
    get_context_engine,
    MemoryResult,
    ContextEngineError
)

logger = logging.getLogger(__name__)


@dataclass
class ActionRecord:
    """Record of an executed action."""
    action_id: str
    action_type: str
    goal_id: str
    context: str
    success: bool
    duration_ms: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "goal_id": self.goal_id,
            "context": self.context,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "metadata": self.metadata
        }


@dataclass
class ConfidenceScore:
    """Confidence score with supporting data."""
    score: float  # 0.0 to 1.0
    sample_count: int
    success_rate: float
    avg_duration_ms: float
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    similar_actions: list = field(default_factory=list)

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough samples for meaningful confidence."""
        return self.sample_count >= 3


@dataclass
class Recommendation:
    """A learning-based recommendation."""
    action_type: str
    context: str
    confidence: float
    reason: str
    supporting_actions: list = field(default_factory=list)


class LearningEngine:
    """
    Learning engine backed by Context-Engine semantic memory.

    Uses semantic search to find similar past actions and
    calculate confidence scores based on outcomes.
    """

    def __init__(
        self,
        context_engine: Optional[ContextEngineClient] = None,
        min_samples: int = 3,
        confidence_decay_days: int = 30,
        success_weight: float = 1.0,
        failure_weight: float = 1.5
    ):
        """
        Initialize the learning engine.

        Args:
            context_engine: Context-Engine client (uses singleton if not provided)
            min_samples: Minimum samples required for confidence
            confidence_decay_days: Days after which confidence starts decaying
            success_weight: Weight multiplier for successful actions
            failure_weight: Weight multiplier for failed actions
        """
        self._ce = context_engine
        self.min_samples = min_samples
        self.confidence_decay_days = confidence_decay_days
        self.success_weight = success_weight
        self.failure_weight = failure_weight

        # Local cache for recent actions (reduces API calls)
        self._cache: dict[str, ConfidenceScore] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._cache_timestamps: dict[str, datetime] = {}

    @property
    def context_engine(self) -> ContextEngineClient:
        """Get the Context-Engine client."""
        if self._ce is None:
            self._ce = get_context_engine()
        return self._ce

    async def record_action(
        self,
        action_type: str,
        goal_id: str,
        context: str,
        success: bool,
        duration_ms: int,
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> ActionRecord:
        """
        Record an action outcome for learning.

        Args:
            action_type: Type of action (shell, notify, agent, etc.)
            goal_id: Goal that triggered this action
            context: Description of what was done
            success: Whether the action succeeded
            duration_ms: Execution time
            error_message: Error details if failed
            metadata: Additional metadata

        Returns:
            The created ActionRecord
        """
        from uuid import uuid4

        record = ActionRecord(
            action_id=str(uuid4()),
            action_type=action_type,
            goal_id=goal_id,
            context=context,
            success=success,
            duration_ms=duration_ms,
            error_message=error_message,
            metadata=metadata or {}
        )

        # Store in Context-Engine
        try:
            await self.context_engine.store_action(
                action_type=action_type,
                goal_id=goal_id,
                success=success,
                duration_ms=duration_ms,
                context=context,
                details={
                    "action_id": record.action_id,
                    "error_message": error_message,
                    **(metadata or {})
                }
            )

            logger.info(
                f"Recorded action: {action_type} for {goal_id} "
                f"({'success' if success else 'failure'})"
            )

            # Invalidate cache for this action type
            self._invalidate_cache(action_type)

        except ContextEngineError as e:
            logger.error(f"Failed to store action in Context-Engine: {e}")
            # Continue without storage - action was still executed

        return record

    async def get_confidence(
        self,
        action_type: str,
        context: str
    ) -> ConfidenceScore:
        """
        Get confidence score for an action.

        Uses semantic search to find similar past actions and
        calculates weighted confidence based on outcomes.

        Args:
            action_type: Type of action
            context: Current action context

        Returns:
            ConfidenceScore with detailed breakdown
        """
        # Check cache
        cache_key = f"{action_type}:{context[:100]}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Query Context-Engine for similar actions
        try:
            results = await self.context_engine.find_memories(
                query=f"{action_type} action: {context}",
                limit=50,
                collection=ContextEngineClient.COLLECTION_LEARNING,
                min_score=0.3  # Only reasonably similar actions
            )
        except ContextEngineError as e:
            logger.error(f"Failed to query action history: {e}")
            return ConfidenceScore(
                score=0.0,
                sample_count=0,
                success_rate=0.0,
                avg_duration_ms=0.0
            )

        if len(results) < self.min_samples:
            return ConfidenceScore(
                score=0.0,
                sample_count=len(results),
                success_rate=0.0,
                avg_duration_ms=0.0,
                similar_actions=results
            )

        # Calculate weighted confidence
        confidence_score = self._calculate_confidence(results)

        # Cache the result
        self._set_cached(cache_key, confidence_score)

        return confidence_score

    def _calculate_confidence(self, results: list[MemoryResult]) -> ConfidenceScore:
        """
        Calculate confidence score from similar actions.

        Weights:
        - Similarity score (more similar = more weight)
        - Recency (recent actions weighted higher)
        - Failure penalty (failures weight 1.5x more than successes)
        """
        weighted_success = 0.0
        total_weight = 0.0
        total_duration = 0
        successes = 0
        failures = 0
        last_success = None
        last_failure = None

        now = datetime.utcnow()

        for result in results:
            metadata = result.metadata
            success = metadata.get("success", False)
            duration = metadata.get("duration_ms", 0)
            timestamp_str = metadata.get("timestamp")

            # Parse timestamp for recency weighting
            try:
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else now
            except (ValueError, TypeError):
                timestamp = now

            # Calculate recency factor (1.0 for today, decays over time)
            days_old = (now - timestamp).days
            recency_factor = max(0.1, 1.0 - (days_old / self.confidence_decay_days))

            # Base weight from similarity score
            weight = result.score * recency_factor

            # Apply success/failure weights
            if success:
                weight *= self.success_weight
                weighted_success += weight
                successes += 1
                if last_success is None or timestamp > last_success:
                    last_success = timestamp
            else:
                weight *= self.failure_weight
                failures += 1
                if last_failure is None or timestamp > last_failure:
                    last_failure = timestamp

            total_weight += weight
            total_duration += duration

        # Calculate final confidence
        confidence = weighted_success / total_weight if total_weight > 0 else 0.0
        sample_count = len(results)
        success_rate = successes / sample_count if sample_count > 0 else 0.0
        avg_duration = total_duration / sample_count if sample_count > 0 else 0.0

        return ConfidenceScore(
            score=confidence,
            sample_count=sample_count,
            success_rate=success_rate,
            avg_duration_ms=avg_duration,
            last_success=last_success,
            last_failure=last_failure,
            similar_actions=results[:5]  # Keep top 5 for reference
        )

    async def get_recommendations(
        self,
        context: str,
        limit: int = 5
    ) -> list[Recommendation]:
        """
        Get action recommendations based on learning history.

        Args:
            context: Current situation context
            limit: Maximum recommendations

        Returns:
            List of recommended actions with confidence
        """
        try:
            results = await self.context_engine.find_memories(
                query=context,
                limit=limit * 3,  # Get extra to filter
                collection=ContextEngineClient.COLLECTION_LEARNING,
                min_score=0.5
            )
        except ContextEngineError as e:
            logger.error(f"Failed to get recommendations: {e}")
            return []

        # Group by action type
        action_groups: dict[str, list[MemoryResult]] = {}
        for result in results:
            action_type = result.metadata.get("action_type", "unknown")
            if action_type not in action_groups:
                action_groups[action_type] = []
            action_groups[action_type].append(result)

        # Generate recommendations
        recommendations = []
        for action_type, group_results in action_groups.items():
            confidence = self._calculate_confidence(group_results)

            if confidence.score > 0.5 and confidence.has_sufficient_data:
                recommendations.append(Recommendation(
                    action_type=action_type,
                    context=context,
                    confidence=confidence.score,
                    reason=self._generate_reason(action_type, confidence),
                    supporting_actions=group_results[:3]
                ))

        # Sort by confidence and limit
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        return recommendations[:limit]

    def _generate_reason(self, action_type: str, confidence: ConfidenceScore) -> str:
        """Generate a human-readable reason for a recommendation."""
        if confidence.success_rate >= 0.9:
            return (
                f"This {action_type} action has a {confidence.success_rate:.0%} success rate "
                f"across {confidence.sample_count} similar situations."
            )
        elif confidence.success_rate >= 0.7:
            return (
                f"This {action_type} action usually works ({confidence.success_rate:.0%} success rate) "
                f"with an average execution time of {confidence.avg_duration_ms:.0f}ms."
            )
        else:
            return (
                f"This {action_type} action has worked in similar contexts, "
                f"though with mixed results ({confidence.success_rate:.0%} success rate)."
            )

    async def get_daily_summary(self, days: int = 1) -> dict:
        """
        Get a summary of learning activity.

        Args:
            days: Number of days to include

        Returns:
            Summary statistics
        """
        try:
            # Search for recent actions
            results = await self.context_engine.find_memories(
                query="action executed",
                limit=100,
                collection=ContextEngineClient.COLLECTION_LEARNING
            )
        except ContextEngineError:
            return {"error": "Failed to retrieve action history"}

        # Filter by date
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent = []

        for result in results:
            timestamp_str = result.metadata.get("timestamp")
            try:
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
                if timestamp and timestamp >= cutoff:
                    recent.append(result)
            except (ValueError, TypeError):
                continue

        # Calculate statistics
        total = len(recent)
        successes = sum(1 for r in recent if r.metadata.get("success", False))
        failures = total - successes

        # Group by action type
        by_type: dict[str, dict] = {}
        for result in recent:
            action_type = result.metadata.get("action_type", "unknown")
            if action_type not in by_type:
                by_type[action_type] = {"total": 0, "success": 0, "failure": 0}
            by_type[action_type]["total"] += 1
            if result.metadata.get("success", False):
                by_type[action_type]["success"] += 1
            else:
                by_type[action_type]["failure"] += 1

        # Group by goal
        by_goal: dict[str, dict] = {}
        for result in recent:
            goal_id = result.metadata.get("goal_id", "unknown")
            if goal_id not in by_goal:
                by_goal[goal_id] = {"total": 0, "success": 0, "failure": 0}
            by_goal[goal_id]["total"] += 1
            if result.metadata.get("success", False):
                by_goal[goal_id]["success"] += 1
            else:
                by_goal[goal_id]["failure"] += 1

        return {
            "period_days": days,
            "total_actions": total,
            "successes": successes,
            "failures": failures,
            "success_rate": successes / total if total > 0 else 0.0,
            "by_action_type": by_type,
            "by_goal": by_goal
        }

    def _get_cached(self, key: str) -> Optional[ConfidenceScore]:
        """Get cached confidence score if not expired."""
        if key in self._cache:
            cached_at = self._cache_timestamps.get(key)
            if cached_at and datetime.utcnow() - cached_at < self._cache_ttl:
                return self._cache[key]
            else:
                # Expired, remove from cache
                del self._cache[key]
                self._cache_timestamps.pop(key, None)
        return None

    def _set_cached(self, key: str, score: ConfidenceScore):
        """Cache a confidence score."""
        self._cache[key] = score
        self._cache_timestamps[key] = datetime.utcnow()

    def _invalidate_cache(self, action_type: str):
        """Invalidate cache entries for an action type."""
        to_remove = [k for k in self._cache if k.startswith(f"{action_type}:")]
        for key in to_remove:
            del self._cache[key]
            self._cache_timestamps.pop(key, None)

    def clear_cache(self):
        """Clear all cached confidence scores."""
        self._cache.clear()
        self._cache_timestamps.clear()
