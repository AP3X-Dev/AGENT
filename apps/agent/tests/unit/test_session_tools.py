"""Tests for session_tools module."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from ag3nt_agent.session_tools import (
    SessionInfo,
    Message,
    SessionToolsResult,
    SessionTools,
    create_list_sessions_tool,
    create_get_session_history_tool,
    create_send_message_tool,
    get_session_tools,
    sessions_list,
    sessions_history,
    sessions_send,
)


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_from_dict(self):
        """Test creating SessionInfo from dict."""
        data = {
            "id": "telegram:bot-1:chat-123",
            "channelType": "telegram",
            "channelId": "bot-1",
            "chatId": "chat-123",
            "userId": "user-456",
            "userName": "John Doe",
            "createdAt": "2024-01-15T10:00:00Z",
            "lastActivityAt": "2024-01-15T11:00:00Z",
            "paired": True,
            "messageCount": 42,
        }

        session = SessionInfo.from_dict(data)

        assert session.id == "telegram:bot-1:chat-123"
        assert session.channel_type == "telegram"
        assert session.channel_id == "bot-1"
        assert session.chat_id == "chat-123"
        assert session.user_id == "user-456"
        assert session.user_name == "John Doe"
        assert session.paired is True
        assert session.message_count == 42
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_activity_at, datetime)

    def test_to_dict(self):
        """Test converting SessionInfo to dict."""
        session = SessionInfo(
            id="telegram:bot-1:chat-123",
            channel_type="telegram",
            channel_id="bot-1",
            chat_id="chat-123",
            user_id="user-456",
            user_name="John Doe",
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            last_activity_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            paired=True,
            message_count=42,
        )

        result = session.to_dict()

        assert result["id"] == "telegram:bot-1:chat-123"
        assert result["channel_type"] == "telegram"
        assert result["paired"] is True
        assert result["message_count"] == 42

    def test_from_dict_without_optional_fields(self):
        """Test creating SessionInfo with missing optional fields."""
        data = {
            "id": "test:1:1",
            "channelType": "test",
            "channelId": "1",
            "userId": "user",
            "createdAt": "2024-01-15T10:00:00Z",
            "lastActivityAt": "2024-01-15T10:00:00Z",
            "paired": False,
        }

        session = SessionInfo.from_dict(data)

        assert session.user_name is None
        assert session.chat_id == ""
        assert session.message_count == 0


class TestMessage:
    """Tests for Message dataclass."""

    def test_from_dict(self):
        """Test creating Message from dict."""
        data = {
            "id": "msg-123",
            "role": "user",
            "content": "Hello world",
            "timestamp": "2024-01-15T10:00:00Z",
            "toolCalls": [{"id": "call-1", "name": "search", "arguments": {}}],
        }

        message = Message.from_dict(data)

        assert message.id == "msg-123"
        assert message.role == "user"
        assert message.content == "Hello world"
        assert isinstance(message.timestamp, datetime)
        assert message.tool_calls is not None
        assert len(message.tool_calls) == 1

    def test_to_dict(self):
        """Test converting Message to dict."""
        message = Message(
            id="msg-123",
            role="assistant",
            content="Hello",
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            tool_calls=None,
        )

        result = message.to_dict()

        assert result["id"] == "msg-123"
        assert result["role"] == "assistant"
        assert result["content"] == "Hello"
        assert "tool_calls" not in result

    def test_to_dict_with_tool_calls(self):
        """Test converting Message with tool_calls to dict."""
        tool_calls = [{"id": "call-1", "name": "test", "arguments": {"x": 1}}]
        message = Message(
            id="msg-123",
            role="assistant",
            content="Hello",
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            tool_calls=tool_calls,
        )

        result = message.to_dict()

        assert "tool_calls" in result
        assert result["tool_calls"] == tool_calls


class TestSessionToolsResult:
    """Tests for SessionToolsResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = SessionToolsResult(success=True, data={"id": "123"})

        assert result.success is True
        assert result.data == {"id": "123"}
        assert result.error is None

    def test_error_result(self):
        """Test error result."""
        result = SessionToolsResult(success=False, error="Not found")

        assert result.success is False
        assert result.error == "Not found"


class TestSessionTools:
    """Tests for SessionTools class."""

    @pytest.fixture
    def tools(self):
        """Create SessionTools instance."""
        return SessionTools("http://localhost:18789")

    def test_init(self, tools):
        """Test initialization."""
        assert tools.gateway_url == "http://localhost:18789"
        assert tools._client is None

    def test_init_strips_trailing_slash(self):
        """Test URL normalization."""
        tools = SessionTools("http://localhost:18789/")
        assert tools.gateway_url == "http://localhost:18789"

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, tools):
        """Test client creation."""
        client = await tools._get_client()

        assert client is not None
        assert isinstance(client, httpx.AsyncClient)

        await tools.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with SessionTools() as tools:
            assert tools._client is not None

        assert tools._client is None

    @pytest.mark.asyncio
    async def test_list_sessions(self, tools):
        """Test list_sessions method."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sessions": [
                {
                    "id": "test:1:1",
                    "channelType": "test",
                    "channelId": "1",
                    "chatId": "1",
                    "userId": "user1",
                    "userName": None,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "lastActivityAt": "2024-01-15T10:00:00Z",
                    "paired": True,
                    "messageCount": 5,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            sessions = await tools.list_sessions(limit=10)

            assert len(sessions) == 1
            assert sessions[0].id == "test:1:1"
            assert sessions[0].message_count == 5

        await tools.close()

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, tools):
        """Test get_session returns None for 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "Not found",
                request=MagicMock(),
                response=mock_response,
            )

            session = await tools.get_session("non-existent")

            assert session is None

        await tools.close()

    @pytest.mark.asyncio
    async def test_send_message_success(self, tools):
        """Test send_message success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "messageId": "msg-123"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            result = await tools.send_message("session-1", "Hello")

            assert result.success is True
            assert result.data["message_id"] == "msg-123"

        await tools.close()

    @pytest.mark.asyncio
    async def test_delete_session_success(self, tools):
        """Test delete_session success."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            httpx.AsyncClient, "delete", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = mock_response

            result = await tools.delete_session("session-1")

            assert result.success is True

        await tools.close()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, tools):
        """Test delete_session for non-existent session."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b""

        with patch.object(
            httpx.AsyncClient, "delete", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.side_effect = httpx.HTTPStatusError(
                "Not found",
                request=MagicMock(),
                response=mock_response,
            )

            result = await tools.delete_session("non-existent")

            assert result.success is False
            assert result.error == "Session not found"

        await tools.close()


class TestToolFactories:
    """Tests for LangChain tool factory functions."""

    @pytest.mark.asyncio
    async def test_create_list_sessions_tool(self):
        """Test list sessions tool factory."""
        tool = create_list_sessions_tool()

        assert callable(tool)
        assert tool.__doc__ is not None

    @pytest.mark.asyncio
    async def test_create_get_session_history_tool(self):
        """Test get session history tool factory."""
        tool = create_get_session_history_tool()

        assert callable(tool)
        assert tool.__doc__ is not None

    @pytest.mark.asyncio
    async def test_create_send_message_tool(self):
        """Test send message tool factory."""
        tool = create_send_message_tool()

        assert callable(tool)
        assert tool.__doc__ is not None


# ============================================================================
# @tool Wrapper Tests
# ============================================================================


class TestGetSessionTools:
    """Tests for get_session_tools() factory function."""

    def test_returns_list(self):
        """Test that get_session_tools returns a list."""
        tools = get_session_tools()
        assert isinstance(tools, list)

    def test_returns_three_tools(self):
        """Test that get_session_tools returns exactly 3 tools."""
        tools = get_session_tools()
        assert len(tools) == 3

    def test_tool_names(self):
        """Test that all expected tools are present."""
        tools = get_session_tools()
        tool_names = {t.name for t in tools}
        expected = {"sessions_list", "sessions_history", "sessions_send"}
        assert tool_names == expected

    def test_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        tools = get_session_tools()
        for t in tools:
            assert t.description, f"Tool {t.name} has no description"


class TestSessionToolWrappers:
    """Tests for @tool decorated session wrapper functions."""

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_list_empty(self, mock_async):
        """Test sessions_list with no sessions."""
        mock_async.return_value = []
        result = sessions_list.invoke({})
        assert "No active sessions found" in result

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_list_with_results(self, mock_async):
        """Test sessions_list with sessions."""
        mock_async.return_value = [
            SessionInfo(
                id="test:1:1",
                channel_type="telegram",
                channel_id="bot-1",
                chat_id="chat-1",
                user_id="user-1",
                user_name="Alice",
                created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
                last_activity_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
                paired=True,
                message_count=10,
            ),
        ]
        result = sessions_list.invoke({})
        assert "1 session(s)" in result
        assert "Alice" in result
        assert "telegram" in result

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_list_error(self, mock_async):
        """Test sessions_list handles errors gracefully."""
        mock_async.side_effect = Exception("Connection refused")
        result = sessions_list.invoke({})
        assert "Error" in result

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_history_empty(self, mock_async):
        """Test sessions_history with no messages."""
        mock_async.return_value = []
        result = sessions_history.invoke({"session_id": "test:1:1"})
        assert "No messages found" in result

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_history_with_messages(self, mock_async):
        """Test sessions_history with messages."""
        mock_async.return_value = [
            Message(
                id="msg-1",
                role="user",
                content="Hello there!",
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            ),
            Message(
                id="msg-2",
                role="assistant",
                content="Hi! How can I help?",
                timestamp=datetime(2024, 1, 15, 10, 30, 5, tzinfo=timezone.utc),
            ),
        ]
        result = sessions_history.invoke({"session_id": "test:1:1"})
        assert "2 message(s)" in result
        assert "Hello there!" in result

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_send_success(self, mock_async):
        """Test sessions_send success."""
        mock_async.return_value = SessionToolsResult(success=True)
        result = sessions_send.invoke({"session_id": "test:1:1", "content": "Hello"})
        assert "Message sent" in result

    @patch("ag3nt_agent.session_tools._run_async")
    def test_sessions_send_failure(self, mock_async):
        """Test sessions_send failure."""
        mock_async.return_value = SessionToolsResult(success=False, error="Session not found")
        result = sessions_send.invoke({"session_id": "bad-id", "content": "Hello"})
        assert "Failed" in result

