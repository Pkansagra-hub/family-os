"""
Tests for TruthWriteAssembler R5 Output Assembly — Issue 8.1.16

Tests cover:
- assemble_insight_writes() → st_sem writes (pattern_type='INSIGHT')
- assemble_counterfactual_writes() → st_prospective writes
- assemble_routine_optimization_writes() → st_procedural updates
- assemble_all() integration with R5 outputs
"""

from __future__ import annotations

import json

import pytest

from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    Insight,
    RoutineOptimization,
)
from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.truth_write_assembler import (
    LAYER_ST_PROCEDURAL,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    TruthWriteAssembler,
)
from k0.pipelines.p03.staged_writes import WriteOperation


# =============================================================================
# FIXTURES
# =============================================================================


def create_sample_insight():
    """Create a sample Insight for testing."""
    return Insight.create(
        insight_id="ins_001",
        insight_type="ASSOCIATION",
        description="Morning coffee leads to productive work",
        confidence=0.85,
        supporting_evidence=["ep_001", "ep_002", "ep_003"],
        novelty_score=0.72,
        concept_a_id="entity_coffee",
        concept_b_id="entity_productivity",
        pmi_score=3.5,
        semantic_distance=0.75,
        relevance_score=0.8,
        actionability_score=0.6,
    )


def create_sample_counterfactual():
    """Create a sample CounterfactualScenario for testing."""
    return CounterfactualScenario.create(
        scenario_id="cf_001",
        scenario_type="UPWARD",
        base_episode_id="ep_base_001",
        perturbation_target="left_earlier",
        original_outcome="Arrived late to meeting",
        counterfactual_outcome="Arrived on time with margin for coffee",
        plausibility=0.8,
        success_probability=0.75,
        utility_delta=2.5,
    )


def create_sample_routine_optimization():
    """Create a sample RoutineOptimization for testing."""
    return RoutineOptimization.create(
        routine_id="routine_morning",
        routine_name="Morning Routine",
        bottleneck_step="shower",
        bottleneck_position=2,
        value_drop=-2.5,
        suggested_action="Prepare clothes night before to reduce shower-to-dress time",
        expected_improvement=1.2,
        confidence=0.78,
    )


def create_assembler():
    """Create TruthWriteAssembler with test configuration."""
    # ULID must be 26 characters
    idem_gen = IdempotencyKeyGenerator(cycle_ulid="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    return TruthWriteAssembler(
        idempotency_gen=idem_gen,
        source_phase="R5",
        tenant_id="tenant_test",
        space_id="space_test",
    )


# =============================================================================
# TESTS: INSIGHT WRITES
# =============================================================================


class TestAssembleInsightWrites:
    """Tests for assemble_insight_writes()."""

    def test_empty_insights_returns_empty_list(self):
        """Empty insights list returns empty writes."""
        assembler = create_assembler()

        result = assembler.assemble_insight_writes([])

        assert result == []

    def test_insight_creates_st_sem_insert(self):
        """Insight creates st_sem INSERT write."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result = assembler.assemble_insight_writes([insight])

        assert len(result) == 1
        write = result[0]
        assert write.layer == LAYER_ST_SEM
        assert write.operation == WriteOperation.INSERT
        assert write.source_phase == "R5"

    def test_insight_record_has_pattern_type_insight(self):
        """Insight record has pattern_type='INSIGHT'."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result = assembler.assemble_insight_writes([insight])

        write = result[0]
        assert write.record_data["pattern_type"] == "INSIGHT"

    def test_insight_record_has_correct_fields(self):
        """Insight record contains all required fields."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result = assembler.assemble_insight_writes([insight])

        data = result[0].record_data
        assert data["pattern_id"] == "insight_ins_001"
        assert data["pattern_name"] == "Morning coffee leads to productive work"
        assert data["confidence_score"] == 0.85
        assert data["novelty_score"] == 0.72
        assert data["pmi_score"] == 3.5
        assert data["semantic_distance"] == 0.75
        assert data["concept_a_id"] == "entity_coffee"
        assert data["concept_b_id"] == "entity_productivity"
        assert data["insight_type"] == "ASSOCIATION"
        assert data["relevance_score"] == 0.8
        assert data["tenant_id"] == "tenant_test"
        assert data["space_id"] == "space_test"

    def test_insight_supporting_evidence_in_source_episodes(self):
        """Insight supporting_evidence maps to source_episodes_json."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result = assembler.assemble_insight_writes([insight])

        data = result[0].record_data
        episodes = json.loads(data["source_episodes_json"])
        assert episodes == ["ep_001", "ep_002", "ep_003"]
        assert data["source_episode_count"] == 3

    def test_insight_has_idempotency_key(self):
        """Insight write has deterministic idempotency key."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result = assembler.assemble_insight_writes([insight])

        write = result[0]
        assert write.idempotency_key is not None
        assert "insight_ins_001" in write.idempotency_key

    def test_multiple_insights_create_multiple_writes(self):
        """Multiple insights create multiple writes."""
        assembler = create_assembler()
        insight1 = create_sample_insight()
        insight2 = Insight.create(
            insight_id="ins_002",
            insight_type="PATTERN",
            description="Weekly grocery shopping pattern",
            confidence=0.9,
            supporting_evidence=["ep_100"],
            novelty_score=0.5,
        )

        result = assembler.assemble_insight_writes([insight1, insight2])

        assert len(result) == 2
        assert result[0].record_id == "insight_ins_001"
        assert result[1].record_id == "insight_ins_002"


# =============================================================================
# TESTS: COUNTERFACTUAL WRITES
# =============================================================================


class TestAssembleCounterfactualWrites:
    """Tests for assemble_counterfactual_writes()."""

    def test_empty_counterfactuals_returns_empty_list(self):
        """Empty counterfactuals list returns empty writes."""
        assembler = create_assembler()

        result = assembler.assemble_counterfactual_writes([])

        assert result == []

    def test_counterfactual_creates_st_prospective_insert(self):
        """Counterfactual creates st_prospective INSERT write."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result = assembler.assemble_counterfactual_writes([cf])

        assert len(result) == 1
        write = result[0]
        assert write.layer == LAYER_ST_PROSPECTIVE
        assert write.operation == WriteOperation.INSERT
        assert write.source_phase == "R5"

    def test_counterfactual_has_intention_type_counterfactual(self):
        """Counterfactual record has intention_type='COUNTERFACTUAL'."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result = assembler.assemble_counterfactual_writes([cf])

        data = result[0].record_data
        assert data["intention_type"] == "COUNTERFACTUAL"

    def test_counterfactual_record_has_correct_fields(self):
        """Counterfactual record contains all required fields."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result = assembler.assemble_counterfactual_writes([cf])

        data = result[0].record_data
        assert data["prosp_id"] == "cf_001"
        assert data["scenario_type"] == "UPWARD"
        assert data["base_episode_id"] == "ep_base_001"
        assert data["perturbation_target"] == "left_earlier"
        assert data["original_outcome"] == "Arrived late to meeting"
        assert data["plausibility"] == 0.8
        assert data["success_probability"] == 0.75
        assert data["utility_delta"] == 2.5
        assert data["tenant_id"] == "tenant_test"

    def test_counterfactual_has_derived_importance(self):
        """Counterfactual importance is plausibility * success_probability."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result = assembler.assemble_counterfactual_writes([cf])

        data = result[0].record_data
        expected_importance = 0.8 * 0.75  # 0.6
        assert data["importance"] == expected_importance

    def test_counterfactual_source_event_ids(self):
        """Counterfactual includes base_episode_id in source_event_ids."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result = assembler.assemble_counterfactual_writes([cf])

        write = result[0]
        assert "ep_base_001" in write.source_event_ids


# =============================================================================
# TESTS: ROUTINE OPTIMIZATION WRITES
# =============================================================================


class TestAssembleRoutineOptimizationWrites:
    """Tests for assemble_routine_optimization_writes()."""

    def test_empty_optimizations_returns_empty_list(self):
        """Empty optimizations list returns empty writes."""
        assembler = create_assembler()

        result = assembler.assemble_routine_optimization_writes([])

        assert result == []

    def test_optimization_creates_st_procedural_insert(self):
        """Routine optimization creates st_procedural INSERT write."""
        assembler = create_assembler()
        opt = create_sample_routine_optimization()

        result = assembler.assemble_routine_optimization_writes([opt])

        assert len(result) == 1
        write = result[0]
        assert write.layer == LAYER_ST_PROCEDURAL
        assert write.operation == WriteOperation.INSERT
        assert write.source_phase == "R5"

    def test_optimization_record_has_correct_fields(self):
        """Routine optimization record contains all required fields."""
        assembler = create_assembler()
        opt = create_sample_routine_optimization()

        result = assembler.assemble_routine_optimization_writes([opt])

        data = result[0].record_data
        assert data["routine_id"] == "routine_morning"
        assert data["routine_name"] == "Morning Routine"
        assert data["bottleneck_step"] == "shower"
        assert data["bottleneck_position"] == 2
        assert data["value_drop"] == -2.5
        assert "Prepare clothes" in data["suggested_action"]
        assert data["expected_improvement"] == 1.2
        assert data["optimization_confidence"] == 0.78
        assert data["optimization_status"] == "PENDING"

    def test_optimization_record_id_includes_position(self):
        """Optimization record_id includes routine_id and position."""
        assembler = create_assembler()
        opt = create_sample_routine_optimization()

        result = assembler.assemble_routine_optimization_writes([opt])

        write = result[0]
        # Format: opt_{routine_id}_{position}
        assert write.record_id == "opt_routine_morning_2"

    def test_multiple_optimizations_for_same_routine(self):
        """Multiple optimizations for same routine create separate writes."""
        assembler = create_assembler()
        opt1 = create_sample_routine_optimization()
        opt2 = RoutineOptimization.create(
            routine_id="routine_morning",
            routine_name="Morning Routine",
            bottleneck_step="breakfast",
            bottleneck_position=3,
            value_drop=-1.8,
            suggested_action="Meal prep on Sunday",
            expected_improvement=0.9,
            confidence=0.65,
        )

        result = assembler.assemble_routine_optimization_writes([opt1, opt2])

        assert len(result) == 2
        assert result[0].record_id == "opt_routine_morning_2"
        assert result[1].record_id == "opt_routine_morning_3"


# =============================================================================
# TESTS: ASSEMBLE_ALL INTEGRATION
# =============================================================================


class TestAssembleAllR5Integration:
    """Tests for assemble_all() with R5 outputs."""

    def test_assemble_all_with_insights(self):
        """assemble_all includes insight writes in st_sem."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result = assembler.assemble_all(insights=[insight])

        assert LAYER_ST_SEM in result
        assert len(result[LAYER_ST_SEM]) == 1
        assert result[LAYER_ST_SEM][0].record_data["pattern_type"] == "INSIGHT"

    def test_assemble_all_with_counterfactuals(self):
        """assemble_all includes counterfactual writes in st_prospective."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result = assembler.assemble_all(counterfactuals=[cf])

        assert LAYER_ST_PROSPECTIVE in result
        assert len(result[LAYER_ST_PROSPECTIVE]) == 1
        assert result[LAYER_ST_PROSPECTIVE][0].record_data["intention_type"] == "COUNTERFACTUAL"

    def test_assemble_all_with_routine_optimizations(self):
        """assemble_all includes routine optimization writes in st_procedural."""
        assembler = create_assembler()
        opt = create_sample_routine_optimization()

        result = assembler.assemble_all(routine_optimizations=[opt])

        assert LAYER_ST_PROCEDURAL in result
        assert len(result[LAYER_ST_PROCEDURAL]) == 1

    def test_assemble_all_merges_r5_insights_with_r3_sem(self):
        """assemble_all merges R5 insights with R3 st_sem writes."""
        from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction

        assembler = create_assembler()
        insight = create_sample_insight()

        # Create R3 event state with CREATE action
        event_state = P03EventState(
            event_id="evt_001",
            embedding_id="emb_001",
            reconciliation_action=ReconciliationAction.CREATE,
        )

        result = assembler.assemble_all(
            event_states={"evt_001": event_state},
            insights=[insight],
        )

        # Should have 2 st_sem writes: 1 from R3, 1 from R5
        assert LAYER_ST_SEM in result
        assert len(result[LAYER_ST_SEM]) == 2

        # Verify both types are present
        pattern_types = [w.record_data.get("pattern_type") for w in result[LAYER_ST_SEM]]
        assert "INSIGHT" in pattern_types

    def test_assemble_all_with_all_r5_outputs(self):
        """assemble_all handles all R5 output types together."""
        assembler = create_assembler()
        insight = create_sample_insight()
        cf = create_sample_counterfactual()
        opt = create_sample_routine_optimization()

        result = assembler.assemble_all(
            insights=[insight],
            counterfactuals=[cf],
            routine_optimizations=[opt],
        )

        assert LAYER_ST_SEM in result
        assert LAYER_ST_PROSPECTIVE in result
        assert LAYER_ST_PROCEDURAL in result

        assert len(result[LAYER_ST_SEM]) == 1
        assert len(result[LAYER_ST_PROSPECTIVE]) == 1
        assert len(result[LAYER_ST_PROCEDURAL]) == 1


# =============================================================================
# TESTS: IDEMPOTENCY
# =============================================================================


class TestR5WriteIdempotency:
    """Tests for R5 write idempotency keys."""

    def test_insight_idempotency_key_is_deterministic(self):
        """Same insight produces same idempotency key."""
        assembler = create_assembler()
        insight = create_sample_insight()

        result1 = assembler.assemble_insight_writes([insight])
        result2 = assembler.assemble_insight_writes([insight])

        assert result1[0].idempotency_key == result2[0].idempotency_key

    def test_counterfactual_idempotency_key_is_deterministic(self):
        """Same counterfactual produces same idempotency key."""
        assembler = create_assembler()
        cf = create_sample_counterfactual()

        result1 = assembler.assemble_counterfactual_writes([cf])
        result2 = assembler.assemble_counterfactual_writes([cf])

        assert result1[0].idempotency_key == result2[0].idempotency_key

    def test_optimization_idempotency_key_is_deterministic(self):
        """Same optimization produces same idempotency key."""
        assembler = create_assembler()
        opt = create_sample_routine_optimization()

        result1 = assembler.assemble_routine_optimization_writes([opt])
        result2 = assembler.assemble_routine_optimization_writes([opt])

        assert result1[0].idempotency_key == result2[0].idempotency_key
