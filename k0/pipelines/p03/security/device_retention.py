"""Device storage retention policy for P03.

Manages storage on device by enforcing band-based retention policies.
This is about STORAGE MANAGEMENT, not compliance (GDPR is irrelevant
for data stored on YOUR OWN device).

Retention Goals:
- Keep device storage under control
- Prioritize frequently accessed data
- Clean up stale data based on privacy band
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


# Retention periods in days (device-focused, not compliance-focused)
RETENTION_DAYS: dict[str, int] = {
    "GREEN": 365,  # Keep for a year (frequently accessed)
    "AMBER": 180,  # 6 months
    "RED": 90,  # 3 months (private, less likely to need)
    "ARCHIVED": 30,  # Archived data: 30 days before permanent delete
    "TOMBSTONE": 7,  # Tombstones: 7 days for undo capability
}


class RetentionAction(str, Enum):
    """Actions taken by retention enforcement."""

    KEEP = "KEEP"
    ARCHIVE = "ARCHIVE"
    DELETE = "DELETE"


@dataclass
class RetentionDecision:
    """Result of retention policy evaluation."""

    action: RetentionAction
    reason: str
    days_until_action: int | None = None


class DeviceRetentionPolicy:
    """Device storage retention policy.

    Focuses on storage management, not compliance:
    - Archive rarely accessed data to save space
    - Delete old tombstones/archives
    - Keep frequently accessed data longer
    """

    @classmethod
    def get_retention_days(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
        *,
        is_archived: bool = False,
        is_tombstone: bool = False,
    ) -> int:
        """Get retention period in days.

        Args:
            band: Privacy band of the data
            is_archived: Whether data is archived
            is_tombstone: Whether data is tombstoned

        Returns:
            Retention period in days
        """
        if is_tombstone:
            return RETENTION_DAYS["TOMBSTONE"]
        if is_archived:
            return RETENTION_DAYS["ARCHIVED"]
        return RETENTION_DAYS.get(band, RETENTION_DAYS["GREEN"])

    @classmethod
    def evaluate_retention(
        cls,
        created_at_ms: int,
        last_accessed_at_ms: int | None,
        band: Literal["GREEN", "AMBER", "RED"],
        *,
        is_archived: bool = False,
        is_tombstone: bool = False,
    ) -> RetentionDecision:
        """Evaluate retention policy for an item.

        Args:
            created_at_ms: Creation timestamp (milliseconds)
            last_accessed_at_ms: Last access timestamp (milliseconds), or None
            band: Privacy band
            is_archived: Whether item is archived
            is_tombstone: Whether item is tombstoned

        Returns:
            RetentionDecision with action to take
        """
        now_ms = int(time.time() * 1000)
        retention_days = cls.get_retention_days(
            band, is_archived=is_archived, is_tombstone=is_tombstone
        )
        retention_ms = retention_days * 24 * 60 * 60 * 1000

        # Use last_accessed if available, else created_at
        reference_time = last_accessed_at_ms or created_at_ms
        age_ms = now_ms - reference_time

        if age_ms >= retention_ms:
            return RetentionDecision(
                action=RetentionAction.DELETE,
                reason=f"Exceeded {retention_days} day retention",
            )

        days_until = (retention_ms - age_ms) // (24 * 60 * 60 * 1000)
        return RetentionDecision(
            action=RetentionAction.KEEP,
            reason="Within retention period",
            days_until_action=days_until,
        )

    @classmethod
    async def cleanup_expired_data(
        cls,
        conn: "Connection",
        *,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """Run retention cleanup on device storage.

        Args:
            conn: Database connection
            dry_run: If True, only report what would be deleted

        Returns:
            Dict with counts of items affected per table
        """
        now_ms = int(time.time() * 1000)
        results: dict[str, int] = {}

        # Cleanup tombstones older than 7 days
        tombstone_cutoff = now_ms - (RETENTION_DAYS["TOMBSTONE"] * 24 * 60 * 60 * 1000)

        if dry_run:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM st_pruned_entities
                WHERE tombstone_at IS NOT NULL
                AND tombstone_at < $1
                """,
                tombstone_cutoff,
            )
        else:
            result = await conn.execute(
                """
                DELETE FROM st_pruned_entities
                WHERE tombstone_at IS NOT NULL
                AND tombstone_at < $1
                """,
                tombstone_cutoff,
            )
            count = int(result.split()[-1]) if result else 0

        results["tombstones_deleted"] = count or 0

        # Cleanup old decay feedback (365 days max)
        feedback_cutoff = now_ms - (365 * 24 * 60 * 60 * 1000)

        if dry_run:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM st_decay_feedback
                WHERE created_at < $1
                """,
                feedback_cutoff,
            )
        else:
            result = await conn.execute(
                """
                DELETE FROM st_decay_feedback
                WHERE created_at < $1
                """,
                feedback_cutoff,
            )
            count = int(result.split()[-1]) if result else 0

        results["feedback_deleted"] = count or 0

        logger.info(
            "Retention cleanup completed",
            extra={"dry_run": dry_run, "results": results},
        )

        return results


async def run_retention_cleanup(
    conn: "Connection",
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Convenience function to run retention cleanup.

    Args:
        conn: Database connection
        dry_run: If True, only report what would be deleted

    Returns:
        Cleanup results
    """
    return await DeviceRetentionPolicy.cleanup_expired_data(conn, dry_run=dry_run)
