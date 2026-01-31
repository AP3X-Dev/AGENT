"""AG3NT agent worker.

FastAPI RPC server that hosts the DeepAgents runtime.
The Gateway calls this worker to run session turns.

Endpoints:
- POST /turn: Run a conversation turn
- POST /resume: Resume an interrupted turn after approval/rejection
- GET /health: Health check
- GET /subagents: List all registered subagents
- GET /subagents/{name}: Get a specific subagent
- POST /subagents: Register a new custom subagent
- DELETE /subagents/{name}: Unregister a custom subagent
"""

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ag3nt_agent.deepagents_runtime import (
    run_turn as deepagents_run_turn,
    resume_turn as deepagents_resume_turn,
)
from ag3nt_agent.errors import get_error_registry
from ag3nt_agent.subagent_registry import SubagentRegistry
from ag3nt_agent.subagent_configs import SubagentConfig

app = FastAPI(title="ag3nt-agent")


# =============================================================================
# Request/Response Models
# =============================================================================


class TurnRequest(BaseModel):
    session_id: str
    text: str
    metadata: dict | None = None


class UsageInfo(BaseModel):
    """Token usage information for tracking and billing."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = "unknown"
    provider: str = "unknown"


class InterruptInfo(BaseModel):
    """Information about an interrupt requiring approval or user input.

    For tool approval interrupts:
        - pending_actions: List of actions needing approval
        - action_count: Number of actions

    For user question interrupts:
        - type: "user_question"
        - question: The question to ask
        - options: Optional list of choices
        - allow_custom: Whether custom answers are allowed
    """

    interrupt_id: str
    # Tool approval fields (optional)
    pending_actions: list[dict] | None = None
    action_count: int | None = None
    # User question fields (optional)
    type: str | None = None
    question: str | None = None
    options: list[str] | None = None
    allow_custom: bool | None = None


class TurnResponse(BaseModel):
    """Response from a turn, may include interrupt for approval."""

    session_id: str
    text: str
    events: list[dict] = []
    interrupt: InterruptInfo | None = None
    usage: UsageInfo | None = None


class ResumeRequest(BaseModel):
    """Request to resume an interrupted turn."""

    session_id: str
    decisions: list[dict]  # Each with {"type": "approve"} or {"type": "reject"}


class ResumeResponse(BaseModel):
    """Response from resuming a turn."""

    session_id: str
    text: str
    events: list[dict] = []
    interrupt: InterruptInfo | None = None
    usage: UsageInfo | None = None


class SubagentConfigRequest(BaseModel):
    """Request to create a new subagent."""

    name: str
    description: str
    system_prompt: str
    tools: list[str] = []
    max_tokens: int = 8000
    max_turns: int = 3
    model_override: str | None = None
    thinking_mode: str = "disabled"
    priority: int = 100


class SubagentResponse(BaseModel):
    """Response for a subagent."""

    name: str
    description: str
    source: str
    system_prompt: str
    tools: list[str]
    max_tokens: int
    max_turns: int
    model_override: str | None
    thinking_mode: str
    priority: int


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/health")
def health():
    return {"ok": True, "name": "ag3nt-agent"}


@app.post("/turn", response_model=TurnResponse)
def turn(req: TurnRequest):
    """Run a turn through the DeepAgents runtime.

    If the agent attempts to use a risky tool, the response will include
    an `interrupt` field with details about the pending action(s).
    The client should display these to the user and call /resume with
    the user's decision.
    """
    result = deepagents_run_turn(
        session_id=req.session_id,
        text=req.text,
        metadata=req.metadata,
    )

    # Build interrupt info if present
    interrupt = None
    if "interrupt" in result and result["interrupt"]:
        interrupt_data = result["interrupt"]
        interrupt = InterruptInfo(
            interrupt_id=interrupt_data["interrupt_id"],
            pending_actions=interrupt_data.get("pending_actions"),
            action_count=interrupt_data.get("action_count"),
            type=interrupt_data.get("type"),
            question=interrupt_data.get("question"),
            options=interrupt_data.get("options"),
            allow_custom=interrupt_data.get("allow_custom"),
        )

    # Build usage info if present
    usage = None
    if "usage" in result and result["usage"]:
        usage = UsageInfo(**result["usage"])

    return TurnResponse(
        session_id=result["session_id"],
        text=result["text"],
        events=result.get("events", []),
        interrupt=interrupt,
        usage=usage,
    )


@app.post("/resume", response_model=ResumeResponse)
def resume(req: ResumeRequest):
    """Resume an interrupted turn after user approval/rejection.

    The `decisions` field should contain one decision per pending action,
    in order. Each decision is a dict with {"type": "approve"} or {"type": "reject"}.

    If the resumed execution triggers another risky tool, the response
    will again contain an `interrupt` field.
    """
    result = deepagents_resume_turn(
        session_id=req.session_id,
        decisions=req.decisions,
    )

    # Build interrupt info if present
    interrupt = None
    if "interrupt" in result and result["interrupt"]:
        interrupt_data = result["interrupt"]
        interrupt = InterruptInfo(
            interrupt_id=interrupt_data["interrupt_id"],
            pending_actions=interrupt_data.get("pending_actions"),
            action_count=interrupt_data.get("action_count"),
            type=interrupt_data.get("type"),
            question=interrupt_data.get("question"),
            options=interrupt_data.get("options"),
            allow_custom=interrupt_data.get("allow_custom"),
        )

    # Build usage info if present
    usage = None
    if "usage" in result and result["usage"]:
        usage = UsageInfo(**result["usage"])

    return ResumeResponse(
        session_id=result["session_id"],
        text=result["text"],
        events=result.get("events", []),
        interrupt=interrupt,
        usage=usage,
    )


@app.get("/errors")
def get_errors():
    """Get all standardized error definitions.

    Returns a dictionary of error codes to their definitions,
    useful for clients to understand error responses.
    """
    registry = get_error_registry()
    definitions = registry.get_all_definitions()
    return {
        "ok": True,
        "errors": {
            code: {
                "code": defn.code,
                "message": defn.message,
                "http_status": defn.http_status,
                "retryable": defn.retryable,
            }
            for code, defn in definitions.items()
        }
    }


# =============================================================================
# Subagent Management Endpoints
# =============================================================================


@app.get("/subagents")
def list_subagents():
    """List all registered subagents (builtin + plugin + user-defined)."""
    registry = SubagentRegistry.get_instance()
    subagents = []
    for config in registry.list_all():
        source = registry.get_source(config.name.lower())
        subagents.append({
            "name": config.name,
            "description": config.description,
            "source": source or "unknown",
            "tools": config.tools,
            "max_tokens": config.max_tokens,
            "priority": config.priority,
        })
    return {"subagents": subagents, "count": len(subagents)}


@app.get("/subagents/{name}")
def get_subagent(name: str):
    """Get a specific subagent by name."""
    registry = SubagentRegistry.get_instance()
    config = registry.get(name)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Subagent '{name}' not found")

    source = registry.get_source(name.lower())
    return SubagentResponse(
        name=config.name,
        description=config.description,
        source=source or "unknown",
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_tokens=config.max_tokens,
        max_turns=config.max_turns,
        model_override=config.model_override,
        thinking_mode=config.thinking_mode,
        priority=config.priority,
    )


@app.post("/subagents", status_code=201)
def create_subagent(req: SubagentConfigRequest):
    """Register a new custom subagent (user-defined)."""
    registry = SubagentRegistry.get_instance()

    # Check if it already exists
    if registry.get(req.name) is not None:
        raise HTTPException(
            status_code=409, detail=f"Subagent '{req.name}' already exists"
        )

    # Create the SubagentConfig
    config = SubagentConfig(
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        tools=req.tools,
        max_tokens=req.max_tokens,
        max_turns=req.max_turns,
        model_override=req.model_override,
        thinking_mode=req.thinking_mode,
        priority=req.priority,
    )

    # Register as user-defined
    success = registry.register(config, source="user")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to register subagent")

    # Persist to user data directory
    from pathlib import Path
    user_data_path = Path.home() / ".ag3nt"
    registry.save_single_config(config, user_data_path)

    return {"message": f"Subagent '{req.name}' registered successfully", "name": req.name}


@app.delete("/subagents/{name}")
def delete_subagent(name: str):
    """Unregister a custom subagent (only user-defined subagents can be deleted)."""
    registry = SubagentRegistry.get_instance()

    # Check if it exists
    config = registry.get(name)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Subagent '{name}' not found")

    # Check if it's builtin (cannot be deleted)
    source = registry.get_source(name.lower())
    if source == "builtin":
        raise HTTPException(
            status_code=403, detail="Cannot delete builtin subagents"
        )

    # Unregister
    success = registry.unregister(name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to unregister subagent")

    # Delete the config file if it exists
    from pathlib import Path
    user_data_path = Path.home() / ".ag3nt" / "subagents"
    config_file = user_data_path / f"{name.lower()}.yaml"
    if config_file.exists():
        config_file.unlink()
    # Also check for JSON
    json_file = user_data_path / f"{name.lower()}.json"
    if json_file.exists():
        json_file.unlink()

    return {"message": f"Subagent '{name}' unregistered successfully"}


def main():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18790)


if __name__ == "__main__":
    main()
