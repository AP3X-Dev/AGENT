"""
Browser Control Tool - Web automation using Playwright.

This tool provides web automation capabilities including navigation,
screenshots, clicking, form filling, and content extraction.
"""

import asyncio
import base64
from typing import Optional, Literal
from langchain_core.tools import tool


# Global browser instance (lazy-loaded)
_browser_instance = None
_browser_context = None
_current_page = None


async def _get_browser():
    """Get or create the browser instance."""
    global _browser_instance, _browser_context, _current_page

    if _browser_instance is None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install it with: pip install playwright && playwright install chromium"
            )

        playwright = await async_playwright().start()
        _browser_instance = await playwright.chromium.launch(headless=True)
        _browser_context = await _browser_instance.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        _current_page = await _browser_context.new_page()

    return _current_page


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
        page = await _get_browser()
        await page.goto(url, wait_until=wait_until, timeout=30000)
        title = await page.title()
        return f"Navigated to: {title} ({url})"

    try:
        return asyncio.run(_navigate())
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
        return asyncio.run(_screenshot())
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
        page = await _get_browser()
        await page.click(selector, timeout=timeout)
        return f"Clicked element: {selector}"

    try:
        return asyncio.run(_click())
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
        page = await _get_browser()
        await page.fill(selector, text, timeout=timeout)
        return f"Filled '{selector}' with: {text}"

    try:
        return asyncio.run(_fill())
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
        return asyncio.run(_get_content())
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
        page = await _get_browser()
        await page.wait_for_selector(selector, state=state, timeout=timeout)
        return f"Element '{selector}' reached state: {state}"

    try:
        return asyncio.run(_wait())
    except Exception as e:
        return f"Error waiting for {selector}: {str(e)}"


@tool
def browser_close() -> str:
    """Close the browser and clean up resources.

    Returns:
        Success message
    """
    global _browser_instance, _browser_context, _current_page

    async def _close():
        global _browser_instance, _browser_context, _current_page
        if _browser_instance:
            await _browser_instance.close()
            _browser_instance = None
            _browser_context = None
            _current_page = None
            return "Browser closed successfully"
        return "Browser was not open"

    try:
        return asyncio.run(_close())
    except Exception as e:
        return f"Error closing browser: {str(e)}"


def get_browser_tools():
    """Get all browser control tools for integration into the agent.

    Returns:
        List of browser control tools
    """
    return [
        browser_navigate,
        browser_screenshot,
        browser_click,
        browser_fill,
        browser_get_content,
        browser_wait_for,
        browser_close,
    ]

