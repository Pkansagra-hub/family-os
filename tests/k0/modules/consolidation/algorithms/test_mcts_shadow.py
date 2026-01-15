"""
Unit tests for MCTS Shadow Validation (Issue 8.1.14).

These tests validate:
- ShadowDecisionRecord creation and validation
- ShadowOutcomeTracker operations
- CycleShadowTracker for per-cycle tracking
- ShadowValidationStats calculations
- Promotion logic with thresholds

References:
- M8_EXECUTION.md Issue 8.1.14: R5 Shadow Validation
- Dossier §4.6.0: MVP Strategy (shadow mode, promotion thresholds)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.mcts_shadow import (
    EVALUATION_WINDOW_MS,
    P03_R5_SHADOW_AGREEMENT_THRESHOLD,
    P03_R5_SHADOW_BETTER_THRESHOLD,
    P03_R5_SHADOW_DIFF_THRESHOLD,
    P03_R5_SHADOW_VALIDATION_WINDOW_DAYS,
    CycleShadowTracker,
    PromotionAnalysis,
    PromotionRecommendation,
    ShadowDecisionRecord,
    ShadowDecisionType,
    ShadowOutcomeTracker,
    ShadowValidationStats,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_shadow_record() -> ShadowDecisionRecord:
    """Create a sample shadow decision record."""
    return ShadowDecisionRecord.create(
        cycle_id="01JFXYZ123456789ABCDEFGHJK",
        decision_type=ShadowDecisionType.MERGE,
        heuristic_choice="merge_accept",
        mcts_choice="merge_reject",
        context={"entity_id": "ent_001", "confidence": 0.85},
    )


@pytest.fixture
def sample_agreement_record() -> ShadowDecisionRecord:
    """Create a record where heuristic and MCTS agree."""
    return ShadowDecisionRecord.create(
        cycle_id="01JFXYZ123456789ABCDEFGHJK",
        decision_type=ShadowDecisionType.CAUSAL,
        heuristic_choice="create_edge",
        mcts_choice="create_edge",  # Same choice
        context={"edge_type": "causal"},
    )


@pytest.fixture
def mock_db_connection() -> AsyncMock:
    """Create a mock database connection."""
    mock = AsyncMock()
    mock.execute = AsyncMock(return_value=None)
    mock.execute_many = AsyncMock(return_value=None)
    mock.fetch_one = AsyncMock(return_value=None)
    mock.fetch_all = AsyncMock(return_value=[])
    return mock


# =============================================================================
# TEST: ShadowDecisionRecord
# =============================================================================


class TestShadowDecisionRecord:
    """Tests for ShadowDecisionRecord dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating record with factory method."""
        record = ShadowDecisionRecord.create(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            decision_type=ShadowDecisionType.MERGE,
            heuristic_choice="accept",
            mcts_choice="reject",
        )

        assert record.cycle_id == "01JFXYZ123456789ABCDEFGHJK"
        assert record.decision_type == "merge"
        assert record.heuristic_choice == "accept"
        assert record.mcts_choice == "reject"
        assert record.choices_differ is True
        assert record.applied_choice == "accept"  # Always heuristic
        assert record.decision_id  # Auto-generated ULID
        assert record.created_at_ms > 0

    def test_create_with_agreement(self, sample_agreement_record: ShadowDecisionRecord) -> None:
        """Test creating record where choices agree."""
        assert sample_agreement_record.choices_differ is False
        assert sample_agreement_record.heuristic_choice == sample_agreement_record.mcts_choice

    def test_create_with_disagreement(self, sample_shadow_record: ShadowDecisionRecord) -> None:
        """Test creating record where choices disagree."""
        assert sample_shadow_record.choices_differ is True
        assert sample_shadow_record.heuristic_choice != sample_shadow_record.mcts_choice

    def test_applied_choice_always_heuristic(self) -> None:
        """Test that applied_choice is always the heuristic choice."""
        record = ShadowDecisionRecord.create(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            decision_type=ShadowDecisionType.CLUSTER,
            heuristic_choice="cluster_a",
            mcts_choice="cluster_b",
        )
        assert record.applied_choice == "cluster_a"

    def test_to_db_dict(self, sample_shadow_record: ShadowDecisionRecord) -> None:
        """Test conversion to database dictionary."""
        db_dict = sample_shadow_record.to_db_dict()

        assert db_dict["decision_id"] == sample_shadow_record.decision_id
        assert db_dict["cycle_id"] == sample_shadow_record.cycle_id
        assert db_dict["decision_type"] == "merge"
        assert db_dict["heuristic_choice"] == "merge_accept"
        assert db_dict["mcts_choice"] == "merge_reject"
        assert db_dict["choices_differ"] is True
        assert db_dict["applied_choice"] == "merge_accept"
        assert "created_at" in db_dict
        assert "context_json" in db_dict

    def test_with_evaluation(self, sample_shadow_record: ShadowDecisionRecord) -> None:
        """Test creating record with evaluation results."""
        evaluated = sample_shadow_record.with_evaluation(
            outcome_heuristic=0.7,
            outcome_mcts=0.9,
            mcts_better=True,
        )

        assert evaluated.outcome_heuristic == 0.7
        assert evaluated.outcome_mcts == 0.9
        assert evaluated.mcts_better is True
        assert evaluated.evaluated_at_ms is not None
        assert evaluated.evaluated_at_ms > 0
        # Original fields preserved
        assert evaluated.decision_id == sample_shadow_record.decision_id
        assert evaluated.cycle_id == sample_shadow_record.cycle_id

    def test_all_decision_types(self) -> None:
        """Test all decision type enum values."""
        for dt in ShadowDecisionType:
            record = ShadowDecisionRecord.create(
                cycle_id="01JFXYZ123456789ABCDEFGHJK",
                decision_type=dt,
                heuristic_choice="choice_a",
                mcts_choice="choice_b",
            )
            assert record.decision_type == dt.value


# =============================================================================
# TEST: ShadowValidationStats
# =============================================================================


class TestShadowValidationStats:
    """Tests for ShadowValidationStats calculations."""

    def test_empty_stats(self) -> None:
        """Test empty stats calculations."""
        stats = ShadowValidationStats()

        assert stats.total_decisions == 0
        assert stats.agreement_rate == 0.0
        assert stats.disagreement_rate == 0.0
        assert stats.mcts_better_rate == 0.0
        assert stats.has_sufficient_data is False

    def test_agreement_rate_calculation(self) -> None:
        """Test agreement rate calculation."""
        stats = ShadowValidationStats(
            total_decisions=100,
            agreements=80,
            disagreements=20,
        )

        assert stats.agreement_rate == 0.8
        assert stats.disagreement_rate == 0.2

    def test_mcts_better_rate_calculation(self) -> None:
        """Test MCTS better rate calculation."""
        stats = ShadowValidationStats(
            total_decisions=100,
            agreements=50,
            disagreements=50,
            mcts_better_count=30,
            heuristic_better_count=15,
            equal_count=5,
        )

        # 30 / (30 + 15 + 5) = 30/50 = 0.6
        assert stats.mcts_better_rate == 0.6

    def test_mcts_better_rate_no_evaluated(self) -> None:
        """Test MCTS better rate when nothing evaluated."""
        stats = ShadowValidationStats(
            total_decisions=100,
            agreements=50,
            disagreements=50,
            mcts_better_count=0,
            heuristic_better_count=0,
            equal_count=0,
        )

        assert stats.mcts_better_rate == 0.0

    def test_sufficient_data_positive(self) -> None:
        """Test sufficient data detection (positive case)."""
        stats = ShadowValidationStats(
            total_decisions=150,
            agreements=100,
            disagreements=50,
            mcts_better_count=10,
            heuristic_better_count=5,
            equal_count=0,
        )

        # 150 decisions >= 100 AND 15 evaluated disagreements >= 10
        assert stats.has_sufficient_data is True

    def test_sufficient_data_negative_low_decisions(self) -> None:
        """Test insufficient data (low decision count)."""
        stats = ShadowValidationStats(
            total_decisions=50,  # < 100
            agreements=30,
            disagreements=20,
            mcts_better_count=10,
            heuristic_better_count=5,
        )

        assert stats.has_sufficient_data is False

    def test_sufficient_data_negative_low_disagreements(self) -> None:
        """Test insufficient data (low evaluated disagreements)."""
        stats = ShadowValidationStats(
            total_decisions=150,
            agreements=145,
            disagreements=5,
            mcts_better_count=3,  # < 10 evaluated
            heuristic_better_count=2,
        )

        assert stats.has_sufficient_data is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        stats = ShadowValidationStats(
            total_decisions=100,
            agreements=80,
            disagreements=20,
            mcts_better_count=10,
        )

        d = stats.to_dict()
        assert d["total_decisions"] == 100
        assert d["agreements"] == 80
        assert d["agreement_rate"] == 0.8
        assert "has_sufficient_data" in d


# =============================================================================
# TEST: PromotionAnalysis
# =============================================================================


class TestPromotionAnalysis:
    """Tests for PromotionAnalysis logic."""

    def test_keep_shadow_insufficient_data(self) -> None:
        """Test KEEP_SHADOW when insufficient data."""
        stats = ShadowValidationStats(total_decisions=50)
        analysis = PromotionAnalysis(
            recommendation=PromotionRecommendation.KEEP_SHADOW,
            stats=stats,
            reasoning="Insufficient data",
        )

        assert analysis.recommendation == PromotionRecommendation.KEEP_SHADOW
        assert "Insufficient" in analysis.reasoning

    def test_keep_disabled_high_agreement(self) -> None:
        """Test KEEP_DISABLED when high agreement rate."""
        stats = ShadowValidationStats(
            total_decisions=200,
            agreements=195,  # 97.5% agreement
            disagreements=5,
            mcts_better_count=3,
            heuristic_better_count=2,
        )

        assert stats.agreement_rate > P03_R5_SHADOW_AGREEMENT_THRESHOLD

    def test_promote_enabled_low_criteria(self) -> None:
        """Test PROMOTE_ENABLED_LOW criteria."""
        stats = ShadowValidationStats(
            total_decisions=200,
            agreements=140,  # 70% agreement = 30% disagreement
            disagreements=60,
            mcts_better_count=40,  # 66% MCTS better
            heuristic_better_count=20,
        )

        assert stats.disagreement_rate > P03_R5_SHADOW_DIFF_THRESHOLD  # 0.30 > 0.20
        assert stats.mcts_better_rate > P03_R5_SHADOW_BETTER_THRESHOLD  # 0.66 > 0.55

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        stats = ShadowValidationStats(total_decisions=100)
        analysis = PromotionAnalysis(
            recommendation=PromotionRecommendation.KEEP_SHADOW,
            stats=stats,
            reasoning="Test",
            thresholds_met={"test": True},
        )

        d = analysis.to_dict()
        assert d["recommendation"] == "keep_shadow"
        assert d["reasoning"] == "Test"
        assert d["thresholds_met"]["test"] is True


# =============================================================================
# TEST: ShadowOutcomeTracker
# =============================================================================


class TestShadowOutcomeTracker:
    """Tests for ShadowOutcomeTracker class."""

    def test_init_without_db(self) -> None:
        """Test initialization without database."""
        tracker = ShadowOutcomeTracker()
        assert tracker._db is None

    def test_set_connection(self, mock_db_connection: AsyncMock) -> None:
        """Test setting database connection."""
        tracker = ShadowOutcomeTracker()
        tracker.set_connection(mock_db_connection)
        assert tracker._db is mock_db_connection

    @pytest.mark.asyncio
    async def test_record_decision_buffers_without_db(
        self,
        sample_shadow_record: ShadowDecisionRecord,
    ) -> None:
        """Test that decisions are buffered when no DB connection."""
        tracker = ShadowOutcomeTracker()

        decision_id = await tracker.record_decision(sample_shadow_record)

        assert decision_id == sample_shadow_record.decision_id
        assert len(tracker._pending_records) == 1

    @pytest.mark.asyncio
    async def test_record_decision_with_db(
        self,
        sample_shadow_record: ShadowDecisionRecord,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test recording decision with database."""
        tracker = ShadowOutcomeTracker(mock_db_connection)

        decision_id = await tracker.record_decision(sample_shadow_record)

        assert decision_id == sample_shadow_record.decision_id
        mock_db_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_decisions_batch(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test batch recording of decisions."""
        tracker = ShadowOutcomeTracker(mock_db_connection)

        records = [
            ShadowDecisionRecord.create(
                cycle_id="01JFXYZ123456789ABCDEFGHJK",
                decision_type=ShadowDecisionType.MERGE,
                heuristic_choice=f"choice_{i}",
                mcts_choice=f"mcts_{i}",
            )
            for i in range(5)
        ]

        count = await tracker.record_decisions_batch(records)

        assert count == 5
        mock_db_connection.execute_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_decisions_batch_empty(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test batch recording with empty list."""
        tracker = ShadowOutcomeTracker(mock_db_connection)

        count = await tracker.record_decisions_batch([])

        assert count == 0
        mock_db_connection.execute_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_pending(
        self,
        sample_shadow_record: ShadowDecisionRecord,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test flushing pending decisions."""
        tracker = ShadowOutcomeTracker()

        # Buffer without DB
        await tracker.record_decision(sample_shadow_record)
        assert len(tracker._pending_records) == 1

        # Set DB and flush
        tracker.set_connection(mock_db_connection)
        count = await tracker.flush_pending()

        assert count == 1
        assert len(tracker._pending_records) == 0

    @pytest.mark.asyncio
    async def test_update_evaluation(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test updating decision with evaluation."""
        tracker = ShadowOutcomeTracker(mock_db_connection)

        success = await tracker.update_evaluation(
            decision_id="01JFXYZ123456789ABCDEFGHJK",
            outcome_heuristic=0.7,
            outcome_mcts=0.9,
            mcts_better=True,
        )

        assert success is True
        mock_db_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats_for_window_no_db(self) -> None:
        """Test getting stats without database returns empty stats."""
        tracker = ShadowOutcomeTracker()

        stats = await tracker.get_stats_for_window()

        assert stats.total_decisions == 0

    @pytest.mark.asyncio
    async def test_get_stats_for_window_with_data(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test getting stats with database data."""
        mock_db_connection.fetch_one.return_value = {
            "total_decisions": 100,
            "agreements": 80,
            "disagreements": 20,
            "mcts_better_count": 10,
            "heuristic_better_count": 8,
            "equal_count": 2,
            "unevaluated_count": 5,
        }

        tracker = ShadowOutcomeTracker(mock_db_connection)
        stats = await tracker.get_stats_for_window()

        assert stats.total_decisions == 100
        assert stats.agreements == 80
        assert stats.disagreements == 20
        assert stats.mcts_better_count == 10

    @pytest.mark.asyncio
    async def test_analyze_for_promotion_insufficient_data(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test promotion analysis with insufficient data."""
        mock_db_connection.fetch_one.return_value = {
            "total_decisions": 50,  # < 100 required
            "agreements": 40,
            "disagreements": 10,
            "mcts_better_count": 3,
            "heuristic_better_count": 2,
            "equal_count": 0,
            "unevaluated_count": 5,
        }

        tracker = ShadowOutcomeTracker(mock_db_connection)
        analysis = await tracker.analyze_for_promotion()

        assert analysis.recommendation == PromotionRecommendation.KEEP_SHADOW
        assert "Insufficient" in analysis.reasoning

    @pytest.mark.asyncio
    async def test_analyze_for_promotion_high_agreement(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test promotion analysis with high agreement (keep disabled)."""
        mock_db_connection.fetch_one.return_value = {
            "total_decisions": 200,
            "agreements": 196,  # 98% agreement
            "disagreements": 4,
            "mcts_better_count": 8,
            "heuristic_better_count": 2,
            "equal_count": 0,
            "unevaluated_count": 0,
        }

        tracker = ShadowOutcomeTracker(mock_db_connection)
        analysis = await tracker.analyze_for_promotion()

        assert analysis.recommendation == PromotionRecommendation.KEEP_DISABLED
        assert "agreement" in analysis.reasoning.lower()

    @pytest.mark.asyncio
    async def test_analyze_for_promotion_mcts_better(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test promotion analysis when MCTS is significantly better."""
        mock_db_connection.fetch_one.return_value = {
            "total_decisions": 200,
            "agreements": 140,  # 70% agreement = 30% disagreement
            "disagreements": 60,
            "mcts_better_count": 40,  # 66% MCTS better
            "heuristic_better_count": 20,
            "equal_count": 0,
            "unevaluated_count": 0,
        }

        tracker = ShadowOutcomeTracker(mock_db_connection)
        analysis = await tracker.analyze_for_promotion()

        assert analysis.recommendation == PromotionRecommendation.PROMOTE_ENABLED_LOW
        assert "Recommend" in analysis.reasoning

    @pytest.mark.asyncio
    async def test_analyze_for_promotion_inconclusive(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test promotion analysis with inconclusive results."""
        mock_db_connection.fetch_one.return_value = {
            "total_decisions": 200,
            "agreements": 160,  # 80% agreement = 20% disagreement (at threshold)
            "disagreements": 40,
            "mcts_better_count": 15,  # 37.5% MCTS better (below threshold)
            "heuristic_better_count": 20,
            "equal_count": 5,
            "unevaluated_count": 0,
        }

        tracker = ShadowOutcomeTracker(mock_db_connection)
        analysis = await tracker.analyze_for_promotion()

        assert analysis.recommendation == PromotionRecommendation.KEEP_SHADOW
        assert "inconclusive" in analysis.reasoning.lower()


# =============================================================================
# TEST: CycleShadowTracker
# =============================================================================


class TestCycleShadowTracker:
    """Tests for CycleShadowTracker class."""

    def test_init(self) -> None:
        """Test initialization."""
        tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")
        assert tracker.cycle_id == "01JFXYZ123456789ABCDEFGHJK"
        assert tracker.decision_count == 0

    def test_record_decision(self) -> None:
        """Test recording a decision."""
        tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")

        record = tracker.record(
            decision_type=ShadowDecisionType.MERGE,
            heuristic_choice="accept",
            mcts_choice="reject",
            context={"test": True},
        )

        assert tracker.decision_count == 1
        assert record.cycle_id == tracker.cycle_id
        assert record.choices_differ is True

    def test_record_multiple_decisions(self) -> None:
        """Test recording multiple decisions."""
        tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")

        # 3 disagreements
        tracker.record(ShadowDecisionType.MERGE, "a", "b")
        tracker.record(ShadowDecisionType.CAUSAL, "x", "y")
        tracker.record(ShadowDecisionType.CLUSTER, "1", "2")

        # 2 agreements
        tracker.record(ShadowDecisionType.DECAY, "same", "same")
        tracker.record(ShadowDecisionType.NOVELTY, "equal", "equal")

        assert tracker.decision_count == 5
        assert tracker.disagreement_count == 3
        assert tracker.agreement_count == 2

    def test_get_summary(self) -> None:
        """Test getting cycle summary."""
        tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")

        tracker.record(ShadowDecisionType.MERGE, "a", "b")
        tracker.record(ShadowDecisionType.MERGE, "same", "same")

        summary = tracker.get_summary()

        assert summary["cycle_id"] == "01JFXYZ123456789ABCDEFGHJK"
        assert summary["decision_count"] == 2
        assert summary["agreement_count"] == 1
        assert summary["disagreement_count"] == 1
        assert summary["agreement_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_persist_all(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test persisting all decisions."""
        cycle_tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")
        cycle_tracker.record(ShadowDecisionType.MERGE, "a", "b")
        cycle_tracker.record(ShadowDecisionType.CAUSAL, "x", "y")

        outcome_tracker = ShadowOutcomeTracker(mock_db_connection)
        count = await cycle_tracker.persist_all(outcome_tracker)

        assert count == 2
        mock_db_connection.execute_many.assert_called_once()

    def test_clear(self) -> None:
        """Test clearing recorded decisions."""
        tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")

        tracker.record(ShadowDecisionType.MERGE, "a", "b")
        assert tracker.decision_count == 1

        tracker.clear()
        assert tracker.decision_count == 0


# =============================================================================
# TEST: Constants and Thresholds
# =============================================================================


class TestConstants:
    """Tests for module constants and thresholds."""

    def test_evaluation_window_ms(self) -> None:
        """Test evaluation window is 7 days in milliseconds."""
        expected_ms = 7 * 24 * 60 * 60 * 1000  # 604800000 ms
        assert EVALUATION_WINDOW_MS == expected_ms

    def test_shadow_thresholds(self) -> None:
        """Test shadow validation thresholds from dossier."""
        assert P03_R5_SHADOW_DIFF_THRESHOLD == 0.20  # 20%
        assert P03_R5_SHADOW_AGREEMENT_THRESHOLD == 0.95  # 95%
        assert P03_R5_SHADOW_BETTER_THRESHOLD == 0.55  # 55%

    def test_validation_window_days(self) -> None:
        """Test default validation window."""
        assert P03_R5_SHADOW_VALIDATION_WINDOW_DAYS == 30


# =============================================================================
# TEST: Integration Scenarios
# =============================================================================


class TestIntegrationScenarios:
    """Integration tests for shadow validation workflow."""

    def test_full_cycle_workflow(self) -> None:
        """Test full cycle shadow tracking workflow."""
        # 1. Create cycle tracker
        cycle_tracker = CycleShadowTracker(cycle_id="01JFXYZ123456789ABCDEFGHJK")

        # 2. Simulate shadow decisions during R5
        decisions = [
            (ShadowDecisionType.MERGE, "accept", "reject"),
            (ShadowDecisionType.MERGE, "accept", "accept"),  # Agreement
            (ShadowDecisionType.CAUSAL, "create", "skip"),
            (ShadowDecisionType.CLUSTER, "a", "b"),
            (ShadowDecisionType.DECAY, "0.9", "0.9"),  # Agreement
        ]

        for dt, heuristic, mcts in decisions:
            cycle_tracker.record(dt, heuristic, mcts)

        # 3. Verify cycle stats
        summary = cycle_tracker.get_summary()
        assert summary["decision_count"] == 5
        assert summary["agreement_count"] == 2
        assert summary["disagreement_count"] == 3
        assert summary["agreement_rate"] == 0.4

    def test_promotion_decision_tree(self) -> None:
        """Test promotion decision tree with different scenarios."""
        # Scenario 1: High agreement -> KEEP_DISABLED
        stats_high_agree = ShadowValidationStats(
            total_decisions=200,
            agreements=192,  # 96%
            disagreements=8,
            mcts_better_count=5,
            heuristic_better_count=3,
        )
        assert stats_high_agree.agreement_rate > P03_R5_SHADOW_AGREEMENT_THRESHOLD

        # Scenario 2: MCTS better -> PROMOTE_ENABLED_LOW
        stats_mcts_better = ShadowValidationStats(
            total_decisions=200,
            agreements=130,  # 65% = 35% disagreement
            disagreements=70,
            mcts_better_count=50,  # 71% MCTS better
            heuristic_better_count=20,
        )
        assert stats_mcts_better.disagreement_rate > P03_R5_SHADOW_DIFF_THRESHOLD
        assert stats_mcts_better.mcts_better_rate > P03_R5_SHADOW_BETTER_THRESHOLD

        # Scenario 3: Inconclusive -> KEEP_SHADOW
        stats_inconclusive = ShadowValidationStats(
            total_decisions=200,
            agreements=160,  # 80%
            disagreements=40,
            mcts_better_count=15,  # 37.5%
            heuristic_better_count=20,
            equal_count=5,
        )
        # Not high enough agreement, not high enough MCTS better rate
        assert stats_inconclusive.agreement_rate <= P03_R5_SHADOW_AGREEMENT_THRESHOLD
        assert stats_inconclusive.mcts_better_rate < P03_R5_SHADOW_BETTER_THRESHOLD

    def test_record_immutability(self) -> None:
        """Test that ShadowDecisionRecord is immutable."""
        record = ShadowDecisionRecord.create(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            decision_type=ShadowDecisionType.MERGE,
            heuristic_choice="accept",
            mcts_choice="reject",
        )

        # Frozen dataclass should raise on modification attempt
        with pytest.raises(AttributeError):
            record.heuristic_choice = "new_value"  # type: ignore

    def test_context_serialization(self) -> None:
        """Test context is properly serialized to JSON."""
        context = {
            "entity_id": "ent_001",
            "confidence": 0.85,
            "nested": {"key": "value"},
            "list": [1, 2, 3],
        }

        record = ShadowDecisionRecord.create(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            decision_type=ShadowDecisionType.MERGE,
            heuristic_choice="accept",
            mcts_choice="reject",
            context=context,
        )

        db_dict = record.to_db_dict()
        # context_json should be a JSON string
        import json

        parsed = json.loads(db_dict["context_json"])
        assert parsed["entity_id"] == "ent_001"
        assert parsed["nested"]["key"] == "value"
