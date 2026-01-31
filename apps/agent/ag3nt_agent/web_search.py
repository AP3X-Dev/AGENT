"""Web search tool for AG3NT with multi-provider support.

This module provides web search capabilities with:
- Tavily as primary provider (requires TAVILY_API_KEY)
- DuckDuckGo as fallback (no API key required)
- Result caching to reduce API calls
- Rate limiting to prevent abuse
- Structured output with SearchResult dataclass

Usage:
    from ag3nt_agent.web_search import WebSearchTool, get_web_search_tool

    # Direct usage
    tool = WebSearchTool()
    results = await tool.search("Python async programming")

    # As LangChain tool
    lc_tool = get_web_search_tool()
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Literal

logger = logging.getLogger("ag3nt.web_search")


@dataclass(frozen=True)
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    score: float = 0.0
    published_date: str | None = None
    source: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}


@dataclass(frozen=True)
class SearchResponse:
    """Response from web search."""

    query: str
    results: tuple[SearchResult, ...]
    provider: Literal["tavily", "duckduckgo", "none"]
    cached: bool = False
    timestamp: str = ""
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if search was successful."""
        return self.error is None and len(self.results) > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for tool output."""
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "provider": self.provider,
            "cached": self.cached,
            "result_count": len(self.results),
            "error": self.error,
        }


@dataclass
class RateLimiter:
    """Simple rate limiter with sliding window."""

    requests_per_minute: int = 10
    _timestamps: list[float] = field(default_factory=list, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def acquire(self) -> bool:
        """Try to acquire a rate limit slot.

        Returns:
            True if request is allowed, False if rate limited.
        """
        with self._lock:
            now = time.time()
            window_start = now - 60.0

            # Remove timestamps outside the window
            self._timestamps = [t for t in self._timestamps if t > window_start]

            if len(self._timestamps) >= self.requests_per_minute:
                return False

            self._timestamps.append(now)
            return True

    def wait_time(self) -> float:
        """Get time to wait before next request is allowed.

        Returns:
            Seconds to wait, or 0 if request is allowed now.
        """
        with self._lock:
            now = time.time()
            window_start = now - 60.0

            self._timestamps = [t for t in self._timestamps if t > window_start]

            if len(self._timestamps) < self.requests_per_minute:
                return 0.0

            # Wait until oldest timestamp expires
            oldest = min(self._timestamps)
            return max(0.0, oldest + 60.0 - now)

    def reset(self) -> None:
        """Reset the rate limiter."""
        with self._lock:
            self._timestamps.clear()


@dataclass
class SearchCache:
    """Simple file-based cache for search results."""

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".ag3nt" / "search_cache")
    ttl_hours: int = 1
    enabled: bool = True

    def __post_init__(self) -> None:
        """Ensure cache directory exists."""
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, query: str, max_results: int) -> str:
        """Generate cache key from query parameters."""
        key_str = f"{query.lower().strip()}:{max_results}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get path to cache file."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, query: str, max_results: int) -> SearchResponse | None:
        """Get cached response if valid.

        Args:
            query: Search query.
            max_results: Max results requested.

        Returns:
            Cached SearchResponse or None if not found/expired.
        """
        if not self.enabled:
            return None

        cache_key = self._get_cache_key(query, max_results)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_time = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            expiry = cached_time + timedelta(hours=self.ttl_hours)

            if datetime.now(timezone.utc) > expiry:
                cache_path.unlink(missing_ok=True)
                return None

            results = tuple(
                SearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r["snippet"],
                    score=r.get("score", 0.0),
                    published_date=r.get("published_date"),
                    source=r.get("source", ""),
                )
                for r in data["results"]
            )

            return SearchResponse(
                query=data["query"],
                results=results,
                provider=data["provider"],
                cached=True,
                timestamp=data["timestamp"],
                error=data.get("error"),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug(f"Cache read error: {e}")
            cache_path.unlink(missing_ok=True)
            return None

    def set(self, query: str, max_results: int, response: SearchResponse) -> None:
        """Cache a search response.

        Args:
            query: Search query.
            max_results: Max results requested.
            response: Response to cache.
        """
        if not self.enabled or response.error:
            return

        cache_key = self._get_cache_key(query, max_results)
        cache_path = self._get_cache_path(cache_key)

        try:
            data = {
                "query": response.query,
                "results": [r.to_dict() for r in response.results],
                "provider": response.provider,
                "timestamp": response.timestamp or datetime.now(timezone.utc).isoformat(),
            }
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning(f"Cache write error: {e}")

    def clear(self, expired_only: bool = True) -> int:
        """Clear cache entries.

        Args:
            expired_only: If True, only remove expired entries.

        Returns:
            Number of entries removed.
        """
        if not self.cache_dir.exists():
            return 0

        removed = 0
        now = datetime.now(timezone.utc)

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if expired_only:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    cached_time = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                    if now <= cached_time + timedelta(hours=self.ttl_hours):
                        continue
                cache_file.unlink()
                removed += 1
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                cache_file.unlink(missing_ok=True)
                removed += 1

        return removed




class WebSearchTool:
    """Web search tool with Tavily primary and DuckDuckGo fallback."""

    def __init__(
        self,
        tavily_api_key: str | None = None,
        max_results: int = 5,
        cache: SearchCache | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize web search tool.

        Args:
            tavily_api_key: Tavily API key (falls back to TAVILY_API_KEY env var).
            max_results: Default max results per search.
            cache: Search cache instance (created if None).
            rate_limiter: Rate limiter instance (created if None).
        """
        self.tavily_api_key = tavily_api_key or os.environ.get("TAVILY_API_KEY")
        self.max_results = max_results
        self.cache = cache or SearchCache()
        self.rate_limiter = rate_limiter or RateLimiter()
        self._tavily_limiter = RateLimiter(requests_per_minute=60)  # Tavily limit
        self._ddg_limiter = RateLimiter(requests_per_minute=30)  # DuckDuckGo limit

    def search(
        self,
        query: str,
        max_results: int | None = None,
        topic: Literal["general", "news", "finance"] = "general",
        use_cache: bool = True,
    ) -> SearchResponse:
        """Search the web for information.

        Args:
            query: Search query string.
            max_results: Override default max results.
            topic: Search topic (general, news, finance).
            use_cache: Whether to use cache.

        Returns:
            SearchResponse with results from Tavily or DuckDuckGo.
        """
        max_results = max_results or self.max_results
        timestamp = datetime.now(timezone.utc).isoformat()

        # Check cache first
        if use_cache:
            cached = self.cache.get(query, max_results)
            if cached:
                logger.debug(f"Cache hit for query: {query[:50]}")
                return cached

        # Check global rate limit
        if not self.rate_limiter.acquire():
            wait = self.rate_limiter.wait_time()
            return SearchResponse(
                query=query,
                results=(),
                provider="none",
                timestamp=timestamp,
                error=f"Rate limited. Try again in {wait:.1f} seconds.",
            )

        # Try Tavily first if API key is available
        if self.tavily_api_key:
            response = self._search_tavily(query, max_results, topic, timestamp)
            if response.success:
                self.cache.set(query, max_results, response)
                return response
            logger.warning(f"Tavily search failed: {response.error}, trying DuckDuckGo")

        # Fallback to DuckDuckGo
        response = self._search_duckduckgo(query, max_results, timestamp)
        if response.success:
            self.cache.set(query, max_results, response)
        return response

    def _search_tavily(
        self,
        query: str,
        max_results: int,
        topic: str,
        timestamp: str,
    ) -> SearchResponse:
        """Search using Tavily API."""
        if not self._tavily_limiter.acquire():
            return SearchResponse(
                query=query,
                results=(),
                provider="tavily",
                timestamp=timestamp,
                error="Tavily rate limit exceeded.",
            )

        try:
            from tavily import TavilyClient
            import concurrent.futures

            def do_search():
                client = TavilyClient(api_key=self.tavily_api_key)
                return client.search(
                    query=query,
                    max_results=max_results,
                    topic=topic,
                )

            # Run with timeout to prevent hanging
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(do_search)
                try:
                    raw_response = future.result(timeout=30)  # 30 second timeout
                except concurrent.futures.TimeoutError:
                    return SearchResponse(
                        query=query,
                        results=(),
                        provider="tavily",
                        timestamp=timestamp,
                        error="Tavily search timed out after 30 seconds.",
                    )

            results = tuple(
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    score=r.get("score", 0.0),
                    published_date=r.get("published_date"),
                    source="tavily",
                )
                for r in raw_response.get("results", [])
            )

            return SearchResponse(
                query=query,
                results=results,
                provider="tavily",
                timestamp=timestamp,
            )

        except ImportError:
            return SearchResponse(
                query=query,
                results=(),
                provider="tavily",
                timestamp=timestamp,
                error="Tavily package not installed. Install with: pip install tavily-python",
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=(),
                provider="tavily",
                timestamp=timestamp,
                error=f"Tavily search failed: {e}",
            )



    def _search_duckduckgo(
        self,
        query: str,
        max_results: int,
        timestamp: str,
    ) -> SearchResponse:
        """Search using DuckDuckGo (no API key required)."""
        if not self._ddg_limiter.acquire():
            return SearchResponse(
                query=query,
                results=(),
                provider="duckduckgo",
                timestamp=timestamp,
                error="DuckDuckGo rate limit exceeded.",
            )

        try:
            from duckduckgo_search import DDGS
            import concurrent.futures

            def do_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))

            # Run with timeout to prevent hanging
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(do_search)
                try:
                    raw_results = future.result(timeout=30)  # 30 second timeout
                except concurrent.futures.TimeoutError:
                    return SearchResponse(
                        query=query,
                        results=(),
                        provider="duckduckgo",
                        timestamp=timestamp,
                        error="DuckDuckGo search timed out after 30 seconds.",
                    )

            results = tuple(
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    score=0.0,
                    source="duckduckgo",
                )
                for r in raw_results
            )

            return SearchResponse(
                query=query,
                results=results,
                provider="duckduckgo",
                timestamp=timestamp,
            )

        except ImportError:
            return SearchResponse(
                query=query,
                results=(),
                provider="duckduckgo",
                timestamp=timestamp,
                error="DuckDuckGo package not installed. Install with: pip install duckduckgo-search",
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=(),
                provider="duckduckgo",
                timestamp=timestamp,
                error=f"DuckDuckGo search failed: {e}",
            )


# Global instance for singleton pattern
_web_search_tool: WebSearchTool | None = None


def get_web_search_tool() -> WebSearchTool:
    """Get or create the global WebSearchTool instance.

    Returns:
        WebSearchTool singleton instance.
    """
    global _web_search_tool
    if _web_search_tool is None:
        _web_search_tool = WebSearchTool()
    return _web_search_tool


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> dict:
    """Search the web for current information.

    This is the main entry point for web search, compatible with the
    existing internet_search tool signature.

    Args:
        query: The search query (be specific and detailed).
        max_results: Number of results to return (default: 5).
        topic: "general" for most queries, "news" for current events,
               "finance" for financial data.

    Returns:
        Search results dict with query, results, provider, and metadata.
    """
    tool = get_web_search_tool()
    response = tool.search(query, max_results=max_results, topic=topic)
    return response.to_dict()
