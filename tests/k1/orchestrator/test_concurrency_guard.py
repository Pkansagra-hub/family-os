"""
Tests for ConcurrencyGuard (Issue 3.2.9).

Enforces single-DAG-at-a-time via asyncio.Lock.
NOT a DAGGuard -- used in OrchestratorService._process_one() before dispatch.

Test classes:
  TestConcurrencyGuardInit          -- Constructor, slots, repr.
  TestAcquireRelease                -- Basic lock/unlock lifecycle.
  TestNonBlockingReject             -- Second acquire fails immediately.
  TestReleaseInFinally              -- finally-block release pattern.
  TestConcurrentTasks               -- asyncio.gather concurrent attempts.
  TestDoubleRelease                 -- release() when not held is safe.
  TestActiveProperty                -- active property tracks state.
  TestReacquireAfterRelease         -- Lock reusable after release.
  TestNotDAGGuard                   -- Confirm not a DAGGuard subclass.
"""

from __future__ import annotations

import asyncio

import pytest

from k1.orchestrator.orchestration.guards import ConcurrencyGuard, DAGGuard

# ===========================================================================
# TestConcurrencyGuardInit
# ===========================================================================


class TestConcurrencyGuardInit:
    """Constructor, slots, repr."""

    def test_initial_state(self) -> None:
        guard = ConcurrencyGuard()
        assert guard.active is False
        assert guard._lock.locked() is False

    def test_repr_inactive(self) -> None:
        guard = ConcurrencyGuard()
        assert repr(guard) == "ConcurrencyGuard(active=False)"

    def test_has_slots(self) -> None:
        guard = ConcurrencyGuard()
        assert hasattr(guard, "__slots__")
        assert "_lock" in guard.__slots__
        assert "_active" in guard.__slots__


# ===========================================================================
# TestNotDAGGuard
# ===========================================================================


class TestNotDAGGuard:
    """ConcurrencyGuard is NOT a DAGGuard."""

    def test_not_dag_guard_subclass(self) -> None:
        guard = ConcurrencyGuard()
        assert not isinstance(guard, DAGGuard)

    def test_no_before_wave(self) -> None:
        guard = ConcurrencyGuard()
        assert not hasattr(guard, "before_wave")

    def test_no_after_step(self) -> None:
        guard = ConcurrencyGuard()
        assert not hasattr(guard, "after_step")

    def test_no_after_wave(self) -> None:
        guard = ConcurrencyGuard()
        assert not hasattr(guard, "after_wave")


# ===========================================================================
# TestAcquireRelease
# ===========================================================================


class TestAcquireRelease:
    """Basic lock/unlock lifecycle."""

    @pytest.mark.asyncio
    async def test_acquire_returns_true(self) -> None:
        guard = ConcurrencyGuard()
        result = await guard.acquire()
        assert result is True
        assert guard.active is True
        guard.release()

    @pytest.mark.asyncio
    async def test_release_makes_inactive(self) -> None:
        guard = ConcurrencyGuard()
        await guard.acquire()
        guard.release()
        assert guard.active is False
        assert guard._lock.locked() is False

    @pytest.mark.asyncio
    async def test_repr_while_active(self) -> None:
        guard = ConcurrencyGuard()
        await guard.acquire()
        assert repr(guard) == "ConcurrencyGuard(active=True)"
        guard.release()


# ===========================================================================
# TestNonBlockingReject
# ===========================================================================


class TestNonBlockingReject:
    """Second acquire fails immediately (non-blocking)."""

    @pytest.mark.asyncio
    async def test_second_acquire_returns_false(self) -> None:
        guard = ConcurrencyGuard()
        assert await guard.acquire() is True
        assert await guard.acquire() is False
        guard.release()

    @pytest.mark.asyncio
    async def test_third_acquire_also_false(self) -> None:
        guard = ConcurrencyGuard()
        await guard.acquire()
        assert await guard.acquire() is False
        assert await guard.acquire() is False
        guard.release()

    @pytest.mark.asyncio
    async def test_active_still_true_after_reject(self) -> None:
        guard = ConcurrencyGuard()
        await guard.acquire()
        await guard.acquire()  # rejected
        assert guard.active is True
        guard.release()


# ===========================================================================
# TestReleaseInFinally
# ===========================================================================


class TestReleaseInFinally:
    """finally-block release pattern covers exceptions."""

    @pytest.mark.asyncio
    async def test_release_after_exception(self) -> None:
        guard = ConcurrencyGuard()

        with pytest.raises(ValueError, match="boom"):
            try:
                await guard.acquire()
                raise ValueError("boom")
            finally:
                guard.release()

        assert guard.active is False
        assert guard._lock.locked() is False

    @pytest.mark.asyncio
    async def test_reacquire_after_exception_release(self) -> None:
        guard = ConcurrencyGuard()

        try:
            await guard.acquire()
            raise RuntimeError("dag failed")
        except RuntimeError:
            pass
        finally:
            guard.release()

        # Lock is reusable
        assert await guard.acquire() is True
        guard.release()


# ===========================================================================
# TestConcurrentTasks
# ===========================================================================


class TestConcurrentTasks:
    """asyncio.gather concurrent attempts -- only one wins."""

    @pytest.mark.asyncio
    async def test_only_one_acquires(self) -> None:
        guard = ConcurrencyGuard()
        results: list[bool] = []

        async def try_acquire(delay_ms: int) -> bool:
            await asyncio.sleep(delay_ms / 1000)
            acquired = await guard.acquire()
            results.append(acquired)
            return acquired

        # First task acquires, holds lock while others try
        await guard.acquire()

        tasks = [try_acquire(0), try_acquire(10), try_acquire(20)]
        await asyncio.gather(*tasks)

        # All three should fail since we already hold the lock
        assert results.count(True) == 0
        assert results.count(False) == 3

        guard.release()

    @pytest.mark.asyncio
    async def test_sequential_acquire_after_release(self) -> None:
        """Multiple sequential acquire-release cycles work."""
        guard = ConcurrencyGuard()

        for i in range(5):
            assert await guard.acquire() is True
            assert guard.active is True
            guard.release()
            assert guard.active is False

    @pytest.mark.asyncio
    async def test_two_tasks_one_wins(self) -> None:
        guard = ConcurrencyGuard()
        winner = None
        loser = None

        async def task_a() -> None:
            nonlocal winner, loser
            acquired = await guard.acquire()
            if acquired:
                winner = "A"
                await asyncio.sleep(0.05)
                guard.release()
            else:
                loser = "A"

        async def task_b() -> None:
            nonlocal winner, loser
            await asyncio.sleep(0.01)  # slight delay so A wins
            acquired = await guard.acquire()
            if acquired:
                winner = "B"
                await asyncio.sleep(0.01)
                guard.release()
            else:
                loser = "B"

        await asyncio.gather(task_a(), task_b())

        assert winner == "A"
        assert loser == "B"


# ===========================================================================
# TestDoubleRelease
# ===========================================================================


class TestDoubleRelease:
    """release() when not held is safe (logs warning, no-op)."""

    @pytest.mark.asyncio
    async def test_release_without_acquire(self) -> None:
        guard = ConcurrencyGuard()
        guard.release()  # Should not raise
        assert guard.active is False

    @pytest.mark.asyncio
    async def test_double_release(self) -> None:
        guard = ConcurrencyGuard()
        await guard.acquire()
        guard.release()
        guard.release()  # Second release should not raise
        assert guard.active is False

    @pytest.mark.asyncio
    async def test_release_noop_no_crash(self) -> None:
        guard = ConcurrencyGuard()
        # Multiple releases without acquire
        for _ in range(3):
            guard.release()
        assert guard.active is False


# ===========================================================================
# TestActiveProperty
# ===========================================================================


class TestActiveProperty:
    """active property tracks state correctly."""

    @pytest.mark.asyncio
    async def test_active_lifecycle(self) -> None:
        guard = ConcurrencyGuard()
        assert guard.active is False
        await guard.acquire()
        assert guard.active is True
        guard.release()
        assert guard.active is False

    @pytest.mark.asyncio
    async def test_active_false_on_rejected_acquire(self) -> None:
        """Rejected acquire does not change active state."""
        guard = ConcurrencyGuard()
        await guard.acquire()
        # Another attempt
        second_guard_view = guard.active
        await guard.acquire()  # rejected
        assert guard.active == second_guard_view  # unchanged (still True)
        guard.release()

    def test_active_is_property(self) -> None:
        """active is a read-only property."""
        assert isinstance(ConcurrencyGuard.active, property)


# ===========================================================================
# TestReacquireAfterRelease
# ===========================================================================


class TestReacquireAfterRelease:
    """Lock is reusable after release."""

    @pytest.mark.asyncio
    async def test_reacquire(self) -> None:
        guard = ConcurrencyGuard()
        assert await guard.acquire() is True
        guard.release()
        assert await guard.acquire() is True
        guard.release()

    @pytest.mark.asyncio
    async def test_reacquire_10_times(self) -> None:
        guard = ConcurrencyGuard()
        for _ in range(10):
            assert await guard.acquire() is True
            assert guard.active is True
            guard.release()
            assert guard.active is False

    @pytest.mark.asyncio
    async def test_acquire_after_rejected_then_released(self) -> None:
        """After a rejection and release, third party can acquire."""
        guard = ConcurrencyGuard()

        # First acquires
        await guard.acquire()
        # Second is rejected
        assert await guard.acquire() is False
        # First releases
        guard.release()
        # Now acquisition succeeds
        assert await guard.acquire() is True
        guard.release()
