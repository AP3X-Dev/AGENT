"""
Browser Control Tool - Web automation using Playwright.

This tool provides web automation capabilities including navigation,
screenshots, clicking, form filling, and content extraction.

Uses BrowserBridge to route through the live browser session when available,
falling back to a standalone headless Playwright instance otherwise.
"""

import asyncio
import base64
import logging
import os as _os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Literal
from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.browser")

# ---------------------------------------------------------------------------
# Async helper: safely run coroutines from sync context inside an existing
# event loop (e.g. uvicorn).  Uses nest_asyncio when available.
# ---------------------------------------------------------------------------

_persistent_loop = None


def _run_async(coro):
    """Run an async coroutine from synchronous code, handling nested event loops.

    When called inside an already-running event loop (e.g. uvicorn), plain
    asyncio.run() raises RuntimeError.  This helper detects that situation and
    uses nest_asyncio to allow nested calls.

    When no event loop is running (standalone / CLI mode), a persistent loop is
    created and reused across calls so that long-lived async resources (like the
    BrowserBridge WebSocket connection and its recv_task) survive between tool
    invocations.
    """
    global _persistent_loop

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Inside an existing loop (e.g. uvicorn).  Use nest_asyncio.
        try:
            import nest_asyncio
            nest_asyncio.apply(loop)
            return loop.run_until_complete(coro)
        except ImportError:
            pass
        # Fallback: run in a separate thread with its own event loop.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)

    # No running loop — use a persistent loop so bridge connections survive
    # between tool calls.
    if _persistent_loop is None or _persistent_loop.is_closed():
        _persistent_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_persistent_loop)
    return _persistent_loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Bridge integration — lazy import to avoid circular deps
# ---------------------------------------------------------------------------

_bridge = None

def _get_bridge():
    """Lazily get the BrowserBridge singleton."""
    global _bridge
    if _bridge is None:
        try:
            from ag3nt_agent.browser_bridge import BrowserBridge
            _bridge = BrowserBridge.get_instance()
        except ImportError:
            logger.debug("BrowserBridge not available, using standalone Playwright")
    return _bridge


# Cooldown tracking for failed bridge connection attempts.
# Avoids retrying a dead WebSocket every tool call in headless mode.
_bridge_last_attempt: float = 0.0
_BRIDGE_RETRY_COOLDOWN = 30.0  # seconds before retrying after a failed connect


async def _try_bridge():
    """Get the bridge and attempt auto-connect if not already live.

    Returns the bridge if connected, None otherwise (caller should fall
    back to standalone headless Playwright).  Uses a cooldown so that
    repeated calls in headless mode (server not running) don't waste time
    on doomed connection attempts.
    """
    global _bridge_last_attempt

    bridge = _get_bridge()
    if bridge is None:
        return None

    # Already connected — fast path
    if bridge.is_live:
        return bridge

    # Cooldown: skip reconnect if we failed recently
    now = time.monotonic()
    if now - _bridge_last_attempt < _BRIDGE_RETRY_COOLDOWN:
        return None

    _bridge_last_attempt = now
    try:
        await bridge.connect_live()
    except Exception as e:
        logger.debug(f"Bridge auto-connect failed (headless fallback): {e}")

    if bridge.is_live:
        logger.info("Bridge connected — agent actions will appear in UI browser")
        return bridge
    return None


# ---------------------------------------------------------------------------
# Standalone Playwright fallback (used when bridge is not connected)
# Uses a persistent profile so logins/cookies survive across restarts.
# ---------------------------------------------------------------------------

_AGENT_PROFILE_DIR = _os.environ.get(
    "BROWSER_AGENT_PROFILE_DIR",
    _os.path.join(_os.path.expanduser("~"), ".ag3nt", "browser-profile-agent"),
)

_browser_instance = None   # unused with persistent context, kept for close()
_browser_context = None
_current_page = None
_playwright_instance = None


async def _get_browser():
    """Get or create the standalone browser with a persistent profile."""
    global _browser_instance, _browser_context, _current_page, _playwright_instance

    if _current_page is None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install it with: pip install playwright && playwright install chromium"
            )

        _os.makedirs(_AGENT_PROFILE_DIR, exist_ok=True)

        _playwright_instance = await async_playwright().start()
        _browser_context = await _playwright_instance.chromium.launch_persistent_context(
            _AGENT_PROFILE_DIR,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            chromium_sandbox=False,
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

        # Reuse existing page if the profile had one open, otherwise create
        if _browser_context.pages:
            _current_page = _browser_context.pages[0]
        else:
            _current_page = await _browser_context.new_page()

    return _current_page


# ---------------------------------------------------------------------------
# Browser server lifecycle management
# ---------------------------------------------------------------------------

_server_process: Optional[subprocess.Popen] = None

# Resolve the browser_ws_server.py script path relative to this file.
# browser_tool.py   -> apps/agent/ag3nt_agent/browser_tool.py
# browser_ws_server -> apps/ui/python/browser_ws_server.py
_THIS_DIR = Path(__file__).resolve().parent               # ag3nt_agent/
_PROJECT_ROOT = _THIS_DIR.parent.parent.parent            # repo root
_BROWSER_SERVER_SCRIPT = _PROJECT_ROOT / "apps" / "ui" / "python" / "browser_ws_server.py"
_BROWSER_SERVER_WD = _PROJECT_ROOT / "apps" / "ui"


def _is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Check whether a TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _start_browser_server(port: int = 8765) -> bool:
    """Start browser_ws_server.py as a background process if not already running.

    Returns True if the server is ready (already running or successfully started).
    """
    global _server_process

    if _is_port_open(port):
        logger.info(f"Browser server already running on port {port}")
        return True

    if not _BROWSER_SERVER_SCRIPT.exists():
        logger.warning(f"Browser server script not found: {_BROWSER_SERVER_SCRIPT}")
        return False

    env = {**_os.environ}
    env["BROWSER_WS_PORT"] = str(port)
    env["BROWSER_WS_HOST"] = "127.0.0.1"

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW

    logger.info(f"Starting browser server: {_BROWSER_SERVER_SCRIPT}")
    _server_process = subprocess.Popen(
        [sys.executable, str(_BROWSER_SERVER_SCRIPT)],
        cwd=str(_BROWSER_SERVER_WD),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    # Poll until the port opens (up to 20 seconds)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if _server_process.poll() is not None:
            logger.error("Browser server process exited unexpectedly")
            return False
        if _is_port_open(port):
            logger.info(f"Browser server ready on port {port}")
            return True
        time.sleep(0.5)

    logger.error("Browser server did not become ready in time")
    return False


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@tool
def browser_start_session(url: str = "https://www.google.com") -> str:
    """Start a live browser session visible in the Agent Browser UI.

    This launches the browser server (if not already running), connects
    the agent's browser tools to it, and navigates to the given URL.
    All subsequent browser_navigate / browser_click / browser_fill calls
    will execute in this live session, visible to the user in the
    Agent Browser UI module.

    Use this when the user explicitly asks to use the agent browser
    or when they want to watch the agent browse.

    Args:
        url: The URL to open (default: https://www.google.com)

    Returns:
        Status message indicating whether the session started successfully.

    Example:
        browser_start_session("https://duckduckgo.com")
    """
    global _bridge_last_attempt

    async def _start():
        global _bridge_last_attempt

        # 1. Determine the port from the bridge's default URL
        from ag3nt_agent.browser_bridge import DEFAULT_WS_URL
        port = 8765
        try:
            port = int(DEFAULT_WS_URL.split(":")[-1].rstrip("/"))
        except (ValueError, IndexError):
            pass

        # 2. Start the server if not running
        if not _is_port_open(port):
            ok = _start_browser_server(port)
            if not ok:
                return "Failed to start browser server. Falling back to headless mode."

        # 3. Reset cooldown and connect bridge
        _bridge_last_attempt = 0.0
        bridge = _get_bridge()
        if bridge is None:
            return "BrowserBridge module not available."

        connected = await bridge.connect_live()
        if not connected:
            return "Browser server is running but bridge failed to connect."

        # 4. Navigate to URL
        result = await bridge.navigate(url)
        return f"Live browser session started. {result}\nAgent actions are now visible in the Agent Browser UI."

    try:
        return _run_async(_start())
    except Exception as e:
        return f"Error starting browser session: {str(e)}"


@tool
def browser_navigate(url: str, wait_until: Literal["load", "domcontentloaded", "networkidle"] = "load") -> str:
    """Navigate to a URL in the browser.

    Args:
        url: The URL to navigate to (must include http:// or https://)
        wait_until: When to consider navigation complete:
            - "load": Wait for load event (default)
            - "domcontentloaded": Wait for DOMContentLoaded event
            - "networkidle": Wait for network to be idle

    Returns:
        Success message with the page title

    Example:
        browser_navigate("https://example.com")
    """
    async def _navigate():
        bridge = await _try_bridge()
        if bridge:
            return await bridge.navigate(url)

        page = await _get_browser()
        await page.goto(url, wait_until=wait_until, timeout=30000)
        title = await page.title()
        return f"Navigated to: {title} ({url})"

    try:
        return _run_async(_navigate())
    except Exception as e:
        return f"Error navigating to {url}: {str(e)}"


@tool
def browser_screenshot(full_page: bool = False, save_path: Optional[str] = None) -> str:
    """Take a screenshot of the current page.

    Args:
        full_page: If True, capture the entire scrollable page. If False, capture viewport only.
        save_path: Optional path to save the screenshot (e.g., "screenshot.png"). If not provided, returns base64.

    Returns:
        If save_path provided: Success message with file path
        If no save_path: Base64-encoded PNG image data

    Example:
        browser_screenshot(full_page=True, save_path="page.png")
    """
    async def _screenshot():
        bridge = await _try_bridge()
        if bridge:
            return await bridge.screenshot(save_path=save_path)

        page = await _get_browser()
        screenshot_bytes = await page.screenshot(full_page=full_page, type="png")

        if save_path:
            with open(save_path, "wb") as f:
                f.write(screenshot_bytes)
            return f"Screenshot saved to: {save_path}"
        else:
            b64_data = base64.b64encode(screenshot_bytes).decode()
            return f"Screenshot captured (base64): {b64_data[:100]}... ({len(b64_data)} chars total)"

    try:
        return _run_async(_screenshot())
    except Exception as e:
        return f"Error taking screenshot: {str(e)}"


@tool
def browser_click(selector: str, timeout: int = 5000) -> str:
    """Click an element on the page.

    Args:
        selector: CSS selector or text selector for the element to click
        timeout: Maximum time to wait for element in milliseconds (default: 5000)

    Returns:
        Success message

    Example:
        browser_click("button.submit")
        browser_click("text=Sign In")
    """
    async def _click():
        bridge = await _try_bridge()
        if bridge:
            return await bridge.click(selector=selector)

        page = await _get_browser()
        await page.click(selector, timeout=timeout)
        return f"Clicked element: {selector}"

    try:
        return _run_async(_click())
    except Exception as e:
        return f"Error clicking {selector}: {str(e)}"


@tool
def browser_fill(selector: str, text: str, timeout: int = 5000) -> str:
    """Fill a form field with text.

    Args:
        selector: CSS selector for the input field
        text: Text to fill into the field
        timeout: Maximum time to wait for element in milliseconds (default: 5000)

    Returns:
        Success message

    Example:
        browser_fill("input[name='email']", "user@example.com")
    """
    async def _fill():
        bridge = await _try_bridge()
        if bridge:
            return await bridge.type_text(text, selector=selector)

        page = await _get_browser()
        await page.fill(selector, text, timeout=timeout)
        return f"Filled '{selector}' with: {text}"

    try:
        return _run_async(_fill())
    except Exception as e:
        return f"Error filling {selector}: {str(e)}"


@tool
def browser_get_content(selector: Optional[str] = None) -> str:
    """Extract text content from the page or a specific element.

    Args:
        selector: Optional CSS selector. If provided, extracts text from that element.
                 If not provided, extracts all text from the page body.

    Returns:
        The extracted text content

    Example:
        browser_get_content()  # Get all page text
        browser_get_content("article.main-content")  # Get specific element text
    """
    async def _get_content():
        bridge = await _try_bridge()
        if bridge:
            return await bridge.get_content(selector=selector)

        page = await _get_browser()
        if selector:
            element = await page.query_selector(selector)
            if element:
                return await element.inner_text()
            else:
                return f"Error: Element not found: {selector}"
        else:
            return await page.inner_text("body")

    try:
        return _run_async(_get_content())
    except Exception as e:
        return f"Error getting content: {str(e)}"


@tool
def browser_wait_for(selector: str, state: Literal["attached", "detached", "visible", "hidden"] = "visible", timeout: int = 5000) -> str:
    """Wait for an element to reach a specific state.

    Args:
        selector: CSS selector for the element
        state: The state to wait for:
            - "attached": Element is attached to DOM
            - "detached": Element is not attached to DOM
            - "visible": Element is visible (default)
            - "hidden": Element is hidden
        timeout: Maximum time to wait in milliseconds (default: 5000)

    Returns:
        Success message

    Example:
        browser_wait_for(".loading-spinner", state="hidden")
    """
    async def _wait():
        # wait_for is not supported via bridge — always use standalone
        page = await _get_browser()
        await page.wait_for_selector(selector, state=state, timeout=timeout)
        return f"Element '{selector}' reached state: {state}"

    try:
        return _run_async(_wait())
    except Exception as e:
        return f"Error waiting for {selector}: {str(e)}"


@tool
def browser_close() -> str:
    """Close the browser and clean up resources.

    Returns:
        Success message
    """
    global _browser_instance, _browser_context, _current_page, _playwright_instance
    global _server_process

    async def _close():
        global _browser_instance, _browser_context, _current_page, _playwright_instance

        # Disconnect bridge if live
        bridge = _get_bridge()  # don't auto-connect just to disconnect
        if bridge and bridge.is_live:
            await bridge.disconnect()

        if _browser_context:
            # Closing persistent context flushes cookies/storage to disk
            await _browser_context.close()
            _browser_context = None
            _browser_instance = None
            _current_page = None
            return "Browser closed successfully (profile saved)"
        return "Browser was not open"

    try:
        result = _run_async(_close())
    except Exception as e:
        result = f"Error closing browser: {str(e)}"

    # Terminate server process if we started it
    if _server_process is not None:
        try:
            _server_process.terminate()
            _server_process.wait(timeout=5)
            logger.info("Browser server process terminated")
        except Exception as e:
            logger.debug(f"Server process cleanup: {e}")
        _server_process = None
        result += "\nBrowser server stopped."

    return result


def get_browser_tools():
    """Get all browser control tools for integration into the agent.

    Returns:
        List of browser control tools
    """
    return [
        browser_start_session,
        browser_navigate,
        browser_screenshot,
        browser_click,
        browser_fill,
        browser_get_content,
        browser_wait_for,
        browser_close,
    ]
