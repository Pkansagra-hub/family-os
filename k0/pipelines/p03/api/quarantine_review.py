"""
Quarantine Manual Review API for P03.

Issue 6.2.15: Manual quarantine review API

API for security operators to manually review quarantined signals,
making RELEASE or DISCARD decisions.

Dossier Reference: Section 6.21.3 Manual Review
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


class ReviewDecision(Enum):
    """Valid review decisions for quarantined signals."""

    RELEASE = "RELEASE"
    DISCARD = "DISCARD"


@dataclass(frozen=True)
class QuarantineRecord:
    """Quarantine record for review.

    Represents a quarantined feedback signal with all
    relevant metadata for review decisions.
    """

    quarantine_id: str
    signal_id: str
    space_id: str
    reason: str
    severity: str
    detected_at: int
    auto_release_at: int
    reviewed_at: Optional[int] = None
    reviewed_by: Optional[str] = None
    decision: Optional[str] = None


@dataclass(frozen=True)
class PendingReviewsResult:
    """Result of pending reviews query with pagination."""

    records: tuple[QuarantineRecord, ...]
    total_count: int
    page: int
    page_size: int

    @property
    def has_next_page(self) -> bool:
        """Check if there are more pages."""
        return self.page * self.page_size < self.total_count

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.page_size == 0:
            return 0
        return (self.total_count + self.page_size - 1) // self.page_size


@dataclass(frozen=True)
class ReviewResult:
    """Result of a review operation."""

    success: bool
    quarantine_id: str
    decision: Optional[ReviewDecision] = None
    error: Optional[str] = None


class QuarantineReviewAPI:
    """
    API for manual review of quarantined signals.

    Allows security operators to:
    - List pending reviews (with pagination and filtering)
    - Get details of specific quarantined signal
    - Make RELEASE or DISCARD decisions
    - Get review statistics

    Dossier Reference: Section 6.21.3
    """

    # Valid severity levels for filtering
    VALID_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH"})

    # Valid reasons for filtering
    VALID_REASONS = frozenset({"RATE_LIMIT", "VELOCITY_SPIKE", "ANOMALY", "ENTROPY"})

    def __init__(
        self,
        *,
        metrics: Optional["MetricsExporter"] = None,
    ):
        """Initialize the review API.

        Args:
            metrics: Optional metrics exporter for observability
        """
        self._metrics = metrics

    async def list_pending_reviews(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        severity_filter: Optional[str] = None,
        reason_filter: Optional[str] = None,
        space_id_filter: Optional[str] = None,
        connection: "asyncpg.Connection",
    ) -> PendingReviewsResult:
        """
        List quarantined signals pending review.

        Args:
            page: Page number (1-indexed)
            page_size: Number of records per page (max 100)
            severity_filter: Filter by severity (LOW, MEDIUM, HIGH)
            reason_filter: Filter by reason (RATE_LIMIT, VELOCITY_SPIKE, ANOMALY, ENTROPY)
            space_id_filter: Filter by space_id
            connection: Database connection

        Returns:
            PendingReviewsResult with records and pagination info.

        Raises:
            ValueError: If invalid filter values provided
        """
        # Validate inputs
        if page < 1:
            page = 1
        page_size = min(max(page_size, 1), 100)  # Clamp to 1-100

        if severity_filter and severity_filter not in self.VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity_filter}")

        if reason_filter and reason_filter not in self.VALID_REASONS:
            raise ValueError(f"Invalid reason: {reason_filter}")

        offset = (page - 1) * page_size

        # Build WHERE clause dynamically
        where_conditions = ["decision IS NULL"]
        params: List = []
        param_idx = 1

        if severity_filter:
            where_conditions.append(f"severity = ${param_idx}")
            params.append(severity_filter)
            param_idx += 1

        if reason_filter:
            where_conditions.append(f"reason = ${param_idx}")
            params.append(reason_filter)
            param_idx += 1

        if space_id_filter:
            where_conditions.append(f"space_id = ${param_idx}")
            params.append(space_id_filter)
            param_idx += 1

        where_clause = " AND ".join(where_conditions)

        # Get total count
        count_row = await connection.fetchrow(
            f"""
            SELECT COUNT(*) as total
            FROM st_feedback_quarantine
            WHERE {where_clause}
            """,
            *params,
        )
        total_count = count_row["total"]

        # Get records with priority sorting (HIGH severity first, then by age)
        rows = await connection.fetch(
            f"""
            SELECT
                quarantine_id, signal_id, space_id,
                reason, severity, detected_at, auto_release_at
            FROM st_feedback_quarantine
            WHERE {where_clause}
            ORDER BY
                CASE severity
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                END,
                detected_at ASC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """,
            *params,
            page_size,
            offset,
        )

        records = tuple(
            QuarantineRecord(
                quarantine_id=row["quarantine_id"],
                signal_id=row["signal_id"],
                space_id=row["space_id"],
                reason=row["reason"],
                severity=row["severity"],
                detected_at=row["detected_at"],
                auto_release_at=row["auto_release_at"],
            )
            for row in rows
        )

        # Emit gauge for pending reviews
        self._emit_pending_gauge(total_count)

        return PendingReviewsResult(
            records=records,
            total_count=total_count,
            page=page,
            page_size=page_size,
        )

    async def get_quarantine_details(
        self,
        quarantine_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> Optional[QuarantineRecord]:
        """
        Get details of a specific quarantined signal.

        Args:
            quarantine_id: ID of quarantine record
            connection: Database connection

        Returns:
            QuarantineRecord if found, None otherwise.
        """
        row = await connection.fetchrow(
            """
            SELECT
                quarantine_id, signal_id, space_id,
                reason, severity, detected_at, auto_release_at,
                reviewed_at, reviewed_by, decision
            FROM st_feedback_quarantine
            WHERE quarantine_id = $1
            """,
            quarantine_id,
        )

        if not row:
            return None

        return QuarantineRecord(
            quarantine_id=row["quarantine_id"],
            signal_id=row["signal_id"],
            space_id=row["space_id"],
            reason=row["reason"],
            severity=row["severity"],
            detected_at=row["detected_at"],
            auto_release_at=row["auto_release_at"],
            reviewed_at=row["reviewed_at"],
            reviewed_by=row["reviewed_by"],
            decision=row["decision"],
        )

    async def review_quarantined_signal(
        self,
        quarantine_id: str,
        reviewer_id: str,
        decision: ReviewDecision,
        *,
        connection: "asyncpg.Connection",
    ) -> ReviewResult:
        """
        Make review decision on quarantined signal.

        Args:
            quarantine_id: ID of quarantine record
            reviewer_id: ID of reviewer making decision
            decision: RELEASE or DISCARD

        Returns:
            ReviewResult with success status.
        """
        if not quarantine_id:
            return ReviewResult(
                success=False,
                quarantine_id=quarantine_id,
                error="quarantine_id is required",
            )

        if not reviewer_id:
            return ReviewResult(
                success=False,
                quarantine_id=quarantine_id,
                error="reviewer_id is required",
            )

        reviewed_at = int(time.time())

        # Update quarantine record (only if not already reviewed)
        result = await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = $2,
                decision = $3
            WHERE quarantine_id = $4
              AND decision IS NULL
            """,
            reviewed_at,
            reviewer_id,
            decision.value,
            quarantine_id,
        )

        if result == "UPDATE 0":
            # Check if record exists
            existing = await connection.fetchrow(
                "SELECT decision FROM st_feedback_quarantine WHERE quarantine_id = $1",
                quarantine_id,
            )
            if existing is None:
                return ReviewResult(
                    success=False,
                    quarantine_id=quarantine_id,
                    error="Quarantine record not found",
                )
            return ReviewResult(
                success=False,
                quarantine_id=quarantine_id,
                error=f"Already reviewed with decision: {existing['decision']}",
            )

        # Get signal_id for updating source
        row = await connection.fetchrow(
            """
            SELECT signal_id
            FROM st_feedback_quarantine
            WHERE quarantine_id = $1
            """,
            quarantine_id,
        )

        if row:
            # Update source signal status
            new_status = "RELEASED" if decision == ReviewDecision.RELEASE else "DISCARDED"
            await connection.execute(
                """
                UPDATE st_feedback_signals
                SET quarantine_status = $1
                WHERE signal_id = $2
                """,
                new_status,
                row["signal_id"],
            )

        # Emit metrics
        self._emit_review_metric(decision)

        return ReviewResult(
            success=True,
            quarantine_id=quarantine_id,
            decision=decision,
        )

    async def bulk_review(
        self,
        quarantine_ids: List[str],
        reviewer_id: str,
        decision: ReviewDecision,
        *,
        connection: "asyncpg.Connection",
    ) -> List[ReviewResult]:
        """
        Bulk review multiple quarantined signals.

        Args:
            quarantine_ids: List of quarantine record IDs
            reviewer_id: ID of reviewer making decision
            decision: RELEASE or DISCARD

        Returns:
            List of ReviewResult for each quarantine_id.
        """
        results = []
        for qid in quarantine_ids:
            result = await self.review_quarantined_signal(
                qid,
                reviewer_id,
                decision,
                connection=connection,
            )
            results.append(result)
        return results

    async def get_review_stats(
        self,
        *,
        space_id: Optional[str] = None,
        connection: "asyncpg.Connection",
    ) -> dict:
        """
        Get quarantine review statistics.

        Args:
            space_id: Optional filter by space
            connection: Database connection

        Returns:
            Dictionary with review statistics.
        """
        base_where = "1=1"
        params: List = []
        param_idx = 1

        if space_id:
            base_where = f"space_id = ${param_idx}"
            params.append(space_id)

        # Get counts by status
        rows = await connection.fetch(
            f"""
            SELECT
                decision,
                severity,
                COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE {base_where}
            GROUP BY decision, severity
            """,
            *params,
        )

        stats = {
            "pending": {"total": 0, "by_severity": {}},
            "released": {"total": 0, "by_severity": {}},
            "discarded": {"total": 0, "by_severity": {}},
        }

        for row in rows:
            decision = row["decision"]
            severity = row["severity"]
            count = row["count"]

            if decision is None:
                category = "pending"
            elif decision == "RELEASE":
                category = "released"
            else:
                category = "discarded"

            stats[category]["total"] += count
            stats[category]["by_severity"][severity] = (
                stats[category]["by_severity"].get(severity, 0) + count
            )

        return stats

    def _emit_pending_gauge(self, count: int) -> None:
        """Emit gauge for pending review count."""
        if self._metrics:
            self._metrics.gauge(
                "p03_quarantine_pending_reviews",
                count,
            )

    def _emit_review_metric(self, decision: ReviewDecision) -> None:
        """Emit counter for review decisions."""
        if self._metrics:
            self._metrics.emit(
                "p03_quarantine_review_decisions_total",
                1.0,
                decision=decision.value,
            )


def create_quarantine_review_api(
    *,
    metrics: Optional["MetricsExporter"] = None,
) -> QuarantineReviewAPI:
    """Factory function for QuarantineReviewAPI.

    Args:
        metrics: Optional metrics exporter

    Returns:
        Configured QuarantineReviewAPI instance
    """
    return QuarantineReviewAPI(metrics=metrics)
    return QuarantineReviewAPI(metrics=metrics)
