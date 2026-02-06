"""Tests for agent warm pool."""

import threading
import pytest
import time
from unittest.mock import patch, MagicMock

from ag3nt_agent.agent_pool import (
    AgentPool,
    PoolEntry,
    PoolStats,
    get_agent_pool,
    shutdown_pool,
)


class TestPoolEntry:
    """Tests for PoolEntry class."""

    def test_is_stale(self):
        """Test stale detection."""
        entry = PoolEntry(agent=MagicMock())
        entry.created_at = time.time() - 100

        assert entry.is_stale(50) is True
        assert entry.is_stale(200) is False

    def test_is_exhausted(self):
        """Test exhaustion detection."""
        entry = PoolEntry(agent=MagicMock())
        entry.turns_executed = 50

        assert entry.is_exhausted(25) is True
        assert entry.is_exhausted(100) is False


class TestPoolStats:
    """Tests for PoolStats class."""

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = PoolStats(pool_hits=75, pool_misses=25)
        assert stats.hit_rate == 0.75

    def test_hit_rate_zero_acquires(self):
        """Test hit rate with zero acquires."""
        stats = PoolStats()
        assert stats.hit_rate == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = PoolStats(
            total_acquires=100,
            total_releases=95,
            pool_hits=80,
            pool_misses=20,
            retirements=5,
            current_size=3,
        )
        d = stats.to_dict()

        assert d["totalAcquires"] == 100
        assert d["totalReleases"] == 95
        assert d["poolHits"] == 80
        assert d["hitRate"] == 0.8
        assert d["currentSize"] == 3


class TestAgentPool:
    """Tests for AgentPool class."""

    def test_acquire_from_empty_pool_builds_agent(self):
        """Test that acquiring from empty pool builds new agent."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3)
            # Don't initialize - pool is empty

            entry = pool.acquire()

            assert entry.agent is mock_agent
            assert entry.turns_executed == 0

            stats = pool.get_stats()
            assert stats.pool_misses == 1

    def test_initialize_warms_pool(self):
        """Test that initialize pre-warms the pool."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3)
            pool.initialize()

            stats = pool.get_stats()
            assert stats.current_size == 3
            assert stats.warmups_completed == 3

    def test_acquire_from_warmed_pool(self):
        """Test acquiring from a warmed pool."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3)
            pool.initialize()

            entry = pool.acquire()

            assert entry.agent is mock_agent

            stats = pool.get_stats()
            assert stats.pool_hits == 1
            assert stats.current_size == 2  # One removed

    def test_release_returns_agent_to_pool(self):
        """Test that release returns agent to pool."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3)
            pool.initialize()

            entry = pool.acquire()
            initial_size = pool.get_stats().current_size

            pool.release(entry)

            stats = pool.get_stats()
            assert stats.current_size == initial_size + 1
            assert entry.turns_executed == 1

    def test_release_retires_exhausted_agent(self):
        """Test that exhausted agents are retired on release."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3, max_turns_per_agent=5)
            pool.initialize()

            entry = pool.acquire()
            entry.turns_executed = 4  # One more turn will exhaust

            pool.release(entry)

            stats = pool.get_stats()
            assert stats.retirements == 1

    def test_release_retires_stale_agent(self):
        """Test that stale agents are retired on release."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3, max_age_seconds=1.0)
            pool.initialize()

            entry = pool.acquire()
            entry.created_at = time.time() - 10  # Make stale

            pool.release(entry)

            stats = pool.get_stats()
            assert stats.retirements == 1

    def test_acquire_skips_stale_entries(self):
        """Test that stale entries are skipped during acquire."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3, max_age_seconds=1.0)
            pool.initialize()

            # Make all entries stale
            for entry in pool._pool:
                entry.created_at = time.time() - 10

            # Acquire should build new agent
            entry = pool.acquire()

            stats = pool.get_stats()
            assert stats.retirements >= 1  # Stale ones retired

    def test_shutdown_clears_pool(self):
        """Test that shutdown clears the pool."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3)
            pool.initialize()

            pool.shutdown()

            stats = pool.get_stats()
            assert stats.current_size == 0

    @pytest.mark.asyncio
    async def test_initialize_async(self):
        """Test async initialization."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=2)
            await pool.initialize_async()

            stats = pool.get_stats()
            assert stats.current_size == 2

    @pytest.mark.asyncio
    async def test_acquire_async(self):
        """Test async acquire."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=2)
            await pool.initialize_async()

            entry = await pool.acquire_async()

            assert entry.agent is mock_agent

            stats = pool.get_stats()
            assert stats.pool_hits == 1


class TestAgentPoolConcurrency:
    """Concurrency tests for AgentPool."""

    def test_concurrent_acquire_stats(self):
        """10 threads acquire, verify total_acquires == 10."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=3)
            barrier = threading.Barrier(10)

            def do_acquire():
                barrier.wait()
                pool.acquire()

            threads = [threading.Thread(target=do_acquire) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            stats = pool.get_stats()
            assert stats.total_acquires == 10

    def test_concurrent_release_stats(self):
        """10 threads release, verify total_releases == 10."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=20, max_turns_per_agent=100)
            # Acquire 10 entries
            entries = [pool.acquire() for _ in range(10)]

            barrier = threading.Barrier(10)

            def do_release(entry):
                barrier.wait()
                pool.release(entry)

            threads = [threading.Thread(target=do_release, args=(e,)) for e in entries]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            stats = pool.get_stats()
            assert stats.total_releases == 10

    def test_replenish_only_starts_once(self):
        """Sequential calls to _replenish_async under lock, verify warmups_started increments by exactly 1."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=5)
            initial_warmups = pool._stats.warmups_started

            # Call _replenish_async multiple times while _warming is still True
            # (before the background thread has a chance to reset it)
            with pool._lock:
                pool._replenish_async()  # Should set _warming=True
                pool._replenish_async()  # Should be a no-op (_warming=True)
                pool._replenish_async()  # Should be a no-op (_warming=True)

            # Only one warmup should have been started
            assert pool._stats.warmups_started == initial_warmups + 1

    def test_concurrent_acquire_and_release(self):
        """Mixed acquire/release, verify stats consistent."""
        mock_agent = MagicMock()

        with patch(
            "ag3nt_agent.agent_pool.AgentPool._build_agent",
            return_value=mock_agent,
        ):
            pool = AgentPool(pool_size=5, max_turns_per_agent=100)
            barrier = threading.Barrier(10)
            acquired = []
            lock = threading.Lock()

            def acquire():
                barrier.wait()
                entry = pool.acquire()
                with lock:
                    acquired.append(entry)

            def release():
                barrier.wait()
                time.sleep(0.01)  # Let acquires happen first
                with lock:
                    if acquired:
                        entry = acquired.pop()
                    else:
                        return
                pool.release(entry)

            threads = []
            for _ in range(5):
                threads.append(threading.Thread(target=acquire))
                threads.append(threading.Thread(target=release))

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            stats = pool.get_stats()
            assert stats.total_acquires == 5
            # Releases may be fewer if acquire hadn't completed yet


class TestGetAgentPool:
    """Tests for the global pool singleton."""

    def test_get_agent_pool_returns_singleton(self):
        """Test that get_agent_pool returns same instance."""
        # Note: We need to reset global state for clean test
        import ag3nt_agent.agent_pool as pool_module

        pool_module._agent_pool = None

        pool1 = get_agent_pool()
        pool2 = get_agent_pool()

        assert pool1 is pool2

        # Cleanup
        shutdown_pool()
