"""Unit tests for the Deep Reasoning tool.

Tests cover:
- ThoughtNode dataclass
- Evidence and Hypothesis dataclasses
- DeepReasoningSession class
- ReasoningSessionManager
- deep_reasoning tool function
- Thread-local session context
"""

import json
import threading
import pytest

from ag3nt_agent.deep_reasoning import (
    # Enums
    ReasoningMode,
    ThoughtType,
    # Data classes
    Evidence,
    ThoughtNode,
    Hypothesis,
    ReasoningResult,
    # Session management
    DeepReasoningSession,
    ReasoningSessionManager,
    get_reasoning_session,
    get_session_manager,
    reset_session_manager,
    # Tool
    deep_reasoning,
    get_deep_reasoning_tool,
    set_current_session_id,
    get_current_session_id,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset session manager before and after each test."""
    reset_session_manager()
    yield
    reset_session_manager()


# =============================================================================
# TEST ENUMS
# =============================================================================


class TestReasoningMode:
    """Tests for ReasoningMode enum."""

    def test_all_modes_exist(self):
        """All expected reasoning modes exist."""
        assert ReasoningMode.ANALYTICAL == "analytical"
        assert ReasoningMode.CREATIVE == "creative"
        assert ReasoningMode.CRITICAL == "critical"
        assert ReasoningMode.EXPLORATORY == "exploratory"
        assert ReasoningMode.DEDUCTIVE == "deductive"
        assert ReasoningMode.INDUCTIVE == "inductive"
        assert ReasoningMode.ABDUCTIVE == "abductive"

    def test_mode_from_string(self):
        """Modes can be created from strings."""
        mode = ReasoningMode("analytical")
        assert mode == ReasoningMode.ANALYTICAL


class TestThoughtType:
    """Tests for ThoughtType enum."""

    def test_all_types_exist(self):
        """All expected thought types exist."""
        assert ThoughtType.REGULAR == "regular"
        assert ThoughtType.HYPOTHESIS == "hypothesis"
        assert ThoughtType.VERIFICATION == "verification"
        assert ThoughtType.REVISION == "revision"
        assert ThoughtType.BRANCH == "branch"
        assert ThoughtType.CONCLUSION == "conclusion"
        assert ThoughtType.QUESTION == "question"
        assert ThoughtType.EVIDENCE == "evidence"


# =============================================================================
# TEST DATA CLASSES
# =============================================================================


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_evidence_creation(self):
        """Evidence is created with defaults."""
        ev = Evidence(source="web_search", content="Found relevant data")
        assert ev.source == "web_search"
        assert ev.content == "Found relevant data"
        assert ev.reliability == 0.8
        assert ev.id  # Auto-generated
        assert ev.timestamp  # Auto-generated

    def test_evidence_custom_reliability(self):
        """Evidence can have custom reliability."""
        ev = Evidence(source="expert", content="Data", reliability=0.95)
        assert ev.reliability == 0.95


class TestThoughtNode:
    """Tests for ThoughtNode dataclass."""

    def test_thought_node_creation(self):
        """ThoughtNode is created with defaults."""
        node = ThoughtNode(thought_number=1, content="First thought")
        assert node.thought_number == 1
        assert node.content == "First thought"
        assert node.thought_type == ThoughtType.REGULAR
        assert node.reasoning_mode == ReasoningMode.ANALYTICAL
        assert node.confidence == 0.7
        assert node.next_thought_needed is True
        assert node.id  # Auto-generated

    def test_thought_node_to_dict(self):
        """ThoughtNode serializes to dict."""
        node = ThoughtNode(thought_number=1, content="Test")
        d = node.to_dict()
        assert d["thought_number"] == 1
        assert d["content"] == "Test"
        assert d["thought_type"] == "regular"
        assert d["reasoning_mode"] == "analytical"

    def test_thought_node_branch(self):
        """ThoughtNode can be on a branch."""
        node = ThoughtNode(
            thought_number=3,
            content="Alternative approach",
            branch_id="branch_1",
            thought_type=ThoughtType.BRANCH,
        )
        assert node.branch_id == "branch_1"
        assert node.thought_type == ThoughtType.BRANCH


class TestHypothesis:
    """Tests for Hypothesis dataclass."""

    def test_hypothesis_creation(self):
        """Hypothesis is created with defaults."""
        hyp = Hypothesis(statement="The error is in the database")
        assert hyp.statement == "The error is in the database"
        assert hyp.status == "proposed"
        assert hyp.confidence == 0.5
        assert hyp.id  # Auto-generated

    def test_hypothesis_to_dict(self):
        """Hypothesis serializes to dict."""
        hyp = Hypothesis(statement="Test hypothesis")
        d = hyp.to_dict()
        assert d["statement"] == "Test hypothesis"
        assert d["status"] == "proposed"
        assert "supporting_thought_ids" in d


class TestReasoningResult:
    """Tests for ReasoningResult dataclass."""

    def test_result_creation(self):
        """ReasoningResult is created correctly."""
        result = ReasoningResult(
            thought_id="abc123",
            thought_number=2,
            total_thoughts=5,
            next_thought_needed=True,
            branches=["branch_1"],
            hypotheses=["hyp_1"],
            thought_history_length=2,
            average_confidence=0.75,
            current_mode="analytical",
            message="Continue reasoning.",
        )
        assert result.thought_id == "abc123"
        assert result.thought_number == 2
        assert result.branches == ["branch_1"]

    def test_result_to_dict(self):
        """ReasoningResult serializes to dict."""
        result = ReasoningResult(
            thought_id="test",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
            branches=[],
            hypotheses=[],
            thought_history_length=1,
            average_confidence=0.7,
            current_mode="analytical",
        )
        d = result.to_dict()
        assert d["thought_id"] == "test"
        assert d["next_thought_needed"] is True


# =============================================================================
# TEST DEEP REASONING SESSION
# =============================================================================


class TestDeepReasoningSession:
    """Tests for DeepReasoningSession class."""

    def test_session_creation(self):
        """Session is created with proper defaults."""
        session = DeepReasoningSession("test_session")
        assert session.session_id == "test_session"
        assert session.max_thoughts == 50
        assert session.max_branches == 10

    def test_process_simple_thought(self):
        """Process a simple thought."""
        session = DeepReasoningSession("test")
        result = session.process_thought(
            thought="This is my first thought",
            thought_number=1,
            total_thoughts=5,
            next_thought_needed=True,
        )
        assert result.thought_number == 1
        assert result.total_thoughts == 5
        assert result.next_thought_needed is True
        assert result.thought_history_length == 1

    def test_process_multiple_thoughts(self):
        """Process multiple thoughts in sequence."""
        session = DeepReasoningSession("test")
        for i in range(1, 4):
            result = session.process_thought(
                thought=f"Thought number {i}",
                thought_number=i,
                total_thoughts=5,
                next_thought_needed=i < 3,
            )
        assert result.thought_number == 3
        assert result.thought_history_length == 3
        assert result.next_thought_needed is False

    def test_adjust_total_thoughts(self):
        """Total thoughts adjusts when exceeded."""
        session = DeepReasoningSession("test")
        result = session.process_thought(
            thought="Thought 8",
            thought_number=8,
            total_thoughts=5,
            next_thought_needed=True,
        )
        # Should auto-adjust total to match thought_number
        assert result.total_thoughts == 8

    def test_confidence_scoring(self):
        """Confidence is tracked correctly."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="High confidence thought",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
            confidence=0.9,
        )
        session.process_thought(
            thought="Low confidence thought",
            thought_number=2,
            total_thoughts=3,
            next_thought_needed=True,
            confidence=0.5,
        )
        result = session.process_thought(
            thought="Medium confidence",
            thought_number=3,
            total_thoughts=3,
            next_thought_needed=False,
            confidence=0.7,
        )
        # Average should be (0.9 + 0.5 + 0.7) / 3 = 0.7
        assert abs(result.average_confidence - 0.7) < 0.01

    def test_confidence_clamping(self):
        """Confidence is clamped to 0.0-1.0 range."""
        session = DeepReasoningSession("test")
        result = session.process_thought(
            thought="Test",
            thought_number=1,
            total_thoughts=1,
            next_thought_needed=False,
            confidence=1.5,  # Above 1.0
        )
        thoughts = session.get_thought_history()
        assert thoughts[0].confidence == 1.0

    def test_reasoning_mode_persistence(self):
        """Reasoning mode persists across thoughts."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Creative exploration",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
            reasoning_mode="creative",
        )
        result = session.process_thought(
            thought="Continue creatively",
            thought_number=2,
            total_thoughts=3,
            next_thought_needed=False,
        )
        assert result.current_mode == "creative"


class TestDeepReasoningBranching:
    """Tests for branching functionality."""

    def test_create_branch(self):
        """Can create a branch from a thought."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Main line thought 1",
            thought_number=1,
            total_thoughts=5,
            next_thought_needed=True,
        )
        session.process_thought(
            thought="Main line thought 2",
            thought_number=2,
            total_thoughts=5,
            next_thought_needed=True,
        )
        result = session.process_thought(
            thought="Exploring alternative",
            thought_number=3,
            total_thoughts=5,
            next_thought_needed=True,
            branch_from_thought=2,
            branch_id="alt_approach",
        )
        assert "alt_approach" in result.branches

    def test_auto_branch_id(self):
        """Branch ID is auto-generated if not provided."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Initial",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
        )
        result = session.process_thought(
            thought="Branch",
            thought_number=2,
            total_thoughts=3,
            next_thought_needed=True,
            branch_from_thought=1,
        )
        assert len(result.branches) == 1
        assert result.branches[0].startswith("branch_")

    def test_get_branch_thoughts(self):
        """Can retrieve thoughts for a specific branch."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Main thought",
            thought_number=1,
            total_thoughts=5,
            next_thought_needed=True,
        )
        session.process_thought(
            thought="Branch thought 1",
            thought_number=2,
            total_thoughts=5,
            next_thought_needed=True,
            branch_from_thought=1,
            branch_id="test_branch",
        )
        session.process_thought(
            thought="Branch thought 2",
            thought_number=3,
            total_thoughts=5,
            next_thought_needed=True,
            branch_id="test_branch",
        )
        branch_thoughts = session.get_branch_thoughts("test_branch")
        assert len(branch_thoughts) == 2

    def test_max_branches_limit(self):
        """Cannot exceed max branches."""
        session = DeepReasoningSession("test", max_branches=2)
        session.process_thought(
            thought="Main",
            thought_number=1,
            total_thoughts=10,
            next_thought_needed=True,
        )
        # Create first branch
        session.process_thought(
            thought="Branch 1",
            thought_number=2,
            total_thoughts=10,
            next_thought_needed=True,
            branch_from_thought=1,
            branch_id="b1",
        )
        # Create second branch
        session.process_thought(
            thought="Branch 2",
            thought_number=3,
            total_thoughts=10,
            next_thought_needed=True,
            branch_from_thought=1,
            branch_id="b2",
        )
        # Try to create third branch
        result = session.process_thought(
            thought="Branch 3",
            thought_number=4,
            total_thoughts=10,
            next_thought_needed=True,
            branch_from_thought=1,
            branch_id="b3",
        )
        assert "Error" in result.message


class TestDeepReasoningRevision:
    """Tests for revision functionality."""

    def test_revise_thought(self):
        """Can revise a previous thought."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Initial thought",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
        )
        result = session.process_thought(
            thought="Actually, I was wrong about thought 1",
            thought_number=2,
            total_thoughts=3,
            next_thought_needed=True,
            is_revision=True,
            revises_thought=1,
        )
        thoughts = session.get_thought_history()
        assert thoughts[1].thought_type == ThoughtType.REVISION


class TestDeepReasoningHypotheses:
    """Tests for hypothesis management."""

    def test_propose_hypothesis(self):
        """Can propose a hypothesis."""
        session = DeepReasoningSession("test")
        hyp = session.propose_hypothesis("The bug is in the API layer", 0.6)
        assert hyp.statement == "The bug is in the API layer"
        assert hyp.status == "proposed"
        assert hyp.confidence == 0.6

    def test_update_hypothesis(self):
        """Can update hypothesis status."""
        session = DeepReasoningSession("test")
        hyp = session.propose_hypothesis("Test hypothesis")
        session.update_hypothesis(hyp.id, status="testing")
        updated = session.get_hypothesis(hyp.id)
        assert updated.status == "testing"

    def test_verify_hypothesis(self):
        """Hypothesis can be verified."""
        session = DeepReasoningSession("test")
        hyp = session.propose_hypothesis("Test", 0.5)
        session.update_hypothesis(hyp.id, status="verified", confidence=0.95)
        updated = session.get_hypothesis(hyp.id)
        assert updated.status == "verified"
        assert updated.confidence == 0.95
        assert updated.resolved_at is not None

    def test_list_hypotheses(self):
        """Can list hypotheses by status."""
        session = DeepReasoningSession("test")
        session.propose_hypothesis("H1")
        session.propose_hypothesis("H2")
        h3 = session.propose_hypothesis("H3")
        session.update_hypothesis(h3.id, status="verified")

        all_hyps = session.list_hypotheses()
        assert len(all_hyps) == 3

        proposed = session.list_hypotheses(status="proposed")
        assert len(proposed) == 2

        verified = session.list_hypotheses(status="verified")
        assert len(verified) == 1


class TestDeepReasoningEvidence:
    """Tests for evidence management."""

    def test_add_evidence(self):
        """Can add evidence to session."""
        session = DeepReasoningSession("test")
        ev = session.add_evidence(
            source="web_search",
            content="Found documentation confirming the issue",
            reliability=0.9,
        )
        assert ev.source == "web_search"
        assert ev.reliability == 0.9

    def test_get_evidence(self):
        """Can retrieve evidence by ID."""
        session = DeepReasoningSession("test")
        ev = session.add_evidence("test", "content")
        retrieved = session.get_evidence(ev.id)
        assert retrieved.content == "content"

    def test_list_evidence(self):
        """Can list all evidence."""
        session = DeepReasoningSession("test")
        session.add_evidence("s1", "c1")
        session.add_evidence("s2", "c2")
        all_evidence = session.list_evidence()
        assert len(all_evidence) == 2


class TestDeepReasoningState:
    """Tests for session state management."""

    def test_get_thought_history(self):
        """Can get thought history."""
        session = DeepReasoningSession("test")
        for i in range(5):
            session.process_thought(
                thought=f"Thought {i}",
                thought_number=i + 1,
                total_thoughts=5,
                next_thought_needed=i < 4,
            )
        history = session.get_thought_history()
        assert len(history) == 5

    def test_get_thought_history_limited(self):
        """Can limit thought history."""
        session = DeepReasoningSession("test")
        for i in range(5):
            session.process_thought(
                thought=f"Thought {i}",
                thought_number=i + 1,
                total_thoughts=5,
                next_thought_needed=i < 4,
            )
        history = session.get_thought_history(limit=3)
        assert len(history) == 3

    def test_get_summary(self):
        """Can get session summary."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Test",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
        )
        summary = session.get_summary()
        assert summary["session_id"] == "test"
        assert summary["total_thoughts"] == 1

    def test_session_to_dict(self):
        """Session serializes to dict."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Test",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
        )
        d = session.to_dict()
        assert "thoughts" in d
        assert len(d["thoughts"]) == 1

    def test_clear_session(self):
        """Can clear session data."""
        session = DeepReasoningSession("test")
        session.process_thought(
            thought="Test",
            thought_number=1,
            total_thoughts=3,
            next_thought_needed=True,
        )
        session.clear()
        history = session.get_thought_history()
        assert len(history) == 0


# =============================================================================
# TEST SESSION MANAGER
# =============================================================================


class TestReasoningSessionManager:
    """Tests for ReasoningSessionManager."""

    def test_get_or_create(self):
        """Can get or create sessions."""
        manager = ReasoningSessionManager()
        session1 = manager.get_or_create("s1")
        session2 = manager.get_or_create("s2")
        session1_again = manager.get_or_create("s1")
        assert session1 is session1_again
        assert session1 is not session2

    def test_list_sessions(self):
        """Can list all session IDs."""
        manager = ReasoningSessionManager()
        manager.get_or_create("s1")
        manager.get_or_create("s2")
        sessions = manager.list_sessions()
        assert "s1" in sessions
        assert "s2" in sessions

    def test_remove_session(self):
        """Can remove a session."""
        manager = ReasoningSessionManager()
        manager.get_or_create("s1")
        assert manager.remove("s1") is True
        assert manager.get("s1") is None
        assert manager.remove("nonexistent") is False

    def test_max_sessions_eviction(self):
        """Oldest session is evicted when max reached."""
        manager = ReasoningSessionManager(max_sessions=2)
        manager.get_or_create("s1")
        manager.get_or_create("s2")
        manager.get_or_create("s3")  # Should evict s1
        assert manager.get("s1") is None
        assert manager.get("s2") is not None
        assert manager.get("s3") is not None


class TestGlobalSessionFunctions:
    """Tests for global session functions."""

    def test_get_session_manager(self):
        """get_session_manager returns singleton."""
        m1 = get_session_manager()
        m2 = get_session_manager()
        assert m1 is m2

    def test_get_reasoning_session(self):
        """get_reasoning_session creates session."""
        session = get_reasoning_session("test_session")
        assert session.session_id == "test_session"


# =============================================================================
# TEST THREAD-LOCAL CONTEXT
# =============================================================================


class TestSessionContext:
    """Tests for thread-local session context."""

    def test_set_and_get_session_id(self):
        """Can set and get session ID."""
        set_current_session_id("my_session")
        assert get_current_session_id() == "my_session"

    def test_default_session_id(self):
        """Default session ID is 'default'."""
        # In a fresh thread without setting
        result = []

        def check_default():
            result.append(get_current_session_id())

        thread = threading.Thread(target=check_default)
        thread.start()
        thread.join()
        assert result[0] == "default"


# =============================================================================
# TEST TOOL FUNCTION
# =============================================================================


class TestDeepReasoningTool:
    """Tests for the deep_reasoning tool function."""

    def test_basic_thought(self):
        """Tool processes a basic thought."""
        set_current_session_id("tool_test")
        result = deep_reasoning.invoke({
            "thought": "Let me think about this step by step",
            "thought_number": 1,
            "total_thoughts": 5,
            "next_thought_needed": True,
        })
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["thought_number"] == 1
        assert data["next_thought_needed"] is True

    def test_tool_with_confidence(self):
        """Tool respects confidence parameter."""
        set_current_session_id("tool_test_conf")
        result = deep_reasoning.invoke({
            "thought": "I'm quite sure about this",
            "thought_number": 1,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "confidence": 0.95,
        })
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["average_confidence"] == 0.95

    def test_tool_with_reasoning_mode(self):
        """Tool respects reasoning mode."""
        set_current_session_id("tool_test_mode")
        result = deep_reasoning.invoke({
            "thought": "Exploring possibilities",
            "thought_number": 1,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "reasoning_mode": "exploratory",
        })
        data = json.loads(result)
        assert data["current_mode"] == "exploratory"

    def test_tool_with_hypothesis(self):
        """Tool can propose hypothesis."""
        set_current_session_id("tool_test_hyp")
        result = deep_reasoning.invoke({
            "thought": "I think the issue is X",
            "thought_number": 1,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "hypothesis_statement": "The bug is caused by race condition",
        })
        data = json.loads(result)
        assert data["status"] == "success"
        assert "hypothesis_id" in data
        assert len(data["hypotheses"]) == 1

    def test_tool_with_branching(self):
        """Tool supports branching."""
        set_current_session_id("tool_test_branch")
        # First thought
        deep_reasoning.invoke({
            "thought": "Main thought",
            "thought_number": 1,
            "total_thoughts": 5,
            "next_thought_needed": True,
        })
        # Branch
        result = deep_reasoning.invoke({
            "thought": "Alternative approach",
            "thought_number": 2,
            "total_thoughts": 5,
            "next_thought_needed": True,
            "branch_from_thought": 1,
            "branch_id": "alternative",
        })
        data = json.loads(result)
        assert "alternative" in data["branches"]

    def test_tool_with_revision(self):
        """Tool supports revision."""
        set_current_session_id("tool_test_rev")
        deep_reasoning.invoke({
            "thought": "Initial thought",
            "thought_number": 1,
            "total_thoughts": 3,
            "next_thought_needed": True,
        })
        result = deep_reasoning.invoke({
            "thought": "Actually, I was wrong",
            "thought_number": 2,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "is_revision": True,
            "revises_thought": 1,
        })
        data = json.loads(result)
        assert data["status"] == "success"

    def test_get_deep_reasoning_tool(self):
        """get_deep_reasoning_tool returns the tool."""
        tool = get_deep_reasoning_tool()
        assert tool is deep_reasoning
        assert tool.name == "deep_reasoning"


class TestDeepReasoningToolGuidance:
    """Tests for the guidance message generation."""

    def test_completion_guidance(self):
        """Guidance for completed reasoning."""
        set_current_session_id("guidance_complete")
        result = deep_reasoning.invoke({
            "thought": "Final conclusion",
            "thought_number": 3,
            "total_thoughts": 3,
            "next_thought_needed": False,
        })
        data = json.loads(result)
        assert "complete" in data["guidance"].lower() or data["guidance"] == ""

    def test_low_confidence_guidance(self):
        """Guidance for low confidence."""
        set_current_session_id("guidance_low")
        for i in range(3):
            result = deep_reasoning.invoke({
                "thought": f"Uncertain thought {i}",
                "thought_number": i + 1,
                "total_thoughts": 5,
                "next_thought_needed": True,
                "confidence": 0.3,
            })
        data = json.loads(result)
        # Low confidence should trigger guidance
        assert data["average_confidence"] < 0.5

