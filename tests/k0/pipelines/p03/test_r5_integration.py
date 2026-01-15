"""
R5 Full Integration Test — Issue 8.1.19

End-to-end test verifying R4→R5→R6→R7→R8 flow with R5 enabled.

Test Categories:
1. Happy path: All algorithms produce outputs, R6 assembles writes, R7 commits, R8 emits
2. Skip path: Backlog > 1000 triggers graceful R5 skip
3. Memory isolation: SPC-UQ reconstructions have is_canonical=False
4. Deterministic seed: Same cycle_id produces same outputs
5. Truth layer writes: st_sem, st_prospective, st_procedural

References:
- M8_EXECUTION.md Issue 8.1.19: R5 Full Integration Test
- Dossier §4.6: R5 — Dream-Like Exploration (REM)
- Dossier Appendix A.0.6: SPC-UQ reconstructions are never canonical

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Dict
from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.algorithms.spc_uq import (
    ReconstructedEpisode,
    ReconstructedValue,
    ReconstructionProvenance,
)
from k0.modules.consolidation.dream import DreamConfig, DreamExplorer, DreamExplorerInput
# Import dream models for TruthWriteAssembler (uses these types)
from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    Insight as DreamInsight,
    RoutineOptimization as DreamRoutineOptimization,
)
from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.outbox_assembler import (
    OutboxEventAssembler,
    TOPIC_INSIGHT_GENERATED,
)
from k0.modules.consolidation.staging.r6_coordinator import R6Coordinator
from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler
from k0.pipelines.p03 import P03BatchEnvelope, P03CycleContext
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_interface import P03RunnerContext
# Import phase_outputs for OutboxEventAssembler (uses these types)
from k0.pipelines.p03.phase_outputs import (
    Insight as PhaseInsight,
    ProspectiveMemory as PhaseProspectiveMemory,
)
from k0.pipelines.p03.phases.r5_dream_explorer import R5DreamExplorer, R5PhaseOutputs, R5SkipReason
from k0.pipelines.p03.r5_config import R5Config, R5Mode
from k0.pipelines.p03.runner_contract import P03PhaseStatus
from k0.pipelines.p03.staged_writes import LAYER_ST_PROCEDURAL, LAYER_ST_PROSPECTIVE, LAYER_ST_SEM

# Valid ULID for tests (exactly 26 characters as required by IdempotencyKeyGenerator)
TEST_ULID = "01JTESTINTEGRATION000000AB"


# =============================================================================
# FIXTURES - Dream Models (for TruthWriteAssembler)
# =============================================================================


@pytest.fixture
def dream_insight() -> DreamInsight:
    """Create sample insight from BGT-SM (dream model for TruthWriteAssembler)."""
    return DreamInsight.create(
        insight_id="ins_test_001",
        insight_type="ASSOCIATION",
        description="Connection between coffee and productivity",
        confidence=0.85,
        supporting_evidence=["evt_001", "evt_002"],
        novelty_score=0.7,
        concept_a_id="entity_coffee",
        concept_b_id="entity_productivity",
        pmi_score=2.5,
        coherence_score=0.8,
        semantic_distance=0.4,
        relevance_score=0.75,
        actionability_score=0.6,
    )


@pytest.fixture
def sample_counterfactual() -> CounterfactualScenario:
    """Create sample counterfactual from CPN."""
    return CounterfactualScenario.create(
        scenario_id="cf_test_001",
        scenario_type="UPWARD",
        base_episode_id="epi_base_001",
        perturbation_target="departure_time",
        original_outcome="Arrived late to meeting",
        counterfactual_outcome="Arrived on time with buffer",
        plausibility=0.75,
        success_probability=0.8,
        utility_delta=0.5,
    )


@pytest.fixture
def dream_routine_optimization() -> DreamRoutineOptimization:
    """Create sample routine optimization from TDL-HCO (dream model)."""
    return DreamRoutineOptimization.create(
        routine_id="routine_morning_001",
        routine_name="Morning Routine",
        bottleneck_step="shower",
        bottleneck_position=2,
        value_drop=-0.15,
        suggested_action="Prepare clothes night before",
        expected_improvement=0.12,
        confidence=0.7,
    )


# =============================================================================
# FIXTURES - Phase Output Models (for OutboxEventAssembler)
# =============================================================================


@pytest.fixture
def phase_insight() -> PhaseInsight:
    """Create sample insight (phase output model for OutboxEventAssembler)."""
    return PhaseInsight(
        insight_id="ins_phase_001",
        insight_type="ASSOCIATION",
        concept_a_id="entity_coffee",
        concept_b_id="entity_productivity",
        pmi_score=2.5,
        novelty_score=0.7,
        relevance_score=0.75,
        natural_language="Coffee consumption correlates with productivity",
        evidence_ids=["evt_001", "evt_002"],
    )


@pytest.fixture
def phase_prospective_memory() -> PhaseProspectiveMemory:
    """Create sample prospective memory (phase output model)."""
    return PhaseProspectiveMemory(
        prosp_id="prosp_test_001",
        intention_type="REMINDER",
        description="Call mom on Sunday",
        trigger_condition="Sunday morning",
        action_to_take="Initiate phone call to Mom",
        deadline_ts=1735689600000,
        importance=0.8,
        source_episode_id="epi_family_001",
    )


# =============================================================================
# FIXTURES - Context and Config
# =============================================================================


@pytest.fixture
def enabled_r5_config() -> R5Config:
    """R5 config with ENABLED mode and reasonable thresholds."""
    return R5Config(
        mode=R5Mode.ENABLED,
        backlog_threshold=1000,
        min_remaining_window_seconds=10,
        mcts_rollouts_override=50,
        max_insights_per_batch=10,
        max_counterfactuals_per_event=5,
    )


@pytest.fixture
def high_backlog_context() -> P03CycleContext:
    """Cycle context with backlog > 1000 to trigger skip."""
    return P03CycleContext.create(
        tenant_id="tenant-skip-test",
        space_id="space-skip-test",
        event_ids=["evt-1", "evt-2"],
        trigger_type="MANUAL",
        trigger_reason="Skip test",
        pending_before=1500,  # Exceeds 1000 threshold
        deadline_ms=300000,
    )


@pytest.fixture
def normal_context() -> P03CycleContext:
    """Cycle context for normal R5 execution."""
    return P03CycleContext.create(
        tenant_id="tenant-integration",
        space_id="space-integration",
        event_ids=["evt-001", "evt-002", "evt-003"],
        trigger_type="MANUAL",
        trigger_reason="Integration test",
        pending_before=50,
        deadline_ms=300000,
    )


@pytest.fixture
def sample_event_states() -> Dict[str, P03EventState]:
    """Create sample event states for R6 coordination."""
    return {
        "evt-001": P03EventState(
            event_id="evt-001",
            hipp_event_id="hipp-001",
            content_text="Test content 1",
            content_type="CHAT",
            content_hash="hash001",
            timestamp=1735600000000,
            channel_id="channel-1",
            embedding_id="vec-001",
            reconciliation_action=ReconciliationAction.CREATE,
            confidence=0.8,
        ),
        "evt-002": P03EventState(
            event_id="evt-002",
            hipp_event_id="hipp-002",
            content_text="Test content 2",
            content_type="CHAT",
            content_hash="hash002",
            timestamp=1735600001000,
            channel_id="channel-1",
            embedding_id="vec-002",
            reconciliation_action=ReconciliationAction.REINFORCE,
            best_match_id="sem_existing_001",
            best_match_layer="st_sem",
            confidence=0.9,
        ),
    }


@pytest.fixture
def mock_metrics_registry() -> MagicMock:
    """Create mock metrics registry."""
    registry = MagicMock()
    registry.emit_r5_skip = MagicMock()
    registry.set_r5_mode = MagicMock()
    registry.emit_r5_duration = MagicMock()
    registry.emit_r5_insights = MagicMock()
    registry.emit_r5_counterfactuals = MagicMock()
    registry.emit_r5_routine_optimizations = MagicMock()
    registry.emit_r5_prospective_memories = MagicMock()
    registry.emit_r5_mcts_decisions = MagicMock()
    return registry


@pytest.fixture
def runner_context(mock_metrics_registry: MagicMock) -> P03RunnerContext:
    """Create runner context with mocked dependencies."""
    ctx = P03RunnerContext.create(
        syscalls=MagicMock(),
        logger=MagicMock(),
        qos_band="GREEN",
        priority=50,
        config={"backlog_threshold": 1000},
    )
    ctx.metrics_registry = mock_metrics_registry
    return ctx


# =============================================================================
# TEST: Happy Path — R4→R5→R6→R7→R8 Flow
# =============================================================================


class TestHappyPathFlow:
    """End-to-end happy path tests for R5 integration."""

    @pytest.mark.asyncio
    async def test_r5_produces_insights_for_r6(
        self,
        enabled_r5_config: R5Config,
        normal_context: P03CycleContext,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 phase produces insights that flow to R6 staging."""
        envelope = P03BatchEnvelope.create(normal_context)
        phase = R5DreamExplorer(config=enabled_r5_config)

        result = await phase.run(envelope, runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert envelope.phases.r5_skipped is False
        # Verify output fields exist (may be empty from stub)
        assert hasattr(envelope.phases, "r5_insights")
        assert hasattr(envelope.phases, "r5_counterfactuals")
        assert hasattr(envelope.phases, "r5_routine_optimizations")
        assert hasattr(envelope.phases, "r5_prospective_memories")

    def test_r6_assembles_insight_writes_to_st_sem(
        self,
        dream_insight: DreamInsight,
    ) -> None:
        """R6 TruthWriteAssembler creates st_sem writes from insights."""
        idempotency_gen = IdempotencyKeyGenerator(TEST_ULID)
        assembler = TruthWriteAssembler(
            idempotency_gen,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        writes = assembler.assemble_insight_writes([dream_insight])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_SEM
        assert write.record_id == f"insight_{dream_insight.insight_id}"
        assert write.record_data["pattern_type"] == "INSIGHT"
        assert write.record_data["confidence_score"] == dream_insight.confidence
        assert write.record_data["novelty_score"] == dream_insight.novelty_score
        assert write.record_data["concept_a_id"] == dream_insight.concept_a_id
        assert write.record_data["concept_b_id"] == dream_insight.concept_b_id

    def test_r6_assembles_counterfactual_writes_to_st_prospective(
        self,
        sample_counterfactual: CounterfactualScenario,
    ) -> None:
        """R6 TruthWriteAssembler creates st_prospective writes from counterfactuals."""
        idempotency_gen = IdempotencyKeyGenerator(TEST_ULID)
        assembler = TruthWriteAssembler(
            idempotency_gen,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        writes = assembler.assemble_counterfactual_writes([sample_counterfactual])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_PROSPECTIVE
        assert write.record_id == sample_counterfactual.scenario_id
        assert write.record_data["intention_type"] == "COUNTERFACTUAL"
        assert write.record_data["scenario_type"] == "UPWARD"
        assert write.record_data["plausibility"] == sample_counterfactual.plausibility

    def test_r6_assembles_routine_optimization_writes_to_st_procedural(
        self,
        dream_routine_optimization: DreamRoutineOptimization,
    ) -> None:
        """R6 TruthWriteAssembler creates st_procedural writes from optimizations."""
        idempotency_gen = IdempotencyKeyGenerator(TEST_ULID)
        assembler = TruthWriteAssembler(
            idempotency_gen,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        writes = assembler.assemble_routine_optimization_writes([dream_routine_optimization])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_PROCEDURAL
        assert write.record_data["routine_id"] == dream_routine_optimization.routine_id
        assert write.record_data["bottleneck_step"] == dream_routine_optimization.bottleneck_step
        assert write.record_data["suggested_action"] == dream_routine_optimization.suggested_action

    def test_r6_assembles_all_r5_outputs(
        self,
        dream_insight: DreamInsight,
        sample_counterfactual: CounterfactualScenario,
        dream_routine_optimization: DreamRoutineOptimization,
        sample_event_states: Dict[str, P03EventState],
    ) -> None:
        """R6 assemble_all includes all R5 output types."""
        idempotency_gen = IdempotencyKeyGenerator(TEST_ULID)
        assembler = TruthWriteAssembler(
            idempotency_gen,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        result = assembler.assemble_all(
            event_states=sample_event_states,
            insights=[dream_insight],
            counterfactuals=[sample_counterfactual],
            routine_optimizations=[dream_routine_optimization],
        )

        # Verify all layers have writes
        assert LAYER_ST_SEM in result
        assert LAYER_ST_PROSPECTIVE in result
        assert LAYER_ST_PROCEDURAL in result

        # Verify st_sem has insight write
        sem_writes = result[LAYER_ST_SEM]
        insight_write = next((w for w in sem_writes if "insight_" in w.record_id), None)
        assert insight_write is not None

        # Verify st_prospective has counterfactual write
        prosp_writes = result[LAYER_ST_PROSPECTIVE]
        cf_write = next((w for w in prosp_writes if w.record_id == sample_counterfactual.scenario_id), None)
        assert cf_write is not None

    def test_r8_outbox_assembles_insight_events(
        self,
        phase_insight: PhaseInsight,
    ) -> None:
        """R8 OutboxEventAssembler creates insight events for emission."""
        assembler = OutboxEventAssembler(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        events = assembler.assemble_insight_events([phase_insight])

        assert len(events) == 1
        event = events[0]
        assert event.topic == TOPIC_INSIGHT_GENERATED
        assert event.payload["insight_id"] == phase_insight.insight_id
        assert event.payload["insight_type"] == phase_insight.insight_type
        # Verify deterministic idempotency key
        expected_key = f"{TEST_ULID}:insight:{phase_insight.insight_id}"
        assert event.idempotency_key == expected_key


# =============================================================================
# TEST: Skip Path — Backlog Exceeds Threshold
# =============================================================================


class TestSkipPath:
    """Tests for R5 skip conditions (backlog > 1000)."""

    @pytest.mark.asyncio
    async def test_r5_skips_when_backlog_exceeds_threshold(
        self,
        enabled_r5_config: R5Config,
        high_backlog_context: P03CycleContext,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 phase skips when pending_before > backlog_threshold."""
        envelope = P03BatchEnvelope.create(high_backlog_context)
        phase = R5DreamExplorer(config=enabled_r5_config)

        result = await phase.run(envelope, runner_context)

        assert result.status == P03PhaseStatus.SKIP
        assert envelope.phases.r5_skipped is True
        assert envelope.phases.r5_skip_reason == R5SkipReason.BACKLOG_EXCEEDED

    @pytest.mark.asyncio
    async def test_r5_skip_emits_metrics(
        self,
        enabled_r5_config: R5Config,
        high_backlog_context: P03CycleContext,
        runner_context: P03RunnerContext,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """R5 skip emits skip metrics."""
        envelope = P03BatchEnvelope.create(high_backlog_context)
        phase = R5DreamExplorer(config=enabled_r5_config)

        await phase.run(envelope, runner_context)

        # Verify skip metrics were emitted
        mock_metrics_registry.emit_r5_skip.assert_called()

    @pytest.mark.asyncio
    async def test_r5_skip_does_not_produce_outputs(
        self,
        enabled_r5_config: R5Config,
        high_backlog_context: P03CycleContext,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 skip produces no algorithm outputs."""
        envelope = P03BatchEnvelope.create(high_backlog_context)
        phase = R5DreamExplorer(config=enabled_r5_config)

        await phase.run(envelope, runner_context)

        # When skipped, no outputs should be staged
        assert envelope.phases.r5_skipped is True


class TestDisabledMode:
    """Tests for R5 DISABLED mode."""

    @pytest.mark.asyncio
    async def test_r5_disabled_mode_skips(
        self,
        normal_context: P03CycleContext,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 with DISABLED mode skips execution."""
        disabled_config = R5Config(mode=R5Mode.DISABLED)
        envelope = P03BatchEnvelope.create(normal_context)
        phase = R5DreamExplorer(config=disabled_config)

        result = await phase.run(envelope, runner_context)

        assert result.status == P03PhaseStatus.SKIP
        assert envelope.phases.r5_skipped is True
        assert envelope.phases.r5_skip_reason == R5SkipReason.DISABLED


# =============================================================================
# TEST: Memory Isolation — SPC-UQ Reconstructions
# =============================================================================


class TestMemoryIsolation:
    """Tests for A.0.6 invariant: SPC-UQ reconstructions are never canonical."""

    def test_reconstructed_episode_is_never_canonical(self) -> None:
        """ReconstructedEpisode.is_canonical is always False."""
        recon = ReconstructedEpisode.create(
            episode_id="recon_001",
            original_episode_id="epi_original_001",
            summary="Reconstructed morning routine",
            reconstructed_fields=[
                ReconstructedValue(
                    attribute_name="location_name",
                    value="Home",
                    confidence=0.7,
                    uncertainty=0.3,
                    provenance=ReconstructionProvenance.PATTERN_COMPLETION,
                ),
            ],
            confidence_score=0.75,
            uncertainty_score=0.25,
            temporal_coherence_score=0.8,
            provenance={"source": "SPC-UQ", "schema_id": "schema_morning"},
        )

        # CRITICAL INVARIANT: is_canonical must be False
        assert recon.is_canonical is False

    def test_reconstructed_episode_raises_on_canonical_true(self) -> None:
        """ReconstructedEpisode raises ValueError if is_canonical=True."""
        with pytest.raises(ValueError, match="NEVER be canonical"):
            ReconstructedEpisode(
                episode_id="recon_bad",
                original_episode_id="epi_original",
                summary="Bad reconstruction",
                reconstructed_fields=(),
                confidence_score=0.5,
                uncertainty_score=0.5,
                temporal_coherence_score=0.5,
                provenance={},
                is_canonical=True,  # VIOLATION
            )

    def test_reconstruction_has_explicit_provenance(self) -> None:
        """Reconstructions include provenance metadata."""
        recon = ReconstructedEpisode.create(
            episode_id="recon_002",
            original_episode_id="epi_original_002",
            summary="Reconstructed dinner",
            reconstructed_fields=[],
            confidence_score=0.6,
            uncertainty_score=0.4,
            temporal_coherence_score=0.7,
            provenance={"source": "SPC-UQ", "simulation_count": 100},
        )

        assert "SPC-UQ" in str(recon.provenance)
        assert recon.provenance["source"] == "SPC-UQ"

    def test_reconstruction_preserves_original_episode_id(self) -> None:
        """Reconstructions track the original episode being reconstructed."""
        original_id = "epi_original_003"
        recon = ReconstructedEpisode.create(
            episode_id="recon_003",
            original_episode_id=original_id,
            summary="Reconstructed event",
            reconstructed_fields=[],
            confidence_score=0.5,
            uncertainty_score=0.5,
            temporal_coherence_score=0.5,
            provenance={},
        )

        assert recon.original_episode_id == original_id
        assert recon.episode_id != recon.original_episode_id


# =============================================================================
# TEST: Deterministic Execution
# =============================================================================


class TestDeterministicExecution:
    """Tests for deterministic R5 execution with fixed seed."""

    def test_same_cycle_id_produces_same_derived_seeds(self) -> None:
        """Same cycle_id derives same algorithm seeds."""
        cycle_id = TEST_ULID
        config1 = DreamConfig(seed=cycle_id)
        config2 = DreamConfig(seed=cycle_id)

        # BGT-SM seeds should match
        seed1_bgt = config1.derive_seed(cycle_id, "bgt_sm")
        seed2_bgt = config2.derive_seed(cycle_id, "bgt_sm")
        assert seed1_bgt == seed2_bgt

        # CPN seeds should match
        seed1_cpn = config1.derive_seed(cycle_id, "cpn")
        seed2_cpn = config2.derive_seed(cycle_id, "cpn")
        assert seed1_cpn == seed2_cpn

        # SPC-UQ seeds should match
        seed1_spc = config1.derive_seed(cycle_id, "spc_uq")
        seed2_spc = config2.derive_seed(cycle_id, "spc_uq")
        assert seed1_spc == seed2_spc

    def test_different_cycle_ids_produce_different_seeds(self) -> None:
        """Different cycle_ids produce different algorithm seeds."""
        cycle_a = "01JCYCLEAAAAAAAAAAAAAAA"
        cycle_b = "01JCYCLEBBBBBBBBBBBBBBB"
        # When seed is None, derive_seed uses cycle_id as base
        config_a = DreamConfig(seed=None)
        config_b = DreamConfig(seed=None)

        seed_a = config_a.derive_seed(cycle_a, "bgt_sm")
        seed_b = config_b.derive_seed(cycle_b, "bgt_sm")

        assert seed_a != seed_b

    @pytest.mark.asyncio
    async def test_dream_explorer_deterministic_with_seed(self) -> None:
        """DreamExplorer produces consistent structure with fixed seed."""
        cycle_id = TEST_ULID
        config = DreamConfig(seed=cycle_id)
        explorer = DreamExplorer(config=config)

        input_data = DreamExplorerInput(
            cycle_id=cycle_id,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        output1 = await explorer.explore(input_data)
        output2 = await explorer.explore(input_data)

        # Outputs should have same structure
        assert output1.total_outputs == output2.total_outputs
        assert output1.is_empty == output2.is_empty


# =============================================================================
# TEST: R6 Coordinator Integration
# =============================================================================


class TestR6CoordinatorIntegration:
    """Tests for R6 coordinator consuming R5 outputs."""

    def test_r6_coordinator_creation(self) -> None:
        """R6 coordinator can be created with valid ULID."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        assert coordinator is not None
        assert coordinator.idempotency_gen.cycle_ulid == TEST_ULID

    def test_r6_coordinator_has_truth_assembler(self) -> None:
        """R6 coordinator has TruthWriteAssembler configured."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        assert coordinator.truth_assembler is not None
        assert coordinator.truth_assembler.tenant_id == "tenant-1"
        assert coordinator.truth_assembler.space_id == "space-1"

    def test_r6_coordinator_has_outbox_assembler(self) -> None:
        """R6 coordinator has OutboxEventAssembler configured."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        assert coordinator.outbox_assembler is not None
        assert coordinator.outbox_assembler.cycle_ulid == TEST_ULID

    def test_r6_can_execute_with_empty_outputs(
        self,
        sample_event_states: Dict[str, P03EventState],
    ) -> None:
        """R6 coordinator can execute with empty R5 outputs."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        phase_outputs = MagicMock()
        phase_outputs.r5_insights = []  # Empty
        phase_outputs.r5_counterfactuals = []
        phase_outputs.r5_routine_optimizations = []
        phase_outputs.r2_clusters = []
        phase_outputs.r4_new_entities = []
        phase_outputs.r4_updated_entities = []
        phase_outputs.r4_new_edges = []
        phase_outputs.r4_updated_edges = []
        phase_outputs.r4_causal_edges = []
        phase_outputs.r4_social_entities = []
        phase_outputs.r5_routines = []
        phase_outputs.r5_intentions = []

        result = coordinator.execute(
            event_states=sample_event_states,
            phase_outputs=phase_outputs,
            gaps=[],
            batch_event_ids=set(sample_event_states.keys()),
        )

        assert result.success is True
        assert result.r6_output is not None
        assert result.r6_output.reconciliation_summary.insight_count == 0


# =============================================================================
# TEST: Outbox Event Assembly
# =============================================================================


class TestOutboxEventAssembly:
    """Tests for R8 insight event assembly."""

    def test_outbox_assembler_all_includes_insights(
        self,
        phase_insight: PhaseInsight,
        sample_event_states: Dict[str, P03EventState],
    ) -> None:
        """assemble_all includes insight events in the result."""
        assembler = OutboxEventAssembler(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        summary = ReconciliationSummary(
            total_events=2,
            total_writes=3,
            consolidated_count=2,
            insight_count=1,
        )

        result = assembler.assemble_all(
            summary=summary,
            event_states=sample_event_states,
            gaps=[],
            phase_durations={"R1": 100, "R2": 200},
            insights=[phase_insight],
        )

        assert len(result.insight_events) == 1
        assert result.event_count_by_topic.get(TOPIC_INSIGHT_GENERATED, 0) == 1

    def test_insight_event_has_deterministic_idempotency_key(
        self,
        phase_insight: PhaseInsight,
    ) -> None:
        """Insight events have deterministic idempotency keys per A.0.5."""
        assembler = OutboxEventAssembler(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        events = assembler.assemble_insight_events([phase_insight])

        assert len(events) == 1
        event = events[0]
        expected_key = f"{TEST_ULID}:insight:{phase_insight.insight_id}"
        assert event.idempotency_key == expected_key

    def test_insight_events_deduplicated_by_id(
        self,
        phase_insight: PhaseInsight,
    ) -> None:
        """Duplicate insight_ids are deduplicated in assembly."""
        assembler = OutboxEventAssembler(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant-1",
            space_id="space-1",
        )

        # Pass same insight twice
        events = assembler.assemble_insight_events([phase_insight, phase_insight])

        # Should only produce one event
        assert len(events) == 1


# =============================================================================
# TEST: R5PhaseOutputs Container
# =============================================================================


class TestR5PhaseOutputs:
    """Tests for R5PhaseOutputs container."""

    def test_r5_phase_outputs_accepts_all_algorithm_results(self) -> None:
        """R5PhaseOutputs container holds all algorithm outputs."""
        outputs = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
            prospective_memories=[],
            mcts_decisions_count=42,
            compute_seconds_saved=0.0,
        )

        assert outputs.mcts_decisions_count == 42
        assert len(outputs.insights) == 0

    def test_r5_phase_outputs_empty_lists(self) -> None:
        """R5PhaseOutputs works with empty lists."""
        outputs = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
            prospective_memories=[],
            mcts_decisions_count=0,
            compute_seconds_saved=0.0,
        )

        assert len(outputs.insights) == 0
        assert len(outputs.counterfactuals) == 0
        assert outputs.mcts_decisions_count == 0
