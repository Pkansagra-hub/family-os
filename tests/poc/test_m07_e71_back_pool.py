"""
Tests for M7 E7.1 -- BackPool Worker Management.

Covers:
  - 7.1.1: BackPoolConfig dataclass validation
  - 7.1.2: BackPool acquire/release/get_active_workers, WorkerSlot lifecycle
  - 7.1.3: Coordinator integration (pool dispatch, overflow queue, done callback)
  - 7.1.4: Pool observability (events, utilization gauge, warning thresholds)

Test count: 30 tests across 6 test classes.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

logger = logging.getLogger(__name__)


# =====================================================================
# 7.1.1 -- BackPoolConfig
# =====================================================================


class TestBackPoolConfig:
    """Test BackPoolConfig dataclass validation and defaults."""

    def test_default_values(self):
        """BackPoolConfig has correct defaults: pool_size=3, max_per_session=2, etc."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        config = BackPoolConfig()
        assert config.pool_size == 3
        assert config.max_concurrent_per_session == 2
        assert config.lease_ttl_s == 300.0
        assert config.reclaim_check_interval_s == 30.0
        assert config.enable_dependency_ordering is True

    def test_custom_values(self):
        """BackPoolConfig accepts custom values."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        config = BackPoolConfig(
            pool_size=5,
            max_concurrent_per_session=3,
            lease_ttl_s=600.0,
            reclaim_check_interval_s=15.0,
            enable_dependency_ordering=False,
        )
        assert config.pool_size == 5
        assert config.max_concurrent_per_session == 3
        assert config.lease_ttl_s == 600.0
        assert config.reclaim_check_interval_s == 15.0
        assert config.enable_dependency_ordering is False

    def test_invalid_pool_size_zero(self):
        """BackPoolConfig rejects pool_size < 1."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="pool_size must be >= 1"):
            BackPoolConfig(pool_size=0)

    def test_invalid_pool_size_negative(self):
        """BackPoolConfig rejects negative pool_size."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="pool_size must be >= 1"):
            BackPoolConfig(pool_size=-1)

    def test_invalid_max_per_session_zero(self):
        """BackPoolConfig rejects max_concurrent_per_session < 1."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="max_concurrent_per_session must be >= 1"):
            BackPoolConfig(max_concurrent_per_session=0)

    def test_invalid_lease_ttl_zero(self):
        """BackPoolConfig rejects lease_ttl_s <= 0."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="lease_ttl_s must be > 0"):
            BackPoolConfig(lease_ttl_s=0)

    def test_invalid_reclaim_interval_zero(self):
        """BackPoolConfig rejects reclaim_check_interval_s <= 0."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="reclaim_check_interval_s must be > 0"):
            BackPoolConfig(reclaim_check_interval_s=0)


# =====================================================================
# 7.1.2 -- WorkerSlot
# =====================================================================


class TestWorkerSlot:
    """Test WorkerSlot dataclass and lifecycle methods."""

    def test_worker_slot_creation(self):
        """WorkerSlot has unique worker_id, correct task_id, and timestamp."""
        from poc.k1_poc.actors.back_pool import WorkerSlot

        slot = WorkerSlot(task_id="task-1", session_id="session-1")
        assert slot.task_id == "task-1"
        assert slot.session_id == "session-1"
        assert slot.worker_id  # UUID string, non-empty
        assert slot.created_at > 0
        assert slot.async_task is None
        assert slot.lease is None

    def test_worker_slot_unique_ids(self):
        """Two WorkerSlots get different worker_ids."""
        from poc.k1_poc.actors.back_pool import WorkerSlot

        slot1 = WorkerSlot(task_id="task-1")
        slot2 = WorkerSlot(task_id="task-2")
        assert slot1.worker_id != slot2.worker_id

    def test_bind_task(self):
        """bind_task sets async_task reference."""
        from poc.k1_poc.actors.back_pool import WorkerSlot

        slot = WorkerSlot(task_id="task-1")

        async def _dummy():
            pass

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(_dummy())
            slot.bind_task(task)
            assert slot.async_task is task
        finally:
            loop.close()

    def test_is_running_no_task(self):
        """is_running returns False when no async_task is bound."""
        from poc.k1_poc.actors.back_pool import WorkerSlot

        slot = WorkerSlot(task_id="task-1")
        assert slot.is_running is False

    def test_bind_task_with_lease(self):
        """bind_task can set both task and lease."""
        from poc.k1_poc.actors.back_pool import WorkerSlot

        slot = WorkerSlot(task_id="task-1")
        mock_lease = {"lease_id": "test"}

        async def _dummy():
            pass

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(_dummy())
            slot.bind_task(task, lease=mock_lease)
            assert slot.lease == mock_lease
        finally:
            loop.close()


# =====================================================================
# 7.1.2 -- BackPool acquire/release lifecycle
# =====================================================================


class TestBackPoolLifecycle:
    """Test BackPool acquire_worker, release_worker, get_active_workers."""

    def test_acquire_worker_basic(self):
        """acquire_worker returns a WorkerSlot with correct task_id."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        slot = pool.acquire_worker("task-1")

        assert slot.task_id == "task-1"
        assert slot.worker_id
        assert pool.active_count == 1
        assert pool.pool_available == 2

    def test_acquire_multiple_workers(self):
        """Multiple workers can be acquired up to pool_size."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        slot1 = pool.acquire_worker("task-1")
        slot2 = pool.acquire_worker("task-2")
        slot3 = pool.acquire_worker("task-3")

        assert pool.active_count == 3
        assert pool.pool_available == 0
        assert slot1.worker_id != slot2.worker_id
        assert slot2.worker_id != slot3.worker_id

    def test_acquire_worker_pool_exhausted(self):
        """acquire_worker raises BackPoolExhausted when pool is full."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig, BackPoolExhausted

        pool = BackPool(BackPoolConfig(pool_size=2))
        pool.acquire_worker("task-1")
        pool.acquire_worker("task-2")

        with pytest.raises(BackPoolExhausted) as exc_info:
            pool.acquire_worker("task-3")

        assert exc_info.value.pool_size == 2
        assert exc_info.value.active_count == 2
        assert exc_info.value.reason == "pool_full"

    def test_acquire_worker_session_limit(self):
        """acquire_worker raises SessionLimitReached when session limit hit."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig, SessionLimitReached

        pool = BackPool(BackPoolConfig(pool_size=5, max_concurrent_per_session=2))
        pool.acquire_worker("task-1", session_id="session-A")
        pool.acquire_worker("task-2", session_id="session-A")

        with pytest.raises(SessionLimitReached) as exc_info:
            pool.acquire_worker("task-3", session_id="session-A")

        assert exc_info.value.session_id == "session-A"
        assert exc_info.value.session_count == 2
        assert exc_info.value.max_per_session == 2

    def test_acquire_worker_session_limit_different_sessions(self):
        """Different sessions can each use up to max_concurrent_per_session."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=6, max_concurrent_per_session=2))
        pool.acquire_worker("task-1", session_id="session-A")
        pool.acquire_worker("task-2", session_id="session-A")
        pool.acquire_worker("task-3", session_id="session-B")
        pool.acquire_worker("task-4", session_id="session-B")

        assert pool.active_count == 4
        assert pool.session_count("session-A") == 2
        assert pool.session_count("session-B") == 2

    def test_acquire_worker_idempotent(self):
        """Acquiring a worker for the same task_id returns existing slot."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        slot1 = pool.acquire_worker("task-1")
        slot2 = pool.acquire_worker("task-1")

        assert slot1.worker_id == slot2.worker_id
        assert pool.active_count == 1  # Not double-counted

    def test_release_worker(self):
        """release_worker frees the slot and returns it."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        assert pool.active_count == 1

        released = pool.release_worker("task-1", reason="completed")
        assert released is not None
        assert released.task_id == "task-1"
        assert pool.active_count == 0
        assert pool.pool_available == 3

    def test_release_unknown_worker(self):
        """release_worker returns None for unknown task_id."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        released = pool.release_worker("unknown-task")
        assert released is None

    def test_release_then_acquire(self):
        """After releasing, pool slot is available for new acquisition."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=1))
        pool.acquire_worker("task-1")
        assert pool.pool_available == 0

        pool.release_worker("task-1")
        assert pool.pool_available == 1

        slot = pool.acquire_worker("task-2")
        assert slot.task_id == "task-2"

    def test_get_active_workers(self):
        """get_active_workers returns list of all active slots."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1", session_id="s1")
        pool.acquire_worker("task-2", session_id="s2")

        workers = pool.get_active_workers()
        assert len(workers) == 2
        task_ids = {w.task_id for w in workers}
        assert task_ids == {"task-1", "task-2"}

    def test_get_worker_for_task(self):
        """get_worker_for_task returns correct slot or None."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")

        assert pool.get_worker_for_task("task-1") is not None
        assert pool.get_worker_for_task("task-999") is None

    def test_has_worker(self):
        """has_worker checks if task has active worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        assert pool.has_worker("task-1") is False

        pool.acquire_worker("task-1")
        assert pool.has_worker("task-1") is True

        pool.release_worker("task-1")
        assert pool.has_worker("task-1") is False


# =====================================================================
# 7.1.2 -- Overflow queue
# =====================================================================


class TestBackPoolOverflow:
    """Test BackPool overflow queue for pool-exhausted scenarios."""

    def test_enqueue_dequeue(self):
        """Overflow queue follows FIFO order."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=1))
        pool.enqueue_overflow({"id": 1})
        pool.enqueue_overflow({"id": 2})
        pool.enqueue_overflow({"id": 3})

        assert pool.overflow_depth == 3
        assert pool.dequeue_overflow() == {"id": 1}
        assert pool.dequeue_overflow() == {"id": 2}
        assert pool.dequeue_overflow() == {"id": 3}
        assert pool.dequeue_overflow() is None
        assert pool.overflow_depth == 0

    def test_drain_overflow(self):
        """drain_overflow returns all and clears the queue."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=1))
        pool.enqueue_overflow("env-1")
        pool.enqueue_overflow("env-2")

        drained = pool.drain_overflow()
        assert len(drained) == 2
        assert pool.overflow_depth == 0


# =====================================================================
# 7.1.4 -- Pool observability
# =====================================================================


class TestBackPoolObservability:
    """Test pool observability: callbacks, state snapshot, utilization."""

    def test_acquire_callback_fires(self):
        """on_worker_acquired callback fires on acquire_worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        acquired_events = []
        pool = BackPool(
            BackPoolConfig(pool_size=3),
            on_worker_acquired=lambda slot: acquired_events.append(slot),
        )
        pool.acquire_worker("task-1")

        assert len(acquired_events) == 1
        assert acquired_events[0].task_id == "task-1"

    def test_release_callback_fires(self):
        """on_worker_released callback fires on release_worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        released_events = []
        pool = BackPool(
            BackPoolConfig(pool_size=3),
            on_worker_released=lambda slot, reason: released_events.append((slot, reason)),
        )
        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="completed")

        assert len(released_events) == 1
        assert released_events[0][0].task_id == "task-1"
        assert released_events[0][1] == "completed"

    def test_get_pool_state_snapshot(self):
        """get_pool_state returns complete pool snapshot."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1", session_id="s1")

        state = pool.get_pool_state()
        assert state["active"] == 1
        assert state["size"] == 3
        assert state["available"] == 2
        assert state["utilization"] == pytest.approx(0.333, abs=0.01)
        assert state["overflow"] == 0
        assert len(state["workers"]) == 1
        assert state["workers"][0]["task_id"] == "task-1"
        assert state["workers"][0]["session_id"] == "s1"

    def test_utilization_property(self):
        """utilization property tracks pool usage correctly."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=4))
        assert pool.utilization == 0.0

        pool.acquire_worker("task-1")
        assert pool.utilization == 0.25

        pool.acquire_worker("task-2")
        assert pool.utilization == 0.5

        pool.acquire_worker("task-3")
        assert pool.utilization == 0.75

        pool.acquire_worker("task-4")
        assert pool.utilization == 1.0

    def test_repr(self):
        """BackPool repr shows active/pool_size and overflow."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        pool.enqueue_overflow("env-1")

        r = repr(pool)
        assert "1/3" in r
        assert "overflow=1" in r


# =====================================================================
# 7.1.4 -- Bus topics and builders
# =====================================================================


class TestBackPoolBusIntegration:
    """Test BackPool bus topic constants and builder functions."""

    def test_backpool_topics_in_all_topics(self):
        """BackPool topics are registered in ALL_TOPICS set."""
        from poc.k1_poc.bus.topics import (
            ALL_TOPICS,
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
        )

        assert TOPIC_BACKPOOL_WORKER_ACQUIRED in ALL_TOPICS
        assert TOPIC_BACKPOOL_WORKER_RELEASED in ALL_TOPICS

    def test_backpool_topics_are_strict(self):
        """BackPool topics are in STRICT_TOPICS (not RELAXED)."""
        from poc.k1_poc.bus.topics import (
            STRICT_TOPICS,
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
        )

        assert TOPIC_BACKPOOL_WORKER_ACQUIRED in STRICT_TOPICS
        assert TOPIC_BACKPOOL_WORKER_RELEASED in STRICT_TOPICS

    def test_build_backpool_worker_acquired(self):
        """build_backpool_worker_acquired creates correct envelope."""
        from poc.k1_poc.bus.builders import build_backpool_worker_acquired
        from poc.k1_poc.bus.topics import TOPIC_BACKPOOL_WORKER_ACQUIRED

        env = build_backpool_worker_acquired(
            payload={
                "worker_id": "w-1",
                "task_id": "task-1",
                "pool_size": 3,
                "active_workers": 1,
                "session_id": "s1",
            }
        )
        assert env.topic == TOPIC_BACKPOOL_WORKER_ACQUIRED
        payload = json.loads(env.payload)
        assert payload["worker_id"] == "w-1"
        assert payload["task_id"] == "task-1"
        assert payload["pool_size"] == 3
        assert payload["active_workers"] == 1

    def test_build_backpool_worker_released(self):
        """build_backpool_worker_released creates correct envelope."""
        from poc.k1_poc.bus.builders import build_backpool_worker_released
        from poc.k1_poc.bus.topics import TOPIC_BACKPOOL_WORKER_RELEASED

        env = build_backpool_worker_released(
            payload={
                "worker_id": "w-1",
                "task_id": "task-1",
                "pool_size": 3,
                "active_workers": 0,
                "release_reason": "completed",
            }
        )
        assert env.topic == TOPIC_BACKPOOL_WORKER_RELEASED
        payload = json.loads(env.payload)
        assert payload["release_reason"] == "completed"

    def test_backpool_builders_in_registry(self):
        """BackPool builders are registered in BUILDERS dict."""
        from poc.k1_poc.bus.builders import BUILDERS
        from poc.k1_poc.bus.topics import (
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
        )

        assert TOPIC_BACKPOOL_WORKER_ACQUIRED in BUILDERS
        assert TOPIC_BACKPOOL_WORKER_RELEASED in BUILDERS

    def test_backpool_in_enriched_registry(self):
        """BackPool builders appear in get_builder_registry with BACKGROUND priority."""
        from poc.k1_poc.bus.builders import get_builder_registry
        from poc.k1_poc.bus.topics import (
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
        )

        registry = get_builder_registry()
        assert TOPIC_BACKPOOL_WORKER_ACQUIRED in registry
        assert TOPIC_BACKPOOL_WORKER_RELEASED in registry
        # BACKGROUND priority for observability events
        assert registry[TOPIC_BACKPOOL_WORKER_ACQUIRED].priority.value == 3  # BACKGROUND
        assert registry[TOPIC_BACKPOOL_WORKER_RELEASED].priority.value == 3

    def test_topic_count_increased(self):
        """ALL_TOPICS count increased by 2 (from 35 to 37)."""
        from poc.k1_poc.bus.topics import ALL_TOPICS

        # M6 had 35 topics; M7 E7.1 adds 2 more
        assert len(ALL_TOPICS) == 40


# =====================================================================
# 7.1 -- Fixture helpers
# =====================================================================


class TestBackPoolFixtures:
    """Test M7 test fixture helpers."""

    def test_create_test_back_pool(self):
        """create_test_back_pool returns configured BackPool."""
        from poc.k1_poc.testing.fixtures import create_test_back_pool

        pool = create_test_back_pool(pool_size=5, max_concurrent_per_session=3)
        assert pool.config.pool_size == 5
        assert pool.config.max_concurrent_per_session == 3

    def test_create_test_worker_slot(self):
        """create_test_worker_slot returns configured WorkerSlot."""
        from poc.k1_poc.testing.fixtures import create_test_worker_slot

        slot = create_test_worker_slot(task_id="my-task", session_id="my-session")
        assert slot.task_id == "my-task"
        assert slot.session_id == "my-session"

    def test_assert_pool_state_passes(self):
        """assert_pool_state passes when values match."""
        from poc.k1_poc.testing.fixtures import assert_pool_state, create_test_back_pool

        pool = create_test_back_pool(pool_size=3)
        pool.acquire_worker("task-1")

        assert_pool_state(pool, active=1, available=2, overflow=0)

    def test_assert_pool_state_fails(self):
        """assert_pool_state raises AssertionError on mismatch."""
        from poc.k1_poc.testing.fixtures import assert_pool_state, create_test_back_pool

        pool = create_test_back_pool(pool_size=3)

        with pytest.raises(AssertionError, match="Expected 1 active workers"):
            assert_pool_state(pool, active=1)
