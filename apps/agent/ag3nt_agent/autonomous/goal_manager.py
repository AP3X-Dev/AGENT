"""
Goal Manager for AG3NT Autonomous System

Manages YAML-based goal configurations that define:
- Event triggers and filters
- Actions to execute
- Risk levels and confidence thresholds
- Rate limiting and cooldowns
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from .event_bus import Event

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level for goal actions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def threshold_multiplier(self) -> float:
        """Higher risk = higher confidence threshold needed."""
        return {
            RiskLevel.LOW: 0.5,
            RiskLevel.MEDIUM: 0.75,
            RiskLevel.HIGH: 0.9,
            RiskLevel.CRITICAL: 1.0
        }[self]


class ActionType(Enum):
    """Types of actions a goal can execute."""
    SHELL = "shell"
    NOTIFY = "notify"
    HTTP = "http"
    AGENT = "agent"


@dataclass
class Trigger:
    """Event trigger configuration."""
    event_type: str
    filter: dict = field(default_factory=dict)
    cooldown_seconds: int = 60

    def matches(self, event: Event) -> bool:
        """Check if an event matches this trigger."""
        # Check event type
        if event.event_type != self.event_type:
            return False

        # Check filter conditions
        for key, pattern in self.filter.items():
            value = event.payload.get(key)

            if value is None:
                return False

            # Handle regex patterns
            if isinstance(pattern, str) and pattern.startswith("regex:"):
                regex = pattern[6:]  # Remove "regex:" prefix
                if not re.search(regex, str(value)):
                    return False
            # Handle exact match
            elif value != pattern:
                return False

        return True


@dataclass
class Action:
    """Action configuration."""
    type: ActionType
    command: Optional[str] = None
    agent_prompt: Optional[str] = None
    url: Optional[str] = None
    method: str = "POST"
    body: Optional[dict] = None
    channel: Optional[str] = None
    message: Optional[str] = None
    timeout_seconds: int = 60
    retry_count: int = 1
    retry_delay_seconds: int = 5

    def render(self, event: Event) -> "Action":
        """
        Render action with event data substituted.

        Supports Jinja2-style {{ variable }} substitution.
        """
        import copy

        rendered = copy.deepcopy(self)

        # Build context for substitution
        context = {
            "event": {
                "type": event.event_type,
                "source": event.source,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
                "metadata": event.metadata
            }
        }

        def substitute(text: str) -> str:
            """Simple template substitution."""
            if not isinstance(text, str):
                return text

            # Find {{ ... }} patterns
            pattern = r'\{\{\s*([^}]+)\s*\}\}'
            matches = re.finditer(pattern, text)

            result = text
            for match in matches:
                expr = match.group(1).strip()
                try:
                    # Evaluate expression against context
                    value = eval(expr, {"__builtins__": {}}, context)
                    result = result.replace(match.group(0), str(value))
                except Exception:
                    # Keep original if evaluation fails
                    pass

            return result

        # Substitute in relevant fields
        if rendered.command:
            rendered.command = substitute(rendered.command)
        if rendered.agent_prompt:
            rendered.agent_prompt = substitute(rendered.agent_prompt)
        if rendered.message:
            rendered.message = substitute(rendered.message)
        if rendered.url:
            rendered.url = substitute(rendered.url)

        return rendered


@dataclass
class Limits:
    """Rate limiting configuration."""
    max_executions_per_hour: int = 10
    max_executions_per_day: int = 100


@dataclass
class Goal:
    """
    A complete goal definition.

    Goals define what the agent should do in response to events,
    including triggers, actions, risk assessment, and rate limiting.
    """
    id: str
    name: str
    description: str
    trigger: Trigger
    action: Action
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidence_threshold: float = 0.75
    requires_approval: bool = False
    limits: Limits = field(default_factory=Limits)
    tags: list[str] = field(default_factory=list)
    owner: str = ""
    enabled: bool = True

    # Runtime state
    _last_triggered: Optional[datetime] = field(default=None, repr=False)
    _executions_this_hour: int = field(default=0, repr=False)
    _executions_today: int = field(default=0, repr=False)
    _hour_reset: Optional[datetime] = field(default=None, repr=False)
    _day_reset: Optional[datetime] = field(default=None, repr=False)

    def matches(self, event: Event) -> bool:
        """Check if this goal should handle an event."""
        if not self.enabled:
            return False

        return self.trigger.matches(event)

    def can_execute(self) -> tuple[bool, str]:
        """
        Check if the goal can execute now.

        Returns:
            Tuple of (can_execute, reason)
        """
        now = datetime.utcnow()

        # Check cooldown
        if self._last_triggered:
            cooldown_end = self._last_triggered + timedelta(seconds=self.trigger.cooldown_seconds)
            if now < cooldown_end:
                remaining = (cooldown_end - now).seconds
                return False, f"Cooldown active ({remaining}s remaining)"

        # Reset hourly counter if needed
        if self._hour_reset is None or now >= self._hour_reset:
            self._executions_this_hour = 0
            self._hour_reset = now + timedelta(hours=1)

        # Reset daily counter if needed
        if self._day_reset is None or now >= self._day_reset:
            self._executions_today = 0
            self._day_reset = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)

        # Check hourly limit
        if self._executions_this_hour >= self.limits.max_executions_per_hour:
            return False, f"Hourly limit reached ({self.limits.max_executions_per_hour}/hour)"

        # Check daily limit
        if self._executions_today >= self.limits.max_executions_per_day:
            return False, f"Daily limit reached ({self.limits.max_executions_per_day}/day)"

        return True, "OK"

    def record_execution(self):
        """Record that the goal was executed."""
        now = datetime.utcnow()
        self._last_triggered = now
        self._executions_this_hour += 1
        self._executions_today += 1

    def to_dict(self) -> dict:
        """Convert goal to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger": {
                "event_type": self.trigger.event_type,
                "filter": self.trigger.filter,
                "cooldown_seconds": self.trigger.cooldown_seconds
            },
            "action": {
                "type": self.action.type.value,
                "command": self.action.command,
                "timeout_seconds": self.action.timeout_seconds
            },
            "risk_level": self.risk_level.value,
            "confidence_threshold": self.confidence_threshold,
            "requires_approval": self.requires_approval,
            "limits": {
                "max_executions_per_hour": self.limits.max_executions_per_hour,
                "max_executions_per_day": self.limits.max_executions_per_day
            },
            "tags": self.tags,
            "owner": self.owner,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        """Create goal from dictionary."""
        trigger = Trigger(
            event_type=data["trigger"]["event_type"],
            filter=data["trigger"].get("filter", {}),
            cooldown_seconds=data["trigger"].get("cooldown_seconds", 60)
        )

        action_data = data["action"]
        action = Action(
            type=ActionType(action_data["type"]),
            command=action_data.get("command"),
            agent_prompt=action_data.get("agent_prompt"),
            url=action_data.get("url"),
            method=action_data.get("method", "POST"),
            body=action_data.get("body"),
            channel=action_data.get("channel"),
            message=action_data.get("message"),
            timeout_seconds=action_data.get("timeout_seconds", 60),
            retry_count=action_data.get("retry_count", 1),
            retry_delay_seconds=action_data.get("retry_delay_seconds", 5)
        )

        limits_data = data.get("limits", {})
        limits = Limits(
            max_executions_per_hour=limits_data.get("max_executions_per_hour", 10),
            max_executions_per_day=limits_data.get("max_executions_per_day", 100)
        )

        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            trigger=trigger,
            action=action,
            risk_level=RiskLevel(data.get("risk_level", "medium")),
            confidence_threshold=data.get("confidence_threshold", 0.75),
            requires_approval=data.get("requires_approval", False),
            limits=limits,
            tags=data.get("tags", []),
            owner=data.get("owner", ""),
            enabled=data.get("enabled", True)
        )


class GoalManager:
    """
    Manages goal configurations and event-to-goal matching.

    Loads goals from YAML files and provides methods for:
    - Finding goals that match events
    - Managing goal lifecycle
    - Persisting goal state
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the goal manager.

        Args:
            config_dir: Directory containing goal YAML files
        """
        self.config_dir = config_dir
        self._goals: dict[str, Goal] = {}

        # Global settings
        self._emergency_stop = False
        self._default_confidence_threshold = 0.75
        self._global_limits = {
            "max_concurrent_actions": 3,
            "max_actions_per_minute": 10
        }

        # Load goals if config_dir provided
        if config_dir and config_dir.exists():
            self.load_goals()

    def load_goals(self, config_dir: Optional[Path] = None):
        """Load goals from YAML files in the config directory."""
        config_dir = config_dir or self.config_dir
        if not config_dir:
            logger.warning("No config directory specified")
            return

        config_dir = Path(config_dir)
        if not config_dir.exists():
            logger.warning(f"Config directory does not exist: {config_dir}")
            return

        # Load all YAML files
        for yaml_file in config_dir.glob("*.yaml"):
            try:
                self._load_yaml_file(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load {yaml_file}: {e}")

        logger.info(f"Loaded {len(self._goals)} goals from {config_dir}")

    def _load_yaml_file(self, filepath: Path):
        """Load goals from a single YAML file."""
        with open(filepath) as f:
            data = yaml.safe_load(f)

        if not data:
            return

        # Load goals
        goals_data = data.get("goals", [])
        for goal_data in goals_data:
            try:
                goal = Goal.from_dict(goal_data)
                self._goals[goal.id] = goal
                logger.debug(f"Loaded goal: {goal.id}")
            except Exception as e:
                logger.error(f"Failed to parse goal: {e}")

        # Load global settings
        settings = data.get("settings", {})
        if settings:
            self._emergency_stop = settings.get("emergency_stop", False)
            self._default_confidence_threshold = settings.get(
                "default_confidence_threshold", 0.75
            )
            self._global_limits.update(settings.get("global_limits", {}))

    def add_goal(self, goal: Goal):
        """Add a goal programmatically."""
        self._goals[goal.id] = goal
        logger.info(f"Added goal: {goal.id}")

    def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal by ID."""
        if goal_id in self._goals:
            del self._goals[goal_id]
            logger.info(f"Removed goal: {goal_id}")
            return True
        return False

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        return self._goals.get(goal_id)

    def list_goals(self) -> list[Goal]:
        """List all goals."""
        return list(self._goals.values())

    def find_matching_goals(self, event: Event) -> list[Goal]:
        """
        Find all goals that match an event.

        Args:
            event: The event to match against

        Returns:
            List of matching goals (may be empty)
        """
        if self._emergency_stop:
            logger.warning("Emergency stop is active, no goals will match")
            return []

        matching = []
        for goal in self._goals.values():
            if goal.matches(event):
                can_execute, reason = goal.can_execute()
                if can_execute:
                    matching.append(goal)
                else:
                    logger.debug(f"Goal {goal.id} matched but cannot execute: {reason}")

        return matching

    def set_emergency_stop(self, active: bool):
        """Enable or disable emergency stop."""
        self._emergency_stop = active
        logger.warning(f"Emergency stop {'activated' if active else 'deactivated'}")

    @property
    def emergency_stop_active(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stop

    def enable_goal(self, goal_id: str) -> bool:
        """Enable a goal."""
        goal = self._goals.get(goal_id)
        if goal:
            goal.enabled = True
            return True
        return False

    def disable_goal(self, goal_id: str) -> bool:
        """Disable a goal."""
        goal = self._goals.get(goal_id)
        if goal:
            goal.enabled = False
            return True
        return False

    def get_status(self) -> dict:
        """Get goal manager status."""
        enabled_count = sum(1 for g in self._goals.values() if g.enabled)
        return {
            "total_goals": len(self._goals),
            "enabled_goals": enabled_count,
            "disabled_goals": len(self._goals) - enabled_count,
            "emergency_stop": self._emergency_stop,
            "default_confidence_threshold": self._default_confidence_threshold,
            "global_limits": self._global_limits
        }
