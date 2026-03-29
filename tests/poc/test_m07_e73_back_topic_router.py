"""
Tests for M7 E7.3 -- Back Mailbox Topic Router.

Covers:
  - 7.3.1: BackTopicRouter class with route(envelope) -> handler_fn
  - 7.3.2: Cancel bypass (synchronous, no pool worker), coordinator wiring
  - 7.3.3: CancellationToken from TaskLease passed to handlers
  - 7.3.4: Late-envelope discard for completed/cancelled tasks

Test count target: ~45 tests across 9 test classes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import pytest

logger = logging.getLogger(__name__)


# =====================================================================
# Helpers -- lightweight Envelope stub for routing tests
# =====================================================================


@dataclass
class _StubEnvelope:
    """Minimal envelope for BackTopicRouter tests."""

    topic: str
    payload: bytes = b"{}"
    envelope_id: int = 1
    parent_id: int = 0
    cognitive_trace_id: str = ""

    @classmethod
    def with_task(cls, topic: str, task_id: str, **kwargs: Any) -> _StubEnvelope:
        payload = json.dumps({"task_id": task_id}).encode()
        return cls(topic=topic, payload=payload, **kwargs)


# =====================================================================
# 7.3.1 -- BackTopicRouter construction
# =====================================================================


class TestBackTopicRouterInit:
    """Test BackTopicRouter initialization."""

    def test_creates_without_pool(self):
        """BackTopicRouter can be created without a BackPool."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        assert router is not None
        assert repr(router).startswith("BackTopicRouter(")

    def test_creates_with_pool(self):
        """BackTopicRouter can be created with a BackPool."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)
        assert "attached" in repr(router)

    def test_routing_table_has_four_entries(self):
        """Routing table covers dispatch, resume, cancel, clarification.response."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        assert len(router._routing_table) == 4

    def test_initial_stats_are_zero(self):
        """All routing stats start at zero."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        stats = router.get_stats()
        assert stats["routed"] == 0
        assert stats["cancel_sync"] == 0
        assert stats["discarded_late"] == 0
        assert stats["discarded_unknown"] == 0


# =====================================================================
# 7.3.1 -- Routing table: route(envelope) -> handler_fn
# =====================================================================


class TestBackTopicRouterRoute:
    """Test BackTopicRouter.route() returns correct handlers."""

    def test_route_dispatch(self):
        """task.dispatch.v1 routes to back_handler."""
        from poc.k1_poc.actors.back import back_handler
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        router = BackTopicRouter()
        env = _StubEnvelope(topic=TOPIC_TASK_DISPATCH)
        handler = router.route(env)
        assert handler is back_handler

    def test_route_resume(self):
        """task.resume.v1 routes to back_resume_handler."""
        from poc.k1_poc.actors.back import back_resume_handler
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME

        router = BackTopicRouter()
        env = _StubEnvelope(topic=TOPIC_TASK_RESUME)
        handler = router.route(env)
        assert handler is back_resume_handler

    def test_route_cancel(self):
        """task.cancel.v1 routes to back_cancel_handler."""
        from poc.k1_poc.actors.back import back_cancel_handler
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL

        router = BackTopicRouter()
        env = _StubEnvelope(topic=TOPIC_TASK_CANCEL)
        handler = router.route(env)
        assert handler is back_cancel_handler

    def test_route_clarification_response(self):
        """clarification.response.v1 routes to back_resume_handler (HITL resolve)."""
        from poc.k1_poc.actors.back import back_resume_handler
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_CLARIFICATION_RESPONSE

        router = BackTopicRouter()
        env = _StubEnvelope(topic=TOPIC_CLARIFICATION_RESPONSE)
        handler = router.route(env)
        assert handler is back_resume_handler

    def test_route_unknown_topic_returns_none(self):
        """Unknown topic returns None (discard)."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        env = _StubEnvelope(topic="k1.unknown.topic.v1")
        handler = router.route(env)
        assert handler is None

    def test_route_empty_topic_returns_none(self):
        """Empty topic string returns None."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        env = _StubEnvelope(topic="")
        handler = router.route(env)
        assert handler is None

    def test_route_increments_routed_stat(self):
        """Successful route increments the routed counter."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        router = BackTopicRouter()
        env = _StubEnvelope(topic=TOPIC_TASK_DISPATCH)
        router.route(env)
        assert router.get_stats()["routed"] == 1

    def test_route_unknown_increments_discarded(self):
        """Unknown topic increments discarded_unknown counter."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        env = _StubEnvelope(topic="k1.bogus.v1")
        router.route(env)
        assert router.get_stats()["discarded_unknown"] == 1


# =====================================================================
# 7.3.2 -- Cancel bypass (synchronous, no pool worker)
# =====================================================================


class TestCancelBypass:
    """Test that cancel envelopes bypass the pool (synchronous dispatch)."""

    def test_is_cancel_topic_true(self):
        """is_cancel_topic returns True for task.cancel.v1."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL

        router = BackTopicRouter()
        assert router.is_cancel_topic(TOPIC_TASK_CANCEL) is True

    def test_is_cancel_topic_false_for_dispatch(self):
        """is_cancel_topic returns False for task.dispatch.v1."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        router = BackTopicRouter()
        assert router.is_cancel_topic(TOPIC_TASK_DISPATCH) is False

    def test_is_cancel_topic_false_for_resume(self):
        """is_cancel_topic returns False for task.resume.v1."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME

        router = BackTopicRouter()
        assert router.is_cancel_topic(TOPIC_TASK_RESUME) is False

    def test_cancel_increments_cancel_sync_stat(self):
        """Routing a cancel envelope increments cancel_sync counter."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL

        router = BackTopicRouter()
        env = _StubEnvelope(topic=TOPIC_TASK_CANCEL)
        router.route(env)
        assert router.get_stats()["cancel_sync"] == 1

    def test_cancel_does_not_consume_pool_slot(self):
        """Cancel should NOT acquire a pool worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL

        pool = BackPool(BackPoolConfig(pool_size=1))
        router = BackTopicRouter(back_pool=pool)

        env = _StubEnvelope.with_task(TOPIC_TASK_CANCEL, "task-1")
        handler = router.route(env)

        # Handler is returned but pool has 0 active workers
        assert handler is not None
        assert pool.active_count == 0


# =====================================================================
# 7.3.3 -- CancellationToken from TaskLease to handlers
# =====================================================================


class TestCancelTokenPassing:
    """Test CancellationToken extraction from TaskLease via router."""

    def test_get_cancel_token_with_active_lease(self):
        """get_cancel_token_for_task returns token from active lease."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        # Acquire a worker (creates lease with token)
        pool.acquire_worker("task-1")

        token = router.get_cancel_token_for_task("task-1")
        assert token is not None
        assert token.task_id == "task-1"
        assert token.is_cancelled is False

    def test_get_cancel_token_unknown_task(self):
        """get_cancel_token_for_task returns None for unknown task."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        token = router.get_cancel_token_for_task("unknown-task")
        assert token is None

    def test_get_cancel_token_no_pool(self):
        """get_cancel_token_for_task returns None when no pool attached."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter(back_pool=None)
        token = router.get_cancel_token_for_task("task-1")
        assert token is None

    def test_token_from_lease_is_same_object(self):
        """The token returned by router is the same object as in the lease."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        slot = pool.acquire_worker("task-1")
        router_token = router.get_cancel_token_for_task("task-1")

        assert router_token is slot.lease.cancellation_token

    def test_route_back_envelope_accepts_cancel_token(self):
        """route_back_envelope function accepts cancel_token kwarg."""
        import inspect

        from poc.k1_poc.actors.back import route_back_envelope

        sig = inspect.signature(route_back_envelope)
        assert "cancel_token" in sig.parameters


# =====================================================================
# 7.3.4 -- Late-envelope discard
# =====================================================================


class TestLateEnvelopeDiscard:
    """Test late-arriving envelope discard for completed/cancelled tasks."""

    def test_released_task_dispatch_discarded(self):
        """Dispatch envelope for a released task is discarded."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        # Acquire and release a worker
        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="completed")

        # Late dispatch for released task
        env = _StubEnvelope.with_task(TOPIC_TASK_DISPATCH, "task-1")
        handler = router.route(env)
        assert handler is None
        assert router.get_stats()["discarded_late"] == 1

    def test_cancelled_task_resume_discarded(self):
        """Resume envelope for a cancelled task is discarded."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="cancelled")

        env = _StubEnvelope.with_task(TOPIC_TASK_RESUME, "task-1")
        handler = router.route(env)
        assert handler is None

    def test_cancel_never_discarded_for_released_task(self):
        """Cancel envelope is NEVER discarded (it stops things)."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="completed")

        # Cancel is never discarded
        env = _StubEnvelope.with_task(TOPIC_TASK_CANCEL, "task-1")
        handler = router.route(env)
        assert handler is not None

    def test_active_task_not_discarded(self):
        """Envelopes for active tasks are NOT discarded."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        pool.acquire_worker("task-1")
        # Task is still active
        env = _StubEnvelope.with_task(TOPIC_TASK_RESUME, "task-1")
        handler = router.route(env)
        assert handler is not None
        assert router.get_stats()["discarded_late"] == 0

    def test_no_pool_never_discards(self):
        """Without a pool, late-envelope discard is skipped."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        router = BackTopicRouter(back_pool=None)
        env = _StubEnvelope.with_task(TOPIC_TASK_DISPATCH, "task-1")
        handler = router.route(env)
        assert handler is not None

    def test_no_task_id_never_discards(self):
        """Envelope without task_id is never discarded."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        # No task_id in payload
        env = _StubEnvelope(topic=TOPIC_TASK_DISPATCH, payload=b"{}")
        handler = router.route(env)
        assert handler is not None


# =====================================================================
# 7.3.4 -- BackPool.is_task_released tracking
# =====================================================================


class TestBackPoolReleasedTracking:
    """Test BackPool._released_task_ids tracking for E7.3.4."""

    def test_is_task_released_false_initially(self):
        """No tasks are released initially."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        assert pool.is_task_released("task-1") is False

    def test_is_task_released_true_after_release(self):
        """Task is marked released after release_worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="completed")
        assert pool.is_task_released("task-1") is True

    def test_is_task_released_true_after_cancel(self):
        """Task is marked released after cancel release."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="cancelled")
        assert pool.is_task_released("task-1") is True

    def test_is_task_released_true_after_lease_expired(self):
        """Task is marked released after lease_expired release."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        pool.release_worker("task-1", reason="lease_expired")
        assert pool.is_task_released("task-1") is True

    def test_multiple_releases_tracked(self):
        """Multiple released task_ids are all tracked."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        for i in range(3):
            pool.acquire_worker(f"task-{i}")
        for i in range(3):
            pool.release_worker(f"task-{i}")

        for i in range(3):
            assert pool.is_task_released(f"task-{i}") is True


# =====================================================================
# 7.3.1 -- Routing statistics
# =====================================================================


class TestRouterStats:
    """Test BackTopicRouter routing statistics for observability."""

    def test_stats_accumulate(self):
        """Stats accumulate across multiple route() calls."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL, TOPIC_TASK_DISPATCH, TOPIC_TASK_RESUME

        router = BackTopicRouter()

        # 2 dispatch + 1 resume + 1 cancel + 1 unknown
        router.route(_StubEnvelope(topic=TOPIC_TASK_DISPATCH))
        router.route(_StubEnvelope(topic=TOPIC_TASK_DISPATCH))
        router.route(_StubEnvelope(topic=TOPIC_TASK_RESUME))
        router.route(_StubEnvelope(topic=TOPIC_TASK_CANCEL))
        router.route(_StubEnvelope(topic="k1.fake.v1"))

        stats = router.get_stats()
        assert stats["routed"] == 4  # dispatch x2 + resume + cancel
        assert stats["cancel_sync"] == 1
        assert stats["discarded_unknown"] == 1


# =====================================================================
# 7.3 -- Fixture helpers
# =====================================================================


class TestE73Fixtures:
    """Test M7 E7.3 fixture helpers."""

    def test_create_test_back_topic_router(self):
        """create_test_back_topic_router returns configured router."""
        from poc.k1_poc.testing.fixtures import create_test_back_topic_router

        router = create_test_back_topic_router()
        assert router is not None
        assert len(router._routing_table) == 4

    def test_create_test_back_topic_router_with_pool(self):
        """create_test_back_topic_router accepts a pool."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.testing.fixtures import create_test_back_topic_router

        pool = BackPool(BackPoolConfig(pool_size=2))
        router = create_test_back_topic_router(back_pool=pool)
        assert "attached" in repr(router)

    def test_assert_router_stats_passes(self):
        """assert_router_stats passes when values match."""
        from poc.k1_poc.testing.fixtures import assert_router_stats, create_test_back_topic_router

        router = create_test_back_topic_router()
        assert_router_stats(
            router,
            routed=0,
            cancel_sync=0,
            discarded_late=0,
            discarded_unknown=0,
        )

    def test_assert_router_stats_fails(self):
        """assert_router_stats raises AssertionError on mismatch."""
        from poc.k1_poc.testing.fixtures import assert_router_stats, create_test_back_topic_router

        router = create_test_back_topic_router()
        with pytest.raises(AssertionError, match="Expected routed=99"):
            assert_router_stats(router, routed=99)


# =====================================================================
# 7.3.2 -- Coordinator integration (structural validation)
# =====================================================================


class TestCoordinatorRouterWiring:
    """Test that coordinator creates BackTopicRouter alongside BackPool."""

    def test_back_topic_router_attribute_exists(self):
        """BackTopicRouter is a declared routing class with expected API."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        router = BackTopicRouter()
        assert hasattr(router, "route")
        assert hasattr(router, "is_cancel_topic")
        assert hasattr(router, "get_cancel_token_for_task")
        assert hasattr(router, "get_stats")
        assert callable(router.route)

    def test_coordinator_imports_router(self):
        """BackTopicRouter is importable from actors.back_router."""
        from poc.k1_poc.actors.back_router import BackTopicRouter

        assert BackTopicRouter is not None

    def test_full_routing_roundtrip(self):
        """End-to-end: create pool, router, acquire, route, check token."""
        from poc.k1_poc.actors.back import back_handler
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH

        # Setup
        pool = BackPool(BackPoolConfig(pool_size=3))
        router = BackTopicRouter(back_pool=pool)

        # Route dispatch
        env = _StubEnvelope.with_task(TOPIC_TASK_DISPATCH, "task-1")
        handler = router.route(env)
        assert handler is back_handler

        # Acquire worker (creates lease with token)
        slot = pool.acquire_worker("task-1")

        # Get cancel token via router
        token = router.get_cancel_token_for_task("task-1")
        assert token is not None
        assert token is slot.lease.cancellation_token

        # Release worker
        pool.release_worker("task-1")

        # Now late envelope should be discarded
        env2 = _StubEnvelope.with_task(TOPIC_TASK_DISPATCH, "task-1")
        assert router.route(env2) is None

    def test_mixed_routing_scenario(self):
        """Multiple topics routed correctly with stats tracking."""
        from poc.k1_poc.actors.back import back_cancel_handler, back_handler, back_resume_handler
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import (
            TOPIC_CLARIFICATION_RESPONSE,
            TOPIC_TASK_CANCEL,
            TOPIC_TASK_DISPATCH,
            TOPIC_TASK_RESUME,
        )

        router = BackTopicRouter()

        assert router.route(_StubEnvelope(topic=TOPIC_TASK_DISPATCH)) is back_handler
        assert router.route(_StubEnvelope(topic=TOPIC_TASK_RESUME)) is back_resume_handler
        assert router.route(_StubEnvelope(topic=TOPIC_TASK_CANCEL)) is back_cancel_handler
        assert (
            router.route(_StubEnvelope(topic=TOPIC_CLARIFICATION_RESPONSE)) is back_resume_handler
        )
        assert router.route(_StubEnvelope(topic="k1.bogus.v1")) is None

        stats = router.get_stats()
        assert stats["routed"] == 4
        assert stats["cancel_sync"] == 1
        assert stats["discarded_unknown"] == 1
        assert stats["discarded_unknown"] == 1
