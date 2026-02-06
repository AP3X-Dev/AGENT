"""
Tests for Goal Manager.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from ag3nt_agent.autonomous.goal_manager import (
    GoalManager,
    Goal,
    Trigger,
    Action,
    ActionType,
    RiskLevel,
    Limits,
)
from ag3nt_agent.autonomous.event_bus import Event


class TestTrigger:
    """Tests for Trigger dataclass."""

    def test_matches_simple(self):
        """Test simple event type matching."""
        trigger = Trigger(event_type="http_check")
        event = Event(event_type="http_check", source="monitor")

        assert trigger.matches(event) is True

    def test_matches_wrong_type(self):
        """Test non-matching event type."""
        trigger = Trigger(event_type="http_check")
        event = Event(event_type="file_change", source="watcher")

        assert trigger.matches(event) is False

    def test_matches_with_filter(self):
        """Test matching with payload filter."""
        trigger = Trigger(
            event_type="http_check",
            filter={"success": False}
        )

        event_match = Event(
            event_type="http_check",
            source="monitor",
            payload={"success": False, "status": 500}
        )
        event_no_match = Event(
            event_type="http_check",
            source="monitor",
            payload={"success": True, "status": 200}
        )

        assert trigger.matches(event_match) is True
        assert trigger.matches(event_no_match) is False

    def test_matches_with_regex_filter(self):
        """Test matching with regex pattern filter."""
        trigger = Trigger(
            event_type="http_check",
            filter={"url": "regex:https?://mysite\\.com.*"}
        )

        event_match = Event(
            event_type="http_check",
            source="monitor",
            payload={"url": "https://mysite.com/health"}
        )
        event_no_match = Event(
            event_type="http_check",
            source="monitor",
            payload={"url": "https://other.com/health"}
        )

        assert trigger.matches(event_match) is True
        assert trigger.matches(event_no_match) is False


class TestAction:
    """Tests for Action dataclass."""

    def test_create_shell_action(self):
        """Test creating a shell action."""
        action = Action(
            type=ActionType.SHELL,
            command="systemctl restart nginx"
        )

        assert action.type == ActionType.SHELL
        assert action.command == "systemctl restart nginx"

    def test_create_notify_action(self):
        """Test creating a notify action."""
        action = Action(
            type=ActionType.NOTIFY,
            channel="slack:#alerts",
            message="Service is down!"
        )

        assert action.type == ActionType.NOTIFY
        assert action.channel == "slack:#alerts"

    def test_render_with_template(self):
        """Test rendering action with event data."""
        action = Action(
            type=ActionType.SHELL,
            command="echo {{ event['payload']['message'] }}"
        )

        event = Event(
            event_type="test",
            source="test",
            payload={"message": "Hello World"}
        )

        rendered = action.render(event)

        assert "Hello World" in rendered.command


class TestGoal:
    """Tests for Goal dataclass."""

    @pytest.fixture
    def sample_goal(self):
        """Create a sample goal."""
        return Goal(
            id="test-goal",
            name="Test Goal",
            description="A test goal",
            trigger=Trigger(event_type="http_check", filter={"success": False}),
            action=Action(type=ActionType.SHELL, command="echo test"),
            risk_level=RiskLevel.MEDIUM,
            confidence_threshold=0.75,
            limits=Limits(max_executions_per_hour=5, max_executions_per_day=20)
        )

    def test_matches_event(self, sample_goal):
        """Test goal matching an event."""
        event = Event(
            event_type="http_check",
            source="monitor",
            payload={"success": False}
        )

        assert sample_goal.matches(event) is True

    def test_matches_event_disabled(self, sample_goal):
        """Test disabled goal doesn't match."""
        sample_goal.enabled = False

        event = Event(
            event_type="http_check",
            source="monitor",
            payload={"success": False}
        )

        assert sample_goal.matches(event) is False

    def test_can_execute_ok(self, sample_goal):
        """Test can_execute when no limits hit."""
        can_exec, reason = sample_goal.can_execute()

        assert can_exec is True
        assert reason == "OK"

    def test_can_execute_cooldown(self, sample_goal):
        """Test can_execute during cooldown."""
        sample_goal._last_triggered = datetime.utcnow()

        can_exec, reason = sample_goal.can_execute()

        assert can_exec is False
        assert "Cooldown" in reason

    def test_can_execute_hourly_limit(self, sample_goal):
        """Test can_execute when hourly limit reached."""
        sample_goal._executions_this_hour = 5
        sample_goal._hour_reset = datetime.utcnow() + timedelta(minutes=30)

        can_exec, reason = sample_goal.can_execute()

        assert can_exec is False
        assert "Hourly limit" in reason

    def test_can_execute_daily_limit(self, sample_goal):
        """Test can_execute when daily limit reached."""
        sample_goal._executions_today = 20
        sample_goal._day_reset = datetime.utcnow() + timedelta(hours=12)

        can_exec, reason = sample_goal.can_execute()

        assert can_exec is False
        assert "Daily limit" in reason

    def test_record_execution(self, sample_goal):
        """Test recording an execution."""
        sample_goal.record_execution()

        assert sample_goal._last_triggered is not None
        assert sample_goal._executions_this_hour == 1
        assert sample_goal._executions_today == 1

    def test_to_dict(self, sample_goal):
        """Test goal serialization."""
        data = sample_goal.to_dict()

        assert data["id"] == "test-goal"
        assert data["name"] == "Test Goal"
        assert data["risk_level"] == "medium"

    def test_from_dict(self):
        """Test goal deserialization."""
        data = {
            "id": "test-goal",
            "name": "Test Goal",
            "description": "A test",
            "trigger": {
                "event_type": "http_check",
                "filter": {"success": False},
                "cooldown_seconds": 300
            },
            "action": {
                "type": "shell",
                "command": "echo test",
                "timeout_seconds": 60
            },
            "risk_level": "high",
            "confidence_threshold": 0.9
        }

        goal = Goal.from_dict(data)

        assert goal.id == "test-goal"
        assert goal.risk_level == RiskLevel.HIGH
        assert goal.trigger.event_type == "http_check"


class TestGoalManager:
    """Tests for GoalManager."""

    @pytest.fixture
    def manager(self):
        """Create a goal manager."""
        return GoalManager()

    @pytest.fixture
    def sample_goal(self):
        """Create a sample goal."""
        return Goal(
            id="test-goal",
            name="Test Goal",
            description="A test goal",
            trigger=Trigger(event_type="http_check"),
            action=Action(type=ActionType.SHELL, command="echo test")
        )

    def test_add_goal(self, manager, sample_goal):
        """Test adding a goal."""
        manager.add_goal(sample_goal)

        assert manager.get_goal("test-goal") is not None

    def test_remove_goal(self, manager, sample_goal):
        """Test removing a goal."""
        manager.add_goal(sample_goal)
        result = manager.remove_goal("test-goal")

        assert result is True
        assert manager.get_goal("test-goal") is None

    def test_remove_nonexistent_goal(self, manager):
        """Test removing a goal that doesn't exist."""
        result = manager.remove_goal("nonexistent")

        assert result is False

    def test_list_goals(self, manager, sample_goal):
        """Test listing all goals."""
        manager.add_goal(sample_goal)

        goals = manager.list_goals()

        assert len(goals) == 1
        assert goals[0].id == "test-goal"

    def test_find_matching_goals(self, manager, sample_goal):
        """Test finding goals that match an event."""
        manager.add_goal(sample_goal)

        event = Event(event_type="http_check", source="monitor")
        matching = manager.find_matching_goals(event)

        assert len(matching) == 1
        assert matching[0].id == "test-goal"

    def test_find_matching_goals_none(self, manager, sample_goal):
        """Test finding goals with no matches."""
        manager.add_goal(sample_goal)

        event = Event(event_type="file_change", source="watcher")
        matching = manager.find_matching_goals(event)

        assert len(matching) == 0

    def test_find_matching_goals_emergency_stop(self, manager, sample_goal):
        """Test that emergency stop prevents matches."""
        manager.add_goal(sample_goal)
        manager.set_emergency_stop(True)

        event = Event(event_type="http_check", source="monitor")
        matching = manager.find_matching_goals(event)

        assert len(matching) == 0

    def test_enable_disable_goal(self, manager, sample_goal):
        """Test enabling and disabling goals."""
        manager.add_goal(sample_goal)

        manager.disable_goal("test-goal")
        assert manager.get_goal("test-goal").enabled is False

        manager.enable_goal("test-goal")
        assert manager.get_goal("test-goal").enabled is True

    def test_get_status(self, manager, sample_goal):
        """Test getting manager status."""
        manager.add_goal(sample_goal)

        status = manager.get_status()

        assert status["total_goals"] == 1
        assert status["enabled_goals"] == 1
        assert status["emergency_stop"] is False

    def test_load_goals_from_yaml(self, manager):
        """Test loading goals from YAML files."""
        yaml_content = """
goals:
  - id: yaml-goal
    name: YAML Goal
    description: Loaded from YAML
    trigger:
      event_type: test
    action:
      type: shell
      command: echo test
    risk_level: low
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "goals.yaml"
            yaml_path.write_text(yaml_content)

            manager.load_goals(Path(tmpdir))

        goal = manager.get_goal("yaml-goal")
        assert goal is not None
        assert goal.name == "YAML Goal"
        assert goal.risk_level == RiskLevel.LOW


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_threshold_multipliers(self):
        """Test risk level threshold multipliers."""
        assert RiskLevel.LOW.threshold_multiplier == 0.5
        assert RiskLevel.MEDIUM.threshold_multiplier == 0.75
        assert RiskLevel.HIGH.threshold_multiplier == 0.9
        assert RiskLevel.CRITICAL.threshold_multiplier == 1.0
