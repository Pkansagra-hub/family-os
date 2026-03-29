"""
Tests for M7 E7.2 -- Task Lease Model.

Covers:
  - 7.2.1: TaskLease dataclass, LeaseStatus enum, factory function
  - 7.2.2: BackPool creates TaskLease at acquire_worker, lease binds to slot
  - 7.2.3: Lease expiry watcher (cooperative cancel -> grace -> hard kill)
  - 7.2.4: task.leased.v1 bus event emission
  - 7.2.5: Lease renewal protocol (renew, max_renewals, denied after max)

Test count target: ~45 tests across 8 test classes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import pytest

logger = logging.getLogger(__name__)


# =====================================================================
# 7.2.1 -- LeaseStatus enum
# =====================================================================


class TestLeaseStatus:
    """Test LeaseStatus enum values."""

    def test_status_values(self):
        """LeaseStatus has 4 expected values."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        assert LeaseStatus.ACTIVE.value == "active"
        assert LeaseStatus.EXPIRED.value == "expired"
        assert LeaseStatus.RELEASED.value == "released"
        assert LeaseStatus.CANCELLED.value == "cancelled"

    def test_status_is_string_enum(self):
        """LeaseStatus values are strings."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        assert isinstance(LeaseStatus.ACTIVE, str)
        assert LeaseStatus.ACTIVE == "active"


# =====================================================================
# 7.2.1 -- TaskLease dataclass
# =====================================================================


class TestTaskLease:
    """Test TaskLease dataclass fields, properties, and methods."""

    def test_create_task_lease_factory(self):
        """create_task_lease returns a valid TaskLease with computed expires_at."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease(
            task_id="task-1",
            worker_id="worker-1",
            lease_ttl_s=300.0,
        )
        assert lease.task_id == "task-1"
        assert lease.worker_id == "worker-1"
        assert lease.lease_id  # non-empty UUID
        assert lease.granted_at_ns > 0
        assert lease.expires_at_ns > lease.granted_at_ns
        assert lease.status == LeaseStatus.ACTIVE
        assert lease.renewed_count == 0
        assert lease.max_renewals == 3
        assert lease.cancellation_token is not None
        assert lease.cancellation_token.task_id == "task-1"

    def test_lease_expires_at_computed(self):
        """expires_at_ns = granted_at_ns + lease_ttl_s * 1e9."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(
            task_id="task-1",
            worker_id="worker-1",
            lease_ttl_s=60.0,
        )
        expected_delta_ns = int(60.0 * 1e9)
        actual_delta_ns = lease.expires_at_ns - lease.granted_at_ns
        # Allow 100ms tolerance for execution time
        assert abs(actual_delta_ns - expected_delta_ns) < int(0.1 * 1e9)

    def test_lease_not_expired_initially(self):
        """Freshly created lease is not expired."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(
            task_id="task-1",
            worker_id="worker-1",
            lease_ttl_s=300.0,
        )
        assert lease.is_expired is False
        assert lease.remaining_s > 299.0

    def test_lease_is_expired_past_ttl(self):
        """Lease with expires_at_ns in the past is expired."""
        from poc.k1_poc.protocols.task_lease import TaskLease

        lease = TaskLease(
            task_id="task-1",
            worker_id="worker-1",
            granted_at_ns=time.monotonic_ns() - int(2e9),
            expires_at_ns=time.monotonic_ns() - int(1e9),
        )
        assert lease.is_expired is True
        assert lease.remaining_ns == 0
        assert lease.remaining_s == 0.0

    def test_lease_remaining_ns(self):
        """remaining_ns returns positive value for active lease."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(
            task_id="task-1",
            worker_id="worker-1",
            lease_ttl_s=300.0,
        )
        assert lease.remaining_ns > 0
        assert lease.remaining_s > 0.0

    def test_auto_creates_cancellation_token(self):
        """TaskLease auto-creates CancellationToken if not provided."""
        from poc.k1_poc.protocols.task_lease import TaskLease

        lease = TaskLease(task_id="task-1", worker_id="worker-1")
        assert lease.cancellation_token is not None
        assert lease.cancellation_token.task_id == "task-1"

    def test_custom_cancellation_token(self):
        """TaskLease accepts custom CancellationToken."""
        from poc.k1_poc.protocols.cancellation import CancellationToken
        from poc.k1_poc.protocols.task_lease import create_task_lease

        token = CancellationToken(task_id="task-1")
        lease = create_task_lease(
            task_id="task-1",
            worker_id="worker-1",
            cancellation_token=token,
        )
        assert lease.cancellation_token is token

    def test_unique_lease_ids(self):
        """Two leases get different lease_ids."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease1 = create_task_lease(task_id="t1", worker_id="w1")
        lease2 = create_task_lease(task_id="t2", worker_id="w2")
        assert lease1.lease_id != lease2.lease_id


# =====================================================================
# 7.2.1 -- TaskLease status transitions
# =====================================================================


class TestTaskLeaseTransitions:
    """Test lease status transitions: release, expire, cancel."""

    def test_release_sets_released(self):
        """release() transitions ACTIVE -> RELEASED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1")
        assert lease.status == LeaseStatus.ACTIVE

        lease.release()
        assert lease.status == LeaseStatus.RELEASED

    def test_expire_sets_expired(self):
        """expire() transitions ACTIVE -> EXPIRED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1")
        lease.expire()
        assert lease.status == LeaseStatus.EXPIRED

    def test_cancel_sets_cancelled(self):
        """cancel() transitions ACTIVE -> CANCELLED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1")
        lease.cancel()
        assert lease.status == LeaseStatus.CANCELLED

    def test_release_only_from_active(self):
        """release() is a no-op if already RELEASED."""
        from poc.k1_poc.protocols.task_lease import LeaseStatus, create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1")
        lease.release()
        assert lease.status == LeaseStatus.RELEASED

        # No-op: already released
        lease.release()
        assert lease.status == LeaseStatus.RELEASED

    def test_is_expired_for_non_active_statuses(self):
        """is_expired returns True for EXPIRED, RELEASED, CANCELLED."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        for transition in ["release", "expire", "cancel"]:
            lease = create_task_lease(task_id="t1", worker_id="w1")
            getattr(lease, transition)()
            assert lease.is_expired is True, f"{transition} should make is_expired True"


# =====================================================================
# 7.2.1 -- TaskLease to_payload
# =====================================================================


class TestTaskLeasePayload:
    """Test TaskLease.to_payload() serialization."""

    def test_to_payload_contains_required_fields(self):
        """to_payload returns dict with all required fields."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1", lease_ttl_s=300.0)
        payload = lease.to_payload()

        assert payload["task_id"] == "t1"
        assert payload["worker_id"] == "w1"
        assert payload["lease_id"] == lease.lease_id
        assert payload["granted_at_ns"] == lease.granted_at_ns
        assert payload["expires_at_ns"] == lease.expires_at_ns
        assert payload["lease_expires_at"] == lease.expires_at_ns
        assert payload["status"] == "active"
        assert payload["renewed_count"] == 0
        assert payload["max_renewals"] == 3
        assert isinstance(payload["remaining_s"], float)

    def test_to_payload_json_serializable(self):
        """to_payload output is JSON-serializable."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1")
        payload = lease.to_payload()
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)
        assert deserialized["task_id"] == "t1"

    def test_repr(self):
        """TaskLease repr shows key fields."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1")
        r = repr(lease)
        assert "t1" in r
        assert "w1" in r
        assert "active" in r


# =====================================================================
# 7.2.2 -- BackPool creates TaskLease at acquire_worker
# =====================================================================


class TestBackPoolLeaseIntegration:
    """Test that BackPool.acquire_worker creates and binds TaskLease."""

    def test_acquire_creates_lease(self):
        """acquire_worker creates a TaskLease bound to the WorkerSlot."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=300.0))
        slot = pool.acquire_worker("task-1")

        assert slot.lease is not None
        assert slot.lease.task_id == "task-1"
        assert slot.lease.worker_id == slot.worker_id
        assert slot.lease.status == LeaseStatus.ACTIVE
        assert slot.lease.cancellation_token is not None

    def test_lease_worker_id_matches_slot(self):
        """Lease worker_id matches the WorkerSlot worker_id."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        slot = pool.acquire_worker("task-1")

        assert slot.worker_id == slot.lease.worker_id

    def test_lease_ttl_from_config(self):
        """Lease TTL uses BackPoolConfig.lease_ttl_s."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=120.0))
        slot = pool.acquire_worker("task-1")

        # TTL should be ~120s
        assert slot.lease.remaining_s > 119.0
        assert slot.lease.remaining_s <= 120.1

    def test_lease_max_renewals_from_config(self):
        """Lease max_renewals uses BackPoolConfig.max_renewals."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, max_renewals=5))
        slot = pool.acquire_worker("task-1")

        assert slot.lease.max_renewals == 5

    def test_release_updates_lease_status_completed(self):
        """release_worker with reason='completed' sets lease to RELEASED."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        released = pool.release_worker("task-1", reason="completed")

        assert released.lease.status == LeaseStatus.RELEASED

    def test_release_updates_lease_status_cancelled(self):
        """release_worker with reason='cancelled' sets lease to CANCELLED."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        released = pool.release_worker("task-1", reason="cancelled")

        assert released.lease.status == LeaseStatus.CANCELLED

    def test_release_updates_lease_status_expired(self):
        """release_worker with reason='lease_expired' sets lease to EXPIRED."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig
        from poc.k1_poc.protocols.task_lease import LeaseStatus

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")
        released = pool.release_worker("task-1", reason="lease_expired")

        assert released.lease.status == LeaseStatus.EXPIRED

    def test_get_lease_returns_lease(self):
        """get_lease returns the TaskLease for an active worker."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        pool.acquire_worker("task-1")

        lease = pool.get_lease("task-1")
        assert lease is not None
        assert lease.task_id == "task-1"

    def test_get_lease_returns_none_for_unknown(self):
        """get_lease returns None for unknown task_id."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        assert pool.get_lease("unknown") is None

    def test_pool_state_includes_lease_info(self):
        """get_pool_state includes lease status, remaining, and renewals."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=300.0))
        pool.acquire_worker("task-1")

        state = pool.get_pool_state()
        worker = state["workers"][0]
        assert worker["lease_status"] == "active"
        assert worker["lease_remaining_s"] > 299.0
        assert worker["lease_renewed_count"] == 0


# =====================================================================
# 7.2.5 -- Lease renewal protocol
# =====================================================================


class TestLeaseRenewal:
    """Test TaskLease renewal via BackPool.renew_lease."""

    def test_renew_extends_expiry(self):
        """renew() extends expires_at_ns by extension_s."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1", lease_ttl_s=60.0)
        old_expires = lease.expires_at_ns

        result = lease.renew(extension_s=30.0)
        assert result is True
        assert lease.expires_at_ns > old_expires
        assert lease.renewed_count == 1

    def test_renew_increments_count(self):
        """Each successful renew increments renewed_count."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1", max_renewals=3)
        lease.renew(extension_s=60.0)
        assert lease.renewed_count == 1
        lease.renew(extension_s=60.0)
        assert lease.renewed_count == 2
        lease.renew(extension_s=60.0)
        assert lease.renewed_count == 3

    def test_renew_denied_after_max(self):
        """renew() returns False after max_renewals."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1", max_renewals=2)
        assert lease.renew(extension_s=60.0) is True
        assert lease.renew(extension_s=60.0) is True
        assert lease.renew(extension_s=60.0) is False
        assert lease.renewed_count == 2

    def test_renew_denied_for_non_active(self):
        """renew() returns False for RELEASED/EXPIRED/CANCELLED leases."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        for transition in ["release", "expire", "cancel"]:
            lease = create_task_lease(task_id="t1", worker_id="w1")
            getattr(lease, transition)()
            assert lease.renew(extension_s=60.0) is False

    def test_renew_via_backpool(self):
        """BackPool.renew_lease delegates to the lease."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=60.0))
        pool.acquire_worker("task-1")

        assert pool.renew_lease("task-1", extension_s=30.0) is True
        lease = pool.get_lease("task-1")
        assert lease.renewed_count == 1

    def test_renew_via_backpool_unknown_task(self):
        """BackPool.renew_lease returns False for unknown task."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3))
        assert pool.renew_lease("unknown", extension_s=30.0) is False

    def test_extension_ns_takes_priority(self):
        """renew(extension_ns=X) uses nanoseconds instead of seconds."""
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(task_id="t1", worker_id="w1", lease_ttl_s=60.0)
        old_expires = lease.expires_at_ns

        lease.renew(extension_ns=int(10e9))  # 10 seconds in ns
        assert lease.expires_at_ns == old_expires + int(10e9)


# =====================================================================
# 7.2.3 -- Lease expiry watcher
# =====================================================================


class TestLeaseExpiryWatcher:
    """Test BackPool lease expiry detection and worker reclamation."""

    def test_get_expired_leases_none_initially(self):
        """No expired leases when all are fresh."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=300.0))
        pool.acquire_worker("task-1")

        assert pool.get_expired_leases() == []

    def test_get_expired_leases_detects_expired(self):
        """get_expired_leases returns slots with expired leases."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=300.0))
        slot = pool.acquire_worker("task-1")

        # Force expiry by setting expires_at_ns to the past
        slot.lease.expires_at_ns = time.monotonic_ns() - int(1e9)

        expired = pool.get_expired_leases()
        assert len(expired) == 1
        assert expired[0].task_id == "task-1"

    @pytest.mark.asyncio
    async def test_reclaim_expired_worker_cooperative(self):
        """Expired lease triggers cooperative cancel via CancellationToken."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, lease_ttl_s=300.0))
        slot = pool.acquire_worker("task-1")

        # Force expiry
        slot.lease.expires_at_ns = time.monotonic_ns() - int(1e9)

        # Create a mock async task that checks cancellation
        cancel_detected = asyncio.Event()

        async def _worker():
            try:
                while True:
                    await asyncio.sleep(0.01)
                    if slot.lease.cancellation_token.is_cancelled:
                        cancel_detected.set()
                        return
            except asyncio.CancelledError:
                return

        task = asyncio.create_task(_worker())
        slot.bind_task(task)

        # Reclaim the expired worker
        await pool._reclaim_expired_worker(slot)

        # Cancellation token should have been triggered
        assert slot.lease.cancellation_token.is_cancelled
        assert cancel_detected.is_set()

    @pytest.mark.asyncio
    async def test_reclaim_expired_worker_hard_kill(self):
        """Worker that ignores cooperative cancel gets hard-killed."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(
            BackPoolConfig(
                pool_size=3,
                lease_ttl_s=300.0,
                lease_grace_period_s=0.1,  # Very short grace for test
            )
        )
        slot = pool.acquire_worker("task-1")

        # Force expiry
        slot.lease.expires_at_ns = time.monotonic_ns() - int(1e9)

        # Create a worker that IGNORES cancellation (simulates hung LLM)
        async def _hung_worker():
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                pass  # Expected hard cancel

        task = asyncio.create_task(_hung_worker())
        slot.bind_task(task)

        # Reclaim should hard-cancel after grace period
        await pool._reclaim_expired_worker(slot)

        # Worker slot should be released
        assert pool.active_count == 0
        assert task.done()

    @pytest.mark.asyncio
    async def test_start_stop_lease_watcher(self):
        """Lease watcher can be started and stopped."""
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool = BackPool(BackPoolConfig(pool_size=3, reclaim_check_interval_s=0.05))
        watcher_task = await pool.start_lease_watcher()
        assert not watcher_task.done()

        await pool.stop_lease_watcher()
        # Give a moment for cancellation to propagate
        await asyncio.sleep(0.05)
        assert watcher_task.done()


# =====================================================================
# 7.2.4 -- task.leased.v1 bus event
# =====================================================================


class TestTaskLeasedEvent:
    """Test task.leased.v1 topic and builder."""

    def test_task_leased_topic_in_all_topics(self):
        """TOPIC_TASK_LEASED is in ALL_TOPICS."""
        from poc.k1_poc.bus.topics import ALL_TOPICS, TOPIC_TASK_LEASED

        assert TOPIC_TASK_LEASED in ALL_TOPICS

    def test_task_leased_topic_is_strict(self):
        """TOPIC_TASK_LEASED is in STRICT_TOPICS."""
        from poc.k1_poc.bus.topics import STRICT_TOPICS, TOPIC_TASK_LEASED

        assert TOPIC_TASK_LEASED in STRICT_TOPICS

    def test_build_task_leased(self):
        """build_task_leased creates correct envelope."""
        from poc.k1_poc.bus.builders import build_task_leased
        from poc.k1_poc.bus.topics import TOPIC_TASK_LEASED

        env = build_task_leased(
            payload={
                "task_id": "task-1",
                "worker_id": "worker-1",
                "lease_id": "lease-abc",
                "lease_expires_at": 12345678,
                "status": "active",
            }
        )
        assert env.topic == TOPIC_TASK_LEASED
        payload = json.loads(env.payload)
        assert payload["task_id"] == "task-1"
        assert payload["lease_id"] == "lease-abc"

    def test_task_leased_in_builders_registry(self):
        """TOPIC_TASK_LEASED is in BUILDERS dict."""
        from poc.k1_poc.bus.builders import BUILDERS
        from poc.k1_poc.bus.topics import TOPIC_TASK_LEASED

        assert TOPIC_TASK_LEASED in BUILDERS

    def test_task_leased_in_enriched_registry(self):
        """TOPIC_TASK_LEASED is in get_builder_registry with BACKGROUND priority."""
        from poc.k1_poc.bus.builders import get_builder_registry
        from poc.k1_poc.bus.topics import TOPIC_TASK_LEASED

        registry = get_builder_registry()
        assert TOPIC_TASK_LEASED in registry
        assert registry[TOPIC_TASK_LEASED].priority.value == 3  # BACKGROUND

    def test_topic_count_increased(self):
        """ALL_TOPICS count is now 38 (37 from E7.1 + 1 from E7.2)."""
        from poc.k1_poc.bus.topics import ALL_TOPICS

        assert len(ALL_TOPICS) == 40


# =====================================================================
# 7.2.2 -- BackPoolConfig new fields
# =====================================================================


class TestBackPoolConfigE72:
    """Test BackPoolConfig E7.2 additions (max_renewals, lease_grace_period_s)."""

    def test_default_max_renewals(self):
        """BackPoolConfig default max_renewals is 3."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        config = BackPoolConfig()
        assert config.max_renewals == 3

    def test_default_lease_grace_period(self):
        """BackPoolConfig default lease_grace_period_s is 5.0."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        config = BackPoolConfig()
        assert config.lease_grace_period_s == 5.0

    def test_custom_max_renewals(self):
        """BackPoolConfig accepts custom max_renewals."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        config = BackPoolConfig(max_renewals=5)
        assert config.max_renewals == 5

    def test_invalid_max_renewals(self):
        """BackPoolConfig rejects negative max_renewals."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="max_renewals must be >= 0"):
            BackPoolConfig(max_renewals=-1)

    def test_invalid_grace_period(self):
        """BackPoolConfig rejects negative lease_grace_period_s."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        with pytest.raises(ValueError, match="lease_grace_period_s must be >= 0"):
            BackPoolConfig(lease_grace_period_s=-1)

    def test_zero_max_renewals_allowed(self):
        """BackPoolConfig allows max_renewals=0 (no renewals)."""
        from poc.k1_poc.actors.back_pool import BackPoolConfig

        config = BackPoolConfig(max_renewals=0)
        assert config.max_renewals == 0


# =====================================================================
# 7.2 -- Fixture helpers
# =====================================================================


class TestLeaseFixtures:
    """Test M7 E7.2 fixture helpers."""

    def test_create_test_task_lease(self):
        """create_test_task_lease returns configured TaskLease."""
        from poc.k1_poc.testing.fixtures import create_test_task_lease

        lease = create_test_task_lease(task_id="my-task", worker_id="my-worker")
        assert lease.task_id == "my-task"
        assert lease.worker_id == "my-worker"

    def test_create_test_expired_lease(self):
        """create_test_expired_lease returns already-expired lease."""
        from poc.k1_poc.testing.fixtures import create_test_expired_lease

        lease = create_test_expired_lease()
        assert lease.is_expired is True

    def test_assert_lease_state_passes(self):
        """assert_lease_state passes when values match."""
        from poc.k1_poc.testing.fixtures import assert_lease_state, create_test_task_lease

        lease = create_test_task_lease()
        assert_lease_state(lease, status="active", is_expired=False, renewed_count=0)

    def test_assert_lease_state_fails(self):
        """assert_lease_state raises AssertionError on mismatch."""
        from poc.k1_poc.testing.fixtures import assert_lease_state, create_test_task_lease

        lease = create_test_task_lease()
        with pytest.raises(AssertionError, match="Expected lease status"):
            assert_lease_state(lease, status="expired")
