"""
IStoragePort - Storage Layer Interface
=======================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.1 Define Storage Port
ISSUE: 3.1.1

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Define the interface SessionState EXPECTS from persistence layer.
    Allows swapping between SQLiteStorageAdapter (LOCAL COLD) and
    BridgeStorageAdapter (K0 sync) without changing SessionState code.

IMPLEMENTATIONS:
    - SQLiteStorageAdapter: LOCAL COLD (K1 SQLite) - always available
    - InMemoryStorageAdapter: For testing (no disk I/O)
    - BridgeStorageAdapter: K0 sync (future, provided by bridge/)

==============================================================================
INTERFACE: IStoragePort
==============================================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ArchiveResult:
    """Result of an archive operation."""

    success: bool
    archive_id: str
    size_bytes: int
    duration_ms: float
    error: Optional[str] = None


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    data: Optional[bytes]
    archive_id: str
    size_bytes: int
    duration_ms: float
    error: Optional[str] = None


@dataclass
class ArchiveEntry:
    """Metadata for an archived item."""

    archive_id: str
    session_id: str
    section: str
    size_bytes: int
    created_at_ms: int
    metadata: Dict[str, Any]


class IStoragePort(ABC):
    """
    Interface for SessionState persistence layer.

    SessionState uses this port for:
    - Archiving evicted data to LOCAL COLD
    - Restoring data for reconstruction
    - Session checkpoints

    Properties:
        is_available: Whether storage is currently accessible
        storage_type: Type identifier ('local' or 'k0')

    Example:
        class SQLiteStorageAdapter(IStoragePort):
            @property
            def is_available(self) -> bool:
                return True  # Local SQLite always available

            def archive(...) -> ArchiveResult:
                # SQLite implementation
                pass
    """

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if storage is currently accessible.

        Returns:
            bool: True if storage can be used

        Notes:
            - LOCAL COLD (SQLite): Always True
            - K0: May be False if offline
        """
        pass

    @property
    @abstractmethod
    def storage_type(self) -> str:
        """
        Get storage type identifier.

        Returns:
            str: 'local' for LOCAL COLD, 'k0' for cloud
        """
        pass

    @abstractmethod
    def archive(
        self,
        section: str,
        data: bytes,
        metadata: Dict[str, Any],
    ) -> ArchiveResult:
        """
        Archive data to storage.

        Args:
            section: Section name (e.g., 'beliefs_history')
            data: FlatBuffer-serialized data
            metadata: Archive metadata (session_id, reason, etc.)

        Returns:
            ArchiveResult: Success/failure with archive_id

        Required metadata:
            - session_id: str
            - reason: str (e.g., 'eviction', 'checkpoint')
        """
        pass

    @abstractmethod
    def restore(
        self,
        section: str,
        filters: Dict[str, Any],
    ) -> RestoreResult:
        """
        Restore data from storage.

        Args:
            section: Section name
            filters: Query filters (session_id required, optional: date range, etc.)

        Returns:
            RestoreResult: Data if found, error if not

        Required filters:
            - session_id: str

        Optional filters:
            - archive_id: str (specific archive)
            - after_ms: int (created after timestamp)
            - before_ms: int (created before timestamp)
        """
        pass

    @abstractmethod
    def list_archives(
        self,
        session_id: str,
    ) -> List[ArchiveEntry]:
        """
        List all archives for a session.

        Args:
            session_id: Session to list

        Returns:
            List[ArchiveEntry]: Archive metadata (not data)
        """
        pass

    @abstractmethod
    def delete(self, archive_id: str) -> bool:
        """
        Delete an archive entry.

        Args:
            archive_id: Archive to delete

        Returns:
            bool: True if deleted, False if not found
        """
        pass


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. ABC USAGE:
   Use ABC for type checking and documentation.
   All methods are @abstractmethod.

2. DATA FORMAT:
   - data parameter is always bytes (FlatBuffer-serialized)
   - metadata is always Dict for flexibility
   - timestamps are always int (ms since epoch)

3. ERROR HANDLING:
   - Return ArchiveResult/RestoreResult with error field
   - Never raise exceptions
   - Log errors internally

4. IMPLEMENTATIONS TO CREATE:
   - SQLiteStorageAdapter (k1/sessionstate/adapters/sqlite_storage.py)
   - InMemoryStorageAdapter (k1/sessionstate/adapters/memory_storage.py)
   - BridgeStorageAdapter (bridge/adapters/storage.py) - FUTURE

5. TESTING:
   Test against interface, not implementation.
   Use InMemoryStorageAdapter for fast tests.
"""
