"""
RLS enforcement verification for P03 learning tables.

Runs on startup and periodically to verify all learning tables
have proper Row-Level Security policies enabled.

Dossier Reference: Section 8.1 `check_rls_policies()`
Related Issues: 6.3.7 RLS enforcement verification job

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)

# All tables that MUST have RLS enabled
RLS_REQUIRED_TABLES: List[str] = [
    "st_learned_weights",
    "st_consolidation_audit",
    "st_pruned_entities",
    "st_decay_feedback",
    "st_feedback_signals",
    "st_feedback_quarantine",
]


@dataclass
class PolicyInfo:
    """RLS policy metadata."""

    name: str
    command: str  # SELECT, INSERT, UPDATE, DELETE, ALL, or command code
    using_expr: str | None
    with_check: str | None


@dataclass
class RLSHealthReport:
    """Result of RLS verification."""

    healthy: bool
    tables_missing_rls: List[str] = field(default_factory=list)
    tables_missing_policy: List[str] = field(default_factory=list)
    policy_details: dict[str, List[PolicyInfo]] = field(default_factory=dict)

    def summary(self) -> str:
        """Human-readable summary."""
        if self.healthy:
            return f"RLS healthy: {len(RLS_REQUIRED_TABLES)} tables protected"
        issues = []
        if self.tables_missing_rls:
            issues.append(f"Missing RLS: {self.tables_missing_rls}")
        if self.tables_missing_policy:
            issues.append(f"Missing policy: {self.tables_missing_policy}")
        return f"RLS UNHEALTHY: {', '.join(issues)}"


async def verify_rls_enabled(conn: "Connection") -> List[str]:
    """
    Check which tables have RLS enabled.

    Args:
        conn: Database connection

    Returns:
        List of table names that are MISSING RLS
    """
    missing = []
    for table in RLS_REQUIRED_TABLES:
        result = await conn.fetchval(
            """
            SELECT relrowsecurity
            FROM pg_class
            WHERE relname = $1
            """,
            table,
        )
        if result is not True:
            missing.append(table)
    return missing


async def verify_rls_policies(
    conn: "Connection",
    table: str,
) -> List[PolicyInfo]:
    """
    Get RLS policy details for a table.

    Args:
        conn: Database connection
        table: Table name

    Returns:
        List of PolicyInfo with policy details
    """
    rows = await conn.fetch(
        """
        SELECT polname, polcmd, pg_get_expr(polqual, polrelid) AS qual,
               pg_get_expr(polwithcheck, polrelid) AS withcheck
        FROM pg_policy
        JOIN pg_class ON pg_policy.polrelid = pg_class.oid
        WHERE pg_class.relname = $1
        """,
        table,
    )
    return [
        PolicyInfo(
            name=r["polname"],
            command=r["polcmd"],
            using_expr=r["qual"],
            with_check=r["withcheck"],
        )
        for r in rows
    ]


async def check_rls_health(conn: "Connection") -> RLSHealthReport:
    """
    Full RLS health check.

    Args:
        conn: Database connection

    Returns:
        RLSHealthReport with full status
    """
    missing_rls = await verify_rls_enabled(conn)
    missing_policy: List[str] = []
    policy_details: dict[str, List[PolicyInfo]] = {}

    for table in RLS_REQUIRED_TABLES:
        policies = await verify_rls_policies(conn, table)
        policy_details[table] = policies
        if not policies:
            missing_policy.append(table)

    healthy = not missing_rls and not missing_policy

    return RLSHealthReport(
        healthy=healthy,
        tables_missing_rls=missing_rls,
        tables_missing_policy=missing_policy,
        policy_details=policy_details,
    )


async def emit_rls_health_metric(conn: "Connection") -> RLSHealthReport:
    """
    Emit RLS health gauge metric.

    Metric: p03_isolation_health (1 = healthy, 0 = violations)

    Args:
        conn: Database connection

    Returns:
        RLSHealthReport with full status
    """
    report = await check_rls_health(conn)
    health_value = 1.0 if report.healthy else 0.0

    # Import metrics lazily to avoid circular imports
    try:
        from k0.observability.metrics import gauge

        gauge(
            "p03_isolation_health",
            health_value,
            labels={"pipeline": "p03_consolidation"},
        )
    except ImportError:
        logger.warning("Metrics module not available, skipping gauge emission")

    if not report.healthy:
        logger.critical(
            "RLS health check FAILED",
            extra={
                "missing_rls": report.tables_missing_rls,
                "missing_policy": report.tables_missing_policy,
            },
        )
    else:
        logger.info(
            "RLS health check passed",
            extra={"tables_protected": len(RLS_REQUIRED_TABLES)},
        )

    return report


async def verify_on_startup(conn: "Connection") -> RLSHealthReport:
    """
    Run RLS verification on P03 startup.

    Args:
        conn: Database connection

    Returns:
        RLSHealthReport with full status

    Raises:
        RuntimeError: If RLS is not properly configured
    """
    report = await check_rls_health(conn)
    if not report.healthy:
        error_msg = (
            f"P03 startup blocked: RLS not properly configured. "
            f"Missing RLS: {report.tables_missing_rls}, "
            f"Missing policy: {report.tables_missing_policy}"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    logger.info("P03 RLS verification passed on startup")
    return report


def get_required_tables() -> List[str]:
    """Return list of tables that require RLS.

    Returns:
        List of table names that must have RLS enabled
    """
    return RLS_REQUIRED_TABLES.copy()
