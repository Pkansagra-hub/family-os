"""
Query auditor for detecting cross-space violations.

Scans pg_stat_statements for queries to learning tables
that are missing space_id filters.

Dossier Reference: Section 8.1 `CrossSpaceAuditor` class
Related Issues: 6.3.8 Query audit scanner for missing space_id

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List

from k0.pipelines.p03.security.rls_verifier import RLS_REQUIRED_TABLES, check_rls_health

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


@dataclass
class QueryViolation:
    """A query that may be violating space isolation."""

    query: str
    table: str
    calls: int
    detected_at: datetime = field(default_factory=datetime.utcnow)
    reason: str = "missing_space_id"  # 'missing_space_id' | 'suspicious_join'


@dataclass
class SecurityReport:
    """Result of security scan."""

    scan_time: datetime
    violations: List[QueryViolation] = field(default_factory=list)
    rls_healthy: bool = True
    tables_without_rls: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Return True if no violations and RLS is healthy."""
        return len(self.violations) == 0 and self.rls_healthy


class CrossSpaceAuditor:
    """
    Audits queries for cross-space isolation violations.

    Uses pg_stat_statements to detect queries that access
    learning tables without proper space_id filtering.
    """

    def __init__(self, conn: "Connection") -> None:
        """Initialize with database connection.

        Args:
            conn: Active database connection
        """
        self.conn = conn

    async def audit_queries(
        self,
        time_window_hours: int = 168,  # 1 week
    ) -> List[QueryViolation]:
        """
        Scan pg_stat_statements for potential violations.

        Args:
            time_window_hours: How far back to scan (default 7 days)

        Returns:
            List of QueryViolation for suspicious queries
        """
        violations: List[QueryViolation] = []

        # Check if pg_stat_statements extension is available
        extension_exists = await self.conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
            )
            """
        )

        if not extension_exists:
            logger.warning("pg_stat_statements extension not installed, " "skipping query audit")
            return violations

        # Build regex pattern for all protected tables
        table_pattern = "|".join(RLS_REQUIRED_TABLES)

        # Query pg_stat_statements for queries touching our tables
        rows = await self.conn.fetch(
            """
            SELECT query, calls
            FROM pg_stat_statements
            WHERE query ~* $1
            ORDER BY calls DESC
            LIMIT 1000
            """,
            table_pattern,
        )

        for row in rows:
            query = row["query"]
            # Check if query mentions a protected table without space_id
            for table in RLS_REQUIRED_TABLES:
                if table in query.lower():
                    if not self._has_space_filter(query):
                        violations.append(
                            QueryViolation(
                                query=query[:500],  # Truncate long queries
                                table=table,
                                calls=row["calls"],
                                detected_at=datetime.utcnow(),
                                reason="missing_space_id",
                            )
                        )

        return violations

    def _has_space_filter(self, query: str) -> bool:
        """Check if query has space_id in WHERE clause.

        Args:
            query: SQL query string

        Returns:
            True if query contains space_id filtering
        """
        query_lower = query.lower()
        # Look for space_id in WHERE clause
        patterns = [
            r"where.*space_id",
            r"and\s+space_id",
            r"space_id\s*=",
            r"current_setting\s*\(\s*['\"]app\.current_space_id",
        ]
        return any(re.search(p, query_lower) for p in patterns)

    async def weekly_scan(self) -> SecurityReport:
        """
        Run full weekly security scan.

        Combines query audit with RLS health check.

        Returns:
            SecurityReport with all findings
        """
        # Audit queries
        violations = await self.audit_queries(time_window_hours=168)

        # Check RLS health
        rls_report = await check_rls_health(self.conn)

        # Emit metrics if available
        try:
            from k0.observability.metrics import counter, gauge

            if violations:
                counter(
                    "p03_cross_space_query_attempts",
                    len(violations),
                    labels={"pipeline": "p03_consolidation"},
                )

            gauge(
                "p03_isolation_health",
                1.0 if rls_report.healthy and not violations else 0.0,
                labels={"pipeline": "p03_consolidation"},
            )
        except ImportError:
            logger.warning("Metrics module not available, skipping emission")

        report = SecurityReport(
            scan_time=datetime.utcnow(),
            violations=violations,
            rls_healthy=rls_report.healthy,
            tables_without_rls=rls_report.tables_missing_rls,
        )

        if not report.is_clean:
            await self.emit_alert("security_violation", report)

        return report

    async def emit_alert(
        self,
        alert_type: str,
        report: SecurityReport,
    ) -> None:
        """
        Emit security alert for violations.

        Args:
            alert_type: Type of alert
            report: Security report with details
        """
        logger.critical(
            "P03 security scan found violations",
            extra={
                "alert_type": alert_type,
                "violation_count": len(report.violations),
                "tables_without_rls": report.tables_without_rls,
                "scan_time": report.scan_time.isoformat(),
            },
        )
        # In production, integrate with alerting system (PagerDuty, etc.)


async def run_security_scan(conn: "Connection") -> SecurityReport:
    """
    Convenience function to run a full security scan.

    Args:
        conn: Database connection

    Returns:
        SecurityReport with all findings
    """
    auditor = CrossSpaceAuditor(conn)
    return await auditor.weekly_scan()
