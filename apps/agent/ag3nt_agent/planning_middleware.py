"""Planning middleware for structured planning before execution.

This middleware enforces a planning-first approach where the agent must:
1. Analyze the user's request
2. Create a detailed plan using write_todos
3. Present the plan for user approval
4. Execute the plan step-by-step

The middleware tracks planning state across turns and modifies the system
prompt to guide the agent through planning and execution phases.
"""

from dataclasses import dataclass, field
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class PlanningState:
    """Tracks planning mode state for a session."""

    enabled: bool = False  # Whether planning mode is active
    planning_phase: bool = True  # True = planning, False = executing
    plan_confirmed: bool = False  # Whether user confirmed the plan
    plan_tasks: list[str] = field(default_factory=list)  # List of task descriptions
    current_task_index: int = 0  # Current task being executed


class PlanningMiddleware:
    """Middleware that enforces planning before execution.

    When enabled, this middleware:
    - Forces the agent to create a plan before taking any actions
    - Prevents file writes/edits during planning phase
    - Tracks execution progress through planned tasks
    - Provides progress updates as tasks complete
    """

    def __init__(self):
        self.sessions: dict[str, PlanningState] = {}
        logger.info("PlanningMiddleware initialized")

    async def __call__(self, state: dict, config: dict) -> dict:
        """Intercept agent execution to enforce planning.

        Args:
            state: Current agent state
            config: Configuration dict with metadata

        Returns:
            Modified state with planning instructions injected
        """
        thread_id = config["configurable"]["thread_id"]

        # Get or create planning state for this session
        if thread_id not in self.sessions:
            # Check if plan_mode enabled in metadata
            plan_mode = config.get("metadata", {}).get("plan_mode", False)
            self.sessions[thread_id] = PlanningState(enabled=plan_mode)
            if plan_mode:
                logger.info(f"Planning mode activated for session {thread_id}")

        plan_state = self.sessions[thread_id]

        # If planning mode not enabled, pass through
        if not plan_state.enabled:
            return state

        # Inject appropriate prompt based on phase
        if plan_state.planning_phase and not plan_state.plan_confirmed:
            state = self._inject_planning_prompt(state)
        elif plan_state.plan_confirmed:
            state = self._inject_execution_prompt(state, plan_state)

        return state

    def _inject_planning_prompt(self, state: dict) -> dict:
        """Add planning instructions to system prompt."""
        planning_instruction = """

🎯 **PLANNING MODE ACTIVE**

You are in planning mode. Before executing any actions, you MUST create a detailed plan.

## Planning Process

1. **Analyze the Request**
   - Break down what the user is asking for
   - Identify all files that need to be read or modified
   - Note any ambiguities or questions

2. **Create a Detailed Plan**
   Use `write_todos` to create tasks:
   - Clear, actionable descriptions
   - Logical order (dependencies first)
   - Estimated complexity for each task
   - Files involved in each task

3. **Present for Approval**
   - Summarize the plan in your response
   - List all tasks clearly
   - Note any assumptions or risks
   - Ask user to confirm before proceeding

## During Planning Phase

✅ **You CAN:**
- Read files to understand context
- Search for information
- Use memory_search
- Create todos with write_todos

❌ **You CANNOT:**
- Write, edit, or delete files
- Execute shell commands
- Make any changes to code

## Plan Format

Structure your response like this:

### Implementation Plan

**Summary:** [1-2 sentence overview of what will be done]

**Files to be modified:**
- `/workspace/file1.py` - Description of changes
- `/workspace/file2.js` - Description of changes

**Tasks:**
1. [Task description] - Complexity: [Low/Med/High] - Files: [...]
2. [Task description] - Complexity: [Low/Med/High] - Files: [...]
...

**Assumptions:**
- [List any assumptions you're making]

**Risks/Concerns:**
- [Note potential issues or edge cases]

**Ready to proceed?** (Wait for user confirmation)

---

**Remember:** Do NOT execute any changes yet. Only create the plan.
"""
        # Append to system message (ensure it exists)
        if "system_message" not in state or state["system_message"] is None:
            state["system_message"] = ""

        state["system_message"] = state["system_message"] + planning_instruction
        return state

    def _inject_execution_prompt(self, state: dict, plan_state: PlanningState) -> dict:
        """Add execution guidance with progress tracking."""
        total_tasks = len(plan_state.plan_tasks)
        current = plan_state.current_task_index + 1

        execution_instruction = f"""

✅ **PLAN APPROVED - EXECUTION MODE**

Execute the approved plan step-by-step.

**Progress:** Task {current}/{total_tasks}

## Execution Guidelines

For each task:
1. **Announce:** State which task you're starting
2. **Execute:** Perform the task carefully
3. **Verify:** Check that changes work as expected
4. **Update:** Mark task complete with `update_todo`
5. **Report:** Briefly summarize what was done

## Current Status

Tasks completed: {plan_state.current_task_index}
Tasks remaining: {total_tasks - plan_state.current_task_index}

After completing each task, provide a brief progress update.
"""
        # Append to system message
        if "system_message" not in state or state["system_message"] is None:
            state["system_message"] = ""

        state["system_message"] = state["system_message"] + execution_instruction
        return state

    def confirm_plan(self, thread_id: str, tasks: list[str]):
        """User confirmed the plan - switch to execution mode.

        Args:
            thread_id: Session ID
            tasks: List of task descriptions from the plan
        """
        if thread_id in self.sessions:
            plan_state = self.sessions[thread_id]
            plan_state.plan_confirmed = True
            plan_state.planning_phase = False
            plan_state.plan_tasks = tasks
            logger.info(f"Plan confirmed for session {thread_id}: {len(tasks)} tasks")

    def advance_task(self, thread_id: str):
        """Move to next task in plan.

        Args:
            thread_id: Session ID
        """
        if thread_id in self.sessions:
            self.sessions[thread_id].current_task_index += 1
            logger.info(
                f"Advanced to task {self.sessions[thread_id].current_task_index + 1}"
            )

    def disable_plan_mode(self, thread_id: str):
        """Disable planning mode for a session.

        Args:
            thread_id: Session ID
        """
        if thread_id in self.sessions:
            self.sessions[thread_id].enabled = False
            logger.info(f"Planning mode disabled for session {thread_id}")

    def get_state(self, thread_id: str) -> PlanningState | None:
        """Get planning state for a session.

        Args:
            thread_id: Session ID

        Returns:
            PlanningState if exists, None otherwise
        """
        return self.sessions.get(thread_id)
