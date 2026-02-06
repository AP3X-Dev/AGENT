"""Gateway client and discovery for AG3NT TUI."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from .config import DEFAULT_PORTS


def discover_gateway_url() -> str:
    """Discover the Gateway URL by:
    1. Checking AG3NT_GATEWAY_URL environment variable
    2. Reading from ~/.ag3nt/runtime.json (written by start.ps1)
    3. Probing default ports for a live Gateway
    """
    # 1. Environment variable takes precedence
    env_url = os.getenv("AG3NT_GATEWAY_URL")
    if env_url:
        return env_url

    # 2. Try to read from runtime.json
    runtime_path = Path.home() / ".ag3nt" / "runtime.json"
    try:
        if runtime_path.exists():
            content = runtime_path.read_text(encoding="utf-8")
            runtime = json.loads(content)
            gateway_url = runtime.get("gatewayUrl")
            if gateway_url:
                # Verify the Gateway is actually responding
                try:
                    resp = httpx.get(f"{gateway_url}/api/health", timeout=2.0)
                    if resp.status_code == 200:
                        return gateway_url
                except Exception:
                    # Gateway from runtime.json is not responding, continue to probe
                    pass
    except Exception:
        # Ignore errors reading runtime.json
        pass

    # 3. Probe default ports
    for port in DEFAULT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            resp = httpx.get(f"{url}/api/health", timeout=1.0)
            if resp.status_code == 200:
                return url
        except Exception:
            # Port not responding, try next
            pass

    # Fallback to default
    return "http://127.0.0.1:18789"


class GatewayClient:
    """HTTP and WebSocket client for AG3NT Gateway."""

    def __init__(self, url: str | None = None, timeout: float = 300.0) -> None:
        """Initialize gateway client.

        Args:
            url: Gateway URL (auto-discovered if not provided)
            timeout: Request timeout in seconds (default 5 minutes for agent responses)
        """
        self.url = url or discover_gateway_url()
        self.timeout = timeout
        self._http_client: httpx.AsyncClient | None = None
        self._ws = None
        self._event_handlers: dict[str, list[Callable]] = {}

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.url,
                timeout=self.timeout,
            )
        return self._http_client

    async def close(self) -> None:
        """Close all connections."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    # HTTP API methods
    async def health(self) -> dict[str, Any]:
        """Check gateway health."""
        resp = await self.http_client.get("/api/health")
        resp.raise_for_status()
        return resp.json()

    async def get_node_status(self) -> dict[str, Any]:
        """Get node status information."""
        resp = await self.http_client.get("/api/nodes/status")
        resp.raise_for_status()
        return resp.json()

    async def get_nodes(self) -> list[dict[str, Any]]:
        """Get list of connected nodes."""
        resp = await self.http_client.get("/api/nodes")
        resp.raise_for_status()
        data = resp.json()
        return data.get("nodes", [])

    async def chat(self, text: str, session_id: str) -> dict[str, Any]:
        """Send chat message and get response."""
        resp = await self.http_client.post(
            "/api/chat",
            json={"text": text, "session_id": session_id},
        )
        return resp.json()

    async def chat_stream(self, text: str, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Stream chat response chunks via SSE.

        Yields dicts with keys:
            - type: "chunk" | "tool_start" | "tool_end" | "complete" | "error"
            - content: text content (for chunk)
            - tool_name, tool_args, tool_call_id (for tool events)
        """
        async with self.http_client.stream(
            "POST",
            "/api/chat/stream",
            json={"text": text, "session_id": session_id},
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        yield data
                    except json.JSONDecodeError:
                        continue

    async def approve_session(
        self, session_id: str, code: str, approved: bool = True
    ) -> dict[str, Any]:
        """Approve or reject a session."""
        resp = await self.http_client.post(
            f"/api/sessions/{session_id}/approve",
            json={"approved": approved, "code": code},
        )
        return resp.json()

    async def cancel_request(self, session_id: str, request_id: str) -> dict[str, Any]:
        """Cancel a running request."""
        resp = await self.http_client.post(
            f"/api/sessions/{session_id}/cancel",
            json={"request_id": request_id},
        )
        return resp.json()

    async def approve_tool(
        self,
        session_id: str,
        tool_call_id: str,
        approved: bool = True,
    ) -> dict[str, Any]:
        """Approve or reject a tool execution.

        Args:
            session_id: Session ID
            tool_call_id: Tool call ID to approve/reject
            approved: True to approve, False to reject

        Returns:
            Response from gateway
        """
        resp = await self.http_client.post(
            f"/api/sessions/{session_id}/tools/{tool_call_id}/approve",
            json={"approved": approved},
        )
        return resp.json()

    async def set_auto_approve(
        self,
        session_id: str,
        enabled: bool,
        tool_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Set auto-approve mode for session.

        Args:
            session_id: Session ID
            enabled: True to enable auto-approve
            tool_names: Optional list of specific tools to auto-approve

        Returns:
            Response from gateway
        """
        resp = await self.http_client.post(
            f"/api/sessions/{session_id}/auto-approve",
            json={"enabled": enabled, "tools": tool_names},
        )
        return resp.json()

    # WebSocket methods
    async def connect_ws(self) -> None:
        """Establish WebSocket connection for real-time events."""
        try:
            import websockets
        except ImportError:
            return  # WebSocket support optional

        ws_url = self.url.replace("http", "ws") + "/ws"
        self._ws = await websockets.connect(ws_url)
        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self) -> None:
        """Listen for WebSocket events."""
        if self._ws is None:
            return
        try:
            async for message in self._ws:
                data = json.loads(message)
                event_type = data.get("type")
                for handler in self._event_handlers.get(event_type, []):
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            handler(data)
                    except Exception:
                        pass  # Don't let handler errors break the loop
        except Exception:
            pass  # Connection closed

    def on(self, event: str, handler: Callable) -> None:
        """Register event handler for WebSocket events.

        Args:
            event: Event type (e.g., "tool_start", "tool_end", "chunk")
            handler: Callback function (can be sync or async)
        """
        self._event_handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler: Callable) -> None:
        """Remove event handler."""
        handlers = self._event_handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)
