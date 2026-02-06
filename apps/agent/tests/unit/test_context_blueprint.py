"""Unit tests for context_blueprint module."""

from __future__ import annotations

import json
import pytest
from datetime import datetime
from pathlib import Path

from ag3nt_agent.context_blueprint import (
    AntiPattern,
    BlueprintStatus,
    BlueprintStore,
    BlueprintTask,
    CodeReference,
    ContextBlueprint,
    SuccessCriterion,
    ValidationGate,
    ValidationLevel,
    get_blueprint_tools,
    read_blueprint,
    update_blueprint_task,
    write_blueprint,
)


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------


@pytest.mark.unit
class TestEnums:
    def test_blueprint_status_values(self):
        assert BlueprintStatus.DRAFT.value == "draft"
        assert BlueprintStatus.APPROVED.value == "approved"
        assert BlueprintStatus.IN_PROGRESS.value == "in_progress"
        assert BlueprintStatus.COMPLETED.value == "completed"
        assert BlueprintStatus.FAILED.value == "failed"

    def test_validation_level_values(self):
        assert ValidationLevel.SYNTAX == 1
        assert ValidationLevel.UNIT_TEST == 2
        assert ValidationLevel.INTEGRATION == 3

    def test_validation_level_ordering(self):
        assert ValidationLevel.SYNTAX < ValidationLevel.UNIT_TEST < ValidationLevel.INTEGRATION


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@pytest.mark.unit
class TestSuccessCriterion:
    def test_defaults(self):
        sc = SuccessCriterion(description="Tests pass")
        assert sc.description == "Tests pass"
        assert sc.validation_command is None
        assert sc.validation_type == "manual"

    def test_all_fields(self):
        sc = SuccessCriterion(
            description="All tests pass",
            validation_command="pytest tests/",
            validation_type="test",
        )
        assert sc.validation_command == "pytest tests/"
        assert sc.validation_type == "test"


@pytest.mark.unit
class TestCodeReference:
    def test_defaults(self):
        ref = CodeReference(file_path="src/main.py")
        assert ref.file_path == "src/main.py"
        assert ref.start_line == 0
        assert ref.end_line == 0
        assert ref.content == ""
        assert ref.relevance == ""
        assert ref.source == ""

    def test_all_fields(self):
        ref = CodeReference(
            file_path="src/auth.py",
            start_line=10,
            end_line=50,
            content="def login():",
            relevance="auth handler",
            source="codebase_search",
        )
        assert ref.start_line == 10
        assert ref.source == "codebase_search"


@pytest.mark.unit
class TestAntiPattern:
    def test_defaults(self):
        ap = AntiPattern(description="Don't use eval()")
        assert ap.description == "Don't use eval()"
        assert ap.example == ""
        assert ap.source == ""


@pytest.mark.unit
class TestBlueprintTask:
    def test_defaults(self):
        task = BlueprintTask(title="Implement feature")
        assert task.title == "Implement feature"
        assert task.status == "pending"
        assert task.complexity == "medium"
        assert task.validation_gate == 1
        assert task.files_involved == []
        assert task.dependencies == []

    def test_all_fields(self):
        task = BlueprintTask(
            title="Add auth middleware",
            description="Create auth middleware",
            pseudocode="if not authenticated: return 401",
            files_involved=["src/middleware/auth.py"],
            dependencies=[0],
            validation_gate=2,
            complexity="high",
        )
        assert task.complexity == "high"
        assert task.dependencies == [0]


# ------------------------------------------------------------------
# ContextBlueprint
# ------------------------------------------------------------------


@pytest.mark.unit
class TestContextBlueprint:
    def _make_blueprint(self, **kwargs):
        now = datetime.utcnow().isoformat()
        defaults = dict(
            id="bp_test123",
            session_id="session_1",
            created_at=now,
            updated_at=now,
            goal="Test goal",
            why="Test why",
            what="Test what",
        )
        defaults.update(kwargs)
        return ContextBlueprint(**defaults)

    def test_creation_defaults(self):
        bp = self._make_blueprint()
        assert bp.id == "bp_test123"
        assert bp.status == "draft"
        assert bp.current_task_index == 0
        assert bp.tasks == []
        assert bp.success_criteria == []

    def test_to_dict_roundtrip(self):
        bp = self._make_blueprint(
            tasks=[BlueprintTask(title="Task 1")],
            success_criteria=[SuccessCriterion(description="Tests pass")],
            anti_patterns=[AntiPattern(description="No eval")],
            code_references=[CodeReference(file_path="a.py")],
        )
        data = bp.to_dict()
        assert isinstance(data, dict)
        assert data["goal"] == "Test goal"
        assert len(data["tasks"]) == 1

        # Roundtrip
        bp2 = ContextBlueprint.from_dict(data)
        assert bp2.goal == bp.goal
        assert bp2.tasks[0].title == "Task 1"
        assert bp2.success_criteria[0].description == "Tests pass"
        assert bp2.anti_patterns[0].description == "No eval"

    def test_to_markdown(self):
        bp = self._make_blueprint(
            tasks=[
                BlueprintTask(title="Step 1", complexity="low"),
                BlueprintTask(title="Step 2", status="completed"),
            ],
            anti_patterns=[AntiPattern(description="Avoid X")],
            gotchas=["Watch out for Y"],
        )
        md = bp.to_markdown()
        assert "# Blueprint: Test goal" in md
        assert "Step 1" in md
        assert "[x]" in md  # completed task
        assert "[ ]" in md  # pending task
        assert "Avoid X" in md
        assert "Watch out for Y" in md

    def test_from_dict_missing_optional(self):
        data = {
            "id": "bp_x",
            "session_id": "s1",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        bp = ContextBlueprint.from_dict(data)
        assert bp.id == "bp_x"
        assert bp.tasks == []
        assert bp.goal == ""


# ------------------------------------------------------------------
# BlueprintStore
# ------------------------------------------------------------------


@pytest.mark.unit
class TestBlueprintStore:
    @pytest.fixture
    def store(self, tmp_path: Path):
        return BlueprintStore(storage_dir=tmp_path / "blueprints")

    def _make_blueprint(self, bp_id="bp_001", session_id="s1"):
        now = datetime.utcnow().isoformat()
        return ContextBlueprint(
            id=bp_id,
            session_id=session_id,
            created_at=now,
            updated_at=now,
            goal="Test goal",
        )

    def test_save_and_load(self, store: BlueprintStore):
        bp = self._make_blueprint()
        store.save(bp)
        loaded = store.load("bp_001")
        assert loaded is not None
        assert loaded.id == "bp_001"
        assert loaded.goal == "Test goal"

    def test_load_missing(self, store: BlueprintStore):
        assert store.load("nonexistent") is None

    def test_load_corrupted(self, store: BlueprintStore):
        store.storage_dir.mkdir(parents=True, exist_ok=True)
        (store.storage_dir / "bad.json").write_text("not json")
        assert store.load("bad") is None

    def test_load_for_session(self, store: BlueprintStore):
        bp1 = self._make_blueprint("bp_001", "session_a")
        bp2 = self._make_blueprint("bp_002", "session_a")
        bp2.updated_at = "2099-01-01T00:00:00"  # newer
        store.save(bp1)
        store.save(bp2)

        result = store.load_for_session("session_a")
        assert result is not None
        assert result.id == "bp_002"  # most recent

    def test_load_for_session_no_match(self, store: BlueprintStore):
        bp = self._make_blueprint("bp_001", "session_a")
        store.save(bp)
        assert store.load_for_session("session_b") is None

    def test_list_recent(self, store: BlueprintStore):
        for i in range(5):
            bp = self._make_blueprint(f"bp_{i:03d}")
            store.save(bp)
        recent = store.list_recent(limit=3)
        assert len(recent) == 3

    def test_list_recent_empty(self, store: BlueprintStore):
        assert store.list_recent() == []

    def test_persistence(self, tmp_path: Path):
        storage_dir = tmp_path / "blueprints"
        store1 = BlueprintStore(storage_dir)
        bp = self._make_blueprint()
        store1.save(bp)

        store2 = BlueprintStore(storage_dir)
        loaded = store2.load("bp_001")
        assert loaded is not None
        assert loaded.goal == "Test goal"


# ------------------------------------------------------------------
# @tool wrappers
# ------------------------------------------------------------------


@pytest.mark.unit
class TestBlueprintTools:
    @pytest.fixture(autouse=True)
    def _use_temp_storage(self, tmp_path, monkeypatch):
        """Use temporary storage for blueprint tools during tests."""
        import ag3nt_agent.context_blueprint as cb

        cb._store = BlueprintStore(storage_dir=tmp_path / "blueprints")
        cb._active_blueprint_id = None

    def test_write_blueprint_basic(self):
        result = write_blueprint.invoke({
            "goal": "Add auth",
            "why": "Security",
            "what": "Add auth middleware",
            "tasks": [
                {"title": "Create middleware", "complexity": "high"},
                {"title": "Add tests"},
            ],
        })
        assert "Blueprint created" in result
        assert "Add auth" in result
        assert "Tasks: 2" in result

    def test_write_blueprint_with_all_fields(self):
        result = write_blueprint.invoke({
            "goal": "Refactor DB",
            "why": "Performance",
            "what": "Switch to connection pooling",
            "tasks": [{"title": "Update config"}],
            "success_criteria": [
                {"description": "Pool connections", "validation_type": "test"},
            ],
            "anti_patterns": [
                {"description": "Don't use global connection"},
            ],
            "gotchas": ["Watch for transaction isolation"],
            "learnings": ["Connection pooling reduced latency by 50%"],
            "code_references": [
                {"file_path": "db.py", "start_line": 10, "relevance": "current DB code"},
            ],
            "session_id": "test_session",
        })
        assert "Refactor DB" in result
        assert "Success criteria: 1" in result
        assert "Anti-patterns: 1" in result

    def test_read_blueprint_active(self):
        write_blueprint.invoke({
            "goal": "Test read",
            "why": "Testing",
            "what": "Test",
            "tasks": [{"title": "Task 1"}],
        })
        result = read_blueprint.invoke({})
        assert "Test read" in result

    def test_read_blueprint_json(self):
        write_blueprint.invoke({
            "goal": "JSON test",
            "why": "Testing",
            "what": "Test",
            "tasks": [{"title": "Task 1"}],
        })
        result = read_blueprint.invoke({"format": "json"})
        data = json.loads(result)
        assert data["goal"] == "JSON test"

    def test_read_blueprint_no_active(self):
        result = read_blueprint.invoke({})
        assert "No active blueprint" in result

    def test_update_blueprint_task_status(self):
        write_blueprint.invoke({
            "goal": "Update test",
            "why": "Testing",
            "what": "Test",
            "tasks": [
                {"title": "Task A"},
                {"title": "Task B"},
            ],
        })
        result = update_blueprint_task.invoke({
            "task_index": 0,
            "status": "completed",
        })
        assert "Updated task 0" in result
        assert "completed" in result
        assert "1/2" in result

    def test_update_blueprint_task_invalid_index(self):
        write_blueprint.invoke({
            "goal": "Test",
            "why": "T",
            "what": "T",
            "tasks": [{"title": "Only task"}],
        })
        result = update_blueprint_task.invoke({
            "task_index": 5,
            "status": "completed",
        })
        assert "Invalid task index" in result

    def test_update_blueprint_task_no_active(self):
        result = update_blueprint_task.invoke({
            "task_index": 0,
            "status": "completed",
        })
        assert "No active blueprint" in result

    def test_blueprint_completion_detection(self):
        write_blueprint.invoke({
            "goal": "Complete test",
            "why": "T",
            "what": "T",
            "tasks": [
                {"title": "Task A"},
                {"title": "Task B"},
            ],
        })
        update_blueprint_task.invoke({"task_index": 0, "status": "completed"})
        result = update_blueprint_task.invoke({"task_index": 1, "status": "completed"})
        assert "completed" in result.lower()

    def test_update_with_notes_and_validation(self):
        write_blueprint.invoke({
            "goal": "Notes test",
            "why": "T",
            "what": "T",
            "tasks": [{"title": "Task 1"}],
        })
        result = update_blueprint_task.invoke({
            "task_index": 0,
            "status": "in_progress",
            "notes": "Working on it",
            "validation_result": "Lint passed",
        })
        assert "Updated task 0" in result


@pytest.mark.unit
class TestGetBlueprintTools:
    def test_returns_list(self):
        tools = get_blueprint_tools()
        assert isinstance(tools, list)

    def test_returns_three_tools(self):
        tools = get_blueprint_tools()
        assert len(tools) == 3

    def test_tool_names(self):
        tools = get_blueprint_tools()
        names = {t.name for t in tools}
        assert names == {"write_blueprint", "read_blueprint", "update_blueprint_task"}

    def test_tools_have_descriptions(self):
        for t in get_blueprint_tools():
            assert t.description, f"Tool {t.name} missing description"
