"""Post-execution learning recorder for blueprints.

Records blueprint outcomes and validation failures in the
Context-Engine so future context gathering can benefit from
past experience.

Stored data:
- Blueprint summaries in ``COLLECTION_BLUEPRINTS`` for similarity search
- Per-task outcomes in ``COLLECTION_LEARNING`` for confidence scoring
- Anti-patterns from failures

Usage:
    from ag3nt_agent.plan_learning import PlanLearningRecorder

    recorder = PlanLearningRecorder()
    await recorder.record_blueprint_outcome(blueprint, success=True, duration_ms=12000)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("ag3nt.plan_learning")


class PlanLearningRecorder:
    """Records blueprint outcomes for future learning.

    Args:
        context_engine: ``ContextEngineClient`` instance.
            If ``None``, uses the singleton from ``get_context_engine()``.
    """

    def __init__(self, context_engine: Any | None = None):
        self._ce = context_engine

    @property
    def context_engine(self) -> Any:
        if self._ce is None:
            from ag3nt_agent.context_engine_client import get_context_engine
            self._ce = get_context_engine()
        return self._ce

    async def record_blueprint_outcome(
        self,
        blueprint: Any,
        success: bool,
        duration_ms: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Record the overall outcome of a blueprint execution.

        Stores:
        1. Blueprint summary in ``COLLECTION_BLUEPRINTS`` for future
           similarity search via ``ContextGatherer``.
        2. Per-task outcomes in ``COLLECTION_LEARNING``.

        Args:
            blueprint: ``ContextBlueprint`` instance.
            success: Whether the blueprint was executed successfully.
            duration_ms: Total execution time in milliseconds.
            error_message: Error details if failed.
        """
        from ag3nt_agent.context_engine_client import COLLECTION_BLUEPRINTS, ContextEngineClient

        ce = self.context_engine

        # 1. Store blueprint summary
        try:
            task_titles = [t.title for t in blueprint.tasks]
            learnings = blueprint.learnings or []
            if error_message:
                learnings = learnings + [f"Failed: {error_message}"]

            await ce.store_memory(
                information=f"Blueprint: {blueprint.goal}",
                metadata={
                    "blueprint_id": blueprint.id,
                    "session_id": blueprint.session_id,
                    "goal": blueprint.goal,
                    "why": blueprint.why,
                    "success": success,
                    "duration_ms": duration_ms,
                    "task_count": len(blueprint.tasks),
                    "task_titles": task_titles,
                    "status": blueprint.status,
                    "learnings": learnings,
                    "error_message": error_message,
                },
                collection=COLLECTION_BLUEPRINTS,
            )
            logger.info(
                "Recorded blueprint outcome: %s (success=%s)", blueprint.id, success
            )
        except Exception as exc:
            logger.warning("Failed to store blueprint outcome: %s", exc)

        # 2. Store per-task outcomes
        for i, task in enumerate(blueprint.tasks):
            task_success = task.status == "completed"
            try:
                await ce.store_memory(
                    information=(
                        f"Task '{task.title}' in blueprint '{blueprint.goal}': "
                        f"{'completed' if task_success else task.status}"
                    ),
                    metadata={
                        "blueprint_id": blueprint.id,
                        "task_index": i,
                        "task_title": task.title,
                        "success": task_success,
                        "complexity": task.complexity,
                        "files_involved": task.files_involved,
                        "validation_result": task.validation_result,
                        "notes": task.notes,
                    },
                    collection=ContextEngineClient.COLLECTION_LEARNING,
                )
            except Exception as exc:
                logger.debug("Failed to store task outcome: %s", exc)

    async def record_validation_failure(
        self,
        blueprint_id: str,
        task_title: str,
        validation_level: int,
        error_details: str,
    ) -> None:
        """Record a validation gate failure as a learning opportunity.

        Args:
            blueprint_id: ID of the blueprint.
            task_title: Title of the task that failed validation.
            validation_level: Validation level (1=syntax, 2=unit, 3=integration).
            error_details: Details of the validation failure.
        """
        from ag3nt_agent.context_engine_client import ContextEngineClient

        try:
            level_names = {1: "syntax", 2: "unit_test", 3: "integration"}
            level_name = level_names.get(validation_level, f"level_{validation_level}")

            await self.context_engine.store_memory(
                information=(
                    f"Validation failure ({level_name}) for task '{task_title}': "
                    f"{error_details[:500]}"
                ),
                metadata={
                    "blueprint_id": blueprint_id,
                    "task_title": task_title,
                    "validation_level": validation_level,
                    "success": False,
                    "error_message": error_details[:1000],
                    "type": "validation_failure",
                },
                collection=ContextEngineClient.COLLECTION_LEARNING,
            )
            logger.info(
                "Recorded validation failure: %s / %s (level %d)",
                blueprint_id, task_title, validation_level,
            )
        except Exception as exc:
            logger.warning("Failed to store validation failure: %s", exc)
