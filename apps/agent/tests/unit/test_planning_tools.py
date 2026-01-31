"""Unit tests for planning_tools module."""

import json
import pytest
from datetime import datetime
from pathlib import Path

from ag3nt_agent.planning_tools import (
    PlanningTools,
    Task,
    TaskStatus,
    get_default_storage_path,
    create_planning_tools,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_status_values(self):
        """Test that all expected status values exist."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.BLOCKED.value == "blocked"

    def test_status_count(self):
        """Test that we have exactly 4 statuses."""
        assert len(TaskStatus) == 4


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation(self):
        """Test basic task creation."""
        now = datetime.now()
        task = Task(
            id="task_001",
            title="Test task",
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        assert task.id == "task_001"
        assert task.title == "Test task"
        assert task.status == TaskStatus.PENDING
        assert task.priority == "medium"  # default
        assert task.parent_id is None
        assert task.notes == ""

    def test_task_with_all_fields(self):
        """Test task with all optional fields."""
        now = datetime.now()
        task = Task(
            id="task_001",
            title="Test task",
            status=TaskStatus.IN_PROGRESS,
            created_at=now,
            updated_at=now,
            priority="high",
            parent_id="task_000",
            notes="Some notes",
        )
        assert task.priority == "high"
        assert task.parent_id == "task_000"
        assert task.notes == "Some notes"

    def test_to_dict(self):
        """Test task serialization to dictionary."""
        now = datetime.now()
        task = Task(
            id="task_001",
            title="Test task",
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            priority="high",
        )
        data = task.to_dict()
        assert data["id"] == "task_001"
        assert data["title"] == "Test task"
        assert data["status"] == "pending"
        assert data["priority"] == "high"
        assert data["created_at"] == now.isoformat()
        assert data["updated_at"] == now.isoformat()

    def test_from_dict(self):
        """Test task deserialization from dictionary."""
        now = datetime.now()
        data = {
            "id": "task_001",
            "title": "Test task",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "priority": "low",
            "parent_id": "task_000",
            "notes": "Test notes",
        }
        task = Task.from_dict(data)
        assert task.id == "task_001"
        assert task.title == "Test task"
        assert task.status == TaskStatus.COMPLETED
        assert task.priority == "low"
        assert task.parent_id == "task_000"
        assert task.notes == "Test notes"

    def test_from_dict_with_defaults(self):
        """Test deserialization with missing optional fields."""
        now = datetime.now()
        data = {
            "id": "task_001",
            "title": "Test task",
            "status": "pending",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        task = Task.from_dict(data)
        assert task.priority == "medium"
        assert task.parent_id is None
        assert task.notes == ""


class TestPlanningTools:
    """Tests for PlanningTools class."""

    @pytest.fixture
    def planner(self, tmp_path: Path):
        """Create a PlanningTools instance with temporary storage."""
        return PlanningTools(tmp_path / "tasks.json")

    def test_create_task(self, planner: PlanningTools):
        """Test basic task creation."""
        task = planner.create_task("Test task")
        assert task.title == "Test task"
        assert task.status == TaskStatus.PENDING
        assert task.id.startswith("task_")
        assert task.priority == "medium"

    def test_create_task_with_priority(self, planner: PlanningTools):
        """Test task creation with priority."""
        task = planner.create_task("High priority task", priority="high")
        assert task.priority == "high"

    def test_create_task_with_parent(self, planner: PlanningTools):
        """Test task creation with parent."""
        parent = planner.create_task("Parent task")
        child = planner.create_task("Child task", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_create_task_with_notes(self, planner: PlanningTools):
        """Test task creation with notes."""
        task = planner.create_task("Task with notes", notes="Some notes")
        assert task.notes == "Some notes"

    def test_create_task_persists(self, tmp_path: Path):
        """Test that created tasks are persisted."""
        storage_path = tmp_path / "tasks.json"
        planner1 = PlanningTools(storage_path)
        task = planner1.create_task("Persisted task")

        # Create new instance, task should be loaded
        planner2 = PlanningTools(storage_path)
        assert task.id in planner2.tasks
        assert planner2.tasks[task.id].title == "Persisted task"

    def test_update_task_status(self, planner: PlanningTools):
        """Test updating task status."""
        task = planner.create_task("Test task")
        updated = planner.update_task(task.id, status=TaskStatus.IN_PROGRESS)
        assert updated.status == TaskStatus.IN_PROGRESS
        assert updated.updated_at >= task.created_at  # May be same if very fast

    def test_update_task_title(self, planner: PlanningTools):
        """Test updating task title."""
        task = planner.create_task("Original title")
        updated = planner.update_task(task.id, title="Updated title")
        assert updated.title == "Updated title"

    def test_update_task_notes(self, planner: PlanningTools):
        """Test updating task notes."""
        task = planner.create_task("Test task")
        updated = planner.update_task(task.id, notes="New notes")
        assert updated.notes == "New notes"

    def test_update_task_priority(self, planner: PlanningTools):
        """Test updating task priority."""
        task = planner.create_task("Test task", priority="low")
        updated = planner.update_task(task.id, priority="high")
        assert updated.priority == "high"

    def test_update_task_not_found(self, planner: PlanningTools):
        """Test updating non-existent task."""
        with pytest.raises(ValueError, match="Task not found"):
            planner.update_task("nonexistent_task", status=TaskStatus.COMPLETED)

    def test_delete_task(self, planner: PlanningTools):
        """Test deleting a task."""
        task = planner.create_task("To be deleted")
        assert planner.delete_task(task.id) is True
        assert task.id not in planner.tasks

    def test_delete_task_not_found(self, planner: PlanningTools):
        """Test deleting non-existent task."""
        assert planner.delete_task("nonexistent_task") is False

    def test_get_task(self, planner: PlanningTools):
        """Test getting a single task."""
        task = planner.create_task("Test task")
        retrieved = planner.get_task(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id
        assert retrieved.title == task.title

    def test_get_task_not_found(self, planner: PlanningTools):
        """Test getting non-existent task."""
        assert planner.get_task("nonexistent_task") is None

    def test_get_tasks_all(self, planner: PlanningTools):
        """Test getting all tasks."""
        planner.create_task("Task 1")
        planner.create_task("Task 2")
        planner.create_task("Task 3")
        tasks = planner.get_tasks()
        assert len(tasks) == 3

    def test_get_tasks_by_status(self, planner: PlanningTools):
        """Test filtering tasks by status."""
        task1 = planner.create_task("Task 1")
        task2 = planner.create_task("Task 2")
        planner.update_task(task1.id, status=TaskStatus.IN_PROGRESS)

        in_progress = planner.get_tasks(status=TaskStatus.IN_PROGRESS)
        assert len(in_progress) == 1
        assert in_progress[0].id == task1.id

    def test_get_tasks_by_priority(self, planner: PlanningTools):
        """Test filtering tasks by priority."""
        planner.create_task("Low priority", priority="low")
        planner.create_task("High priority", priority="high")
        planner.create_task("Medium priority")

        high_priority = planner.get_tasks(priority="high")
        assert len(high_priority) == 1
        assert high_priority[0].priority == "high"

    def test_get_tasks_by_parent(self, planner: PlanningTools):
        """Test filtering tasks by parent."""
        parent = planner.create_task("Parent")
        child1 = planner.create_task("Child 1", parent_id=parent.id)
        child2 = planner.create_task("Child 2", parent_id=parent.id)
        planner.create_task("Orphan")

        children = planner.get_tasks(parent_id=parent.id)
        assert len(children) == 2
        assert {c.id for c in children} == {child1.id, child2.id}

    def test_get_tasks_sorted_by_creation(self, planner: PlanningTools):
        """Test that tasks are sorted by creation time (newest first)."""
        import time

        task1 = planner.create_task("Task 1")
        time.sleep(0.01)  # Small delay to ensure different timestamps
        task2 = planner.create_task("Task 2")
        time.sleep(0.01)
        task3 = planner.create_task("Task 3")

        tasks = planner.get_tasks()
        assert tasks[0].id == task3.id  # newest first
        assert tasks[2].id == task1.id  # oldest last

    def test_clear_completed(self, planner: PlanningTools):
        """Test clearing completed tasks."""
        task1 = planner.create_task("Task 1")
        task2 = planner.create_task("Task 2")
        task3 = planner.create_task("Task 3")
        planner.update_task(task1.id, status=TaskStatus.COMPLETED)
        planner.update_task(task2.id, status=TaskStatus.COMPLETED)

        removed = planner.clear_completed()
        assert removed == 2
        assert len(planner.tasks) == 1
        assert task3.id in planner.tasks

    def test_clear_completed_none(self, planner: PlanningTools):
        """Test clearing when no completed tasks."""
        planner.create_task("Task 1")
        removed = planner.clear_completed()
        assert removed == 0

    def test_to_markdown(self, planner: PlanningTools):
        """Test markdown export."""
        task1 = planner.create_task("Pending task")
        task2 = planner.create_task("Completed task")
        planner.update_task(task2.id, status=TaskStatus.COMPLETED)

        md = planner.to_markdown()
        assert "# Tasks" in md
        assert "## Pending" in md
        assert "## Completed" in md
        assert "Pending task" in md
        assert "Completed task" in md
        assert "[x]" in md
        assert "[ ]" in md

    def test_to_markdown_with_notes(self, planner: PlanningTools):
        """Test markdown export with notes."""
        planner.create_task("Task with notes", notes="Some notes")
        md = planner.to_markdown()
        assert "Some notes" in md

    def test_to_markdown_with_priority(self, planner: PlanningTools):
        """Test markdown export shows priority."""
        planner.create_task("High priority", priority="high")
        md = planner.to_markdown()
        assert "(high)" in md

    def test_to_json(self, planner: PlanningTools):
        """Test JSON export."""
        planner.create_task("Task 1")
        planner.create_task("Task 2")

        json_str = planner.to_json()
        data = json.loads(json_str)
        assert "tasks" in data
        assert len(data["tasks"]) == 2

    def test_persistence_across_instances(self, tmp_path: Path):
        """Test full persistence workflow."""
        storage_path = tmp_path / "tasks.json"

        # Create tasks
        planner1 = PlanningTools(storage_path)
        task = planner1.create_task("Persistent task", priority="high")
        planner1.update_task(task.id, status=TaskStatus.IN_PROGRESS, notes="Working")

        # Load in new instance
        planner2 = PlanningTools(storage_path)
        loaded_task = planner2.get_task(task.id)
        assert loaded_task is not None
        assert loaded_task.title == "Persistent task"
        assert loaded_task.status == TaskStatus.IN_PROGRESS
        assert loaded_task.priority == "high"
        assert loaded_task.notes == "Working"

    def test_corrupted_file_recovery(self, tmp_path: Path):
        """Test recovery from corrupted storage file."""
        storage_path = tmp_path / "tasks.json"
        storage_path.write_text("not valid json")

        planner = PlanningTools(storage_path)
        assert len(planner.tasks) == 0  # Start fresh

    def test_empty_file_handling(self, tmp_path: Path):
        """Test handling empty storage file."""
        storage_path = tmp_path / "tasks.json"
        storage_path.write_text("")

        planner = PlanningTools(storage_path)
        assert len(planner.tasks) == 0

    def test_storage_path_created(self, tmp_path: Path):
        """Test that storage directory is created if it doesn't exist."""
        storage_path = tmp_path / "nested" / "dir" / "tasks.json"
        planner = PlanningTools(storage_path)
        planner.create_task("Test")
        assert storage_path.exists()


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_default_storage_path(self):
        """Test default storage path."""
        path = get_default_storage_path()
        assert path.name == "todos.json"
        assert ".ag3nt" in str(path)

    def test_create_planning_tools_default(self, monkeypatch, tmp_path: Path):
        """Test creating PlanningTools with default path."""
        # Mock home to tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        planner = create_planning_tools()
        assert planner.storage_path == tmp_path / ".ag3nt" / "todos.json"

    def test_create_planning_tools_custom_path(self, tmp_path: Path):
        """Test creating PlanningTools with custom path."""
        custom_path = tmp_path / "custom" / "tasks.json"
        planner = create_planning_tools(custom_path)
        assert planner.storage_path == custom_path

