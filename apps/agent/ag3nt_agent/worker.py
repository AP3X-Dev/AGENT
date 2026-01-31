"""AG3NT agent worker.

FastAPI RPC server that hosts the DeepAgents runtime.
The Gateway calls this worker to run session turns.

Endpoints:
- POST /turn: Run a conversation turn
- POST /resume: Resume an interrupted turn after approval/rejection
- GET /health: Health check
"""

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel

from ag3nt_agent.deepagents_runtime import (
    run_turn as deepagents_run_turn,
    resume_turn as deepagents_resume_turn,
)
from ag3nt_agent.errors import get_error_registry

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
    """Information about an interrupt requiring approval."""

    interrupt_id: str
    pending_actions: list[dict]
    action_count: int


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
        interrupt = InterruptInfo(
            interrupt_id=result["interrupt"]["interrupt_id"],
            pending_actions=result["interrupt"]["pending_actions"],
            action_count=result["interrupt"]["action_count"],
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
        interrupt = InterruptInfo(
            interrupt_id=result["interrupt"]["interrupt_id"],
            pending_actions=result["interrupt"]["pending_actions"],
            action_count=result["interrupt"]["action_count"],
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


def main():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18790)


if __name__ == "__main__":
    main()
