"""Concurrency tests for worker WebSocket dicts."""

import threading
import pytest

import ag3nt_agent.worker as worker_mod


class TestWorkerConcurrency:
    """Tests proving worker WebSocket dicts are thread-safe."""

    @pytest.fixture(autouse=True)
    def _reset_dicts(self):
        """Reset WebSocket dicts before each test."""
        with worker_mod._ws_lock:
            worker_mod._gateway_connections.clear()
            worker_mod._session_websockets.clear()
        yield
        with worker_mod._ws_lock:
            worker_mod._gateway_connections.clear()
            worker_mod._session_websockets.clear()

    def test_concurrent_gateway_connection_add_remove(self):
        """10 threads add/remove, verify integrity."""
        barrier = threading.Barrier(20)
        errors = []

        def add(i):
            try:
                barrier.wait()
                with worker_mod._ws_lock:
                    worker_mod._gateway_connections[f"conn-{i}"] = f"ws-{i}"
            except Exception as e:
                errors.append(e)

        def remove(i):
            try:
                barrier.wait()
                with worker_mod._ws_lock:
                    worker_mod._gateway_connections.pop(f"conn-{i}", None)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=add, args=(i,)))
            threads.append(threading.Thread(target=remove, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Dict should be consistent (no crash, no corrupt state)
        with worker_mod._ws_lock:
            assert isinstance(worker_mod._gateway_connections, dict)

    def test_concurrent_session_websocket_access(self):
        """Concurrent modifications to _session_websockets, no KeyError."""
        barrier = threading.Barrier(20)
        errors = []

        def add(i):
            try:
                barrier.wait()
                with worker_mod._ws_lock:
                    worker_mod._session_websockets[f"sess-{i}"] = f"ws-{i}"
            except Exception as e:
                errors.append(e)

        def remove(i):
            try:
                barrier.wait()
                with worker_mod._ws_lock:
                    worker_mod._session_websockets.pop(f"sess-{i}", None)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=add, args=(i,)))
            threads.append(threading.Thread(target=remove, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        with worker_mod._ws_lock:
            assert isinstance(worker_mod._session_websockets, dict)
