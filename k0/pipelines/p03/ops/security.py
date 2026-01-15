"""P03 Cross-Space Security — Issue 6.1.14.

This module implements cross-space leakage detection metrics and monitoring.
RLS (Row Level Security) is enforced at the PostgreSQL level via Alembic
migrations. This module provides application-level monitoring to detect
any bypass attempts.

Issue Reference: M6_EXECUTION.md Issue 6.1.14
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.1

ARCHITECTURE NOTE:
    RLS is enforced in PostgreSQL via:
    - 0036_st_consolidation_audit.py: ENABLE ROW LEVEL SECURITY
    - 0040_st_learned_weights.py: ENABLE ROW LEVEL SECURITY
    - 0041_st_learned_weights_history.py: ENABLE ROW LEVEL SECURITY
    - 0042_st_feedback_quarantine.py: ENABLE ROW LEVEL SECURITY
    - 0044_st_golden_dataset.py: ENABLE ROW LEVEL SECURITY

    This module provides metrics and monitoring, NOT RLS enforcement.

Key Features:
    - Metrics for cross-space query attempt detection
    - RLS policy block counting
    - Isolation health gauge
    - Query audit scanning (requires pg_stat_statements)

Usage:
    from k0.pipelines.p03.ops.security import CrossSpaceAuditor

    auditor = CrossSpaceAuditor(metrics_registry)

    # Check RLS is enabled on protected tables
    rls_status = await auditor.check_rls_policies(db)

    # Scan for queries without space_id filter (requires pg_stat_statements)
    violations = await auditor.audit_queries(db, time_window_hours=168)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

__all__ = [
    "CrossSpaceAuditor",
    "PROTECTED_TABLES",
    "RLSViolation",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# PROTECTED TABLES (from Dossier 8.1)
# =============================================================================

# Tables with RLS policies requiring space_id isolation
PROTECTED_TABLES = frozenset(
    {
        "st_learned_weights",
        "st_learned_weights_history",
        "st_consolidation_audit",
        "st_feedback_quarantine",
        "st_golden_dataset_pairs",
        "st_validation_results",
    }
)

# Tables that P03 writes to (subset of PROTECTED_TABLES)
P03_WRITE_TABLES = frozenset(
    {
        "st_learned_weights",
        "st_consolidation_audit",
    }
)

# Query types for metric labeling
QUERY_TYPES = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    }
)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True, slots=True)
class RLSViolation:
    """Record of a potential RLS violation."""

    table: str
    query_type: str
    query_hash: str  # Hashed query for identification
    calls: int
    user_id: str | None = None


@dataclass(frozen=True, slots=True)
class RLSPolicyStatus:
    """Status of RLS policy on a table."""

    table: str
    rls_enabled: bool
    policy_count: int = 0


# =============================================================================
# CROSS-SPACE AUDITOR
# =============================================================================


class CrossSpaceAuditor:
    """Monitor and audit cross-space access attempts.

    This class provides metrics and audit capabilities for detecting
    cross-space data access attempts. RLS enforcement is handled by
    PostgreSQL policies - this class monitors and reports.

    Thread Safety:
        Thread-safe. Uses P03MetricsRegistry which is thread-safe.

    Usage:
        auditor = CrossSpaceAuditor(metrics_registry)

        # On startup, verify RLS is enabled
        rls_status = await auditor.check_rls_policies(db)
        if not all(s.rls_enabled for s in rls_status.values()):
            logger.critical("RLS not enabled on protected tables!")

        # Periodic audit (e.g., weekly job)
        violations = await auditor.audit_queries(db)
        if violations:
            alert("Cross-space query attempts detected!")
    """

    def __init__(self, metrics: P03MetricsRegistry | None = None) -> None:
        """Initialize auditor.

        Args:
            metrics: P03MetricsRegistry for emitting security metrics.
        """
        self._metrics = metrics

    async def check_rls_policies(self, db: Any) -> dict[str, RLSPolicyStatus]:
        """Verify RLS is enabled on all protected tables.

        Args:
            db: Database connection with fetchval method.

        Returns:
            Dict mapping table name to RLSPolicyStatus.
        """
        results: dict[str, RLSPolicyStatus] = {}

        for table in PROTECTED_TABLES:
            try:
                # Check if table exists and has RLS enabled
                rls_enabled = await db.fetchval(
                    """
                    SELECT relrowsecurity
                    FROM pg_class
                    WHERE relname = $1
                    """,
                    table,
                )

                # Count policies on table
                policy_count = (
                    await db.fetchval(
                        """
                    SELECT COUNT(*)
                    FROM pg_policies
                    WHERE tablename = $1
                    """,
                        table,
                    )
                    or 0
                )

                results[table] = RLSPolicyStatus(
                    table=table,
                    rls_enabled=bool(rls_enabled),
                    policy_count=int(policy_count),
                )

                if not rls_enabled:
                    LOGGER.critical(
                        "RLS NOT ENABLED on protected table: %s",
                        table,
                    )
                    if self._metrics:
                        self._emit_isolation_health(False)

            except Exception as e:
                LOGGER.error(
                    "Failed to check RLS status for table %s: %s",
                    table,
                    e,
                )
                results[table] = RLSPolicyStatus(
                    table=table,
                    rls_enabled=False,
                    policy_count=0,
                )

        # Set isolation health based on all tables
        all_enabled = all(s.rls_enabled for s in results.values())
        if self._metrics:
            self._emit_isolation_health(all_enabled)

        return results

    async def audit_queries(
        self,
        db: Any,
        time_window_hours: int = 168,  # 7 days
    ) -> list[RLSViolation]:
        """Scan pg_stat_statements for queries missing space_id filter.

        Requires pg_stat_statements extension to be enabled.

        Args:
            db: Database connection.
            time_window_hours: Time window for query analysis (default 7 days).

        Returns:
            List of potential violations.
        """
        violations: list[RLSViolation] = []

        # Check if pg_stat_statements is available
        try:
            has_extension = await db.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
                )
                """
            )
            if not has_extension:
                LOGGER.warning(
                    "pg_stat_statements extension not installed, " "query auditing disabled"
                )
                return violations
        except Exception as e:
            LOGGER.warning("Cannot check pg_stat_statements: %s", e)
            return violations

        for table in PROTECTED_TABLES:
            try:
                # Query for statements hitting this table without space_id
                rows = await db.fetch(
                    """
                    SELECT
                        query,
                        calls,
                        userid::text as user_id,
                        queryid::text as query_hash
                    FROM pg_stat_statements
                    WHERE query ILIKE $1
                      AND query NOT ILIKE '%space_id%'
                      AND query NOT ILIKE '%CREATE%'
                      AND query NOT ILIKE '%ALTER%'
                      AND query NOT ILIKE '%DROP%'
                      AND query NOT ILIKE '%GRANT%'
                      AND query NOT ILIKE '%REVOKE%'
                      AND query NOT ILIKE '%POLICY%'
                    LIMIT 100
                    """,
                    f"%{table}%",
                )

                for row in rows:
                    query = row.get("query", "")
                    query_type = self._classify_query(query)

                    violation = RLSViolation(
                        table=table,
                        query_type=query_type,
                        query_hash=row.get("query_hash", "unknown"),
                        calls=row.get("calls", 0),
                        user_id=row.get("user_id"),
                    )
                    violations.append(violation)

                    # Emit metric for each violation
                    if self._metrics:
                        self._emit_cross_space_attempt(table, query_type)

            except Exception as e:
                LOGGER.error("Failed to audit table %s: %s", table, e)

        # Update isolation health
        if violations:
            LOGGER.critical(
                "Cross-space query violations detected: %d queries",
                len(violations),
            )
            if self._metrics:
                self._emit_isolation_health(False)
        else:
            if self._metrics:
                self._emit_isolation_health(True)

        return violations

    def record_rls_block(self, table: str, policy_name: str = "space_isolation") -> None:
        """Record when RLS policy blocks a query.

        Call this from exception handlers when PostgreSQL raises an RLS
        violation error.

        Args:
            table: Table that blocked the query.
            policy_name: Name of the RLS policy.
        """
        LOGGER.warning("RLS policy blocked query on table %s", table)
        if self._metrics:
            self._emit_rls_block(table, policy_name)

    def _classify_query(self, query: str) -> str:
        """Classify query type from SQL text."""
        query_upper = query.strip().upper()
        for query_type in QUERY_TYPES:
            if query_upper.startswith(query_type):
                return query_type
        return "OTHER"

    def _extract_table(self, query: str) -> str:
        """Extract table name from query (best effort)."""
        # Simple regex to find table names
        for table in PROTECTED_TABLES:
            if re.search(rf"\b{table}\b", query, re.IGNORECASE):
                return table
        return "unknown"

    # =========================================================================
    # METRICS EMISSION
    # =========================================================================

    def _emit_cross_space_attempt(self, table: str, query_type: str) -> None:
        """Emit cross-space query attempt counter."""
        if self._metrics:
            self._metrics.exporter.emit(
                "p03_cross_space_query_attempts",
                1.0,
                table=table,
                query_type=query_type,
            )

    def _emit_rls_block(self, table: str, policy_name: str) -> None:
        """Emit RLS policy block counter."""
        if self._metrics:
            self._metrics.exporter.emit(
                "p03_rls_policy_blocks",
                1.0,
                table=table,
                policy_name=policy_name,
            )

    def _emit_isolation_health(self, healthy: bool) -> None:
        """Set isolation health gauge."""
        if self._metrics:
            self._metrics.exporter.set_gauge(
                "p03_isolation_health",
                1.0 if healthy else 0.0,
            )
