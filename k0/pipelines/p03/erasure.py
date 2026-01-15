"""
P03 GDPR Erasure Hooks - Implements right-to-erasure for audit and truth tables.

This module provides GDPR-compliant data erasure with three scopes:
- ACTOR_DATA: Erase only actor's own memories
- ALL_MENTIONS: Erase memories mentioning the actor
- FULL_PURGE: Complete erasure including references

Spec Reference: Dossier §6.21 GDPR Erasure

DESIGN DECISIONS:
    - Three erasure scopes with clear semantics
    - Cascades to all truth tables (st_epi, st_sem, st_kg_dom, st_kg_edges)
    - Tombstone markers for st_hipp_events (preserve event structure)
    - Compliance entries written to WAL for audit trail
    - Idempotent operations

TIMESTAMP CONVENTION (LOCKED):
    All `*_at` and `*_ts` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Set

# =============================================================================
# ERASURE SCOPE ENUM
# =============================================================================


class ErasureScope(str, Enum):
    """
    Defines the scope of data erasure for GDPR requests.

    ACTOR_DATA:
        Erase only memories directly owned by the actor.
        Use case: Actor wants to remove their personal data.

    ALL_MENTIONS:
        Erase memories where the actor appears as subject/object.
        Use case: Actor wants to be forgotten from the system.

    FULL_PURGE:
        Complete erasure including all references and edges.
        Use case: Legal requirement for complete data removal.
    """

    ACTOR_DATA = "ACTOR_DATA"
    ALL_MENTIONS = "ALL_MENTIONS"
    FULL_PURGE = "FULL_PURGE"


# =============================================================================
# ERASURE REQUEST DATACLASS
# =============================================================================


@dataclass
class ErasureRequest:
    """
    Request to erase data for a specific actor.

    Captures all context needed to perform and audit the erasure.
    """

    # Unique identifier for this erasure request
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Target actor
    actor_id: str = ""
    tenant_id: str = ""
    space_id: Optional[str] = None  # None means all spaces

    # Erasure scope
    scope: ErasureScope = ErasureScope.ACTOR_DATA

    # Requester context
    requested_by: str = ""  # Who initiated the request
    reason: str = ""  # Legal basis or reason

    # Timestamps
    requested_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "request_id": self.request_id,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "scope": self.scope.value,
            "requested_by": self.requested_by,
            "reason": self.reason,
            "requested_at": self.requested_at,
        }


@dataclass
class ErasureResult:
    """
    Result of an erasure operation.
    """

    # Request reference
    request_id: str

    # Operation timestamps
    started_at: int = field(default_factory=lambda: int(time.time() * 1000))
    completed_at: int = 0

    # Counts per table
    records_erased: Dict[str, int] = field(default_factory=dict)
    tombstones_created: int = 0

    # Compliance
    wal_entries_written: int = 0
    compliance_record_id: Optional[str] = None

    # Status
    success: bool = True
    errors: List[str] = field(default_factory=list)

    @property
    def total_erased(self) -> int:
        """Total records erased across all tables."""
        return sum(self.records_erased.values())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "request_id": self.request_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "records_erased": self.records_erased,
            "total_erased": self.total_erased,
            "tombstones_created": self.tombstones_created,
            "wal_entries_written": self.wal_entries_written,
            "compliance_record_id": self.compliance_record_id,
            "success": self.success,
            "errors": self.errors,
        }


# =============================================================================
# TOMBSTONE DATACLASS
# =============================================================================


@dataclass
class TombstoneMarker:
    """
    Tombstone marker for erased events in st_hipp_events.

    Preserves event structure while indicating erasure.
    """

    event_id: str
    original_type: str
    erased_at: int = field(default_factory=lambda: int(time.time() * 1000))
    erasure_request_id: str = ""
    erasure_scope: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "event_id": self.event_id,
            "original_type": self.original_type,
            "erased_at": self.erased_at,
            "erasure_request_id": self.erasure_request_id,
            "erasure_scope": self.erasure_scope,
            "is_tombstone": True,
        }


# =============================================================================
# REPOSITORY PROTOCOL
# =============================================================================


class ErasureRepository(Protocol):
    """
    Protocol for erasure operations across truth tables.

    Implementations must handle:
    - Cascading deletes across related tables
    - Tombstone creation for events
    - WAL compliance entries
    """

    def erase_from_st_epi(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """
        Erase episodic memories.

        Returns number of records erased.
        """
        ...

    def erase_from_st_sem(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """
        Erase semantic memories.

        Returns number of records erased.
        """
        ...

    def erase_from_st_kg_dom(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """
        Erase knowledge graph domain entities.

        Returns number of records erased.
        """
        ...

    def erase_from_st_kg_edges(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """
        Erase knowledge graph edges.

        Returns number of records erased.
        """
        ...

    def erase_from_st_consolidation_audit(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """
        Erase consolidation audit records.

        Returns number of records erased.
        """
        ...

    def create_tombstone_for_event(
        self,
        event_id: str,
        original_type: str,
        request_id: str,
        scope: ErasureScope,
    ) -> bool:
        """
        Create tombstone marker for an event.

        Returns True if successful.
        """
        ...

    def get_affected_event_ids(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> List[str]:
        """
        Get event IDs that will be affected by erasure.

        Returns list of event IDs.
        """
        ...

    def write_compliance_wal_entry(
        self,
        request: ErasureRequest,
        result: ErasureResult,
    ) -> str:
        """
        Write compliance entry to WAL.

        Returns the compliance record ID.
        """
        ...


# =============================================================================
# IN-MEMORY MOCK REPOSITORY (for testing)
# =============================================================================


class InMemoryErasureRepository:
    """
    In-memory implementation of ErasureRepository for testing.
    """

    def __init__(self):
        self._st_epi: List[Dict[str, Any]] = []
        self._st_sem: List[Dict[str, Any]] = []
        self._st_kg_dom: List[Dict[str, Any]] = []
        self._st_kg_edges: List[Dict[str, Any]] = []
        self._st_consolidation_audit: List[Dict[str, Any]] = []
        self._st_hipp_events: List[Dict[str, Any]] = []
        self._tombstones: List[TombstoneMarker] = []
        self._wal_entries: List[Dict[str, Any]] = []

    def add_epi_record(self, record: Dict[str, Any]) -> None:
        """Add episodic memory for testing."""
        self._st_epi.append(record)

    def add_sem_record(self, record: Dict[str, Any]) -> None:
        """Add semantic memory for testing."""
        self._st_sem.append(record)

    def add_kg_dom_record(self, record: Dict[str, Any]) -> None:
        """Add KG domain entity for testing."""
        self._st_kg_dom.append(record)

    def add_kg_edge_record(self, record: Dict[str, Any]) -> None:
        """Add KG edge for testing."""
        self._st_kg_edges.append(record)

    def add_audit_record(self, record: Dict[str, Any]) -> None:
        """Add audit record for testing."""
        self._st_consolidation_audit.append(record)

    def add_hipp_event(self, event: Dict[str, Any]) -> None:
        """Add hippocampus event for testing."""
        self._st_hipp_events.append(event)

    def clear(self) -> None:
        """Clear all data."""
        self._st_epi.clear()
        self._st_sem.clear()
        self._st_kg_dom.clear()
        self._st_kg_edges.clear()
        self._st_consolidation_audit.clear()
        self._st_hipp_events.clear()
        self._tombstones.clear()
        self._wal_entries.clear()

    def _matches_scope(
        self,
        record: Dict[str, Any],
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> bool:
        """Check if a record matches the erasure criteria."""
        # Check tenant/space first
        if record.get("tenant_id") != tenant_id:
            return False
        if space_id and record.get("space_id") != space_id:
            return False

        if scope == ErasureScope.ACTOR_DATA:
            # Only owned records
            return record.get("actor_id") == actor_id
        elif scope == ErasureScope.ALL_MENTIONS:
            # Owned or mentioned
            return (
                record.get("actor_id") == actor_id
                or record.get("subject_id") == actor_id
                or record.get("object_id") == actor_id
                or actor_id in record.get("mentions", [])
            )
        else:  # FULL_PURGE
            # All related including references
            return (
                record.get("actor_id") == actor_id
                or record.get("subject_id") == actor_id
                or record.get("object_id") == actor_id
                or record.get("source_id") == actor_id
                or record.get("target_id") == actor_id
                or actor_id in record.get("mentions", [])
                or actor_id in record.get("references", [])
            )

    def _erase_from_list(
        self,
        records: List[Dict[str, Any]],
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """Helper to erase matching records from a list."""
        original_count = len(records)
        records[:] = [
            r for r in records if not self._matches_scope(r, actor_id, tenant_id, space_id, scope)
        ]
        return original_count - len(records)

    def erase_from_st_epi(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """Erase from episodic memories."""
        return self._erase_from_list(self._st_epi, actor_id, tenant_id, space_id, scope)

    def erase_from_st_sem(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """Erase from semantic memories."""
        return self._erase_from_list(self._st_sem, actor_id, tenant_id, space_id, scope)

    def erase_from_st_kg_dom(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """Erase from KG domain entities."""
        return self._erase_from_list(self._st_kg_dom, actor_id, tenant_id, space_id, scope)

    def erase_from_st_kg_edges(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """Erase from KG edges."""
        return self._erase_from_list(self._st_kg_edges, actor_id, tenant_id, space_id, scope)

    def erase_from_st_consolidation_audit(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> int:
        """Erase from consolidation audit."""
        return self._erase_from_list(
            self._st_consolidation_audit, actor_id, tenant_id, space_id, scope
        )

    def create_tombstone_for_event(
        self,
        event_id: str,
        original_type: str,
        request_id: str,
        scope: ErasureScope,
    ) -> bool:
        """Create tombstone for an event."""
        tombstone = TombstoneMarker(
            event_id=event_id,
            original_type=original_type,
            erasure_request_id=request_id,
            erasure_scope=scope.value,
        )
        self._tombstones.append(tombstone)
        return True

    def get_affected_event_ids(
        self,
        actor_id: str,
        tenant_id: str,
        space_id: Optional[str],
        scope: ErasureScope,
    ) -> List[str]:
        """Get event IDs affected by erasure."""
        affected: List[str] = []
        for event in self._st_hipp_events:
            if self._matches_scope(event, actor_id, tenant_id, space_id, scope):
                event_id = event.get("event_id")
                if event_id:
                    affected.append(str(event_id))
        return affected

    def write_compliance_wal_entry(
        self,
        request: ErasureRequest,
        result: ErasureResult,
    ) -> str:
        """Write compliance entry to WAL."""
        entry_id = str(uuid.uuid4())
        entry = {
            "entry_id": entry_id,
            "type": "GDPR_ERASURE",
            "request": request.to_dict(),
            "result": result.to_dict(),
            "written_at": int(time.time() * 1000),
        }
        self._wal_entries.append(entry)
        return entry_id

    def get_tombstones(self) -> List[TombstoneMarker]:
        """Get all tombstones (for testing)."""
        return list(self._tombstones)

    def get_wal_entries(self) -> List[Dict[str, Any]]:
        """Get all WAL entries (for testing)."""
        return list(self._wal_entries)


# =============================================================================
# ERASURE SERVICE
# =============================================================================


# Tables to erase from in order (respects foreign key relationships)
ERASURE_TABLE_ORDER = [
    "st_kg_edges",  # Edges first (reference entities)
    "st_kg_dom",  # Then entities
    "st_epi",  # Episodic memories
    "st_sem",  # Semantic memories
    "st_consolidation_audit",  # Audit records
]


class ErasureService:
    """
    Service for executing GDPR erasure requests.

    Implements three erasure scopes with cascading deletes,
    tombstone creation, and WAL compliance entries.

    Usage:
        repo = InMemoryErasureRepository()
        service = ErasureService(repo)

        request = ErasureRequest(
            actor_id="user_123",
            tenant_id="tenant_1",
            scope=ErasureScope.ACTOR_DATA,
            requested_by="admin",
            reason="GDPR Article 17 request",
        )
        result = service.execute_erasure(request)
    """

    def __init__(self, repository: ErasureRepository):
        """
        Initialize erasure service.

        Args:
            repository: Implementation of ErasureRepository protocol
        """
        self._repository = repository

    def execute_erasure(self, request: ErasureRequest) -> ErasureResult:
        """
        Execute an erasure request.

        This method:
        1. Identifies affected events and creates tombstones
        2. Erases from all truth tables in order
        3. Writes compliance entry to WAL

        Args:
            request: The erasure request to execute

        Returns:
            ErasureResult with counts and status
        """
        result = ErasureResult(request_id=request.request_id)

        try:
            # Step 1: Create tombstones for affected events
            event_ids = self._repository.get_affected_event_ids(
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                space_id=request.space_id,
                scope=request.scope,
            )

            for event_id in event_ids:
                success = self._repository.create_tombstone_for_event(
                    event_id=event_id,
                    original_type="ERASED",
                    request_id=request.request_id,
                    scope=request.scope,
                )
                if success:
                    result.tombstones_created += 1

            # Step 2: Erase from each table
            # st_kg_edges
            erased = self._repository.erase_from_st_kg_edges(
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                space_id=request.space_id,
                scope=request.scope,
            )
            if erased > 0:
                result.records_erased["st_kg_edges"] = erased

            # st_kg_dom
            erased = self._repository.erase_from_st_kg_dom(
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                space_id=request.space_id,
                scope=request.scope,
            )
            if erased > 0:
                result.records_erased["st_kg_dom"] = erased

            # st_epi
            erased = self._repository.erase_from_st_epi(
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                space_id=request.space_id,
                scope=request.scope,
            )
            if erased > 0:
                result.records_erased["st_epi"] = erased

            # st_sem
            erased = self._repository.erase_from_st_sem(
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                space_id=request.space_id,
                scope=request.scope,
            )
            if erased > 0:
                result.records_erased["st_sem"] = erased

            # st_consolidation_audit
            erased = self._repository.erase_from_st_consolidation_audit(
                actor_id=request.actor_id,
                tenant_id=request.tenant_id,
                space_id=request.space_id,
                scope=request.scope,
            )
            if erased > 0:
                result.records_erased["st_consolidation_audit"] = erased

            # Step 3: Write compliance entry to WAL
            compliance_id = self._repository.write_compliance_wal_entry(
                request=request,
                result=result,
            )
            result.compliance_record_id = compliance_id
            result.wal_entries_written = 1

        except Exception as e:
            result.success = False
            result.errors.append(str(e))

        result.completed_at = int(time.time() * 1000)
        return result

    def validate_request(self, request: ErasureRequest) -> List[str]:
        """
        Validate an erasure request before execution.

        Args:
            request: The request to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[str] = []

        if not request.actor_id:
            errors.append("actor_id is required")
        if not request.tenant_id:
            errors.append("tenant_id is required")
        if not request.requested_by:
            errors.append("requested_by is required")
        if not request.reason:
            errors.append("reason is required for compliance")

        return errors

    def get_affected_tables(self, scope: ErasureScope) -> Set[str]:
        """
        Get the set of tables affected by an erasure scope.

        Args:
            scope: The erasure scope

        Returns:
            Set of table names
        """
        # All scopes affect all tables
        return set(ERASURE_TABLE_ORDER)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_erasure_service(repository: ErasureRepository) -> ErasureService:
    """
    Factory function to create an erasure service.

    Args:
        repository: Erasure repository implementation

    Returns:
        Configured ErasureService
    """
    return ErasureService(repository=repository)


def create_erasure_request(
    actor_id: str,
    tenant_id: str,
    scope: ErasureScope,
    requested_by: str,
    reason: str,
    space_id: Optional[str] = None,
) -> ErasureRequest:
    """
    Create a validated erasure request.

    Args:
        actor_id: ID of the actor to erase
        tenant_id: Tenant ID
        scope: Erasure scope
        requested_by: Who initiated the request
        reason: Legal basis or reason
        space_id: Optional space ID (None = all spaces)

    Returns:
        Configured ErasureRequest
    """
    return ErasureRequest(
        actor_id=actor_id,
        tenant_id=tenant_id,
        space_id=space_id,
        scope=scope,
        requested_by=requested_by,
        reason=reason,
    )
