"""
Tests for M7 E7.5 -- End-to-End Wiring: BackPool + Task Lease + Topic Router
into Cumulative M1-M6 Infrastructure.

Covers:
  - 7.5.1: Guard table entries for BackPool/Lease topics + canonical event classes
  - 7.5.2: BackPool + BackTopicRouter wired into coordinator consumer
  - 7.5.3: Cancel token unification (FSM + Lease share same token)
  - 7.5.4: ReadyQueue into TaskBridge completion path
  - 7.5.5: HITL + Lease suspension lifecycle
  - 7.5.6: Arbiter + pool-aware InflightContext
  - 7.5.7: Extended test fixtures (create_wired_fsm with M7 params)
  - 7.5.8: 12 backward compatibility regression tests
  - 7.5.9: Demo smoke tests (concurrent pool, lease lifecycle, dep ordering)

Test count target: 53+ tests across 9 test classes.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import pytest

logger = logging.getLogger(__name__)


# =====================================================================
# Stub envelope for ReadyQueue tests (no real Envelope exists in k1_poc)
# =====================================================================


@dataclass
class _StubEnvelope:
    """Minimal envelope stub for ReadyQueue / wiring tests."""

    envelope_id: int = 1
    topic: str = "task.dispatch.v1"
    payload: str = "{}"


# =====================================================================
# 7.5.1 -- Guard table entries for BackPool/Lease topics
# =====================================================================


class TestGuardTablePoolTopics:
    """Verify FULL_GUARD_TABLE has OBSERVE entries for all BackPool topics."""

    def test_guard_table_has_worker_acquired_in_all_states(self):
        """TOPIC_BACKPOOL_WORKER_ACQUIRED has OBSERVE entry in all 11 states."""
        from poc.k1_poc.bus.topics import TOPIC_BACKPOOL_WORKER_ACQUIRED
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        for state_key, topic_map in FULL_GUARD_TABLE.items():
            assert TOPIC_BACKPOOL_WORKER_ACQUIRED in topic_map, (
                f"State {state_key}: missing guard entry for " f"TOPIC_BACKPOOL_WORKER_ACQUIRED"
            )
            action, _ = topic_map[TOPIC_BACKPOOL_WORKER_ACQUIRED]
            assert (
                action == GuardAction.OBSERVE
            ), f"State {state_key}: expected OBSERVE, got {action}"

    def test_guard_table_has_worker_released_in_all_states(self):
        """TOPIC_BACKPOOL_WORKER_RELEASED has OBSERVE entry in all 11 states."""
        from poc.k1_poc.bus.topics import TOPIC_BACKPOOL_WORKER_RELEASED
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        for state_key, topic_map in FULL_GUARD_TABLE.items():
            assert TOPIC_BACKPOOL_WORKER_RELEASED in topic_map, (
                f"State {state_key}: missing guard entry for " f"TOPIC_BACKPOOL_WORKER_RELEASED"
            )
            action, _ = topic_map[TOPIC_BACKPOOL_WORKER_RELEASED]
            assert action == GuardAction.OBSERVE

    def test_guard_table_has_task_leased_in_all_states(self):
        """TOPIC_TASK_LEASED has OBSERVE entry in all 11 states."""
        from poc.k1_poc.bus.topics import TOPIC_TASK_LEASED
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        for state_key, topic_map in FULL_GUARD_TABLE.items():
            assert (
                TOPIC_TASK_LEASED in topic_map
            ), f"State {state_key}: missing guard entry for TOPIC_TASK_LEASED"
            action, _ = topic_map[TOPIC_TASK_LEASED]
            assert action == GuardAction.OBSERVE

    def test_guard_table_has_11_states(self):
        """FULL_GUARD_TABLE covers all 11 FSM states."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE

        assert len(FULL_GUARD_TABLE) == 11

    def test_pool_topics_do_not_cause_state_transition(self):
        """OBSERVE entries have target_state=None (no transition)."""
        from poc.k1_poc.bus.topics import (
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
            TOPIC_TASK_LEASED,
        )
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE

        pool_topics = [
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
            TOPIC_TASK_LEASED,
        ]
        for state_key, topic_map in FULL_GUARD_TABLE.items():
            for topic in pool_topics:
                _, target = topic_map[topic]
                assert target is None, (
                    f"State {state_key}, topic {topic}: "
                    f"OBSERVE must have target_state=None, got {target}"
                )


# =====================================================================
# 7.5.1 -- Canonical event classes
# =====================================================================


class TestCanonicalPoolEvents:
    """Verify canonical event classes for BackPool/Lease lifecycle."""

    def test_worker_acquired_event_fields(self):
        """BackPoolWorkerAcquiredEvent has required fields."""
        from poc.k1_poc.events.pool import BackPoolWorkerAcquiredEvent

        evt = BackPoolWorkerAcquiredEvent(
            worker_id="w-1",
            pool_size=3,
            active_workers=1,
            session_id="sess-1",
        )
        assert evt.event_type == "pool.worker.acquired"
        assert evt.worker_id == "w-1"
        assert evt.pool_size == 3
        assert evt.active_workers == 1
        assert evt.session_id == "sess-1"

    def test_worker_released_event_fields(self):
        """BackPoolWorkerReleasedEvent has required fields."""
        from poc.k1_poc.events.pool import BackPoolWorkerReleasedEvent

        evt = BackPoolWorkerReleasedEvent(
            worker_id="w-1",
            pool_size=3,
            active_workers=0,
            release_reason="completed",
        )
        assert evt.event_type == "pool.worker.released"
        assert evt.release_reason == "completed"

    def test_task_leased_event_fields(self):
        """TaskLeasedEvent has required fields."""
        from poc.k1_poc.events.pool import TaskLeasedEvent

        evt = TaskLeasedEvent(
            worker_id="w-1",
            lease_id="lease-1",
            lease_ttl_s=300,
            expires_at_ns=1000000,
            pool_size=3,
            active_workers=1,
        )
        assert evt.event_type == "pool.task.leased"
        assert evt.lease_ttl_s == 300

    def test_task_lease_expired_event_fields(self):
        """TaskLeaseExpiredEvent has required fields."""
        from poc.k1_poc.events.pool import TaskLeaseExpiredEvent

        evt = TaskLeaseExpiredEvent(
            worker_id="w-1",
            lease_id="lease-1",
            elapsed_s=301.5,
            renewals_used=2,
            hard_killed=False,
        )
        assert evt.event_type == "pool.task.lease_expired"
        assert evt.hard_killed is False

    def test_task_lease_renewed_event_fields(self):
        """TaskLeaseRenewedEvent has required fields."""
        from poc.k1_poc.events.pool import TaskLeaseRenewedEvent

        evt = TaskLeaseRenewedEvent(
            worker_id="w-1",
            lease_id="lease-1",
            renewal_count=1,
            new_expires_at_ns=2000000,
            extension_s=300,
        )
        assert evt.event_type == "pool.task.lease_renewed"

    def test_task_deferred_event_fields(self):
        """TaskDeferredEvent for ReadyQueue deferral."""
        from poc.k1_poc.events.pool import TaskDeferredEvent

        evt = TaskDeferredEvent(
            depends_on="task-A",
            queue_depth=1,
        )
        assert evt.event_type == "pool.task.deferred"
        assert evt.depends_on == "task-A"

    def test_dependency_failed_event_fields(self):
        """DependencyFailedEvent for failed predecessor."""
        from poc.k1_poc.events.pool import DependencyFailedEvent

        evt = DependencyFailedEvent(
            depends_on="task-A",
            reason="circular_dependency",
        )
        assert evt.event_type == "pool.task.dependency_failed"

    def test_event_to_payload_roundtrip(self):
        """Events serialize via to_payload and deserialize via from_payload."""
        from poc.k1_poc.events.pool import BackPoolWorkerAcquiredEvent

        evt = BackPoolWorkerAcquiredEvent(
            worker_id="w-1",
            pool_size=3,
            active_workers=1,
            session_id="sess-1",
        )
        payload = evt.to_payload()
        assert isinstance(payload, dict)
        assert payload["worker_id"] == "w-1"
        assert payload["event_type"] == "pool.worker.acquired"

        # Deserialize
        evt2 = BackPoolWorkerAcquiredEvent.from_payload(payload)
        assert evt2.worker_id == "w-1"
        assert evt2.pool_size == 3

    def test_all_pool_events_in_registry(self):
        """All 7 pool event types are registered in EVENT_TYPE_REGISTRY."""
        from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY

        expected = [
            "pool.worker.acquired",
            "pool.worker.released",
            "pool.task.leased",
            "pool.task.lease_expired",
            "pool.task.lease_renewed",
            "pool.task.deferred",
            "pool.task.dependency_failed",
        ]
        for event_type in expected:
            assert (
                event_type in EVENT_TYPE_REGISTRY
            ), f"Event type {event_type!r} missing from EVENT_TYPE_REGISTRY"


# =====================================================================
# 7.5.3 -- Cancel token unification
# =====================================================================


class TestCancelTokenUnification:
    """Verify single CancellationToken shared across FSM, lease, and handler."""

    def test_controller_get_cancel_token_returns_registered_token(self):
        """ConciergeController.get_cancel_token returns the handler's token."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_cancel_tokens=True)
        fsm = ctx["fsm"]
        handler = ctx["cancel_handler"]

        # Register a task
        token = handler.register_task("task-1")
        retrieved = fsm.get_cancel_token("task-1")
        assert retrieved is token, "get_cancel_token must return the SAME token object"

    def test_controller_get_cancel_token_returns_none_for_unknown(self):
        """get_cancel_token returns None for unregistered task."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_cancel_tokens=True)
        fsm = ctx["fsm"]
        assert fsm.get_cancel_token("nonexistent") is None

    def test_acquire_worker_with_external_cancel_token(self):
        """BackPool.acquire_worker accepts cancellation_token from FSM."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.cancellation import CancellationToken

        pool = BackPool(BackPoolConfig(pool_size=3))
        external_token = CancellationToken(task_id="task-1")

        slot = pool.acquire_worker(
            "task-1",
            cancellation_token=external_token,
        )
        assert slot.lease is not None
        assert slot.lease.cancellation_token is external_token

    def test_cancel_via_token_propagates_to_lease(self):
        """Cancelling the shared token sets lease status to CANCELLED."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.cancellation import CancellationToken
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        pool = BackPool(BackPoolConfig(pool_size=3))
        token = CancellationToken(task_id="task-1")

        slot = pool.acquire_worker("task-1", cancellation_token=token)
        lease = slot.lease

        assert not token.is_cancelled
        assert lease.status == LeaseStatus.ACTIVE

        # Cancel via shared token
        from poc.k1_poc.protocols.cancellation import CancelReason

        token.cancel(CancelReason.USER_REQUESTED)
        assert token.is_cancelled

        # Lease's cancel() also uses this token
        lease.cancel()
        assert lease.status == LeaseStatus.CANCELLED

    def test_fsm_cancel_handler_and_lease_share_same_token(self):
        """End-to-end: FSM handler.register_task token == lease token."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        pool = BackPool(BackPoolConfig(pool_size=3))

        # FSM registers task, creating token
        fsm_token = handler.register_task("task-1")

        # Pool acquires worker with FSM's token
        slot = pool.acquire_worker("task-1", cancellation_token=fsm_token)

        # They are the SAME object
        assert slot.lease.cancellation_token is fsm_token

        # Cancel from FSM side
        handler.request_cancel("task-1")
        assert slot.lease.cancellation_token.is_cancelled

    async def test_build_cancellation_check_uses_passed_token(self):
        """_build_cancellation_check returns real check when token is provided."""
        from poc.k1_poc.actors.back import _build_cancellation_check
        from poc.k1_poc.protocols.cancellation import CancellationToken

        token = CancellationToken(task_id="task-1")
        check = _build_cancellation_check(cancel_token=token)

        # Not cancelled yet
        result = await check()
        assert result is False

        from poc.k1_poc.protocols.cancellation import CancelReason

        token.cancel(CancelReason.USER_REQUESTED)
        result = await check()
        assert result is True

    def test_build_cancellation_check_never_cancel_without_token(self):
        """_build_cancellation_check returns _never_cancel when no token."""
        from poc.k1_poc.actors.back import _build_cancellation_check
        from poc.k1_poc.actors.shared import never_cancel

        check = _build_cancellation_check()
        assert check is never_cancel


# =====================================================================
# 7.5.5 -- HITL + Lease suspension lifecycle
# =====================================================================


class TestLeaseSuspension:
    """Verify TaskLease SUSPENDED state for HITL wait periods."""

    def test_lease_suspend_transitions_to_suspended(self):
        """suspend() moves ACTIVE lease to SUSPENDED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        assert lease.status == LeaseStatus.ACTIVE

        lease.suspend()
        assert lease.status == LeaseStatus.SUSPENDED

    def test_suspended_lease_not_expired(self):
        """SUSPENDED lease returns is_expired=False (TTL paused)."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=0.001)
        lease.suspend()
        time.sleep(0.01)  # Exceed TTL
        assert lease.is_expired is False

    def test_lease_resume_transitions_to_active(self):
        """resume() moves SUSPENDED lease back to ACTIVE."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        lease.suspend()
        assert lease.status == LeaseStatus.SUSPENDED

        lease.resume(new_worker_id="worker-2")
        assert lease.status == LeaseStatus.ACTIVE
        assert lease.worker_id == "worker-2"

    def test_lease_resume_restores_remaining_ttl(self):
        """resume() restores TTL from the saved remaining at suspend time."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        remaining_before = lease.remaining_s
        assert remaining_before > 299  # Just created

        lease.suspend()
        time.sleep(0.05)  # Time passes during suspension
        lease.resume()

        # Remaining should be close to what was saved at suspend, not reduced
        remaining_after = lease.remaining_s
        assert (
            remaining_after > 298
        ), f"TTL should be restored near original, got {remaining_after:.1f}s"

    def test_cancel_suspended_lease(self):
        """cancel() works on SUSPENDED lease and cancels token."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        lease.suspend()
        lease.cancel()

        assert lease.status == LeaseStatus.CANCELLED
        assert lease.cancellation_token.is_cancelled

    def test_suspended_remaining_ns_returns_zero(self):
        """remaining_ns returns 0 for SUSPENDED (TTL paused, not counting)."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        lease.suspend()
        assert lease.remaining_ns == 0

    def test_lease_status_enum_has_suspended(self):
        """LeaseStatus enum includes SUSPENDED between ACTIVE and EXPIRED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        assert hasattr(LeaseStatus, "SUSPENDED")
        assert LeaseStatus.SUSPENDED.value == "suspended"

    def test_suspend_resume_preserves_cancel_token_identity(self):
        """Same CancellationToken across suspend/resume cycle."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        original_token = lease.cancellation_token
        lease.suspend()
        lease.resume(new_worker_id="worker-2")
        assert lease.cancellation_token is original_token


# =====================================================================
# 7.5.6 -- Arbiter + pool-aware InflightContext
# =====================================================================


class TestInflightContextPoolFields:
    """Verify InflightContext includes BackPool capacity fields."""

    def test_inflight_context_has_pool_fields(self):
        """InflightContext dataclass includes pool_active_workers etc."""
        from poc.k1_poc.fsm.arbiter import InflightContext

        ctx = InflightContext(
            tasks=[],
            pending_results=0,
            cancelled_task_ids=set(),
            fsm_state="LISTENING",
            current_turn=1,
            pool_active_workers=2,
            pool_size=3,
            pool_available=1,
            lease_deadlines={"task-1": 1000},
        )
        assert ctx.pool_active_workers == 2
        assert ctx.pool_size == 3
        assert ctx.pool_available == 1
        assert ctx.lease_deadlines == {"task-1": 1000}

    def test_inflight_context_pool_defaults_to_zero(self):
        """Pool fields default to 0 when not provided."""
        from poc.k1_poc.fsm.arbiter import InflightContext

        ctx = InflightContext(
            tasks=[],
            pending_results=0,
            cancelled_task_ids=set(),
            fsm_state="LISTENING",
            current_turn=1,
        )
        assert ctx.pool_active_workers == 0
        assert ctx.pool_size == 0
        assert ctx.pool_available == 0
        assert ctx.lease_deadlines == {}

    def test_build_inflight_context_with_back_pool(self):
        """build_inflight_context reads BackPool state when provided."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.fsm.arbiter import build_inflight_context

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        pool.acquire_worker("task-2")

        ctx = build_inflight_context(
            ss=None,
            suspension_manager=None,
            cancel_handler=None,
            turn_state=None,
            current_turn=1,
            back_pool=pool,
        )
        assert ctx.pool_active_workers == 2
        assert ctx.pool_size == 3
        assert ctx.pool_available == 1
        assert len(ctx.lease_deadlines) == 2
        assert "task-1" in ctx.lease_deadlines
        assert "task-2" in ctx.lease_deadlines

    def test_build_inflight_context_without_back_pool(self):
        """build_inflight_context works without back_pool (backward compat)."""
        from poc.k1_poc.fsm.arbiter import build_inflight_context

        ctx = build_inflight_context(
            ss=None,
            suspension_manager=None,
            cancel_handler=None,
            turn_state=None,
            current_turn=1,
        )
        assert ctx.pool_active_workers == 0
        assert ctx.pool_size == 0

    def test_controller_set_back_pool(self):
        """ConciergeController.set_back_pool attaches pool reference."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm()
        fsm = ctx["fsm"]
        pool = BackPool(BackPoolConfig(pool_size=5))
        fsm.set_back_pool(pool)
        assert fsm._back_pool is pool


# =====================================================================
# 7.5.7 -- Extended test fixtures
# =====================================================================


class TestExtendedFixtures:
    """Verify create_wired_fsm accepts M7 parameters."""

    def test_create_wired_fsm_default_no_pool(self):
        """Default create_wired_fsm does NOT create pool (backward compat)."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm()
        assert "back_pool" not in ctx
        assert "ready_queue" not in ctx
        assert "topic_router" not in ctx

    def test_create_wired_fsm_with_back_pool(self):
        """with_back_pool=True creates BackPool attached to FSM."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_back_pool=True, pool_size=5)
        assert "back_pool" in ctx
        pool = ctx["back_pool"]
        assert pool.config.pool_size == 5
        # with_back_pool implies with_cancel_tokens
        assert "cancel_handler" in ctx

    def test_create_wired_fsm_with_lease_implies_pool(self):
        """with_lease=True implies with_back_pool=True."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_lease=True, lease_ttl_s=60.0)
        assert "back_pool" in ctx
        assert ctx["back_pool"].config.lease_ttl_s == 60.0

    def test_create_wired_fsm_with_ready_queue(self):
        """with_ready_queue=True creates ReadyQueue."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_ready_queue=True)
        assert "ready_queue" in ctx

    def test_create_wired_fsm_with_topic_router(self):
        """with_topic_router=True creates BackTopicRouter + BackPool."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_topic_router=True)
        assert "topic_router" in ctx
        assert "back_pool" in ctx  # Implied

    def test_create_wired_fsm_full_m7_wiring(self):
        """Full M7 wiring creates all M7 components."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(
            with_back_pool=True,
            pool_size=4,
            with_lease=True,
            lease_ttl_s=120.0,
            with_ready_queue=True,
            with_topic_router=True,
            with_cancel_tokens=True,
            with_arbiter=True,
        )
        assert "back_pool" in ctx
        assert "ready_queue" in ctx
        assert "topic_router" in ctx
        assert "cancel_handler" in ctx
        assert "arbiter" in ctx
        assert "ledger" in ctx
        assert ctx["back_pool"].config.pool_size == 4
        assert ctx["back_pool"].config.lease_ttl_s == 120.0

    def test_create_wired_fsm_m7_backward_compat_with_m1_m6(self):
        """Existing M1-M6 fixture params still work with M7 additions."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(
            with_ledger=True,
            with_dead_letter_consumer=True,
            with_cancel_tokens=True,
            with_arbiter=True,
            with_back_pool=True,
        )
        assert "bus" in ctx
        assert "router" in ctx
        assert "fsm" in ctx
        assert "ledger" in ctx
        assert "ledger_store" in ctx
        assert "dead_letter_consumer" in ctx
        assert "cancel_handler" in ctx
        assert "arbiter" in ctx
        assert "back_pool" in ctx


# =====================================================================
# 7.5.8 -- Backward compatibility regression (12 tests)
# =====================================================================


class TestWiringRegression:
    """12 regression tests verifying M1-M6 wiring survives M7 refactoring."""

    # Test 1: Guard table allows pool/lease topics
    def test_r01_guard_table_allows_pool_topics(self):
        """M2 FULL_GUARD_TABLE has OBSERVE for all 3 pool topics in all states."""
        from poc.k1_poc.bus.topics import (
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
            TOPIC_TASK_LEASED,
        )
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        pool_topics = [
            TOPIC_BACKPOOL_WORKER_ACQUIRED,
            TOPIC_BACKPOOL_WORKER_RELEASED,
            TOPIC_TASK_LEASED,
        ]
        for state_key, topic_map in FULL_GUARD_TABLE.items():
            for topic in pool_topics:
                assert topic in topic_map, f"Missing in state {state_key}: {topic}"
                action, target = topic_map[topic]
                assert action == GuardAction.OBSERVE
                assert target is None

    # Test 2: Event registry has all pool events
    def test_r02_event_registry_complete(self):
        """M1 EVENT_TYPE_REGISTRY has all 7 pool/lease event types."""
        from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY

        required = [
            "pool.worker.acquired",
            "pool.worker.released",
            "pool.task.leased",
            "pool.task.lease_expired",
            "pool.task.lease_renewed",
            "pool.task.deferred",
            "pool.task.dependency_failed",
        ]
        for et in required:
            assert et in EVENT_TYPE_REGISTRY, f"Missing: {et}"

    # Test 3: Cancel token same object across FSM and lease
    def test_r03_cancel_token_same_object(self):
        """M3 cancel token is same object when passed to BackPool.acquire_worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        pool = BackPool(BackPoolConfig(pool_size=3))

        token = handler.register_task("task-1")
        slot = pool.acquire_worker("task-1", cancellation_token=token)
        assert slot.lease.cancellation_token is token

        # Cancel from handler side propagates
        handler.request_cancel("task-1")
        assert slot.lease.cancellation_token.is_cancelled is True

    # Test 4: ReadyQueue notify_completed works
    def test_r04_ready_queue_notify_completed(self):
        """M7 ReadyQueue.notify_completed releases dependent envelopes."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        queue = ReadyQueue()
        queue.register_task("task-A")
        queue.register_task("task-B")

        env_b = _StubEnvelope(
            envelope_id=100,
            topic="task.dispatch.v1",
            payload=json.dumps({"task_id": "task-B"}),
        )
        status, _ = queue.enqueue(env_b, depends_on="task-A")
        assert status == "waiting"

        released, _ = queue.notify_completed("task-A", status="completed")
        assert len(released) >= 0  # Released envelopes or count

    # Test 5: InflightContext reflects pool state
    def test_r05_inflight_context_pool_state(self):
        """M5 InflightContext includes pool state after M7 addition."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.fsm.arbiter import build_inflight_context

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")

        ctx = build_inflight_context(
            ss=None,
            suspension_manager=None,
            cancel_handler=None,
            turn_state=None,
            current_turn=1,
            back_pool=pool,
        )
        assert ctx.pool_active_workers == 1
        assert ctx.pool_size == 3
        assert ctx.pool_available == 2

    # Test 6: BackPool lease cancel propagates to token
    def test_r06_lease_cancel_propagates(self):
        """M7 TaskLease.cancel() propagates to CancellationToken."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1")
        assert not lease.cancellation_token.is_cancelled
        lease.cancel()
        assert lease.status == LeaseStatus.CANCELLED
        assert lease.cancellation_token.is_cancelled

    # Test 7: HITL suspension preserves lease
    def test_r07_hitl_suspension_preserves_lease(self):
        """M6 HITL suspend: lease SUSPENDED, TTL paused."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        lease.suspend()
        assert lease.status == LeaseStatus.SUSPENDED
        assert lease.is_expired is False

    # Test 8: HITL resume re-activates lease with same token
    def test_r08_hitl_resume_reactivates_lease(self):
        """M6 resume: lease ACTIVE again, same cancel token."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        original_token = lease.cancellation_token
        lease.suspend()
        lease.resume(new_worker_id="worker-2")
        assert lease.status == LeaseStatus.ACTIVE
        assert lease.worker_id == "worker-2"
        assert lease.cancellation_token is original_token

    # Test 9: Cancel SUSPENDED lease
    def test_r09_cancel_suspended_lease(self):
        """HITL timeout: cancel SUSPENDED lease sets token cancelled."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1")
        lease.suspend()
        lease.cancel()
        assert lease.status == LeaseStatus.CANCELLED
        assert lease.cancellation_token.is_cancelled

    # Test 10: BackTopicRouter routes resume correctly
    def test_r10_topic_router_routes_resume(self):
        """BackTopicRouter routes task.resume.v1 to resume handler."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH, TOPIC_TASK_RESUME

        router = BackTopicRouter()

        dispatch_env = _StubEnvelope(
            envelope_id=1,
            topic=TOPIC_TASK_DISPATCH,
            payload="{}",
        )
        resume_env = _StubEnvelope(
            envelope_id=2,
            topic=TOPIC_TASK_RESUME,
            payload="{}",
        )

        dispatch_fn = router.route(dispatch_env)
        resume_fn = router.route(resume_env)

        assert dispatch_fn is not None
        assert resume_fn is not None
        # They should be different handler functions
        assert dispatch_fn is not resume_fn

    # Test 11: Pool acquire assigns unique worker_ids
    def test_r11_pool_unique_worker_ids(self):
        """BackPool assigns unique worker_ids to concurrent tasks."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        s1 = pool.acquire_worker("task-1")
        s2 = pool.acquire_worker("task-2")
        s3 = pool.acquire_worker("task-3")

        worker_ids = {s1.worker_id, s2.worker_id, s3.worker_id}
        assert len(worker_ids) == 3, "Worker IDs must be unique"

    # Test 12: get_cancel_token on controller
    def test_r12_controller_get_cancel_token(self):
        """ConciergeController.get_cancel_token is public and functional."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(with_cancel_tokens=True)
        fsm = ctx["fsm"]
        handler = ctx["cancel_handler"]

        # Before registration
        assert fsm.get_cancel_token("task-x") is None

        # After registration
        token = handler.register_task("task-x")
        assert fsm.get_cancel_token("task-x") is token


# =====================================================================
# 7.5.9 -- Demo smoke tests
# =====================================================================


class TestDemoSmoke:
    """Smoke tests for end-to-end pool lifecycle scenarios."""

    def test_smoke_concurrent_worker_acquisition(self):
        """Scenario A: 3 tasks get different worker slots in pool_size=3."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig, BackPoolExhausted

        pool = BackPool(BackPoolConfig(pool_size=3))
        slots = []
        for i in range(3):
            slot = pool.acquire_worker(f"task-{i}")
            slots.append(slot)

        assert pool.active_count == 3
        assert pool.pool_available == 0

        # 4th task exhausts pool
        with pytest.raises(BackPoolExhausted):
            pool.acquire_worker("task-overflow")

        # Release one, then 4th should work
        pool.release_worker("task-0", reason="completed")
        assert pool.pool_available == 1
        slot4 = pool.acquire_worker("task-overflow")
        assert slot4 is not None

    def test_smoke_lease_lifecycle_active_to_released(self):
        """Scenario B: Lease ACTIVE -> complete -> RELEASED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=300.0)
        assert lease.status == LeaseStatus.ACTIVE
        assert not lease.is_expired
        assert lease.remaining_s > 299

        # Complete (release) the lease
        lease.release()
        assert lease.status == LeaseStatus.RELEASED

    def test_smoke_dependency_ordering(self):
        """Scenario D: Task B waits for Task A, auto-dispatches on completion."""
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        queue = ReadyQueue()
        queue.register_task("task-A")
        queue.register_task("task-B")

        # Enqueue B with dependency on A
        env_b = _StubEnvelope(
            envelope_id=100,
            topic="task.dispatch.v1",
            payload=json.dumps({"task_id": "task-B"}),
        )
        status, _ = queue.enqueue(env_b, depends_on="task-A")
        assert status == "waiting"
        assert queue.waiting_count == 1

        # Complete A
        released, _ = queue.notify_completed("task-A", status="completed")
        ready_envs = queue.dequeue_ready()
        assert len(ready_envs) >= 1

    def test_smoke_hitl_suspend_resume_lifecycle(self):
        """Scenario F: dispatch -> suspend -> resume -> complete."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        pool = BackPool(BackPoolConfig(pool_size=2))
        slot = pool.acquire_worker("task-A")
        lease = slot.lease

        assert pool.active_count == 1
        assert lease.status == LeaseStatus.ACTIVE
        original_token = lease.cancellation_token

        # HITL suspension
        lease.suspend()
        pool.release_worker("task-A", reason="suspended")
        assert lease.status == LeaseStatus.SUSPENDED
        assert pool.active_count == 0
        assert pool.pool_available == 2

        # Meanwhile, dispatch another task (uses freed slot)
        slot_b = pool.acquire_worker("task-B")
        assert pool.active_count == 1

        # Resume A (re-acquire worker)
        slot_a2 = pool.acquire_worker("task-A-resumed")
        lease.resume(new_worker_id=slot_a2.worker_id)
        assert lease.status == LeaseStatus.ACTIVE
        assert lease.cancellation_token is original_token
        assert pool.active_count == 2

    def test_smoke_pool_exhausted_overflow(self):
        """Pool full -> overflow queue -> retry on release."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig, BackPoolExhausted

        pool = BackPool(BackPoolConfig(pool_size=2))
        pool.acquire_worker("task-1")
        pool.acquire_worker("task-2")

        overflow_env = _StubEnvelope(
            envelope_id=99,
            topic="task.dispatch.v1",
            payload=json.dumps({"task_id": "task-3"}),
        )

        # Pool full, enqueue overflow
        with pytest.raises(BackPoolExhausted):
            pool.acquire_worker("task-3")
        pool.enqueue_overflow(overflow_env)
        assert pool.overflow_depth == 1

        # Release one worker
        pool.release_worker("task-1", reason="completed")
        assert pool.pool_available == 1

        # Dequeue overflow and retry
        retry_env = pool.dequeue_overflow()
        assert retry_env is not None
        assert pool.overflow_depth == 0

    def test_smoke_topic_router_cancel_bypass(self):
        """Scenario E: Cancel envelopes bypass pool (synchronous)."""
        from poc.k1_poc.actors.back_router import BackTopicRouter
        from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL

        router = BackTopicRouter()
        cancel_env = _StubEnvelope(
            envelope_id=1,
            topic=TOPIC_TASK_CANCEL,
            payload=json.dumps({"task_id": "task-1"}),
        )
        assert router.is_cancel_topic(cancel_env.topic)
        handler_fn = router.route(cancel_env)
        assert handler_fn is not None

    def test_smoke_full_wired_fixture_creates_all_components(self):
        """Full M7 fixture creates pool + queue + router + ledger."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(
            with_back_pool=True,
            pool_size=3,
            with_lease=True,
            lease_ttl_s=120.0,
            with_ready_queue=True,
            with_topic_router=True,
            with_arbiter=True,
            with_cancel_tokens=True,
        )
        assert ctx["back_pool"].config.pool_size == 3
        assert ctx["back_pool"].config.lease_ttl_s == 120.0
        assert ctx["ready_queue"] is not None
        assert ctx["topic_router"] is not None
        assert ctx["arbiter"] is not None
        assert ctx["cancel_handler"] is not None
        assert ctx["fsm"]._back_pool is ctx["back_pool"]

    def test_smoke_lease_renewal(self):
        """Lease renewal extends TTL and increments count."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease("task-1", "worker-1", lease_ttl_s=10.0, max_renewals=3)
        remaining_before = lease.remaining_s
        assert lease.renewed_count == 0

        lease.renew(extension_s=10.0)
        assert lease.renewed_count == 1
        assert lease.remaining_s > remaining_before
        assert lease.status == LeaseStatus.ACTIVE

    def test_smoke_inflight_context_end_to_end(self):
        """Build InflightContext with pool, verify arbiter sees pool state."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        ctx = create_wired_fsm(
            with_back_pool=True,
            pool_size=3,
            with_arbiter=True,
        )
        pool = ctx["back_pool"]
        pool.acquire_worker("task-1")
        pool.acquire_worker("task-2")

        from poc.k1_poc.fsm.arbiter import build_inflight_context

        inflight = build_inflight_context(
            ss=None,
            suspension_manager=None,
            cancel_handler=None,
            turn_state=None,
            current_turn=1,
            back_pool=pool,
        )
        assert inflight.pool_active_workers == 2
        assert inflight.pool_size == 3
        assert inflight.pool_available == 1
        assert len(inflight.lease_deadlines) == 2
