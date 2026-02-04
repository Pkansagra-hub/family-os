"""
InMemoryStorageAdapter - Fast Testing Storage Implementation
=============================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.1 Define Storage Port
ISSUE: 3.1.3

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Fast in-memory storage for unit tests.
    No disk I/O, cleared between tests.

USE CASE:
    - Unit tests that don't need persistence
    - Fast test execution
    - NOT for integration tests (use SQLiteStorageAdapter)

==============================================================================
CLASS: InMemoryStorageAdapter
==============================================================================
"""

import time
import uuid
from typing import Any, Dict, List

from ..ports.storage import ArchiveEntry, ArchiveResult, IStoragePort, RestoreResult


class InMemoryStorageAdapter(IStoragePort):
    """
    In-memory storage adapter for fast testing.

    Data is stored in dictionaries, no disk I/O.
    Call clear() between tests for isolation.

    Attributes:
        _archives: Dict[archive_id, data]
        _metadata: Dict[archive_id, ArchiveEntry]

    Example:
        adapter = InMemoryStorageAdapter()

        # Use in tests
        result = adapter.archive("beliefs", data, {"session_id": "test"})
        assert result.success

        # Clear between tests
        adapter.clear()
    """

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._archives: Dict[str, bytes] = {}
        self._metadata: Dict[str, ArchiveEntry] = {}

    @property
    def is_available(self) -> bool:
        """
        Always available.

        Returns:
            bool: True
        """
        return True

    @property
    def storage_type(self) -> str:
        """
        Get storage type.

        Returns:
            str: 'memory'
        """
        return "memory"

    def archive(
        self,
        section: str,
        data: bytes,
        metadata: Dict[str, Any],
    ) -> ArchiveResult:
        """
        Store data in memory.

        Args:
            section: Section name
            data: Data bytes
            metadata: Must include 'session_id'

        Returns:
            ArchiveResult: Always succeeds
        """
        start = time.perf_counter()
        archive_id = str(uuid.uuid4())

        session_id = metadata.get("session_id", "")
        if not session_id:
            return ArchiveResult(
                success=False,
                archive_id="",
                size_bytes=0,
                duration_ms=0.0,
                error="session_id required in metadata",
            )

        self._archives[archive_id] = data
        self._metadata[archive_id] = ArchiveEntry(
            archive_id=archive_id,
            session_id=session_id,
            section=section,
            size_bytes=len(data),
            created_at_ms=int(time.time() * 1000),
            metadata=metadata,
        )

        duration_ms = (time.perf_counter() - start) * 1000
        return ArchiveResult(
            success=True,
            archive_id=archive_id,
            size_bytes=len(data),
            duration_ms=duration_ms,
        )

    def restore(
        self,
        section: str,
        filters: Dict[str, Any],
    ) -> RestoreResult:
        """
        Restore data from memory.

        Args:
            section: Section name
            filters: Must include 'session_id'

        Returns:
            RestoreResult: Data if found
        """
        start = time.perf_counter()

        session_id = filters.get("session_id", "")
        if not session_id:
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=0.0,
                error="session_id required in filters",
            )

        # Check for specific archive_id
        archive_id = filters.get("archive_id")
        if archive_id:
            if archive_id in self._archives:
                entry = self._metadata[archive_id]
                duration_ms = (time.perf_counter() - start) * 1000
                return RestoreResult(
                    success=True,
                    data=self._archives[archive_id],
                    archive_id=archive_id,
                    size_bytes=entry.size_bytes,
                    duration_ms=duration_ms,
                )
            else:
                duration_ms = (time.perf_counter() - start) * 1000
                return RestoreResult(
                    success=False,
                    data=None,
                    archive_id="",
                    size_bytes=0,
                    duration_ms=duration_ms,
                    error=f"Archive not found: {archive_id}",
                )

        # Find most recent matching session_id and section
        matching = [
            (aid, entry)
            for aid, entry in self._metadata.items()
            if entry.session_id == session_id and entry.section == section
        ]

        if not matching:
            duration_ms = (time.perf_counter() - start) * 1000
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=duration_ms,
                error=f"No archive found for session={session_id}, section={section}",
            )

        # Get most recent
        matching.sort(key=lambda x: x[1].created_at_ms, reverse=True)
        archive_id, entry = matching[0]

        duration_ms = (time.perf_counter() - start) * 1000
        return RestoreResult(
            success=True,
            data=self._archives[archive_id],
            archive_id=archive_id,
            size_bytes=entry.size_bytes,
            duration_ms=duration_ms,
        )

    def list_archives(
        self,
        session_id: str,
    ) -> List[ArchiveEntry]:
        """
        List archives for session.

        Args:
            session_id: Session to list

        Returns:
            List[ArchiveEntry]: Matching archives
        """
        entries = [entry for entry in self._metadata.values() if entry.session_id == session_id]
        entries.sort(key=lambda x: x.created_at_ms, reverse=True)
        return entries

    def delete(self, archive_id: str) -> bool:
        """
        Delete archive.

        Args:
            archive_id: Archive to delete

        Returns:
            bool: True if found and deleted
        """
        if archive_id in self._archives:
            del self._archives[archive_id]
            del self._metadata[archive_id]
            return True
        return False

    def clear(self) -> None:
        """
        Clear all stored data.

        Call between tests for isolation.
        """
        self._archives.clear()
        self._metadata.clear()

    def get_archive_count(self) -> int:
        """
        Get number of stored archives.

        Returns:
            int: Archive count
        """
        return len(self._archives)

    def get_total_size(self) -> int:
        """
        Get total size of stored data.

        Returns:
            int: Total bytes
        """
        return sum(len(data) for data in self._archives.values())

    def __repr__(self) -> str:
        """String representation."""
        return f"InMemoryStorageAdapter(archives={len(self._archives)})"
