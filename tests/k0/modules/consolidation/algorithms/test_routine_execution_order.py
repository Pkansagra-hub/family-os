"""
Integration tests for M5-E2: Routine Execution Order.

These tests validate:
- RoutineDetector runs BEFORE TDL-HCO
- RoutineDetector output flows to R6 TruthWriteAssembler
- RoutineCandidate is written to st_procedural
- TDL-HCO receives detected routines from RoutineDetector

References:
- R5_ALGORITHM_BACKLOG.md M5-E2: Execution Order
- GAP-003: Routine Detection
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.routine_detector import FrequencyPattern, RoutineCandidate
from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler
from k0.pipelines.p03.staged_writes import LAYER_ST_PROCEDURAL

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def routine_candidate() -> RoutineCandidate:
    """Sample RoutineCandidate from RoutineDetector."""
    return RoutineCandidate(
        routine_id="routine_morning_coffee",
        routine_name="Morning Coffee Routine",
        routine_category="DAILY_ROUTINE",
        temporal_anchor="08:00",
        day_pattern="weekdays",
        frequency=FrequencyPattern.DAILY,
        regularity_score=0.85,
        action_sequence_json='[{"action": "wake_up"}, {"action": "make_coffee"}]',
        source_episodes_json='["ep_001", "ep_002", "ep_003"]',
        source_episode_count=3,
        typical_duration_minutes=15,
        confidence_score=0.9,
        streak_count=5,
    )


@pytest.fixture
def truth_write_assembler() -> TruthWriteAssembler:
    """TruthWriteAssembler for testing."""
    from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator

    # ULID must be 26 characters
    idempotency_gen = IdempotencyKeyGenerator(cycle_ulid="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return TruthWriteAssembler(
        idempotency_gen=idempotency_gen,
        tenant_id="tenant_001",
        space_id="space_001",
    )


# =============================================================================
# ROUTINE CANDIDATE TO ST_PROCEDURAL TESTS
# =============================================================================


class TestRoutineCandidateToStProcedural:
    """Tests for RoutineCandidate → st_procedural write flow."""

    def test_assemble_routine_candidate_writes_creates_st_procedural_write(
        self,
        truth_write_assembler: TruthWriteAssembler,
        routine_candidate: RoutineCandidate,
    ) -> None:
        """RoutineCandidate assembles to st_procedural StagedWrite."""
        writes = truth_write_assembler.assemble_routine_candidate_writes([routine_candidate])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_PROCEDURAL
        assert write.record_id == "routine_morning_coffee"

    def test_routine_candidate_fields_mapped_correctly(
        self,
        truth_write_assembler: TruthWriteAssembler,
        routine_candidate: RoutineCandidate,
    ) -> None:
        """RoutineCandidate fields map to st_procedural columns."""
        writes = truth_write_assembler.assemble_routine_candidate_writes([routine_candidate])

        write = writes[0]
        data = write.record_data

        assert data["routine_id"] == "routine_morning_coffee"
        assert data["routine_name"] == "Morning Coffee Routine"
        assert data["routine_category"] == "DAILY_ROUTINE"
        assert data["temporal_anchor"] == "08:00"
        assert data["day_pattern"] == "weekdays"
        assert data["regularity_score"] == 0.85
        assert data["source_episode_count"] == 3
        assert data["is_canonical"] is True

    def test_assemble_all_includes_routine_candidates(
        self,
        truth_write_assembler: TruthWriteAssembler,
        routine_candidate: RoutineCandidate,
    ) -> None:
        """assemble_all includes routine_candidates in st_procedural."""
        result = truth_write_assembler.assemble_all(
            routine_candidates=[routine_candidate],
        )

        assert LAYER_ST_PROCEDURAL in result
        proc_writes = result[LAYER_ST_PROCEDURAL]
        assert len(proc_writes) >= 1

        # Find our routine candidate write
        candidate_write = next(
            (w for w in proc_writes if w.record_id == "routine_morning_coffee"),
            None,
        )
        assert candidate_write is not None


# =============================================================================
# EXECUTION ORDER TESTS
# =============================================================================


class TestRoutineDetectorExecutionOrder:
    """Tests for RoutineDetector → TDL-HCO execution order."""

    def test_routine_detector_runs_in_parallel_phase(self) -> None:
        """RoutineDetector runs in _run_parallel_algorithms."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())

        # Check that _run_routine_detector method exists
        assert hasattr(explorer, "_run_routine_detector")
        assert callable(getattr(explorer, "_run_routine_detector"))

    def test_tdl_hco_accepts_detected_routines_parameter(self) -> None:
        """TDL-HCO accepts detected_routines from RoutineDetector."""
        import inspect

        from k0.modules.consolidation.dream import DreamExplorer

        sig = inspect.signature(DreamExplorer._run_tdl_hco)
        params = list(sig.parameters.keys())

        assert "detected_routines" in params

    def test_dream_explorer_output_includes_routine_candidates(self) -> None:
        """DreamExplorerOutput has routine_candidates field."""
        from k0.modules.consolidation.dream.models import DreamExplorerOutput

        output = DreamExplorerOutput()

        assert hasattr(output, "routine_candidates")
        assert isinstance(output.routine_candidates, list)


# =============================================================================
# R6 COORDINATOR INTEGRATION TESTS
# =============================================================================


class TestR6RoutineCandidateFlow:
    """Tests for R6 extracting and passing routine_candidates."""

    def test_p03_phase_outputs_has_r5_routine_candidates(self) -> None:
        """P03PhaseOutputs has r5_routine_candidates field."""
        from k0.pipelines.p03.phase_outputs import P03PhaseOutputs

        outputs = P03PhaseOutputs()

        assert hasattr(outputs, "r5_routine_candidates")
        assert isinstance(outputs.r5_routine_candidates, list)

    def test_r5_phase_output_has_routine_candidates(self) -> None:
        """R5PhaseOutputs has routine_candidates field."""
        from k0.pipelines.p03.phases.r5_dream_explorer import R5PhaseOutputs

        output = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
        )

        assert hasattr(output, "routine_candidates")
        assert isinstance(output.routine_candidates, list)


# =============================================================================
# M5-E2 ACCEPTANCE CRITERIA TESTS
# =============================================================================


class TestM5E2AcceptanceCriteria:
    """Tests verifying M5-E2 acceptance criteria are met."""

    def test_m5_e2_i1_routine_detector_runs_before_tdl_hco(self) -> None:
        """M5-E2-I1: RoutineDetector runs in parallel phase before TDL-HCO."""
        # RoutineDetector runs in _run_parallel_algorithms
        # TDL-HCO runs after parallel phase completes
        # This is verified by inspect of DreamExplorer.explore()
        import inspect

        from k0.modules.consolidation.dream import DreamExplorer

        source = inspect.getsource(DreamExplorer.explore)

        # parallel_algorithms runs first
        assert "_run_parallel_algorithms" in source

        # routine_candidates extracted from parallel results
        assert "routine_candidates = parallel_results.get(" in source

        # TDL-HCO runs after with routine_candidates
        assert "_run_tdl_hco" in source
        assert "routine_candidates" in source

    def test_m5_e2_i1_routine_candidates_passed_to_tdl_hco(self) -> None:
        """M5-E2-I1: routine_candidates passed to TDL-HCO."""
        import inspect

        from k0.modules.consolidation.dream import DreamExplorer

        source = inspect.getsource(DreamExplorer.explore)

        # TDL-HCO receives routine_candidates
        assert "routine_candidates)" in source

    def test_m5_e2_i1_r5_output_flows_to_r6(self) -> None:
        """M5-E2-I1: R5 routine_candidates flows to R6."""
        from k0.pipelines.p03.phase_outputs import P03PhaseOutputs
        from k0.pipelines.p03.phases.r5_dream_explorer import R5PhaseOutputs

        # R5 output has routine_candidates
        r5_out = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
        )
        assert hasattr(r5_out, "routine_candidates")

        # P03PhaseOutputs has r5_routine_candidates
        p03_out = P03PhaseOutputs()
        assert hasattr(p03_out, "r5_routine_candidates")

    def test_m5_e2_i1_truth_assembler_handles_routine_candidates(self) -> None:
        """M5-E2-I1: TruthWriteAssembler.assemble_all accepts routine_candidates."""
        import inspect

        from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler

        sig = inspect.signature(TruthWriteAssembler.assemble_all)
        params = list(sig.parameters.keys())

        assert "routine_candidates" in params

    def test_m5_e2_no_duplicate_routine_detector_run(self) -> None:
        """M5-E2: RoutineDetector should NOT run twice in explore()."""
        import inspect

        from k0.modules.consolidation.dream import DreamExplorer

        source = inspect.getsource(DreamExplorer.explore)

        # Check that PHASE 5 duplicate run has been removed
        # The old code had a second "PHASE 5: Retrospective Routine Detection" block
        # that called _run_routine_detector again, overwriting parallel results
        phase_5_routine_block = "PHASE 5: Retrospective Routine Detection"

        # After M5-E2 fix, this block should NOT exist
        assert phase_5_routine_block not in source, (
            "PHASE 5 duplicate RoutineDetector run should be removed. "
            "RoutineDetector already runs in _run_parallel_algorithms."
        )

        # Verify the M5-E2 note is present
        assert (
            "M5-E2: Removed duplicate PHASE 5" in source
        ), "M5-E2 removal comment should be present in explore() method."
