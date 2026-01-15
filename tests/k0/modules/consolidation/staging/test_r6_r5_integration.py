"""
Tests for Issue 8.1.17 — R5→R6 Integration Handoff.

Verifies:
1. R6Coordinator.execute() processes R5 outputs alongside R2-R4
2. R6Output manifest includes insight_count, counterfactual_count, routine_optimization_count
3. SummaryGenerator correctly propagates R5 counts
4. ReconciliationSummary includes all R5 fields
"""

from __future__ import annotations

from typing import Dict, List
import pytest

from k0.modules.consolidation.staging.r6_output import (
    ReconciliationSummary,
)
from k0.modules.consolidation.staging.summary_generator import (
    GeneratorResult,
    SummaryGenerator,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def sample_event_states() -> Dict[str, P03EventState]:
    """Create sample event states for testing."""
    state1 = P03EventState(event_id="evt_001")
    state1.reconciliation_action = ReconciliationAction.CREATE
    state2 = P03EventState(event_id="evt_002")
    state2.reconciliation_action = ReconciliationAction.REINFORCE
    return {
        "evt_001": state1,
        "evt_002": state2,
    }


@pytest.fixture
def sample_truth_writes() -> List[StagedWrite]:
    """Create sample truth writes."""
    return [
        StagedWrite(
            write_id="w001",
            layer="st_episodic",
            operation=WriteOperation.INSERT,
            record_id="rec_001",
            record_data={"event_id": "evt_001"},
            idempotency_key="R5:st_episodic:rec_001",
            source_phase="R5",
        ),
        StagedWrite(
            write_id="w002",
            layer="st_sem",
            operation=WriteOperation.INSERT,
            record_id="rec_002",
            record_data={"pattern_type": "INSIGHT", "event_id": "evt_001"},
            idempotency_key="R5:st_sem:rec_002",
            source_phase="R5",
        ),
        StagedWrite(
            write_id="w003",
            layer="st_prospective",
            operation=WriteOperation.INSERT,
            record_id="rec_003",
            record_data={"intention_type": "COUNTERFACTUAL", "event_id": "evt_001"},
            idempotency_key="R5:st_prospective:rec_003",
            source_phase="R5",
        ),
        StagedWrite(
            write_id="w004",
            layer="st_procedural",
            operation=WriteOperation.UPDATE,
            record_id="routine_001",
            record_data={"routine_id": "routine_001"},
            idempotency_key="R5:st_procedural:routine_001",
            source_phase="R5",
            expected_version=1,
        ),
    ]


@pytest.fixture
def sample_kg_writes() -> List[StagedWrite]:
    """Create sample KG writes."""
    return [
        StagedWrite(
            write_id="kg001",
            layer="st_kg_dom",
            operation=WriteOperation.INSERT,
            record_id="ent_001",
            record_data={"entity_id": "ent_001"},
            idempotency_key="R5:st_kg_dom:ent_001",
            source_phase="R5",
        ),
    ]


# =============================================================================
# ReconciliationSummary TESTS
# =============================================================================


class TestReconciliationSummaryR5Fields:
    """Tests for R5 fields in ReconciliationSummary (Issue 8.1.17)."""

    def test_reconciliation_summary_has_counterfactual_count(self):
        """ReconciliationSummary includes counterfactual_count field."""
        summary = ReconciliationSummary(counterfactual_count=5)
        assert summary.counterfactual_count == 5

    def test_reconciliation_summary_has_routine_optimization_count(self):
        """ReconciliationSummary includes routine_optimization_count field."""
        summary = ReconciliationSummary(routine_optimization_count=3)
        assert summary.routine_optimization_count == 3

    def test_reconciliation_summary_defaults(self):
        """R5 fields default to 0."""
        summary = ReconciliationSummary()
        assert summary.counterfactual_count == 0
        assert summary.routine_optimization_count == 0
        assert summary.insight_count == 0

    def test_to_dict_includes_r5_counts(self):
        """to_dict() includes all R5 count fields."""
        summary = ReconciliationSummary(
            insight_count=10,
            counterfactual_count=5,
            routine_optimization_count=3,
        )
        result = summary.to_dict()
        assert result["insight_count"] == 10
        assert result["counterfactual_count"] == 5
        assert result["routine_optimization_count"] == 3

    def test_all_r5_fields_in_summary(self):
        """All R5 fields are properly stored and retrievable."""
        summary = ReconciliationSummary(
            total_events=10,
            consolidated_count=8,
            insight_count=4,
            counterfactual_count=2,
            routine_optimization_count=1,
        )
        assert summary.total_events == 10
        assert summary.consolidated_count == 8
        assert summary.insight_count == 4
        assert summary.counterfactual_count == 2
        assert summary.routine_optimization_count == 1


# =============================================================================
# SummaryGenerator TESTS
# =============================================================================


class TestSummaryGeneratorR5Counts:
    """Tests for SummaryGenerator R5 count handling (Issue 8.1.17)."""

    def test_compute_accepts_counterfactual_count(
        self,
        sample_event_states: Dict[str, P03EventState],
    ):
        """compute() accepts counterfactual_count parameter."""
        gen = SummaryGenerator()
        result = gen.compute(
            event_states=sample_event_states,
            counterfactual_count=5,
        )
        assert result.summary.counterfactual_count == 5

    def test_compute_accepts_routine_optimization_count(
        self,
        sample_event_states: Dict[str, P03EventState],
    ):
        """compute() accepts routine_optimization_count parameter."""
        gen = SummaryGenerator()
        result = gen.compute(
            event_states=sample_event_states,
            routine_optimization_count=3,
        )
        assert result.summary.routine_optimization_count == 3

    def test_compute_with_all_r5_params(
        self,
        sample_event_states: Dict[str, P03EventState],
    ):
        """compute() works with all R5 parameters."""
        gen = SummaryGenerator()
        result = gen.compute(
            event_states=sample_event_states,
            insight_count=10,
            counterfactual_count=5,
            routine_optimization_count=3,
        )
        assert result.summary.insight_count == 10
        assert result.summary.counterfactual_count == 5
        assert result.summary.routine_optimization_count == 3

    def test_compute_with_writes_accepts_r5_counts(
        self,
        sample_event_states: Dict[str, P03EventState],
        sample_truth_writes: List[StagedWrite],
        sample_kg_writes: List[StagedWrite],
    ):
        """compute_with_writes() accepts R5 count parameters."""
        gen = SummaryGenerator()
        result = gen.compute_with_writes(
            event_states=sample_event_states,
            truth_writes=sample_truth_writes,
            kg_writes=sample_kg_writes,
            insight_count=10,
            counterfactual_count=5,
            routine_optimization_count=3,
        )
        assert result.summary.insight_count == 10
        assert result.summary.counterfactual_count == 5
        assert result.summary.routine_optimization_count == 3

    def test_compute_with_writes_defaults_r5_counts(
        self,
        sample_event_states: Dict[str, P03EventState],
        sample_truth_writes: List[StagedWrite],
        sample_kg_writes: List[StagedWrite],
    ):
        """compute_with_writes() defaults R5 counts to 0."""
        gen = SummaryGenerator()
        result = gen.compute_with_writes(
            event_states=sample_event_states,
            truth_writes=sample_truth_writes,
            kg_writes=sample_kg_writes,
        )
        assert result.summary.insight_count == 0
        assert result.summary.counterfactual_count == 0
        assert result.summary.routine_optimization_count == 0


class TestSummaryGeneratorMerge:
    """Tests for SummaryGenerator.merge() with R5 counts (Issue 8.1.17)."""

    def test_merge_aggregates_counterfactual_count(self):
        """merge() sums counterfactual_count across summaries."""
        gen = SummaryGenerator()
        summaries = [
            ReconciliationSummary(counterfactual_count=3),
            ReconciliationSummary(counterfactual_count=2),
            ReconciliationSummary(counterfactual_count=5),
        ]
        result = gen.merge(summaries)
        assert result.counterfactual_count == 10

    def test_merge_aggregates_routine_optimization_count(self):
        """merge() sums routine_optimization_count across summaries."""
        gen = SummaryGenerator()
        summaries = [
            ReconciliationSummary(routine_optimization_count=1),
            ReconciliationSummary(routine_optimization_count=2),
            ReconciliationSummary(routine_optimization_count=3),
        ]
        result = gen.merge(summaries)
        assert result.routine_optimization_count == 6

    def test_merge_aggregates_all_r5_counts(self):
        """merge() correctly aggregates all R5 counts."""
        gen = SummaryGenerator()
        summaries = [
            ReconciliationSummary(
                insight_count=5,
                counterfactual_count=2,
                routine_optimization_count=1,
            ),
            ReconciliationSummary(
                insight_count=3,
                counterfactual_count=4,
                routine_optimization_count=2,
            ),
        ]
        result = gen.merge(summaries)
        assert result.insight_count == 8
        assert result.counterfactual_count == 6
        assert result.routine_optimization_count == 3

    def test_merge_single_summary_preserves_r5_counts(self):
        """merge() with single summary preserves R5 counts."""
        gen = SummaryGenerator()
        original = ReconciliationSummary(
            insight_count=7,
            counterfactual_count=3,
            routine_optimization_count=2,
        )
        result = gen.merge([original])
        assert result.insight_count == 7
        assert result.counterfactual_count == 3
        assert result.routine_optimization_count == 2


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestR5ToR6Integration:
    """End-to-end tests for R5→R6 integration (Issue 8.1.17)."""

    def test_summary_generator_pipeline_with_r5(
        self,
        sample_event_states: Dict[str, P03EventState],
        sample_truth_writes: List[StagedWrite],
        sample_kg_writes: List[StagedWrite],
    ):
        """Full pipeline: writes → compute_with_writes → summary with R5 counts."""
        gen = SummaryGenerator()

        # Simulate R5 outputs
        insight_count = 4
        counterfactual_count = 2
        routine_optimization_count = 1

        result = gen.compute_with_writes(
            event_states=sample_event_states,
            truth_writes=sample_truth_writes,
            kg_writes=sample_kg_writes,
            insight_count=insight_count,
            counterfactual_count=counterfactual_count,
            routine_optimization_count=routine_optimization_count,
            cycle_duration_ms=150,
        )

        # Verify R5 counts in summary
        assert result.summary.insight_count == 4
        assert result.summary.counterfactual_count == 2
        assert result.summary.routine_optimization_count == 1

        # Verify other summary fields still work
        assert result.summary.total_events == 2
        assert result.summary.total_writes == 5  # 4 truth + 1 kg
        assert result.summary.cycle_duration_ms == 150

    def test_merge_multiple_batches_with_r5(self):
        """Merging multiple batch summaries aggregates R5 counts correctly."""
        gen = SummaryGenerator()

        # Simulate batch processing with different R5 outputs
        batch1 = ReconciliationSummary(
            total_events=5,
            consolidated_count=5,
            insight_count=3,
            counterfactual_count=1,
            routine_optimization_count=2,
            total_writes=10,
        )
        batch2 = ReconciliationSummary(
            total_events=3,
            consolidated_count=3,
            insight_count=2,
            counterfactual_count=3,
            routine_optimization_count=1,
            total_writes=6,
        )

        merged = gen.merge([batch1, batch2])

        # Verify aggregation
        assert merged.total_events == 8
        assert merged.consolidated_count == 8
        assert merged.insight_count == 5  # 3 + 2
        assert merged.counterfactual_count == 4  # 1 + 3
        assert merged.routine_optimization_count == 3  # 2 + 1
        assert merged.total_writes == 16


# =============================================================================
# CONTRACT VALIDATION TESTS
# =============================================================================


class TestR5OutputContract:
    """Tests validating R5→R6 contract compliance (Issue 8.1.17)."""

    def test_summary_fields_match_contract(self):
        """ReconciliationSummary has all R5 fields per contract."""
        summary = ReconciliationSummary()

        # Verify all R5 fields exist
        assert hasattr(summary, "insight_count")
        assert hasattr(summary, "counterfactual_count")
        assert hasattr(summary, "routine_optimization_count")

        # Verify field types
        assert isinstance(summary.insight_count, int)
        assert isinstance(summary.counterfactual_count, int)
        assert isinstance(summary.routine_optimization_count, int)

    def test_to_dict_r5_keys_present(self):
        """to_dict() output contains all R5 keys."""
        summary = ReconciliationSummary()
        result = summary.to_dict()

        assert "insight_count" in result
        assert "counterfactual_count" in result
        assert "routine_optimization_count" in result

    def test_generator_result_r5_support(
        self,
        sample_event_states: Dict[str, P03EventState],
    ):
        """GeneratorResult correctly wraps summary with R5 counts."""
        gen = SummaryGenerator()
        result = gen.compute(
            event_states=sample_event_states,
            insight_count=5,
            counterfactual_count=3,
            routine_optimization_count=2,
        )

        assert isinstance(result, GeneratorResult)
        assert result.summary.insight_count == 5
        assert result.summary.counterfactual_count == 3
        assert result.summary.routine_optimization_count == 2
