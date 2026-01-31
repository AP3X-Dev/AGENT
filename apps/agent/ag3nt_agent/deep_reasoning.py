"""Deep Reasoning Tool for AG3NT.

This module provides an enhanced sequential thinking tool for structured,
multi-step reasoning with support for branching, revision, hypothesis
generation, and verification.

Inspired by the Sequential Thinking MCP server, extended with:
- Confidence scoring per thought
- Multiple reasoning modes (analytical, creative, critical, exploratory)
- Evidence tracking and linking
- Memory integration for persistence
- Hypothesis generation and verification workflow
- Subagent delegation for complex sub-problems

Usage:
    from ag3nt_agent.deep_reasoning import deep_reasoning, get_reasoning_session

    # Use as a tool
    result = deep_reasoning(
        thought="Let me analyze this step by step...",
        thought_number=1,
        total_thoughts=5,
        next_thought_needed=True,
    )

    # Or access session directly
    session = get_reasoning_session("session_123")
    session.process_thought(thought_data)
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================


class ReasoningMode(str, Enum):
    """Mode of reasoning being applied."""

    ANALYTICAL = "analytical"  # Breaking down into components
    CREATIVE = "creative"  # Generating novel ideas
    CRITICAL = "critical"  # Evaluating and questioning
    EXPLORATORY = "exploratory"  # Exploring possibilities
    DEDUCTIVE = "deductive"  # From general to specific
    INDUCTIVE = "inductive"  # From specific to general
    ABDUCTIVE = "abductive"  # Best explanation inference


class ThoughtType(str, Enum):
    """Type of thought in the reasoning chain."""

    REGULAR = "regular"  # Normal analytical step
    HYPOTHESIS = "hypothesis"  # A hypothesis being proposed
    VERIFICATION = "verification"  # Verifying a hypothesis
    REVISION = "revision"  # Revising previous thinking
    BRANCH = "branch"  # Exploring alternative path
    CONCLUSION = "conclusion"  # Final conclusion
    QUESTION = "question"  # Raising a question
    EVIDENCE = "evidence"  # Presenting evidence


# Default configuration
DEFAULT_MAX_THOUGHTS = 50
DEFAULT_MAX_BRANCHES = 10
DEFAULT_MAX_HISTORY_SIZE = 1000


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class Evidence:
    """Evidence supporting a thought.

    Attributes:
        id: Unique evidence identifier
        source: Where the evidence came from
        content: The evidence content
        reliability: Reliability score (0.0-1.0)
        timestamp: When evidence was recorded
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: str = ""
    content: str = ""
    reliability: float = 0.8
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ThoughtNode:
    """A single thought in the reasoning chain.

    Attributes:
        id: Unique thought identifier
        thought_number: Position in the sequence
        content: The thought content
        thought_type: Type of thought
        reasoning_mode: Mode of reasoning used
        confidence: Confidence level (0.0-1.0)
        parent_id: ID of parent thought (for branches)
        branch_id: Branch identifier if on a branch
        revises_thought: ID of thought being revised
        evidence_ids: IDs of supporting evidence
        next_thought_needed: Whether more thinking is needed
        timestamp: When thought was created
        metadata: Additional metadata
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    thought_number: int = 1
    content: str = ""
    thought_type: ThoughtType = ThoughtType.REGULAR
    reasoning_mode: ReasoningMode = ReasoningMode.ANALYTICAL
    confidence: float = 0.7
    parent_id: str | None = None
    branch_id: str | None = None
    revises_thought: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    next_thought_needed: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "thought_number": self.thought_number,
            "content": self.content,
            "thought_type": self.thought_type.value,
            "reasoning_mode": self.reasoning_mode.value,
            "confidence": self.confidence,
            "parent_id": self.parent_id,
            "branch_id": self.branch_id,
            "revises_thought": self.revises_thought,
            "evidence_ids": self.evidence_ids,
            "next_thought_needed": self.next_thought_needed,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class Hypothesis:
    """A hypothesis being tested in the reasoning process.

    Attributes:
        id: Unique hypothesis identifier
        statement: The hypothesis statement
        status: Current status (proposed, testing, verified, refuted, revised)
        confidence: Confidence level (0.0-1.0)
        supporting_thought_ids: Thoughts supporting this hypothesis
        contradicting_thought_ids: Thoughts contradicting this hypothesis
        evidence_ids: Evidence related to this hypothesis
        created_at: When hypothesis was created
        resolved_at: When hypothesis was resolved (if applicable)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    statement: str = ""
    status: str = "proposed"  # proposed, testing, verified, refuted, revised
    confidence: float = 0.5
    supporting_thought_ids: list[str] = field(default_factory=list)
    contradicting_thought_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "statement": self.statement,
            "status": self.status,
            "confidence": self.confidence,
            "supporting_thought_ids": self.supporting_thought_ids,
            "contradicting_thought_ids": self.contradicting_thought_ids,
            "evidence_ids": self.evidence_ids,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class ReasoningResult:
    """Result from processing a thought.

    Attributes:
        thought_id: ID of the processed thought
        thought_number: Current thought number
        total_thoughts: Estimated total thoughts
        next_thought_needed: Whether another thought is needed
        branches: List of active branch IDs
        hypotheses: List of active hypotheses
        thought_history_length: Total thoughts in history
        average_confidence: Average confidence across thoughts
        current_mode: Current reasoning mode
        message: Guidance message for next step
    """

    thought_id: str
    thought_number: int
    total_thoughts: int
    next_thought_needed: bool
    branches: list[str]
    hypotheses: list[str]
    thought_history_length: int
    average_confidence: float
    current_mode: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "thought_id": self.thought_id,
            "thought_number": self.thought_number,
            "total_thoughts": self.total_thoughts,
            "next_thought_needed": self.next_thought_needed,
            "branches": self.branches,
            "hypotheses": self.hypotheses,
            "thought_history_length": self.thought_history_length,
            "average_confidence": self.average_confidence,
            "current_mode": self.current_mode,
            "message": self.message,
        }


# =============================================================================
# DEEP REASONING SESSION
# =============================================================================


class DeepReasoningSession:
    """Manages a deep reasoning session with thought tracking and analysis.

    This class provides structured reasoning capabilities including:
    - Sequential thought tracking
    - Branching for alternative exploration
    - Revision of previous thoughts
    - Hypothesis generation and verification
    - Evidence tracking
    - Confidence scoring

    Thread-safe for concurrent access.
    """

    def __init__(
        self,
        session_id: str,
        max_thoughts: int = DEFAULT_MAX_THOUGHTS,
        max_branches: int = DEFAULT_MAX_BRANCHES,
    ) -> None:
        """Initialize a new reasoning session.

        Args:
            session_id: Unique session identifier
            max_thoughts: Maximum thoughts allowed
            max_branches: Maximum concurrent branches
        """
        self.session_id = session_id
        self.max_thoughts = max_thoughts
        self.max_branches = max_branches

        self._thoughts: list[ThoughtNode] = []
        self._branches: dict[str, list[ThoughtNode]] = {}
        self._hypotheses: dict[str, Hypothesis] = {}
        self._evidence: dict[str, Evidence] = {}
        self._current_branch: str | None = None
        self._total_thoughts_estimate: int = 5
        self._current_mode: ReasoningMode = ReasoningMode.ANALYTICAL
        self._lock = threading.Lock()

        self._created_at = datetime.now(UTC).isoformat()
        self._last_updated = self._created_at
        logger.debug(f"Created reasoning session: {session_id}")

    # -------------------------------------------------------------------------
    # Core Thought Processing
    # -------------------------------------------------------------------------

    def process_thought(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        next_thought_needed: bool,
        *,
        thought_type: ThoughtType | str = ThoughtType.REGULAR,
        reasoning_mode: ReasoningMode | str | None = None,
        confidence: float = 0.7,
        is_revision: bool = False,
        revises_thought: int | None = None,
        branch_from_thought: int | None = None,
        branch_id: str | None = None,
        evidence: list[dict] | None = None,
        hypothesis_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReasoningResult:
        """Process a new thought in the reasoning chain.

        Args:
            thought: The thought content
            thought_number: Current thought number in sequence
            total_thoughts: Estimated total thoughts needed
            next_thought_needed: Whether more thinking is needed
            thought_type: Type of thought (regular, hypothesis, etc.)
            reasoning_mode: Mode of reasoning being applied
            confidence: Confidence level (0.0-1.0)
            is_revision: Whether this revises previous thinking
            revises_thought: Which thought number is being revised
            branch_from_thought: If branching, which thought to branch from
            branch_id: Identifier for the branch
            evidence: List of evidence dicts to attach
            hypothesis_id: ID of hypothesis this thought relates to
            metadata: Additional metadata

        Returns:
            ReasoningResult with processing outcome
        """
        with self._lock:
            # Normalize enums
            if isinstance(thought_type, str):
                thought_type = ThoughtType(thought_type)
            if isinstance(reasoning_mode, str):
                reasoning_mode = ReasoningMode(reasoning_mode)
            elif reasoning_mode is None:
                reasoning_mode = self._current_mode

            # Update estimates
            if thought_number > total_thoughts:
                total_thoughts = thought_number
            self._total_thoughts_estimate = total_thoughts
            self._current_mode = reasoning_mode

            # Create evidence if provided
            evidence_ids = []
            if evidence:
                for ev in evidence:
                    ev_obj = Evidence(
                        source=ev.get("source", ""),
                        content=ev.get("content", ""),
                        reliability=ev.get("reliability", 0.8),
                    )
                    self._evidence[ev_obj.id] = ev_obj
                    evidence_ids.append(ev_obj.id)

            # Handle branching
            if branch_from_thought is not None:
                if branch_id is None:
                    branch_id = f"branch_{len(self._branches) + 1}"
                if branch_id not in self._branches:
                    if len(self._branches) >= self.max_branches:
                        return self._error_result(
                            f"Maximum branches ({self.max_branches}) exceeded"
                        )
                    self._branches[branch_id] = []
                self._current_branch = branch_id
                thought_type = ThoughtType.BRANCH

            # Handle revision
            parent_id = None
            revises_id = None
            if is_revision and revises_thought is not None:
                thought_type = ThoughtType.REVISION
                # Find the thought being revised
                for t in self._thoughts:
                    if t.thought_number == revises_thought:
                        revises_id = t.id
                        parent_id = t.parent_id
                        break

            # Create thought node
            node = ThoughtNode(
                thought_number=thought_number,
                content=thought,
                thought_type=thought_type,
                reasoning_mode=reasoning_mode,
                confidence=max(0.0, min(1.0, confidence)),
                parent_id=parent_id,
                branch_id=branch_id or self._current_branch,
                revises_thought=revises_id,
                evidence_ids=evidence_ids,
                next_thought_needed=next_thought_needed,
                metadata=metadata or {},
            )

            # Add to appropriate collection
            if node.branch_id and node.branch_id in self._branches:
                self._branches[node.branch_id].append(node)
            self._thoughts.append(node)

            # Update hypothesis if specified
            if hypothesis_id and hypothesis_id in self._hypotheses:
                hyp = self._hypotheses[hypothesis_id]
                if thought_type == ThoughtType.VERIFICATION:
                    if confidence > 0.7:
                        hyp.supporting_thought_ids.append(node.id)
                        hyp.confidence = min(1.0, hyp.confidence + 0.1)
                    elif confidence < 0.4:
                        hyp.contradicting_thought_ids.append(node.id)
                        hyp.confidence = max(0.0, hyp.confidence - 0.1)

            # Enforce limits
            if len(self._thoughts) > self.max_thoughts:
                self._thoughts = self._thoughts[-self.max_thoughts:]

            self._last_updated = datetime.now(UTC).isoformat()

            # Generate guidance message
            message = self._generate_guidance(node, next_thought_needed)

            return ReasoningResult(
                thought_id=node.id,
                thought_number=thought_number,
                total_thoughts=self._total_thoughts_estimate,
                next_thought_needed=next_thought_needed,
                branches=list(self._branches.keys()),
                hypotheses=[h.id for h in self._hypotheses.values() if h.status in ("proposed", "testing")],
                thought_history_length=len(self._thoughts),
                average_confidence=self._calculate_average_confidence(),
                current_mode=self._current_mode.value,
                message=message,
            )

    # -------------------------------------------------------------------------
    # Hypothesis Management
    # -------------------------------------------------------------------------

    def propose_hypothesis(self, statement: str, confidence: float = 0.5) -> Hypothesis:
        """Propose a new hypothesis for testing.

        Args:
            statement: The hypothesis statement
            confidence: Initial confidence level

        Returns:
            The created Hypothesis
        """
        with self._lock:
            hyp = Hypothesis(
                statement=statement,
                status="proposed",
                confidence=max(0.0, min(1.0, confidence)),
            )
            self._hypotheses[hyp.id] = hyp
            logger.debug(f"Proposed hypothesis: {hyp.id} - {statement[:50]}...")
            return hyp

    def update_hypothesis(
        self,
        hypothesis_id: str,
        status: str | None = None,
        confidence: float | None = None,
    ) -> Hypothesis | None:
        """Update a hypothesis status or confidence.

        Args:
            hypothesis_id: ID of hypothesis to update
            status: New status (proposed, testing, verified, refuted, revised)
            confidence: New confidence level

        Returns:
            Updated Hypothesis or None if not found
        """
        with self._lock:
            if hypothesis_id not in self._hypotheses:
                return None
            hyp = self._hypotheses[hypothesis_id]
            if status:
                hyp.status = status
                if status in ("verified", "refuted"):
                    hyp.resolved_at = datetime.now(UTC).isoformat()
            if confidence is not None:
                hyp.confidence = max(0.0, min(1.0, confidence))
            return hyp

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        """Get a hypothesis by ID."""
        return self._hypotheses.get(hypothesis_id)

    def list_hypotheses(self, status: str | None = None) -> list[Hypothesis]:
        """List all hypotheses, optionally filtered by status."""
        with self._lock:
            if status:
                return [h for h in self._hypotheses.values() if h.status == status]
            return list(self._hypotheses.values())

    # -------------------------------------------------------------------------
    # Evidence Management
    # -------------------------------------------------------------------------

    def add_evidence(
        self,
        source: str,
        content: str,
        reliability: float = 0.8,
    ) -> Evidence:
        """Add evidence to the reasoning session.

        Args:
            source: Where the evidence came from
            content: The evidence content
            reliability: Reliability score (0.0-1.0)

        Returns:
            The created Evidence
        """
        with self._lock:
            ev = Evidence(
                source=source,
                content=content,
                reliability=max(0.0, min(1.0, reliability)),
            )
            self._evidence[ev.id] = ev
            return ev

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        """Get evidence by ID."""
        return self._evidence.get(evidence_id)

    def list_evidence(self) -> list[Evidence]:
        """List all evidence."""
        return list(self._evidence.values())

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _calculate_average_confidence(self) -> float:
        """Calculate average confidence across all thoughts."""
        if not self._thoughts:
            return 0.0
        return sum(t.confidence for t in self._thoughts) / len(self._thoughts)

    def _generate_guidance(self, node: ThoughtNode, next_needed: bool) -> str:
        """Generate guidance message based on current state."""
        if not next_needed:
            return "Reasoning complete. Consider summarizing conclusions."

        avg_conf = self._calculate_average_confidence()
        messages = []

        if avg_conf < 0.5:
            messages.append("Low confidence - consider gathering more evidence.")
        elif avg_conf > 0.85:
            messages.append("High confidence - proceed toward conclusion.")

        active_hyps = [h for h in self._hypotheses.values() if h.status == "proposed"]
        if active_hyps:
            messages.append(f"{len(active_hyps)} hypothesis(es) awaiting verification.")

        if node.thought_type == ThoughtType.BRANCH:
            messages.append("Exploring alternative branch.")
        elif node.thought_type == ThoughtType.REVISION:
            messages.append("Previous thinking revised.")

        return " ".join(messages) if messages else "Continue reasoning."

    def _error_result(self, message: str) -> ReasoningResult:
        """Create an error result."""
        return ReasoningResult(
            thought_id="error",
            thought_number=len(self._thoughts),
            total_thoughts=self._total_thoughts_estimate,
            next_thought_needed=True,
            branches=list(self._branches.keys()),
            hypotheses=[],
            thought_history_length=len(self._thoughts),
            average_confidence=self._calculate_average_confidence(),
            current_mode=self._current_mode.value,
            message=f"Error: {message}",
        )

    # -------------------------------------------------------------------------
    # State Management
    # -------------------------------------------------------------------------

    def get_thought_history(self, limit: int | None = None) -> list[ThoughtNode]:
        """Get thought history, optionally limited."""
        with self._lock:
            if limit:
                return self._thoughts[-limit:]
            return list(self._thoughts)

    def get_branch_thoughts(self, branch_id: str) -> list[ThoughtNode]:
        """Get thoughts for a specific branch."""
        with self._lock:
            return list(self._branches.get(branch_id, []))

    def switch_branch(self, branch_id: str | None) -> bool:
        """Switch to a different branch (or main line if None)."""
        with self._lock:
            if branch_id is not None and branch_id not in self._branches:
                return False
            self._current_branch = branch_id
            return True

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the reasoning session."""
        with self._lock:
            return {
                "session_id": self.session_id,
                "created_at": self._created_at,
                "last_updated": self._last_updated,
                "total_thoughts": len(self._thoughts),
                "total_branches": len(self._branches),
                "total_hypotheses": len(self._hypotheses),
                "total_evidence": len(self._evidence),
                "average_confidence": self._calculate_average_confidence(),
                "current_mode": self._current_mode.value,
                "current_branch": self._current_branch,
                "active_hypotheses": [
                    h.id for h in self._hypotheses.values()
                    if h.status in ("proposed", "testing")
                ],
                "verified_hypotheses": [
                    h.id for h in self._hypotheses.values()
                    if h.status == "verified"
                ],
            }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire session to a dictionary."""
        with self._lock:
            return {
                "session_id": self.session_id,
                "created_at": self._created_at,
                "last_updated": self._last_updated,
                "thoughts": [t.to_dict() for t in self._thoughts],
                "branches": {
                    bid: [t.to_dict() for t in thoughts]
                    for bid, thoughts in self._branches.items()
                },
                "hypotheses": {
                    hid: h.to_dict() for hid, h in self._hypotheses.items()
                },
                "evidence": {
                    eid: {"id": e.id, "source": e.source, "content": e.content, "reliability": e.reliability}
                    for eid, e in self._evidence.items()
                },
                "current_mode": self._current_mode.value,
                "current_branch": self._current_branch,
            }

    def clear(self) -> None:
        """Clear all session data."""
        with self._lock:
            self._thoughts.clear()
            self._branches.clear()
            self._hypotheses.clear()
            self._evidence.clear()
            self._current_branch = None
            self._total_thoughts_estimate = 5
            self._current_mode = ReasoningMode.ANALYTICAL
            self._last_updated = datetime.now(UTC).isoformat()


# =============================================================================
# SESSION MANAGER
# =============================================================================


class ReasoningSessionManager:
    """Manages multiple reasoning sessions.

    Thread-safe singleton manager for all reasoning sessions.
    """

    def __init__(self, max_sessions: int = 100) -> None:
        """Initialize the session manager.

        Args:
            max_sessions: Maximum concurrent sessions
        """
        self.max_sessions = max_sessions
        self._sessions: dict[str, DeepReasoningSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> DeepReasoningSession:
        """Get existing session or create new one.

        Args:
            session_id: Session identifier

        Returns:
            DeepReasoningSession instance
        """
        with self._lock:
            if session_id not in self._sessions:
                if len(self._sessions) >= self.max_sessions:
                    # Remove oldest session
                    oldest = min(
                        self._sessions.items(),
                        key=lambda x: x[1]._last_updated
                    )
                    del self._sessions[oldest[0]]
                    logger.debug(f"Evicted oldest session: {oldest[0]}")
                self._sessions[session_id] = DeepReasoningSession(session_id)
            return self._sessions[session_id]

    def get(self, session_id: str) -> DeepReasoningSession | None:
        """Get a session by ID, returns None if not found."""
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> bool:
        """Remove a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def list_sessions(self) -> list[str]:
        """List all session IDs."""
        return list(self._sessions.keys())

    def clear_all(self) -> None:
        """Clear all sessions."""
        with self._lock:
            self._sessions.clear()


# Global session manager
_session_manager: ReasoningSessionManager | None = None
_manager_lock = threading.Lock()


def get_session_manager() -> ReasoningSessionManager:
    """Get the global session manager."""
    global _session_manager
    with _manager_lock:
        if _session_manager is None:
            _session_manager = ReasoningSessionManager()
        return _session_manager


def get_reasoning_session(session_id: str) -> DeepReasoningSession:
    """Get or create a reasoning session for the given session ID.

    This is the main entry point for accessing reasoning sessions.

    Args:
        session_id: Session identifier

    Returns:
        DeepReasoningSession instance
    """
    return get_session_manager().get_or_create(session_id)


def reset_session_manager() -> None:
    """Reset the global session manager (for testing)."""
    global _session_manager
    with _manager_lock:
        _session_manager = None


# =============================================================================
# LANGCHAIN TOOL
# =============================================================================


# Thread-local storage for session ID context
_thread_local = threading.local()


def set_current_session_id(session_id: str) -> None:
    """Set the current session ID for the calling thread."""
    _thread_local.session_id = session_id


def get_current_session_id() -> str:
    """Get the current session ID for the calling thread."""
    return getattr(_thread_local, "session_id", "default")


@tool
def deep_reasoning(
    thought: str,
    thought_number: int,
    total_thoughts: int,
    next_thought_needed: bool,
    thought_type: str = "regular",
    reasoning_mode: str = "analytical",
    confidence: float = 0.7,
    is_revision: bool = False,
    revises_thought: int | None = None,
    branch_from_thought: int | None = None,
    branch_id: str | None = None,
    hypothesis_statement: str | None = None,
    hypothesis_id: str | None = None,
) -> str:
    """A powerful tool for structured, multi-step reasoning and problem solving.

    Use this tool when you need to think through complex problems systematically.
    It helps you track your reasoning, explore alternatives, and verify conclusions.

    WHEN TO USE:
    - Breaking down complex problems into manageable steps
    - Exploring multiple solution approaches (branching)
    - Revising earlier thinking when new information emerges
    - Generating and testing hypotheses
    - Making decisions with explicit confidence levels
    - Any multi-step analysis that benefits from structured thinking

    HOW TO USE:
    1. Start with thought_number=1 and estimate total_thoughts needed
    2. Set next_thought_needed=True while still thinking
    3. Adjust total_thoughts up/down as the problem becomes clearer
    4. Use is_revision=True to reconsider previous thoughts
    5. Use branch_from_thought to explore alternatives
    6. Use hypothesis_statement to propose testable hypotheses
    7. Set next_thought_needed=False only when reasoning is complete

    THOUGHT TYPES:
    - regular: Normal analytical step
    - hypothesis: Proposing a hypothesis
    - verification: Testing a hypothesis
    - revision: Revising previous thinking
    - branch: Exploring an alternative
    - conclusion: Final conclusion
    - question: Raising a question
    - evidence: Presenting evidence

    REASONING MODES:
    - analytical: Breaking down into components
    - creative: Generating novel ideas
    - critical: Evaluating and questioning
    - exploratory: Exploring possibilities
    - deductive: From general to specific
    - inductive: From specific to general
    - abductive: Best explanation inference

    Args:
        thought: Your current thinking step - be detailed and explicit
        thought_number: Current thought number (start at 1)
        total_thoughts: Estimated total thoughts needed (adjust as you go)
        next_thought_needed: True if more thinking needed, False when done
        thought_type: Type of thought (regular, hypothesis, verification, etc.)
        reasoning_mode: Mode of reasoning (analytical, creative, critical, etc.)
        confidence: Your confidence in this thought (0.0-1.0)
        is_revision: True if revising previous thinking
        revises_thought: If revising, which thought number to revise
        branch_from_thought: If branching, which thought number to branch from
        branch_id: Optional identifier for this branch
        hypothesis_statement: If proposing a hypothesis, the statement to test
        hypothesis_id: If verifying a hypothesis, its ID

    Returns:
        JSON with reasoning state: thought_id, progress, branches, hypotheses, guidance
    """
    try:
        session_id = get_current_session_id()
        session = get_reasoning_session(session_id)

        # Handle hypothesis proposal
        hyp_id = hypothesis_id
        if hypothesis_statement and not hypothesis_id:
            hyp = session.propose_hypothesis(hypothesis_statement, confidence)
            hyp_id = hyp.id

        # Process the thought
        result = session.process_thought(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            next_thought_needed=next_thought_needed,
            thought_type=thought_type,
            reasoning_mode=reasoning_mode,
            confidence=confidence,
            is_revision=is_revision,
            revises_thought=revises_thought,
            branch_from_thought=branch_from_thought,
            branch_id=branch_id,
            hypothesis_id=hyp_id,
        )

        # Format response
        response = {
            "status": "success",
            "thought_id": result.thought_id,
            "thought_number": result.thought_number,
            "total_thoughts": result.total_thoughts,
            "next_thought_needed": result.next_thought_needed,
            "branches": result.branches,
            "hypotheses": result.hypotheses,
            "history_length": result.thought_history_length,
            "average_confidence": round(result.average_confidence, 2),
            "current_mode": result.current_mode,
            "guidance": result.message,
        }

        if hyp_id:
            response["hypothesis_id"] = hyp_id

        import json
        return json.dumps(response, indent=2)

    except Exception as e:
        logger.exception(f"Error in deep_reasoning: {e}")
        import json
        return json.dumps({
            "status": "error",
            "error": str(e),
            "thought_number": thought_number,
            "next_thought_needed": True,
        })


def get_deep_reasoning_tool():
    """Get the deep_reasoning tool for adding to agent tools list."""
    return deep_reasoning

