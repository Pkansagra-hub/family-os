"""Local filesystem-backed blob driver placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry


class LocalBlobDriver:
    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path("/data/blobs")

    def store(self, payload: bytes, fingerprint: str) -> Path:
        raise NotImplementedError("Blob store not yet implemented")

    def apply(self, entry: OutboxEntry) -> None:
        """Apply outbox entry (Driver SPI requirement).

        Placeholder for blob storage operations.
        Currently no-op to avoid crashing outbox worker.

        Args:
            entry: Outbox entry with wal_pos, tenant_id, space_id, payload
        """
        # TODO: Implement blob storage when ready
        pass


# Factory function for outbox worker compatibility
def build_driver() -> LocalBlobDriver:
    """Factory function to create LocalBlobDriver instance.

    Returns:
        LocalBlobDriver: Configured driver instance
    """
    return LocalBlobDriver()
