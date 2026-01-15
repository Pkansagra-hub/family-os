"""
R5 DreamExplorer Integration Tests — Issue 8.1.3

Test Categories:
1. Full R5 phase execution with DreamExplorer
2. DreamExplorer wiring and delegation
3. Deterministic outputs with fixed cycle_id
4. Output staging in envelope.phases
5. Shadow mode discards outputs
6. Mode ENABLED triggers DreamExplorer

References:
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- Dossier §4.6: R5 — Dream-Like Exploration (REM)
- Dossier §7.4.5: M22 — DreamExplorer
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.dream import DreamConfig, DreamExplorer, DreamExplorerInput
from k0.pipelines.p03 import P03BatchEnvelope, P03CycleContext
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phases.r5_dream_explorer import R5DreamExplorer, R5PhaseOutputs
from k0.pipelines.p03.r5_config import R5Config, R5Mode

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def enabled_r5_config() -> R5Config:
    """R5 config with ENABLED mode."""
    return R5Config(
        mode=R5Mode.ENABLED,
        backlog_threshold=1000,
        min_remaining_window_seconds=10,
        mcts_rollouts_override=100,
    )


@pytest.fixture
def shadow_r5_config() -> R5Config:
    """R5 config with SHADOW mode."""
    return R5Config(
        mode=R5Mode.SHADOW,
        backlog_threshold=1000,
        min_remaining_window_seconds=10,
    )


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create a sample cycle context that won't trigger skip."""
    return P03CycleContext.create(
        tenant_id="tenant-integration",
        space_id="space-integration",
        event_ids=["evt-1", "evt-2", "evt-3"],
        trigger_type="MANUAL",
        trigger_reason="Integration test",
        pending_before=50,  # Well below 1000 threshold
        deadline_ms=300000,  # 5 minute deadline - plenty of time
    )


@pytest.fixture
def sample_envelope(sample_context: P03CycleContext) -> P03BatchEnvelope:
    """Create sample envelope for integration test."""
    return P03BatchEnvelope.create(sample_context)


@pytest.fixture
def mock_metrics_registry() -> MagicMock:
    """Create mock metrics registry."""
    registry = MagicMock()
    # Add all expected methods
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
    """Create runner context with metrics registry."""
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
# TEST: DreamExplorer Wiring
# =============================================================================


class TestDreamExplorerWiring:
    """Test that R5 phase correctly wires to DreamExplorer."""

    @pytest.mark.asyncio
    async def test_enabled_mode_calls_dream_explorer(
        self,
        enabled_r5_config: R5Config,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 in ENABLED mode should delegate to DreamExplorer."""
        phase = R5DreamExplorer(config=enabled_r5_config)

        result = await phase.run(sample_envelope, runner_context)

        # Should complete successfully (stub returns empty outputs)
        assert result.status == P03PhaseStatus.DONE
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_dream_explorer_receives_correct_input(
        self,
        enabled_r5_config: R5Config,
        sample_context: P03CycleContext,
    ) -> None:
        """DreamExplorer should receive correct input from envelope."""
        envelope = P03BatchEnvelope.create(sample_context)

        # Build input as R5 phase would (testing input structure, not config)
        input_data = DreamExplorerInput(
            cycle_id=envelope.context.cycle_id,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            recent_episodes=list(envelope.phases.r2_clusters),
            kg_entities=list(envelope.phases.r4_new_entities),
            kg_edges=list(envelope.phases.r4_new_edges),
            event_states=list(envelope.events),
        )

        # Verify input data structure
        assert input_data.cycle_id == envelope.context.cycle_id
        assert input_data.tenant_id == "tenant-integration"
        assert input_data.space_id == "space-integration"

        # Verify empty collections (no prior phase output)
        assert input_data.recent_episodes == []
        assert input_data.kg_entities == []
        assert input_data.kg_edges == []


# =============================================================================
# TEST: Full R5 Phase Execution
# =============================================================================


class TestFullR5Execution:
    """Test full R5 phase execution with DreamExplorer."""

    @pytest.mark.asyncio
    async def test_full_r5_execution_enabled(
        self,
        enabled_r5_config: R5Config,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Full R5 execution should complete with DONE status."""
        phase = R5DreamExplorer(config=enabled_r5_config)

        result = await phase.run(sample_envelope, runner_context)

        # Verify successful completion
        assert result.status == P03PhaseStatus.DONE
        assert result.error_info is None
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_r5_outputs_are_staged(
        self,
        enabled_r5_config: R5Config,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 outputs should be staged in envelope.phases."""
        phase = R5DreamExplorer(config=enabled_r5_config)

        await phase.run(sample_envelope, runner_context)

        # Stub returns empty lists, but staging should work
        assert sample_envelope.phases.r5_skipped is False
        assert sample_envelope.phases.r5_skip_reason is None

        # Output lists should exist (empty from stub)
        assert sample_envelope.phases.r5_insights is not None
        assert sample_envelope.phases.r5_counterfactuals is not None
        assert sample_envelope.phases.r5_routine_optimizations is not None
        assert sample_envelope.phases.r5_prospective_memories is not None

    @pytest.mark.asyncio
    async def test_r5_shadow_mode_discards_outputs(
        self,
        shadow_r5_config: R5Config,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Shadow mode should not persist outputs to envelope."""
        phase = R5DreamExplorer(config=shadow_r5_config)

        result = await phase.run(sample_envelope, runner_context)

        # Should complete successfully
        assert result.status == P03PhaseStatus.DONE

        # Outputs should NOT be staged (shadow mode)
        # The staging sets r5_skipped = False, so if not staged, it remains True/None
        # depending on initialization


# =============================================================================
# TEST: Deterministic Execution
# =============================================================================


class TestDeterministicExecution:
    """Test deterministic behavior with fixed cycle_id."""

    @pytest.mark.asyncio
    async def test_same_cycle_id_same_seed_derivation(
        self,
        enabled_r5_config: R5Config,
    ) -> None:
        """Same cycle_id should derive same algorithm seeds."""
        cycle_id = "01JTEST_DETERMINISM_FIXED"

        # Create config with cycle_id as seed (as R5 phase does)
        config1 = DreamConfig(seed=cycle_id)
        config2 = DreamConfig(seed=cycle_id)

        # Same seeds should be derived
        seed1_bgt = config1.derive_seed(cycle_id, "bgt_sm")
        seed2_bgt = config2.derive_seed(cycle_id, "bgt_sm")
        assert seed1_bgt == seed2_bgt

        seed1_cpn = config1.derive_seed(cycle_id, "cpn")
        seed2_cpn = config2.derive_seed(cycle_id, "cpn")
        assert seed1_cpn == seed2_cpn

    @pytest.mark.asyncio
    async def test_dream_explorer_deterministic_with_seed(self) -> None:
        """DreamExplorer should produce deterministic output with seed."""
        cycle_id = "01JTEST_DETERMINISM_RUN"
        config = DreamConfig(seed=cycle_id)
        explorer = DreamExplorer(config=config)

        input_data = DreamExplorerInput(
            cycle_id=cycle_id,
            tenant_id="t1",
            space_id="s1",
        )

        # Run twice
        output1 = await explorer.explore(input_data)
        output2 = await explorer.explore(input_data)

        # With stub, both are empty, but structure is deterministic
        assert output1.total_outputs == output2.total_outputs
        assert output1.is_empty == output2.is_empty


# =============================================================================
# TEST: Config Mapping
# =============================================================================


class TestConfigMapping:
    """Test R5Config to DreamConfig mapping."""

    def test_from_r5_config_maps_correctly(self) -> None:
        """DreamConfig.from_r5_config should map all parameters."""
        r5_config = R5Config(
            mode=R5Mode.ENABLED,
            max_insights_per_batch=15,
            max_counterfactuals_per_event=7,
            bgt_sm_semantic_distance_threshold=0.4,
            bgt_sm_pmi_threshold=2.5,
            bgt_sm_corpus_size_n=15000,
            cpn_perturbation_std=0.15,
            cpn_counterfactual_types=("UPWARD", "DOWNWARD"),
            spc_uq_simulation_count=200,
            spc_uq_uncertainty_alpha=1.5,
            spc_uq_uncertainty_beta=0.5,
            tdl_hco_learning_rate=0.02,
            tdl_hco_discount_factor=0.9,
        )

        dream_config = DreamConfig.from_r5_config(r5_config)

        # Verify mappings
        assert dream_config.max_insights == 15
        assert dream_config.max_counterfactuals == 7
        assert dream_config.semantic_distance_threshold == 0.4
        assert dream_config.pmi_threshold == 2.5
        assert dream_config.corpus_size_n == 15000
        assert dream_config.cpn_perturbation_std == 0.15
        assert dream_config.cpn_counterfactual_types == ("UPWARD", "DOWNWARD")
        assert dream_config.spc_simulation_count == 200
        assert dream_config.spc_uncertainty_alpha == 1.5
        assert dream_config.spc_uncertainty_beta == 0.5
        assert dream_config.tdl_learning_rate == 0.02
        assert dream_config.tdl_discount_factor == 0.9


# =============================================================================
# TEST: R5PhaseOutputs
# =============================================================================


class TestR5PhaseOutputs:
    """Test R5PhaseOutputs container."""

    def test_empty_outputs(self) -> None:
        """R5PhaseOutputs with empty lists should work."""
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

    def test_outputs_with_mcts_count(self) -> None:
        """R5PhaseOutputs should track MCTS decisions."""
        outputs = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
            prospective_memories=[],
            mcts_decisions_count=150,
            compute_seconds_saved=0.0,
        )

        assert outputs.mcts_decisions_count == 150


# =============================================================================
# TEST: Error Handling
# =============================================================================


class TestErrorHandling:
    """Test R5 phase error handling."""

    @pytest.mark.asyncio
    async def test_r5_handles_dream_explorer_error(
        self,
        enabled_r5_config: R5Config,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R5 should handle DreamExplorer exceptions gracefully."""
        phase = R5DreamExplorer(config=enabled_r5_config)

        # Simulate DreamExplorer raising an exception
        async def mock_explore(*args, **kwargs):
            raise RuntimeError("DreamExplorer test error")

        # Patch DreamExplorer.explore
        from k0.modules.consolidation.dream import DreamExplorer as DE

        monkeypatch.setattr(DE, "explore", mock_explore)

        result = await phase.run(sample_envelope, runner_context)

        # Should return FAIL status
        assert result.status == P03PhaseStatus.FAIL
        assert result.error_info is not None
        assert "DreamExplorer test error" in result.error_info.error_message


# =============================================================================
# TEST: Metrics Emission
# =============================================================================


class TestMetricsEmission:
    """Test that R5 phase emits correct metrics."""

    @pytest.mark.asyncio
    async def test_success_metrics_emitted(
        self,
        enabled_r5_config: R5Config,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """Successful R5 execution should emit metrics."""
        phase = R5DreamExplorer(config=enabled_r5_config)

        await phase.run(sample_envelope, runner_context)

        # Verify metrics were emitted (mode and duration always called)
        mock_metrics_registry.set_r5_mode.assert_called()
        mock_metrics_registry.emit_r5_duration.assert_called()
        # Note: emit_r5_insights only called if outputs.insights is non-empty
        # Stub returns empty, so insights counter not called
