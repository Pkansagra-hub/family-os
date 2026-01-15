"""
P03 Explainability Query API - Read path for memory decision explanations.

This module provides the query surface for answering "why was this memory
handled this way?" by looking up audit records from st_consolidation_audit.

Spec Reference: Dossier §6.20.3, §14.10

DESIGN DECISIONS:
    - Returns only user-safe fields (no inputs_json/outputs_json)
    - Cross-space lookups blocked by RLS at database level
    - Default explanations provided when no audit record exists
    - Immutable result dataclass for thread safety

TIMESTAMP CONVENTION (LOCKED):
    All `*_at` and `*_ts` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

# =============================================================================
# RESULT DATACLASS
# =============================================================================


@dataclass(frozen=True)
class MemoryExplanation:
    """
    User-facing explanation for a memory decision.

    This is the public API result - it intentionally excludes
    inputs_json/outputs_json which are for ops/debug only.
    """

    memory_id: str
    action: str
    explanation: str
    confidence: Optional[float]
    created_at: int  # Unix timestamp ms
    source_table: Optional[str] = None
    formula_used: Optional[str] = None
    cycle_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "memory_id": self.memory_id,
            "action": self.action,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "source_table": self.source_table,
            "formula_used": self.formula_used,
            "cycle_id": self.cycle_id,
        }


# =============================================================================
# DEFAULT EXPLANATIONS
# =============================================================================


DEFAULT_EXPLANATION = (
    "No consolidation decision has been recorded for this memory yet. "
    "The memory may be new or awaiting processing."
)


def get_default_explanation(memory_id: str) -> MemoryExplanation:
    """
    Return default explanation when no audit record exists.

    Args:
        memory_id: The memory ID that was queried

    Returns:
        MemoryExplanation with default values
    """
    return MemoryExplanation(
        memory_id=memory_id,
        action="UNKNOWN",
        explanation=DEFAULT_EXPLANATION,
        confidence=None,
        created_at=0,
        source_table=None,
        formula_used=None,
        cycle_id=None,
    )


# =============================================================================
# DATABASE PROTOCOL
# =============================================================================


class AuditRepository(Protocol):
    """
    Protocol for audit record lookup.

    This abstraction allows for different implementations:
    - Real database queries (production)
    - In-memory mock (testing)
    """

    def get_latest_audit_for_memory(
        self,
        memory_id: str,
        space_id: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Lookup the latest audit record for a memory.

        Args:
            memory_id: The memory ID to lookup
            space_id: User/family space for isolation
            tenant_id: Tenant ID for multi-tenant isolation

        Returns:
            Dictionary with audit record fields, or None if not found
        """
        ...

    def get_audit_history_for_memory(
        self,
        memory_id: str,
        space_id: str,
        tenant_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get audit history for a memory (newest first).

        Args:
            memory_id: The memory ID to lookup
            space_id: User/family space for isolation
            tenant_id: Tenant ID for multi-tenant isolation
            limit: Maximum number of records to return

        Returns:
            List of audit record dictionaries ordered by created_at DESC
        """
        ...


# =============================================================================
# IN-MEMORY MOCK REPOSITORY (for testing)
# =============================================================================


class InMemoryAuditRepository:
    """
    In-memory implementation of AuditRepository for testing.

    Thread Safety: NOT thread-safe.
    """

    def __init__(self):
        self._records: List[Dict[str, Any]] = []

    def add_record(self, record: Dict[str, Any]) -> None:
        """Add an audit record to the store."""
        self._records.append(record)

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()

    def get_latest_audit_for_memory(
        self,
        memory_id: str,
        space_id: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Lookup the latest audit record for a memory."""
        matching = [
            r
            for r in self._records
            if r.get("memory_id") == memory_id
            and r.get("space_id") == space_id
            and r.get("tenant_id") == tenant_id
        ]
        if not matching:
            return None
        # Return most recent by created_at
        return max(matching, key=lambda r: r.get("created_at", 0))

    def get_audit_history_for_memory(
        self,
        memory_id: str,
        space_id: str,
        tenant_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get audit history for a memory (newest first)."""
        matching = [
            r
            for r in self._records
            if r.get("memory_id") == memory_id
            and r.get("space_id") == space_id
            and r.get("tenant_id") == tenant_id
        ]
        # Sort by created_at descending
        sorted_records = sorted(matching, key=lambda r: r.get("created_at", 0), reverse=True)
        return sorted_records[:limit]


# =============================================================================
# EXPLAINABILITY SERVICE
# =============================================================================


class ExplainabilityService:
    """
    Service for querying memory decision explanations.

    Provides the read path for P03 consolidation decisions, returning
    user-safe explanation data without leaking internal debug fields.

    Usage:
        repo = InMemoryAuditRepository()  # or real DB repo
        service = ExplainabilityService(repo)
        explanation = service.explain_memory("mem_123", "sp_1", "t_1")
    """

    def __init__(self, repository: AuditRepository):
        """
        Initialize service with audit repository.

        Args:
            repository: Implementation of AuditRepository protocol
        """
        self._repository = repository

    def explain_memory(
        self,
        memory_id: str,
        space_id: str,
        tenant_id: str,
    ) -> MemoryExplanation:
        """
        Get explanation for a memory's most recent consolidation decision.

        Args:
            memory_id: The memory ID to explain
            space_id: User/family space (enforces isolation)
            tenant_id: Tenant ID for multi-tenant isolation

        Returns:
            MemoryExplanation with decision details or default if not found
        """
        record = self._repository.get_latest_audit_for_memory(
            memory_id=memory_id,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        if record is None:
            return get_default_explanation(memory_id)

        return self._record_to_explanation(record)

    def get_memory_history(
        self,
        memory_id: str,
        space_id: str,
        tenant_id: str,
        limit: int = 10,
    ) -> List[MemoryExplanation]:
        """
        Get history of consolidation decisions for a memory.

        Args:
            memory_id: The memory ID to query
            space_id: User/family space (enforces isolation)
            tenant_id: Tenant ID for multi-tenant isolation
            limit: Maximum number of records to return

        Returns:
            List of MemoryExplanation objects (newest first)
        """
        records = self._repository.get_audit_history_for_memory(
            memory_id=memory_id,
            space_id=space_id,
            tenant_id=tenant_id,
            limit=limit,
        )

        return [self._record_to_explanation(r) for r in records]

    def _record_to_explanation(self, record: Dict[str, Any]) -> MemoryExplanation:
        """
        Convert audit record dictionary to MemoryExplanation.

        Intentionally excludes inputs_json and outputs_json.

        Args:
            record: Raw audit record from repository

        Returns:
            User-safe MemoryExplanation object
        """
        return MemoryExplanation(
            memory_id=record.get("memory_id", ""),
            action=record.get("action", "UNKNOWN"),
            explanation=record.get("explanation", DEFAULT_EXPLANATION),
            confidence=record.get("confidence"),
            created_at=record.get("created_at", 0),
            source_table=record.get("source_table"),
            formula_used=record.get("formula_used"),
            cycle_id=record.get("cycle_id"),
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_explainability_service(
    repository: AuditRepository,
) -> ExplainabilityService:
    """
    Factory function to create an explainability service.

    Args:
        repository: Audit repository implementation

    Returns:
        Configured ExplainabilityService
    """
    return ExplainabilityService(repository=repository)
