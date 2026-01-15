"""
Unit tests for MCTS Decision Persistence (Issue 8.1.7).

These tests validate:
- MCTSDecisionRecord creation and validation
- MCTSDecisionPersistence operations
- CycleDecisionTracker budget tracking
- Integration with MCTSDecision.to_persistence_record()

References:
- M8_EXECUTION.md Issue 8.1.7: Persist MCTS Decisions + Metrics
- Dossier Appendix D: st_mcts_decisions schema
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.mcts import MCTSDecision
from k0.modules.consolidation.dream.mcts_persistence import (
    CycleDecisionTracker,
    MCTSDecisionPersistence,
    MCTSDecisionRecord,
    MCTSDecisionType,
    TerminationReason,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_decision_record() -> MCTSDecisionRecord:
    """Create a sample decision record."""
    return MCTSDecisionRecord.create(
        cycle_id="01JFXYZ123456789ABCDEFGHJK",
        decision_type=MCTSDecisionType.MERGE,
        context={"entity_id": "ent_001", "confidence": 0.85},
        rollouts_allocated=100,
        rollouts_executed=75,
        early_termination=True,
        termination_reason=TerminationReason.CLEAR_WINNER,
        chosen_action="merge_accept",
        value_estimate=0.92,
        confidence_interval_width=0.03,
        compute_ms=45,
    )


@pytest.fixture
def sample_mcts_decision() -> MCTSDecision:
    """Create a sample MCTS decision from algorithm module."""
    return MCTSDecision(
        decision_id="01JFABC123456789XYZDEFGHIJ",
        decision_type="entity_merge",
        context={"entity_id": "ent_002"},
        rollouts_allocated=50,
        rollouts_executed=50,
        early_termination=False,
        termination_reason=None,
        chosen_action="merge_reject",
        value_estimate=0.45,
        confidence_interval_width=0.08,
        compute_ms=32,
        created_at_ms=1704067200000,
    )


@pytest.fixture
def mock_db_connection() -> AsyncMock:
    """Create a mock database connection."""
    mock = AsyncMock()
    mock.execute = AsyncMock(return_value=None)
    mock.execute_many = AsyncMock(return_value=None)
    return mock


# =============================================================================
# MCTSDecisionRecord Tests
# =============================================================================


class TestMCTSDecisionRecord:
    """Tests for MCTSDecisionRecord dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating record with factory method."""
        record = MCTSDecisionRecord.create(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            decision_type=MCTSDecisionType.CAUSAL,
        )

        assert record.cycle_id == "01JFXYZ123456789ABCDEFGHJK"
        assert record.decision_type == "causal"
        assert record.rollouts_allocated == 0
        assert record.rollouts_executed == 0
        assert record.early_termination is False
        assert record.termination_reason == "none"
        assert record.decision_id  # Auto-generated ULID

    def test_create_with_all_fields(self, sample_decision_record: MCTSDecisionRecord) -> None:
        """Test creating record with all fields specified."""
        record = sample_decision_record

        assert record.decision_type == "merge"
        assert record.rollouts_allocated == 100
        assert record.rollouts_executed == 75
        assert record.early_termination is True
        assert record.termination_reason == "clear_winner"
        assert record.chosen_action == "merge_accept"
        assert record.value_estimate == 0.92
        assert record.confidence_interval_width == 0.03
        assert record.compute_ms == 45

    def test_to_db_dict(self, sample_decision_record: MCTSDecisionRecord) -> None:
        """Test conversion to database dictionary."""
        db_dict = sample_decision_record.to_db_dict()

        assert db_dict["decision_id"] == sample_decision_record.decision_id
        assert db_dict["cycle_id"] == sample_decision_record.cycle_id
        assert db_dict["decision_type"] == "merge"
        assert db_dict["early_termination"] is True
        assert db_dict["termination_reason"] == "clear_winner"
        assert "created_at" in db_dict
        assert "context_json" in db_dict

    def test_to_db_dict_no_termination_reason_when_not_early(self) -> None:
        """Test that termination_reason is None when not early terminated."""
        record = MCTSDecisionRecord.create(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            decision_type=MCTSDecisionType.CLUSTER,
            early_termination=False,
        )

        db_dict = record.to_db_dict()
        assert db_dict["termination_reason"] is None

    def test_all_decision_types(self) -> None:
        """Test all decision type enum values."""
        for dt in MCTSDecisionType:
            record = MCTSDecisionRecord.create(
                cycle_id="01JFXYZ123456789ABCDEFGHJK",
                decision_type=dt,
            )
            assert record.decision_type == dt.value

    def test_all_termination_reasons(self) -> None:
        """Test all termination reason enum values."""
        for tr in TerminationReason:
            record = MCTSDecisionRecord.create(
                cycle_id="01JFXYZ123456789ABCDEFGHJK",
                decision_type=MCTSDecisionType.MERGE,
                early_termination=True,
                termination_reason=tr,
            )
            assert record.termination_reason == tr.value


# =============================================================================
# MCTSDecision.to_persistence_record Tests
# =============================================================================


class TestMCTSDecisionConversion:
    """Tests for MCTSDecision.to_persistence_record()."""

    def test_basic_conversion(self, sample_mcts_decision: MCTSDecision) -> None:
        """Test basic conversion to persistence record."""
        cycle_id = "01JFXYZ123456789ABCDEFGHJK"
        record = sample_mcts_decision.to_persistence_record(cycle_id)

        assert record.decision_id == sample_mcts_decision.decision_id
        assert record.cycle_id == cycle_id
        assert record.decision_type == sample_mcts_decision.decision_type
        assert record.rollouts_allocated == sample_mcts_decision.rollouts_allocated
        assert record.rollouts_executed == sample_mcts_decision.rollouts_executed
        assert record.early_termination == sample_mcts_decision.early_termination
        assert record.chosen_action == sample_mcts_decision.chosen_action
        assert record.value_estimate == sample_mcts_decision.value_estimate

    def test_conversion_with_early_termination(self) -> None:
        """Test conversion when decision has early termination."""
        decision = MCTSDecision(
            decision_id="01JFABC123456789XYZDEFGHIJ",
            decision_type="causal_edge",
            context={},
            rollouts_allocated=50,
            rollouts_executed=25,
            early_termination=True,
            termination_reason="clear_winner",
            chosen_action="create_edge",
            value_estimate=0.88,
            confidence_interval_width=0.02,
            compute_ms=20,
            created_at_ms=1704067200000,
        )

        record = decision.to_persistence_record("01JFCYCLE")
        assert record.early_termination is True
        assert record.termination_reason == "clear_winner"

    def test_conversion_with_unknown_termination_reason(self) -> None:
        """Test conversion handles unknown termination reason."""
        decision = MCTSDecision(
            decision_id="01JFABC123456789XYZDEFGHIJ",
            decision_type="generic",
            context={},
            rollouts_allocated=20,
            rollouts_executed=20,
            early_termination=True,
            termination_reason="unknown_reason",  # Not in enum
            chosen_action="accept",
            value_estimate=0.5,
            confidence_interval_width=0.1,
            compute_ms=10,
            created_at_ms=1704067200000,
        )

        record = decision.to_persistence_record("01JFCYCLE")
        assert record.termination_reason == "none"  # Falls back to NONE


# =============================================================================
# MCTSDecisionPersistence Tests
# =============================================================================


class TestMCTSDecisionPersistence:
    """Tests for MCTSDecisionPersistence class."""

    @pytest.mark.asyncio
    async def test_persist_single_decision(
        self,
        sample_decision_record: MCTSDecisionRecord,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test persisting a single decision."""
        persistence = MCTSDecisionPersistence(db=mock_db_connection)

        result = await persistence.persist_decision(sample_decision_record)

        assert result == sample_decision_record.decision_id
        mock_db_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_decision_without_db_buffers(
        self,
        sample_decision_record: MCTSDecisionRecord,
    ) -> None:
        """Test that decisions are buffered when no DB connection."""
        persistence = MCTSDecisionPersistence(db=None)

        result = await persistence.persist_decision(sample_decision_record)

        assert result == sample_decision_record.decision_id
        assert len(persistence._pending_decisions) == 1

    @pytest.mark.asyncio
    async def test_persist_batch(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test batch persistence of multiple decisions."""
        persistence = MCTSDecisionPersistence(db=mock_db_connection)

        records = [
            MCTSDecisionRecord.create(
                cycle_id="01JFCYCLE",
                decision_type=MCTSDecisionType.MERGE,
            )
            for _ in range(5)
        ]

        count = await persistence.persist_decisions_batch(records)

        assert count == 5
        mock_db_connection.execute_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_empty_batch(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test batch persistence with empty list."""
        persistence = MCTSDecisionPersistence(db=mock_db_connection)

        count = await persistence.persist_decisions_batch([])

        assert count == 0
        mock_db_connection.execute_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_pending(
        self,
        sample_decision_record: MCTSDecisionRecord,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test flushing pending decisions."""
        persistence = MCTSDecisionPersistence(db=None)

        # Buffer some decisions
        await persistence.persist_decision(sample_decision_record)
        await persistence.persist_decision(sample_decision_record)

        assert len(persistence._pending_decisions) == 2

        # Set connection and flush
        persistence.set_connection(mock_db_connection)
        count = await persistence.flush_pending()

        assert count == 2
        assert len(persistence._pending_decisions) == 0

    def test_set_connection(self, mock_db_connection: AsyncMock) -> None:
        """Test setting database connection after init."""
        persistence = MCTSDecisionPersistence(db=None)
        assert persistence._db is None

        persistence.set_connection(mock_db_connection)
        assert persistence._db is mock_db_connection


# =============================================================================
# CycleDecisionTracker Tests
# =============================================================================


class TestCycleDecisionTracker:
    """Tests for CycleDecisionTracker class."""

    def test_basic_tracking(self) -> None:
        """Test basic decision tracking."""
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE", max_rollouts=1000)

        record = MCTSDecisionRecord.create(
            cycle_id="01JFCYCLE",
            decision_type=MCTSDecisionType.MERGE,
            rollouts_executed=100,
        )
        tracker.record_decision(record)

        assert tracker.decision_count == 1
        assert tracker.total_rollouts == 100
        assert tracker.remaining_budget == 900

    def test_budget_exhaustion(self) -> None:
        """Test budget exhaustion detection."""
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE", max_rollouts=100)

        for _ in range(5):
            record = MCTSDecisionRecord.create(
                cycle_id="01JFCYCLE",
                decision_type=MCTSDecisionType.MERGE,
                rollouts_executed=25,
            )
            tracker.record_decision(record)

        assert tracker.total_rollouts == 125
        assert tracker.budget_exhausted is True
        assert tracker.remaining_budget == 0

    def test_early_termination_tracking(self) -> None:
        """Test early termination rate calculation."""
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE")

        # Add 3 decisions: 2 early terminated, 1 not
        for i in range(3):
            record = MCTSDecisionRecord.create(
                cycle_id="01JFCYCLE",
                decision_type=MCTSDecisionType.MERGE,
                rollouts_executed=10,
                early_termination=(i < 2),  # First 2 are early terminated
                termination_reason=(
                    TerminationReason.CLEAR_WINNER if i < 2 else TerminationReason.NONE
                ),
            )
            tracker.record_decision(record)

        assert tracker.early_termination_rate == pytest.approx(2 / 3)

    def test_get_stats(self) -> None:
        """Test getting cycle statistics."""
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE", max_rollouts=500)

        record = MCTSDecisionRecord.create(
            cycle_id="01JFCYCLE",
            decision_type=MCTSDecisionType.CAUSAL,
            rollouts_executed=50,
            early_termination=True,
            termination_reason=TerminationReason.LOW_UNCERTAINTY,
        )
        tracker.record_decision(record)

        stats = tracker.get_stats()

        assert stats["cycle_id"] == "01JFCYCLE"
        assert stats["decision_count"] == 1
        assert stats["total_rollouts"] == 50
        assert stats["max_rollouts"] == 500
        assert stats["remaining_budget"] == 450
        assert stats["budget_exhausted"] is False
        assert stats["early_termination_count"] == 1
        assert stats["early_termination_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_persist_all(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test persisting all tracked decisions."""
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE")
        persistence = MCTSDecisionPersistence(db=mock_db_connection)

        for _ in range(3):
            record = MCTSDecisionRecord.create(
                cycle_id="01JFCYCLE",
                decision_type=MCTSDecisionType.CLUSTER,
                rollouts_executed=30,
            )
            tracker.record_decision(record)

        count = await tracker.persist_all(persistence)

        assert count == 3
        mock_db_connection.execute_many.assert_called_once()

    def test_clear(self) -> None:
        """Test clearing tracker state."""
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE")

        record = MCTSDecisionRecord.create(
            cycle_id="01JFCYCLE",
            decision_type=MCTSDecisionType.MERGE,
            rollouts_executed=100,
            early_termination=True,
            termination_reason=TerminationReason.CLEAR_WINNER,
        )
        tracker.record_decision(record)

        assert tracker.decision_count == 1
        assert tracker.total_rollouts == 100

        tracker.clear()

        assert tracker.decision_count == 0
        assert tracker.total_rollouts == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestMCTSPersistenceIntegration:
    """Integration tests for MCTS persistence workflow."""

    @pytest.mark.asyncio
    async def test_full_cycle_workflow(
        self,
        mock_db_connection: AsyncMock,
    ) -> None:
        """Test complete cycle workflow: track -> persist -> clear."""
        # Setup
        tracker = CycleDecisionTracker(cycle_id="01JFCYCLE", max_rollouts=1000)
        persistence = MCTSDecisionPersistence(db=mock_db_connection)

        # Simulate decisions during cycle
        for decision_type in [
            MCTSDecisionType.MERGE,
            MCTSDecisionType.CAUSAL,
            MCTSDecisionType.CLUSTER,
        ]:
            record = MCTSDecisionRecord.create(
                cycle_id="01JFCYCLE",
                decision_type=decision_type,
                rollouts_executed=50,
                early_termination=(decision_type == MCTSDecisionType.MERGE),
                termination_reason=(
                    TerminationReason.CLEAR_WINNER
                    if decision_type == MCTSDecisionType.MERGE
                    else TerminationReason.NONE
                ),
            )
            tracker.record_decision(record)

        # Verify tracking
        assert tracker.decision_count == 3
        assert tracker.total_rollouts == 150
        assert tracker.early_termination_rate == pytest.approx(1 / 3)

        # Persist and clear
        count = await tracker.persist_all(persistence)
        tracker.clear()

        # Verify
        assert count == 3
        assert tracker.decision_count == 0

    def test_mcts_decision_to_record_to_db(self) -> None:
        """Test full conversion pipeline: MCTSDecision -> Record -> DB dict."""
        # Create MCTS decision from algorithm
        mcts_decision = MCTSDecision(
            decision_id="01JFABC123456789XYZDEFGHIJ",
            decision_type="entity_merge",
            context={"entity_id": "ent_123", "similarity": 0.95},
            rollouts_allocated=100,
            rollouts_executed=45,
            early_termination=True,
            termination_reason="clear_winner",
            chosen_action="merge_accept",
            value_estimate=0.92,
            confidence_interval_width=0.03,
            compute_ms=38,
            created_at_ms=1704067200000,
        )

        # Convert to persistence record
        record = mcts_decision.to_persistence_record(cycle_id="01JFCYCLE123")

        # Convert to DB dict
        db_dict = record.to_db_dict()

        # Verify complete pipeline
        assert db_dict["decision_id"] == mcts_decision.decision_id
        assert db_dict["cycle_id"] == "01JFCYCLE123"
        assert db_dict["decision_type"] == "entity_merge"
        assert db_dict["rollouts_allocated"] == 100
        assert db_dict["rollouts_executed"] == 45
        assert db_dict["early_termination"] is True
        assert db_dict["termination_reason"] == "clear_winner"
        assert db_dict["chosen_action"] == "merge_accept"
        assert db_dict["value_estimate"] == 0.92


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
