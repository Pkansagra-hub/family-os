"""
Tests for QuarantineReviewAPI.

Issue 6.2.15: Manual quarantine review API
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.api.quarantine_review import (
    PendingReviewsResult,
    QuarantineRecord,
    QuarantineReviewAPI,
    ReviewDecision,
    ReviewResult,
    create_quarantine_review_api,
)

# ============================================================================
# Mock database connection
# ============================================================================


@dataclass
class MockRow:
    """Mock database row."""

    data: dict

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class MockConnection:
    """Mock asyncpg connection for testing."""

    def __init__(self) -> None:
        self.executed: List[tuple] = []
        self.fetched: List[tuple] = []
        self._fetch_results: List[List[MockRow]] = []
        self._fetchrow_results: List[Optional[MockRow]] = []
        self._execute_results: List[str] = []

    def set_fetch_results(self, results: List[List[dict]]) -> None:
        """Set results for fetch() calls."""
        self._fetch_results = [[MockRow(r) for r in rows] for rows in results]

    def set_fetchrow_results(self, results: List[Optional[dict]]) -> None:
        """Set results for fetchrow() calls."""
        self._fetchrow_results = [MockRow(r) if r else None for r in results]

    def set_execute_results(self, results: List[str]) -> None:
        """Set results for execute() calls."""
        self._execute_results = results

    async def fetch(self, query: str, *args: Any) -> List[MockRow]:
        self.fetched.append((query, args))
        if self._fetch_results:
            return self._fetch_results.pop(0)
        return []

    async def fetchrow(self, query: str, *args: Any) -> Optional[MockRow]:
        self.fetched.append((query, args))
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        if self._execute_results:
            return self._execute_results.pop(0)
        return "UPDATE 1"


# ============================================================================
# Factory tests
# ============================================================================


class TestFactory:
    """Tests for create_quarantine_review_api factory."""

    def test_create_without_metrics(self) -> None:
        """Test factory without metrics."""
        api = create_quarantine_review_api()
        assert api is not None
        assert isinstance(api, QuarantineReviewAPI)

    def test_create_with_metrics(self) -> None:
        """Test factory with metrics."""
        metrics = MagicMock()
        api = create_quarantine_review_api(metrics=metrics)
        assert api is not None
        assert api._metrics is metrics


# ============================================================================
# ReviewDecision tests
# ============================================================================


class TestReviewDecision:
    """Tests for ReviewDecision enum."""

    def test_release_value(self) -> None:
        """Test RELEASE decision value."""
        assert ReviewDecision.RELEASE.value == "RELEASE"

    def test_discard_value(self) -> None:
        """Test DISCARD decision value."""
        assert ReviewDecision.DISCARD.value == "DISCARD"

    def test_enum_members(self) -> None:
        """Test enum has exactly two members."""
        assert len(ReviewDecision) == 2


# ============================================================================
# QuarantineRecord tests
# ============================================================================


class TestQuarantineRecord:
    """Tests for QuarantineRecord dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating minimal record."""
        record = QuarantineRecord(
            quarantine_id="q1",
            signal_id="s1",
            space_id="space1",
            reason="RATE_LIMIT",
            severity="LOW",
            detected_at=1000,
            auto_release_at=2000,
        )
        assert record.quarantine_id == "q1"
        assert record.reviewed_at is None
        assert record.decision is None

    def test_create_with_review(self) -> None:
        """Test creating record with review data."""
        record = QuarantineRecord(
            quarantine_id="q1",
            signal_id="s1",
            space_id="space1",
            reason="ANOMALY",
            severity="HIGH",
            detected_at=1000,
            auto_release_at=2000,
            reviewed_at=1500,
            reviewed_by="reviewer1",
            decision="RELEASE",
        )
        assert record.reviewed_at == 1500
        assert record.decision == "RELEASE"

    def test_frozen(self) -> None:
        """Test record is frozen (immutable)."""
        record = QuarantineRecord(
            quarantine_id="q1",
            signal_id="s1",
            space_id="space1",
            reason="RATE_LIMIT",
            severity="LOW",
            detected_at=1000,
            auto_release_at=2000,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            record.quarantine_id = "q2"  # type: ignore


# ============================================================================
# PendingReviewsResult tests
# ============================================================================


class TestPendingReviewsResult:
    """Tests for PendingReviewsResult dataclass."""

    def test_has_next_page_true(self) -> None:
        """Test has_next_page when more pages exist."""
        result = PendingReviewsResult(
            records=(),
            total_count=100,
            page=1,
            page_size=20,
        )
        assert result.has_next_page is True

    def test_has_next_page_false(self) -> None:
        """Test has_next_page when on last page."""
        result = PendingReviewsResult(
            records=(),
            total_count=100,
            page=5,
            page_size=20,
        )
        assert result.has_next_page is False

    def test_total_pages_exact(self) -> None:
        """Test total_pages with exact division."""
        result = PendingReviewsResult(
            records=(),
            total_count=100,
            page=1,
            page_size=20,
        )
        assert result.total_pages == 5

    def test_total_pages_remainder(self) -> None:
        """Test total_pages with remainder."""
        result = PendingReviewsResult(
            records=(),
            total_count=101,
            page=1,
            page_size=20,
        )
        assert result.total_pages == 6

    def test_total_pages_zero_page_size(self) -> None:
        """Test total_pages with zero page size."""
        result = PendingReviewsResult(
            records=(),
            total_count=100,
            page=1,
            page_size=0,
        )
        assert result.total_pages == 0


# ============================================================================
# ReviewResult tests
# ============================================================================


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_successful_review(self) -> None:
        """Test successful review result."""
        result = ReviewResult(
            success=True,
            quarantine_id="q1",
            decision=ReviewDecision.RELEASE,
        )
        assert result.success is True
        assert result.error is None

    def test_failed_review(self) -> None:
        """Test failed review result."""
        result = ReviewResult(
            success=False,
            quarantine_id="q1",
            error="Already reviewed",
        )
        assert result.success is False
        assert result.error == "Already reviewed"


# ============================================================================
# QuarantineReviewAPI.list_pending_reviews tests
# ============================================================================


class TestListPendingReviews:
    """Tests for list_pending_reviews method."""

    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        """Test listing with no results."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results([{"total": 0}])
        conn.set_fetch_results([[]])

        result = await api.list_pending_reviews(connection=conn)

        assert result.total_count == 0
        assert len(result.records) == 0

    @pytest.mark.asyncio
    async def test_list_with_results(self) -> None:
        """Test listing with results."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results([{"total": 2}])
        conn.set_fetch_results(
            [
                [
                    {
                        "quarantine_id": "q1",
                        "signal_id": "s1",
                        "space_id": "space1",
                        "reason": "RATE_LIMIT",
                        "severity": "LOW",
                        "detected_at": 1000,
                        "auto_release_at": 2000,
                    },
                    {
                        "quarantine_id": "q2",
                        "signal_id": "s2",
                        "space_id": "space1",
                        "reason": "ANOMALY",
                        "severity": "HIGH",
                        "detected_at": 1100,
                        "auto_release_at": 2100,
                    },
                ]
            ]
        )

        result = await api.list_pending_reviews(connection=conn)

        assert result.total_count == 2
        assert len(result.records) == 2
        assert result.records[0].quarantine_id == "q1"

    @pytest.mark.asyncio
    async def test_list_with_severity_filter(self) -> None:
        """Test listing with severity filter."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results([{"total": 1}])
        conn.set_fetch_results(
            [
                [
                    {
                        "quarantine_id": "q1",
                        "signal_id": "s1",
                        "space_id": "space1",
                        "reason": "ANOMALY",
                        "severity": "HIGH",
                        "detected_at": 1000,
                        "auto_release_at": 2000,
                    },
                ]
            ]
        )

        result = await api.list_pending_reviews(
            severity_filter="HIGH",
            connection=conn,
        )

        assert result.total_count == 1
        # Verify filter was applied in query
        assert any("severity" in str(query) for query, _ in conn.fetched)

    @pytest.mark.asyncio
    async def test_list_invalid_severity(self) -> None:
        """Test listing with invalid severity raises error."""
        api = QuarantineReviewAPI()
        conn = MockConnection()

        with pytest.raises(ValueError, match="Invalid severity"):
            await api.list_pending_reviews(
                severity_filter="INVALID",
                connection=conn,
            )

    @pytest.mark.asyncio
    async def test_list_invalid_reason(self) -> None:
        """Test listing with invalid reason raises error."""
        api = QuarantineReviewAPI()
        conn = MockConnection()

        with pytest.raises(ValueError, match="Invalid reason"):
            await api.list_pending_reviews(
                reason_filter="INVALID",
                connection=conn,
            )

    @pytest.mark.asyncio
    async def test_list_pagination(self) -> None:
        """Test pagination parameters."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results([{"total": 100}])
        conn.set_fetch_results([[]])

        result = await api.list_pending_reviews(
            page=2,
            page_size=25,
            connection=conn,
        )

        assert result.page == 2
        assert result.page_size == 25

    @pytest.mark.asyncio
    async def test_list_page_size_clamped(self) -> None:
        """Test page size is clamped to max 100."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results([{"total": 0}])
        conn.set_fetch_results([[]])

        result = await api.list_pending_reviews(
            page_size=200,  # Over max
            connection=conn,
        )

        assert result.page_size == 100  # Clamped


# ============================================================================
# QuarantineReviewAPI.get_quarantine_details tests
# ============================================================================


class TestGetQuarantineDetails:
    """Tests for get_quarantine_details method."""

    @pytest.mark.asyncio
    async def test_get_existing(self) -> None:
        """Test getting existing record."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results(
            [
                {
                    "quarantine_id": "q1",
                    "signal_id": "s1",
                    "space_id": "space1",
                    "reason": "RATE_LIMIT",
                    "severity": "LOW",
                    "detected_at": 1000,
                    "auto_release_at": 2000,
                    "reviewed_at": None,
                    "reviewed_by": None,
                    "decision": None,
                }
            ]
        )

        result = await api.get_quarantine_details("q1", connection=conn)

        assert result is not None
        assert result.quarantine_id == "q1"
        assert result.decision is None

    @pytest.mark.asyncio
    async def test_get_not_found(self) -> None:
        """Test getting non-existent record."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results([None])

        result = await api.get_quarantine_details("not_found", connection=conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_reviewed(self) -> None:
        """Test getting reviewed record."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetchrow_results(
            [
                {
                    "quarantine_id": "q1",
                    "signal_id": "s1",
                    "space_id": "space1",
                    "reason": "ANOMALY",
                    "severity": "HIGH",
                    "detected_at": 1000,
                    "auto_release_at": 2000,
                    "reviewed_at": 1500,
                    "reviewed_by": "admin",
                    "decision": "RELEASE",
                }
            ]
        )

        result = await api.get_quarantine_details("q1", connection=conn)

        assert result is not None
        assert result.decision == "RELEASE"
        assert result.reviewed_by == "admin"


# ============================================================================
# QuarantineReviewAPI.review_quarantined_signal tests
# ============================================================================


class TestReviewQuarantinedSignal:
    """Tests for review_quarantined_signal method."""

    @pytest.mark.asyncio
    async def test_successful_release(self) -> None:
        """Test successful release decision."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 1", "UPDATE 1"])
        conn.set_fetchrow_results([{"signal_id": "s1"}])

        result = await api.review_quarantined_signal(
            "q1",
            "reviewer1",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        assert result.success is True
        assert result.decision == ReviewDecision.RELEASE

    @pytest.mark.asyncio
    async def test_successful_discard(self) -> None:
        """Test successful discard decision."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 1", "UPDATE 1"])
        conn.set_fetchrow_results([{"signal_id": "s1"}])

        result = await api.review_quarantined_signal(
            "q1",
            "reviewer1",
            ReviewDecision.DISCARD,
            connection=conn,
        )

        assert result.success is True
        assert result.decision == ReviewDecision.DISCARD

    @pytest.mark.asyncio
    async def test_already_reviewed(self) -> None:
        """Test reviewing already-reviewed signal."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 0"])
        conn.set_fetchrow_results([{"decision": "RELEASE"}])

        result = await api.review_quarantined_signal(
            "q1",
            "reviewer1",
            ReviewDecision.DISCARD,
            connection=conn,
        )

        assert result.success is False
        assert "Already reviewed" in str(result.error)

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """Test reviewing non-existent signal."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 0"])
        conn.set_fetchrow_results([None])

        result = await api.review_quarantined_signal(
            "not_found",
            "reviewer1",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        assert result.success is False
        assert "not found" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_empty_quarantine_id(self) -> None:
        """Test with empty quarantine_id."""
        api = QuarantineReviewAPI()
        conn = MockConnection()

        result = await api.review_quarantined_signal(
            "",
            "reviewer1",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        assert result.success is False
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_empty_reviewer_id(self) -> None:
        """Test with empty reviewer_id."""
        api = QuarantineReviewAPI()
        conn = MockConnection()

        result = await api.review_quarantined_signal(
            "q1",
            "",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        assert result.success is False
        assert "required" in str(result.error).lower()


# ============================================================================
# QuarantineReviewAPI.bulk_review tests
# ============================================================================


class TestBulkReview:
    """Tests for bulk_review method."""

    @pytest.mark.asyncio
    async def test_bulk_review_all_success(self) -> None:
        """Test bulk review with all successful."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        # Set up responses for 2 reviews
        conn.set_execute_results(["UPDATE 1", "UPDATE 1", "UPDATE 1", "UPDATE 1"])
        conn.set_fetchrow_results([{"signal_id": "s1"}, {"signal_id": "s2"}])

        results = await api.bulk_review(
            ["q1", "q2"],
            "reviewer1",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_bulk_review_partial_failure(self) -> None:
        """Test bulk review with some failures."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 1", "UPDATE 1", "UPDATE 0"])
        conn.set_fetchrow_results([{"signal_id": "s1"}, {"decision": "DISCARD"}])

        results = await api.bulk_review(
            ["q1", "q2"],
            "reviewer1",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False


# ============================================================================
# QuarantineReviewAPI.get_review_stats tests
# ============================================================================


class TestGetReviewStats:
    """Tests for get_review_stats method."""

    @pytest.mark.asyncio
    async def test_stats_empty(self) -> None:
        """Test stats with no records."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetch_results([[]])

        stats = await api.get_review_stats(connection=conn)

        assert stats["pending"]["total"] == 0
        assert stats["released"]["total"] == 0
        assert stats["discarded"]["total"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_data(self) -> None:
        """Test stats with mixed data."""
        api = QuarantineReviewAPI()
        conn = MockConnection()
        conn.set_fetch_results(
            [
                [
                    {"decision": None, "severity": "HIGH", "count": 5},
                    {"decision": None, "severity": "LOW", "count": 10},
                    {"decision": "RELEASE", "severity": "LOW", "count": 3},
                    {"decision": "DISCARD", "severity": "HIGH", "count": 2},
                ]
            ]
        )

        stats = await api.get_review_stats(connection=conn)

        assert stats["pending"]["total"] == 15
        assert stats["pending"]["by_severity"]["HIGH"] == 5
        assert stats["released"]["total"] == 3
        assert stats["discarded"]["total"] == 2


# ============================================================================
# Metrics emission tests
# ============================================================================


class TestMetricsEmission:
    """Tests for metrics emission."""

    @pytest.mark.asyncio
    async def test_pending_gauge_emitted(self) -> None:
        """Test pending reviews gauge is emitted."""
        metrics = MagicMock()
        api = QuarantineReviewAPI(metrics=metrics)
        conn = MockConnection()
        conn.set_fetchrow_results([{"total": 42}])
        conn.set_fetch_results([[]])

        await api.list_pending_reviews(connection=conn)

        metrics.gauge.assert_called_with(
            "p03_quarantine_pending_reviews",
            42,
        )

    @pytest.mark.asyncio
    async def test_review_counter_emitted(self) -> None:
        """Test review decision counter is emitted."""
        metrics = MagicMock()
        api = QuarantineReviewAPI(metrics=metrics)
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 1", "UPDATE 1"])
        conn.set_fetchrow_results([{"signal_id": "s1"}])

        await api.review_quarantined_signal(
            "q1",
            "reviewer1",
            ReviewDecision.RELEASE,
            connection=conn,
        )

        metrics.emit.assert_called_with(
            "p03_quarantine_review_decisions_total",
            1.0,
            decision="RELEASE",
        )
