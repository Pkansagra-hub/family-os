"""
M7 E7.4 -- Dependency Ordering + Ready Queue tests.

Covers:
  - 7.4.1: ReadyQueue with enqueue/dequeue_ready/notify_completed
  - 7.4.2: Coordinator wiring (notify_completed on task done, dispatch released)
  - 7.4.3: Circular and missing dependency detection

Test count target: ~40 tests (extending 2243 -> ~2283).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# =====================================================================
# Helpers -- lightweight Envelope stub for queue tests
# =====================================================================


@dataclass
class _StubEnvelope:
    """Minimal envelope for ReadyQueue tests."""

    topic: str = "k1.orchestration.task.dispatch.v1"
    payload: bytes = b"{}"
    envelope_id: int = 1
    parent_id: int = 0

    @classmethod
    def with_task(
        cls,
        task_id: str,
        depends_on: str | None = None,
        **kwargs: Any,
    ) -> _StubEnvelope:
        payload_dict: dict[str, Any] = {"task_id": task_id}
        if depends_on is not None:
            payload_dict["depends_on"] = depends_on
        payload = json.dumps(payload_dict).encode()
        return cls(payload=payload, **kwargs)


_NEXT_EID = 100


def _make_env(
    task_id: str,
    depends_on: str | None = None,
) -> _StubEnvelope:
    """Create a stub envelope with unique envelope_id."""
    global _NEXT_EID
    _NEXT_EID += 1
    return _StubEnvelope.with_task(
        task_id=task_id,
        depends_on=depends_on,
        envelope_id=_NEXT_EID,
    )


# =====================================================================
# 7.4.1 -- ReadyQueue class
# =====================================================================


class TestReadyQueueInit:
    """Test ReadyQueue initialization."""

    def test_creation(self):
        """ReadyQueue can be created with default state."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        assert q.ready_count == 0
        assert q.waiting_count == 0
        assert q.total_pending == 0

    def test_initial_stats_zero(self):
        """All stats start at zero."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        stats = q.get_stats()
        assert all(v == 0 for v in stats.values())

    def test_repr(self):
        """ReadyQueue has informative repr."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        r = repr(q)
        assert "ReadyQueue" in r
        assert "ready=0" in r
        assert "waiting=0" in r

    def test_all_export(self):
        """ReadyQueue is in __all__."""
        from poc.k1_poc.actors import ready_queue

        assert "ReadyQueue" in ready_queue.__all__


class TestReadyQueueEnqueueNoDeps:
    """Test enqueue without dependencies (immediately ready)."""

    def test_no_dependency_immediate(self):
        """Envelope without depends_on is immediately ready."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        env = _make_env("task-1")
        status, failed = q.enqueue(env, depends_on=None)
        assert status == "immediate"
        assert failed == []
        assert q.ready_count == 1

    def test_dequeue_ready_returns_envelope(self):
        """dequeue_ready returns the immediately-ready envelope."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        env = _make_env("task-1")
        q.enqueue(env)
        ready = q.dequeue_ready()
        assert len(ready) == 1
        assert ready[0] is env

    def test_dequeue_ready_clears_queue(self):
        """dequeue_ready empties the ready list."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.enqueue(_make_env("task-1"))
        q.dequeue_ready()
        assert q.ready_count == 0
        assert q.dequeue_ready() == []

    def test_multiple_no_dep_fifo(self):
        """Multiple no-dep envelopes are returned FIFO."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        e1 = _make_env("task-1")
        e2 = _make_env("task-2")
        e3 = _make_env("task-3")
        q.enqueue(e1)
        q.enqueue(e2)
        q.enqueue(e3)
        ready = q.dequeue_ready()
        assert ready == [e1, e2, e3]

    def test_immediate_stat_incremented(self):
        """Immediate enqueue increments immediate stat."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.enqueue(_make_env("task-1"))
        q.enqueue(_make_env("task-2"))
        assert q.get_stats()["immediate"] == 2


class TestReadyQueueEnqueueWithDeps:
    """Test enqueue with dependencies (waiting)."""

    def test_dependency_waiting(self):
        """Envelope with depends_on is buffered."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        env = _make_env("task-child")
        status, failed = q.enqueue(env, depends_on="task-parent")
        assert status == "waiting"
        assert failed == []
        assert q.waiting_count == 1
        assert q.ready_count == 0

    def test_waiting_not_in_dequeue(self):
        """Waiting envelopes are not returned by dequeue_ready."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        assert q.dequeue_ready() == []

    def test_multiple_waiters_same_dep(self):
        """Multiple envelopes can wait on the same dependency."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-c1"), depends_on="task-parent")
        q.enqueue(_make_env("task-c2"), depends_on="task-parent")
        assert q.waiting_count == 2

    def test_enqueued_stat_incremented(self):
        """Enqueue with dep increments enqueued stat."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        assert q.get_stats()["enqueued"] == 1


class TestReadyQueueNotifyCompleted:
    """Test notify_completed releasing dependents."""

    def test_notify_releases_dependents(self):
        """notify_completed releases waiting envelopes."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        child_env = _make_env("task-child")
        q.enqueue(child_env, depends_on="task-parent")
        released, failed = q.notify_completed("task-parent", "completed")
        assert len(released) == 1
        assert released[0] is child_env
        assert failed == []

    def test_released_goes_to_ready(self):
        """Released envelopes appear in ready queue."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        child_env = _make_env("task-child")
        q.enqueue(child_env, depends_on="task-parent")
        q.notify_completed("task-parent", "completed")
        assert q.ready_count == 1
        ready = q.dequeue_ready()
        assert ready[0] is child_env

    def test_multiple_released_fifo(self):
        """Multiple released envelopes maintain FIFO order."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        e1 = _make_env("task-c1")
        e2 = _make_env("task-c2")
        q.enqueue(e1, depends_on="task-parent")
        q.enqueue(e2, depends_on="task-parent")
        q.notify_completed("task-parent", "completed")
        ready = q.dequeue_ready()
        assert ready == [e1, e2]

    def test_notify_no_waiters(self):
        """notify_completed with no waiters returns empty lists."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        released, failed = q.notify_completed("task-x", "completed")
        assert released == []
        assert failed == []

    def test_released_stat_incremented(self):
        """Released envelopes increment released stat."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        q.notify_completed("task-parent", "completed")
        assert q.get_stats()["released"] == 1

    def test_dependency_already_completed_immediate(self):
        """Enqueue after dependency completed is immediately ready."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.notify_completed("task-parent", "completed")
        env = _make_env("task-child")
        status, failed = q.enqueue(env, depends_on="task-parent")
        assert status == "immediate"
        assert q.ready_count == 1

    def test_chained_dependencies(self):
        """A -> B -> C chain releases in order."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-a")
        q.register_task("task-b")
        env_b = _make_env("task-b")
        env_c = _make_env("task-c")
        q.enqueue(env_b, depends_on="task-a")
        # task-c depends on task-b (which is itself waiting)
        q.enqueue(env_c, depends_on="task-b")
        assert q.waiting_count == 2

        # Complete A -> releases B
        released, _ = q.notify_completed("task-a", "completed")
        assert len(released) == 1
        assert released[0] is env_b
        assert q.waiting_count == 1  # C still waiting

        # Complete B -> releases C
        released2, _ = q.notify_completed("task-b", "completed")
        assert len(released2) == 1
        assert released2[0] is env_c
        assert q.waiting_count == 0


class TestReadyQueueFailedDependency:
    """Test behavior when predecessor fails/is cancelled (7.4.2)."""

    def test_predecessor_failed(self):
        """Failed predecessor causes dependent to fail."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        released, failed = q.notify_completed("task-parent", "failed")
        assert released == []
        assert "task-child" in failed

    def test_predecessor_cancelled(self):
        """Cancelled predecessor causes dependent to fail."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        released, failed = q.notify_completed("task-parent", "cancelled")
        assert released == []
        assert "task-child" in failed

    def test_predecessor_error(self):
        """Error predecessor causes dependent to fail."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        released, failed = q.notify_completed("task-parent", "error")
        assert released == []
        assert "task-child" in failed

    def test_failed_dep_stat(self):
        """Failed dependency increments failed_dep stat."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        q.notify_completed("task-parent", "failed")
        assert q.get_stats()["failed_dep"] == 1

    def test_enqueue_after_failed_dep(self):
        """Enqueueing after dependency already failed returns dep_failed."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.notify_completed("task-parent", "failed")
        status, failed = q.enqueue(
            _make_env("task-child"),
            depends_on="task-parent",
        )
        assert status == "dep_failed"
        assert "task-child" in failed

    def test_multiple_dependents_all_fail(self):
        """Multiple dependents all fail when predecessor fails."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-c1"), depends_on="task-parent")
        q.enqueue(_make_env("task-c2"), depends_on="task-parent")
        released, failed = q.notify_completed("task-parent", "cancelled")
        assert released == []
        assert set(failed) == {"task-c1", "task-c2"}


# =====================================================================
# 7.4.3 -- Circular dependency detection
# =====================================================================


class TestCircularDependency:
    """Test circular dependency detection."""

    def test_direct_cycle_ab(self):
        """A -> B, B -> A detected as circular."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-a")
        q.register_task("task-b")
        # A depends on B
        q.enqueue(_make_env("task-a"), depends_on="task-b")
        # B depends on A -- cycle!
        status, failed = q.enqueue(_make_env("task-b"), depends_on="task-a")
        assert status == "circular"
        assert "task-b" in failed  # Current task
        assert "task-a" in failed  # Cycle participant

    def test_circular_stat(self):
        """Circular detection increments circular stat."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-a")
        q.register_task("task-b")
        q.enqueue(_make_env("task-a"), depends_on="task-b")
        q.enqueue(_make_env("task-b"), depends_on="task-a")
        assert q.get_stats()["circular"] == 1

    def test_cycle_cleans_waiting(self):
        """Circular detection removes participants from waiting."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-a")
        q.register_task("task-b")
        q.enqueue(_make_env("task-a"), depends_on="task-b")
        q.enqueue(_make_env("task-b"), depends_on="task-a")
        # Both should be removed from waiting
        assert q.waiting_count == 0


class TestMissingDependency:
    """Test missing/unknown dependency handling (7.4.3)."""

    def test_unknown_dep_dispatches_immediately(self):
        """Unknown depends_on dispatches immediately."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        env = _make_env("task-child")
        status, failed = q.enqueue(env, depends_on="task-nonexistent")
        assert status == "unknown_dep"
        assert failed == []
        assert q.ready_count == 1

    def test_unknown_dep_stat(self):
        """Unknown dependency increments unknown_dep stat."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.enqueue(_make_env("task-child"), depends_on="task-xxx")
        assert q.get_stats()["unknown_dep"] == 1

    def test_registered_task_not_unknown(self):
        """Registered task_id is not treated as unknown."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        status, _ = q.enqueue(
            _make_env("task-child"),
            depends_on="task-parent",
        )
        assert status == "waiting"  # Not unknown_dep


# =====================================================================
# 7.4.1 -- ReadyQueue state queries
# =====================================================================


class TestReadyQueueStateQueries:
    """Test state query properties and methods."""

    def test_is_task_completed(self):
        """is_task_completed returns True after notify."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        assert not q.is_task_completed("task-x")
        q.notify_completed("task-x", "completed")
        assert q.is_task_completed("task-x")

    def test_get_task_status(self):
        """get_task_status returns the completion status."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        assert q.get_task_status("task-x") is None
        q.notify_completed("task-x", "failed")
        assert q.get_task_status("task-x") == "failed"

    def test_total_pending(self):
        """total_pending = ready + waiting."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-1"))  # ready
        q.enqueue(_make_env("task-2"), depends_on="task-parent")  # waiting
        assert q.total_pending == 2
        assert q.ready_count == 1
        assert q.waiting_count == 1

    def test_get_queue_state(self):
        """get_queue_state returns structured snapshot."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")
        state = q.get_queue_state()
        assert state["ready"] == 0
        assert state["waiting"] == 1
        assert "task-parent" in state["waiting_details"]
        assert "task-child" in state["waiting_details"]["task-parent"]


# =====================================================================
# E7.4 Fixtures
# =====================================================================


class TestE74Fixtures:
    """Test E7.4 fixture helpers."""

    def test_create_test_ready_queue(self):
        """Fixture creates a ReadyQueue instance."""
        from poc.k1_poc.testing.fixtures import create_test_ready_queue

        q = create_test_ready_queue()
        assert q is not None
        assert q.ready_count == 0

    def test_assert_ready_queue_state_pass(self):
        """assert_ready_queue_state passes with correct values."""
        from poc.k1_poc.testing.fixtures import assert_ready_queue_state, create_test_ready_queue

        q = create_test_ready_queue()
        assert_ready_queue_state(q, ready=0, waiting=0)

    def test_assert_ready_queue_state_fail(self):
        """assert_ready_queue_state fails with incorrect values."""
        import pytest

        from poc.k1_poc.testing.fixtures import assert_ready_queue_state, create_test_ready_queue

        q = create_test_ready_queue()
        with pytest.raises(AssertionError):
            assert_ready_queue_state(q, ready=5)

    def test_assert_queue_stats_pass(self):
        """assert_queue_stats passes with correct values."""
        from poc.k1_poc.testing.fixtures import assert_queue_stats, create_test_ready_queue

        q = create_test_ready_queue()
        assert_queue_stats(q, immediate=0, enqueued=0, released=0)

    def test_assert_queue_stats_fail(self):
        """assert_queue_stats fails with incorrect values."""
        import pytest

        from poc.k1_poc.testing.fixtures import assert_queue_stats, create_test_ready_queue

        q = create_test_ready_queue()
        with pytest.raises(AssertionError):
            assert_queue_stats(q, immediate=99)

    def test_fixtures_in_all(self):
        """E7.4 fixtures are in __all__."""
        from poc.k1_poc.testing import fixtures

        assert "create_test_ready_queue" in fixtures.__all__
        assert "assert_ready_queue_state" in fixtures.__all__
        assert "assert_queue_stats" in fixtures.__all__


# =====================================================================
# 7.4.2 -- Coordinator wiring
# =====================================================================


class TestCoordinatorReadyQueueWiring:
    """Test ReadyQueue integration in coordinator."""

    def test_coordinator_has_ready_queue_attr(self):
        """K1DemoCoordinator declares ready_queue attribute."""
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        c = K1DemoCoordinator.__new__(K1DemoCoordinator)
        # Verify the attribute is declared in __init__
        import inspect

        source = inspect.getsource(K1DemoCoordinator.__init__)
        assert "ready_queue" in source

    def test_ready_queue_import(self):
        """ReadyQueue can be imported from actors.ready_queue."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        assert ReadyQueue is not None

    def test_dispatch_to_back_pool_extracts_depends_on(self):
        """_dispatch_to_back_pool references depends_on in source."""
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator._dispatch_to_back_pool)
        assert "depends_on" in source

    def test_on_back_task_done_notifies_ready_queue(self):
        """_on_back_task_done calls ready_queue.notify_completed."""
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator._on_back_task_done)
        assert "notify_completed" in source

    def test_dispatch_ready_queue_method_exists(self):
        """_dispatch_ready_queue method exists on coordinator."""
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        assert hasattr(K1DemoCoordinator, "_dispatch_ready_queue")

    def test_emit_dependency_failed_method_exists(self):
        """_emit_dependency_failed method exists on coordinator."""
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        assert hasattr(K1DemoCoordinator, "_emit_dependency_failed")


# =====================================================================
# Integration: ReadyQueue + BackPool
# =====================================================================


class TestReadyQueueBackPoolIntegration:
    """Test ReadyQueue works with BackPool for real dispatch scenarios."""

    def test_no_dep_immediate_dispatch(self):
        """Envelope without depends_on flows through immediately."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue
        from poc.k1_poc.testing.fixtures import create_test_back_pool

        pool = create_test_back_pool()
        q = ReadyQueue()

        env = _make_env("task-1")
        status, _ = q.enqueue(env)
        assert status == "immediate"

        # Pool can acquire worker
        slot = pool.acquire_worker("task-1")
        assert slot.task_id == "task-1"

    def test_dep_wait_then_release(self):
        """Dependent envelope waits, then released after parent completes."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue
        from poc.k1_poc.testing.fixtures import create_test_back_pool

        pool = create_test_back_pool()
        q = ReadyQueue()

        # Parent dispatches and acquires worker
        parent_env = _make_env("task-parent")
        q.register_task("task-parent")
        q.enqueue(parent_env)
        pool.acquire_worker("task-parent")

        # Drain the parent from ready queue (coordinator would do this)
        q.dequeue_ready()

        # Child depends on parent
        child_env = _make_env("task-child")
        status, _ = q.enqueue(child_env, depends_on="task-parent")
        assert status == "waiting"

        # Parent completes
        pool.release_worker("task-parent", reason="completed")
        released, _ = q.notify_completed("task-parent", "completed")
        assert len(released) == 1

        # Drain ready queue -- only child should be there
        ready = q.dequeue_ready()
        assert len(ready) == 1
        assert ready[0] is child_env

        # Now child can acquire worker
        slot = pool.acquire_worker("task-child")
        assert slot.task_id == "task-child"

    def test_dep_failed_no_worker_acquired(self):
        """Failed dependency means child never acquires a worker."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue
        from poc.k1_poc.testing.fixtures import create_test_back_pool

        pool = create_test_back_pool()
        q = ReadyQueue()

        q.register_task("task-parent")
        pool.acquire_worker("task-parent")
        q.enqueue(_make_env("task-child"), depends_on="task-parent")

        # Parent fails
        pool.release_worker("task-parent", reason="error")
        _, failed = q.notify_completed("task-parent", "failed")
        assert "task-child" in failed
        # Child should NOT be in ready queue
        assert q.ready_count == 0


# =====================================================================
# Stats accumulation across mixed operations
# =====================================================================


class TestReadyQueueStatsAccumulation:
    """Test that stats accumulate correctly across operations."""

    def test_mixed_scenario_stats(self):
        """Stats track all operations in a mixed scenario."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue
        from poc.k1_poc.testing.fixtures import assert_queue_stats

        q = ReadyQueue()

        # 2 immediate
        q.enqueue(_make_env("task-1"))
        q.enqueue(_make_env("task-2"))

        # 1 unknown dep
        q.enqueue(_make_env("task-3"), depends_on="task-missing")

        # 1 enqueued (waiting)
        q.register_task("task-parent")
        q.enqueue(_make_env("task-4"), depends_on="task-parent")

        # 1 released
        q.notify_completed("task-parent", "completed")

        assert_queue_stats(
            q,
            immediate=2,
            unknown_dep=1,
            enqueued=1,
            released=1,
            failed_dep=0,
            circular=0,
        )

    def test_register_then_notify_then_enqueue(self):
        """Register -> notify -> enqueue sees dep as already completed."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        q = ReadyQueue()
        q.register_task("task-parent")
        q.notify_completed("task-parent", "completed")
        status, _ = q.enqueue(
            _make_env("task-child"),
            depends_on="task-parent",
        )
        assert status == "immediate"
        assert q.get_stats()["immediate"] == 1
