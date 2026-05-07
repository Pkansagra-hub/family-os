"""
k1.concierge.protocols.task_lease -- Task Lease Model (M7 E7.2).

Provides temporal ownership and expiry for Back worker tasks.
Each TaskLease binds a task_id to a worker_id with a monotonic
expiry timestamp and a cooperative CancellationToken.

Key design:
  - Lease is created at acquire_worker() time (E7.2.2).
  - The CancellationToken is passed to the Back react_loop.
  - When the lease expires, the token is cancelled (cooperative).
  - If the react_loop does not exit within grace period, the
    asyncio.Task is hard-cancelled (E7.2.3).
  - Lease renewal extends expires_at_ns up to max_renewals (E7.2.5).

V3 Milestone 7 E7.2.1-7.2.5
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from k1.concierge.protocols.cancellation import CancellationToken

logger = logging.getLogger(__name__)


# =====================================================================
# E7.2.1 -- LeaseStatus enum
# =====================================================================


class LeaseStatus(str, Enum):
    """Status of a task lease.

    ACTIVE:    Lease is valid and the worker is running.
    SUSPENDED: Worker released during HITL wait; lease preserved, TTL paused.
    EXPIRED:   Lease TTL elapsed without renewal or release.
    RELEASED:  Worker completed normally and lease was released.
    CANCELLED: Lease was cancelled (user cancel, arbiter supersede, etc.).
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    RELEASED = "released"
    CANCELLED = "cancelled"


# =====================================================================
# E7.2.1 -- TaskLease dataclass
# =====================================================================


@dataclass
class TaskLease:
    """Temporal ownership record for a Back worker task.

    M7 E7.2.1: Binds a task to a worker with monotonic expiry
    and a cooperative CancellationToken. The lease is the single
    authority for whether a worker has permission to continue.

    Attributes:
        task_id:              The task this lease governs.
        worker_id:            The worker that owns this task.
        lease_id:             Unique identifier for this lease (uuid4).
        granted_at_ns:        Monotonic timestamp when lease was granted.
        expires_at_ns:        Monotonic timestamp when lease expires.
        cancellation_token:   Cooperative cancellation token for the task.
        renewed_count:        Number of times the lease has been renewed.
        max_renewals:         Maximum allowed renewals (configurable).
        status:               Current lease status.
    """

    task_id: str
    worker_id: str
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    granted_at_ns: int = field(default_factory=time.monotonic_ns)
    expires_at_ns: int = 0  # Set by factory; 0 = must be computed
    cancellation_token: CancellationToken | None = field(default=None, repr=False)
    renewed_count: int = 0
    max_renewals: int = 3
    status: LeaseStatus = LeaseStatus.ACTIVE

    def __post_init__(self) -> None:
        # Auto-create CancellationToken if not provided
        if self.cancellation_token is None:
            self.cancellation_token = CancellationToken(task_id=self.task_id)

    # -----------------------------------------------------------------
    # Expiry check
    # -----------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Whether the lease has exceeded its TTL.

        Uses monotonic_ns for clock-skew immunity.
        Suspended leases are NOT considered expired (TTL paused).
        """
        if self.status in (LeaseStatus.EXPIRED, LeaseStatus.RELEASED, LeaseStatus.CANCELLED):
            return True
        if self.status == LeaseStatus.SUSPENDED:
            return False  # TTL paused during HITL suspension
        return time.monotonic_ns() >= self.expires_at_ns

    @property
    def remaining_ns(self) -> int:
        """Nanoseconds remaining before expiry. 0 if expired."""
        if self.status not in (LeaseStatus.ACTIVE,):
            return 0
        remaining = self.expires_at_ns - time.monotonic_ns()
        return max(0, remaining)

    @property
    def remaining_s(self) -> float:
        """Seconds remaining before expiry. 0.0 if expired."""
        return self.remaining_ns / 1e9

    # -----------------------------------------------------------------
    # Lease renewal (E7.2.5)
    # -----------------------------------------------------------------

    def renew(self, extension_ns: int | None = None, extension_s: float = 60.0) -> bool:
        """Extend the lease expiry for long-running tasks.

        M7 E7.2.5: The Back react_loop calls this between iterations
        if it needs more time. Each renewal extends expires_at_ns.
        Returns False if max_renewals exceeded or lease not ACTIVE.

        Args:
            extension_ns: Extension in nanoseconds (takes priority).
            extension_s:  Extension in seconds (default 60s).

        Returns:
            True if renewal succeeded, False if denied.
        """
        if self.status != LeaseStatus.ACTIVE:
            logger.warning(
                "TaskLease.renew: cannot renew lease_id=%s " "status=%s (not ACTIVE)",
                self.lease_id,
                self.status.value,
            )
            return False

        if self.renewed_count >= self.max_renewals:
            logger.warning(
                "TaskLease.renew: max renewals (%d) exceeded for " "lease_id=%s task_id=%s",
                self.max_renewals,
                self.lease_id,
                self.task_id,
            )
            return False

        ext_ns = extension_ns if extension_ns is not None else int(extension_s * 1e9)
        old_expires = self.expires_at_ns
        self.expires_at_ns += ext_ns
        self.renewed_count += 1

        logger.info(
            "TaskLease.renew: lease_id=%s task_id=%s worker_id=%s "
            "renewed_count=%d/%d extension_s=%.1f new_remaining_s=%.1f",
            self.lease_id,
            self.task_id,
            self.worker_id,
            self.renewed_count,
            self.max_renewals,
            ext_ns / 1e9,
            (self.expires_at_ns - time.monotonic_ns()) / 1e9,
        )
        return True

    # -----------------------------------------------------------------
    # Status transitions
    # -----------------------------------------------------------------

    def release(self) -> None:
        """Mark the lease as RELEASED (normal completion)."""
        if self.status == LeaseStatus.ACTIVE:
            self.status = LeaseStatus.RELEASED
            logger.info(
                "TaskLease.release: lease_id=%s task_id=%s worker_id=%s",
                self.lease_id,
                self.task_id,
                self.worker_id,
            )

    def expire(self) -> None:
        """Mark the lease as EXPIRED (TTL exceeded)."""
        if self.status == LeaseStatus.ACTIVE:
            self.status = LeaseStatus.EXPIRED
            logger.info(
                "TaskLease.expire: lease_id=%s task_id=%s worker_id=%s",
                self.lease_id,
                self.task_id,
                self.worker_id,
            )

    def cancel(self) -> None:
        """Mark the lease as CANCELLED."""
        if self.status in (LeaseStatus.ACTIVE, LeaseStatus.SUSPENDED):
            self.status = LeaseStatus.CANCELLED
            # Cancel the cooperative token so react_loop sees it
            if self.cancellation_token is not None:
                self.cancellation_token.cancel()
            logger.info(
                "TaskLease.cancel: lease_id=%s task_id=%s worker_id=%s",
                self.lease_id,
                self.task_id,
                self.worker_id,
            )

    # -----------------------------------------------------------------
    # HITL suspension lifecycle (M7 E7.5.5)
    # -----------------------------------------------------------------

    def suspend(self) -> None:
        """Transition to SUSPENDED for HITL wait (TTL paused).

        M7 E7.5.5: Worker slot is released but the lease stays alive.
        The expiry watcher must skip SUSPENDED leases.
        """
        if self.status == LeaseStatus.ACTIVE:
            self._suspended_remaining_ns = self.remaining_ns
            self.status = LeaseStatus.SUSPENDED
            logger.info(
                "TaskLease.suspend: lease_id=%s task_id=%s " "remaining_s=%.1f (TTL paused)",
                self.lease_id,
                self.task_id,
                self._suspended_remaining_ns / 1e9,
            )

    def resume(self, new_worker_id: str | None = None) -> None:
        """Resume from SUSPENDED to ACTIVE (HITL resolved).

        M7 E7.5.5: Re-acquires a worker slot. Restores the remaining
        TTL from suspension time. Same CancellationToken is preserved.

        Args:
            new_worker_id: If provided, update the worker_id.
        """
        if self.status == LeaseStatus.SUSPENDED:
            remaining = getattr(self, "_suspended_remaining_ns", 0)
            self.expires_at_ns = time.monotonic_ns() + remaining
            if new_worker_id:
                self.worker_id = new_worker_id
            self.status = LeaseStatus.ACTIVE
            logger.info(
                "TaskLease.resume: lease_id=%s task_id=%s "
                "new_worker_id=%s remaining_s=%.1f (TTL resumed)",
                self.lease_id,
                self.task_id,
                self.worker_id,
                remaining / 1e9,
            )

    # -----------------------------------------------------------------
    # Serialization (E7.2.4)
    # -----------------------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        """Serialize lease to a dict for the task.leased.v1 event.

        M7 E7.2.4: Used by the bus builder to emit the leased event.

        Returns:
            Dict with task_id, worker_id, lease_id, granted_at_ns,
            expires_at_ns, status, renewed_count.
        """
        return {
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "granted_at_ns": self.granted_at_ns,
            "expires_at_ns": self.expires_at_ns,
            "lease_expires_at": self.expires_at_ns,
            "status": self.status.value,
            "renewed_count": self.renewed_count,
            "max_renewals": self.max_renewals,
            "remaining_s": round(self.remaining_s, 3),
        }

    def __repr__(self) -> str:
        return (
            f"TaskLease(task_id={self.task_id!r}, worker_id={self.worker_id!r}, "
            f"status={self.status.value}, renewed={self.renewed_count}/{self.max_renewals}, "
            f"remaining_s={self.remaining_s:.1f})"
        )


# =====================================================================
# Factory function
# =====================================================================


def create_task_lease(
    task_id: str,
    worker_id: str,
    lease_ttl_s: float = 300.0,
    max_renewals: int = 3,
    cancellation_token: CancellationToken | None = None,
) -> TaskLease:
    """Create a TaskLease with computed expires_at_ns.

    M7 E7.2.2: Called by BackPool.acquire_worker() at dispatch time.

    Args:
        task_id:              The task to lease.
        worker_id:            The worker that will own this task.
        lease_ttl_s:          Lease duration in seconds.
        max_renewals:         Maximum allowed renewals.
        cancellation_token:   Optional pre-created token (for testing).

    Returns:
        TaskLease with expires_at_ns = granted_at_ns + ttl.
    """
    granted_at_ns = time.monotonic_ns()
    expires_at_ns = granted_at_ns + int(lease_ttl_s * 1e9)
    token = cancellation_token or CancellationToken(task_id=task_id)

    lease = TaskLease(
        task_id=task_id,
        worker_id=worker_id,
        granted_at_ns=granted_at_ns,
        expires_at_ns=expires_at_ns,
        cancellation_token=token,
        max_renewals=max_renewals,
    )

    logger.info(
        "create_task_lease: task_id=%s worker_id=%s lease_id=%s " "ttl_s=%.1f max_renewals=%d",
        task_id,
        worker_id,
        lease.lease_id,
        lease_ttl_s,
        max_renewals,
    )
    return lease


__all__ = [
    "LeaseStatus",
    "TaskLease",
    "create_task_lease",
]
