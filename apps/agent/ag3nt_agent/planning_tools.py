"""Extended planning tools for AG3NT.

This module provides task management capabilities with persistence.
It complements the TodoListMiddleware from langchain by providing:
- Persistent task storage in ~/.ag3nt/todos.json
- Extended task attributes (priority, parent_id, notes)
- Task filtering and markdown export
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal
import json
import uuid


class TaskStatus(Enum):
    """Status of a task in the planning system."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class Task:
    """A task in the planning system."""

    id: str
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    priority: Literal["low", "medium", "high"] = "medium"
    parent_id: str | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        """Convert task to a serializable dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "priority": self.priority,
            "parent_id": self.parent_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Create a Task from a dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            status=TaskStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            priority=data.get("priority", "medium"),
            parent_id=data.get("parent_id"),
            notes=data.get("notes", ""),
        )


class PlanningTools:
    """Extended planning capabilities with persistence.

    Provides CRUD operations for tasks with JSON file persistence.
    Tasks are stored in the specified storage_path.

    Args:
        storage_path: Path to the JSON file for task persistence.
    """

    def __init__(self, storage_path: str | Path):
        """Initialize PlanningTools with a storage path.

        Args:
            storage_path: Path to store tasks (JSON file).
        """
        self.storage_path = Path(storage_path)
        self.tasks: dict[str, Task] = {}
        self._load()

    def _load(self) -> None:
        """Load tasks from storage file."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for task_data in data.get("tasks", []):
                        task = Task.from_dict(task_data)
                        self.tasks[task.id] = task
            except (json.JSONDecodeError, KeyError, ValueError):
                # Start fresh if file is corrupted
                self.tasks = {}

    def _save(self) -> None:
        """Save tasks to storage file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"tasks": [task.to_dict() for task in self.tasks.values()]}
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def create_task(
        self,
        title: str,
        *,
        priority: Literal["low", "medium", "high"] = "medium",
        parent_id: str | None = None,
        notes: str = "",
    ) -> Task:
        """Create a new task.

        Args:
            title: Task title/description.
            priority: Task priority (low, medium, high).
            parent_id: Optional parent task ID for subtasks.
            notes: Additional notes for the task.

        Returns:
            The created Task object.
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = datetime.now()

        task = Task(
            id=task_id,
            title=title,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            priority=priority,
            parent_id=parent_id,
            notes=notes,
        )
        self.tasks[task_id] = task
        self._save()
        return task

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        title: str | None = None,
        notes: str | None = None,
        priority: Literal["low", "medium", "high"] | None = None,
    ) -> Task:
        """Update an existing task.

        Args:
            task_id: ID of the task to update.
            status: New status (optional).
            title: New title (optional).
            notes: New notes (optional).
            priority: New priority (optional).

        Returns:
            The updated Task object.

        Raises:
            ValueError: If task_id is not found.
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task not found: {task_id}")

        task = self.tasks[task_id]
        if status is not None:
            task.status = status
        if title is not None:
            task.title = title
        if notes is not None:
            task.notes = notes
        if priority is not None:
            task.priority = priority
        task.updated_at = datetime.now()

        self._save()
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: ID of the task to delete.

        Returns:
            True if task was deleted, False if not found.
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save()
            return True
        return False

    def get_task(self, task_id: str) -> Task | None:
        """Get a single task by ID.

        Args:
            task_id: ID of the task to retrieve.

        Returns:
            The Task object, or None if not found.
        """
        return self.tasks.get(task_id)

    def get_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        priority: Literal["low", "medium", "high"] | None = None,
        parent_id: str | None = None,
    ) -> list[Task]:
        """Get tasks with optional filters.

        Args:
            status: Filter by status (optional).
            priority: Filter by priority (optional).
            parent_id: Filter by parent task ID (optional).

        Returns:
            List of matching Task objects, sorted by creation time (newest first).
        """
        tasks = list(self.tasks.values())

        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if priority is not None:
            tasks = [t for t in tasks if t.priority == priority]
        if parent_id is not None:
            tasks = [t for t in tasks if t.parent_id == parent_id]

        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def clear_completed(self) -> int:
        """Remove all completed tasks.

        Returns:
            Number of tasks removed.
        """
        completed_ids = [
            task_id
            for task_id, task in self.tasks.items()
            if task.status == TaskStatus.COMPLETED
        ]
        for task_id in completed_ids:
            del self.tasks[task_id]
        if completed_ids:
            self._save()
        return len(completed_ids)

    def to_markdown(self) -> str:
        """Export tasks as markdown.

        Returns:
            Markdown string representing all tasks grouped by status.
        """
        lines = ["# Tasks\n"]

        for status in TaskStatus:
            status_tasks = [t for t in self.tasks.values() if t.status == status]
            if status_tasks:
                status_title = status.value.replace("_", " ").title()
                lines.append(f"\n## {status_title}\n")
                for task in sorted(status_tasks, key=lambda t: t.created_at):
                    checkbox = "[x]" if task.status == TaskStatus.COMPLETED else "[ ]"
                    lines.append(f"- {checkbox} **{task.title}** ({task.priority})")
                    if task.notes:
                        lines.append(f"  - {task.notes}")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export tasks as JSON string.

        Returns:
            JSON string of all tasks.
        """
        return json.dumps(
            {"tasks": [task.to_dict() for task in self.tasks.values()]},
            indent=2,
        )


def get_default_storage_path() -> Path:
    """Get the default storage path for tasks.

    Returns:
        Path to ~/.ag3nt/todos.json
    """
    return Path.home() / ".ag3nt" / "todos.json"


def create_planning_tools(storage_path: Path | None = None) -> PlanningTools:
    """Create a PlanningTools instance with default or custom storage path.

    Args:
        storage_path: Optional custom storage path. Defaults to ~/.ag3nt/todos.json

    Returns:
        Configured PlanningTools instance.
    """
    if storage_path is None:
        storage_path = get_default_storage_path()
    return PlanningTools(storage_path)

