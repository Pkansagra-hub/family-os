"""
LocalColdTier - LOCAL COLD Tier Manager
========================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.4 Implement Tier Managers
ISSUE: 2.4.3 (local_cold_tier)

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Manage LOCAL COLD tier (K1 SQLite).
    Offline-safe persistent archive.

EDGE-FIRST DESIGN:
    - Always available (no network)
    - K0 cloud sync is OPTIONAL enhancement
    - SessionState MUST work fully offline

ARCHIVE TYPES:
    - Evicted beliefs (from beliefs_history)
    - Evicted history (from history_recent)
    - Session checkpoints (full snapshots)
    - Evicted persona (rare)

STORAGE:
    Uses LocalColdArchive for actual persistence.
    This tier manager coordinates access.

SLA:
    <50ms for restore (P95)

OPERATIONS:
    - archive(section, data): Archive evicted data
    - restore(section, filters): Restore archived data
    - checkpoint(snapshot): Save full checkpoint
    - restore_checkpoint(): Restore from checkpoint
    - list_archives(): List available archives
    - prune_old(max_age_days): Remove old archives

==============================================================================
CLASS: LocalColdTier
==============================================================================
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..config import ColdConfig, SessionStateConfig

if TYPE_CHECKING:
    from ..local_cold import LocalColdArchive as LocalColdArchiveType

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Archive retention (config: sessionstate.cold.default_max_age_days)
DEFAULT_MAX_AGE_DAYS: int = 30

# SLA target (config: sessionstate.cold.restore_sla_ms)
RESTORE_SLA_MS: float = 50.0

# Sections that can be archived
ARCHIVABLE_SECTIONS: List[str] = [
    "beliefs_history",
    "history_recent",
    "persona",
    "telemetry",
    "artifacts_warm",  # W6: WARM eviction target
    "narrative_active",
    "checkpoint",
]


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class ArchiveInfo:
    """
    Archive metadata.

    Attributes:
        archive_id: Unique archive identifier
        section: Source section name
        session_id: Session this belongs to
        size_bytes: Size of archived data
        created_at_ms: Archive timestamp
        metadata: Additional metadata
    """

    archive_id: str
    section: str
    session_id: str
    size_bytes: int
    created_at_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "archive_id": self.archive_id,
            "section": self.section,
            "session_id": self.session_id,
            "size_bytes": self.size_bytes,
            "created_at_ms": self.created_at_ms,
            "metadata": self.metadata,
        }


@dataclass
class RestoreResult:
    """
    Result of restore operation.

    Attributes:
        success: Whether restore succeeded
        data: Restored data (bytes)
        archive_id: ID of restored archive
        size_bytes: Size of restored data
        duration_ms: Time taken
        sla_met: Whether SLA was met
        error: Error message if failed
    """

    success: bool
    data: Optional[bytes] = None
    archive_id: str = ""
    size_bytes: int = 0
    duration_ms: float = 0.0
    sla_met: bool = True
    error: str = ""

    @classmethod
    def failure(cls, error: str, duration_ms: float = 0.0) -> "RestoreResult":
        """Create a failure result."""
        return cls(
            success=False,
            error=error,
            duration_ms=duration_ms,
            sla_met=duration_ms <= ColdConfig().restore_sla_ms,
        )

    @classmethod
    def not_found(cls, section: str, session_id: str, duration_ms: float = 0.0) -> "RestoreResult":
        """Create a not-found result."""
        return cls(
            success=False,
            error=f"No archive found for {section} in session {session_id}",
            duration_ms=duration_ms,
            sla_met=duration_ms <= ColdConfig().restore_sla_ms,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "archive_id": self.archive_id,
            "size_bytes": self.size_bytes,
            "duration_ms": round(self.duration_ms, 3),
            "sla_met": self.sla_met,
            "error": self.error,
        }


@dataclass
class ArchiveResult:
    """
    Result of archive operation.

    Attributes:
        success: Whether archive succeeded
        archive_id: ID of created archive entry
        size_bytes: Size of archived data
        duration_ms: Time taken
        error: Error message if failed
    """

    success: bool
    archive_id: str = ""
    size_bytes: int = 0
    duration_ms: float = 0.0
    error: str = ""

    @classmethod
    def failure(cls, error: str, duration_ms: float = 0.0) -> "ArchiveResult":
        """Create a failure result."""
        return cls(success=False, error=error, duration_ms=duration_ms)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "archive_id": self.archive_id,
            "size_bytes": self.size_bytes,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
        }


@dataclass
class LocalColdSnapshot:
    """
    Snapshot of LOCAL COLD tier state.

    Attributes:
        session_id: Current session ID
        total_size_bytes: Total archived bytes for session
        archive_count: Number of archive entries
        checkpoint_count: Number of checkpoints
        section_counts: Archives per section
        is_available: Whether storage is available
        timestamp_ms: Snapshot timestamp
    """

    session_id: str
    total_size_bytes: int
    archive_count: int
    checkpoint_count: int
    section_counts: Dict[str, int]
    is_available: bool
    timestamp_ms: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "total_size_bytes": self.total_size_bytes,
            "archive_count": self.archive_count,
            "checkpoint_count": self.checkpoint_count,
            "section_counts": self.section_counts,
            "is_available": self.is_available,
            "timestamp_ms": self.timestamp_ms,
        }


# =============================================================================
# LOCALCOLDTIER CLASS
# =============================================================================


class LocalColdTier:
    """
    LOCAL COLD tier manager.

    Wraps LocalColdArchive with tier semantics for consistent API
    across the tier hierarchy (HotTier, WarmTier, LocalColdTier).

    Edge-First Design:
        - Always available (no network dependency)
        - K0 sync is optional enhancement
        - SessionState MUST work fully offline

    SLA:
        - <50ms for restore operations (P95)

    Attributes:
        _storage: LocalColdArchive implementation
        _session_id: Current session ID
        _restore_sla_violations: Count of SLA violations
        _total_restores: Total restore count

    Example:
        from poc.k1_poc.sessionstate.local_cold import LocalColdArchive

        storage = LocalColdArchive()
        tier = LocalColdTier(storage, session_id="abc-123")

        # Archive evicted data
        result = tier.archive("beliefs_history", serialized_beliefs, {"reason": "eviction"})

        # Restore for reconstruction
        result = tier.restore("beliefs_history")
        if result.success:
            # Deserialize result.data
            pass

        # Checkpointing
        checkpoint_id = tier.checkpoint(full_session_bytes)
        result = tier.restore_checkpoint()
    """

    __slots__ = (
        "_ss_cfg",
        "_storage",
        "_session_id",
        "_restore_sla_violations",
        "_total_restores",
        "_total_archives",
        "_bytes_archived",
        "_bytes_restored",
        "_created_at_ms",
    )

    def __init__(
        self,
        storage: Optional["LocalColdArchiveType"] = None,
        session_id: str = "",
        config: Optional[SessionStateConfig] = None,
    ) -> None:
        """
        Initialize LocalColdTier.

        Args:
            storage: LocalColdArchive instance (optional for testing)
            session_id: Current session ID
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        self._storage = storage
        self._session_id = session_id
        self._restore_sla_violations = 0
        self._total_restores = 0
        self._total_archives = 0
        self._bytes_archived = 0
        self._bytes_restored = 0
        self._created_at_ms = int(time.time() * 1000)

        logger.debug(
            "LocalColdTier initialized (session=%s, storage=%s)",
            session_id[:8] if session_id else "none",
            "attached" if storage else "none",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def tier_name(self) -> str:
        """Tier name."""
        return "local_cold"

    @property
    def session_id(self) -> str:
        """Current session ID."""
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        """Set session ID."""
        self._session_id = value

    @property
    def is_available(self) -> bool:
        """Check if storage is available."""
        if self._storage is None:
            return False
        # Check if storage is not closed
        return not getattr(self._storage, "is_closed", False)

    @property
    def restore_sla_ms(self) -> float:
        """SLA target for restore operations."""
        return RESTORE_SLA_MS

    @property
    def sla_compliance_rate(self) -> float:
        """Calculate SLA compliance rate (0.0-1.0)."""
        if self._total_restores == 0:
            return 1.0
        compliant = self._total_restores - self._restore_sla_violations
        return compliant / self._total_restores

    # =========================================================================
    # Archive Operations
    # =========================================================================

    def archive(
        self,
        section: str,
        data: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArchiveResult:
        """
        Archive evicted data.

        Args:
            section: Source section name (e.g., "beliefs_history", "history_recent")
            data: Serialized data (FlatBuffer bytes)
            metadata: Additional metadata (reason, turn_id, etc.)

        Returns:
            ArchiveResult: Success/failure with archive_id

        Example:
            result = tier.archive(
                section="beliefs_history",
                data=beliefs_bytes,
                metadata={"reason": "eviction", "priority": 2},
            )
            if result.success:
                print(f"Archived: {result.archive_id}")
        """
        start_time = time.perf_counter()

        if self._storage is None:
            return ArchiveResult.failure("No storage attached")

        if not self._session_id:
            return ArchiveResult.failure("No session_id set")

        # Delegate to LocalColdArchive
        result = self._storage.archive(
            section=section,
            data=data,
            session_id=self._session_id,
            metadata=metadata,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        if result.success:
            self._total_archives += 1
            self._bytes_archived += result.size_bytes

        return ArchiveResult(
            success=result.success,
            archive_id=result.archive_id,
            size_bytes=result.size_bytes,
            duration_ms=duration_ms,
            error=result.error or "",
        )

    def can_archive(self, section: str) -> bool:
        """
        Check if a section can be archived.

        Args:
            section: Section name

        Returns:
            bool: True if section is archivable
        """
        return section in ARCHIVABLE_SECTIONS or section.startswith(
            ("beliefs", "history", "narrative")
        )

    # =========================================================================
    # Restore Operations
    # =========================================================================

    def restore(
        self,
        section: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> RestoreResult:
        """
        Restore archived data.

        Args:
            section: Section to restore
            filters: Query filters (archive_id, after_ms, before_ms)

        Returns:
            RestoreResult: Restored data or error

        SLA: <50ms

        Example:
            result = tier.restore("beliefs_history")
            if result.success:
                section.from_flatbuffer(result.data)
        """
        start_time = time.perf_counter()
        self._total_restores += 1

        if self._storage is None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return RestoreResult.failure("No storage attached", duration_ms)

        if not self._session_id:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return RestoreResult.failure("No session_id set", duration_ms)

        # Delegate to LocalColdArchive
        result = self._storage.restore(
            section=section,
            session_id=self._session_id,
            filters=filters,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        _cold_sla = self._ss_cfg.cold.restore_sla_ms
        sla_met = duration_ms <= _cold_sla

        if not sla_met:
            self._restore_sla_violations += 1
            logger.warning(
                "Restore SLA breach: %s for session %s took %.2fms (>%.0fms)",
                section,
                self._session_id[:8] if self._session_id else "none",
                duration_ms,
                _cold_sla,
            )

        if result.success:
            self._bytes_restored += result.size_bytes
            return RestoreResult(
                success=True,
                data=result.data,
                archive_id=result.archive_id,
                size_bytes=result.size_bytes,
                duration_ms=duration_ms,
                sla_met=sla_met,
            )
        else:
            return RestoreResult(
                success=False,
                error=result.error or "Unknown error",
                duration_ms=duration_ms,
                sla_met=sla_met,
            )

    def restore_all(
        self,
        section: str,
        limit: int = 100,
    ) -> List[RestoreResult]:
        """
        Restore all archives for a section.

        Args:
            section: Section to restore
            limit: Maximum entries to return

        Returns:
            List[RestoreResult]: All matching archives (newest first)
        """
        if self._storage is None:
            return []

        if not self._session_id:
            return []

        # Delegate to LocalColdArchive
        results = self._storage.restore_all(
            section=section,
            session_id=self._session_id,
            limit=limit,
        )

        # Convert to our RestoreResult type
        return [
            RestoreResult(
                success=r.success,
                data=r.data,
                archive_id=r.archive_id,
                size_bytes=r.size_bytes,
                duration_ms=r.duration_ms,
                sla_met=r.duration_ms <= RESTORE_SLA_MS,
                error=r.error or "",
            )
            for r in results
        ]

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    def checkpoint(
        self,
        snapshot_data: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArchiveResult:
        """
        Save full session checkpoint.

        Args:
            snapshot_data: Serialized full snapshot
            metadata: Checkpoint metadata

        Returns:
            ArchiveResult: Success with checkpoint_id

        Example:
            result = tier.checkpoint(session_bytes, {"trigger": "periodic"})
            if result.success:
                print(f"Checkpoint: {result.archive_id}")
        """
        return self.archive("checkpoint", snapshot_data, metadata)

    def restore_checkpoint(
        self,
        checkpoint_id: Optional[str] = None,
    ) -> RestoreResult:
        """
        Restore from checkpoint.

        Args:
            checkpoint_id: Specific checkpoint (None = latest)

        Returns:
            RestoreResult: Checkpoint data or error
        """
        filters = {}
        if checkpoint_id:
            filters["archive_id"] = checkpoint_id

        return self.restore("checkpoint", filters)

    def list_checkpoints(self) -> List[ArchiveInfo]:
        """
        List available checkpoints.

        Returns:
            List[ArchiveInfo]: Checkpoint metadata (newest first)
        """
        return self.list_archives(section="checkpoint")

    def prune_checkpoints(self, keep_count: int = 5) -> int:
        """
        Remove old checkpoints, keeping most recent.

        Args:
            keep_count: Number of checkpoints to keep

        Returns:
            int: Number of checkpoints deleted
        """
        if self._storage is None:
            return 0

        if not self._session_id:
            return 0

        return self._storage.prune_checkpoints(
            session_id=self._session_id,
            keep_count=keep_count,
        )

    # =========================================================================
    # List Operations
    # =========================================================================

    def list_archives(
        self,
        section: Optional[str] = None,
    ) -> List[ArchiveInfo]:
        """
        List available archives.

        Args:
            section: Filter by section (or all)

        Returns:
            List[ArchiveInfo]: Archive metadata (newest first)
        """
        if self._storage is None:
            return []

        if not self._session_id:
            return []

        entries = self._storage.list_archives(
            session_id=self._session_id,
            section=section,
        )

        return [
            ArchiveInfo(
                archive_id=e.archive_id,
                section=e.section,
                session_id=e.session_id,
                size_bytes=e.size_bytes,
                created_at_ms=e.created_at_ms,
                metadata=e.metadata,
            )
            for e in entries
        ]

    def has_archives(self) -> bool:
        """
        Check if session has any archives.

        Returns:
            bool: True if any archives exist
        """
        if self._storage is None:
            return False

        if not self._session_id:
            return False

        return self._storage.has_session(self._session_id)

    # =========================================================================
    # Delete Operations
    # =========================================================================

    def delete_archive(self, archive_id: str) -> bool:
        """
        Delete an archive.

        Args:
            archive_id: Archive to delete

        Returns:
            bool: True if deleted
        """
        if self._storage is None:
            return False

        return self._storage.delete(archive_id)

    def delete_all_archives(self) -> int:
        """
        Delete all archives for current session.

        Returns:
            int: Number of archives deleted
        """
        if self._storage is None:
            return 0

        if not self._session_id:
            return 0

        return self._storage.delete_session(self._session_id)

    # =========================================================================
    # Pruning Operations
    # =========================================================================

    def prune_old(
        self,
        max_age_days: int | None = None,
    ) -> int:
        """
        Remove old archives.

        Args:
            max_age_days: Max age in days (default from config)

        Returns:
            int: Number pruned

        Note:
            This is a placeholder. Full implementation would:
            1. Calculate cutoff timestamp
            2. Query archives older than cutoff
            3. Delete matching archives
        """
        # LocalColdArchive doesn't have a prune_by_age method yet
        # This would need to be implemented if needed
        if max_age_days is None:
            max_age_days = self._ss_cfg.cold.default_max_age_days
        logger.debug(
            "prune_old called with max_age_days=%d (not implemented)",
            max_age_days,
        )
        return 0

    # =========================================================================
    # Size / Stats Operations
    # =========================================================================

    def get_storage_size(self) -> int:
        """
        Get total storage size for current session.

        Returns:
            int: Total bytes in storage
        """
        if self._storage is None:
            return 0

        if not self._session_id:
            return self._storage.get_total_size()

        return self._storage.get_total_size(self._session_id)

    def get_archive_count(self) -> int:
        """
        Get archive count for current session.

        Returns:
            int: Number of archive entries
        """
        if self._storage is None:
            return 0

        if not self._session_id:
            return self._storage.get_archive_count()

        return self._storage.get_archive_count(self._session_id)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dict with total_size_bytes, archive_count, tables breakdown
        """
        if self._storage is None:
            return {
                "total_size_bytes": 0,
                "archive_count": 0,
                "tables": {},
            }

        if self._session_id:
            return self._storage.get_stats(self._session_id)

        return self._storage.get_stats()

    # =========================================================================
    # Snapshot / Metrics
    # =========================================================================

    def get_snapshot(self) -> LocalColdSnapshot:
        """
        Get a snapshot of LOCAL COLD tier state.

        Returns:
            LocalColdSnapshot: Current state
        """
        stats = self.get_stats()
        checkpoint_count = len(self.list_checkpoints())

        # Count by section
        section_counts: Dict[str, int] = {}
        for table_name, table_stats in stats.get("tables", {}).items():
            # Map table back to section
            if "checkpoint" in table_name:
                section_counts["checkpoint"] = table_stats.get("count", 0)
            elif "beliefs" in table_name:
                section_counts["beliefs"] = table_stats.get("count", 0)
            elif "history" in table_name:
                section_counts["history"] = table_stats.get("count", 0)
            elif "narrative" in table_name:
                section_counts["narrative"] = table_stats.get("count", 0)

        return LocalColdSnapshot(
            session_id=self._session_id,
            total_size_bytes=stats.get("total_size_bytes", 0),
            archive_count=stats.get("archive_count", 0),
            checkpoint_count=checkpoint_count,
            section_counts=section_counts,
            is_available=self.is_available,
            timestamp_ms=int(time.time() * 1000),
        )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get operational metrics.

        Returns:
            Dict with restores, archives, SLA info
        """
        return {
            "tier": self.tier_name,
            "session_id": self._session_id,
            "is_available": self.is_available,
            "total_restores": self._total_restores,
            "total_archives": self._total_archives,
            "bytes_archived": self._bytes_archived,
            "bytes_restored": self._bytes_restored,
            "sla_violations": self._restore_sla_violations,
            "sla_compliance_rate": self.sla_compliance_rate,
            "restore_sla_ms": self._ss_cfg.cold.restore_sla_ms,
            "created_at_ms": self._created_at_ms,
        }

    def reset_metrics(self) -> None:
        """Reset operational metrics."""
        self._total_restores = 0
        self._total_archives = 0
        self._bytes_archived = 0
        self._bytes_restored = 0
        self._restore_sla_violations = 0

    # =========================================================================
    # Storage Management
    # =========================================================================

    def set_storage(self, storage: "LocalColdArchiveType") -> None:
        """
        Set or replace the storage backend.

        Args:
            storage: LocalColdArchive instance
        """
        self._storage = storage
        logger.debug("LocalColdTier storage set")

    def vacuum(self) -> None:
        """
        Vacuum the SQLite database to reclaim space.

        Call after deleting significant data.
        """
        if self._storage is not None:
            self._storage.vacuum()

    def close(self) -> None:
        """
        Close the storage connection.

        Call on shutdown.
        """
        if self._storage is not None:
            self._storage.close()
            logger.debug("LocalColdTier storage closed")

    # =========================================================================
    # String Representation
    # =========================================================================

    def __repr__(self) -> str:
        """Return detailed representation."""
        return (
            f"LocalColdTier("
            f"session={self._session_id[:8] if self._session_id else 'none'}..., "
            f"available={self.is_available}, "
            f"archives={self._total_archives}, "
            f"sla_rate={self.sla_compliance_rate:.1%})"
        )

    def __str__(self) -> str:
        """Return readable string."""
        storage_size = self.get_storage_size()
        size_kb = storage_size / 1024
        return f"LocalColdTier: {size_kb:.1f}KB stored, {self._total_archives} archives"


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_local_cold_tier(
    session_id: str = "",
    storage: Optional["LocalColdArchiveType"] = None,
    db_path: Optional[Path] = None,
) -> LocalColdTier:
    """
    Factory function to create a LocalColdTier.

    Args:
        session_id: Session ID
        storage: Existing LocalColdArchive instance
        db_path: Path to create new LocalColdArchive

    Returns:
        LocalColdTier: Configured tier

    Example:
        # With existing storage
        tier = create_local_cold_tier(session_id="abc-123", storage=archive)

        # Create new storage
        tier = create_local_cold_tier(session_id="abc-123", db_path=Path("./test.db"))

        # No storage (for testing)
        tier = create_local_cold_tier(session_id="abc-123")
    """
    if storage is None and db_path is not None:
        # Import here to avoid circular imports
        from ..local_cold import LocalColdArchive

        storage = LocalColdArchive(db_path=db_path)

    return LocalColdTier(storage=storage, session_id=session_id)
