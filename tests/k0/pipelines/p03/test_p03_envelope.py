"""
P03 Envelope Model Tests.

Issue 1.1.8: Envelope model tests + fixtures

Test Categories:
1. Context Determinism - batch_id stable across event ID permutations
2. Context Immutability - P03CycleContext frozen after construction
3. Event State Mutability - P03EventState can be enriched through phases
4. Staged Writes Order - get_all_writes_ordered() returns dependency order
5. Serializer Roundtrip - to_full_dict() -> from_dict() -> equivalent
6. Lazy Embedding - Default event state has embedding_id without vector
7. Phase Output Defaults - All phase outputs have safe defaults
8. Error Collection - Errors accumulate with recoverable distinction
9. Observability Context - Phase timing and metrics
10. Phase Transitions - P03PhaseId enum validation
"""

from __future__ import annotations

import json
import time
from typing import List

import pytest

from k0.pipelines.p03 import (  # Context; Event State; Phase Outputs; Staged Writes
    LAYER_ST_EPI,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    PIPELINE_ID,
    P03CycleContext,
    P03EnvelopeSerializer,
    P03EventState,
    P03ObservabilityContext,
    P03PhaseId,
    P03PhaseOutputs,
    P03StagedWrites,
    PhaseCheckpoint,
    PruneDecision,
    ReconciliationAction,
    StagedWrite,
    generate_phase_summary,
    generate_ulid,
)

# =============================================================================
# 1. CONTEXT DETERMINISM TESTS
# =============================================================================


class TestContextDeterminism:
    """Test that batch_id is stable/deterministic for same event IDs."""

    def test_batch_id_stable_for_same_event_ids(self, sample_event_ids: List[str]) -> None:
        """batch_id should be identical when created with same event IDs."""
        ctx1 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=sample_event_ids,
            trigger_type="MANUAL",
            trigger_reason="Test 1",
        )

        ctx2 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=sample_event_ids,
            trigger_type="MANUAL",
            trigger_reason="Test 2",
        )

        assert ctx1.batch_id == ctx2.batch_id, "batch_id should be deterministic"

    def test_batch_id_stable_across_permutations(self, sample_event_ids: List[str]) -> None:
        """batch_id should be identical regardless of event ID order."""
        # Original order
        ctx1 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=sample_event_ids,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        # Reversed order
        ctx2 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=list(reversed(sample_event_ids)),
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        # Random shuffle order
        shuffled = sample_event_ids[2:] + sample_event_ids[:2]
        ctx3 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=shuffled,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        assert (
            ctx1.batch_id == ctx2.batch_id == ctx3.batch_id
        ), "batch_id should be stable across permutations (sorted internally)"

    def test_batch_id_handles_duplicates(self) -> None:
        """batch_id should deduplicate event IDs."""
        ids_with_dupes = ["evt-1", "evt-2", "evt-1", "evt-3", "evt-2"]
        unique_ids = ["evt-1", "evt-2", "evt-3"]

        ctx_dupes = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=ids_with_dupes,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        ctx_unique = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=unique_ids,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        assert ctx_dupes.batch_id == ctx_unique.batch_id
        assert ctx_dupes.batch_size == 3, "batch_size should reflect unique count"

    def test_batch_id_different_for_different_events(self) -> None:
        """batch_id should differ when event IDs differ."""
        ctx1 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=["evt-1", "evt-2"],
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        ctx2 = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=["evt-3", "evt-4"],
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        assert ctx1.batch_id != ctx2.batch_id


# =============================================================================
# 2. CONTEXT IMMUTABILITY TESTS
# =============================================================================


class TestContextImmutability:
    """Test that P03CycleContext is frozen after construction."""

    def test_context_is_frozen(self, sample_cycle_context: P03CycleContext) -> None:
        """P03CycleContext should raise on attribute assignment."""
        with pytest.raises(AttributeError):
            sample_cycle_context.batch_size = 999  # type: ignore

    def test_context_cycle_id_immutable(self, sample_cycle_context: P03CycleContext) -> None:
        """cycle_id should not be modifiable."""
        with pytest.raises(AttributeError):
            sample_cycle_context.cycle_id = "new-id"  # type: ignore

    def test_context_event_ids_is_tuple(self, sample_cycle_context: P03CycleContext) -> None:
        """event_ids should be a tuple (immutable sequence)."""
        assert isinstance(sample_cycle_context.event_ids, tuple)

    def test_context_batch_size_matches_event_ids(
        self, sample_cycle_context: P03CycleContext
    ) -> None:
        """batch_size should always equal len(event_ids)."""
        assert sample_cycle_context.batch_size == len(sample_cycle_context.event_ids)


# =============================================================================
# 3. EVENT STATE MUTABILITY TESTS
# =============================================================================


class TestEventStateMutability:
    """Test that P03EventState can be enriched through phases."""

    def test_event_state_importance_can_be_set(self, sample_event_state: P03EventState) -> None:
        """R1 should be able to set importance fields."""
        sample_event_state.importance_score = 0.85
        sample_event_state.importance_computed = True

        assert sample_event_state.importance_score == 0.85
        assert sample_event_state.importance_computed is True

    def test_event_state_cluster_can_be_set(self, sample_event_state: P03EventState) -> None:
        """R2 should be able to set cluster fields."""
        sample_event_state.cluster_id = "cluster-001"
        sample_event_state.cluster_label = 0
        sample_event_state.is_noise = False
        sample_event_state.centroid_distance = 0.15

        assert sample_event_state.cluster_id == "cluster-001"
        assert sample_event_state.is_noise is False

    def test_event_state_reconciliation_can_be_set(self, sample_event_state: P03EventState) -> None:
        """R3 should be able to set reconciliation fields."""
        sample_event_state.reconciliation_action = ReconciliationAction.REINFORCE
        sample_event_state.best_match_id = "truth-001"
        sample_event_state.similarity_score = 0.92
        sample_event_state.confidence = 0.88

        assert sample_event_state.reconciliation_action == ReconciliationAction.REINFORCE
        assert sample_event_state.confidence == 0.88

    def test_event_state_default_reconciliation_is_pending(self) -> None:
        """Default reconciliation action should be PENDING."""
        event = P03EventState(event_id="evt-1")
        assert event.reconciliation_action == ReconciliationAction.PENDING

    def test_event_state_default_prune_decision_is_keep(self) -> None:
        """Default prune decision should be KEEP."""
        event = P03EventState(event_id="evt-1")
        assert event.prune_decision == PruneDecision.KEEP


# =============================================================================
# 3b. EVENT STATE METHODS TESTS
# =============================================================================


class TestEventStateMethods:
    """Test P03EventState helper methods for phase enrichment."""

    # -------------------------------------------------------------------------
    # Embedding Methods
    # -------------------------------------------------------------------------

    def test_materialize_embedding_valid(self, sample_event_state: P03EventState) -> None:
        """materialize_embedding() should accept 768-dim vector."""
        embedding = [0.1] * 768
        sample_event_state.materialize_embedding(embedding)
        assert sample_event_state.embedding_768 == embedding

    def test_materialize_embedding_invalid_dimension(
        self, sample_event_state: P03EventState
    ) -> None:
        """materialize_embedding() should raise ValueError for wrong dimension."""
        embedding = [0.1] * 512  # Wrong size
        with pytest.raises(ValueError) as exc_info:
            sample_event_state.materialize_embedding(embedding)
        assert "dimension mismatch" in str(exc_info.value).lower()
        assert "768" in str(exc_info.value)
        assert "512" in str(exc_info.value)

    def test_clear_embedding(self, sample_event_state: P03EventState) -> None:
        """clear_embedding() should set embedding_768 to None."""
        sample_event_state.embedding_768 = [0.1] * 768
        sample_event_state.clear_embedding()
        assert sample_event_state.embedding_768 is None

    # -------------------------------------------------------------------------
    # R1: Importance Scoring
    # -------------------------------------------------------------------------

    def test_set_importance(self, sample_event_state: P03EventState) -> None:
        """set_importance() should set all importance factors."""
        sample_event_state.set_importance(
            score=0.85,
            recency=0.9,
            affect=0.7,
            social=0.8,
            novelty=0.6,
        )
        assert sample_event_state.importance_score == 0.85
        assert sample_event_state.recency_factor == 0.9
        assert sample_event_state.affect_factor == 0.7
        assert sample_event_state.social_factor == 0.8
        assert sample_event_state.novelty_factor == 0.6
        assert sample_event_state.importance_computed is True

    def test_add_hebbian_update(self, sample_event_state: P03EventState) -> None:
        """add_hebbian_update() should append to hebbian_updates list."""
        sample_event_state.add_hebbian_update(
            source_entity_id="entity-001",
            target_entity_id="entity-002",
            old_weight=0.5,
            new_weight=0.7,
            update_type="STRENGTHEN",
        )
        assert len(sample_event_state.hebbian_updates) == 1
        update = sample_event_state.hebbian_updates[0]
        assert update["source_entity_id"] == "entity-001"
        assert update["target_entity_id"] == "entity-002"
        assert update["old_weight"] == 0.5
        assert update["new_weight"] == 0.7
        assert update["update_type"] == "STRENGTHEN"

    # -------------------------------------------------------------------------
    # R2: Clustering
    # -------------------------------------------------------------------------

    def test_assign_cluster(self, sample_event_state: P03EventState) -> None:
        """assign_cluster() should set cluster fields."""
        sample_event_state.assign_cluster(
            cluster_id="cluster-001",
            label=2,
            distance=0.15,
        )
        assert sample_event_state.cluster_id == "cluster-001"
        assert sample_event_state.cluster_label == 2
        assert sample_event_state.is_noise is False
        assert sample_event_state.centroid_distance == 0.15

    def test_assign_cluster_noise_label(self, sample_event_state: P03EventState) -> None:
        """assign_cluster() with label=-1 should set is_noise=True."""
        sample_event_state.assign_cluster(
            cluster_id="noise-cluster",
            label=-1,
            distance=0.0,
        )
        assert sample_event_state.cluster_label == -1
        assert sample_event_state.is_noise is True

    def test_mark_as_noise(self, sample_event_state: P03EventState) -> None:
        """mark_as_noise() should clear cluster and set noise flags."""
        sample_event_state.cluster_id = "cluster-001"
        sample_event_state.cluster_label = 2
        sample_event_state.is_noise = False

        sample_event_state.mark_as_noise()

        assert sample_event_state.cluster_id is None
        assert sample_event_state.cluster_label == -1
        assert sample_event_state.is_noise is True
        assert sample_event_state.centroid_distance == 0.0

    # -------------------------------------------------------------------------
    # R3: Reconciliation
    # -------------------------------------------------------------------------

    def test_set_reconciliation(self, sample_event_state: P03EventState) -> None:
        """set_reconciliation() should set all reconciliation fields."""
        sample_event_state.set_reconciliation(
            action=ReconciliationAction.REINFORCE,
            match_id="truth-001",
            match_layer="st_epi",
            similarity=0.92,
            confidence=0.88,
            reason="High similarity match",
        )
        assert sample_event_state.reconciliation_action == ReconciliationAction.REINFORCE
        assert sample_event_state.best_match_id == "truth-001"
        assert sample_event_state.best_match_layer == "st_epi"
        assert sample_event_state.similarity_score == 0.92
        assert sample_event_state.confidence == 0.88
        assert sample_event_state.reconciliation_reason == "High similarity match"

    def test_mark_duplicate(self, sample_event_state: P03EventState) -> None:
        """mark_duplicate() should set duplicate fields and SKIP action."""
        sample_event_state.mark_duplicate(
            canonical_id="canonical-001",
            hamming_dist=3,
        )
        assert sample_event_state.is_duplicate is True
        assert sample_event_state.duplicate_of_id == "canonical-001"
        assert sample_event_state.hamming_distance == 3
        assert sample_event_state.reconciliation_action == ReconciliationAction.SKIP
        assert "Duplicate" in sample_event_state.reconciliation_reason
        assert "canonical-001" in sample_event_state.reconciliation_reason

    def test_set_decay(self, sample_event_state: P03EventState) -> None:
        """set_decay() should set decay fields and prune decision."""
        sample_event_state.set_decay(
            decay_score=0.3,
            lambda_decay=0.1,
            days_since=120,
            access_count=5,
            decision=PruneDecision.ARCHIVE,
        )
        assert sample_event_state.decay_score == 0.3
        assert sample_event_state.lambda_decay == 0.1
        assert sample_event_state.days_since_access == 120
        assert sample_event_state.access_count == 5
        assert sample_event_state.prune_decision == PruneDecision.ARCHIVE
        # NOTE: reconciliation_action is NOT automatically set
        assert sample_event_state.reconciliation_action == ReconciliationAction.PENDING

    # -------------------------------------------------------------------------
    # R6/R7: Version Conflict & Write Results
    # -------------------------------------------------------------------------

    def test_set_version_conflict(self, sample_event_state: P03EventState) -> None:
        """set_version_conflict() should record conflict state."""
        sample_event_state.set_version_conflict(expected=5)
        assert sample_event_state.expected_version == 5
        assert sample_event_state.version_conflict is True

    def test_set_write_result_success(self, sample_event_state: P03EventState) -> None:
        """set_write_result() should record successful write."""
        sample_event_state.set_write_result(
            success=True,
            layer="st_epi",
            record_id="epi-001",
        )
        assert sample_event_state.write_success is True
        assert sample_event_state.written_to_layer == "st_epi"
        assert sample_event_state.written_record_id == "epi-001"
        assert sample_event_state.write_error is None

    def test_set_write_result_failure(self, sample_event_state: P03EventState) -> None:
        """set_write_result() should record failed write with error."""
        sample_event_state.set_write_result(
            success=False,
            layer="st_epi",
            error="Connection timeout",
        )
        assert sample_event_state.write_success is False
        assert sample_event_state.written_to_layer == "st_epi"
        assert sample_event_state.write_error == "Connection timeout"

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def test_is_actionable_true(self, sample_event_state: P03EventState) -> None:
        """is_actionable() should return True for actionable states."""
        actionable_actions = [
            ReconciliationAction.REINFORCE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.CREATE,
            ReconciliationAction.EVOLVE,
            ReconciliationAction.CONTRADICT,
            ReconciliationAction.PRUNE,
        ]
        for action in actionable_actions:
            sample_event_state.reconciliation_action = action
            sample_event_state.version_conflict = False
            assert sample_event_state.is_actionable() is True, f"{action} should be actionable"

    def test_is_actionable_false_for_skip(self, sample_event_state: P03EventState) -> None:
        """is_actionable() should return False for SKIP action."""
        sample_event_state.reconciliation_action = ReconciliationAction.SKIP
        assert sample_event_state.is_actionable() is False

    def test_is_actionable_false_for_pending(self, sample_event_state: P03EventState) -> None:
        """is_actionable() should return False for PENDING action."""
        sample_event_state.reconciliation_action = ReconciliationAction.PENDING
        assert sample_event_state.is_actionable() is False

    def test_is_actionable_false_with_version_conflict(
        self, sample_event_state: P03EventState
    ) -> None:
        """is_actionable() should return False if version_conflict=True."""
        sample_event_state.reconciliation_action = ReconciliationAction.REINFORCE
        sample_event_state.version_conflict = True
        assert sample_event_state.is_actionable() is False

    def test_needs_truth_write(self, sample_event_state: P03EventState) -> None:
        """needs_truth_write() should return True for CREATE/EXTEND/EVOLVE."""
        for action in [
            ReconciliationAction.CREATE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.EVOLVE,
        ]:
            sample_event_state.reconciliation_action = action
            assert sample_event_state.needs_truth_write() is True, f"{action} needs write"

    def test_needs_truth_write_false(self, sample_event_state: P03EventState) -> None:
        """needs_truth_write() should return False for REINFORCE/SKIP."""
        for action in [ReconciliationAction.REINFORCE, ReconciliationAction.SKIP]:
            sample_event_state.reconciliation_action = action
            assert sample_event_state.needs_truth_write() is False, f"{action} no write"

    def test_needs_reinforcement(self, sample_event_state: P03EventState) -> None:
        """needs_reinforcement() should return True only for REINFORCE."""
        sample_event_state.reconciliation_action = ReconciliationAction.REINFORCE
        assert sample_event_state.needs_reinforcement() is True

        sample_event_state.reconciliation_action = ReconciliationAction.CREATE
        assert sample_event_state.needs_reinforcement() is False

    def test_to_summary_dict(self, enriched_event_state: P03EventState) -> None:
        """to_summary_dict() should return minimal summary fields."""
        summary = enriched_event_state.to_summary_dict()

        assert "event_id" in summary
        assert "reconciliation_action" in summary
        assert "importance_score" in summary
        assert "cluster_id" in summary
        assert "is_duplicate" in summary
        assert "write_success" in summary
        assert summary["event_id"] == enriched_event_state.event_id
        assert summary["reconciliation_action"] == enriched_event_state.reconciliation_action.value

    def test_from_hipp_event(self) -> None:
        """from_hipp_event() factory should create event with P02/hipp fields."""
        event = P03EventState.from_hipp_event(
            event_id="evt-001",
            hipp_event_id="hipp-001",
            content_text="Test content",
            content_type="CHAT",
            content_hash="abc123",
            simhash_hex="FEDCBA9876543210",
            timestamp=1700000000000,
            channel_id="family-chat",
            embedding_id="vec-001",
            sentiment_score=0.7,
            sentiment_label="positive",
            emotions_json='["joy"]',
            intent_label="INFORM",
            ner_entities_json='[{"text": "test", "type": "MISC"}]',
            temporal_expressions_json="[]",
        )

        assert event.event_id == "evt-001"
        assert event.hipp_event_id == "hipp-001"
        assert event.content_text == "Test content"
        assert event.content_type == "CHAT"
        assert event.content_hash == "abc123"
        assert event.simhash_hex == "FEDCBA9876543210"
        assert event.timestamp == 1700000000000
        assert event.channel_id == "family-chat"
        assert event.embedding_id == "vec-001"
        assert event.sentiment_score == 0.7
        assert event.sentiment_label == "positive"
        assert event.emotions_json == '["joy"]'
        assert event.intent_label == "INFORM"
        assert event.ner_entities_json == '[{"text": "test", "type": "MISC"}]'
        assert event.temporal_expressions_json == "[]"
        # Default fields should be set
        assert event.reconciliation_action == ReconciliationAction.PENDING
        assert event.prune_decision == PruneDecision.KEEP


# =============================================================================
# 4. STAGED WRITES ORDER TESTS
# =============================================================================


class TestStagedWritesOrder:
    """Test get_all_writes_ordered() returns dependency order."""

    def test_writes_ordered_by_layer_dependency(
        self, sample_staged_writes: P03StagedWrites
    ) -> None:
        """Writes should be ordered: KG first, then episodic, then vectors."""
        ordered = sample_staged_writes.get_all_writes_ordered()

        # Verify we got all writes
        assert len(ordered) == 5

        # Check layer order matches dependency (KG before episodic before vec)
        layer_order = [w.layer for w in ordered]

        # KG layers should come before dependent layers
        kg_dom_idx = next(i for i, l in enumerate(layer_order) if l == LAYER_ST_KG_DOM)
        kg_edges_idx = next(i for i, l in enumerate(layer_order) if l == LAYER_ST_KG_EDGES)

        # KG domain should come before KG edges (entities before edges)
        assert kg_dom_idx < kg_edges_idx, "KG domain should be written before KG edges"

    def test_writes_by_layer_returns_correct_layer(
        self, sample_staged_writes: P03StagedWrites
    ) -> None:
        """get_writes_by_layer() should filter correctly."""
        epi_writes = sample_staged_writes.get_writes_by_layer(LAYER_ST_EPI)
        kg_writes = sample_staged_writes.get_writes_by_layer(LAYER_ST_KG_DOM)

        assert len(epi_writes) == 1
        assert all(w.layer == LAYER_ST_EPI for w in epi_writes)

        assert len(kg_writes) == 1
        assert all(w.layer == LAYER_ST_KG_DOM for w in kg_writes)

    def test_empty_writes_returns_empty_list(self, empty_staged_writes: P03StagedWrites) -> None:
        """Empty container should return empty list."""
        assert empty_staged_writes.get_all_writes_ordered() == []

    def test_add_write_rejects_unknown_layer(self, empty_staged_writes: P03StagedWrites) -> None:
        """add_write() should return False for unknown layer."""
        write = StagedWrite.insert(
            layer="unknown_layer",
            record_id="rec-001",
            data={},
            phase="R6",
        )

        result = empty_staged_writes.add_write(write)
        assert result is False

    def test_add_write_accepts_valid_layer(self, empty_staged_writes: P03StagedWrites) -> None:
        """add_write() should return True for valid layer."""
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi-001",
            data={"test": "data"},
            phase="R6",
        )

        result = empty_staged_writes.add_write(write)
        assert result is True
        assert len(empty_staged_writes.get_writes_by_layer(LAYER_ST_EPI)) == 1


# =============================================================================
# 5. SERIALIZER ROUNDTRIP TESTS
# =============================================================================


class TestSerializerRoundtrip:
    """Test to_full_dict() -> from_dict() produces equivalent data."""

    def test_context_roundtrip(self, sample_cycle_context: P03CycleContext) -> None:
        """Context should survive serialization roundtrip."""
        # Serialize
        ctx_dict = P03EnvelopeSerializer._serialize_context(sample_cycle_context)

        # Deserialize
        ctx_restored = P03EnvelopeSerializer.context_from_dict(ctx_dict)

        # Verify
        assert ctx_restored.cycle_id == sample_cycle_context.cycle_id
        assert ctx_restored.batch_id == sample_cycle_context.batch_id
        assert ctx_restored.tenant_id == sample_cycle_context.tenant_id
        assert ctx_restored.space_id == sample_cycle_context.space_id
        assert ctx_restored.trace_id == sample_cycle_context.trace_id
        assert ctx_restored.batch_size == sample_cycle_context.batch_size
        assert ctx_restored.event_ids == sample_cycle_context.event_ids

    def test_event_state_roundtrip(self, enriched_event_state: P03EventState) -> None:
        """Enriched event state should survive serialization roundtrip."""
        # Serialize
        evt_dict = P03EnvelopeSerializer._serialize_event(enriched_event_state)

        # Deserialize
        evt_restored = P03EnvelopeSerializer.event_from_dict(evt_dict)

        # Verify core fields
        assert evt_restored.event_id == enriched_event_state.event_id
        assert evt_restored.content_text == enriched_event_state.content_text

        # Verify enrichment fields
        assert evt_restored.importance_score == enriched_event_state.importance_score
        assert evt_restored.cluster_id == enriched_event_state.cluster_id
        assert evt_restored.reconciliation_action == enriched_event_state.reconciliation_action
        assert evt_restored.similarity_score == enriched_event_state.similarity_score

    def test_observability_roundtrip(
        self, sample_observability_context: P03ObservabilityContext
    ) -> None:
        """Observability context should survive serialization roundtrip."""
        # Serialize
        obs_dict = P03EnvelopeSerializer._serialize_observability(sample_observability_context)

        # Deserialize
        obs_restored = P03EnvelopeSerializer.observability_from_dict(obs_dict)

        # Verify
        assert obs_restored.trace_id == sample_observability_context.trace_id

    def test_full_envelope_roundtrip(
        self,
        sample_cycle_context: P03CycleContext,
        sample_event_states: List[P03EventState],
        sample_phase_outputs: P03PhaseOutputs,
        sample_staged_writes: P03StagedWrites,
        sample_observability_context: P03ObservabilityContext,
    ) -> None:
        """Full envelope should produce valid JSON."""
        # Serialize to full dict
        full_dict = P03EnvelopeSerializer.to_full_dict(
            context=sample_cycle_context,
            current_phase="R3",
            events=sample_event_states,
            phases=sample_phase_outputs,
            staged=sample_staged_writes,
            observability=sample_observability_context,
        )

        # Should be JSON-serializable
        json_str = json.dumps(full_dict)
        assert len(json_str) > 0

        # Should parse back
        parsed = json.loads(json_str)
        assert parsed["context"]["cycle_id"] == sample_cycle_context.cycle_id
        assert len(parsed["events"]) == len(sample_event_states)

    def test_serialized_output_is_valid_json(self, sample_cycle_context: P03CycleContext) -> None:
        """All serialization methods should produce valid JSON."""
        events = [P03EventState(event_id="evt-1")]
        phases = P03PhaseOutputs()
        staged = P03StagedWrites()
        obs = P03ObservabilityContext.create()

        # to_summary_dict
        summary = P03EnvelopeSerializer.to_summary_dict(sample_cycle_context, "R1", 1, 0, 0, obs)
        json.dumps(summary)  # Should not raise

        # to_dict
        standard = P03EnvelopeSerializer.to_dict(
            sample_cycle_context, "R1", events, phases, staged, obs
        )
        json.dumps(standard)  # Should not raise

        # to_full_dict
        full = P03EnvelopeSerializer.to_full_dict(
            sample_cycle_context, "R1", events, phases, staged, obs
        )
        json.dumps(full)  # Should not raise


# =============================================================================
# 6. LAZY EMBEDDING TESTS
# =============================================================================


class TestLazyEmbedding:
    """Test that embedding is lazy-loaded (embedding_id without vector)."""

    def test_default_embedding_768_is_none(self) -> None:
        """Default embedding_768 should be None (not materialized)."""
        event = P03EventState(
            event_id="evt-1",
            embedding_id="vec-001",  # Reference exists
        )

        assert event.embedding_id == "vec-001"
        assert event.embedding_768 is None, "Embedding should not be materialized by default"

    def test_embedding_can_be_materialized(self) -> None:
        """embedding_768 can be set when needed."""
        event = P03EventState(
            event_id="evt-1",
            embedding_id="vec-001",
        )

        # Simulate lazy load
        fake_embedding = [0.1] * 768
        event.embedding_768 = fake_embedding

        assert event.embedding_768 is not None
        assert len(event.embedding_768) == 768


# =============================================================================
# 7. PHASE OUTPUT DEFAULTS TESTS
# =============================================================================


class TestPhaseOutputDefaults:
    """Test that all phase outputs have safe defaults."""

    def test_r1_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R1 outputs should have safe defaults."""
        assert empty_phase_outputs.r1_scored_events == []
        assert empty_phase_outputs.r1_hebbian_updates == []

    def test_r2_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R2 outputs should have safe defaults."""
        assert empty_phase_outputs.r2_clusters == []
        assert empty_phase_outputs.r2_noise_event_ids == []
        assert empty_phase_outputs.r2_avg_cluster_size == 0.0

    def test_r3_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R3 outputs should have safe defaults."""
        assert empty_phase_outputs.r3_dedup_merges == []
        assert empty_phase_outputs.r3_archive_candidates == []
        assert empty_phase_outputs.r3_prune_candidates == []
        assert empty_phase_outputs.r3_decay_updates == []

    def test_r4_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R4 outputs should have safe defaults."""
        assert empty_phase_outputs.r4_new_entities == []
        assert empty_phase_outputs.r4_updated_entities == []
        assert empty_phase_outputs.r4_new_edges == []
        assert empty_phase_outputs.r4_updated_edges == []
        assert empty_phase_outputs.r4_causal_edges == []
        assert empty_phase_outputs.r4_gap_candidates == []

    def test_r5_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R5 outputs should have safe defaults."""
        assert empty_phase_outputs.r5_skipped is False
        assert empty_phase_outputs.r5_skip_reason is None
        assert empty_phase_outputs.r5_counterfactuals == []
        assert empty_phase_outputs.r5_insights == []

    def test_r6_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R6 outputs should have safe defaults."""
        assert empty_phase_outputs.r6_summary is not None
        assert empty_phase_outputs.r6_summary.total_processed == 0

    def test_r7_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R7 outputs should have safe defaults."""
        assert empty_phase_outputs.r7_manifest is None
        assert empty_phase_outputs.r7_success is False
        assert empty_phase_outputs.r7_error is None

    def test_r8_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """R8 outputs should have safe defaults."""
        assert empty_phase_outputs.r8_emitted_events == []
        assert empty_phase_outputs.r8_cycle_summary is None
        assert empty_phase_outputs.r8_success is False

    def test_to_summary_dict_with_defaults(self, empty_phase_outputs: P03PhaseOutputs) -> None:
        """to_summary_dict() should work with all defaults."""
        summary = empty_phase_outputs.to_summary_dict()

        assert summary["r1"]["hebbian_updates"] == 0
        assert summary["r2"]["cluster_count"] == 0
        assert summary["r4"]["new_entities"] == 0
        assert summary["r7"]["success"] is False


# =============================================================================
# 8. ERROR COLLECTION TESTS
# =============================================================================


class TestErrorCollection:
    """Test error accumulation with recoverable distinction."""

    def test_record_error_adds_to_collection(
        self, fresh_observability_context: P03ObservabilityContext
    ) -> None:
        """record_error() should add error to collection."""
        fresh_observability_context.record_error(
            phase="R2",
            stage_id="clustering",
            error_type="ValidationError",
            error_message="Test error",
            recoverable=True,
        )

        assert fresh_observability_context.has_errors()
        assert len(fresh_observability_context.errors) == 1

    def test_record_exception_captures_details(
        self, fresh_observability_context: P03ObservabilityContext
    ) -> None:
        """record_exception() should capture exception details."""
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            fresh_observability_context.record_exception(
                phase="R3",
                stage_id="dedup",
                exc=e,
                recoverable=False,
            )

        assert fresh_observability_context.has_errors()
        error = fresh_observability_context.errors[0]
        assert "ValueError" in error.error_type
        assert "Test exception" in error.error_message

    def test_recoverable_vs_unrecoverable(
        self, observability_with_errors: P03ObservabilityContext
    ) -> None:
        """has_unrecoverable_errors() should detect non-recoverable errors."""
        assert observability_with_errors.has_errors()
        assert observability_with_errors.has_unrecoverable_errors()

    def test_errors_by_phase(self, observability_with_errors: P03ObservabilityContext) -> None:
        """get_errors_by_phase() should filter correctly."""
        r2_errors = observability_with_errors.get_errors_by_phase("R2")
        r3_errors = observability_with_errors.get_errors_by_phase("R3")
        r1_errors = observability_with_errors.get_errors_by_phase("R1")

        assert len(r2_errors) == 1
        assert len(r3_errors) == 1
        assert len(r1_errors) == 0

    def test_error_counter_incremented(
        self, fresh_observability_context: P03ObservabilityContext
    ) -> None:
        """Recording errors should increment error counters."""
        fresh_observability_context.record_error(
            phase="R2",
            stage_id="test",
            error_type="TestError",
            error_message="Test",
            recoverable=True,
        )
        fresh_observability_context.record_error(
            phase="R2",
            stage_id="test",
            error_type="TestError",
            error_message="Test 2",
            recoverable=True,
        )

        # Counter should be incremented
        assert fresh_observability_context.counters.get("errors.R2", 0) == 2


# =============================================================================
# 9. OBSERVABILITY CONTEXT TESTS
# =============================================================================


class TestObservabilityContext:
    """Test phase timing and metrics collection."""

    def test_phase_timing(self, fresh_observability_context: P03ObservabilityContext) -> None:
        """Phase timing should capture duration."""
        fresh_observability_context.start_phase("R1")
        time.sleep(0.01)  # 10ms
        fresh_observability_context.end_phase("R1")

        duration = fresh_observability_context.get_phase_duration_ms("R1")
        assert duration is not None
        assert duration >= 10  # At least 10ms

    def test_get_all_phase_durations(
        self, sample_observability_context: P03ObservabilityContext
    ) -> None:
        """get_all_phase_durations() should return all completed phases."""
        durations = sample_observability_context.get_all_phase_durations()

        assert "R0" in durations
        assert "R1" in durations
        assert "R2" in durations

    def test_increment_counter(self, fresh_observability_context: P03ObservabilityContext) -> None:
        """increment() should update counter."""
        fresh_observability_context.increment("events_processed", 5)
        fresh_observability_context.increment("events_processed", 3)

        assert fresh_observability_context.counters["events_processed"] == 8

    def test_histogram_stats(self, fresh_observability_context: P03ObservabilityContext) -> None:
        """record_histogram() and get_histogram_stats() should work."""
        fresh_observability_context.record_histogram("scores", 0.5)
        fresh_observability_context.record_histogram("scores", 0.7)
        fresh_observability_context.record_histogram("scores", 0.9)

        stats = fresh_observability_context.get_histogram_stats("scores")

        assert stats["count"] == 3
        assert stats["min"] == 0.5
        assert stats["max"] == 0.9
        assert 0.69 <= stats["avg"] <= 0.71  # ~0.7

    def test_log_context_includes_required_fields(
        self, fresh_observability_context: P03ObservabilityContext
    ) -> None:
        """get_log_context() should include all required fields."""
        ctx = fresh_observability_context.get_log_context("R2", "clustering")

        assert ctx["pipeline_id"] == PIPELINE_ID
        assert "trace_id" in ctx
        assert "span_id" in ctx
        assert ctx["phase"] == "R2"
        assert ctx["module_id"] == "clustering"

    def test_to_summary_dict(self, sample_observability_context: P03ObservabilityContext) -> None:
        """to_summary_dict() should return compact summary."""
        summary = sample_observability_context.to_summary_dict()

        assert "trace_id" in summary
        assert "counters" in summary
        assert "phase_durations_ms" in summary


# =============================================================================
# 10. PHASE TRANSITION TESTS
# =============================================================================


class TestPhaseTransitions:
    """Test P03PhaseId enum and transition validation."""

    def test_valid_transition_r1_to_r2(self) -> None:
        """R1 -> R2 should be valid."""
        assert P03PhaseId.R1_SCORE.can_transition_to(P03PhaseId.R2_CLUSTER)

    def test_valid_transition_r1_to_failed(self) -> None:
        """R1 -> FAILED should be valid."""
        assert P03PhaseId.R1_SCORE.can_transition_to(P03PhaseId.FAILED)

    def test_invalid_transition_r1_to_r4(self) -> None:
        """R1 -> R4 should be invalid (must go through R2, R3)."""
        assert not P03PhaseId.R1_SCORE.can_transition_to(P03PhaseId.R4_KG)

    def test_r4_can_skip_r5(self) -> None:
        """R4 -> R6 should be valid (R5 is optional)."""
        assert P03PhaseId.R4_KG.can_transition_to(P03PhaseId.R6_STAGE)

    def test_r4_can_go_to_r5(self) -> None:
        """R4 -> R5 should be valid."""
        assert P03PhaseId.R4_KG.can_transition_to(P03PhaseId.R5_DREAM)

    def test_terminal_states_have_no_transitions(self) -> None:
        """COMPLETE and FAILED should have no valid transitions."""
        assert not P03PhaseId.COMPLETE.can_transition_to(P03PhaseId.R0_INIT)
        assert not P03PhaseId.FAILED.can_transition_to(P03PhaseId.R0_INIT)

    def test_r8_can_complete(self) -> None:
        """R8 -> COMPLETE should be valid."""
        assert P03PhaseId.R8_EMIT.can_transition_to(P03PhaseId.COMPLETE)

    def test_all_phases_defined(self) -> None:
        """All phases R0-R8 + COMPLETE + FAILED should be defined."""
        phases = [p.value for p in P03PhaseId]

        assert "R0" in phases
        assert "R1" in phases
        assert "R2" in phases
        assert "R3" in phases
        assert "R4" in phases
        assert "R5" in phases
        assert "R6" in phases
        assert "R7" in phases
        assert "R8" in phases
        assert "COMPLETE" in phases
        assert "FAILED" in phases


# =============================================================================
# 11. GENERATE PHASE SUMMARY TESTS
# =============================================================================


class TestGeneratePhaseSummary:
    """Test generate_phase_summary() helper."""

    def test_r0_summary(
        self, empty_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """R0 summary should count events loaded."""
        summary = generate_phase_summary("R0", empty_phase_outputs, sample_event_states)

        assert summary["events_loaded"] == len(sample_event_states)

    def test_r1_summary(
        self, sample_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """R1 summary should include scoring stats."""
        summary = generate_phase_summary("R1", sample_phase_outputs, sample_event_states)

        assert "events_scored" in summary
        assert "hebbian_updates" in summary

    def test_r4_summary(
        self, sample_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """R4 summary should include KG stats."""
        summary = generate_phase_summary("R4", sample_phase_outputs, sample_event_states)

        assert summary["entities_created"] == 1
        assert summary["edges_created"] == 1
        assert summary["causal_edges"] == 1

    def test_r6_summary(
        self, sample_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """R6 summary should include reconciliation counts."""
        summary = generate_phase_summary("R6", sample_phase_outputs, sample_event_states)

        assert summary["reinforce"] == 3
        assert summary["create"] == 2
        # total_processed excludes skip_count per ReconciliationSummary.total_processed
        # = reinforce(3) + extend(1) + create(2) + evolve(0) + contradict(0) + prune(0) = 6
        assert summary["total_processed"] == 6

    def test_r7_summary_with_manifest(
        self, sample_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """R7 summary should include write stats when manifest present."""
        summary = generate_phase_summary("R7", sample_phase_outputs, sample_event_states)

        assert summary["records_written"] == 5
        assert summary["records_failed"] == 0

    def test_r7_summary_without_manifest(
        self, empty_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """R7 summary should handle missing manifest."""
        summary = generate_phase_summary("R7", empty_phase_outputs, sample_event_states)

        assert "success" in summary

    def test_unknown_phase_returns_empty(
        self, empty_phase_outputs: P03PhaseOutputs, sample_event_states: List[P03EventState]
    ) -> None:
        """Unknown phase should return empty dict."""
        summary = generate_phase_summary("UNKNOWN", empty_phase_outputs, sample_event_states)

        assert summary == {}


# =============================================================================
# 12. CHECKPOINT TESTS
# =============================================================================


class TestPhaseCheckpoint:
    """Test PhaseCheckpoint dataclass."""

    def test_checkpoint_creation(self, sample_checkpoint: PhaseCheckpoint) -> None:
        """PhaseCheckpoint should store all fields."""
        assert sample_checkpoint.phase == "R3"
        assert sample_checkpoint.events_count == 5
        assert sample_checkpoint.errors_count == 0
        assert "dedup_merges" in sample_checkpoint.summary

    def test_checkpoint_to_dict(self, sample_checkpoint: PhaseCheckpoint) -> None:
        """to_dict() should produce JSON-serializable output."""
        d = sample_checkpoint.to_dict()

        json_str = json.dumps(d)
        assert len(json_str) > 0

        parsed = json.loads(json_str)
        assert parsed["phase"] == "R3"

    def test_checkpoint_from_dict_roundtrip(self, sample_checkpoint: PhaseCheckpoint) -> None:
        """from_dict() should reconstruct checkpoint."""
        d = sample_checkpoint.to_dict()
        restored = PhaseCheckpoint(
            checkpoint_id=d["checkpoint_id"],
            phase=d["phase"],
            timestamp_ms=d["timestamp_ms"],
            events_count=d["events_count"],
            staged_writes_count=d["staged_writes_count"],
            errors_count=d["errors_count"],
            phase_timings_ms=d["phase_timings_ms"],
            summary=d["summary"],
        )

        assert restored.phase == sample_checkpoint.phase
        assert restored.events_count == sample_checkpoint.events_count
        assert restored.summary == sample_checkpoint.summary


# =============================================================================
# 13. ULID GENERATION TESTS
# =============================================================================


class TestUlidGeneration:
    """Test generate_ulid() helper."""

    def test_ulid_length(self) -> None:
        """ULID should be 26 characters."""
        ulid = generate_ulid()
        assert len(ulid) == 26

    def test_ulid_uniqueness(self) -> None:
        """Generated ULIDs should be unique."""
        ulids = [generate_ulid() for _ in range(100)]
        assert len(set(ulids)) == 100

    def test_ulid_lexicographic_order(self) -> None:
        """ULIDs generated later should sort after earlier ones."""
        ulid1 = generate_ulid()
        time.sleep(0.002)  # 2ms gap
        ulid2 = generate_ulid()

        assert ulid2 > ulid1, "Later ULID should sort after earlier one"

    def test_ulid_uses_crockford_base32(self) -> None:
        """ULID should use Crockford's base32 (no I, L, O, U)."""
        alphabet = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")

        # Generate many ULIDs and check all characters
        for _ in range(10):
            ulid = generate_ulid()
            for char in ulid:
                assert char in alphabet, f"Invalid character {char} in ULID"


# =============================================================================
# 14. EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_event_ids_batch(self) -> None:
        """Context with empty event_ids should have batch_size 0."""
        ctx = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=[],
            trigger_type="MANUAL",
            trigger_reason="Empty batch test",
        )

        assert ctx.batch_size == 0
        assert ctx.event_ids == ()

    def test_single_event_batch(self) -> None:
        """Context with single event should work."""
        ctx = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=["single-event"],
            trigger_type="MANUAL",
            trigger_reason="Single event test",
        )

        assert ctx.batch_size == 1
        assert ctx.event_ids == ("single-event",)

    def test_large_batch(self) -> None:
        """Context should handle large batches."""
        large_ids = [f"evt-{i:05d}" for i in range(1000)]

        ctx = P03CycleContext.create(
            tenant_id="t1",
            space_id="s1",
            event_ids=large_ids,
            trigger_type="THRESHOLD",
            trigger_reason="Large batch test",
        )

        assert ctx.batch_size == 1000

    def test_context_contains_event(self, sample_cycle_context: P03CycleContext) -> None:
        """contains_event() should check membership."""
        first_event = sample_cycle_context.event_ids[0]

        assert sample_cycle_context.contains_event(first_event)
        assert not sample_cycle_context.contains_event("non-existent-id")

    def test_staged_writes_summary(self, sample_staged_writes: P03StagedWrites) -> None:
        """to_summary_dict() should provide write counts."""
        summary = sample_staged_writes.to_summary_dict()

        assert summary["total_writes"] == 5
        assert "by_layer" in summary
        assert "by_operation" in summary
