"""Unit tests for ag3nt_agent.web_search module.

Tests cover:
- SearchResult and SearchResponse dataclasses
- RateLimiter with sliding window
- SearchCache with TTL expiration
- WebSearchTool with mocked providers
- Error handling and fallback behavior
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from ag3nt_agent.web_search import (
    RateLimiter,
    SearchCache,
    SearchResponse,
    SearchResult,
    WebSearchTool,
    get_web_search_tool,
    internet_search,
)


# =============================================================================
# SearchResult Tests
# =============================================================================


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_create_basic_result(self):
        """Test creating a basic search result."""
        result = SearchResult(
            title="Python Tutorial",
            url="https://python.org",
            snippet="Learn Python programming...",
        )
        assert result.title == "Python Tutorial"
        assert result.url == "https://python.org"
        assert result.snippet == "Learn Python programming..."
        assert result.score == 0.0
        assert result.published_date is None
        assert result.source == ""

    def test_create_full_result(self):
        """Test creating a result with all fields."""
        result = SearchResult(
            title="News Article",
            url="https://news.com/article",
            snippet="Breaking news...",
            score=0.95,
            published_date="2024-01-15",
            source="tavily",
        )
        assert result.score == 0.95
        assert result.published_date == "2024-01-15"
        assert result.source == "tavily"

    def test_result_is_frozen(self):
        """Test that SearchResult is immutable."""
        result = SearchResult(title="Test", url="http://test.com", snippet="test")
        with pytest.raises(AttributeError):
            result.title = "Modified"  # type: ignore

    def test_to_dict_excludes_empty(self):
        """Test to_dict excludes None and empty string values."""
        result = SearchResult(
            title="Test",
            url="http://test.com",
            snippet="content",
            score=0.5,
        )
        d = result.to_dict()
        assert "title" in d
        assert "url" in d
        assert "snippet" in d
        assert "score" in d
        assert "published_date" not in d  # None excluded
        assert "source" not in d  # Empty string excluded

    def test_to_dict_includes_all_set(self):
        """Test to_dict includes all set values."""
        result = SearchResult(
            title="Test",
            url="http://test.com",
            snippet="content",
            score=0.8,
            published_date="2024-01-01",
            source="duckduckgo",
        )
        d = result.to_dict()
        assert d["published_date"] == "2024-01-01"
        assert d["source"] == "duckduckgo"


# =============================================================================
# SearchResponse Tests
# =============================================================================


class TestSearchResponse:
    """Tests for SearchResponse dataclass."""

    def test_create_successful_response(self):
        """Test creating a successful response."""
        results = (
            SearchResult(title="R1", url="http://r1.com", snippet="s1"),
            SearchResult(title="R2", url="http://r2.com", snippet="s2"),
        )
        response = SearchResponse(
            query="test query",
            results=results,
            provider="tavily",
            timestamp="2024-01-15T12:00:00Z",
        )
        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.provider == "tavily"
        assert response.success is True
        assert response.cached is False

    def test_success_property_no_results(self):
        """Test success is False when no results."""
        response = SearchResponse(
            query="test",
            results=(),
            provider="tavily",
        )
        assert response.success is False

    def test_success_property_with_error(self):
        """Test success is False when error is set."""
        results = (SearchResult(title="R1", url="http://r1.com", snippet="s1"),)
        response = SearchResponse(
            query="test",
            results=results,
            provider="tavily",
            error="API error",
        )
        assert response.success is False


# =============================================================================
# RateLimiter Tests
# =============================================================================


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_acquire_within_limit(self):
        """Test acquiring within rate limit."""
        limiter = RateLimiter(requests_per_minute=5)
        for _ in range(5):
            assert limiter.acquire() is True

    def test_acquire_exceeds_limit(self):
        """Test acquire returns False when limit exceeded."""
        limiter = RateLimiter(requests_per_minute=3)
        for _ in range(3):
            limiter.acquire()
        assert limiter.acquire() is False

    def test_wait_time_when_available(self):
        """Test wait_time returns 0 when slots available."""
        limiter = RateLimiter(requests_per_minute=5)
        limiter.acquire()
        assert limiter.wait_time() == 0.0

    def test_wait_time_when_limited(self):
        """Test wait_time returns positive when limited."""
        limiter = RateLimiter(requests_per_minute=1)
        limiter.acquire()
        wait = limiter.wait_time()
        assert wait > 0
        assert wait <= 60.0

    def test_reset_clears_timestamps(self):
        """Test reset clears all timestamps."""
        limiter = RateLimiter(requests_per_minute=2)
        limiter.acquire()
        limiter.acquire()
        assert limiter.acquire() is False
        limiter.reset()
        assert limiter.acquire() is True

    def test_sliding_window_expires_old(self):
        """Test that old timestamps expire from window."""
        limiter = RateLimiter(requests_per_minute=1)
        # Manually insert an old timestamp
        with limiter._lock:
            limiter._timestamps.append(time.time() - 61)
        # Should be able to acquire since old timestamp expired
        assert limiter.acquire() is True


# =============================================================================
# SearchCache Tests
# =============================================================================


class TestSearchCache:
    """Tests for SearchCache class."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path: Path):
        """Create a temporary cache directory."""
        cache_dir = tmp_path / "search_cache"
        return cache_dir

    @pytest.fixture
    def cache(self, temp_cache_dir: Path):
        """Create a cache instance with temp directory."""
        return SearchCache(cache_dir=temp_cache_dir, ttl_hours=1)

    def test_cache_dir_created(self, temp_cache_dir: Path):
        """Test cache directory is created on init."""
        cache = SearchCache(cache_dir=temp_cache_dir)
        assert temp_cache_dir.exists()

    def test_disabled_cache_returns_none(self, temp_cache_dir: Path):
        """Test disabled cache always returns None."""
        cache = SearchCache(cache_dir=temp_cache_dir, enabled=False)
        assert cache.get("test query", 5) is None

    def test_get_nonexistent_returns_none(self, cache: SearchCache):
        """Test get returns None for non-cached query."""
        assert cache.get("nonexistent query", 5) is None

    def test_set_and_get_cached_response(self, cache: SearchCache):
        """Test set and get work correctly."""
        response = SearchResponse(
            query="python tutorial",
            results=(SearchResult(title="R1", url="http://r1.com", snippet="s1"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        cache.set("python tutorial", 5, response)
        cached = cache.get("python tutorial", 5)

        assert cached is not None
        assert cached.query == "python tutorial"
        assert cached.cached is True
        assert len(cached.results) == 1

    def test_cache_key_case_insensitive(self, cache: SearchCache):
        """Test cache key is case insensitive."""
        response = SearchResponse(
            query="Python Tutorial",
            results=(SearchResult(title="R1", url="http://r1.com", snippet="s1"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        cache.set("Python Tutorial", 5, response)
        # Should find with different case
        cached = cache.get("python tutorial", 5)
        assert cached is not None

    def test_cache_key_includes_max_results(self, cache: SearchCache):
        """Test cache key includes max_results."""
        response = SearchResponse(
            query="test",
            results=(SearchResult(title="R1", url="http://r1.com", snippet="s1"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        cache.set("test", 5, response)
        # Different max_results should not find cache
        assert cache.get("test", 10) is None
        assert cache.get("test", 5) is not None

    def test_expired_cache_returns_none(self, temp_cache_dir: Path):
        """Test expired cache entries return None."""
        cache = SearchCache(cache_dir=temp_cache_dir, ttl_hours=1)
        # Create an old cache entry manually
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        cache_key = cache._get_cache_key("old query", 5)
        cache_path = cache._get_cache_path(cache_key)
        cache_path.write_text(json.dumps({
            "query": "old query",
            "results": [],
            "provider": "tavily",
            "timestamp": old_time.isoformat(),
        }))

        # Should return None for expired entry
        assert cache.get("old query", 5) is None
        # File should be deleted
        assert not cache_path.exists()

    def test_clear_all(self, cache: SearchCache):
        """Test clear with expired_only=False removes all."""
        response = SearchResponse(
            query="test",
            results=(SearchResult(title="R1", url="http://r1.com", snippet="s1"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        cache.set("test1", 5, response)
        cache.set("test2", 5, response)
        removed = cache.clear(expired_only=False)
        assert removed == 2
        assert cache.get("test1", 5) is None

    def test_clear_expired_only(self, temp_cache_dir: Path):
        """Test clear with expired_only=True only removes old."""
        cache = SearchCache(cache_dir=temp_cache_dir, ttl_hours=1)
        # Create current and expired entries
        current = SearchResponse(
            query="current",
            results=(SearchResult(title="R1", url="http://r1.com", snippet="s1"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        cache.set("current", 5, current)

        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        cache_key = cache._get_cache_key("old", 5)
        cache_path = cache._get_cache_path(cache_key)
        cache_path.write_text(json.dumps({
            "query": "old",
            "results": [],
            "provider": "tavily",
            "timestamp": old_time.isoformat(),
        }))

        removed = cache.clear(expired_only=True)
        assert removed == 1
        # Current should still exist
        assert cache.get("current", 5) is not None

    def test_set_does_not_cache_errors(self, cache: SearchCache):
        """Test that responses with errors are not cached."""
        response = SearchResponse(
            query="error query",
            results=(),
            provider="tavily",
            error="API error",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        cache.set("error query", 5, response)
        assert cache.get("error query", 5) is None

    def test_get_handles_corrupt_json(self, temp_cache_dir: Path):
        """Test get handles corrupt JSON gracefully."""
        cache = SearchCache(cache_dir=temp_cache_dir, ttl_hours=1)
        cache_key = cache._get_cache_key("corrupt", 5)
        cache_path = cache._get_cache_path(cache_key)
        cache_path.write_text("not valid json {{{", encoding="utf-8")

        result = cache.get("corrupt", 5)
        assert result is None
        # File should be deleted
        assert not cache_path.exists()

    def test_clear_nonexistent_dir(self, tmp_path: Path):
        """Test clear on nonexistent directory returns 0."""
        cache = SearchCache(cache_dir=tmp_path / "does_not_exist", enabled=False)
        assert cache.clear() == 0




# =============================================================================
# WebSearchTool Tests
# =============================================================================


class TestWebSearchTool:
    """Tests for WebSearchTool class."""

    @pytest.fixture
    def mock_cache(self, tmp_path: Path):
        """Create a mock cache for testing."""
        return SearchCache(cache_dir=tmp_path / "cache", ttl_hours=1)

    @pytest.fixture
    def tool(self, mock_cache: SearchCache):
        """Create a WebSearchTool with mocked components."""
        return WebSearchTool(
            tavily_api_key="test-key",
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

    def test_init_with_env_api_key(self, mock_cache: SearchCache):
        """Test initialization with environment API key."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "env-key"}):
            tool = WebSearchTool(cache=mock_cache)
            assert tool.tavily_api_key == "env-key"

    def test_init_explicit_key_overrides_env(self, mock_cache: SearchCache):
        """Test explicit API key overrides environment."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "env-key"}):
            tool = WebSearchTool(tavily_api_key="explicit-key", cache=mock_cache)
            assert tool.tavily_api_key == "explicit-key"

    def test_search_returns_cached_response(self, tool: WebSearchTool, mock_cache: SearchCache):
        """Test search returns cached response when available."""
        # Pre-cache a response
        cached_response = SearchResponse(
            query="cached query",
            results=(SearchResult(title="Cached", url="http://cached.com", snippet="cached"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        mock_cache.set("cached query", 5, cached_response)

        result = tool.search("cached query")
        assert result.cached is True
        assert result.results[0].title == "Cached"

    def test_search_skips_cache_when_disabled(self, tool: WebSearchTool, mock_cache: SearchCache):
        """Test search skips cache when use_cache=False."""
        # Pre-cache a response
        mock_cache.set("query", 5, SearchResponse(
            query="query",
            results=(SearchResult(title="Cached", url="http://c.com", snippet="c"),),
            provider="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))

        # Mock Tavily to return different result
        mock_tavily_client = MagicMock()
        mock_tavily_client.search.return_value = {
            "results": [{"title": "Fresh", "url": "http://f.com", "content": "fresh"}]
        }
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_tavily_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = tool.search("query", use_cache=False)
            assert result.cached is False
            assert result.results[0].title == "Fresh"

    def test_search_with_tavily_success(self, tool: WebSearchTool):
        """Test successful Tavily search."""
        mock_tavily_client = MagicMock()
        mock_tavily_client.search.return_value = {
            "results": [
                {"title": "Result 1", "url": "http://r1.com", "content": "snippet 1", "score": 0.9},
                {"title": "Result 2", "url": "http://r2.com", "content": "snippet 2", "score": 0.8},
            ]
        }
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_tavily_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = tool.search("python tutorial", use_cache=False)
            assert result.success is True
            assert result.provider == "tavily"
            assert len(result.results) == 2
            assert result.results[0].score == 0.9

    def test_search_falls_back_to_duckduckgo(self, mock_cache: SearchCache):
        """Test fallback to DuckDuckGo when Tavily fails."""
        tool = WebSearchTool(
            tavily_api_key="test-key",
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

        # Mock Tavily to fail
        mock_tavily_client = MagicMock()
        mock_tavily_client.search.side_effect = Exception("API Error")
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_tavily_client

        # Mock DuckDuckGo to succeed
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = [
            {"title": "DDG Result", "href": "http://ddg.com", "body": "ddg snippet"}
        ]
        mock_ddg_module = MagicMock()
        mock_ddg_module.DDGS.return_value = mock_ddgs_instance

        with patch.dict("sys.modules", {"tavily": mock_tavily_module, "duckduckgo_search": mock_ddg_module}):
            result = tool.search("test query", use_cache=False)
            assert result.success is True
            assert result.provider == "duckduckgo"
            assert result.results[0].title == "DDG Result"

    def test_search_rate_limited(self, mock_cache: SearchCache):
        """Test rate limiting returns error response."""
        # Create a rate limiter that's already at limit
        limiter = RateLimiter(requests_per_minute=1)
        limiter.acquire()  # Use up the limit

        tool = WebSearchTool(
            tavily_api_key="test-key",
            cache=mock_cache,
            rate_limiter=limiter,
        )

        result = tool.search("test query", use_cache=False)
        assert result.success is False
        assert result.provider == "none"
        assert "Rate limited" in (result.error or "")

    def test_search_tavily_import_error(self, mock_cache: SearchCache):
        """Test handling when Tavily is not installed."""
        tool = WebSearchTool(
            tavily_api_key="test-key",
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

        # Remove tavily from sys.modules to simulate ImportError
        import sys
        original_modules = sys.modules.copy()

        # Create a mock that raises ImportError on import
        def raise_import(*args, **kwargs):
            raise ImportError("No module named 'tavily'")

        # Mock DDG to also fail
        with patch.dict("sys.modules", {"tavily": None, "duckduckgo_search": None}):
            result = tool.search("test", use_cache=False)
            assert result.success is False

    def test_search_duckduckgo_only(self, mock_cache: SearchCache):
        """Test search without Tavily API key uses DuckDuckGo."""
        tool = WebSearchTool(
            tavily_api_key=None,  # No Tavily key
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = [
            {"title": "DDG Only", "href": "http://ddg.com", "body": "ddg only"}
        ]
        mock_ddg_module = MagicMock()
        mock_ddg_module.DDGS.return_value = mock_ddgs_instance

        with patch.dict("sys.modules", {"duckduckgo_search": mock_ddg_module}):
            result = tool.search("test", use_cache=False)
            assert result.provider == "duckduckgo"
            assert result.success is True

    def test_tavily_rate_limit_exceeded(self, mock_cache: SearchCache):
        """Test when Tavily's per-provider rate limit is exceeded."""
        tool = WebSearchTool(
            tavily_api_key="test-key",
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )
        # Exhaust Tavily rate limiter
        for _ in range(60):
            tool._tavily_limiter.acquire()

        # Mock DuckDuckGo to succeed
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = [
            {"title": "Fallback", "href": "http://ddg.com", "body": "ddg"}
        ]
        mock_ddg_module = MagicMock()
        mock_ddg_module.DDGS.return_value = mock_ddgs_instance

        with patch.dict("sys.modules", {"duckduckgo_search": mock_ddg_module}):
            result = tool.search("test", use_cache=False)
            # Should fall back to DuckDuckGo
            assert result.provider == "duckduckgo"
            assert result.success is True

    def test_duckduckgo_rate_limit_exceeded(self, mock_cache: SearchCache):
        """Test when DuckDuckGo's rate limit is exceeded (no Tavily)."""
        tool = WebSearchTool(
            tavily_api_key=None,  # No Tavily
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )
        # Exhaust DuckDuckGo rate limiter
        for _ in range(30):
            tool._ddg_limiter.acquire()

        result = tool.search("test", use_cache=False)
        assert result.success is False
        assert "rate limit" in (result.error or "").lower()

    def test_duckduckgo_exception(self, mock_cache: SearchCache):
        """Test DuckDuckGo exception handling."""
        tool = WebSearchTool(
            tavily_api_key=None,  # No Tavily
            cache=mock_cache,
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.side_effect = Exception("Network error")
        mock_ddg_module = MagicMock()
        mock_ddg_module.DDGS.return_value = mock_ddgs_instance

        with patch.dict("sys.modules", {"duckduckgo_search": mock_ddg_module}):
            result = tool.search("test", use_cache=False)
            assert result.success is False
            assert "DuckDuckGo search failed" in (result.error or "")


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for web search module."""

    def test_get_web_search_tool_singleton(self):
        """Test get_web_search_tool returns singleton."""
        import ag3nt_agent.web_search as ws
        # Reset singleton
        ws._web_search_tool = None

        tool1 = get_web_search_tool()
        tool2 = get_web_search_tool()
        assert tool1 is tool2

    def test_internet_search_function(self, tmp_path: Path):
        """Test internet_search wrapper function."""
        import ag3nt_agent.web_search as ws
        # Reset singleton with test config
        ws._web_search_tool = WebSearchTool(
            tavily_api_key="test",
            cache=SearchCache(cache_dir=tmp_path / "cache"),
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

        mock_tavily_client = MagicMock()
        mock_tavily_client.search.return_value = {
            "results": [{"title": "Test", "url": "http://test.com", "content": "test content"}]
        }
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_tavily_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = internet_search("test query", max_results=3)
            assert isinstance(result, dict)
            assert result["query"] == "test query"
            assert result["provider"] == "tavily"
            assert len(result["results"]) == 1

    def test_internet_search_topic_parameter(self, tmp_path: Path):
        """Test internet_search passes topic parameter."""
        import ag3nt_agent.web_search as ws
        ws._web_search_tool = WebSearchTool(
            tavily_api_key="test",
            cache=SearchCache(cache_dir=tmp_path / "cache"),
            rate_limiter=RateLimiter(requests_per_minute=100),
        )

        mock_tavily_client = MagicMock()
        mock_tavily_client.search.return_value = {"results": []}
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_tavily_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            internet_search("stock prices", topic="finance")
            mock_tavily_client.search.assert_called_with(
                query="stock prices",
                max_results=5,
                topic="finance",
            )
