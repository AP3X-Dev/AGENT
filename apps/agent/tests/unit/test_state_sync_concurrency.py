"""Concurrency tests for InMemoryStateSync."""

import asyncio
import pytest

from ag3nt_agent.state_sync import InMemoryStateSync, SessionState


class TestStateSyncConcurrency:
    """Tests proving InMemoryStateSync is safe under concurrent async access."""

    @pytest.fixture
    def sync(self):
        return InMemoryStateSync()

    @pytest.mark.asyncio
    async def test_concurrent_update_session(self, sync):
        """asyncio.gather 10 updates, verify version incremented correctly."""
        # Set initial session
        initial = SessionState(session_id="s1", version=1)
        await sync.set_session("s1", initial)

        async def update(i):
            await sync.update_session("s1", {"messageCount": i})

        await asyncio.gather(*[update(i) for i in range(10)])

        session = await sync.get_session("s1")
        assert session is not None
        # Each update increments version; with lock they should be sequential
        assert session.version == 11  # 1 initial + 10 updates

    @pytest.mark.asyncio
    async def test_concurrent_set_and_get(self, sync):
        """Concurrent set/get, no crash."""
        errors = []

        async def setter(i):
            try:
                state = SessionState(session_id=f"s{i}", version=1)
                await sync.set_session(f"s{i}", state)
            except Exception as e:
                errors.append(e)

        async def getter(i):
            try:
                await sync.get_session(f"s{i}")
            except Exception as e:
                errors.append(e)

        tasks = []
        for i in range(10):
            tasks.append(setter(i))
            tasks.append(getter(i))

        await asyncio.gather(*tasks)
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_and_notify(self, sync):
        """Subscribe while notifications fire, no iteration error."""
        state = SessionState(session_id="s1", version=1)
        await sync.set_session("s1", state)

        received = []
        errors = []

        def cb(s):
            received.append(s.session_id)

        async def subscribe_loop():
            try:
                for _ in range(5):
                    sync.subscribe("s1", cb)
                    await asyncio.sleep(0)
            except Exception as e:
                errors.append(e)

        async def update_loop():
            try:
                for i in range(5):
                    await sync.update_session("s1", {"messageCount": i})
            except Exception as e:
                errors.append(e)

        await asyncio.gather(subscribe_loop(), update_loop())
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_singleton_creation_concurrency(self):
        """asyncio.gather 10 calls to get_state_sync, verify same instance."""
        import ag3nt_agent.state_sync as mod

        # Reset singleton
        mod._state_sync = None

        results = []

        async def get():
            s = await mod.get_state_sync()
            results.append(id(s))

        await asyncio.gather(*[get() for _ in range(10)])

        # All should be the same instance
        assert len(set(results)) == 1

        # Clean up
        await mod.close_state_sync()
