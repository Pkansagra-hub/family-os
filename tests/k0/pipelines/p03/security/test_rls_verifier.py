"""
Tests for RLS enforcement verification job.

Related Issues: 6.3.7 RLS enforcement verification job

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from k0.pipelines.p03.security.rls_verifier import (
    RLS_REQUIRED_TABLES,
    PolicyInfo,
    RLSHealthReport,
    check_rls_health,
    get_required_tables,
    verify_on_startup,
    verify_rls_enabled,
    verify_rls_policies,
)


class TestRLSRequiredTables:
    """Tests for RLS_REQUIRED_TABLES configuration."""

    def test_all_learning_tables_included(self) -> None:
        """Verify all learning tables are in the list."""
        assert "st_learned_weights" in RLS_REQUIRED_TABLES
        assert "st_consolidation_audit" in RLS_REQUIRED_TABLES
        assert "st_pruned_entities" in RLS_REQUIRED_TABLES
        assert "st_decay_feedback" in RLS_REQUIRED_TABLES
        assert "st_feedback_signals" in RLS_REQUIRED_TABLES
        assert "st_feedback_quarantine" in RLS_REQUIRED_TABLES

    def test_table_count(self) -> None:
        """Verify expected number of tables."""
        assert len(RLS_REQUIRED_TABLES) == 6

    def test_no_duplicates(self) -> None:
        """Verify no duplicate table names."""
        assert len(RLS_REQUIRED_TABLES) == len(set(RLS_REQUIRED_TABLES))

    def test_get_required_tables_returns_copy(self) -> None:
        """Verify get_required_tables returns a copy."""
        tables = get_required_tables()
        tables.append("test_table")
        assert "test_table" not in RLS_REQUIRED_TABLES


class TestPolicyInfo:
    """Tests for PolicyInfo dataclass."""

    def test_policy_info_creation(self) -> None:
        """Test creating PolicyInfo instance."""
        policy = PolicyInfo(
            name="test_policy",
            command="ALL",
            using_expr="space_id = current_setting('app.current_space_id')",
            with_check="space_id = current_setting('app.current_space_id')",
        )
        assert policy.name == "test_policy"
        assert policy.command == "ALL"
        assert policy.using_expr is not None and "space_id" in policy.using_expr
        assert policy.with_check is not None and "space_id" in policy.with_check

    def test_policy_info_optional_fields(self) -> None:
        """Test PolicyInfo with None fields."""
        policy = PolicyInfo(
            name="select_only",
            command="r",  # SELECT
            using_expr="true",
            with_check=None,
        )
        assert policy.with_check is None


class TestRLSHealthReport:
    """Tests for RLSHealthReport dataclass."""

    def test_healthy_report(self) -> None:
        """Test healthy report creation."""
        report = RLSHealthReport(healthy=True)
        assert report.healthy
        assert len(report.tables_missing_rls) == 0
        assert len(report.tables_missing_policy) == 0

    def test_unhealthy_report(self) -> None:
        """Test unhealthy report creation."""
        report = RLSHealthReport(
            healthy=False,
            tables_missing_rls=["st_feedback_signals"],
            tables_missing_policy=["st_feedback_quarantine"],
        )
        assert not report.healthy
        assert "st_feedback_signals" in report.tables_missing_rls
        assert "st_feedback_quarantine" in report.tables_missing_policy

    def test_summary_healthy(self) -> None:
        """Test summary for healthy report."""
        report = RLSHealthReport(healthy=True)
        summary = report.summary()
        assert "healthy" in summary.lower()
        assert "6" in summary  # 6 tables

    def test_summary_unhealthy(self) -> None:
        """Test summary for unhealthy report."""
        report = RLSHealthReport(
            healthy=False,
            tables_missing_rls=["st_feedback_signals"],
        )
        summary = report.summary()
        assert "UNHEALTHY" in summary
        assert "st_feedback_signals" in summary


class TestVerifyRLSEnabled:
    """Tests for verify_rls_enabled function."""

    @pytest.mark.asyncio
    async def test_all_tables_have_rls(self) -> None:
        """Test when all tables have RLS enabled."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True

        missing = await verify_rls_enabled(mock_conn)

        assert len(missing) == 0
        assert mock_conn.fetchval.call_count == 6

    @pytest.mark.asyncio
    async def test_some_tables_missing_rls(self) -> None:
        """Test when some tables are missing RLS."""
        mock_conn = AsyncMock()

        # First 4 have RLS, last 2 don't
        mock_conn.fetchval.side_effect = [True, True, True, True, False, False]

        missing = await verify_rls_enabled(mock_conn)

        assert len(missing) == 2
        assert "st_feedback_signals" in missing
        assert "st_feedback_quarantine" in missing

    @pytest.mark.asyncio
    async def test_query_structure(self) -> None:
        """Verify correct SQL query is used."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True

        await verify_rls_enabled(mock_conn)

        # Check the SQL query pattern
        call_args = mock_conn.fetchval.call_args_list[0]
        query = call_args[0][0]
        assert "pg_class" in query
        assert "relrowsecurity" in query


class TestVerifyRLSPolicies:
    """Tests for verify_rls_policies function."""

    @pytest.mark.asyncio
    async def test_table_with_policies(self) -> None:
        """Test table that has RLS policies."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "polname": "st_learned_weights_isolation",
                "polcmd": "*",  # ALL
                "qual": "space_id = current_setting('app.current_space_id')",
                "withcheck": "space_id = current_setting('app.current_space_id')",
            }
        ]

        policies = await verify_rls_policies(mock_conn, "st_learned_weights")

        assert len(policies) == 1
        assert policies[0].name == "st_learned_weights_isolation"
        assert policies[0].using_expr is not None and "space_id" in policies[0].using_expr

    @pytest.mark.asyncio
    async def test_table_without_policies(self) -> None:
        """Test table that has no RLS policies."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        policies = await verify_rls_policies(mock_conn, "unprotected_table")

        assert len(policies) == 0

    @pytest.mark.asyncio
    async def test_query_structure(self) -> None:
        """Verify correct SQL query is used."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        await verify_rls_policies(mock_conn, "test_table")

        call_args = mock_conn.fetch.call_args
        query = call_args[0][0]
        assert "pg_policy" in query
        assert "polname" in query


class TestCheckRLSHealth:
    """Tests for check_rls_health function."""

    @pytest.mark.asyncio
    async def test_healthy_system(self) -> None:
        """Test fully healthy system."""
        mock_conn = AsyncMock()
        # All tables have RLS
        mock_conn.fetchval.return_value = True
        # All tables have policies
        mock_conn.fetch.return_value = [
            {
                "polname": "test_policy",
                "polcmd": "*",
                "qual": "space_id = current_setting('app.current_space_id')",
                "withcheck": "space_id = current_setting('app.current_space_id')",
            }
        ]

        report = await check_rls_health(mock_conn)

        assert report.healthy
        assert len(report.tables_missing_rls) == 0
        assert len(report.tables_missing_policy) == 0
        assert len(report.policy_details) == 6

    @pytest.mark.asyncio
    async def test_missing_rls_on_table(self) -> None:
        """Test system with table missing RLS."""
        mock_conn = AsyncMock()
        # Last table doesn't have RLS
        mock_conn.fetchval.side_effect = [True, True, True, True, True, False]
        mock_conn.fetch.return_value = [
            {"polname": "policy", "polcmd": "*", "qual": "true", "withcheck": None}
        ]

        report = await check_rls_health(mock_conn)

        assert not report.healthy
        assert "st_feedback_quarantine" in report.tables_missing_rls

    @pytest.mark.asyncio
    async def test_missing_policy_on_table(self) -> None:
        """Test system with table missing policy."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True

        # Most tables have policies, one doesn't
        def fetch_side_effect(query, table):
            if table == "st_feedback_signals":
                return []
            return [{"polname": "policy", "polcmd": "*", "qual": "true", "withcheck": None}]

        mock_conn.fetch.side_effect = fetch_side_effect

        report = await check_rls_health(mock_conn)

        assert not report.healthy
        assert "st_feedback_signals" in report.tables_missing_policy


class TestVerifyOnStartup:
    """Tests for verify_on_startup function."""

    @pytest.mark.asyncio
    async def test_startup_passes_when_healthy(self) -> None:
        """Test startup succeeds when RLS is healthy."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True
        mock_conn.fetch.return_value = [
            {"polname": "policy", "polcmd": "*", "qual": "true", "withcheck": None}
        ]

        report = await verify_on_startup(mock_conn)

        assert report.healthy

    @pytest.mark.asyncio
    async def test_startup_fails_when_unhealthy(self) -> None:
        """Test startup raises when RLS is misconfigured."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = False  # No RLS
        mock_conn.fetch.return_value = []

        with pytest.raises(RuntimeError) as exc_info:
            await verify_on_startup(mock_conn)

        assert "P03 startup blocked" in str(exc_info.value)
        assert "RLS not properly configured" in str(exc_info.value)
