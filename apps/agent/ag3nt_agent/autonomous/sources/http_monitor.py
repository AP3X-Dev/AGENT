"""
HTTP Monitor Event Source

Monitors HTTP endpoints and emits events based on health checks.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

from ..event_bus import Event, EventBus, EventPriority

logger = logging.getLogger(__name__)


@dataclass
class HTTPEndpoint:
    """Configuration for an HTTP endpoint to monitor."""
    id: str
    url: str
    method: str = "GET"
    expected_status: int = 200
    timeout_seconds: float = 10.0
    interval_seconds: float = 60.0
    headers: dict = field(default_factory=dict)
    alert_on_status: list[int] = field(default_factory=lambda: [500, 502, 503, 504])
    alert_on_timeout: bool = True
    response_time_threshold_ms: int = 5000

    @classmethod
    def from_dict(cls, data: dict) -> "HTTPEndpoint":
        return cls(
            id=data["id"],
            url=data["url"],
            method=data.get("method", "GET"),
            expected_status=data.get("expected_status", 200),
            timeout_seconds=data.get("timeout_seconds", 10.0),
            interval_seconds=data.get("interval_seconds", 60.0),
            headers=data.get("headers", {}),
            alert_on_status=data.get("alert_on_status", [500, 502, 503, 504]),
            alert_on_timeout=data.get("alert_on_timeout", True),
            response_time_threshold_ms=data.get("response_time_threshold_ms", 5000)
        )


@dataclass
class CheckResult:
    """Result of an HTTP health check."""
    endpoint_id: str
    url: str
    success: bool
    status_code: Optional[int] = None
    response_time_ms: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class HTTPMonitor:
    """
    Monitors HTTP endpoints and emits events to the Event Bus.

    Performs periodic health checks and emits events when:
    - Endpoints return error status codes
    - Endpoints timeout
    - Response time exceeds threshold
    - Endpoints recover from failure
    """

    def __init__(self, event_bus: EventBus):
        """
        Initialize the HTTP monitor.

        Args:
            event_bus: Event bus to publish events to
        """
        self.event_bus = event_bus
        self._endpoints: dict[str, HTTPEndpoint] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._client: Optional[httpx.AsyncClient] = None

        # Track endpoint states for recovery detection
        self._last_results: dict[str, CheckResult] = {}

    async def start(self):
        """Start monitoring all configured endpoints."""
        if self._running:
            return

        self._running = True
        self._client = httpx.AsyncClient()

        # Start monitoring tasks for each endpoint
        for endpoint_id, endpoint in self._endpoints.items():
            task = asyncio.create_task(self._monitor_endpoint(endpoint))
            self._tasks[endpoint_id] = task

        logger.info(f"HTTP monitor started with {len(self._endpoints)} endpoints")

    async def stop(self):
        """Stop all monitoring tasks."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks.values():
            task.cancel()

        # Wait for cancellation
        for task in self._tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()

        # Close HTTP client
        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("HTTP monitor stopped")

    def add_endpoint(self, endpoint: HTTPEndpoint):
        """
        Add an endpoint to monitor.

        Args:
            endpoint: Endpoint configuration
        """
        self._endpoints[endpoint.id] = endpoint

        # If already running, start monitoring this endpoint
        if self._running:
            task = asyncio.create_task(self._monitor_endpoint(endpoint))
            self._tasks[endpoint.id] = task

        logger.info(f"Added HTTP endpoint: {endpoint.id} ({endpoint.url})")

    def remove_endpoint(self, endpoint_id: str) -> bool:
        """
        Remove an endpoint from monitoring.

        Args:
            endpoint_id: ID of endpoint to remove

        Returns:
            True if removed, False if not found
        """
        if endpoint_id not in self._endpoints:
            return False

        # Cancel monitoring task
        if endpoint_id in self._tasks:
            self._tasks[endpoint_id].cancel()
            del self._tasks[endpoint_id]

        del self._endpoints[endpoint_id]
        self._last_results.pop(endpoint_id, None)

        logger.info(f"Removed HTTP endpoint: {endpoint_id}")
        return True

    async def _monitor_endpoint(self, endpoint: HTTPEndpoint):
        """Monitoring loop for a single endpoint."""
        while self._running:
            try:
                result = await self._check_endpoint(endpoint)
                await self._process_result(endpoint, result)

                # Wait for next check
                await asyncio.sleep(endpoint.interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring {endpoint.id}: {e}")
                await asyncio.sleep(endpoint.interval_seconds)

    async def _check_endpoint(self, endpoint: HTTPEndpoint) -> CheckResult:
        """Perform a health check on an endpoint."""
        start_time = datetime.utcnow()

        try:
            response = await self._client.request(
                method=endpoint.method,
                url=endpoint.url,
                headers=endpoint.headers,
                timeout=endpoint.timeout_seconds
            )

            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            success = response.status_code == endpoint.expected_status

            return CheckResult(
                endpoint_id=endpoint.id,
                url=endpoint.url,
                success=success,
                status_code=response.status_code,
                response_time_ms=elapsed_ms
            )

        except httpx.TimeoutException:
            return CheckResult(
                endpoint_id=endpoint.id,
                url=endpoint.url,
                success=False,
                error="Timeout"
            )

        except Exception as e:
            return CheckResult(
                endpoint_id=endpoint.id,
                url=endpoint.url,
                success=False,
                error=str(e)
            )

    async def _process_result(self, endpoint: HTTPEndpoint, result: CheckResult):
        """Process a check result and emit events as needed."""
        previous = self._last_results.get(endpoint.id)
        self._last_results[endpoint.id] = result

        # Determine if we should emit an event
        should_emit = False
        priority = EventPriority.MEDIUM

        if not result.success:
            should_emit = True

            # Check for error status codes
            if result.status_code in endpoint.alert_on_status:
                priority = EventPriority.HIGH

            # Check for timeout
            elif result.error == "Timeout" and endpoint.alert_on_timeout:
                priority = EventPriority.HIGH

        # Check for slow response
        elif result.response_time_ms > endpoint.response_time_threshold_ms:
            should_emit = True
            priority = EventPriority.MEDIUM

        # Check for recovery (was failed, now success)
        elif previous and not previous.success and result.success:
            should_emit = True
            priority = EventPriority.LOW

        if should_emit:
            event = Event(
                event_type="http_check",
                source=f"http_monitor:{endpoint.id}",
                payload={
                    "endpoint_id": endpoint.id,
                    "url": endpoint.url,
                    "success": result.success,
                    "status_code": result.status_code,
                    "response_time_ms": result.response_time_ms,
                    "error": result.error,
                    "recovered": previous and not previous.success and result.success
                },
                priority=priority
            )

            await self.event_bus.publish(event)

            logger.info(
                f"HTTP check event: {endpoint.id} - "
                f"{'OK' if result.success else 'FAIL'} "
                f"({result.status_code or result.error})"
            )

    def get_status(self) -> dict:
        """Get monitor status."""
        statuses = {}
        for endpoint_id, endpoint in self._endpoints.items():
            result = self._last_results.get(endpoint_id)
            statuses[endpoint_id] = {
                "url": endpoint.url,
                "status": "healthy" if result and result.success else "unhealthy",
                "last_check": result.timestamp.isoformat() if result else None,
                "response_time_ms": result.response_time_ms if result else None,
                "last_error": result.error if result else None
            }

        return {
            "running": self._running,
            "endpoint_count": len(self._endpoints),
            "endpoints": statuses
        }
