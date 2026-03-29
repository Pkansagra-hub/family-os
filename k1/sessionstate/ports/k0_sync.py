"""
IK0SyncPort - Optional K0 Cloud Sync Interface
================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.1 Define Storage Port
ISSUE: 3.1.4

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Optional async sync to K0 cloud storage.
    This is an ENHANCEMENT, not a requirement.
    SessionState MUST work fully offline with LOCAL COLD.

EDGE-FIRST DESIGN:
    - K0 sync is OPTIONAL (may be unavailable)
    - Never block on K0 operations
    - Graceful degradation if K0 unreachable
    - Queue sync requests for later if offline

IMPLEMENTATIONS:
    - BridgeSyncAdapter: K0 sync via Bridge (future)
    - NullSyncAdapter: No-op (standalone mode)

==============================================================================
INTERFACE: IK0SyncPort
==============================================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class SyncStatus(str, Enum):
    """Status of a sync operation."""

    PENDING = "pending"  # Queued for sync
    SYNCING = "syncing"  # Sync in progress
    SYNCED = "synced"  # Successfully synced
    FAILED = "failed"  # Sync failed (will retry)
    OFFLINE = "offline"  # K0 unavailable


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    status: SyncStatus
    session_id: str
    sections_synced: List[str]
    bytes_synced: int
    duration_ms: float
    error: Optional[str] = None


@dataclass
class RestoreFromK0Result:
    """Result of restoring from K0."""

    success: bool
    session_id: str
    sections_restored: List[str]
    bytes_restored: int
    duration_ms: float
    error: Optional[str] = None


class IK0SyncPort(ABC):
    """
    Interface for optional K0 cloud sync.

    SessionState may use this port to:
    - Sync data to K0 for cross-device access
    - Restore from K0 when LOCAL COLD doesn't have data

    Properties:
        is_available: Whether K0 is currently reachable

    CRITICAL DESIGN PRINCIPLE:
        This is OPTIONAL. SessionState MUST work without K0.
        All operations are best-effort, non-blocking.

    Example:
        class BridgeSyncAdapter(IK0SyncPort):
            @property
            def is_available(self) -> bool:
                return self._bridge.is_connected()

            async def sync_to_k0(self, session_id: str) -> SyncResult:
                if not self.is_available:
                    return SyncResult(success=False, status=SyncStatus.OFFLINE, ...)
                # Queue for async sync
                ...
    """

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if K0 is currently reachable.

        Returns:
            bool: True if K0 sync is possible

        Notes:
            - Check network connectivity
            - Check Bridge health
            - May return False if offline
        """
        pass

    @abstractmethod
    def sync_to_k0(self, session_id: str) -> SyncResult:
        """
        Queue session data for sync to K0.

        Args:
            session_id: Session to sync

        Returns:
            SyncResult: Immediate status (may be PENDING)

        Behavior:
            - Non-blocking (queues for async sync)
            - Best-effort (may fail silently)
            - Retries automatically on transient failures

        Use cases:
            - After checkpoint, queue K0 sync
            - Periodic background sync
            - User-triggered "sync now"
        """
        pass

    @abstractmethod
    def restore_from_k0(self, session_id: str) -> RestoreFromK0Result:
        """
        Restore session from K0 cloud.

        Args:
            session_id: Session to restore

        Returns:
            RestoreFromK0Result: Data if available

        Behavior:
            - Blocking (waits for response)
            - Timeout after ~100ms
            - Returns failure if offline or not found

        Use case:
            Called by ReconstructionSLA when LOCAL COLD doesn't have session.
            This is a FALLBACK, not the primary source.
        """
        pass

    @abstractmethod
    def get_sync_status(self, session_id: str) -> SyncStatus:
        """
        Get current sync status for a session.

        Args:
            session_id: Session to check

        Returns:
            SyncStatus: Current sync state
        """
        pass

    @abstractmethod
    def cancel_sync(self, session_id: str) -> bool:
        """
        Cancel pending sync for a session.

        Args:
            session_id: Session to cancel

        Returns:
            bool: True if cancelled, False if no pending sync
        """
        pass


class NullSyncPort(IK0SyncPort):
    """
    No-op implementation for standalone mode.

    Use when K0 sync is not needed (development, testing, offline-only).
    """

    @property
    def is_available(self) -> bool:
        """K0 never available in standalone mode."""
        return False

    def sync_to_k0(self, session_id: str) -> SyncResult:
        """No-op sync."""
        return SyncResult(
            success=False,
            status=SyncStatus.OFFLINE,
            session_id=session_id,
            sections_synced=[],
            bytes_synced=0,
            duration_ms=0,
            error="K0 sync not configured",
        )

    def restore_from_k0(self, session_id: str) -> RestoreFromK0Result:
        """No-op restore."""
        return RestoreFromK0Result(
            success=False,
            session_id=session_id,
            sections_restored=[],
            bytes_restored=0,
            duration_ms=0,
            error="K0 sync not configured",
        )

    def get_sync_status(self, session_id: str) -> SyncStatus:
        """Always offline."""
        return SyncStatus.OFFLINE

    def cancel_sync(self, session_id: str) -> bool:
        """Nothing to cancel."""
        return False


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. OPTIONAL BY DESIGN:
   This entire port is optional.
   SessionState.create_standalone() uses NullSyncPort.
   Only production with Bridge uses real implementation.

2. NON-BLOCKING:
   sync_to_k0() should queue and return immediately.
   Use background thread/task for actual sync.
   Never block SessionState operations on K0.

3. GRACEFUL DEGRADATION:
   - K0 unavailable? Log and continue.
   - Sync failed? Retry later.
   - Restore failed? Use LOCAL COLD.

4. SYNC QUEUEING:
   Maintain internal queue of pending syncs.
   Process queue when K0 becomes available.
   Deduplicate (only sync latest state).

5. IMPLEMENTATIONS TO CREATE:
   - NullSyncPort (included above)
   - BridgeSyncAdapter (bridge/adapters/k0_sync.py) - FUTURE

6. TESTING:
   Test with NullSyncPort (verify no side effects).
   Test fallback behavior in ReconstructionSLA.
"""
