"""AG3NT DeepAgents JSON-RPC daemon for AP3X-UI.

This process is intended to be spawned by the AP3X-UI Next.js server (node runtime)
and communicates over stdio using newline-delimited JSON.

Requests:
  {"id":"1","method":"health","params":{}}
  {"id":"2","method":"chat_stream","params":{"thread_id":"t1","assistant_id":"agent","message":"hi"}}
  {"id":"3","method":"resume_stream","params":{"thread_id":"t1","assistant_id":"agent","interrupt_id":"...","decision":"approve"}}

Streaming responses:
  {"id":"2","ok":true,"event":{"type":"text_delta","text":"Hello"}}
  ...
  {"id":"2","ok":true,"event":{"type":"done","approval_required":false,"auto_approve":false}}

Non-streaming responses:
  {"id":"1","ok":true,"result":{"status":"ok"}}

Notes:
- The AP3X-UI frontend expects specific event types: status, thread_id, text_delta,
  reasoning_delta, tool_call, tool_result, approval_required, done.
- DeepAgents v0.3.8 resumes HITL interrupts via Command(resume={"decisions":[...]}).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command, Interrupt
from pydantic import TypeAdapter


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_paths() -> None:
    root = _repo_root()
    agent_pkg_root = root / "apps" / "agent"
    if agent_pkg_root.exists():
        sys.path.insert(0, str(agent_pkg_root))


_ensure_import_paths()


try:
    from dotenv import load_dotenv

    root = _repo_root()
    load_dotenv(root / ".env")
    load_dotenv()
except Exception:
    # Daemon should still run even if python-dotenv isn't available.
    pass


from ag3nt_agent import deepagents_runtime  # noqa: E402


_HITL_REQUEST_ADAPTER = TypeAdapter(dict)


def _stringify_tool_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (bytes, bytearray)):
        try:
            return content.decode("utf-8", errors="replace")
        except Exception:
            return repr(content)
    if isinstance(content, (dict, list)):
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)
    return str(content)


def _safe_filename(name: str) -> str:
    name = name.strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    name = name[:80] if name else "attachment"
    if not name:
        return "attachment"
    return name


def _format_status_message(tool_name: str, args: dict[str, Any] | None) -> str:
    if tool_name == "task" and args:
        subagent_type = args.get("subagent_type", "") or args.get("subagentType", "")
        if subagent_type:
            formatted = " ".join(
                word.capitalize()
                for word in str(subagent_type).replace("-", " ").replace("_", " ").split()
            )
            return f"{formatted} Agent working..."
        description = args.get("description", "")
        if description:
            desc = str(description)
            preview = desc[:40] + "..." if len(desc) > 40 else desc
            return f"Agent working: {preview}"
        return "Subagent working..."

    friendly = {
        "internet_search": "Searching the web...",
        "fetch_url": "Fetching web page...",
        "memory_search": "Searching memory...",
        "run_skill": "Running skill...",
        "shell": "Running command...",
        "execute": "Executing code...",
        "browser_navigate": "Browsing...",
        "browser_screenshot": "Taking screenshot...",
        "browser_click": "Interacting with page...",
        "browser_fill": "Filling form...",
    }
    if tool_name in friendly:
        return friendly[tool_name]
    formatted = " ".join(
        word.capitalize() for word in str(tool_name).replace("-", " ").replace("_", " ").split()
    )
    return f"{formatted}..."


def _generate_thread_id() -> str:
    return uuid.uuid4().hex[:8]


def _tool_param_type(prop: dict[str, Any]) -> str:
    t = prop.get("type")
    if t in {"string", "number", "integer", "boolean", "array", "object"}:
        return t

    # Handle JSON Schema union forms.
    for key in ("anyOf", "oneOf", "allOf"):
        variants = prop.get(key)
        if isinstance(variants, list):
            for variant in variants:
                if isinstance(variant, dict) and variant.get("type") in {
                    "string",
                    "number",
                    "integer",
                    "boolean",
                    "array",
                    "object",
                }:
                    return str(variant["type"])

    return "string"


def _tool_category(name: str) -> str:
    if name in {"ls", "glob", "grep"} or name.endswith("_file") or name in {"read_file", "write_file", "edit_file"}:
        return "filesystem"
    if name in {"execute", "shell"}:
        return "shell"
    if name.startswith("browser_"):
        return "browser"
    if name in {"internet_search", "fetch_url"}:
        return "web"
    if name.startswith("memory") or name.startswith("summarize"):
        return "data"
    if name in {"deep_reasoning", "task"}:
        return "ai"
    if name in {"write_todos", "run_skill", "execute_node_action"}:
        return "utility"
    if name in {"schedule_reminder"}:
        return "communication"
    return "general"


def _tool_cost(category: str) -> str:
    if category in {"web"}:
        return "low"
    return "free"


def _tool_to_ui(tool: Any, risky: set[str]) -> dict[str, Any]:
    name = str(getattr(tool, "name", "") or "")
    description = str(getattr(tool, "description", "") or "")

    parameters: list[dict[str, Any]] = []
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None:
        try:
            schema = args_schema.model_json_schema()  # pydantic v2
            props = schema.get("properties") or {}
            required = set(schema.get("required") or [])
            if isinstance(props, dict):
                for pname, prop in props.items():
                    if not isinstance(prop, dict):
                        continue
                    parameters.append(
                        {
                            "name": str(pname),
                            "type": _tool_param_type(prop),
                            "description": str(prop.get("description") or ""),
                            "required": pname in required,
                            **({"default": prop["default"]} if "default" in prop else {}),
                            **({"enum": prop["enum"]} if "enum" in prop else {}),
                        }
                    )
        except Exception:
            parameters = []

    category = _tool_category(name)
    requires_approval = name in risky

    source = "builtin"
    mcp_server: str | None = None
    try:
        mod = getattr(tool.__class__, "__module__", "") or ""
        meta = getattr(tool, "metadata", None)
        if isinstance(meta, dict):
            mcp_server = meta.get("mcp_server") or meta.get("mcpServer") or meta.get("server")
        if "langchain_mcp_adapters" in mod or (isinstance(mcp_server, str) and mcp_server):
            source = "mcp"
    except Exception:
        pass

    tags = [category]
    if requires_approval:
        tags.append("approval")

    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "source": source,
        "status": "active",
        "metadata": {
            "category": category,
            "tags": tags,
            "cost": _tool_cost(category),
            "requiresApproval": requires_approval,
            "maxRetries": 0,
            "cacheable": False,
            "cacheTtlSeconds": 0,
        },
        **({"mcpServer": str(mcp_server)} if isinstance(mcp_server, str) and mcp_server else {}),
    }


def _agent_category(name: str) -> str:
    n = name.lower()
    if "coder" in n or "code" in n or "dev" in n:
        return "coding"
    if "research" in n:
        return "research"
    if "data" in n or "analyst" in n:
        return "data"
    if "creative" in n or "writer" in n:
        return "creative"
    if "auto" in n or "ops" in n:
        return "automation"
    if "debug" in n or "analysis" in n:
        return "analysis"
    return "general"


@dataclass
class PendingApproval:
    interrupt_id: str
    action_requests: list[dict[str, Any]]


@dataclass
class SessionState:
    thread_id: str
    auto_approve: bool = False
    assistant_id: str | None = None
    model_name: str | None = None
    updated_at: str | None = None
    preview: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


class AgentRuntime:
    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}
        self._sessions: dict[str, SessionState] = {}
        self._pending_approvals: dict[str, PendingApproval] = {}

    def clear_caches(self) -> dict[str, Any]:
        agents = len(self._agents)
        sessions = len(self._sessions)
        interrupts = len(self._pending_approvals)
        self._agents.clear()
        self._pending_approvals.clear()
        # Keep sessions so thread history doesn't disappear on clear-caches.
        return {
            "cleared_agents": agents,
            "cleared_sessions": 0,
            "cleared_interrupts": interrupts,
        }

    def delete_thread(self, thread_id: str) -> bool:
        existed = thread_id in self._sessions
        self._sessions.pop(thread_id, None)
        self._pending_approvals.pop(thread_id, None)
        return existed

    def list_threads(self, agent_name: str | None = None, limit: int = 50) -> dict[str, Any]:
        threads = list(self._sessions.values())
        if agent_name:
            threads = [t for t in threads if (t.assistant_id or "agent") == agent_name]
        threads.sort(key=lambda t: t.updated_at or "", reverse=True)
        threads = threads[: max(1, int(limit or 50))]
        return {
            "threads": [
                {
                    "thread_id": t.thread_id,
                    "agent_name": t.assistant_id,
                    "updated_at": t.updated_at,
                    "preview": t.preview,
                }
                for t in threads
            ]
        }

    def get_thread_messages(self, thread_id: str, limit: int = 50) -> dict[str, Any]:
        session = self._sessions.get(thread_id)
        if not session:
            return {"thread_id": thread_id, "messages": []}
        msgs = session.messages[-max(1, int(limit or 50)) :]
        return {"thread_id": thread_id, "messages": msgs}

    def _get_session(self, thread_id: str) -> SessionState:
        session = self._sessions.get(thread_id)
        if session is None:
            session = SessionState(thread_id=thread_id)
            self._sessions[thread_id] = session
        return session

    def _set_session_preview(self, session: SessionState, text: str | None) -> None:
        session.updated_at = datetime.now(UTC).isoformat()
        if not text:
            return
        preview = text.strip().replace("\n", " ")
        session.preview = preview[:140] if preview else None

    def _get_agent(self, model_name: str | None = None) -> Any:
        cache_key = model_name or "default"
        existing = self._agents.get(cache_key)
        if existing is not None:
            return existing

        original_model_name = os.environ.get("AG3NT_MODEL_NAME")
        try:
            if model_name:
                os.environ["AG3NT_MODEL_NAME"] = model_name
            agent = deepagents_runtime._build_agent()  # noqa: SLF001
        finally:
            if original_model_name is None:
                os.environ.pop("AG3NT_MODEL_NAME", None)
            else:
                os.environ["AG3NT_MODEL_NAME"] = original_model_name

        self._agents[cache_key] = agent
        return agent

    def list_tools(self, model_name: str | None = None) -> dict[str, Any]:
        agent = self._get_agent(model_name=model_name)
        graph = agent.get_graph()
        tools_node = graph.nodes.get("tools")
        if not tools_node:
            return {"tools": [], "mcp_servers": []}

        tool_runner = getattr(tools_node, "data", None)
        tools_by_name = getattr(tool_runner, "_tools_by_name", None)
        if not isinstance(tools_by_name, dict):
            return {"tools": [], "mcp_servers": []}

        risky = set(getattr(deepagents_runtime, "RISKY_TOOLS", []) or [])
        tools_out = [_tool_to_ui(t, risky) for _, t in sorted(tools_by_name.items(), key=lambda kv: str(kv[0]))]
        return {"tools": tools_out, "mcp_servers": []}

    def list_agents(self) -> dict[str, Any]:
        # Default model config (used as display-only metadata).
        provider = os.environ.get("AG3NT_MODEL_PROVIDER") or "auto"
        model = os.environ.get("AG3NT_MODEL_NAME") or "default"

        # Main agent entry (DeepAgents graph + AG3NT middleware).
        main_agent = {
            "name": "ag3nt",
            "description": "AG3NT main agent (DeepAgents graph) with tools, skills, memory, and subagents.",
            "mode": "main",
            "status": "active",
            "systemPrompt": "",
            "model": {"provider": provider, "model": model, "temperature": 0.0},
            "permissions": {},
            "enabledTools": [],
            "disabledTools": [],
            "middleware": [],
            "metadata": {"category": "general", "tags": ["main"]},
        }

        agents: list[dict[str, Any]] = [main_agent]

        try:
            from ag3nt_agent.subagent_registry import SubagentRegistry

            # Ensure user subagents are loaded (matches deepagents_runtime behavior).
            try:
                user_data_path = deepagents_runtime._get_user_data_path()  # noqa: SLF001
                SubagentRegistry.get_instance().load_user_configs(user_data_path)
            except Exception:
                pass

            reg = SubagentRegistry.get_instance().to_dict()
            for _, entry in sorted(reg.items(), key=lambda kv: str(kv[0])):
                cfg = entry.get("config") or {}
                source = entry.get("source") or "unknown"
                name = str(cfg.get("name") or "").strip() or str(cfg.get("id") or "").strip()
                if not name:
                    continue
                tools = cfg.get("tools") or []
                if not isinstance(tools, list):
                    tools = []
                sys_prompt = str(cfg.get("system_prompt") or "")
                agents.append(
                    {
                        "name": name,
                        "description": str(cfg.get("description") or ""),
                        "mode": "subagent",
                        "status": "active",
                        "systemPrompt": sys_prompt,
                        "model": {
                            "provider": provider,
                            "model": str(cfg.get("model_override") or model),
                            "temperature": 0.0,
                        },
                        "permissions": {},
                        "enabledTools": [str(t) for t in tools if isinstance(t, str)],
                        "disabledTools": [],
                        "middleware": [],
                        "metadata": {"category": _agent_category(name), "tags": [str(source)]},
                    }
                )
        except Exception:
            # Subagent registry is optional; keep main agent only.
            pass

        return {"agents": agents}

    async def chat(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = params.get("thread_id") or _generate_thread_id()
        assistant_id = params.get("assistant_id") or "agent"
        message = params.get("message") or ""
        auto_approve = bool(params.get("auto_approve", False))
        model = params.get("model")
        attachments = params.get("attachments")
        ui_context = params.get("ui_context")

        text_parts: list[str] = []
        approvals: list[dict[str, Any]] = []
        approval_required = False

        async for event in self.chat_stream(
            thread_id=thread_id,
            assistant_id=assistant_id,
            message=message,
            auto_approve=auto_approve,
            model=model,
            attachments=attachments,
            ui_context=ui_context,
        ):
            if event.get("type") == "text_delta":
                text_parts.append(str(event.get("text") or ""))
            elif event.get("type") == "approval_required":
                approval_required = True
                approvals = list(event.get("approvals") or [])

        return {
            "thread_id": thread_id,
            "text": "".join(text_parts),
            "approval_required": approval_required,
            "approvals": approvals,
        }

    async def resume(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = params.get("thread_id")
        assistant_id = params.get("assistant_id") or "agent"
        interrupt_id = params.get("interrupt_id") or ""
        decision = params.get("decision")

        if not thread_id or not decision:
            raise ValueError("resume requires thread_id and decision")

        text_parts: list[str] = []
        approvals: list[dict[str, Any]] = []
        approval_required = False

        async for event in self.resume_stream(
            thread_id=str(thread_id),
            assistant_id=assistant_id,
            interrupt_id=str(interrupt_id),
            decision=str(decision),
        ):
            if event.get("type") == "text_delta":
                text_parts.append(str(event.get("text") or ""))
            elif event.get("type") == "approval_required":
                approval_required = True
                approvals = list(event.get("approvals") or [])

        return {
            "thread_id": thread_id,
            "text": "".join(text_parts),
            "approval_required": approval_required,
            "approvals": approvals,
        }

    async def mcp_test_server(self, server_id: str) -> dict[str, Any]:
        server_id = str(server_id or "")
        if not server_id:
            raise ValueError("mcp_test_server requires server_id")

        # Use the same config source as the runtime.
        config = None
        try:
            config = deepagents_runtime._load_mcp_config()  # noqa: SLF001
        except Exception:
            config = None

        servers = (config or {}).get("mcpServers") if isinstance(config, dict) else None
        if not isinstance(servers, dict) or server_id not in servers:
            return {"status": "error", "error": f"Unknown MCP server: {server_id}", "tool_count": 0, "tools": []}

        server_cfg = servers.get(server_id)
        if not isinstance(server_cfg, dict):
            return {"status": "error", "error": f"Invalid MCP server config: {server_id}", "tool_count": 0, "tools": []}

        if server_cfg.get("enabled") is False:
            return {"status": "disconnected", "error": None, "tool_count": 0, "tools": []}

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except Exception as e:
            return {
                "status": "error",
                "error": f"langchain-mcp-adapters not installed: {e}",
                "tool_count": 0,
                "tools": [],
            }

        params = {
            server_id: {
                "command": server_cfg.get("command"),
                "args": server_cfg.get("args", []),
                "env": server_cfg.get("env"),
            }
        }

        try:
            async with MultiServerMCPClient(params) as mcp_client:
                tools = mcp_client.get_tools()
                names = [str(t.name) for t in tools if getattr(t, "name", None)]
                return {"status": "connected", "error": None, "tool_count": len(names), "tools": names}
        except Exception as e:
            return {"status": "error", "error": str(e), "tool_count": 0, "tools": []}

    def _build_config(self, *, thread_id: str, assistant_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "assistant_id": assistant_id,
                "agent_name": assistant_id,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        }

    def _workspace_dir(self) -> Path:
        # Must match AG3NT runtime workspace.
        base = Path.home() / ".ag3nt" / "workspace"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _save_attachment(self, attachment: dict[str, Any]) -> tuple[str | None, str | None]:
        """Save a binary attachment into AG3NT workspace and return (virtual_path, error)."""
        import base64

        file_type = str(attachment.get("type") or "")
        file_name = _safe_filename(str(attachment.get("name") or "attachment"))
        content_b64 = attachment.get("content") or ""
        data_url = attachment.get("data_url") or attachment.get("dataUrl") or ""

        raw_b64 = ""
        if isinstance(data_url, str) and "base64," in data_url:
            raw_b64 = data_url.split("base64,", 1)[1]
        elif isinstance(content_b64, str):
            raw_b64 = content_b64

        if not raw_b64:
            return None, "No base64 content"

        try:
            data = base64.b64decode(raw_b64)
        except Exception as e:
            return None, f"Failed to decode base64: {e!s}"

        attachments_dir = self._workspace_dir() / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)

        ext = ""
        if "/" in file_type:
            ext = file_type.split("/", 1)[1].split(";", 1)[0].strip()
        if ext.lower() == "jpeg":
            ext = "jpg"
        if ext and not file_name.lower().endswith(f".{ext.lower()}"):
            file_name = f"{file_name}.{ext}"

        unique = uuid.uuid4().hex[:8]
        disk_name = f"{unique}_{file_name}"
        disk_path = attachments_dir / disk_name
        try:
            disk_path.write_bytes(data)
        except Exception as e:
            return None, f"Failed to write attachment: {e!s}"

        return f"/workspace/attachments/{disk_name}", None

    def _build_message_content(
        self, message: str, attachments: list[dict[str, Any]] | None
    ) -> str | list[dict[str, Any]]:
        if not attachments:
            return message

        blocks: list[dict[str, Any]] = []
        if message.strip():
            blocks.append({"type": "text", "text": message})

        for att in attachments:
            file_name = str(att.get("name") or "attachment")
            file_type = str(att.get("type") or "")
            if file_type.startswith("image/") or file_type.startswith("application/octet-stream"):
                vpath, err = self._save_attachment(att)
                if vpath:
                    blocks.append(
                        {
                            "type": "text",
                            "text": (
                                f"\n\n[User attached file: {file_name}]\n"
                                f"Saved to: {vpath}\n"
                                "Use read_file or other tools on this virtual path.\n"
                            ),
                        }
                    )
                else:
                    blocks.append(
                        {
                            "type": "text",
                            "text": f"\n\n[Attachment: {file_name} - failed to save: {err}]\n",
                        }
                    )
                continue

            # For text/code/data: embed content
            content = att.get("content") or ""
            if isinstance(content, str) and content:
                # Content is usually base64 encoded.
                try:
                    import base64

                    decoded = base64.b64decode(content).decode("utf-8")
                except Exception:
                    decoded = str(content)
            else:
                decoded = "[No content]"
            blocks.append(
                {
                    "type": "text",
                    "text": f"\n\n--- FILE: {file_name} ---\n{decoded}\n--- END FILE ---\n",
                }
            )

        return blocks if blocks else message

    async def chat_stream(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        message: str,
        auto_approve: bool = False,
        model: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        ui_context: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        session = self._get_session(thread_id)
        session.auto_approve = bool(auto_approve)
        session.assistant_id = assistant_id
        session.model_name = model
        self._pending_approvals.pop(thread_id, None)

        agent = self._get_agent(model_name=model)
        config = self._build_config(thread_id=thread_id, assistant_id=assistant_id)

        message_content = self._build_message_content(message, attachments)

        messages: list[dict[str, Any]] = []
        if ui_context:
            messages.append({"role": "system", "content": ui_context})
        messages.append({"role": "user", "content": message_content})

        session.messages.append(
            {"role": "user", "content": message, "id": f"msg_user_{uuid.uuid4().hex[:8]}"}
        )

        stream_input: dict[str, Any] | Command = {"messages": messages}

        assistant_full_text = ""
        async for ev in self._stream_until_done_or_approval(
            agent=agent,
            config=config,
            session=session,
            stream_input=stream_input,
        ):
            if ev.get("type") == "text_delta":
                assistant_full_text += str(ev.get("text") or "")
            yield ev

        if assistant_full_text.strip():
            session.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_full_text,
                    "id": f"msg_asst_{uuid.uuid4().hex[:8]}",
                }
            )
            self._set_session_preview(session, assistant_full_text)

    async def resume_stream(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        interrupt_id: str,
        decision: Literal["approve", "reject", "auto_approve_all"] | str,
    ) -> AsyncIterator[dict[str, Any]]:
        session = self._get_session(thread_id)
        session.assistant_id = assistant_id

        pending = self._pending_approvals.get(thread_id)
        action_reqs: list[dict[str, Any]] = []
        if pending and pending.action_requests:
            action_reqs = pending.action_requests

        if decision == "auto_approve_all":
            session.auto_approve = True
            decision_type = "approve"
        else:
            decision_type = str(decision)

        decisions = [{"type": decision_type} for _ in action_reqs] or [{"type": decision_type}]
        stream_input: Command = Command(resume={"decisions": decisions})

        agent = self._get_agent(model_name=session.model_name)
        config = self._build_config(thread_id=thread_id, assistant_id=assistant_id)

        assistant_full_text = ""
        async for ev in self._stream_until_done_or_approval(
            agent=agent,
            config=config,
            session=session,
            stream_input=stream_input,
        ):
            if ev.get("type") == "text_delta":
                assistant_full_text += str(ev.get("text") or "")
            yield ev

        if assistant_full_text.strip():
            session.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_full_text,
                    "id": f"msg_asst_{uuid.uuid4().hex[:8]}",
                }
            )
            self._set_session_preview(session, assistant_full_text)

    async def _stream_until_done_or_approval(
        self,
        *,
        agent: Any,
        config: dict[str, Any],
        session: SessionState,
        stream_input: dict[str, Any] | Command,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "status", "status": "thinking", "message": "Agent is thinking..."}
        yield {"type": "thread_id", "thread_id": session.thread_id}

        tool_call_args: dict[str, dict[str, Any]] = {}
        tool_call_names: dict[str, str] = {}
        tool_call_buffers: dict[str | int, dict[str, Any]] = {}
        displayed_tool_ids: set[str] = set()
        assistant_seen: str = ""

        while True:
            interrupt_values: list[tuple[str, dict[str, Any]]] = []

            async for chunk in agent.astream(
                stream_input,
                stream_mode=["messages", "updates"],
                subgraphs=True,
                config=config,
                durability="exit",
            ):
                if not isinstance(chunk, tuple) or len(chunk) != 3:
                    continue
                namespace, mode, data = chunk
                ns_key = tuple(namespace) if namespace else ()
                is_main = ns_key == ()

                if mode == "updates":
                    if not isinstance(data, dict):
                        continue
                    if "__interrupt__" in data:
                        interrupts: list[Interrupt] = data.get("__interrupt__") or []
                        for it in interrupts:
                            try:
                                validated = _HITL_REQUEST_ADAPTER.validate_python(it.value)
                            except Exception:
                                validated = it.value
                            if isinstance(validated, dict):
                                interrupt_values.append((str(it.id), validated))
                    continue

                if mode != "messages":
                    continue
                if not is_main:
                    continue
                if not isinstance(data, tuple) or len(data) != 2:
                    continue

                message, _meta = data

                if isinstance(message, HumanMessage):
                    continue

                if isinstance(message, ToolMessage):
                    tool_call_id = getattr(message, "tool_call_id", None)
                    status = getattr(message, "status", "success") or "success"
                    name = getattr(message, "name", "") or tool_call_names.get(str(tool_call_id or ""), "")
                    args = tool_call_args.get(str(tool_call_id or ""), {})

                    yield {
                        "type": "tool_result",
                        "tool_name": name,
                        "tool_call_id": tool_call_id,
                        "status": status,
                        "output": _stringify_tool_content(message.content),
                        "args": args,
                    }
                    yield {"type": "status", "status": "thinking", "message": "Agent is thinking..."}
                    continue

                blocks = getattr(message, "content_blocks", None)
                if blocks is None:
                    # Tool calls (non-streaming)
                    if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
                        for tc in message.tool_calls:
                            tc_id = tc.get("id")
                            tc_name = tc.get("name")
                            tc_args = tc.get("args") or {}
                            if tc_id and tc_name and tc_id not in displayed_tool_ids:
                                displayed_tool_ids.add(tc_id)
                                if isinstance(tc_args, dict):
                                    tool_call_args[tc_id] = tc_args
                                tool_call_names[tc_id] = tc_name
                                yield {
                                    "type": "status",
                                    "status": "executing",
                                    "message": _format_status_message(tc_name, tc_args if isinstance(tc_args, dict) else None),
                                }
                                yield {"type": "tool_call", "tool_name": tc_name, "tool_call_id": tc_id, "args": tc_args}

                    # Text (non-block streaming)
                    content = getattr(message, "content", None)
                    if isinstance(content, str) and content:
                        if content.startswith(assistant_seen):
                            delta = content[len(assistant_seen) :]
                        else:
                            delta = content
                        if delta:
                            assistant_seen = content
                            yield {"type": "text_delta", "text": delta}
                    continue

                for block in blocks:
                    btype = block.get("type")
                    if btype == "text":
                        text = block.get("text", "")
                        if text:
                            yield {"type": "text_delta", "text": text}
                    elif btype == "reasoning_details":
                        reasoning_text = block.get("text", "")
                        if reasoning_text:
                            yield {"type": "reasoning_delta", "text": reasoning_text}
                    elif btype in ("tool_call_chunk", "tool_call"):
                        chunk_name = block.get("name")
                        chunk_args = block.get("args")
                        chunk_id = block.get("id")
                        chunk_index = block.get("index")

                        key: str | int
                        if chunk_index is not None:
                            key = chunk_index
                        elif chunk_id is not None:
                            key = chunk_id
                        else:
                            key = f"unknown-{len(tool_call_buffers)}"

                        buffer = tool_call_buffers.setdefault(
                            key,
                            {"name": None, "id": None, "args_parts": []},
                        )
                        if chunk_name:
                            buffer["name"] = chunk_name
                        if chunk_id:
                            buffer["id"] = chunk_id

                        parsed_args: Any = None
                        if isinstance(chunk_args, dict):
                            parsed_args = chunk_args
                        elif isinstance(chunk_args, str):
                            parts: list[str] = buffer.setdefault("args_parts", [])
                            if chunk_args and (not parts or chunk_args != parts[-1]):
                                parts.append(chunk_args)
                            try:
                                parsed_args = json.loads("".join(parts))
                            except json.JSONDecodeError:
                                parsed_args = None

                        if buffer.get("name") and buffer.get("id") and isinstance(parsed_args, dict):
                            tc_name = str(buffer["name"])
                            tc_id = str(buffer["id"])
                            if tc_id not in displayed_tool_ids:
                                displayed_tool_ids.add(tc_id)
                                tool_call_args[tc_id] = parsed_args
                                tool_call_names[tc_id] = tc_name
                                yield {
                                    "type": "status",
                                    "status": "executing",
                                    "message": _format_status_message(tc_name, parsed_args),
                                }
                                yield {"type": "tool_call", "tool_name": tc_name, "tool_call_id": tc_id, "args": parsed_args}
                            tool_call_buffers.pop(key, None)

            if interrupt_values:
                # Store the first interrupt's action_requests for resume.
                # DeepAgents v0.3.8 resume uses a single decisions list.
                # We still send interrupt_id to the UI for display/compat.
                interrupt_id, payload = interrupt_values[0]
                action_reqs = payload.get("action_requests", []) if isinstance(payload, dict) else []
                if not isinstance(action_reqs, list):
                    action_reqs = []
                self._pending_approvals[session.thread_id] = PendingApproval(
                    interrupt_id=interrupt_id,
                    action_requests=action_reqs,
                )

                if session.auto_approve:
                    decisions = [{"type": "approve"} for _ in action_reqs] or [{"type": "approve"}]
                    stream_input = Command(resume={"decisions": decisions})
                    continue

                approvals_payload = [{"interrupt_id": interrupt_id, "action_requests": action_reqs}]
                yield {"type": "approval_required", "approvals": approvals_payload, "auto_approve": session.auto_approve}
                yield {"type": "done", "approval_required": True, "auto_approve": session.auto_approve}
                return

            yield {"type": "status", "status": "done", "message": ""}
            yield {"type": "done", "approval_required": False, "auto_approve": session.auto_approve}
            return


async def _readline() -> str:
    return await asyncio.to_thread(sys.stdin.readline)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[ag3nt-daemon] %(message)s", stream=sys.stderr)
    logging.info("AG3NT daemon starting")

    runtime = AgentRuntime()

    while True:
        line = await _readline()
        if not line:
            return
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        try:
            if method == "health":
                result = {"status": "ok"}
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "clear_caches":
                result = runtime.clear_caches()
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "list_threads":
                agent_name = params.get("agent_name")
                limit = int(params.get("limit") or 50)
                result = runtime.list_threads(agent_name, limit=limit)
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "delete_thread":
                thread_id = str(params.get("thread_id") or "")
                if not thread_id:
                    raise ValueError("delete_thread requires thread_id")
                deleted = runtime.delete_thread(thread_id)
                result = {"deleted": deleted, "thread_id": thread_id}
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "get_thread_messages":
                thread_id = str(params.get("thread_id") or "")
                limit = int(params.get("limit") or 50)
                if not thread_id:
                    raise ValueError("get_thread_messages requires thread_id")
                result = runtime.get_thread_messages(thread_id, limit=limit)
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "list_tools":
                model_name = params.get("model")
                result = runtime.list_tools(model_name=str(model_name) if model_name else None)
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "list_agents":
                result = runtime.list_agents()
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "chat":
                result = await runtime.chat(params)
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "resume":
                result = await runtime.resume(params)
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "chat_stream":
                thread_id = params.get("thread_id") or _generate_thread_id()
                assistant_id = params.get("assistant_id") or "agent"
                message = params.get("message") or ""
                auto_approve = bool(params.get("auto_approve", False))
                model = params.get("model")
                attachments = params.get("attachments")
                ui_context = params.get("ui_context")

                async for event in runtime.chat_stream(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    message=message,
                    auto_approve=auto_approve,
                    model=model,
                    attachments=attachments,
                    ui_context=ui_context,
                ):
                    sys.stdout.write(json.dumps({"id": req_id, "ok": True, "event": event}) + "\n")
                    sys.stdout.flush()
                continue

            if method == "mcp_test_server":
                server_id = params.get("server_id") or params.get("id") or params.get("server") or ""
                result = await runtime.mcp_test_server(str(server_id))
                sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
                sys.stdout.flush()
                continue

            if method == "resume_stream":
                thread_id = params.get("thread_id")
                assistant_id = params.get("assistant_id") or "agent"
                interrupt_id = params.get("interrupt_id") or ""
                decision = params.get("decision")
                if not thread_id or not decision:
                    raise ValueError("resume_stream requires thread_id and decision")

                async for event in runtime.resume_stream(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    interrupt_id=str(interrupt_id),
                    decision=str(decision),
                ):
                    sys.stdout.write(json.dumps({"id": req_id, "ok": True, "event": event}) + "\n")
                    sys.stdout.flush()
                continue

            raise ValueError(f"Unknown method: {method}")
        except Exception as e:
            sys.stdout.write(
                json.dumps(
                    {
                        "id": req_id,
                        "ok": False,
                        "error": {
                            "message": str(e),
                            "type": e.__class__.__name__,
                            "trace": traceback.format_exc(limit=30),
                        },
                    }
                )
                + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
