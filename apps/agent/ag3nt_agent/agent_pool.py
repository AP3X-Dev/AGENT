"""Agent warm pool for fast turn execution.

This module provides a pool of pre-warmed agent instances to eliminate
cold start latency. Instead of building an agent on first request,
agents are pre-built and ready to serve immediately.

Usage:
    from ag3nt_agent.agent_pool import get_agent_pool

    pool = get_agent_pool()

    # Acquire an agent for a turn
    entry = pool.acquire()
    try:
        result = await run_turn_with_agent(entry["agent"], ...)
    finally:
        pool.release(entry)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ag3nt.agent_pool")


@dataclass
class PoolEntry:
    """A single agent pool entry."""

    agent: Any
    created_at: float = field(default_factory=time.time)
    turns_executed: int = 0
    last_used_at: float = field(default_factory=time.time)

    def is_stale(self, max_age_seconds: float) -> bool:
        """Check if this entry is too old."""
        return time.time() - self.created_at > max_age_seconds

    def is_exhausted(self, max_turns: int) -> bool:
        """Check if this entry has executed too many turns."""
        return self.turns_executed >= max_turns


@dataclass
class PoolStats:
    """Statistics about pool performance."""

    total_acquires: int = 0
    total_releases: int = 0
    pool_hits: int = 0
    pool_misses: int = 0
    retirements: int = 0
    current_size: int = 0
    warmups_started: int = 0
    warmups_completed: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate pool hit rate."""
        total = self.pool_hits + self.pool_misses
        return self.pool_hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "totalAcquires": self.total_acquires,
            "totalReleases": self.total_releases,
            "poolHits": self.pool_hits,
            "poolMisses": self.pool_misses,
            "hitRate": self.hit_rate,
            "retirements": self.retirements,
            "currentSize": self.current_size,
            "warmupsStarted": self.warmups_started,
            "warmupsCompleted": self.warmups_completed,
        }


class AgentPool:
    """Pool of pre-warmed agent instances for fast turn execution.

    The pool maintains a set of ready-to-use agent instances. When an agent
    is needed, it's acquired from the pool (fast) instead of being built
    from scratch (slow). After use, agents are returned to the pool for reuse.

    Agents are retired after a configurable number of turns or age to prevent
    memory leaks from accumulating conversation state.
    """

    def __init__(
        self,
        pool_size: int = 3,
        max_turns_per_agent: int = 100,
        max_age_seconds: float = 3600.0,  # 1 hour
        warmup_threshold: float = 0.5,  # Replenish when below 50%
    ):
        """Initialize the agent pool.

        Args:
            pool_size: Target number of agents to keep warm
            max_turns_per_agent: Retire agents after this many turns
            max_age_seconds: Retire agents older than this
            warmup_threshold: Start warming when pool falls below this fraction
        """
        self.pool_size = pool_size
        self.max_turns_per_agent = max_turns_per_agent
        self.max_age_seconds = max_age_seconds
        self.warmup_threshold = warmup_threshold

        self._pool: deque[PoolEntry] = deque()
        self._lock = threading.Lock()
        self._warming = False
        self._stats = PoolStats()
        self._initialized = False
        self._shutdown = False

    def initialize(self) -> None:
        """Pre-warm the agent pool.

        This should be called at startup to populate the pool with
        ready-to-use agents.
        """
        if self._initialized:
            return

        logger.info(f"Initializing agent pool with {self.pool_size} agents...")
        start_time = time.time()

        for i in range(self.pool_size):
            try:
                agent = self._build_agent()
                entry = PoolEntry(agent=agent)
                with self._lock:
                    self._pool.append(entry)
                    self._stats.warmups_completed += 1
                logger.debug(f"Warmed agent {i + 1}/{self.pool_size}")
            except Exception as e:
                logger.error(f"Failed to warm agent {i + 1}: {e}")

        self._initialized = True
        elapsed = time.time() - start_time
        logger.info(
            f"Agent pool initialized: {len(self._pool)} agents in {elapsed:.2f}s"
        )

    async def initialize_async(self) -> None:
        """Pre-warm the agent pool asynchronously."""
        if self._initialized:
            return

        logger.info(f"Initializing agent pool with {self.pool_size} agents...")
        start_time = time.time()

        loop = asyncio.get_event_loop()

        # Build agents in parallel using thread pool
        async def build_one(index: int) -> PoolEntry | None:
            try:
                agent = await loop.run_in_executor(None, self._build_agent)
                self._stats.warmups_completed += 1
                logger.debug(f"Warmed agent {index + 1}/{self.pool_size}")
                return PoolEntry(agent=agent)
            except Exception as e:
                logger.error(f"Failed to warm agent {index + 1}: {e}")
                return None

        # Build all agents concurrently
        entries = await asyncio.gather(
            *[build_one(i) for i in range(self.pool_size)]
        )

        with self._lock:
            for entry in entries:
                if entry is not None:
                    self._pool.append(entry)

        self._initialized = True
        elapsed = time.time() - start_time
        logger.info(
            f"Agent pool initialized: {len(self._pool)} agents in {elapsed:.2f}s"
        )

    def acquire(self) -> PoolEntry:
        """Acquire an agent from the pool.

        Returns a PoolEntry containing the agent. The entry must be
        returned via release() when done.

        If the pool is empty, a new agent is built on demand (slower).
        """
        with self._lock:
            self._stats.total_acquires += 1

            # Try to get from pool
            while self._pool:
                entry = self._pool.popleft()

                # Check if entry is still valid
                if entry.is_stale(self.max_age_seconds):
                    self._stats.retirements += 1
                    logger.debug("Retired stale agent from pool")
                    continue

                if entry.is_exhausted(self.max_turns_per_agent):
                    self._stats.retirements += 1
                    logger.debug("Retired exhausted agent from pool")
                    continue

                # Valid entry found
                self._stats.pool_hits += 1
                self._stats.current_size = len(self._pool)

                # Trigger replenishment if needed
                if len(self._pool) < self.pool_size * self.warmup_threshold:
                    self._replenish_async()

                return entry

            # Pool exhausted
            self._stats.pool_misses += 1

        logger.warning("Pool exhausted, building agent on demand")

        agent = self._build_agent()
        return PoolEntry(agent=agent)

    async def acquire_async(self) -> PoolEntry:
        """Acquire an agent asynchronously.

        Same as acquire() but builds agent in thread pool if pool is empty.
        """
        with self._lock:
            self._stats.total_acquires += 1

            # Try to get from pool
            while self._pool:
                entry = self._pool.popleft()

                # Check if entry is still valid
                if entry.is_stale(self.max_age_seconds):
                    self._stats.retirements += 1
                    continue

                if entry.is_exhausted(self.max_turns_per_agent):
                    self._stats.retirements += 1
                    continue

                # Valid entry found
                self._stats.pool_hits += 1
                self._stats.current_size = len(self._pool)

                # Trigger replenishment if needed
                if len(self._pool) < self.pool_size * self.warmup_threshold:
                    self._replenish_async()

                return entry

            # Pool exhausted
            self._stats.pool_misses += 1

        logger.warning("Pool exhausted, building agent on demand")

        loop = asyncio.get_event_loop()
        agent = await loop.run_in_executor(None, self._build_agent)
        return PoolEntry(agent=agent)

    def release(self, entry: PoolEntry) -> None:
        """Return an agent to the pool.

        Args:
            entry: The PoolEntry acquired earlier
        """
        entry.turns_executed += 1
        entry.last_used_at = time.time()

        # Check if should retire
        with self._lock:
            self._stats.total_releases += 1

            if entry.is_stale(self.max_age_seconds):
                self._stats.retirements += 1
                logger.debug("Retiring stale agent on release")
                return

            if entry.is_exhausted(self.max_turns_per_agent):
                self._stats.retirements += 1
                logger.debug("Retiring exhausted agent on release")
                return

            if self._shutdown:
                return

            # Only add back if pool isn't overfull
            if len(self._pool) < self.pool_size:
                self._pool.append(entry)
                self._stats.current_size = len(self._pool)

    def get_stats(self) -> PoolStats:
        """Get pool statistics."""
        with self._lock:
            self._stats.current_size = len(self._pool)
            return PoolStats(
                total_acquires=self._stats.total_acquires,
                total_releases=self._stats.total_releases,
                pool_hits=self._stats.pool_hits,
                pool_misses=self._stats.pool_misses,
                retirements=self._stats.retirements,
                current_size=len(self._pool),
                warmups_started=self._stats.warmups_started,
                warmups_completed=self._stats.warmups_completed,
            )

    def shutdown(self) -> None:
        """Shutdown the pool and release all agents."""
        logger.info("Shutting down agent pool")
        self._shutdown = True

        with self._lock:
            self._pool.clear()
            self._stats.current_size = 0

    def _build_agent(self) -> Any:
        """Build a new agent instance."""
        from ag3nt_agent.deepagents_runtime import _build_agent

        return _build_agent()

    def _replenish_async(self) -> None:
        """Replenish pool in background thread.

        Note: This method may be called with self._lock held (from acquire),
        so we only check/set _warming under the existing lock context.
        """
        # _lock is already held by caller (acquire/acquire_async)
        if self._warming or self._shutdown:
            return

        self._warming = True
        self._stats.warmups_started += 1

        def build_and_add():
            try:
                agent = self._build_agent()
                entry = PoolEntry(agent=agent)

                with self._lock:
                    if not self._shutdown and len(self._pool) < self.pool_size:
                        self._pool.append(entry)
                        self._stats.warmups_completed += 1
                        self._stats.current_size = len(self._pool)
                        logger.debug("Background warmup completed")
            except Exception as e:
                logger.error(f"Background warmup failed: {e}")
            finally:
                with self._lock:
                    self._warming = False

        thread = threading.Thread(target=build_and_add, daemon=True)
        thread.start()


# Global pool instance
_agent_pool: AgentPool | None = None
_pool_lock = threading.Lock()


def get_agent_pool(
    pool_size: int = 3,
    max_turns_per_agent: int = 100,
) -> AgentPool:
    """Get or create the global agent pool.

    Args:
        pool_size: Target number of warm agents
        max_turns_per_agent: Retire agents after this many turns

    Returns:
        The global AgentPool instance
    """
    global _agent_pool

    if _agent_pool is None:
        with _pool_lock:
            if _agent_pool is None:
                _agent_pool = AgentPool(
                    pool_size=pool_size,
                    max_turns_per_agent=max_turns_per_agent,
                )

    return _agent_pool


def initialize_pool(pool_size: int = 3) -> None:
    """Initialize the global agent pool.

    Call this at application startup to pre-warm agents.
    """
    pool = get_agent_pool(pool_size=pool_size)
    pool.initialize()


async def initialize_pool_async(pool_size: int = 3) -> None:
    """Initialize the global agent pool asynchronously.

    Call this at application startup to pre-warm agents.
    """
    pool = get_agent_pool(pool_size=pool_size)
    await pool.initialize_async()


def shutdown_pool() -> None:
    """Shutdown the global agent pool."""
    global _agent_pool

    if _agent_pool is not None:
        _agent_pool.shutdown()
        _agent_pool = None
