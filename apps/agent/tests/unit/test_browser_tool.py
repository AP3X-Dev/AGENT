"""Tests for browser automation tools."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from ag3nt_agent.browser_tool import (
    browser_navigate,
    browser_screenshot,
    browser_click,
    browser_fill,
    browser_get_content,
    browser_wait_for,
    browser_close,
    get_browser_tools,
)


class TestBrowserTools:
    """Test suite for browser automation tools."""

    def test_get_browser_tools_returns_all_tools(self):
        """Test that get_browser_tools returns all 7 tools."""
        tools = get_browser_tools()
        assert len(tools) == 7
        
        tool_names = [tool.name for tool in tools]
        expected_names = [
            "browser_navigate",
            "browser_screenshot",
            "browser_click",
            "browser_fill",
            "browser_get_content",
            "browser_wait_for",
            "browser_close",
        ]
        
        for expected_name in expected_names:
            assert expected_name in tool_names

    def test_browser_tools_have_descriptions(self):
        """Test that all browser tools have descriptions."""
        tools = get_browser_tools()
        
        for tool in tools:
            assert tool.description is not None
            assert len(tool.description) > 0

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    @patch('ag3nt_agent.browser_tool._get_browser')
    def test_browser_navigate_success(self, mock_get_browser, mock_asyncio_run):
        """Test successful navigation."""
        # Mock the async function to return a success message
        mock_asyncio_run.return_value = "Navigated to: Example Domain (https://example.com)"
        
        result = browser_navigate.invoke({"url": "https://example.com"})
        
        assert "Navigated to" in result
        assert "example.com" in result
        mock_asyncio_run.assert_called_once()

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_navigate_error_handling(self, mock_asyncio_run):
        """Test navigation error handling."""
        mock_asyncio_run.side_effect = Exception("Network error")
        
        result = browser_navigate.invoke({"url": "https://invalid-url"})
        
        assert "Error" in result
        assert "Network error" in result

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_screenshot_success(self, mock_asyncio_run):
        """Test successful screenshot capture."""
        mock_asyncio_run.return_value = "Screenshot saved to: test.png"
        
        result = browser_screenshot.invoke({
            "full_page": True,
            "save_path": "test.png"
        })
        
        assert "Screenshot" in result
        mock_asyncio_run.assert_called_once()

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_click_success(self, mock_asyncio_run):
        """Test successful element click."""
        mock_asyncio_run.return_value = "Clicked: button.submit"
        
        result = browser_click.invoke({"selector": "button.submit"})
        
        assert "Clicked" in result
        mock_asyncio_run.assert_called_once()

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_fill_success(self, mock_asyncio_run):
        """Test successful form fill."""
        mock_asyncio_run.return_value = "Filled 'input[name=\"email\"]' with: test@example.com"
        
        result = browser_fill.invoke({
            "selector": "input[name='email']",
            "text": "test@example.com"
        })
        
        assert "Filled" in result
        assert "test@example.com" in result
        mock_asyncio_run.assert_called_once()

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_get_content_success(self, mock_asyncio_run):
        """Test successful content extraction."""
        mock_asyncio_run.return_value = "Page content here"
        
        result = browser_get_content.invoke({})
        
        assert isinstance(result, str)
        mock_asyncio_run.assert_called_once()

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_wait_for_success(self, mock_asyncio_run):
        """Test successful wait for element."""
        mock_asyncio_run.return_value = "Element '.loading' reached state: hidden"
        
        result = browser_wait_for.invoke({
            "selector": ".loading",
            "state": "hidden"
        })
        
        assert "Element" in result
        assert "hidden" in result
        mock_asyncio_run.assert_called_once()

    @patch('ag3nt_agent.browser_tool.asyncio.run')
    def test_browser_close_success(self, mock_asyncio_run):
        """Test successful browser close."""
        mock_asyncio_run.return_value = "Browser closed successfully"
        
        result = browser_close.invoke({})
        
        assert "closed" in result.lower()
        mock_asyncio_run.assert_called_once()

