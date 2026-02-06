"""Unit tests for plan_learning module."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ag3nt_agent.plan_learning import PlanLearningRecorder


def _make_mock_blueprint(
    bp_id="bp_test",
    session_id="s1",
    goal="Test goal",
    status="completed",
    tasks=None,
    learnings=None,
    why="Test why",
):
    """Create a mock ContextBlueprint."""
    bp = MagicMock()
    bp.id = bp_id
    bp.session_id = session_id
    bp.goal = goal
    bp.why = why
    bp.status = status
    bp.learnings = learnings or []

    if tasks is None:
        task1 = MagicMock()
        task1.title = "Task 1"
        task1.status = "completed"
        task1.complexity = "medium"
        task1.files_involved = ["file1.py"]
        task1.validation_result = "passed"
        task1.notes = ""

        task2 = MagicMock()
        task2.title = "Task 2"
        task2.status = "completed"
        task2.complexity = "high"
        task2.files_involved = ["file2.py"]
        task2.validation_result = "passed"
        task2.notes = "Done well"

        tasks = [task1, task2]

    bp.tasks = tasks
    return bp


# ------------------------------------------------------------------
# PlanLearningRecorder
# ------------------------------------------------------------------


@pytest.mark.unit
class TestPlanLearningRecorder:
    @pytest.fixture
    def mock_ce(self):
        ce = AsyncMock()
        ce.store_memory = AsyncMock(return_value={"id": "mem_123"})
        return ce

    @pytest.fixture
    def recorder(self, mock_ce):
        return PlanLearningRecorder(context_engine=mock_ce)

    @pytest.mark.asyncio
    async def test_record_blueprint_outcome_success(self, recorder, mock_ce):
        bp = _make_mock_blueprint()
        await recorder.record_blueprint_outcome(
            blueprint=bp, success=True, duration_ms=5000,
        )
        # Should store 1 blueprint summary + 2 task outcomes = 3 calls
        assert mock_ce.store_memory.call_count == 3

    @pytest.mark.asyncio
    async def test_record_blueprint_outcome_failure(self, recorder, mock_ce):
        bp = _make_mock_blueprint(status="failed")
        await recorder.record_blueprint_outcome(
            blueprint=bp, success=False, duration_ms=2000,
            error_message="Tests failed",
        )
        # First call: blueprint summary
        first_call = mock_ce.store_memory.call_args_list[0]
        metadata = first_call.kwargs.get("metadata", first_call[1].get("metadata", {}))
        assert metadata["success"] is False
        assert metadata["error_message"] == "Tests failed"
        assert "Failed: Tests failed" in metadata["learnings"]

    @pytest.mark.asyncio
    async def test_record_blueprint_stores_summary(self, recorder, mock_ce):
        bp = _make_mock_blueprint(goal="Add auth feature", learnings=["Use JWT"])
        await recorder.record_blueprint_outcome(bp, success=True, duration_ms=10000)

        first_call = mock_ce.store_memory.call_args_list[0]
        assert "Blueprint: Add auth feature" in first_call.kwargs.get(
            "information", first_call[1].get("information", "")
        )
        metadata = first_call.kwargs.get("metadata", first_call[1].get("metadata", {}))
        assert metadata["goal"] == "Add auth feature"
        assert metadata["task_count"] == 2
        assert "Use JWT" in metadata["learnings"]

    @pytest.mark.asyncio
    async def test_record_blueprint_stores_task_outcomes(self, recorder, mock_ce):
        bp = _make_mock_blueprint()
        await recorder.record_blueprint_outcome(bp, success=True, duration_ms=5000)

        # Calls 2 and 3 are task outcomes
        task_calls = mock_ce.store_memory.call_args_list[1:]
        assert len(task_calls) == 2

        first_task_meta = task_calls[0].kwargs.get(
            "metadata", task_calls[0][1].get("metadata", {})
        )
        assert first_task_meta["task_title"] == "Task 1"
        assert first_task_meta["success"] is True

    @pytest.mark.asyncio
    async def test_record_blueprint_store_failure_graceful(self, recorder, mock_ce):
        """Storage failure should not raise."""
        mock_ce.store_memory = AsyncMock(side_effect=Exception("Connection failed"))
        bp = _make_mock_blueprint()
        # Should not raise
        await recorder.record_blueprint_outcome(bp, success=True)

    @pytest.mark.asyncio
    async def test_record_validation_failure(self, recorder, mock_ce):
        await recorder.record_validation_failure(
            blueprint_id="bp_test",
            task_title="Add middleware",
            validation_level=1,
            error_details="Syntax error on line 42",
        )
        assert mock_ce.store_memory.call_count == 1
        call = mock_ce.store_memory.call_args
        info = call.kwargs.get("information", call[1].get("information", ""))
        assert "syntax" in info
        assert "Add middleware" in info
        metadata = call.kwargs.get("metadata", call[1].get("metadata", {}))
        assert metadata["success"] is False
        assert metadata["type"] == "validation_failure"

    @pytest.mark.asyncio
    async def test_record_validation_failure_graceful(self, recorder, mock_ce):
        """Validation failure recording should not raise on error."""
        mock_ce.store_memory = AsyncMock(side_effect=Exception("Storage error"))
        # Should not raise
        await recorder.record_validation_failure(
            blueprint_id="bp_test",
            task_title="Test task",
            validation_level=2,
            error_details="Test failed",
        )

    @pytest.mark.asyncio
    async def test_record_validation_levels(self, recorder, mock_ce):
        """Test that level names map correctly."""
        for level, expected in [(1, "syntax"), (2, "unit_test"), (3, "integration")]:
            await recorder.record_validation_failure(
                blueprint_id="bp_test",
                task_title=f"Task level {level}",
                validation_level=level,
                error_details="Error",
            )
            call = mock_ce.store_memory.call_args
            info = call.kwargs.get("information", call[1].get("information", ""))
            assert expected in info

    @pytest.mark.asyncio
    async def test_error_details_truncation(self, recorder, mock_ce):
        long_error = "x" * 5000
        await recorder.record_validation_failure(
            blueprint_id="bp_test",
            task_title="Task",
            validation_level=1,
            error_details=long_error,
        )
        call = mock_ce.store_memory.call_args
        metadata = call.kwargs.get("metadata", call[1].get("metadata", {}))
        # error_message should be truncated to 1000
        assert len(metadata["error_message"]) <= 1000


# ------------------------------------------------------------------
# Singleton context engine fallback
# ------------------------------------------------------------------


@pytest.mark.unit
class TestRecorderContextEngineProperty:
    def test_lazy_init(self):
        """Test that context_engine is lazily initialized."""
        recorder = PlanLearningRecorder(context_engine=None)
        with patch(
            "ag3nt_agent.plan_learning.get_context_engine",
            return_value=MagicMock(),
            create=True,
        ):
            # The import is inside the property, so we need to patch differently
            with patch(
                "ag3nt_agent.context_engine_client.get_context_engine",
                return_value=MagicMock(),
            ):
                ce = recorder.context_engine
                assert ce is not None
