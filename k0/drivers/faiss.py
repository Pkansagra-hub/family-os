"""FAISS vector driver placeholder."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry


class FaissDriver:
    def apply(self, entry: OutboxEntry) -> None:
        """Apply outbox entry (Driver SPI requirement).

        Placeholder for FAISS vector index updates.
        Currently no-op to avoid crashing outbox worker.

        Args:
            entry: Outbox entry with wal_pos, tenant_id, space_id, payload
        """
        # TODO: Implement FAISS vector operations when ready
        pass


# Factory function for outbox worker compatibility
def build_driver() -> FaissDriver:
    """Factory function to create FaissDriver instance.

    Returns:
        FaissDriver: Configured driver instance
    """
    return FaissDriver()
