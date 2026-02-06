"""
Browser Bridge - Connects agent browser tools to the live browser session.

This singleton bridges the agent's browser tool calls to the user-visible
browser session running in browser_ws_server.py via WebSocket. When a live
session is available, agent actions (navigate, click, type, screenshot, etc.)
are routed through the same browser the user sees, enabling co-browsing.

When no live session is connected, the bridge reports `is_live = False` and
callers (browser_tool.py) fall back to a standalone headless Playwright
instance.
"""

import asyncio
import base64
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("ag3nt.browser_bridge")

# Default WebSocket URL for the local browser server
DEFAULT_WS_URL = os.environ.get("BROWSER_BRIDGE_WS_URL", "ws://localhost:8765")

# Timeout for request/response pairs (screenshot, get_content)
REQUEST_TIMEOUT = float(os.environ.get("BROWSER_BRIDGE_TIMEOUT", "15"))


class BrowserBridge:
    """Singleton bridge connecting agent tools to the live browser session."""

    _instance: Optional["BrowserBridge"] = None

    def __init__(self):
        self._ws = None
        self._ws_url: Optional[str] = None
        self._connected = False
        self._pending: dict[str, asyncio.Future] = {}
        self._request_id = 0
        self._recv_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> "BrowserBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def is_live(self) -> bool:
        """True when connected to a live browser session."""
        return self._connected and self._ws is not None

    async def connect_live(self, ws_url: Optional[str] = None) -> bool:
        """Connect to an existing live browser session.

        Args:
            ws_url: WebSocket URL of the browser_ws_server. Defaults to
                    ws://localhost:8765 or BROWSER_BRIDGE_WS_URL env var.

        Returns:
            True if connected successfully.
        """
        url = ws_url or DEFAULT_WS_URL
        if self._connected and self._ws_url == url:
            return True

        # Disconnect previous if any
        await self.disconnect()

        try:
            import websockets
            self._ws = await websockets.connect(
                url,
                max_size=8 * 1024 * 1024,
                open_timeout=3,       # fail fast when server isn't running
                ping_interval=20,
                ping_timeout=20,
            )
            self._ws_url = url
            self._connected = True

            # Start background receiver
            self._recv_task = asyncio.create_task(self._recv_loop())

            logger.info(f"BrowserBridge connected to {url}")
            return True
        except Exception as e:
            logger.warning(f"BrowserBridge connect failed: {e}")
            self._connected = False
            self._ws = None
            return False

    async def disconnect(self):
        """Disconnect from the live session."""
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recv_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        # Cancel all pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        logger.info("BrowserBridge disconnected")

    async def _ensure_connected(self):
        """Ensure we're connected, auto-connecting if possible."""
        if not self.is_live:
            await self.connect_live()
        if not self.is_live:
            raise ConnectionError("BrowserBridge is not connected to a live session")

    # ------------------------------------------------------------------
    # Background receiver
    # ------------------------------------------------------------------

    async def _recv_loop(self):
        """Receive messages from the WebSocket and dispatch responses."""
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    # Binary frame data — ignore in bridge context
                    continue
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = msg.get("type", "")

                # Match response to pending request
                req_id = msg.get("_req_id")
                if req_id and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(msg)
                    continue

                # Match by response type conventions
                if msg_type == "screenshot_result":
                    self._resolve_pending_by_type("screenshot", msg)
                elif msg_type == "content_result":
                    self._resolve_pending_by_type("get_content", msg)
                elif msg_type == "navigated":
                    self._resolve_pending_by_type("navigate", msg)
                elif msg_type == "pong":
                    pass  # heartbeat
                elif msg_type == "error":
                    # Resolve any pending request with the error
                    for key in list(self._pending.keys()):
                        fut = self._pending.pop(key)
                        if not fut.done():
                            fut.set_result(msg)
                        break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"BrowserBridge recv loop ended: {e}")
        finally:
            self._connected = False

    def _resolve_pending_by_type(self, prefix: str, msg: dict):
        """Resolve the first pending future matching a prefix."""
        for key in list(self._pending.keys()):
            if key.startswith(prefix):
                fut = self._pending.pop(key)
                if not fut.done():
                    fut.set_result(msg)
                return

    # ------------------------------------------------------------------
    # Send + request/response helpers
    # ------------------------------------------------------------------

    async def _send(self, msg: dict):
        """Send a JSON message to the live browser session."""
        await self._ensure_connected()
        await self._ws.send(json.dumps(msg))

    async def _request(self, msg_type: str, msg: dict, timeout: float = REQUEST_TIMEOUT) -> dict:
        """Send a message and wait for a matching response."""
        self._request_id += 1
        req_id = f"{msg_type}_{self._request_id}"
        msg["_req_id"] = req_id

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        await self._send(msg)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"BrowserBridge request '{msg_type}' timed out after {timeout}s")

    async def _send_agent_action(self, action: str, **kwargs):
        """Broadcast an agent action to the UI for cursor overlay."""
        try:
            await self._send({
                "type": "agent_action",
                "action": action,
                **kwargs,
            })
        except Exception:
            pass  # non-critical

    # ------------------------------------------------------------------
    # High-level browser operations
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> str:
        """Navigate to a URL in the live browser."""
        await self._send_agent_action("navigate", url=url)
        resp = await self._request("navigate", {"type": "goto", "url": url}, timeout=30)
        if resp.get("type") == "error":
            return f"Error navigating to {url}: {resp.get('message', 'unknown error')}"
        final_url = resp.get("url", url)
        title = resp.get("title", "")
        return f"Navigated to: {title} ({final_url})"

    async def click(self, x: int = 0, y: int = 0, selector: Optional[str] = None) -> str:
        """Click at coordinates or on a selector.

        When connected to the live session, selector-based clicks are converted
        to coordinate clicks by first querying the element's bounding box.
        For simplicity, we send a click at the center of the page if no
        coordinates or selector are provided.
        """
        if selector:
            # For selector clicks via the WS protocol, we send a click message
            # with the selector. The server's handle_input will use page.click().
            await self._send_agent_action("click", selector=selector)
            await self._send({"type": "click_selector", "selector": selector})
            # Give the page time to process
            await asyncio.sleep(0.3)
            return f"Clicked element: {selector}"
        else:
            await self._send_agent_action("click", x=x, y=y)
            await self._send({"type": "click", "x": x, "y": y})
            return f"Clicked at ({x}, {y})"

    async def type_text(self, text: str, selector: Optional[str] = None) -> str:
        """Type text, optionally into a specific selector."""
        if selector:
            await self._send_agent_action("type", selector=selector)
            # Click the selector first to focus it, then type
            await self._send({"type": "click_selector", "selector": selector})
            await asyncio.sleep(0.2)
        await self._send_agent_action("type", text=text[:50])
        await self._send({"type": "type", "text": text})
        if selector:
            return f"Filled '{selector}' with: {text}"
        return f"Typed: {text}"

    async def screenshot(self, save_path: Optional[str] = None) -> str:
        """Request a PNG screenshot from the live browser."""
        await self._send_agent_action("screenshot")
        resp = await self._request("screenshot", {"type": "screenshot"}, timeout=10)
        if resp.get("type") == "error":
            return f"Screenshot error: {resp.get('message', 'unknown')}"

        b64_data = resp.get("data", "")
        if save_path and b64_data:
            img_bytes = base64.b64decode(b64_data)
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            return f"Screenshot saved to: {save_path}"
        return f"Screenshot captured (base64): {b64_data[:100]}... ({len(b64_data)} chars total)"

    async def get_content(self, selector: Optional[str] = None) -> str:
        """Extract text content from the live browser page."""
        msg = {"type": "get_content"}
        if selector:
            msg["selector"] = selector
        resp = await self._request("get_content", msg, timeout=10)
        if resp.get("type") == "error":
            return f"Get content error: {resp.get('message', 'unknown')}"
        return resp.get("text", "")
