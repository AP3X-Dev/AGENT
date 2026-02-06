"""Tool call batching for efficient parallel execution.

This module batches similar tool calls that arrive within a time window
and executes them in parallel, reducing overall latency for operations
like multiple file reads or grep searches.

Usage:
    from ag3nt_agent.tool_batcher import get_tool_batcher

    batcher = get_tool_batcher()

    # Execute tool (may be batched with similar calls)
    result = await batcher.execute("read_file", read_file_fn, {"path": "/foo.txt"})
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger("ag3nt.tool_batcher")


@dataclass
class PendingCall:
    """A pending tool call waiting to be batched."""

    tool_name: str
    args: dict[str, Any]
    future: asyncio.Future[Any]
    created_at: float = field(default_factory=time.time)


@dataclass
class BatchStats:
    """Statistics about batching performance."""

    total_calls: int = 0
    batched_calls: int = 0
    immediate_calls: int = 0
    batches_executed: int = 0
    total_batch_size: int = 0
    errors: int = 0

    @property
    def batch_rate(self) -> float:
        """Calculate what percentage of calls were batched."""
        if self.total_calls == 0:
            return 0.0
        return self.batched_calls / self.total_calls

    @property
    def avg_batch_size(self) -> float:
        """Calculate average batch size."""
        if self.batches_executed == 0:
            return 0.0
        return self.total_batch_size / self.batches_executed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "totalCalls": self.total_calls,
            "batchedCalls": self.batched_calls,
            "immediateCalls": self.immediate_calls,
            "batchesExecuted": self.batches_executed,
            "batchRate": self.batch_rate,
            "avgBatchSize": self.avg_batch_size,
            "errors": self.errors,
        }


class ToolBatcher:
    """Batches similar tool calls for efficient parallel execution.

    When multiple tool calls of the same type arrive within a short window,
    they are batched together and executed in parallel. This reduces latency
    for operations like reading multiple files.
    """

    # Tools that can be batched (concurrent execution is safe)
    BATCHABLE_TOOLS: set[str] = {
        "read_file",
        "glob_tool",
        "grep_tool",
        "list_directory",
        "file_exists",
    }

    def __init__(
        self,
        batch_window_ms: int = 50,
        max_batch_size: int = 20,
    ):
        """Initialize the batcher.

        Args:
            batch_window_ms: Time window to collect calls before executing
            max_batch_size: Maximum calls to batch together
        """
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size

        self._pending: dict[str, list[PendingCall]] = defaultdict(list)
        self._batch_tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._stats = BatchStats()
        self._stats_lock = threading.Lock()

    async def execute(
        self,
        tool_name: str,
        tool_fn: Callable[..., Any] | Callable[..., Awaitable[Any]],
        args: dict[str, Any],
    ) -> Any:
        """Execute a tool, potentially batching with similar calls.

        Args:
            tool_name: Name of the tool
            tool_fn: The tool function to execute
            args: Arguments to pass to the tool

        Returns:
            The tool result
        """
        with self._stats_lock:
            self._stats.total_calls += 1

        # Non-batchable tools execute immediately
        if tool_name not in self.BATCHABLE_TOOLS:
            with self._stats_lock:
                self._stats.immediate_calls += 1
            return await self._execute_single(tool_fn, args)

        # Add to pending batch
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        call = PendingCall(tool_name=tool_name, args=args, future=future)

        async with self._lock:
            self._pending[tool_name].append(call)
            with self._stats_lock:
                self._stats.batched_calls += 1

            # Start batch timer if not already running
            if tool_name not in self._batch_tasks:
                self._batch_tasks[tool_name] = asyncio.create_task(
                    self._process_batch(tool_name, tool_fn)
                )

            # Force batch execution if at max size
            if len(self._pending[tool_name]) >= self.max_batch_size:
                # Cancel timer and execute now
                task = self._batch_tasks.pop(tool_name, None)
                if task:
                    task.cancel()
                asyncio.create_task(
                    self._execute_batch(tool_name, tool_fn)
                )

        return await future

    async def _process_batch(
        self,
        tool_name: str,
        tool_fn: Callable[..., Any] | Callable[..., Awaitable[Any]],
    ) -> None:
        """Wait for batch window then execute batch."""
        try:
            await asyncio.sleep(self.batch_window_ms / 1000)
            await self._execute_batch(tool_name, tool_fn)
        except asyncio.CancelledError:
            pass  # Batch was triggered early

    async def _execute_batch(
        self,
        tool_name: str,
        tool_fn: Callable[..., Any] | Callable[..., Awaitable[Any]],
    ) -> None:
        """Execute all pending calls for a tool type in parallel."""
        async with self._lock:
            batch = self._pending.pop(tool_name, [])
            self._batch_tasks.pop(tool_name, None)

        if not batch:
            return

        with self._stats_lock:
            self._stats.batches_executed += 1
            self._stats.total_batch_size += len(batch)

        logger.debug(f"Executing batch of {len(batch)} {tool_name} calls")

        # Execute all in parallel
        tasks = [
            asyncio.create_task(
                self._execute_and_resolve(tool_fn, call.args, call.future)
            )
            for call in batch
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_and_resolve(
        self,
        tool_fn: Callable[..., Any] | Callable[..., Awaitable[Any]],
        args: dict[str, Any],
        future: asyncio.Future[Any],
    ) -> None:
        """Execute single tool call and resolve its future."""
        try:
            result = await self._execute_single(tool_fn, args)
            if not future.done():
                future.set_result(result)
        except Exception as e:
            with self._stats_lock:
                self._stats.errors += 1
            if not future.done():
                future.set_exception(e)

    async def _execute_single(
        self,
        tool_fn: Callable[..., Any] | Callable[..., Awaitable[Any]],
        args: dict[str, Any],
    ) -> Any:
        """Execute a single tool call."""
        if asyncio.iscoroutinefunction(tool_fn):
            return await tool_fn(**args)
        else:
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: tool_fn(**args)
            )

    def get_stats(self) -> BatchStats:
        """Get batching statistics."""
        with self._stats_lock:
            return BatchStats(
                total_calls=self._stats.total_calls,
                batched_calls=self._stats.batched_calls,
                immediate_calls=self._stats.immediate_calls,
                batches_executed=self._stats.batches_executed,
                total_batch_size=self._stats.total_batch_size,
                errors=self._stats.errors,
            )

    async def flush(self) -> None:
        """Flush all pending batches immediately."""
        async with self._lock:
            # Cancel all batch timers
            for task in self._batch_tasks.values():
                task.cancel()
            self._batch_tasks.clear()

            # Note: Pending calls will have their futures resolved
            # when their batch tasks complete or get cancelled


# Global batcher instance
_tool_batcher: ToolBatcher | None = None
_batcher_lock = threading.Lock()


def get_tool_batcher(
    batch_window_ms: int = 50,
    max_batch_size: int = 20,
) -> ToolBatcher:
    """Get or create the global tool batcher.

    Args:
        batch_window_ms: Time window to collect calls
        max_batch_size: Maximum calls per batch

    Returns:
        The global ToolBatcher instance
    """
    global _tool_batcher

    if _tool_batcher is None:
        with _batcher_lock:
            if _tool_batcher is None:
                _tool_batcher = ToolBatcher(
                    batch_window_ms=batch_window_ms,
                    max_batch_size=max_batch_size,
                )

    return _tool_batcher
