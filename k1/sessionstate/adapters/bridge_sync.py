"""BridgeSyncAdapter -- Optional K0 cloud sync via Bridge [E-0.5.11 stub].

Replaces ``NullSyncPort`` when K0 cross-device sync is available.
Queues session data for async sync to K0 cloud storage.

Blocked by: Bridge + K0 connectivity (MS-2+, lowest priority).
Current stand-in: ``NullSyncPort`` (edge-first: K1 works fully offline).
"""

from __future__ import annotations

from ..ports.k0_sync import IK0SyncPort, RestoreFromK0Result, SyncResult, SyncStatus

_BLOCKED = "BridgeSyncAdapter blocked by Bridge + K0 integration — target: MS-2+"


class BridgeSyncAdapter(IK0SyncPort):
    """Stub IK0SyncPort for K0 cloud sync via Bridge.

    All methods raise ``NotImplementedError`` until Bridge transport
    and K0 connectivity are available.
    """

    __slots__ = ()

    @property
    def is_available(self) -> bool:  # noqa: D102
        return False

    def sync_to_k0(self, session_id: str) -> SyncResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def restore_from_k0(self, session_id: str) -> RestoreFromK0Result:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def get_sync_status(self, session_id: str) -> SyncStatus:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def cancel_sync(self, session_id: str) -> bool:  # noqa: D102
        raise NotImplementedError(_BLOCKED)
