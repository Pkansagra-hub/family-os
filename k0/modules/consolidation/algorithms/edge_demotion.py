"""
CausalEdgeFeedbackProcessor - Process feedback and demote contradicted edges.

This module implements edge demotion based on prediction accuracy:
- Track prediction outcomes per causal edge
- Boost confidence for accurate predictions (>90%)
- Lower confidence for below-target accuracy (50-70%)
- Demote to CORRELATED for consistently wrong predictions (<50%)
- Archive stale unused edges (90 days)

Spec Reference:
    - Dossier §4.5.4.4: Causal Edge Feedback
    - Dossier §4.5.4.3: Confound Detection
    - M4_EXECUTION.md Issue 4.4.11

Human Memory Model:
    We update our mental causal models based on outcomes.
    "I thought coffee caused my productivity, but tracking shows it's the morning routine."

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================


# Accuracy thresholds for actions
ACCURACY_BOOST_THRESHOLD = 0.90  # Boost if >90%
ACCURACY_ADEQUATE_THRESHOLD = 0.70  # Adequate if 70-90%
ACCURACY_DEMOTE_THRESHOLD = 0.50  # Demote if <50%

# Confidence adjustments
BOOST_AMOUNT = 0.05
LOWER_AMOUNT = 0.10

# Staleness
STALENESS_DAYS = 90
MIN_FEEDBACK_SAMPLES = 5

# Feedback window
FEEDBACK_WINDOW_DAYS = 30


# =============================================================================
# Enums
# =============================================================================


class EdgeStatus(Enum):
    """Edge type/status values."""

    CAUSAL = "CAUSAL"
    CORRELATED = "CORRELATED"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    ARCHIVED = "ARCHIVED"


class DemotionAction(Enum):
    """Actions that can be taken on an edge."""

    BOOST = "boost"
    MAINTAIN = "maintain"
    LOWER = "lower"
    DEMOTE = "demote"
    ARCHIVE = "archive"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class DemotionResult:
    """
    Result of edge demotion evaluation.

    Contains the action taken and the before/after state.
    """

    edge_id: str
    action: DemotionAction
    old_status: EdgeStatus
    new_status: EdgeStatus
    old_confidence: float
    new_confidence: float
    reason: str
    accuracy: Optional[float] = None
    sample_count: int = 0


@dataclass
class FeedbackRecord:
    """Record of a single feedback event."""

    feedback_id: str
    edge_id: str
    signal_type: str
    source_system: str
    prediction_context: Dict[str, Any]
    actual_outcome: Dict[str, Any]
    space_id: str
    created_at: int


# =============================================================================
# Utility Functions
# =============================================================================


def now_ms() -> int:
    """Current time in milliseconds since Unix epoch."""
    return int(time.time() * 1000)


def generate_ulid() -> str:
    """Generate a ULID for new records."""
    import secrets

    timestamp_ms = now_ms()
    time_bytes = timestamp_ms.to_bytes(6, byteorder="big")
    random_bytes = secrets.token_bytes(10)
    ulid_bytes = time_bytes + random_bytes

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    result = []
    value = int.from_bytes(ulid_bytes, byteorder="big")

    for _ in range(26):
        result.append(alphabet[value & 31])
        value >>= 5

    return "".join(reversed(result))


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database operations."""

    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        """Fetch single row."""
        ...

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch single value."""
        ...

    async def fetch(self, query: str, *args) -> List[dict]:
        """Fetch multiple rows."""
        ...

    async def execute(self, query: str, *args) -> str:
        """Execute query and return status."""
        ...


# =============================================================================
# CausalEdgeFeedbackProcessor
# =============================================================================


class CausalEdgeFeedbackProcessor:
    """
    Process feedback for causal edges and adjust confidence.

    Spec: Dossier §4.5.4.4

    Features:
    - Track prediction accuracy per edge
    - Boost/lower confidence based on accuracy
    - Demote edges that are wrong more than right
    - Archive stale unused edges

    Accuracy Thresholds:
    - >90%: Boost confidence +0.05
    - 70-90%: Maintain current state
    - 50-70%: Lower confidence -0.10
    - <50%: Demote to CORRELATED
    """

    def __init__(
        self,
        accuracy_boost_threshold: float = ACCURACY_BOOST_THRESHOLD,
        accuracy_adequate_threshold: float = ACCURACY_ADEQUATE_THRESHOLD,
        accuracy_demote_threshold: float = ACCURACY_DEMOTE_THRESHOLD,
        boost_amount: float = BOOST_AMOUNT,
        lower_amount: float = LOWER_AMOUNT,
        min_feedback_samples: int = MIN_FEEDBACK_SAMPLES,
        feedback_window_days: int = FEEDBACK_WINDOW_DAYS,
    ):
        """
        Initialize feedback processor.

        Args:
            accuracy_boost_threshold: Boost if accuracy above this
            accuracy_adequate_threshold: Adequate if above this
            accuracy_demote_threshold: Demote if below this
            boost_amount: Amount to boost confidence
            lower_amount: Amount to lower confidence
            min_feedback_samples: Minimum samples before demotion
            feedback_window_days: Days to consider for accuracy
        """
        self.accuracy_boost_threshold = accuracy_boost_threshold
        self.accuracy_adequate_threshold = accuracy_adequate_threshold
        self.accuracy_demote_threshold = accuracy_demote_threshold
        self.boost_amount = boost_amount
        self.lower_amount = lower_amount
        self.min_feedback_samples = min_feedback_samples
        self.feedback_window_days = feedback_window_days

    async def process_feedback(
        self,
        edge_id: str,
        feedback_signal: str,
        outcome_details: Dict[str, Any],
        db_conn: DatabaseConnection,
    ) -> Optional[DemotionResult]:
        """
        Update causal edge based on usage feedback.

        Main entry point for processing feedback. Records the feedback,
        computes accuracy, and applies appropriate action.

        Args:
            edge_id: ID of the causal edge
            feedback_signal: Type of feedback (CONFIRMED, WRONG, etc.)
            outcome_details: Details about the prediction/outcome
            db_conn: Database connection

        Returns:
            DemotionResult if action taken, None if edge not found
        """
        # Fetch edge
        edge = await db_conn.fetchrow(
            """
            SELECT * FROM st_kg_edges
            WHERE edge_id = $1 AND edge_type IN ('CAUSAL', 'CORRELATED')
            """,
            edge_id,
        )

        if not edge:
            logger.warning(f"Edge not found for feedback: {edge_id}")
            return None

        # Record feedback in tracking table
        await self._record_feedback(edge_id, feedback_signal, outcome_details, db_conn)

        # Compute accuracy over feedback window
        accuracy = await self.compute_accuracy(
            edge_id, days=self.feedback_window_days, db_conn=db_conn
        )

        # Get sample count for demotion protection
        sample_count = await self._get_sample_count(edge_id, self.feedback_window_days, db_conn)

        # Determine action based on accuracy
        result = await self._evaluate_edge(edge, accuracy, sample_count, db_conn)

        logger.info(
            f"Processed feedback for edge {edge_id}: "
            f"signal={feedback_signal}, accuracy={accuracy:.2f}, action={result.action.value}"
        )

        return result

    async def _record_feedback(
        self,
        edge_id: str,
        feedback_signal: str,
        outcome_details: Dict[str, Any],
        db_conn: DatabaseConnection,
    ) -> None:
        """Record feedback in st_causal_feedback table."""
        await db_conn.execute(
            """
            INSERT INTO st_causal_feedback (
                feedback_id, edge_id, signal_type, source_system,
                prediction_context, actual_outcome, space_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            generate_ulid(),
            edge_id,
            feedback_signal,
            outcome_details.get("source", "K1"),
            json.dumps(outcome_details.get("prediction", {})),
            json.dumps(outcome_details.get("actual", {})),
            outcome_details.get("space_id", "default"),
            now_ms(),
        )

    async def compute_accuracy(
        self,
        edge_id: str,
        days: int,
        db_conn: DatabaseConnection,
    ) -> float:
        """
        Compute prediction accuracy over time window.

        Accuracy = correct / total

        Args:
            edge_id: Edge to compute accuracy for
            days: Number of days to look back
            db_conn: Database connection

        Returns:
            Accuracy [0.0, 1.0], defaults to 1.0 if no feedback
        """
        cutoff_time = now_ms() - (days * 86400000)

        result = await db_conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE signal_type = 'CAUSAL_PREDICTION_CONFIRMED'
                ) as correct,
                COUNT(*) FILTER (
                    WHERE signal_type IN ('CAUSAL_PREDICTION_WRONG', 'USER_REJECTS_CAUSATION')
                ) as incorrect,
                COUNT(*) as total
            FROM st_causal_feedback
            WHERE edge_id = $1
              AND created_at >= $2
            """,
            edge_id,
            cutoff_time,
        )

        if result is None or result["total"] == 0:
            return 1.0  # No feedback yet, assume correct

        return result["correct"] / result["total"]

    async def _get_sample_count(
        self,
        edge_id: str,
        days: int,
        db_conn: DatabaseConnection,
    ) -> int:
        """Get feedback sample count for edge."""
        cutoff_time = now_ms() - (days * 86400000)
        result = await db_conn.fetchval(
            """
            SELECT COUNT(*) FROM st_causal_feedback
            WHERE edge_id = $1 AND created_at >= $2
            """,
            edge_id,
            cutoff_time,
        )
        return result or 0

    async def _evaluate_edge(
        self,
        edge: dict,
        accuracy: float,
        sample_count: int,
        db_conn: DatabaseConnection,
    ) -> DemotionResult:
        """Evaluate edge and apply action based on accuracy."""
        edge_id = edge["edge_id"]
        old_confidence = edge.get("causal_confidence", 0.5)
        old_status = EdgeStatus(edge["edge_type"])

        if accuracy > self.accuracy_boost_threshold:
            # Boost confidence
            new_confidence = min(1.0, old_confidence + self.boost_amount)
            await self._update_edge_confidence(edge_id, new_confidence, db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action=DemotionAction.BOOST,
                old_status=old_status,
                new_status=old_status,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                reason=f"High accuracy ({accuracy:.2f})",
                accuracy=accuracy,
                sample_count=sample_count,
            )

        elif accuracy >= self.accuracy_adequate_threshold:
            # Maintain current state
            await self._update_last_validated(edge_id, db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action=DemotionAction.MAINTAIN,
                old_status=old_status,
                new_status=old_status,
                old_confidence=old_confidence,
                new_confidence=old_confidence,
                reason=f"Adequate accuracy ({accuracy:.2f})",
                accuracy=accuracy,
                sample_count=sample_count,
            )

        elif accuracy >= self.accuracy_demote_threshold:
            # Lower confidence but don't demote yet
            new_confidence = max(0.0, old_confidence - self.lower_amount)
            await self._update_edge_confidence(edge_id, new_confidence, db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action=DemotionAction.LOWER,
                old_status=old_status,
                new_status=old_status,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                reason=f"Below target accuracy ({accuracy:.2f})",
                accuracy=accuracy,
                sample_count=sample_count,
            )

        else:
            # Accuracy < 50%: demote to CORRELATED
            if sample_count < self.min_feedback_samples:
                # Not enough samples, don't demote yet
                return DemotionResult(
                    edge_id=edge_id,
                    action=DemotionAction.MAINTAIN,
                    old_status=old_status,
                    new_status=old_status,
                    old_confidence=old_confidence,
                    new_confidence=old_confidence,
                    reason=f"Low accuracy but insufficient samples ({sample_count})",
                    accuracy=accuracy,
                    sample_count=sample_count,
                )

            await self._demote_edge(edge_id, f"LOW_ACCURACY_{accuracy:.2f}", db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action=DemotionAction.DEMOTE,
                old_status=old_status,
                new_status=EdgeStatus.CORRELATED,
                old_confidence=old_confidence,
                new_confidence=0.0,
                reason=f"Demoted: accuracy {accuracy:.2f} < 0.50",
                accuracy=accuracy,
                sample_count=sample_count,
            )

    async def _demote_edge(
        self,
        edge_id: str,
        reason: str,
        db_conn: DatabaseConnection,
    ) -> None:
        """Demote causal edge to CORRELATED."""
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET edge_type = 'CORRELATED',
                metadata_json = jsonb_set(
                    COALESCE(metadata_json, '{}'::jsonb),
                    '{demotion_reason}',
                    to_jsonb($1::text)
                ),
                updated_at = $2
            WHERE edge_id = $3
            """,
            reason,
            now_ms(),
            edge_id,
        )

        logger.info(f"Demoted edge {edge_id} to CORRELATED: {reason}")

    async def _update_edge_confidence(
        self,
        edge_id: str,
        confidence: float,
        db_conn: DatabaseConnection,
    ) -> None:
        """Update edge confidence."""
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET causal_confidence = $1,
                last_validated_at = $2
            WHERE edge_id = $3
            """,
            confidence,
            now_ms(),
            edge_id,
        )

    async def _update_last_validated(
        self,
        edge_id: str,
        db_conn: DatabaseConnection,
    ) -> None:
        """Update last validated timestamp."""
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET last_validated_at = $1
            WHERE edge_id = $2
            """,
            now_ms(),
            edge_id,
        )


# =============================================================================
# CausalEdgeStalenessChecker
# =============================================================================


class CausalEdgeStalenessChecker:
    """
    Identify and archive unused causal edges.

    Spec: Dossier §4.5.4.4

    Edges that haven't been used in 90 days are considered stale
    and should be archived to reduce noise in the knowledge graph.
    """

    def __init__(self, staleness_days: int = STALENESS_DAYS):
        """
        Initialize staleness checker.

        Args:
            staleness_days: Days after which unused edges are stale
        """
        self.staleness_days = staleness_days

    async def check_staleness(
        self,
        space_id: str,
        db_conn: DatabaseConnection,
    ) -> List[str]:
        """
        Find causal edges not used in staleness window.

        Args:
            space_id: Space to check
            db_conn: Database connection

        Returns:
            List of stale edge_ids
        """
        cutoff_time = now_ms() - (self.staleness_days * 86400000)

        stale_edges = await db_conn.fetch(
            """
            SELECT edge_id FROM st_kg_edges
            WHERE edge_type = 'CAUSAL'
              AND space_id = $1
              AND (last_used_at IS NULL OR last_used_at < $2)
            """,
            space_id,
            cutoff_time,
        )

        return [e["edge_id"] for e in stale_edges]

    async def archive_stale_edges(
        self,
        space_id: str,
        db_conn: DatabaseConnection,
    ) -> int:
        """
        Archive causal edges unused for staleness window.

        Args:
            space_id: Space to archive edges in
            db_conn: Database connection

        Returns:
            Count of archived edges
        """
        stale_edge_ids = await self.check_staleness(space_id, db_conn)

        if not stale_edge_ids:
            return 0

        result = await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET archival_status = 'ARCHIVED',
                archived_at = $1
            WHERE edge_id = ANY($2)
            """,
            now_ms(),
            stale_edge_ids,
        )

        # Parse count from result string like "UPDATE 5"
        try:
            count = int(result.split()[-1])
        except (ValueError, IndexError):
            count = len(stale_edge_ids)

        logger.info(f"Archived {count} stale causal edges in space {space_id}")
        return count

    async def archive_single_edge(
        self,
        edge_id: str,
        reason: str,
        db_conn: DatabaseConnection,
    ) -> DemotionResult:
        """
        Archive a single edge with reason.

        Args:
            edge_id: Edge to archive
            reason: Reason for archival
            db_conn: Database connection

        Returns:
            DemotionResult with archive action
        """
        # Get current edge state
        edge = await db_conn.fetchrow(
            "SELECT * FROM st_kg_edges WHERE edge_id = $1",
            edge_id,
        )

        if not edge:
            return DemotionResult(
                edge_id=edge_id,
                action=DemotionAction.ARCHIVE,
                old_status=EdgeStatus.CAUSAL,
                new_status=EdgeStatus.ARCHIVED,
                old_confidence=0.0,
                new_confidence=0.0,
                reason="Edge not found",
            )

        old_status = EdgeStatus(edge.get("edge_type", "CAUSAL"))
        old_confidence = edge.get("causal_confidence", 0.0)

        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                metadata_json = jsonb_set(
                    COALESCE(metadata_json, '{}'::jsonb),
                    '{archive_reason}',
                    to_jsonb($2::text)
                )
            WHERE edge_id = $3
            """,
            now_ms(),
            reason,
            edge_id,
        )

        logger.info(f"Archived edge {edge_id}: {reason}")

        return DemotionResult(
            edge_id=edge_id,
            action=DemotionAction.ARCHIVE,
            old_status=old_status,
            new_status=EdgeStatus.ARCHIVED,
            old_confidence=old_confidence,
            new_confidence=0.0,
            reason=reason,
        )
