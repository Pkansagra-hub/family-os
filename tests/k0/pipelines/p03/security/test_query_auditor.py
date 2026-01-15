"""
Tests for Query auditor for detecting cross-space violations.

Related Issues: 6.3.8 Query audit scanner for missing space_id

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from k0.pipelines.p03.security.query_auditor import (
    CrossSpaceAuditor,
    QueryViolation,
    SecurityReport,
    run_security_scan,
)


class TestQueryViolation:
    """Tests for QueryViolation dataclass."""

    def test_violation_creation(self) -> None:
        """Test creating QueryViolation instance."""
        violation = QueryViolation(
            query="SELECT * FROM st_learned_weights",
            table="st_learned_weights",
            calls=100,
        )
        assert violation.query == "SELECT * FROM st_learned_weights"
        assert violation.table == "st_learned_weights"
        assert violation.calls == 100
        assert violation.reason == "missing_space_id"
        assert isinstance(violation.detected_at, datetime)

    def test_violation_with_custom_reason(self) -> None:
        """Test violation with custom reason."""
        violation = QueryViolation(
            query="SELECT * FROM st_learned_weights JOIN other",
            table="st_learned_weights",
            calls=50,
            reason="suspicious_join",
        )
        assert violation.reason == "suspicious_join"


class TestSecurityReport:
    """Tests for SecurityReport dataclass."""

    def test_clean_report(self) -> None:
        """Test clean report with no violations."""
        report = SecurityReport(
            scan_time=datetime.utcnow(),
            rls_healthy=True,
        )
        assert report.is_clean
        assert len(report.violations) == 0
        assert len(report.tables_without_rls) == 0

    def test_report_with_violations(self) -> None:
        """Test report with violations."""
        violation = QueryViolation(
            query="SELECT * FROM st_learned_weights",
            table="st_learned_weights",
            calls=10,
        )
        report = SecurityReport(
            scan_time=datetime.utcnow(),
            violations=[violation],
            rls_healthy=True,
        )
        assert not report.is_clean
        assert len(report.violations) == 1

    def test_report_with_unhealthy_rls(self) -> None:
        """Test report with unhealthy RLS."""
        report = SecurityReport(
            scan_time=datetime.utcnow(),
            rls_healthy=False,
            tables_without_rls=["st_feedback_signals"],
        )
        assert not report.is_clean


class TestCrossSpaceAuditor:
    """Tests for CrossSpaceAuditor class."""

    @pytest.mark.asyncio
    async def test_auditor_init(self) -> None:
        """Test auditor initialization."""
        mock_conn = AsyncMock()
        auditor = CrossSpaceAuditor(mock_conn)
        assert auditor.conn is mock_conn

    @pytest.mark.asyncio
    async def test_audit_queries_no_extension(self) -> None:
        """Test audit when pg_stat_statements not installed."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = False  # Extension not installed

        auditor = CrossSpaceAuditor(mock_conn)
        violations = await auditor.audit_queries()

        assert len(violations) == 0

    @pytest.mark.asyncio
    async def test_audit_queries_no_violations(self) -> None:
        """Test audit with no violating queries."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True  # Extension installed
        # All queries have space_id filter
        mock_conn.fetch.return_value = [
            {
                "query": "SELECT * FROM st_learned_weights WHERE space_id = $1",
                "calls": 100,
            }
        ]

        auditor = CrossSpaceAuditor(mock_conn)
        violations = await auditor.audit_queries()

        assert len(violations) == 0

    @pytest.mark.asyncio
    async def test_audit_queries_with_violations(self) -> None:
        """Test audit detects missing space_id filter."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True
        mock_conn.fetch.return_value = [
            {
                "query": "SELECT * FROM st_learned_weights WHERE layer = 'st_epi'",
                "calls": 50,
            }
        ]

        auditor = CrossSpaceAuditor(mock_conn)
        violations = await auditor.audit_queries()

        assert len(violations) == 1
        assert violations[0].table == "st_learned_weights"
        assert violations[0].reason == "missing_space_id"

    @pytest.mark.asyncio
    async def test_has_space_filter_patterns(self) -> None:
        """Test _has_space_filter detection patterns."""
        mock_conn = AsyncMock()
        auditor = CrossSpaceAuditor(mock_conn)

        # Should match
        assert auditor._has_space_filter("SELECT * FROM t WHERE space_id = $1")
        assert auditor._has_space_filter("SELECT * FROM t WHERE id = 1 AND space_id = $2")
        assert auditor._has_space_filter("WHERE x = 1 and space_id = y")
        assert auditor._has_space_filter(
            "SELECT * FROM t WHERE space_id = current_setting('app.current_space_id')"
        )

        # Should not match
        assert not auditor._has_space_filter("SELECT * FROM t WHERE id = 1")
        assert not auditor._has_space_filter("SELECT space_id FROM t")
        assert not auditor._has_space_filter("INSERT INTO t (space_id) VALUES ($1)")

    @pytest.mark.asyncio
    async def test_weekly_scan_combines_checks(self) -> None:
        """Test weekly_scan combines query audit and RLS check."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True
        mock_conn.fetch.return_value = []

        auditor = CrossSpaceAuditor(mock_conn)

        with patch("k0.pipelines.p03.security.query_auditor.check_rls_health") as mock_health:
            from k0.pipelines.p03.security.rls_verifier import RLSHealthReport

            mock_health.return_value = RLSHealthReport(healthy=True)

            report = await auditor.weekly_scan()

            assert report.is_clean
            assert report.rls_healthy
            mock_health.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_weekly_scan_emits_alert_on_violations(self) -> None:
        """Test weekly_scan calls emit_alert when violations found."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True
        mock_conn.fetch.return_value = [{"query": "SELECT * FROM st_learned_weights", "calls": 1}]

        auditor = CrossSpaceAuditor(mock_conn)
        auditor.emit_alert = AsyncMock()

        with patch("k0.pipelines.p03.security.query_auditor.check_rls_health") as mock_health:
            from k0.pipelines.p03.security.rls_verifier import RLSHealthReport

            mock_health.return_value = RLSHealthReport(healthy=True)

            report = await auditor.weekly_scan()

            assert not report.is_clean
            auditor.emit_alert.assert_called_once()


class TestRunSecurityScan:
    """Tests for run_security_scan convenience function."""

    @pytest.mark.asyncio
    async def test_run_security_scan(self) -> None:
        """Test convenience function runs weekly scan."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True
        mock_conn.fetch.return_value = []

        with patch("k0.pipelines.p03.security.query_auditor.check_rls_health") as mock_health:
            from k0.pipelines.p03.security.rls_verifier import RLSHealthReport

            mock_health.return_value = RLSHealthReport(healthy=True)

            report = await run_security_scan(mock_conn)

            assert isinstance(report, SecurityReport)
            assert report.is_clean
