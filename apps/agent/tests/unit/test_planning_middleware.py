"""Unit tests for PlanningMiddleware."""

from __future__ import annotations

import pytest

from ag3nt_agent.planning_middleware import PlanningMiddleware, PlanningState


# ------------------------------------------------------------------
# PlanningState dataclass
# ------------------------------------------------------------------


@pytest.mark.unit
class TestPlanningState:
    def test_defaults(self):
        s = PlanningState()
        assert s.enabled is False
        assert s.planning_phase is True
        assert s.plan_confirmed is False
        assert s.plan_tasks == []
        assert s.current_task_index == 0

    def test_custom_values(self):
        s = PlanningState(enabled=True, planning_phase=False, plan_confirmed=True,
                          plan_tasks=["a", "b"], current_task_index=1)
        assert s.enabled is True
        assert s.plan_tasks == ["a", "b"]
        assert s.current_task_index == 1


# ------------------------------------------------------------------
# PlanningMiddleware lifecycle
# ------------------------------------------------------------------


@pytest.mark.unit
class TestPlanningMiddleware:
    def test_init(self):
        mw = PlanningMiddleware()
        assert mw.sessions == {}
        assert mw.tools == []

    def test_confirm_plan(self):
        mw = PlanningMiddleware()
        mw.sessions["t1"] = PlanningState(enabled=True)
        mw.confirm_plan("t1", ["Task A", "Task B"])
        state = mw.sessions["t1"]
        assert state.plan_confirmed is True
        assert state.planning_phase is False
        assert state.plan_tasks == ["Task A", "Task B"]

    def test_confirm_plan_unknown_session(self):
        mw = PlanningMiddleware()
        mw.confirm_plan("unknown", ["x"])  # should not raise

    def test_advance_task(self):
        mw = PlanningMiddleware()
        mw.sessions["t1"] = PlanningState(enabled=True, plan_tasks=["a", "b", "c"])
        mw.advance_task("t1")
        assert mw.sessions["t1"].current_task_index == 1
        mw.advance_task("t1")
        assert mw.sessions["t1"].current_task_index == 2

    def test_advance_task_unknown_session(self):
        mw = PlanningMiddleware()
        mw.advance_task("nope")  # should not raise

    def test_disable_plan_mode(self):
        mw = PlanningMiddleware()
        mw.sessions["t1"] = PlanningState(enabled=True)
        mw.disable_plan_mode("t1")
        assert mw.sessions["t1"].enabled is False

    def test_disable_plan_mode_unknown_session(self):
        mw = PlanningMiddleware()
        mw.disable_plan_mode("nope")  # should not raise

    def test_get_state_exists(self):
        mw = PlanningMiddleware()
        mw.sessions["t1"] = PlanningState(enabled=True)
        assert mw.get_state("t1") is not None
        assert mw.get_state("t1").enabled is True

    def test_get_state_missing(self):
        mw = PlanningMiddleware()
        assert mw.get_state("nope") is None


# ------------------------------------------------------------------
# Prompt generation
# ------------------------------------------------------------------


@pytest.mark.unit
class TestPromptGeneration:
    def test_planning_prompt_contains_instructions(self):
        mw = PlanningMiddleware()
        prompt = mw._get_planning_prompt()
        assert "PLANNING MODE" in prompt
        assert "write_todos" in prompt

    def test_execution_prompt_contains_progress(self):
        mw = PlanningMiddleware()
        state = PlanningState(enabled=True, plan_confirmed=True,
                              plan_tasks=["T1", "T2", "T3"], current_task_index=1)
        prompt = mw._get_execution_prompt(state)
        assert "2/3" in prompt
        assert "EXECUTION MODE" in prompt
        assert "Tasks completed: 1" in prompt
        assert "Tasks remaining: 2" in prompt


# ------------------------------------------------------------------
# before_model
# ------------------------------------------------------------------


@pytest.mark.unit
class TestBeforeModel:
    def _make_runtime(self, thread_id="default", plan_mode=False):
        """Create a mock runtime with config."""

        class MockRuntime:
            config = {
                "configurable": {"thread_id": thread_id},
                "metadata": {"plan_mode": plan_mode},
            }

        return MockRuntime()

    def _make_state(self, system_message=""):
        class MockState:
            pass

        s = MockState()
        s.system_message = system_message
        return s

    def test_no_planning_mode_returns_none(self):
        mw = PlanningMiddleware()
        runtime = self._make_runtime(plan_mode=False)
        result = mw.before_model(self._make_state(), runtime)
        assert result is None

    def test_planning_mode_before_model_returns_none(self):
        """before_model returns None; prompt injection is in wrap_model_call."""
        mw = PlanningMiddleware()
        runtime = self._make_runtime(thread_id="s1", plan_mode=True)
        result = mw.before_model(self._make_state("base"), runtime)
        # Session is initialized, but no state dict is returned
        assert result is None
        # The prompt is available via the internal helper
        prompt = mw._compute_planning_prompt("s1")
        assert prompt is not None
        assert "PLANNING MODE" in prompt

    def test_execution_mode_before_model_returns_none(self):
        """before_model returns None; prompt injection is in wrap_model_call."""
        mw = PlanningMiddleware()
        mw.sessions["s1"] = PlanningState(
            enabled=True, plan_confirmed=True, planning_phase=False,
            plan_tasks=["A", "B"],
        )
        runtime = self._make_runtime(thread_id="s1", plan_mode=True)
        result = mw.before_model(self._make_state("base"), runtime)
        assert result is None
        prompt = mw._compute_planning_prompt("s1")
        assert prompt is not None
        assert "EXECUTION MODE" in prompt

    def test_disabled_after_disable_returns_none(self):
        mw = PlanningMiddleware()
        mw.sessions["s1"] = PlanningState(enabled=False)
        runtime = self._make_runtime(thread_id="s1")
        result = mw.before_model(self._make_state(), runtime)
        assert result is None


# ------------------------------------------------------------------
# Thread safety
# ------------------------------------------------------------------


@pytest.mark.unit
class TestConcurrentAccess:
    def test_concurrent_session_access(self):
        """Multiple threads accessing different sessions should not race."""
        import threading

        mw = PlanningMiddleware()
        errors: list[Exception] = []

        def create_and_confirm(thread_id: str):
            try:
                mw.sessions[thread_id] = PlanningState(enabled=True)
                mw.confirm_plan(thread_id, [f"task-{thread_id}"])
                state = mw.get_state(thread_id)
                assert state is not None
                assert state.plan_confirmed is True
                mw.advance_task(thread_id)
                mw.disable_plan_mode(thread_id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=create_and_confirm, args=(f"t{i}",))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent access errors: {errors}"
        assert len(mw.sessions) == 20
