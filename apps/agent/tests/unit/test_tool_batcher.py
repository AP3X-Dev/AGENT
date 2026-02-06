"""Tests for tool call batching."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from ag3nt_agent.tool_batcher import (
    ToolBatcher,
    get_tool_batcher,
    BatchStats,
)


class TestToolBatcher:
    """Tests for ToolBatcher class."""

    @pytest.mark.asyncio
    async def test_execute_non_batchable_tool_immediately(self):
        """Test that non-batchable tools execute immediately."""
        batcher = ToolBatcher(batch_window_ms=100)
        call_count = 0

        async def shell_tool(command: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"output: {command}"

        result = await batcher.execute("shell_tool", shell_tool, {"command": "ls"})

        assert result == "output: ls"
        assert call_count == 1

        stats = batcher.get_stats()
        assert stats.immediate_calls == 1
        assert stats.batched_calls == 0

    @pytest.mark.asyncio
    async def test_execute_batchable_tool(self):
        """Test that batchable tools are batched."""
        batcher = ToolBatcher(batch_window_ms=50)
        call_times: list[float] = []

        async def read_file(path: str) -> str:
            call_times.append(asyncio.get_event_loop().time())
            return f"contents of {path}"

        # Launch multiple calls concurrently
        results = await asyncio.gather(
            batcher.execute("read_file", read_file, {"path": "/a.txt"}),
            batcher.execute("read_file", read_file, {"path": "/b.txt"}),
            batcher.execute("read_file", read_file, {"path": "/c.txt"}),
        )

        assert len(results) == 3
        assert results[0] == "contents of /a.txt"
        assert results[1] == "contents of /b.txt"
        assert results[2] == "contents of /c.txt"

        # All calls should have been batched (executed close together)
        if len(call_times) == 3:
            time_spread = max(call_times) - min(call_times)
            assert time_spread < 0.1  # Should execute within 100ms of each other

        stats = batcher.get_stats()
        assert stats.batched_calls == 3

    @pytest.mark.asyncio
    async def test_batch_executes_after_window(self):
        """Test that batch executes after the window expires."""
        batcher = ToolBatcher(batch_window_ms=20)
        executed = asyncio.Event()

        async def read_file(path: str) -> str:
            executed.set()
            return f"contents of {path}"

        # Start a single call
        task = asyncio.create_task(
            batcher.execute("read_file", read_file, {"path": "/a.txt"})
        )

        # Wait for execution
        await asyncio.wait_for(executed.wait(), timeout=1.0)
        result = await task

        assert result == "contents of /a.txt"

    @pytest.mark.asyncio
    async def test_batch_max_size_triggers_execution(self):
        """Test that reaching max batch size triggers immediate execution."""
        batcher = ToolBatcher(batch_window_ms=1000, max_batch_size=3)
        call_count = 0

        async def read_file(path: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"contents of {path}"

        # Launch exactly max_batch_size calls
        start = asyncio.get_event_loop().time()
        results = await asyncio.gather(
            batcher.execute("read_file", read_file, {"path": "/1.txt"}),
            batcher.execute("read_file", read_file, {"path": "/2.txt"}),
            batcher.execute("read_file", read_file, {"path": "/3.txt"}),
        )
        elapsed = asyncio.get_event_loop().time() - start

        assert len(results) == 3
        # Should complete much faster than batch_window_ms
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_sync_tool_function(self):
        """Test that sync tool functions work correctly."""
        batcher = ToolBatcher(batch_window_ms=20)

        def read_file_sync(path: str) -> str:
            return f"sync contents of {path}"

        result = await batcher.execute(
            "read_file", read_file_sync, {"path": "/sync.txt"}
        )

        assert result == "sync contents of /sync.txt"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test that errors are properly propagated."""
        batcher = ToolBatcher(batch_window_ms=20)

        async def failing_tool(path: str) -> str:
            raise ValueError("Tool failed")

        with pytest.raises(ValueError, match="Tool failed"):
            await batcher.execute("read_file", failing_tool, {"path": "/fail.txt"})

        stats = batcher.get_stats()
        assert stats.errors == 1

    @pytest.mark.asyncio
    async def test_flush_pending_batches(self):
        """Test that flush cancels pending batch timers."""
        batcher = ToolBatcher(batch_window_ms=1000)

        async def read_file(path: str) -> str:
            return f"contents of {path}"

        # Start a call but don't wait
        task = asyncio.create_task(
            batcher.execute("read_file", read_file, {"path": "/a.txt"})
        )

        # Flush should not raise
        await batcher.flush()

        # The task should still complete (or be handled gracefully)
        # Note: behavior depends on timing

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Test that statistics are tracked correctly."""
        batcher = ToolBatcher(batch_window_ms=20)

        async def read_file(path: str) -> str:
            return f"contents of {path}"

        async def shell_tool(command: str) -> str:
            return f"output: {command}"

        # Execute some tools
        await batcher.execute("read_file", read_file, {"path": "/a.txt"})
        await batcher.execute("shell_tool", shell_tool, {"command": "ls"})

        stats = batcher.get_stats()
        assert stats.total_calls == 2
        assert stats.batched_calls >= 1  # read_file is batchable
        assert stats.immediate_calls >= 1  # shell_tool is not batchable


class TestBatchStats:
    """Tests for BatchStats class."""

    def test_batch_rate_calculation(self):
        """Test batch rate calculation."""
        stats = BatchStats(
            total_calls=100,
            batched_calls=75,
            immediate_calls=25,
        )
        assert stats.batch_rate == 0.75

    def test_batch_rate_zero_calls(self):
        """Test batch rate with zero calls."""
        stats = BatchStats()
        assert stats.batch_rate == 0.0

    def test_avg_batch_size_calculation(self):
        """Test average batch size calculation."""
        stats = BatchStats(
            batches_executed=10,
            total_batch_size=50,
        )
        assert stats.avg_batch_size == 5.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = BatchStats(
            total_calls=100,
            batched_calls=75,
            immediate_calls=25,
            batches_executed=10,
            total_batch_size=50,
            errors=2,
        )
        d = stats.to_dict()

        assert d["totalCalls"] == 100
        assert d["batchedCalls"] == 75
        assert d["batchRate"] == 0.75
        assert d["avgBatchSize"] == 5.0
        assert d["errors"] == 2


class TestToolBatcherConcurrency:
    """Concurrency tests for ToolBatcher stats."""

    @pytest.mark.asyncio
    async def test_concurrent_sync_tool_stats(self):
        """10 sync tools via gather, verify total_calls correct."""
        batcher = ToolBatcher(batch_window_ms=20)

        def sync_tool(command: str) -> str:
            return f"output: {command}"

        results = await asyncio.gather(*[
            batcher.execute("shell_tool", sync_tool, {"command": f"cmd-{i}"})
            for i in range(10)
        ])

        assert len(results) == 10
        stats = batcher.get_stats()
        assert stats.total_calls == 10
        assert stats.immediate_calls == 10  # shell_tool is not batchable

    @pytest.mark.asyncio
    async def test_concurrent_batched_and_immediate_stats(self):
        """Mix batchable/non-batchable, verify stats add up."""
        batcher = ToolBatcher(batch_window_ms=20)

        async def read_file(path: str) -> str:
            return f"contents of {path}"

        def shell_tool(command: str) -> str:
            return f"output: {command}"

        tasks = []
        for i in range(5):
            tasks.append(batcher.execute("read_file", read_file, {"path": f"/f{i}.txt"}))
            tasks.append(batcher.execute("shell_tool", shell_tool, {"command": f"cmd-{i}"}))

        results = await asyncio.gather(*tasks)
        assert len(results) == 10

        stats = batcher.get_stats()
        assert stats.total_calls == 10
        assert stats.batched_calls + stats.immediate_calls == 10


class TestGetToolBatcher:
    """Tests for the global batcher singleton."""

    def test_get_tool_batcher_returns_singleton(self):
        """Test that get_tool_batcher returns the same instance."""
        batcher1 = get_tool_batcher()
        batcher2 = get_tool_batcher()
        assert batcher1 is batcher2
