"""
P03 Audit Retention - Retention wiring for consolidation audit records.

This module implements the retention policy for st_consolidation_audit,
enforcing 90-day raw retention with aggregation before deletion.

Spec Reference: Dossier §6.20 Retention Policy

DESIGN DECISIONS:
    - 90 days raw audit records, then aggregate and delete
    - Daily summaries per space with action counts and avg confidence
    - Idempotent: safe to run multiple times
    - Logs counts without sensitive payloads

TIMESTAMP CONVENTION (LOCKED):
    All `*_at` and `*_ts` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

# =============================================================================
# CONSTANTS
# =============================================================================


# Default retention period in days
DEFAULT_RETENTION_DAYS = 90

# Milliseconds per day
MS_PER_DAY = 24 * 60 * 60 * 1000


# =============================================================================
# AGGREGATION RESULT DATACLASS
# =============================================================================


@dataclass
class DailyAuditSummary:
    """
    Daily aggregated summary of audit records for a space.

    Created before deleting raw records to preserve statistical value.
    """

    # Summary key
    summary_date: str  # ISO date format: YYYY-MM-DD
    space_id: str
    tenant_id: str

    # Aggregated counts per action
    action_counts: Dict[str, int] = field(default_factory=dict)

    # Aggregated statistics
    total_records: int = 0
    avg_confidence: Optional[float] = None
    min_confidence: Optional[float] = None
    max_confidence: Optional[float] = None

    # Source formulas used
    formula_counts: Dict[str, int] = field(default_factory=dict)

    # Timestamp of aggregation
    aggregated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "summary_date": self.summary_date,
            "space_id": self.space_id,
            "tenant_id": self.tenant_id,
            "action_counts": self.action_counts,
            "total_records": self.total_records,
            "avg_confidence": self.avg_confidence,
            "min_confidence": self.min_confidence,
            "max_confidence": self.max_confidence,
            "formula_counts": self.formula_counts,
            "aggregated_at": self.aggregated_at,
        }


@dataclass
class RetentionJobResult:
    """
    Result of running the retention maintenance job.
    """

    # Time range processed
    cutoff_timestamp_ms: int
    job_started_at: int
    job_completed_at: int = 0

    # Counts
    records_scanned: int = 0
    records_deleted: int = 0
    summaries_created: int = 0

    # Errors (if any)
    errors: List[str] = field(default_factory=list)

    # Status
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "cutoff_timestamp_ms": self.cutoff_timestamp_ms,
            "job_started_at": self.job_started_at,
            "job_completed_at": self.job_completed_at,
            "records_scanned": self.records_scanned,
            "records_deleted": self.records_deleted,
            "summaries_created": self.summaries_created,
            "errors": self.errors,
            "success": self.success,
        }


# =============================================================================
# REPOSITORY PROTOCOL
# =============================================================================


class RetentionRepository(Protocol):
    """
    Protocol for retention operations on audit records.

    This abstraction allows for different implementations:
    - Real database operations (production)
    - In-memory mock (testing)
    """

    def get_records_before_cutoff(
        self,
        cutoff_ms: int,
        batch_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get audit records older than cutoff timestamp.

        Args:
            cutoff_ms: Unix timestamp in milliseconds
            batch_size: Maximum records to return per call

        Returns:
            List of audit record dictionaries
        """
        ...

    def delete_records_by_ids(
        self,
        audit_ids: List[str],
    ) -> int:
        """
        Delete audit records by their IDs.

        Args:
            audit_ids: List of audit_id values to delete

        Returns:
            Number of records deleted
        """
        ...

    def save_daily_summary(
        self,
        summary: DailyAuditSummary,
    ) -> bool:
        """
        Save a daily aggregated summary.

        Args:
            summary: The summary to save

        Returns:
            True if saved successfully
        """
        ...

    def summary_exists(
        self,
        summary_date: str,
        space_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Check if a summary already exists (for idempotency).

        Args:
            summary_date: ISO date string
            space_id: Space ID
            tenant_id: Tenant ID

        Returns:
            True if summary already exists
        """
        ...


# =============================================================================
# IN-MEMORY MOCK REPOSITORY (for testing)
# =============================================================================


class InMemoryRetentionRepository:
    """
    In-memory implementation of RetentionRepository for testing.
    """

    def __init__(self):
        self._records: List[Dict[str, Any]] = []
        self._summaries: List[DailyAuditSummary] = []

    def add_record(self, record: Dict[str, Any]) -> None:
        """Add an audit record to the store."""
        self._records.append(record)

    def clear(self) -> None:
        """Clear all records and summaries."""
        self._records.clear()
        self._summaries.clear()

    def get_records_before_cutoff(
        self,
        cutoff_ms: int,
        batch_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get records older than cutoff."""
        matching = [r for r in self._records if r.get("created_at", 0) < cutoff_ms]
        return matching[:batch_size]

    def delete_records_by_ids(
        self,
        audit_ids: List[str],
    ) -> int:
        """Delete records by IDs."""
        id_set = set(audit_ids)
        original_count = len(self._records)
        self._records = [r for r in self._records if r.get("audit_id") not in id_set]
        return original_count - len(self._records)

    def save_daily_summary(
        self,
        summary: DailyAuditSummary,
    ) -> bool:
        """Save a daily summary."""
        self._summaries.append(summary)
        return True

    def summary_exists(
        self,
        summary_date: str,
        space_id: str,
        tenant_id: str,
    ) -> bool:
        """Check if summary exists."""
        return any(
            s.summary_date == summary_date and s.space_id == space_id and s.tenant_id == tenant_id
            for s in self._summaries
        )

    def get_summaries(self) -> List[DailyAuditSummary]:
        """Get all summaries (for testing)."""
        return list(self._summaries)


# =============================================================================
# AGGREGATION FUNCTIONS
# =============================================================================


def aggregate_records_to_daily_summaries(
    records: List[Dict[str, Any]],
) -> List[DailyAuditSummary]:
    """
    Aggregate audit records into daily summaries per space.

    Groups records by (date, space_id, tenant_id) and computes:
    - Action counts
    - Formula counts
    - Confidence statistics

    Args:
        records: List of audit record dictionaries

    Returns:
        List of DailyAuditSummary objects
    """
    # Group by (date, space_id, tenant_id)
    groups: Dict[tuple, List[Dict[str, Any]]] = {}

    for record in records:
        created_at_ms = record.get("created_at", 0)
        space_id = record.get("space_id", "unknown")
        tenant_id = record.get("tenant_id", "unknown")

        # Convert ms timestamp to date
        dt = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")

        key = (date_str, space_id, tenant_id)
        if key not in groups:
            groups[key] = []
        groups[key].append(record)

    # Create summaries
    summaries = []
    for (date_str, space_id, tenant_id), group_records in groups.items():
        # Count actions
        action_counts: Dict[str, int] = {}
        for r in group_records:
            action = r.get("action", "UNKNOWN")
            action_counts[action] = action_counts.get(action, 0) + 1

        # Count formulas
        formula_counts: Dict[str, int] = {}
        for r in group_records:
            formula = r.get("formula_used")
            if formula:
                formula_counts[formula] = formula_counts.get(formula, 0) + 1

        # Compute confidence statistics
        confidences: List[float] = []
        for r in group_records:
            conf = r.get("confidence")
            if conf is not None:
                confidences.append(float(conf))
        avg_conf: Optional[float] = sum(confidences) / len(confidences) if confidences else None
        min_conf: Optional[float] = min(confidences) if confidences else None
        max_conf: Optional[float] = max(confidences) if confidences else None

        summary = DailyAuditSummary(
            summary_date=date_str,
            space_id=space_id,
            tenant_id=tenant_id,
            action_counts=action_counts,
            total_records=len(group_records),
            avg_confidence=avg_conf,
            min_confidence=min_conf,
            max_confidence=max_conf,
            formula_counts=formula_counts,
        )
        summaries.append(summary)

    return summaries


# =============================================================================
# RETENTION SERVICE
# =============================================================================


class RetentionService:
    """
    Service for managing audit record retention.

    Implements the 90-day retention policy with aggregation:
    1. Find records older than retention period
    2. Aggregate into daily summaries (if not already done)
    3. Delete raw records
    4. Log results (without sensitive payloads)

    Usage:
        repo = InMemoryRetentionRepository()
        service = RetentionService(repo, retention_days=90)
        result = service.run_maintenance()
    """

    def __init__(
        self,
        repository: RetentionRepository,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ):
        """
        Initialize retention service.

        Args:
            repository: Implementation of RetentionRepository protocol
            retention_days: Number of days to retain raw records
        """
        self._repository = repository
        self._retention_days = retention_days

    def calculate_cutoff_timestamp(self, now_ms: Optional[int] = None) -> int:
        """
        Calculate the cutoff timestamp for retention.

        Args:
            now_ms: Current timestamp in ms (defaults to now)

        Returns:
            Cutoff timestamp in milliseconds
        """
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return now_ms - (self._retention_days * MS_PER_DAY)

    def run_maintenance(
        self,
        batch_size: int = 1000,
        now_ms: Optional[int] = None,
    ) -> RetentionJobResult:
        """
        Run the retention maintenance job.

        This method is idempotent - safe to run multiple times.

        Args:
            batch_size: Number of records to process per batch
            now_ms: Current timestamp (for testing)

        Returns:
            RetentionJobResult with counts and status
        """
        job_started = int(time.time() * 1000)
        cutoff_ms = self.calculate_cutoff_timestamp(now_ms)

        result = RetentionJobResult(
            cutoff_timestamp_ms=cutoff_ms,
            job_started_at=job_started,
        )

        try:
            # Process in batches until no more records
            while True:
                records = self._repository.get_records_before_cutoff(
                    cutoff_ms=cutoff_ms,
                    batch_size=batch_size,
                )

                if not records:
                    break

                result.records_scanned += len(records)

                # Aggregate records into daily summaries
                summaries = aggregate_records_to_daily_summaries(records)

                # Save summaries (skip if already exists for idempotency)
                for summary in summaries:
                    if not self._repository.summary_exists(
                        summary.summary_date,
                        summary.space_id,
                        summary.tenant_id,
                    ):
                        self._repository.save_daily_summary(summary)
                        result.summaries_created += 1

                # Delete processed records
                audit_ids: List[str] = [
                    str(r.get("audit_id")) for r in records if r.get("audit_id")
                ]
                deleted = self._repository.delete_records_by_ids(audit_ids)
                result.records_deleted += deleted

        except Exception as e:
            result.success = False
            result.errors.append(str(e))

        result.job_completed_at = int(time.time() * 1000)
        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_retention_service(
    repository: RetentionRepository,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> RetentionService:
    """
    Factory function to create a retention service.

    Args:
        repository: Retention repository implementation
        retention_days: Days to retain raw records (default 90)

    Returns:
        Configured RetentionService
    """
    return RetentionService(repository=repository, retention_days=retention_days)


def get_retention_policy_config() -> Dict[str, Any]:
    """
    Get retention policy configuration for st_consolidation_audit.

    This can be used to register in st_retention_policy table.

    Returns:
        Dictionary with retention policy fields
    """
    return {
        "policy_name": "consolidation_audit_retention",
        "resource_type": "st_consolidation_audit",
        "privacy_band": "AMBER",  # Contains decision metadata
        "retention_days": DEFAULT_RETENTION_DAYS,
        "archive_enabled": True,
        "archive_after_days": DEFAULT_RETENTION_DAYS,
    }
