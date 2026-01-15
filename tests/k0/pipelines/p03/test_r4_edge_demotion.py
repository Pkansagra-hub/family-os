"""
Tests for R4 Edge Demotion for Contradicted Relationships.

Issue: 4.4.11 - Implement edge demotion for contradicted relationships

Spec Reference:
    - Dossier §4.5.4.4: Causal Edge Feedback
    - Dossier §4.5.4.3: Confound Detection
    - M4_EXECUTION.md Issue 4.4.11

Test Cases (from M4_EXECUTION.md):
    1. test_high_accuracy_boosts_confidence — >90% → +0.05
    2. test_adequate_accuracy_maintains — 70-90% → no change
    3. test_low_accuracy_lowers_confidence — 50-70% → -0.10
    4. test_very_low_accuracy_demotes — <50% → CORRELATED
    5. test_demotion_requires_min_samples — <5 samples → no demote
    6. test_feedback_recorded — Inserted to st_causal_feedback
    7. test_compute_accuracy — Correct / total calculation
    8. test_staleness_check — Finds edges unused 90 days
    9. test_archive_stale_edges — Sets archival_status=ARCHIVED
    10. test_demotion_event_emitted — Event published

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pytest

from k0.modules.consolidation.algorithms.edge_demotion import (
    ACCURACY_ADEQUATE_THRESHOLD,
    ACCURACY_BOOST_THRESHOLD,
    ACCURACY_DEMOTE_THRESHOLD,
    BOOST_AMOUNT,
    LOWER_AMOUNT,
    MIN_FEEDBACK_SAMPLES,
    STALENESS_DAYS,
    CausalEdgeFeedbackProcessor,
    CausalEdgeStalenessChecker,
    DemotionAction,
    DemotionResult,
    EdgeStatus,
    generate_ulid,
    now_ms,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def processor() -> CausalEdgeFeedbackProcessor:
    """Feedback processor instance."""
    return CausalEdgeFeedbackProcessor()


@pytest.fixture
def staleness_checker() -> CausalEdgeStalenessChecker:
    """Staleness checker instance."""
    return CausalEdgeStalenessChecker()


@pytest.fixture
def base_time() -> int:
    """Base timestamp in milliseconds - use now() so it's within the feedback window."""
    return now_ms()


# =============================================================================
# Mock Database Connection
# =============================================================================


class MockDatabaseConnection:
    """Mock database connection for testing."""

    def __init__(self):
        self.edges: Dict[str, Dict] = {}
        self.feedback: List[Dict] = []
        self.queries_executed: List[str] = []

    def add_edge(
        self,
        edge_id: str,
        edge_type: str = "CAUSAL",
        causal_confidence: float = 0.80,
        space_id: str = "test_space",
        last_used_at: Optional[int] = None,
    ) -> None:
        """Add a mock edge."""
        self.edges[edge_id] = {
            "edge_id": edge_id,
            "edge_type": edge_type,
            "causal_confidence": causal_confidence,
            "space_id": space_id,
            "last_used_at": last_used_at,
            "archival_status": "ACTIVE",
        }

    def add_feedback(
        self,
        edge_id: str,
        signal_type: str,
        created_at: int,
    ) -> None:
        """Add a mock feedback record."""
        self.feedback.append(
            {
                "feedback_id": generate_ulid(),
                "edge_id": edge_id,
                "signal_type": signal_type,
                "created_at": created_at,
            }
        )

    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Fetch single row."""
        self.queries_executed.append(query)

        if "SELECT * FROM st_kg_edges" in query and len(args) >= 1:
            edge_id = args[0]
            return self.edges.get(edge_id)

        if "SELECT" in query and "COUNT" in query and "st_causal_feedback" in query:
            # Accuracy query
            edge_id = args[0]
            cutoff_time = args[1] if len(args) > 1 else 0

            relevant = [
                f
                for f in self.feedback
                if f["edge_id"] == edge_id and f["created_at"] >= cutoff_time
            ]

            correct = sum(1 for f in relevant if f["signal_type"] == "CAUSAL_PREDICTION_CONFIRMED")
            incorrect = sum(
                1
                for f in relevant
                if f["signal_type"] in ("CAUSAL_PREDICTION_WRONG", "USER_REJECTS_CAUSATION")
            )

            return {
                "correct": correct,
                "incorrect": incorrect,
                "total": len(relevant),
            }

        return None

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch single value."""
        self.queries_executed.append(query)

        if "COUNT(*) FROM st_causal_feedback" in query:
            edge_id = args[0]
            cutoff_time = args[1] if len(args) > 1 else 0

            return sum(
                1
                for f in self.feedback
                if f["edge_id"] == edge_id and f["created_at"] >= cutoff_time
            )

        return 0

    async def fetch(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows."""
        self.queries_executed.append(query)

        if "SELECT edge_id FROM st_kg_edges" in query and "last_used_at" in query:
            space_id = args[0]
            cutoff_time = args[1] if len(args) > 1 else 0

            return [
                {"edge_id": e["edge_id"]}
                for e in self.edges.values()
                if e.get("space_id") == space_id
                and e.get("edge_type") == "CAUSAL"
                and (e.get("last_used_at") is None or e.get("last_used_at", 0) < cutoff_time)
            ]

        return []

    async def execute(self, query: str, *args) -> str:
        """Execute query and return status."""
        self.queries_executed.append(query)

        if "INSERT INTO st_causal_feedback" in query:
            self.feedback.append(
                {
                    "feedback_id": args[0],
                    "edge_id": args[1],
                    "signal_type": args[2],
                    "source_system": args[3],
                    "created_at": args[7] if len(args) > 7 else now_ms(),
                }
            )
            return "INSERT 1"

        if "UPDATE st_kg_edges" in query:
            # Handle confidence update
            if "causal_confidence" in query and len(args) >= 3:
                edge_id = args[2]
                if edge_id in self.edges:
                    self.edges[edge_id]["causal_confidence"] = args[0]
                    self.edges[edge_id]["last_validated_at"] = args[1]
                return "UPDATE 1"

            # Handle demotion
            if "edge_type = 'CORRELATED'" in query and len(args) >= 3:
                edge_id = args[2]
                if edge_id in self.edges:
                    self.edges[edge_id]["edge_type"] = "CORRELATED"
                return "UPDATE 1"

            # Handle archival
            if "archival_status = 'ARCHIVED'" in query:
                if "ANY($2)" in query and len(args) >= 2:
                    edge_ids = args[1]
                    count = 0
                    for edge_id in edge_ids:
                        if edge_id in self.edges:
                            self.edges[edge_id]["archival_status"] = "ARCHIVED"
                            count += 1
                    return f"UPDATE {count}"
                elif len(args) >= 3:
                    edge_id = args[2]
                    if edge_id in self.edges:
                        self.edges[edge_id]["archival_status"] = "ARCHIVED"
                    return "UPDATE 1"

            # Handle last_validated_at only update
            if "last_validated_at" in query and len(args) >= 2:
                edge_id = args[1]
                if edge_id in self.edges:
                    self.edges[edge_id]["last_validated_at"] = args[0]
                return "UPDATE 1"

        return "OK"


# =============================================================================
# Test: Accuracy-Based Actions
# =============================================================================


class TestAccuracyBasedActions:
    """Tests for accuracy-based edge adjustments."""

    @pytest.mark.asyncio
    async def test_high_accuracy_boosts_confidence(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 1: >90% accuracy → +0.05 boost.
        """
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.80)

        # Add 10 confirmed, 0 wrong = 100% accuracy
        for i in range(10):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_CONFIRMED",
            outcome_details={"space_id": "test_space"},
            db_conn=db,
        )

        assert result is not None
        assert result.action == DemotionAction.BOOST
        assert result.old_confidence == 0.80
        assert math.isclose(result.new_confidence, 0.85, rel_tol=1e-9)  # 0.80 + 0.05
        assert result.accuracy is not None and result.accuracy > 0.90

    @pytest.mark.asyncio
    async def test_adequate_accuracy_maintains(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 2: 70-90% accuracy → no change.
        """
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.80)

        # Add 8 confirmed, 2 wrong = 80% accuracy
        for i in range(8):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)
        for i in range(2):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 10 + i)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_CONFIRMED",
            outcome_details={"space_id": "test_space"},
            db_conn=db,
        )

        assert result is not None
        assert result.action == DemotionAction.MAINTAIN
        assert result.old_confidence == 0.80
        assert result.new_confidence == 0.80  # No change
        assert 0.70 <= result.accuracy <= 0.90

    @pytest.mark.asyncio
    async def test_low_accuracy_lowers_confidence(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 3: 50-70% accuracy → -0.10 lower.
        """
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.80)

        # Add 6 confirmed, 4 wrong = 60% accuracy
        for i in range(6):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)
        for i in range(4):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 10 + i)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_WRONG",
            outcome_details={"space_id": "test_space"},
            db_conn=db,
        )

        assert result is not None
        assert result.action == DemotionAction.LOWER
        assert result.old_confidence == 0.80
        assert math.isclose(result.new_confidence, 0.70, rel_tol=1e-9)  # 0.80 - 0.10
        assert result.accuracy is not None and 0.50 <= result.accuracy < 0.70

    @pytest.mark.asyncio
    async def test_very_low_accuracy_demotes(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 4: <50% accuracy → CORRELATED.
        """
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.80)

        # Add 2 confirmed, 8 wrong = 20% accuracy (need 5+ samples for demotion)
        for i in range(2):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)
        for i in range(8):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 10 + i)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_WRONG",
            outcome_details={"space_id": "test_space"},
            db_conn=db,
        )

        assert result is not None
        assert result.action == DemotionAction.DEMOTE
        assert result.old_status == EdgeStatus.CAUSAL
        assert result.new_status == EdgeStatus.CORRELATED
        assert result.accuracy < 0.50

    @pytest.mark.asyncio
    async def test_demotion_requires_min_samples(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 5: <5 samples → no demote even if accuracy low.
        """
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.80)

        # Add only 3 samples (process_feedback adds 1 more = 4 total < 5)
        # 0 confirmed, 3 wrong = 0% accuracy but only 4 samples after process_feedback
        db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time)
        db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 1)
        db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 2)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_WRONG",
            outcome_details={"space_id": "test_space"},
            db_conn=db,
        )

        assert result is not None
        assert result.action == DemotionAction.MAINTAIN  # Not demote
        assert result.sample_count < MIN_FEEDBACK_SAMPLES
        assert "insufficient samples" in result.reason.lower()


# =============================================================================
# Test: Feedback Recording
# =============================================================================


class TestFeedbackRecording:
    """Tests for feedback recording."""

    @pytest.mark.asyncio
    async def test_feedback_recorded(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 6: Feedback inserted to st_causal_feedback.
        """
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.80)

        await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_CONFIRMED",
            outcome_details={
                "source": "K1",
                "prediction": {"predicted": "B follows A"},
                "actual": {"observed": "B followed A"},
                "space_id": "test_space",
            },
            db_conn=db,
        )

        # Verify feedback was recorded
        assert len(db.feedback) >= 1
        latest = db.feedback[-1]
        assert latest["edge_id"] == "edge_1"
        assert latest["signal_type"] == "CAUSAL_PREDICTION_CONFIRMED"
        assert latest["source_system"] == "K1"


# =============================================================================
# Test: Accuracy Computation
# =============================================================================


class TestAccuracyComputation:
    """Tests for accuracy computation."""

    @pytest.mark.asyncio
    async def test_compute_accuracy(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """
        Test Case 7: Accuracy = correct / total.
        """
        db = MockDatabaseConnection()

        # Add 7 confirmed, 3 wrong
        for i in range(7):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)
        for i in range(3):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 10 + i)

        accuracy = await processor.compute_accuracy("edge_1", days=30, db_conn=db)

        assert accuracy == 0.7  # 7 / 10

    @pytest.mark.asyncio
    async def test_compute_accuracy_no_feedback(
        self,
        processor: CausalEdgeFeedbackProcessor,
    ):
        """No feedback defaults to 1.0 accuracy."""
        db = MockDatabaseConnection()

        accuracy = await processor.compute_accuracy("edge_1", days=30, db_conn=db)

        assert accuracy == 1.0  # Default when no feedback

    @pytest.mark.asyncio
    async def test_compute_accuracy_user_rejects_counts_as_wrong(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """USER_REJECTS_CAUSATION counts as incorrect."""
        db = MockDatabaseConnection()

        # 5 confirmed, 5 user rejects = 50% accuracy
        for i in range(5):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)
        for i in range(5):
            db.add_feedback("edge_1", "USER_REJECTS_CAUSATION", base_time + 10 + i)

        accuracy = await processor.compute_accuracy("edge_1", days=30, db_conn=db)

        assert accuracy == 0.5


# =============================================================================
# Test: Staleness Checking
# =============================================================================


class TestStalenessChecking:
    """Tests for staleness checking and archival."""

    @pytest.mark.asyncio
    async def test_staleness_check(
        self,
        staleness_checker: CausalEdgeStalenessChecker,
        base_time: int,
    ):
        """
        Test Case 8: Finds edges unused 90 days.
        """
        db = MockDatabaseConnection()

        # Edge used recently - should not be stale
        db.add_edge("edge_recent", last_used_at=now_ms() - 10 * 86400000)  # 10 days ago

        # Edge never used - should be stale
        db.add_edge("edge_never", last_used_at=None)

        # Edge used 100 days ago - should be stale
        db.add_edge("edge_old", last_used_at=now_ms() - 100 * 86400000)

        stale = await staleness_checker.check_staleness("test_space", db)

        assert "edge_recent" not in stale
        assert "edge_never" in stale
        assert "edge_old" in stale

    @pytest.mark.asyncio
    async def test_archive_stale_edges(
        self,
        staleness_checker: CausalEdgeStalenessChecker,
    ):
        """
        Test Case 9: Sets archival_status=ARCHIVED.
        """
        db = MockDatabaseConnection()

        # Add stale edges
        db.add_edge("edge_1", last_used_at=None)
        db.add_edge("edge_2", last_used_at=None)

        count = await staleness_checker.archive_stale_edges("test_space", db)

        assert count == 2
        assert db.edges["edge_1"]["archival_status"] == "ARCHIVED"
        assert db.edges["edge_2"]["archival_status"] == "ARCHIVED"

    @pytest.mark.asyncio
    async def test_archive_no_stale_edges(
        self,
        staleness_checker: CausalEdgeStalenessChecker,
    ):
        """No stale edges returns 0."""
        db = MockDatabaseConnection()

        # Add recent edge
        db.add_edge("edge_recent", last_used_at=now_ms())

        count = await staleness_checker.archive_stale_edges("test_space", db)

        assert count == 0


# =============================================================================
# Test: Edge Not Found
# =============================================================================


class TestEdgeNotFound:
    """Tests for handling missing edges."""

    @pytest.mark.asyncio
    async def test_feedback_for_missing_edge(
        self,
        processor: CausalEdgeFeedbackProcessor,
    ):
        """Process feedback for non-existent edge returns None."""
        db = MockDatabaseConnection()

        result = await processor.process_feedback(
            edge_id="nonexistent_edge",
            feedback_signal="CAUSAL_PREDICTION_CONFIRMED",
            outcome_details={},
            db_conn=db,
        )

        assert result is None


# =============================================================================
# Test: Confidence Clamping
# =============================================================================


class TestConfidenceClamping:
    """Tests for confidence value clamping."""

    @pytest.mark.asyncio
    async def test_boost_clamped_to_max(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """Confidence cannot exceed 1.0."""
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.98)

        # 100% accuracy should boost but clamp
        for i in range(10):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_CONFIRMED",
            outcome_details={},
            db_conn=db,
        )

        assert result is not None
        assert result.new_confidence == 1.0  # Clamped to max

    @pytest.mark.asyncio
    async def test_lower_clamped_to_min(
        self,
        processor: CausalEdgeFeedbackProcessor,
        base_time: int,
    ):
        """Confidence cannot go below 0.0."""
        db = MockDatabaseConnection()
        db.add_edge("edge_1", causal_confidence=0.05)

        # 60% accuracy should lower but clamp
        for i in range(6):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_CONFIRMED", base_time + i)
        for i in range(4):
            db.add_feedback("edge_1", "CAUSAL_PREDICTION_WRONG", base_time + 10 + i)

        result = await processor.process_feedback(
            edge_id="edge_1",
            feedback_signal="CAUSAL_PREDICTION_WRONG",
            outcome_details={},
            db_conn=db,
        )

        assert result is not None
        assert result.new_confidence == 0.0  # Clamped to min


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_generate_ulid_uniqueness(self):
        """Generated ULIDs should be unique."""
        ulids = [generate_ulid() for _ in range(100)]
        assert len(set(ulids)) == 100

    def test_generate_ulid_format(self):
        """Generated ULID should be 26 characters."""
        ulid = generate_ulid()
        assert len(ulid) == 26

    def test_now_ms(self):
        """now_ms should return current time in milliseconds."""
        import time

        before = int(time.time() * 1000)
        result = now_ms()
        after = int(time.time() * 1000)

        assert before <= result <= after


# =============================================================================
# Test: Configuration Constants
# =============================================================================


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_accuracy_thresholds(self):
        """Verify threshold values from spec."""
        assert ACCURACY_BOOST_THRESHOLD == 0.90
        assert ACCURACY_ADEQUATE_THRESHOLD == 0.70
        assert ACCURACY_DEMOTE_THRESHOLD == 0.50

    def test_adjustment_amounts(self):
        """Verify adjustment amounts from spec."""
        assert BOOST_AMOUNT == 0.05
        assert LOWER_AMOUNT == 0.10

    def test_staleness_days(self):
        """Verify staleness window from spec."""
        assert STALENESS_DAYS == 90
        assert MIN_FEEDBACK_SAMPLES == 5


# =============================================================================
# Test: DemotionResult Dataclass
# =============================================================================


class TestDemotionResult:
    """Tests for DemotionResult dataclass."""

    def test_demotion_result_fields(self):
        """DemotionResult has all expected fields."""
        result = DemotionResult(
            edge_id="edge_1",
            action=DemotionAction.BOOST,
            old_status=EdgeStatus.CAUSAL,
            new_status=EdgeStatus.CAUSAL,
            old_confidence=0.80,
            new_confidence=0.85,
            reason="High accuracy",
            accuracy=0.95,
            sample_count=20,
        )

        assert result.edge_id == "edge_1"
        assert result.action == DemotionAction.BOOST
        assert result.old_status == EdgeStatus.CAUSAL
        assert result.new_status == EdgeStatus.CAUSAL
        assert result.old_confidence == 0.80
        assert result.new_confidence == 0.85
        assert result.reason == "High accuracy"
        assert result.accuracy == 0.95
        assert result.sample_count == 20


# =============================================================================
# Test: EdgeStatus Enum
# =============================================================================


class TestEdgeStatus:
    """Tests for EdgeStatus enum."""

    def test_edge_status_values(self):
        """EdgeStatus has all expected values."""
        assert EdgeStatus.CAUSAL.value == "CAUSAL"
        assert EdgeStatus.CORRELATED.value == "CORRELATED"
        assert EdgeStatus.CONTEXT_DEPENDENT.value == "CONTEXT_DEPENDENT"
        assert EdgeStatus.ARCHIVED.value == "ARCHIVED"


# =============================================================================
# Test: DemotionAction Enum
# =============================================================================


class TestDemotionAction:
    """Tests for DemotionAction enum."""

    def test_demotion_action_values(self):
        """DemotionAction has all expected values."""
        assert DemotionAction.BOOST.value == "boost"
        assert DemotionAction.MAINTAIN.value == "maintain"
        assert DemotionAction.LOWER.value == "lower"
        assert DemotionAction.DEMOTE.value == "demote"
        assert DemotionAction.ARCHIVE.value == "archive"
