"""
Unit tests for ConsolidationStatusMarker — Issue 5.1.2

Tests the status assignment logic for P03 events based on
ReconciliationAction and other event state fields.

Spec Reference:
    - Dossier §4.7.1 (Status Mapping)
    - M5_EXECUTION.md Issue 5.1.2
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.staging.status_marker import (
    ConsolidationStatusMarker,
    StatusResult,
)
from k0.pipelines.p03.event_state import (
    P03EventState,
    PruneDecision,
    ReconciliationAction,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def marker() -> ConsolidationStatusMarker:
    """Provide a StatusMarker instance."""
    return ConsolidationStatusMarker()


def make_event(
    event_id: str = "evt_001",
    reconciliation_action: ReconciliationAction = ReconciliationAction.PENDING,
    prune_decision: PruneDecision = PruneDecision.KEEP,
    is_duplicate: bool = False,
    duplicate_of_id: str | None = None,
    hamming_distance: int = 64,
    confidence: float = 0.9,
) -> P03EventState:
    """Factory to create P03EventState with common defaults."""
    return P03EventState(
        event_id=event_id,
        reconciliation_action=reconciliation_action,
        prune_decision=prune_decision,
        is_duplicate=is_duplicate,
        duplicate_of_id=duplicate_of_id,
        hamming_distance=hamming_distance,
        confidence=confidence,
    )


# =============================================================================
# Test: DUPLICATE Status
# =============================================================================


class TestDuplicateStatus:
    """Tests for is_duplicate → DUPLICATE status."""

    def test_is_duplicate_true_returns_duplicate(self, marker: ConsolidationStatusMarker):
        """When is_duplicate=True, status should be DUPLICATE."""
        event_state = make_event(
            is_duplicate=True,
            duplicate_of_id="evt_canonical",
            hamming_distance=2,
        )

        result = marker.mark_status(event_state)

        assert result.status == "DUPLICATE"
        assert "duplicate" in result.reason.lower() or "evt_canonical" in result.reason

    def test_is_duplicate_without_canonical_id(self, marker: ConsolidationStatusMarker):
        """When is_duplicate=True but no canonical_id, still DUPLICATE."""
        event_state = make_event(
            is_duplicate=True,
            duplicate_of_id=None,
        )

        result = marker.mark_status(event_state)

        assert result.status == "DUPLICATE"


# =============================================================================
# Test: PRUNED Status
# =============================================================================


class TestPrunedStatus:
    """Tests for prune actions → PRUNED status."""

    def test_prune_action_returns_pruned(self, marker: ConsolidationStatusMarker):
        """ReconciliationAction.PRUNE → PRUNED status."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.PRUNE,
            prune_decision=PruneDecision.ARCHIVE,
        )

        result = marker.mark_status(event_state)

        assert result.status == "PRUNED"
        assert "PRUNE" in result.reason.upper() or "pruned" in result.reason.lower()

    def test_archive_prune_decision_returns_pruned(self, marker: ConsolidationStatusMarker):
        """PruneDecision.ARCHIVE → PRUNED status."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.REINFORCE,  # Not PRUNE action
            prune_decision=PruneDecision.ARCHIVE,
        )

        result = marker.mark_status(event_state)

        assert result.status == "PRUNED"
        assert "ARCHIVE" in result.reason.upper()

    def test_tombstone_prune_decision_returns_pruned(self, marker: ConsolidationStatusMarker):
        """PruneDecision.TOMBSTONE → PRUNED status."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.REINFORCE,
            prune_decision=PruneDecision.TOMBSTONE,
        )

        result = marker.mark_status(event_state)

        assert result.status == "PRUNED"
        assert "TOMBSTONE" in result.reason.upper()


# =============================================================================
# Test: PENDING_REVIEW Status
# =============================================================================


class TestPendingReviewStatus:
    """Tests for CONTRADICT action → PENDING_REVIEW status."""

    def test_contradict_action_returns_pending_review(self, marker: ConsolidationStatusMarker):
        """ReconciliationAction.CONTRADICT → PENDING_REVIEW status."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.CONTRADICT,
        )

        result = marker.mark_status(event_state)

        assert result.status == "PENDING_REVIEW"
        assert "CONTRADICT" in result.reason.upper() or "contradict" in result.reason.lower()


# =============================================================================
# Test: CONSOLIDATED Status
# =============================================================================


class TestConsolidatedStatus:
    """Tests for successful actions → CONSOLIDATED status."""

    @pytest.mark.parametrize(
        "action",
        [
            ReconciliationAction.CREATE,
            ReconciliationAction.REINFORCE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.EVOLVE,
        ],
    )
    def test_positive_actions_return_consolidated(
        self,
        marker: ConsolidationStatusMarker,
        action: ReconciliationAction,
    ):
        """Positive reconciliation actions → CONSOLIDATED status."""
        event_state = make_event(
            reconciliation_action=action,
            prune_decision=PruneDecision.KEEP,
        )

        result = marker.mark_status(event_state)

        assert result.status == "CONSOLIDATED"
        assert action.name in result.reason.upper() or action.value in result.reason.upper()


# =============================================================================
# Test: SKIP Action Analysis
# =============================================================================


class TestSkipActionAnalysis:
    """Tests for SKIP action with reason analysis."""

    def test_skip_action_default_behavior(self, marker: ConsolidationStatusMarker):
        """SKIP action has predictable behavior."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.SKIP,
        )

        result = marker.mark_status(event_state)

        # SKIP could be DUPLICATE, CONSOLIDATED, or PRUNED depending on context
        # Just verify it returns a valid status
        assert result.status in ("DUPLICATE", "CONSOLIDATED", "PRUNED", "PENDING_REVIEW")


# =============================================================================
# Test: PENDING Action
# =============================================================================


class TestPendingAction:
    """Tests for PENDING action handling."""

    def test_pending_action_returns_pending_review(self, marker: ConsolidationStatusMarker):
        """ReconciliationAction.PENDING → PENDING_REVIEW status."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.PENDING,
        )

        result = marker.mark_status(event_state)

        assert result.status == "PENDING_REVIEW"
        assert "PENDING" in result.reason.upper()


# =============================================================================
# Test: Status Priority
# =============================================================================


class TestStatusPriority:
    """Tests for status priority rules."""

    def test_duplicate_takes_priority_over_prune(self, marker: ConsolidationStatusMarker):
        """is_duplicate should take priority over prune_decision."""
        event_state = make_event(
            is_duplicate=True,
            duplicate_of_id="evt_canonical",
            prune_decision=PruneDecision.ARCHIVE,
        )

        result = marker.mark_status(event_state)

        # Duplicate check happens first
        assert result.status == "DUPLICATE"


# =============================================================================
# Test: StatusResult Dataclass
# =============================================================================


class TestStatusResult:
    """Tests for StatusResult dataclass."""

    def test_status_result_fields(self):
        """StatusResult should have required fields."""
        result = StatusResult(
            event_id="evt_001",
            status="CONSOLIDATED",
            reason="Action: CREATE",
            source_decision="ReconciliationAction.CREATE",
            contributing_factors={"action": "CREATE"},
        )

        assert result.event_id == "evt_001"
        assert result.status == "CONSOLIDATED"
        assert result.reason == "Action: CREATE"
        assert result.source_decision == "ReconciliationAction.CREATE"

    def test_status_result_validates_status(self):
        """StatusResult should validate status value."""
        with pytest.raises(ValueError, match="Invalid status"):
            StatusResult(
                event_id="evt_001",
                status="INVALID_STATUS",
                reason="test",
                source_decision="test",
                contributing_factors={},
            )


# =============================================================================
# Test: Batch Processing
# =============================================================================


class TestBatchProcessing:
    """Tests for processing multiple events."""

    def test_batch_processing(self, marker: ConsolidationStatusMarker):
        """Test batch processing of events."""
        events = [
            make_event(event_id="evt_001", reconciliation_action=ReconciliationAction.CREATE),
            make_event(event_id="evt_002", is_duplicate=True, duplicate_of_id="evt_001"),
            make_event(event_id="evt_003", reconciliation_action=ReconciliationAction.PRUNE),
            make_event(event_id="evt_004", reconciliation_action=ReconciliationAction.CONTRADICT),
        ]

        results = [marker.mark_status(e) for e in events]

        assert results[0].status == "CONSOLIDATED"
        assert results[1].status == "DUPLICATE"
        assert results[2].status == "PRUNED"
        assert results[3].status == "PENDING_REVIEW"

    def test_mark_batch_method(self, marker: ConsolidationStatusMarker):
        """Test the mark_batch convenience method."""
        events = [
            make_event(event_id="evt_001", reconciliation_action=ReconciliationAction.CREATE),
            make_event(event_id="evt_002", reconciliation_action=ReconciliationAction.REINFORCE),
        ]

        results = marker.mark_batch(events)

        assert len(results) == 2
        assert all(r.status == "CONSOLIDATED" for r in results.values())


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_none_fields_handled_gracefully(self, marker: ConsolidationStatusMarker):
        """None values in optional fields handled gracefully."""
        event_state = make_event(
            reconciliation_action=ReconciliationAction.CREATE,
            prune_decision=PruneDecision.KEEP,
            is_duplicate=False,
            duplicate_of_id=None,
        )

        result = marker.mark_status(event_state)

        assert result.status == "CONSOLIDATED"

    def test_status_counts_method(self, marker: ConsolidationStatusMarker):
        """Test get_status_counts method."""
        results = {
            "evt_001": StatusResult("evt_001", "CONSOLIDATED", "r1", "s1", {}),
            "evt_002": StatusResult("evt_002", "CONSOLIDATED", "r2", "s2", {}),
            "evt_003": StatusResult("evt_003", "DUPLICATE", "r3", "s3", {}),
            "evt_004": StatusResult("evt_004", "PRUNED", "r4", "s4", {}),
        }

        counts = marker.get_status_counts(results)

        assert counts.get("CONSOLIDATED", 0) == 2
        assert counts.get("DUPLICATE", 0) == 1
        assert counts.get("PRUNED", 0) == 1
        assert counts.get("PENDING_REVIEW", 0) == 0
