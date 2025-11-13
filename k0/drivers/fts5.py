"""FTS5 shadow index driver placeholder."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry


class FTS5Driver:
    def configure(self) -> None:
        raise NotImplementedError("FTS5 driver configuration not yet implemented")

    def apply(self, entry: OutboxEntry) -> None:
        """Apply outbox entry (Driver SPI requirement).

        Placeholder for FTS5 full-text search index updates.
        Currently no-op to avoid crashing outbox worker.

        Args:
            entry: Outbox entry with wal_pos, tenant_id, space_id, payload
        """
        # TODO: Implement FTS5 index updates when ready
        pass


# Factory function for outbox worker compatibility
def build_driver() -> FTS5Driver:
    """Factory function to create FTS5Driver instance.

    Returns:
        FTS5Driver: Configured driver instance
    """
    return FTS5Driver()
