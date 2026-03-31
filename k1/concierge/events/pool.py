"""
k1.concierge.events.pool -- V3 canonical BackPool/Lease lifecycle events.

M7 E7.5.1: Five canonical event classes for pool and lease observability.
M7 E7.5.4: Two canonical event classes for dependency ordering.

Events:
    BackPoolWorkerAcquiredEvent  -- Worker slot assigned to a task.
    BackPoolWorkerReleasedEvent  -- Worker slot returned to the pool.
    TaskLeasedEvent              -- Lease created for task/worker binding.
    TaskLeaseExpiredEvent        -- Lease TTL expired (auto-cancel).
    TaskLeaseRenewedEvent        -- Lease TTL extended (long-running task).
    TaskDeferredEvent            -- Task held in ReadyQueue (depends_on).
    DependencyFailedEvent        -- Task failed due to dependency issue.

Topic mapping:
    BackPoolWorkerAcquiredEvent -> k1.backpool.worker.acquired.v1
    BackPoolWorkerReleasedEvent -> k1.backpool.worker.released.v1
    TaskLeasedEvent             -> k1.backpool.task.leased.v1
    TaskLeaseExpiredEvent       -> k1.backpool.task.leased.v1 (sub-type)
    TaskLeaseRenewedEvent       -> k1.backpool.task.leased.v1 (sub-type)
    TaskDeferredEvent           -> (internal, ledger only)
    DependencyFailedEvent       -> (internal, ledger only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.concierge.events.base import CanonicalEventMeta

# =====================================================================
# BackPool worker lifecycle
# =====================================================================


@dataclass
class BackPoolWorkerAcquiredEvent(CanonicalEventMeta):
    """Worker slot assigned to a task from the BackPool.

    Attributes:
        worker_id:       UUID of the acquired worker slot.
        pool_size:       Total pool capacity.
        active_workers:  Count AFTER acquisition.
        session_id:      Session that owns the task (if any).
    """

    event_type: str = field(default="pool.worker.acquired", init=False)
    worker_id: str = ""
    pool_size: int = 3
    active_workers: int = 0
    session_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["worker_id"] = self.worker_id
        d["pool_size"] = self.pool_size
        d["active_workers"] = self.active_workers
        d["session_id"] = self.session_id
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> BackPoolWorkerAcquiredEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            worker_id=data.get("worker_id", ""),
            pool_size=data.get("pool_size", 3),
            active_workers=data.get("active_workers", 0),
        )


@dataclass
class BackPoolWorkerReleasedEvent(CanonicalEventMeta):
    """Worker slot returned to the BackPool.

    Attributes:
        worker_id:        UUID of the released worker slot.
        pool_size:        Total pool capacity.
        active_workers:   Count AFTER release.
        release_reason:   Why the worker was released.
    """

    event_type: str = field(default="pool.worker.released", init=False)
    worker_id: str = ""
    pool_size: int = 3
    active_workers: int = 0
    release_reason: str = "completed"

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["worker_id"] = self.worker_id
        d["pool_size"] = self.pool_size
        d["active_workers"] = self.active_workers
        d["release_reason"] = self.release_reason
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> BackPoolWorkerReleasedEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            worker_id=data.get("worker_id", ""),
            pool_size=data.get("pool_size", 3),
            active_workers=data.get("active_workers", 0),
            release_reason=data.get("release_reason", "completed"),
        )


# =====================================================================
# TaskLease lifecycle
# =====================================================================


@dataclass
class TaskLeasedEvent(CanonicalEventMeta):
    """Lease created for task/worker ownership binding.

    Attributes:
        worker_id:       UUID of the Back worker.
        lease_id:        UUID of the lease.
        lease_ttl_s:     Lease TTL in seconds.
        expires_at_ns:   Absolute expiry timestamp (monotonic ns).
        pool_size:       Pool capacity at lease time.
        active_workers:  Pool utilization at lease time.
    """

    event_type: str = field(default="pool.task.leased", init=False)
    worker_id: str = ""
    lease_id: str = ""
    lease_ttl_s: int = 300
    expires_at_ns: int = 0
    pool_size: int = 3
    active_workers: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["worker_id"] = self.worker_id
        d["lease_id"] = self.lease_id
        d["lease_ttl_s"] = self.lease_ttl_s
        d["expires_at_ns"] = self.expires_at_ns
        d["pool_size"] = self.pool_size
        d["active_workers"] = self.active_workers
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskLeasedEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            worker_id=data.get("worker_id", ""),
            lease_id=data.get("lease_id", ""),
            lease_ttl_s=data.get("lease_ttl_s", 300),
            expires_at_ns=data.get("expires_at_ns", 0),
            pool_size=data.get("pool_size", 3),
            active_workers=data.get("active_workers", 0),
        )


@dataclass
class TaskLeaseExpiredEvent(CanonicalEventMeta):
    """Lease TTL expired -- task auto-cancelled.

    Attributes:
        worker_id:       UUID of the worker whose lease expired.
        lease_id:        UUID of the expired lease.
        elapsed_s:       Actual elapsed seconds since lease creation.
        renewals_used:   Number of renewals consumed before expiry.
        hard_killed:     True if cooperative cancel timed out.
    """

    event_type: str = field(default="pool.task.lease_expired", init=False)
    worker_id: str = ""
    lease_id: str = ""
    elapsed_s: float = 0.0
    renewals_used: int = 0
    hard_killed: bool = False

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["worker_id"] = self.worker_id
        d["lease_id"] = self.lease_id
        d["elapsed_s"] = self.elapsed_s
        d["renewals_used"] = self.renewals_used
        d["hard_killed"] = self.hard_killed
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskLeaseExpiredEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            worker_id=data.get("worker_id", ""),
            lease_id=data.get("lease_id", ""),
            elapsed_s=data.get("elapsed_s", 0.0),
            renewals_used=data.get("renewals_used", 0),
            hard_killed=data.get("hard_killed", False),
        )


@dataclass
class TaskLeaseRenewedEvent(CanonicalEventMeta):
    """Lease TTL extended for a long-running task.

    Attributes:
        worker_id:           UUID of the worker.
        lease_id:            UUID of the lease.
        renewal_count:       Which renewal this is (1, 2, or 3).
        new_expires_at_ns:   New absolute expiry (monotonic ns).
        extension_s:         Seconds added to the TTL.
    """

    event_type: str = field(default="pool.task.lease_renewed", init=False)
    worker_id: str = ""
    lease_id: str = ""
    renewal_count: int = 0
    new_expires_at_ns: int = 0
    extension_s: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["worker_id"] = self.worker_id
        d["lease_id"] = self.lease_id
        d["renewal_count"] = self.renewal_count
        d["new_expires_at_ns"] = self.new_expires_at_ns
        d["extension_s"] = self.extension_s
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskLeaseRenewedEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            worker_id=data.get("worker_id", ""),
            lease_id=data.get("lease_id", ""),
            renewal_count=data.get("renewal_count", 0),
            new_expires_at_ns=data.get("new_expires_at_ns", 0),
            extension_s=data.get("extension_s", 0),
        )


# =====================================================================
# Dependency ordering events (M7 E7.5.4)
# =====================================================================


@dataclass
class TaskDeferredEvent(CanonicalEventMeta):
    """Task held in ReadyQueue waiting for predecessor to complete.

    Attributes:
        depends_on:   Task ID of the predecessor.
        queue_depth:  ReadyQueue depth at time of deferral.
    """

    event_type: str = field(default="pool.task.deferred", init=False)
    depends_on: str = ""
    queue_depth: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["depends_on"] = self.depends_on
        d["queue_depth"] = self.queue_depth
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskDeferredEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            depends_on=data.get("depends_on", ""),
            queue_depth=data.get("queue_depth", 0),
        )


@dataclass
class DependencyFailedEvent(CanonicalEventMeta):
    """Task failed due to dependency issue (unknown, circular, or predecessor failed).

    Attributes:
        depends_on: Task ID of the problematic dependency.
        reason:     Why the dependency failed.
    """

    event_type: str = field(default="pool.task.dependency_failed", init=False)
    depends_on: str = ""
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["depends_on"] = self.depends_on
        d["reason"] = self.reason
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> DependencyFailedEvent:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            depends_on=data.get("depends_on", ""),
            reason=data.get("reason", ""),
        )


__all__ = [
    "BackPoolWorkerAcquiredEvent",
    "BackPoolWorkerReleasedEvent",
    "TaskLeasedEvent",
    "TaskLeaseExpiredEvent",
    "TaskLeaseRenewedEvent",
    "TaskDeferredEvent",
    "DependencyFailedEvent",
]
