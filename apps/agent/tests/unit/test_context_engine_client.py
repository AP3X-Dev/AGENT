"""
Tests for Context-Engine client.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from ag3nt_agent.context_engine_client import (
    ContextEngineClient,
    MemoryResult,
    CodeSearchResult,
    ContextEngineError,
    ToolCallError,
    ConnectionError,
    get_context_engine,
    init_context_engine,
)


@pytest.fixture
def client():
    """Create a test client."""
    return ContextEngineClient(
        memory_url="http://test:8002/mcp",
        indexer_url="http://test:8003/mcp",
        qdrant_url="http://test:6333"
    )


class TestMemoryResult:
    """Tests for MemoryResult dataclass."""

    def test_from_response_basic(self):
        """Test creating MemoryResult from response."""
        data = {
            "content": "test content",
            "score": 0.95,
            "metadata": {"key": "value"}
        }
        result = MemoryResult.from_response(data)

        assert result.content == "test content"
        assert result.score == 0.95
        assert result.metadata == {"key": "value"}

    def test_from_response_alternative_fields(self):
        """Test creating MemoryResult with alternative field names."""
        data = {
            "information": "test info",
            "score": 0.8
        }
        result = MemoryResult.from_response(data)

        assert result.content == "test info"
        assert result.score == 0.8


class TestCodeSearchResult:
    """Tests for CodeSearchResult dataclass."""

    def test_from_response_basic(self):
        """Test creating CodeSearchResult from response."""
        data = {
            "file_path": "/path/to/file.py",
            "content": "def test():\n    pass",
            "score": 0.9,
            "language": "python",
            "start_line": 10,
            "end_line": 12
        }
        result = CodeSearchResult.from_response(data)

        assert result.file_path == "/path/to/file.py"
        assert result.content == "def test():\n    pass"
        assert result.score == 0.9
        assert result.language == "python"


class TestContextEngineClient:
    """Tests for ContextEngineClient."""

    @pytest.mark.asyncio
    async def test_init_with_defaults(self):
        """Test client initialization with default values."""
        client = ContextEngineClient()

        assert "localhost:8002" in client.memory_url
        assert "localhost:8003" in client.indexer_url

    @pytest.mark.asyncio
    async def test_init_with_custom_urls(self, client):
        """Test client initialization with custom URLs."""
        assert client.memory_url == "http://test:8002/mcp"
        assert client.indexer_url == "http://test:8003/mcp"

    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager."""
        async with client as c:
            assert c is client

    @pytest.mark.asyncio
    async def test_store_memory(self, client):
        """Test storing a memory."""
        with patch.object(client, '_call_mcp_tool', new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "test-id", "status": "stored"}

            result = await client.store_memory(
                information="Test information",
                metadata={"tag": "test"},
                collection="test-collection"
            )

            mock.assert_called_once()
            call_args = mock.call_args
            assert call_args[0][1] == "store"
            assert "Test information" in call_args[0][2]["information"]

    @pytest.mark.asyncio
    async def test_find_memories(self, client):
        """Test finding memories."""
        with patch.object(client, '_call_mcp_tool', new_callable=AsyncMock) as mock:
            mock.return_value = {
                "results": [
                    {"content": "result 1", "score": 0.9, "metadata": {}},
                    {"content": "result 2", "score": 0.8, "metadata": {}}
                ]
            }

            results = await client.find_memories(
                query="test query",
                limit=10,
                collection="test-collection"
            )

            assert len(results) == 2
            assert results[0].content == "result 1"
            assert results[0].score == 0.9

    @pytest.mark.asyncio
    async def test_find_memories_with_min_score(self, client):
        """Test filtering results by minimum score."""
        with patch.object(client, '_call_mcp_tool', new_callable=AsyncMock) as mock:
            mock.return_value = {
                "results": [
                    {"content": "result 1", "score": 0.9, "metadata": {}},
                    {"content": "result 2", "score": 0.3, "metadata": {}}
                ]
            }

            results = await client.find_memories(
                query="test query",
                limit=10,
                collection="test-collection",
                min_score=0.5
            )

            assert len(results) == 1
            assert results[0].score >= 0.5

    @pytest.mark.asyncio
    async def test_search_code(self, client):
        """Test code search."""
        with patch.object(client, '_call_mcp_tool', new_callable=AsyncMock) as mock:
            mock.return_value = {
                "results": [
                    {"file_path": "/test.py", "content": "code", "score": 0.9}
                ]
            }

            results = await client.search_code(
                query="test function",
                limit=5
            )

            assert len(results) == 1
            assert results[0].file_path == "/test.py"

    @pytest.mark.asyncio
    async def test_context_search(self, client):
        """Test unified context search."""
        with patch.object(client, 'find_memories', new_callable=AsyncMock) as mem_mock, \
             patch.object(client, 'search_code', new_callable=AsyncMock) as code_mock:

            mem_mock.return_value = [MemoryResult("mem1", 0.9)]
            code_mock.return_value = [CodeSearchResult("/test.py", "code", 0.8)]

            results = await client.context_search("test query")

            assert len(results["memory"]) == 1
            assert len(results["code"]) == 1

    @pytest.mark.asyncio
    async def test_store_action(self, client):
        """Test storing an action for learning."""
        with patch.object(client, 'store_memory', new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "action-id"}

            result = await client.store_action(
                action_type="shell",
                goal_id="test-goal",
                success=True,
                duration_ms=1500,
                context="restarted nginx"
            )

            mock.assert_called_once()
            call_args = mock.call_args
            assert call_args[1]["collection"] == ContextEngineClient.COLLECTION_LEARNING

    @pytest.mark.asyncio
    async def test_get_action_confidence(self, client):
        """Test calculating action confidence."""
        with patch.object(client, 'find_memories', new_callable=AsyncMock) as mock:
            mock.return_value = [
                MemoryResult("action 1", 0.9, {"success": True}),
                MemoryResult("action 2", 0.85, {"success": True}),
                MemoryResult("action 3", 0.8, {"success": False}),
            ]

            confidence, count = await client.get_action_confidence(
                action_type="shell",
                context="restart service"
            )

            assert count == 3
            assert 0 < confidence < 1

    @pytest.mark.asyncio
    async def test_get_action_confidence_insufficient_samples(self, client):
        """Test confidence with insufficient samples."""
        with patch.object(client, 'find_memories', new_callable=AsyncMock) as mock:
            mock.return_value = [
                MemoryResult("action 1", 0.9, {"success": True}),
            ]

            confidence, count = await client.get_action_confidence(
                action_type="shell",
                context="restart service",
                min_samples=3
            )

            assert count == 1
            assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health check."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        with patch.object(client, '_get_client', new_callable=AsyncMock) as mock:
            mock.return_value = mock_client

            status = await client.health_check()

            assert "healthy" in status


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_context_engine_singleton(self):
        """Test singleton pattern."""
        # Reset singleton
        import ag3nt_agent.context_engine_client as module
        module._client = None

        client1 = get_context_engine()
        client2 = get_context_engine()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_init_context_engine(self):
        """Test custom initialization."""
        import ag3nt_agent.context_engine_client as module
        module._client = None

        client = await init_context_engine(
            memory_url="http://custom:8002/mcp"
        )

        assert client.memory_url == "http://custom:8002/mcp"
