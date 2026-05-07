"""BridgeStorageAdapter -- K0 cloud storage via Bridge [E-0.5.11 stub].

Replaces ``SQLiteStorageAdapter`` when K0 cloud persistence is available.
Routes archive/restore operations through Bridge transport layer to K0.

Blocked by: Bridge runtime integration (MS-2+).
Current stand-in: ``SQLiteStorageAdapter`` (LOCAL COLD, always available).
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..ports.storage import ArchiveEntry, ArchiveResult, IStoragePort, RestoreResult

_BLOCKED = "BridgeStorageAdapter blocked by Bridge integration — target: MS-2+"


class BridgeStorageAdapter(IStoragePort):
    """Stub IStoragePort for K0 cloud storage via Bridge.

    All methods raise ``NotImplementedError`` until the Bridge runtime
    transport layer is available.
    """

    __slots__ = ()

    @property
    def is_available(self) -> bool:  # noqa: D102
        return False

    @property
    def storage_type(self) -> str:  # noqa: D102
        return "k0"

    def archive(
        self,
        section: str,
        data: bytes,
        metadata: Dict[str, Any],
    ) -> ArchiveResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def restore(
        self,
        section: str,
        filters: Dict[str, Any],
    ) -> RestoreResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def list_archives(self, session_id: str) -> List[ArchiveEntry]:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def delete(self, archive_id: str) -> bool:  # noqa: D102
        raise NotImplementedError(_BLOCKED)
