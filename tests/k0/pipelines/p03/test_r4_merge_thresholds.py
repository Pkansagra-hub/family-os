"""
R4 Merge Threshold Learner Tests — Epic 4.4.6

Spec Reference: M4_EXECUTION.md, Issue 4.4.6

Tests for AdaptiveMergeThresholds:
1. test_family_member_high_threshold — Default 0.90
2. test_concept_low_threshold — Default 0.65
3. test_should_merge_above_threshold — 0.92 PERSON → should_merge=True
4. test_should_merge_below_threshold — 0.80 PERSON → should_merge=False
5. test_merge_rejected_raises_threshold — +0.02 adjustment
6. test_split_request_raises_more — +0.05 adjustment
7. test_missed_merge_lowers_threshold — -0.02 adjustment
8. test_threshold_clamped_max — Cannot exceed upper bound
9. test_threshold_clamped_min — Cannot go below lower bound
10. test_unknown_type_default — Unknown uses 0.75
11. test_persist_threshold — Upsert to st_learned_weights
12. test_load_from_database — Loads overrides correctly
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.merge_threshold_learner import (
    AdaptiveMergeThresholds,
    ThresholdBounds,
    get_adaptive_merge_thresholds,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def learner() -> AdaptiveMergeThresholds:
    """Create fresh learner instance."""
    return AdaptiveMergeThresholds()


@pytest.fixture
def learner_with_overrides() -> AdaptiveMergeThresholds:
    """Create learner with custom thresholds."""
    return AdaptiveMergeThresholds(learned_thresholds={"PERSON": 0.88, "CONCEPT": 0.70})


@pytest.fixture
def mock_db_conn() -> AsyncMock:
    """Create mock database connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    return conn


# =============================================================================
# Test Default Thresholds
# =============================================================================


class TestDefaultThresholds:
    """Tests for default threshold values per entity type."""

    def test_family_member_high_threshold(self, learner: AdaptiveMergeThresholds):
        """FAMILY_MEMBER should have highest threshold (0.90)."""
        threshold = learner.get_threshold("FAMILY_MEMBER")
        assert threshold == 0.90

    def test_person_threshold(self, learner: AdaptiveMergeThresholds):
        """PERSON should have threshold of 0.85."""
        threshold = learner.get_threshold("PERSON")
        assert threshold == 0.85

    def test_concept_low_threshold(self, learner: AdaptiveMergeThresholds):
        """CONCEPT should have lowest threshold (0.65)."""
        threshold = learner.get_threshold("CONCEPT")
        assert threshold == 0.65

    def test_place_threshold(self, learner: AdaptiveMergeThresholds):
        """PLACE should have threshold of 0.75."""
        threshold = learner.get_threshold("PLACE")
        assert threshold == 0.75

    def test_location_same_as_place(self, learner: AdaptiveMergeThresholds):
        """LOCATION should have same threshold as PLACE."""
        assert learner.get_threshold("LOCATION") == learner.get_threshold("PLACE")

    def test_organization_threshold(self, learner: AdaptiveMergeThresholds):
        """ORGANIZATION should have threshold of 0.80."""
        threshold = learner.get_threshold("ORGANIZATION")
        assert threshold == 0.80

    def test_thing_object_same(self, learner: AdaptiveMergeThresholds):
        """THING and OBJECT should have same threshold (0.70)."""
        assert learner.get_threshold("THING") == 0.70
        assert learner.get_threshold("OBJECT") == 0.70

    def test_event_threshold(self, learner: AdaptiveMergeThresholds):
        """EVENT should have threshold of 0.75."""
        threshold = learner.get_threshold("EVENT")
        assert threshold == 0.75

    def test_temporal_threshold(self, learner: AdaptiveMergeThresholds):
        """TEMPORAL should have threshold of 0.80."""
        threshold = learner.get_threshold("TEMPORAL")
        assert threshold == 0.80

    def test_unknown_type_default(self, learner: AdaptiveMergeThresholds):
        """Unknown entity type should use default threshold (0.75)."""
        threshold = learner.get_threshold("UNKNOWN_TYPE")
        assert threshold == 0.75

    def test_another_unknown_type(self, learner: AdaptiveMergeThresholds):
        """Another unknown type also uses default."""
        threshold = learner.get_threshold("MADE_UP_ENTITY")
        assert threshold == 0.75


# =============================================================================
# Test should_merge() Decision
# =============================================================================


class TestShouldMerge:
    """Tests for merge decision based on similarity score."""

    def test_should_merge_above_threshold(self, learner: AdaptiveMergeThresholds):
        """Score above threshold → should_merge=True."""
        decision = learner.should_merge("PERSON", 0.92)
        assert decision.should_merge is True
        assert decision.entity_type == "PERSON"
        assert decision.similarity_score == 0.92
        assert decision.threshold == 0.85

    def test_should_merge_below_threshold(self, learner: AdaptiveMergeThresholds):
        """Score below threshold → should_merge=False."""
        decision = learner.should_merge("PERSON", 0.80)
        assert decision.should_merge is False
        assert decision.similarity_score == 0.80

    def test_should_merge_at_exact_threshold(self, learner: AdaptiveMergeThresholds):
        """Score exactly at threshold → should_merge=True (>=)."""
        decision = learner.should_merge("PERSON", 0.85)
        assert decision.should_merge is True

    def test_should_merge_family_member_strict(self, learner: AdaptiveMergeThresholds):
        """FAMILY_MEMBER requires 0.90, so 0.89 should fail."""
        decision = learner.should_merge("FAMILY_MEMBER", 0.89)
        assert decision.should_merge is False

        decision = learner.should_merge("FAMILY_MEMBER", 0.90)
        assert decision.should_merge is True

    def test_should_merge_concept_lenient(self, learner: AdaptiveMergeThresholds):
        """CONCEPT has low threshold (0.65), so 0.68 should pass."""
        decision = learner.should_merge("CONCEPT", 0.68)
        assert decision.should_merge is True

    def test_margin_calculation(self, learner: AdaptiveMergeThresholds):
        """Score - threshold margin should be calculable."""
        decision = learner.should_merge("PERSON", 0.92)
        expected_margin = 0.92 - 0.85
        # Margin is calculated as score - threshold
        actual_margin = decision.similarity_score - decision.threshold
        assert abs(actual_margin - expected_margin) < 0.0001


# =============================================================================
# Test Threshold Adjustment
# =============================================================================


class TestThresholdAdjustment:
    """Tests for learning from feedback signals."""

    def test_merge_rejected_raises_threshold(self, learner: AdaptiveMergeThresholds):
        """MERGE_REJECTED should raise threshold by 0.02."""
        old_threshold = learner.get_threshold("PERSON")
        adjustment = learner.adjust_threshold("PERSON", "MERGE_REJECTED")

        assert adjustment.old_threshold == old_threshold
        assert adjustment.new_threshold == old_threshold + 0.02
        assert adjustment.adjustment == 0.02
        assert adjustment.reason == "MERGE_REJECTED"

    def test_split_request_raises_more(self, learner: AdaptiveMergeThresholds):
        """SPLIT_REQUEST should raise threshold by 0.05."""
        old_threshold = learner.get_threshold("PERSON")
        adjustment = learner.adjust_threshold("PERSON", "SPLIT_REQUEST")

        assert adjustment.new_threshold == old_threshold + 0.05
        assert adjustment.adjustment == 0.05

    def test_missed_merge_lowers_threshold(self, learner: AdaptiveMergeThresholds):
        """MISSED_MERGE should lower threshold by 0.02."""
        old_threshold = learner.get_threshold("PERSON")
        adjustment = learner.adjust_threshold("PERSON", "MISSED_MERGE")

        assert adjustment.new_threshold == old_threshold - 0.02
        assert adjustment.adjustment == -0.02

    def test_merge_confirmed_no_change(self, learner: AdaptiveMergeThresholds):
        """MERGE_CONFIRMED should not change threshold."""
        old_threshold = learner.get_threshold("PERSON")
        adjustment = learner.adjust_threshold("PERSON", "MERGE_CONFIRMED")

        assert adjustment.new_threshold == old_threshold
        assert adjustment.adjustment == 0.0

    def test_threshold_clamped_max(self, learner: AdaptiveMergeThresholds):
        """Threshold cannot exceed upper bound."""
        # PERSON has bounds (0.70, 0.95, 0.85)
        # Apply many SPLIT_REQUEST signals to try to exceed max
        for _ in range(10):
            learner.adjust_threshold("PERSON", "SPLIT_REQUEST")

        threshold = learner.get_threshold("PERSON")
        assert threshold <= 0.95  # Should not exceed upper bound

    def test_threshold_clamped_min(self, learner: AdaptiveMergeThresholds):
        """Threshold cannot go below lower bound."""
        # PERSON has bounds (0.70, 0.95, 0.85)
        # Apply many MISSED_MERGE signals to try to go below min
        for _ in range(20):
            learner.adjust_threshold("PERSON", "MISSED_MERGE")

        threshold = learner.get_threshold("PERSON")
        assert threshold >= 0.70  # Should not go below lower bound

    def test_string_feedback_signal(self, learner: AdaptiveMergeThresholds):
        """Should accept string feedback signal (for JSON deserialization)."""
        old_threshold = learner.get_threshold("PERSON")
        adjustment = learner.adjust_threshold("PERSON", "MERGE_REJECTED")

        assert adjustment.new_threshold == old_threshold + 0.02

    def test_adjustment_updates_internal_state(self, learner: AdaptiveMergeThresholds):
        """After adjustment, get_threshold should return new value."""
        learner.adjust_threshold("PERSON", "SPLIT_REQUEST")
        new_threshold = learner.get_threshold("PERSON")
        assert new_threshold == 0.90  # 0.85 + 0.05


# =============================================================================
# Test Learned Overrides
# =============================================================================


class TestLearnedOverrides:
    """Tests for loading pre-learned thresholds."""

    def test_override_applied(self, learner_with_overrides: AdaptiveMergeThresholds):
        """Pre-loaded overrides should be applied."""
        assert learner_with_overrides.get_threshold("PERSON") == 0.88
        assert learner_with_overrides.get_threshold("CONCEPT") == 0.70

    def test_non_overridden_uses_default(self, learner_with_overrides: AdaptiveMergeThresholds):
        """Non-overridden types should use defaults."""
        # FAMILY_MEMBER not overridden, should be default
        assert learner_with_overrides.get_threshold("FAMILY_MEMBER") == 0.90


# =============================================================================
# Test Persistence
# =============================================================================


class TestPersistence:
    """Tests for database persistence."""

    @pytest.mark.asyncio
    async def test_persist_threshold(
        self, learner: AdaptiveMergeThresholds, mock_db_conn: AsyncMock
    ):
        """persist_threshold should upsert to st_learned_weights."""
        # Adjust threshold first so there's something to persist
        learner.adjust_threshold("PERSON", "SPLIT_REQUEST")

        result = await learner.persist_threshold("PERSON", mock_db_conn, "space_123")

        assert result is True
        mock_db_conn.execute.assert_called_once()

        # Verify the SQL contains expected elements
        call_args = mock_db_conn.execute.call_args
        sql = call_args[0][0]
        assert "st_learned_weights" in sql
        assert "INSERT" in sql or "UPSERT" in sql.upper() or "ON CONFLICT" in sql

    @pytest.mark.asyncio
    async def test_persist_threshold_no_value(
        self, learner: AdaptiveMergeThresholds, mock_db_conn: AsyncMock
    ):
        """persist_threshold should return False if no override exists."""
        # Create learner without any overrides for UNKNOWN_TYPE
        result = await learner.persist_threshold("COMPLETELY_NEW_TYPE", mock_db_conn, "space_123")

        # Should return False as there's no learned override
        # (only the default, which isn't stored as override)
        assert result is False

    @pytest.mark.asyncio
    async def test_load_from_database(self, mock_db_conn: AsyncMock):
        """load_from_database should create instance with db values."""
        # Mock database to return some learned thresholds
        mock_db_conn.fetch.return_value = [
            {"scope_id": "PERSON", "current_value": "0.88"},
            {"scope_id": "CONCEPT", "current_value": "0.68"},
        ]

        learner = await AdaptiveMergeThresholds.load_from_database(mock_db_conn, "space_123")

        assert learner.get_threshold("PERSON") == 0.88
        assert learner.get_threshold("CONCEPT") == 0.68
        # Non-overridden should use default
        assert learner.get_threshold("FAMILY_MEMBER") == 0.90


# =============================================================================
# Test Factory Function
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_get_adaptive_merge_thresholds(self):
        """Factory should return configured instance."""
        learner = get_adaptive_merge_thresholds()
        assert isinstance(learner, AdaptiveMergeThresholds)
        # Should have default thresholds
        assert learner.get_threshold("PERSON") == 0.85


# =============================================================================
# Test ThresholdBounds Dataclass
# =============================================================================


class TestThresholdBoundsDataclass:
    """Tests for ThresholdBounds dataclass."""

    def test_threshold_bounds_creation(self):
        """ThresholdBounds should store min, max, default."""
        bounds = ThresholdBounds(min_value=0.60, max_value=0.95, default=0.80)
        assert bounds.min_value == 0.60
        assert bounds.max_value == 0.95
        assert bounds.default == 0.80

    def test_threshold_bounds_default_thresholds_structure(self):
        """DEFAULT_THRESHOLD_BOUNDS should have correct structure."""
        # Import module-level constant
        from k0.modules.consolidation.algorithms.merge_threshold_learner import (
            DEFAULT_THRESHOLD_BOUNDS,
        )

        # All known entity types should have bounds
        expected_types = [
            "FAMILY_MEMBER",
            "PERSON",
            "PLACE",
            "LOCATION",
            "ORGANIZATION",
            "THING",
            "OBJECT",
            "CONCEPT",
            "EVENT",
            "TEMPORAL",
        ]
        for entity_type in expected_types:
            assert entity_type in DEFAULT_THRESHOLD_BOUNDS
            b = DEFAULT_THRESHOLD_BOUNDS[entity_type]
            assert isinstance(b, ThresholdBounds)
            assert b.min_value <= b.default <= b.max_value


# =============================================================================
# Test MergeDecision Dataclass
# =============================================================================


class TestMergeDecisionDataclass:
    """Tests for MergeDecision dataclass."""

    def test_merge_decision_to_dict(self, learner: AdaptiveMergeThresholds):
        """MergeDecision should be serializable."""
        decision = learner.should_merge("PERSON", 0.92)
        d = decision.to_dict()

        assert d["should_merge"] is True
        assert d["entity_type"] == "PERSON"
        # similarity_score is rounded to 4 decimal places
        assert abs(d["similarity_score"] - 0.92) < 0.0001
        assert "threshold" in d


# =============================================================================
# Test Metrics
# =============================================================================


class TestMetrics:
    """Tests for metrics tracking."""

    def test_metrics_initialized(self, learner: AdaptiveMergeThresholds):
        """Metrics should be initialized to zero."""
        metrics = learner.metrics
        assert metrics.total_decisions == 0
        assert metrics.merge_count == 0
        assert metrics.reject_count == 0

    def test_metrics_updated_on_decision(self, learner: AdaptiveMergeThresholds):
        """Metrics should be updated after decisions."""
        learner.should_merge("PERSON", 0.92)  # Should merge
        learner.should_merge("PERSON", 0.75)  # Should not merge

        metrics = learner.metrics
        assert metrics.total_decisions == 2
        assert metrics.merge_count == 1
        assert metrics.reject_count == 1

    def test_adjustment_count(self, learner: AdaptiveMergeThresholds):
        """Adjustment count should track feedback processing."""
        learner.adjust_threshold("PERSON", "MERGE_REJECTED")
        learner.adjust_threshold("PERSON", "SPLIT_REQUEST")

        metrics = learner.metrics
        # Both are positive adjustments (raise threshold)
        assert metrics.adjustments_up == 2
