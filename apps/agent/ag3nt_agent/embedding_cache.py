"""Embedding cache for AG3NT.

This module provides caching for embeddings to avoid re-embedding unchanged content.
Uses SQLite for persistent storage with MD5 content hashing for cache keys.

Usage:
    from ag3nt_agent.embedding_cache import EmbeddingCache, get_embedding_cache

    # Get cached embedding or compute new one
    cache = get_embedding_cache()
    embedding = cache.get_or_compute("Some text", embeddings_model.embed_query)
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = Path.home() / ".ag3nt" / "cache"
CACHE_DB_FILE = CACHE_DIR / "embeddings.db"
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_MAX_ENTRIES = 10000


@dataclass
class CacheStats:
    """Statistics for embedding cache operations."""

    hits: int = 0
    misses: int = 0
    total_queries: int = 0
    entries_count: int = 0
    cache_size_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate (0-1)."""
        if self.total_queries == 0:
            return 0.0
        return self.hits / self.total_queries


class EmbeddingCache:
    """SQLite-backed embedding cache.

    Caches embeddings by content hash to avoid re-computing embeddings
    for unchanged content.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        """Initialize the embedding cache.

        Args:
            db_path: Path to SQLite database (defaults to ~/.ag3nt/cache/embeddings.db)
            max_age_days: Maximum age for cache entries before cleanup
            max_entries: Maximum number of entries before LRU cleanup
        """
        self._db_path = db_path or CACHE_DB_FILE
        self._max_age_days = max_age_days
        self._max_entries = max_entries
        self._conn: sqlite3.Connection | None = None
        self._stats = CacheStats()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize the database connection and schema."""
        if self._initialized:
            return

        # Create cache directory
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Create schema
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                content_hash TEXT PRIMARY KEY,
                embedding TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                dimensions INTEGER,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_accessed
            ON embeddings(last_accessed)
        """)
        self._conn.commit()
        self._initialized = True
        logger.debug(f"Embedding cache initialized at {self._db_path}")

    def _compute_hash(self, content: str) -> str:
        """Compute MD5 hash for content."""
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, content: str) -> list[float] | None:
        """Get cached embedding for content.

        Args:
            content: Text content to look up

        Returns:
            Cached embedding vector or None if not found
        """
        self._ensure_initialized()
        self._stats.total_queries += 1

        content_hash = self._compute_hash(content)
        cursor = self._conn.execute(
            "SELECT embedding FROM embeddings WHERE content_hash = ?",
            (content_hash,),
        )
        row = cursor.fetchone()

        if row is None:
            self._stats.misses += 1
            return None

        # Update last accessed time
        self._conn.execute(
            "UPDATE embeddings SET last_accessed = ? WHERE content_hash = ?",
            (time.time(), content_hash),
        )
        self._conn.commit()

        self._stats.hits += 1
        return json.loads(row["embedding"])

    def set(
        self,
        content: str,
        embedding: list[float],
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Store embedding in cache.

        Args:
            content: Text content
            embedding: Embedding vector
            provider: Embedding provider name (e.g., "openai")
            model: Model name (e.g., "text-embedding-3-small")
        """
        self._ensure_initialized()

        content_hash = self._compute_hash(content)
        now = time.time()

        self._conn.execute(
            """
            INSERT OR REPLACE INTO embeddings
            (content_hash, embedding, provider, model, dimensions, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content_hash,
                json.dumps(embedding),
                provider,
                model,
                len(embedding),
                now,
                now,
            ),
        )
        self._conn.commit()

    def get_or_compute(
        self,
        content: str,
        compute_fn: Callable[[str], list[float]],
        provider: str | None = None,
        model: str | None = None,
    ) -> list[float]:
        """Get cached embedding or compute and cache a new one.

        Args:
            content: Text content to embed
            compute_fn: Function to compute embedding if not cached
            provider: Embedding provider name
            model: Model name

        Returns:
            Embedding vector (from cache or freshly computed)
        """
        cached = self.get(content)
        if cached is not None:
            return cached

        # Compute new embedding
        embedding = compute_fn(content)
        self.set(content, embedding, provider, model)
        return embedding

    def get_or_compute_batch(
        self,
        contents: list[str],
        compute_fn: Callable[[list[str]], list[list[float]]],
        provider: str | None = None,
        model: str | None = None,
    ) -> list[list[float]]:
        """Get cached embeddings or compute and cache new ones (batch version).

        Args:
            contents: List of text contents to embed
            compute_fn: Function to compute embeddings for a batch
            provider: Embedding provider name
            model: Model name

        Returns:
            List of embedding vectors
        """
        results: list[list[float] | None] = [None] * len(contents)
        to_compute_indices: list[int] = []
        to_compute_contents: list[str] = []

        # Check cache for each content
        for i, content in enumerate(contents):
            cached = self.get(content)
            if cached is not None:
                results[i] = cached
            else:
                to_compute_indices.append(i)
                to_compute_contents.append(content)

        # Compute missing embeddings in batch
        if to_compute_contents:
            computed = compute_fn(to_compute_contents)
            for i, (idx, content) in enumerate(
                zip(to_compute_indices, to_compute_contents)
            ):
                embedding = computed[i]
                results[idx] = embedding
                self.set(content, embedding, provider, model)

        return results  # type: ignore

    def cleanup_stale(self, max_age_days: int | None = None) -> int:
        """Remove cache entries older than max age.

        Args:
            max_age_days: Max age in days (uses default if not provided)

        Returns:
            Number of entries removed
        """
        self._ensure_initialized()

        max_age = max_age_days or self._max_age_days
        cutoff = time.time() - (max_age * 24 * 3600)

        cursor = self._conn.execute(
            "DELETE FROM embeddings WHERE last_accessed < ?",
            (cutoff,),
        )
        self._conn.commit()

        removed = cursor.rowcount
        if removed > 0:
            logger.info(f"Cleaned up {removed} stale embedding cache entries")
        return removed

    def cleanup_lru(self, max_entries: int | None = None) -> int:
        """Remove least recently used entries if over limit.

        Args:
            max_entries: Maximum entries to keep (uses default if not provided)

        Returns:
            Number of entries removed
        """
        self._ensure_initialized()

        max_count = max_entries or self._max_entries
        count = self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

        if count <= max_count:
            return 0

        # Delete oldest entries
        to_delete = count - max_count
        cursor = self._conn.execute(
            """
            DELETE FROM embeddings
            WHERE content_hash IN (
                SELECT content_hash FROM embeddings
                ORDER BY last_accessed ASC
                LIMIT ?
            )
            """,
            (to_delete,),
        )
        self._conn.commit()

        removed = cursor.rowcount
        if removed > 0:
            logger.info(f"Cleaned up {removed} LRU embedding cache entries")
        return removed

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries removed
        """
        self._ensure_initialized()

        cursor = self._conn.execute("DELETE FROM embeddings")
        self._conn.commit()

        removed = cursor.rowcount
        logger.info(f"Cleared {removed} embedding cache entries")
        return removed

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats with hit/miss counts and cache size
        """
        self._ensure_initialized()

        # Update entry count
        self._stats.entries_count = self._conn.execute(
            "SELECT COUNT(*) FROM embeddings"
        ).fetchone()[0]

        # Get cache size
        self._stats.cache_size_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0

        return self._stats

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False


# Global cache instance
_embedding_cache: EmbeddingCache | None = None


def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance.

    Returns:
        Global EmbeddingCache instance
    """
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache


def reset_embedding_cache() -> None:
    """Reset the global embedding cache (for testing)."""
    global _embedding_cache
    if _embedding_cache is not None:
        _embedding_cache.close()
    _embedding_cache = None

