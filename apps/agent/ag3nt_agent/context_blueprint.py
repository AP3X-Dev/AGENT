"""Context Blueprint — PRP-style structured planning for AG3NT.

This module provides a blueprint data model that extends the basic
write_todos planning flow with:
- Structured goal/why/what decomposition (PRP framework)
- Code references with relevance scoring
- Anti-patterns and gotchas from past experience
- Validation gates between tasks
- Per-blueprint persistence in ~/.ag3nt/blueprints/

The blueprint system is opt-in and coexists with the existing
PlanningTools task system.  Blueprints are activated when
``metadata["context_engineering"] = True``.

Usage:
    from ag3nt_agent.context_blueprint import get_blueprint_tools

    tools = get_blueprint_tools()
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.blueprint")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BlueprintStatus(str, Enum):
    """Lifecycle status of a blueprint."""

    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationLevel(int, Enum):
    """Validation gate severity levels."""

    SYNTAX = 1
    UNIT_TEST = 2
    INTEGRATION = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SuccessCriterion:
    """A single success criterion for a blueprint."""

    description: str
    validation_command: str | None = None
    validation_type: Literal["manual", "lint", "test", "type_check"] = "manual"


@dataclass
class CodeReference:
    """A reference to existing code relevant to the blueprint."""

    file_path: str
    start_line: int = 0
    end_line: int = 0
    content: str = ""
    relevance: str = ""
    source: str = ""  # "codebase_search", "context_engine", "user"


@dataclass
class AntiPattern:
    """A known anti-pattern to avoid."""

    description: str
    example: str = ""
    source: str = ""  # where this was learned


@dataclass
class BlueprintTask:
    """A single task within a blueprint."""

    title: str
    description: str = ""
    pseudocode: str = ""
    files_involved: list[str] = field(default_factory=list)
    dependencies: list[int] = field(default_factory=list)  # indices of prerequisite tasks
    validation_gate: int = 1  # ValidationLevel value
    complexity: Literal["low", "medium", "high"] = "medium"
    status: str = "pending"  # pending, in_progress, completed, skipped
    notes: str = ""
    validation_result: str = ""


@dataclass
class ValidationGate:
    """A validation checkpoint between tasks."""

    level: int  # ValidationLevel value
    name: str = ""
    checks: list[str] = field(default_factory=list)
    passed: bool | None = None
    results: str = ""


@dataclass
class ContextBlueprint:
    """Full PRP-style blueprint for a planning session.

    This is the primary data structure for context-engineered plans.
    """

    id: str
    session_id: str
    created_at: str
    updated_at: str

    # PRP fields
    goal: str = ""
    why: str = ""
    what: str = ""
    success_criteria: list[SuccessCriterion] = field(default_factory=list)

    # Context
    code_references: list[CodeReference] = field(default_factory=list)
    documentation_refs: list[str] = field(default_factory=list)
    anti_patterns: list[AntiPattern] = field(default_factory=list)
    gotchas: list[str] = field(default_factory=list)
    learnings: list[str] = field(default_factory=list)

    # Execution plan
    tasks: list[BlueprintTask] = field(default_factory=list)
    validation_gates: list[ValidationGate] = field(default_factory=list)

    # Status tracking
    status: str = BlueprintStatus.DRAFT.value
    current_task_index: int = 0

    def to_dict(self) -> dict:
        """Serialize blueprint to a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ContextBlueprint:
        """Deserialize a blueprint from a dictionary."""
        # Reconstruct nested dataclasses
        data = dict(data)  # shallow copy
        data["success_criteria"] = [
            SuccessCriterion(**sc) if isinstance(sc, dict) else sc
            for sc in data.get("success_criteria", [])
        ]
        data["code_references"] = [
            CodeReference(**cr) if isinstance(cr, dict) else cr
            for cr in data.get("code_references", [])
        ]
        data["anti_patterns"] = [
            AntiPattern(**ap) if isinstance(ap, dict) else ap
            for ap in data.get("anti_patterns", [])
        ]
        data["tasks"] = [
            BlueprintTask(**t) if isinstance(t, dict) else t
            for t in data.get("tasks", [])
        ]
        data["validation_gates"] = [
            ValidationGate(**vg) if isinstance(vg, dict) else vg
            for vg in data.get("validation_gates", [])
        ]
        return cls(**data)

    def to_markdown(self) -> str:
        """Export as readable markdown."""
        lines: list[str] = []
        lines.append(f"# Blueprint: {self.goal}")
        lines.append(f"\n**Status:** {self.status}")
        lines.append(f"**ID:** {self.id}")
        lines.append(f"**Session:** {self.session_id}")

        if self.why:
            lines.append(f"\n## Why\n{self.why}")
        if self.what:
            lines.append(f"\n## What\n{self.what}")

        if self.success_criteria:
            lines.append("\n## Success Criteria")
            for sc in self.success_criteria:
                cmd = f" (`{sc.validation_command}`)" if sc.validation_command else ""
                lines.append(f"- [{sc.validation_type}] {sc.description}{cmd}")

        if self.tasks:
            lines.append("\n## Tasks")
            for i, task in enumerate(self.tasks):
                check = "[x]" if task.status == "completed" else "[ ]"
                arrow = " <-- CURRENT" if i == self.current_task_index and self.status == BlueprintStatus.IN_PROGRESS.value else ""
                lines.append(f"{i+1}. {check} **{task.title}** ({task.complexity}){arrow}")
                if task.description:
                    lines.append(f"   {task.description}")
                if task.files_involved:
                    lines.append(f"   Files: {', '.join(task.files_involved)}")

        if self.anti_patterns:
            lines.append("\n## Anti-Patterns")
            for ap in self.anti_patterns:
                lines.append(f"- {ap.description}")

        if self.gotchas:
            lines.append("\n## Gotchas")
            for g in self.gotchas:
                lines.append(f"- {g}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Blueprint Store
# ---------------------------------------------------------------------------

def _get_blueprints_dir() -> Path:
    """Get the blueprints storage directory."""
    return Path.home() / ".ag3nt" / "blueprints"


class BlueprintStore:
    """Persistence layer for context blueprints.

    Stores each blueprint as a separate JSON file under
    ``~/.ag3nt/blueprints/{id}.json``.
    """

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or _get_blueprints_dir()

    def save(self, blueprint: ContextBlueprint) -> None:
        """Save a blueprint to disk."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.storage_dir / f"{blueprint.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(blueprint.to_dict(), f, indent=2)
        logger.debug("Saved blueprint %s", blueprint.id)

    def load(self, blueprint_id: str) -> ContextBlueprint | None:
        """Load a blueprint by ID."""
        path = self.storage_dir / f"{blueprint_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ContextBlueprint.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load blueprint %s: %s", blueprint_id, exc)
            return None

    def load_for_session(self, session_id: str) -> ContextBlueprint | None:
        """Load the most recent blueprint for a session."""
        if not self.storage_dir.exists():
            return None
        best: ContextBlueprint | None = None
        for path in self.storage_dir.glob("*.json"):
            bp = self.load(path.stem)
            if bp and bp.session_id == session_id:
                if best is None or bp.updated_at > best.updated_at:
                    best = bp
        return best

    def list_recent(self, limit: int = 10) -> list[ContextBlueprint]:
        """List the most recently updated blueprints."""
        if not self.storage_dir.exists():
            return []
        blueprints: list[ContextBlueprint] = []
        for path in self.storage_dir.glob("*.json"):
            bp = self.load(path.stem)
            if bp:
                blueprints.append(bp)
        blueprints.sort(key=lambda b: b.updated_at, reverse=True)
        return blueprints[:limit]


# ---------------------------------------------------------------------------
# Singleton store and active blueprint tracking
# ---------------------------------------------------------------------------

_store: BlueprintStore | None = None
_active_blueprint_id: str | None = None


def _get_store() -> BlueprintStore:
    global _store
    if _store is None:
        _store = BlueprintStore()
    return _store


def _get_active_blueprint() -> ContextBlueprint | None:
    """Get the currently active blueprint, if any."""
    if _active_blueprint_id is None:
        return None
    return _get_store().load(_active_blueprint_id)


# ---------------------------------------------------------------------------
# LangChain @tool wrappers
# ---------------------------------------------------------------------------


@tool
def write_blueprint(
    goal: str,
    why: str,
    what: str,
    tasks: list[dict[str, Any]],
    success_criteria: list[dict[str, Any]] | None = None,
    anti_patterns: list[dict[str, Any]] | None = None,
    gotchas: list[str] | None = None,
    learnings: list[str] | None = None,
    code_references: list[dict[str, Any]] | None = None,
    session_id: str = "",
) -> str:
    """Create a PRP-style implementation blueprint.

    Use this instead of write_todos when context engineering is enabled.
    Produces a structured plan with validation gates and context.

    Args:
        goal: What needs to be achieved (1-2 sentences).
        why: Business/technical reason for this change.
        what: Detailed description of what will change.
        tasks: List of task dicts with keys: title, description, pseudocode,
               files_involved, dependencies, validation_gate, complexity.
        success_criteria: List of dicts with: description, validation_command,
                         validation_type (manual/lint/test/type_check).
        anti_patterns: List of dicts with: description, example, source.
        gotchas: List of gotcha strings.
        learnings: List of relevant past learnings.
        code_references: List of dicts with: file_path, start_line, end_line,
                         content, relevance, source.
        session_id: Session ID for this blueprint.
    """
    global _active_blueprint_id

    now = datetime.utcnow().isoformat()
    blueprint_id = f"bp_{uuid.uuid4().hex[:12]}"

    # Build tasks
    bp_tasks = []
    for t in tasks:
        bp_tasks.append(BlueprintTask(
            title=t.get("title", "Untitled"),
            description=t.get("description", ""),
            pseudocode=t.get("pseudocode", ""),
            files_involved=t.get("files_involved", []),
            dependencies=t.get("dependencies", []),
            validation_gate=t.get("validation_gate", 1),
            complexity=t.get("complexity", "medium"),
        ))

    # Build success criteria
    bp_criteria = []
    for sc in (success_criteria or []):
        bp_criteria.append(SuccessCriterion(
            description=sc.get("description", ""),
            validation_command=sc.get("validation_command"),
            validation_type=sc.get("validation_type", "manual"),
        ))

    # Build anti-patterns
    bp_anti_patterns = []
    for ap in (anti_patterns or []):
        bp_anti_patterns.append(AntiPattern(
            description=ap.get("description", ""),
            example=ap.get("example", ""),
            source=ap.get("source", ""),
        ))

    # Build code references
    bp_code_refs = []
    for cr in (code_references or []):
        bp_code_refs.append(CodeReference(
            file_path=cr.get("file_path", ""),
            start_line=cr.get("start_line", 0),
            end_line=cr.get("end_line", 0),
            content=cr.get("content", ""),
            relevance=cr.get("relevance", ""),
            source=cr.get("source", ""),
        ))

    # Build default validation gates from tasks
    gate_levels_used = {t.validation_gate for t in bp_tasks}
    bp_gates = []
    for level in sorted(gate_levels_used):
        try:
            vl = ValidationLevel(level)
            bp_gates.append(ValidationGate(
                level=level,
                name=vl.name.replace("_", " ").title(),
            ))
        except ValueError:
            bp_gates.append(ValidationGate(level=level, name=f"Level {level}"))

    blueprint = ContextBlueprint(
        id=blueprint_id,
        session_id=session_id,
        created_at=now,
        updated_at=now,
        goal=goal,
        why=why,
        what=what,
        success_criteria=bp_criteria,
        code_references=bp_code_refs,
        anti_patterns=bp_anti_patterns,
        gotchas=gotchas or [],
        learnings=learnings or [],
        tasks=bp_tasks,
        validation_gates=bp_gates,
        status=BlueprintStatus.DRAFT.value,
    )

    store = _get_store()
    store.save(blueprint)
    _active_blueprint_id = blueprint_id

    summary_lines = [
        f"Blueprint created: {blueprint_id}",
        f"Goal: {goal}",
        f"Tasks: {len(bp_tasks)}",
    ]
    if bp_criteria:
        summary_lines.append(f"Success criteria: {len(bp_criteria)}")
    if bp_anti_patterns:
        summary_lines.append(f"Anti-patterns: {len(bp_anti_patterns)}")

    summary_lines.append("")
    summary_lines.append(blueprint.to_markdown())

    return "\n".join(summary_lines)


@tool
def read_blueprint(
    blueprint_id: str | None = None,
    format: str = "markdown",
) -> str:
    """Read the current or a specified blueprint.

    Args:
        blueprint_id: Blueprint ID to read. If omitted, reads the active blueprint.
        format: Output format — "markdown" or "json".
    """
    if blueprint_id:
        bp = _get_store().load(blueprint_id)
    else:
        bp = _get_active_blueprint()

    if bp is None:
        return "No active blueprint found. Use write_blueprint to create one."

    if format == "json":
        return json.dumps(bp.to_dict(), indent=2)
    return bp.to_markdown()


@tool
def update_blueprint_task(
    task_index: int,
    status: str,
    notes: str = "",
    validation_result: str = "",
    blueprint_id: str | None = None,
) -> str:
    """Update a task within the active blueprint.

    Args:
        task_index: Zero-based index of the task to update.
        status: New status — "pending", "in_progress", "completed", "skipped".
        notes: Optional notes about the task execution.
        validation_result: Optional validation gate result.
        blueprint_id: Blueprint ID. Uses active blueprint if omitted.
    """
    store = _get_store()
    if blueprint_id:
        bp = store.load(blueprint_id)
    else:
        bp = _get_active_blueprint()

    if bp is None:
        return "No active blueprint found."

    if task_index < 0 or task_index >= len(bp.tasks):
        return f"Invalid task index {task_index}. Blueprint has {len(bp.tasks)} tasks."

    task = bp.tasks[task_index]
    task.status = status
    if notes:
        task.notes = notes
    if validation_result:
        task.validation_result = validation_result

    # Advance current_task_index if this task was completed
    if status == "completed" and task_index == bp.current_task_index:
        bp.current_task_index = min(task_index + 1, len(bp.tasks) - 1)

    # Update blueprint status based on tasks
    if status == "in_progress" and bp.status == BlueprintStatus.DRAFT.value:
        bp.status = BlueprintStatus.IN_PROGRESS.value
    elif all(t.status in ("completed", "skipped") for t in bp.tasks):
        bp.status = BlueprintStatus.COMPLETED.value

    bp.updated_at = datetime.utcnow().isoformat()
    store.save(bp)

    completed = sum(1 for t in bp.tasks if t.status == "completed")
    total = len(bp.tasks)
    return (
        f"Updated task {task_index}: '{task.title}' -> {status}\n"
        f"Progress: {completed}/{total} tasks completed\n"
        f"Blueprint status: {bp.status}"
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_blueprint_tools() -> list:
    """Get all blueprint LangChain tools for the agent.

    Returns:
        List of @tool decorated blueprint functions.
    """
    return [write_blueprint, read_blueprint, update_blueprint_task]
