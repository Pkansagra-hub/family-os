"""Simple soft-delete (tombstone) management.

For UNDO capability, not GDPR compliance.
When a user deletes something, we soft-delete first so they can undo.
After 7 days, permanently delete.

NOT for:
- GDPR right to erasure (irrelevant - this is YOUR device)
- Legal compliance (no legal hold on personal device)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


# How long tombstones are kept before permanent deletion
TOMBSTONE_RETENTION_DAYS = 7


class TombstoneState(str, Enum):
    """States for tombstoned items."""

    ACTIVE = "ACTIVE"  # Normal, not deleted
    TOMBSTONED = "TOMBSTONED"  # Soft-deleted, can undo
    DELETED = "DELETED"  # Permanently deleted


@dataclass
class TombstoneInfo:
    """Information about a tombstoned item."""

    entity_id: str
    tombstoned_at_ms: int
    reason: str
    can_restore_until_ms: int

    @property
    def days_until_permanent(self) -> int:
        """Days until permanent deletion."""
        now_ms = int(time.time() * 1000)
        remaining_ms = self.can_restore_until_ms - now_ms
        return max(0, remaining_ms // (24 * 60 * 60 * 1000))


async def soft_delete(
    conn: "Connection",
    table: str,
    entity_id: str,
    id_column: str = "entity_id",
    reason: str = "user_deleted",
) -> bool:
    """Soft-delete an entity (set tombstone timestamp).

    Args:
        conn: Database connection
        table: Table name
        entity_id: Entity to soft-delete
        id_column: Column name for entity ID
        reason: Reason for deletion

    Returns:
        True if entity was tombstoned, False if not found
    """
    now_ms = int(time.time() * 1000)

    result = await conn.execute(
        f"""
        UPDATE {table}
        SET tombstone_at = $1,
            tombstone_reason = $2
        WHERE {id_column} = $3
        AND tombstone_at IS NULL
        """,
        now_ms,
        reason,
        entity_id,
    )

    affected = int(result.split()[-1]) if result else 0

    if affected > 0:
        logger.info(
            "Entity soft-deleted",
            extra={
                "table": table,
                "entity_id": entity_id,
                "reason": reason,
            },
        )
        return True
    return False


async def restore(
    conn: "Connection",
    table: str,
    entity_id: str,
    id_column: str = "entity_id",
) -> bool:
    """Restore a soft-deleted entity (undo delete).

    Args:
        conn: Database connection
        table: Table name
        entity_id: Entity to restore
        id_column: Column name for entity ID

    Returns:
        True if restored, False if not found or already restored
    """
    result = await conn.execute(
        f"""
        UPDATE {table}
        SET tombstone_at = NULL,
            tombstone_reason = NULL
        WHERE {id_column} = $1
        AND tombstone_at IS NOT NULL
        """,
        entity_id,
    )

    affected = int(result.split()[-1]) if result else 0

    if affected > 0:
        logger.info(
            "Entity restored from tombstone",
            extra={"table": table, "entity_id": entity_id},
        )
        return True
    return False


async def cleanup_expired_tombstones(
    conn: "Connection",
    table: str,
) -> int:
    """Permanently delete tombstones older than retention period.

    Args:
        conn: Database connection
        table: Table name

    Returns:
        Number of items permanently deleted
    """
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - (TOMBSTONE_RETENTION_DAYS * 24 * 60 * 60 * 1000)

    result = await conn.execute(
        f"""
        DELETE FROM {table}
        WHERE tombstone_at IS NOT NULL
        AND tombstone_at < $1
        """,
        cutoff_ms,
    )

    deleted = int(result.split()[-1]) if result else 0

    if deleted > 0:
        logger.info(
            "Expired tombstones permanently deleted",
            extra={"table": table, "count": deleted},
        )

    return deleted


async def get_tombstoned_items(
    conn: "Connection",
    table: str,
    id_column: str = "entity_id",
) -> list[TombstoneInfo]:
    """Get all tombstoned items that can still be restored.

    Args:
        conn: Database connection
        table: Table name
        id_column: Column name for entity ID

    Returns:
        List of tombstone info for restorable items
    """
    rows = await conn.fetch(
        f"""
        SELECT {id_column} as entity_id, tombstone_at, tombstone_reason
        FROM {table}
        WHERE tombstone_at IS NOT NULL
        ORDER BY tombstone_at DESC
        """,
    )

    retention_ms = TOMBSTONE_RETENTION_DAYS * 24 * 60 * 60 * 1000

    return [
        TombstoneInfo(
            entity_id=row["entity_id"],
            tombstoned_at_ms=row["tombstone_at"],
            reason=row["tombstone_reason"] or "unknown",
            can_restore_until_ms=row["tombstone_at"] + retention_ms,
        )
        for row in rows
    ]


def can_restore(tombstoned_at_ms: int) -> bool:
    """Check if a tombstoned item can still be restored.

    Args:
        tombstoned_at_ms: When item was tombstoned

    Returns:
        True if within restoration window
    """
    now_ms = int(time.time() * 1000)
    retention_ms = TOMBSTONE_RETENTION_DAYS * 24 * 60 * 60 * 1000
    return (now_ms - tombstoned_at_ms) < retention_ms
