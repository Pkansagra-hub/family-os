"""
P03 Envelope Test Fixtures.

Provides reusable fixtures for testing P03 envelope components:
- Context fixtures (cycle context, trace IDs)
- Event state fixtures (single and batch)
- Phase output fixtures
- Staged writes fixtures
- Observability fixtures
- Full envelope fixtures

Issue 1.1.8: Envelope model tests + fixtures
"""

from __future__ import annotations

import time
from typing import List

import pytest

from k0.pipelines.p03 import (  # Context; Phase Outputs; Staged Writes
    LAYER_ST_EPI,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_SEM,
    LAYER_ST_VEC,
    CausalEdge,
    CycleSummary,
    DecayUpdate,
    DedupMerge,
    EmittedEvent,
    EpisodeCluster,
    HebbianEdgeUpdate,
    KGEdge,
    KGEntity,
    P03CycleContext,
    P03EventState,
    P03ObservabilityContext,
    P03PhaseOutputs,
    P03StagedWrites,
    PhaseCheckpoint,
    PruneDecision,
    ReconciliationAction,
    ReconciliationSummary,
    ScoredEvent,
    StagedWrite,
    WriteManifest,
)

# =============================================================================
# DETERMINISTIC IDS FOR TESTING
# =============================================================================


@pytest.fixture
def sample_event_ids() -> List[str]:
    """
    Deterministic list of event IDs for batch testing.

    Returns 5 ULIDs that are:
    - Lexicographically sortable
    - Deterministic across test runs
    - Unique within the batch
    """
    return [
        "01JFXYZ000000000000000001",
        "01JFXYZ000000000000000002",
        "01JFXYZ000000000000000003",
        "01JFXYZ000000000000000004",
        "01JFXYZ000000000000000005",
    ]


@pytest.fixture
def sample_tenant_id() -> str:
    """Deterministic tenant ID for testing."""
    return "tenant-test-001"


@pytest.fixture
def sample_space_id() -> str:
    """Deterministic space ID for testing."""
    return "family-test-abc"


# =============================================================================
# CONTEXT FIXTURES
# =============================================================================


@pytest.fixture
def sample_cycle_context(
    sample_tenant_id: str,
    sample_space_id: str,
    sample_event_ids: List[str],
) -> P03CycleContext:
    """
    Pre-built P03CycleContext with deterministic values.

    Uses the factory method to ensure proper initialization.
    """
    return P03CycleContext.create(
        tenant_id=sample_tenant_id,
        space_id=sample_space_id,
        event_ids=sample_event_ids,
        trigger_type="MANUAL",
        trigger_reason="Test fixture context",
        priority=50,
        qos_band="GREEN",
        deadline_ms=300000,
        pending_before=10,
    )


@pytest.fixture
def minimal_cycle_context() -> P03CycleContext:
    """Minimal context with only required fields."""
    return P03CycleContext.create(
        tenant_id="t1",
        space_id="s1",
        event_ids=["evt-1", "evt-2"],
        trigger_type="INTERVAL",
        trigger_reason="Scheduled",
    )


# =============================================================================
# EVENT STATE FIXTURES
# =============================================================================


@pytest.fixture
def sample_event_state() -> P03EventState:
    """
    Single P03EventState with P02 pre-computed data.

    Simulates an event that has been through P02 NLP pipeline.
    """
    return P03EventState(
        event_id="01JFXYZ000000000000000001",
        hipp_event_id="hipp-event-001",
        content_text="Dad took Emma to soccer practice at 3pm",
        content_type="CHAT",
        content_hash="abc123def456",
        simhash_hex="FEDCBA9876543210",
        timestamp=int(time.time() * 1000),
        channel_id="family-chat",
        embedding_id="vec-001",
        embedding_768=None,  # Lazy load - not materialized
        sentiment_score=0.7,
        sentiment_label="positive",
        emotions_json='["joy", "anticipation"]',
        intent_label="INFORM_ACTIVITY",
        ner_entities_json='[{"text": "Emma", "type": "PERSON"}, {"text": "soccer practice", "type": "ACTIVITY"}]',
        temporal_expressions_json='[{"text": "3pm", "type": "TIME"}]',
    )


@pytest.fixture
def sample_event_states(sample_event_ids: List[str]) -> List[P03EventState]:
    """
    Batch of P03EventState instances for testing.

    Each event has unique content but follows same pattern.
    """
    events = []
    base_ts = int(time.time() * 1000)

    content_samples = [
        ("Dad picked up Emma from school", "CHAT", "joy"),
        ("Mom scheduled dentist appointment", "CALENDAR", "neutral"),
        ("Paid electricity bill $150", "TRANSACTION", "neutral"),
        ("Family movie night at 7pm", "CHAT", "anticipation"),
        ("Emma got A+ on math test", "CHAT", "joy"),
    ]

    for i, event_id in enumerate(sample_event_ids):
        text, ctype, sentiment = content_samples[i]
        events.append(
            P03EventState(
                event_id=event_id,
                hipp_event_id=f"hipp-{i+1:03d}",
                content_text=text,
                content_type=ctype,
                content_hash=f"hash-{i+1:03d}",
                simhash_hex=f"{i:016X}",
                timestamp=base_ts + (i * 1000),
                channel_id="family-chat",
                embedding_id=f"vec-{i+1:03d}",
                sentiment_score=0.7 if sentiment != "neutral" else 0.0,
                sentiment_label=sentiment,
            )
        )

    return events


@pytest.fixture
def enriched_event_state() -> P03EventState:
    """
    Event state with R1-R3 enrichment applied.

    Simulates an event that has been through scoring, clustering,
    and reconciliation phases.
    """
    event = P03EventState(
        event_id="01JFXYZ000000000000000001",
        hipp_event_id="hipp-event-001",
        content_text="Dad took Emma to soccer practice",
        content_type="CHAT",
        content_hash="abc123",
        timestamp=int(time.time() * 1000),
        channel_id="family-chat",
        embedding_id="vec-001",
    )

    # R1: Importance scoring
    event.importance_score = 0.85
    event.recency_factor = 0.9
    event.affect_factor = 0.7
    event.social_factor = 0.8
    event.novelty_factor = 0.6
    event.importance_computed = True

    # R2: Clustering
    event.cluster_id = "cluster-001"
    event.cluster_label = 0
    event.is_noise = False
    event.centroid_distance = 0.15

    # R3: Reconciliation
    event.reconciliation_action = ReconciliationAction.REINFORCE
    event.best_match_id = "truth-record-001"
    event.best_match_layer = "st_epi"
    event.similarity_score = 0.92
    event.confidence = 0.88
    event.reconciliation_reason = "High similarity to existing episodic memory"
    event.is_duplicate = False
    event.decay_score = 0.95
    event.prune_decision = PruneDecision.KEEP

    return event


# =============================================================================
# PHASE OUTPUT FIXTURES
# =============================================================================


@pytest.fixture
def sample_phase_outputs() -> P03PhaseOutputs:
    """
    P03PhaseOutputs with sample data for each phase.

    Contains minimal but valid data for testing serialization.
    """
    outputs = P03PhaseOutputs()

    # R1 outputs
    outputs.r1_scored_events = [
        ScoredEvent(
            event_id="evt-1",
            importance_score=0.85,
            recency_factor=0.9,
            affect_factor=0.7,
            social_factor=0.8,
            novelty_factor=0.6,
        ),
    ]
    outputs.r1_hebbian_updates = [
        HebbianEdgeUpdate(
            source_entity_id="entity-1",
            target_entity_id="entity-2",
            old_weight=0.70,
            new_weight=0.75,
            delta=0.05,
            update_type="STRENGTHEN",
        ),
    ]

    # R2 outputs
    outputs.r2_clusters = [
        EpisodeCluster(
            cluster_id="cluster-001",
            member_event_ids=["evt-1", "evt-2"],
            centroid_embedding_id="centroid-001",
            dominant_sentiment=0.8,
            temporal_start=1000000,
            temporal_end=4600000,
            title="Family activity",
        ),
    ]
    outputs.r2_noise_event_ids = ["evt-5"]
    outputs.r2_avg_cluster_size = 2.0

    # R3 outputs
    outputs.r3_dedup_merges = [
        DedupMerge(
            duplicate_id="evt-1-dup",
            canonical_id="evt-1",
            hamming_distance=3,
            merge_confidence=0.95,
            content_type="CHAT",
        ),
    ]
    outputs.r3_decay_updates = [
        DecayUpdate(
            record_id="truth-001",
            layer="st_epi",
            old_decay=0.9,
            new_decay=0.85,
            days_since_access=7,
            decision="KEEP",
        ),
    ]

    # R4 outputs
    outputs.r4_new_entities = [
        KGEntity(
            entity_id="entity-new-001",
            canonical_name="Emma",
            entity_type="PERSON",
            aliases_json='["Emmy"]',
            source_event_ids=["evt-1"],
            confidence=0.95,
        ),
    ]
    outputs.r4_new_edges = [
        KGEdge(
            edge_id="edge-new-001",
            source_entity_id="entity-dad",
            target_entity_id="entity-emma",
            relationship_type="PARENT_OF",
            weight=0.9,
            confidence=0.99,
            evidence_event_ids=["evt-1"],
        ),
    ]
    outputs.r4_causal_edges = [
        CausalEdge(
            cause_entity_id="entity-1",
            effect_entity_id="entity-2",
            lag_days=1,
            granger_p_value=0.01,
            effect_size=0.5,
            confidence=0.7,
        ),
    ]

    # R6 outputs
    outputs.r6_summary = ReconciliationSummary(
        reinforce_count=3,
        extend_count=1,
        create_count=2,
        evolve_count=0,
        contradict_count=0,
        skip_count=1,
        prune_count=0,
    )

    # R7 outputs
    outputs.r7_manifest = WriteManifest(
        cycle_id="cycle-001",
        total_writes=5,
        successful_writes=5,
        failed_writes=0,
        tables_touched=["st_epi", "st_kg_dom", "st_kg_edges"],
    )
    outputs.r7_success = True

    # R8 outputs
    outputs.r8_emitted_events = [
        EmittedEvent(
            event_id="emit-001",
            topic="p03.cycle.completed",
            payload_summary="Cycle cycle-001 completed with 5 events",
            timestamp=int(time.time() * 1000),
        ),
    ]
    base_ts = int(time.time() * 1000)
    outputs.r8_cycle_summary = CycleSummary(
        cycle_id="cycle-001",
        batch_id="batch-001",
        events_processed=5,
        events_skipped=0,
        episodes_created=2,
        entities_created=2,
        edges_created=3,
        insights_generated=0,
        gaps_detected=0,
        writes_committed=5,
        writes_failed=0,
        duration_ms=1500,
        started_at=base_ts - 1500,
        completed_at=base_ts,
        final_status="SUCCESS",
    )
    outputs.r8_success = True

    return outputs


@pytest.fixture
def empty_phase_outputs() -> P03PhaseOutputs:
    """Empty P03PhaseOutputs with all defaults."""
    return P03PhaseOutputs()


# =============================================================================
# STAGED WRITES FIXTURES
# =============================================================================


@pytest.fixture
def sample_staged_writes() -> P03StagedWrites:
    """
    P03StagedWrites with sample writes per layer.

    Contains writes to different truth layers.
    """
    staged = P03StagedWrites()

    # Add writes to different layers
    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi-001",
            data={"content": "Family dinner event", "importance": 0.8},
            phase="R6",
            event_ids=["evt-1"],
        )
    )

    staged.add_write(
        StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id="sem-001",
            data={"decay_score": 0.85},
            phase="R6",
            expected_version=2,
        )
    )

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id="entity-001",
            data={"type": "PERSON", "name": "Emma"},
            phase="R4",
            event_ids=["evt-1"],
        )
    )

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_KG_EDGES,
            record_id="edge-001",
            data={"source": "entity-dad", "target": "entity-emma", "type": "PARENT_OF"},
            phase="R4",
            event_ids=["evt-1"],
        )
    )

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_VEC,
            record_id="vec-001",
            data={"embedding_id": "vec-001"},
            phase="R6",
        )
    )

    return staged


@pytest.fixture
def empty_staged_writes() -> P03StagedWrites:
    """Empty P03StagedWrites container."""
    return P03StagedWrites()


# =============================================================================
# OBSERVABILITY FIXTURES
# =============================================================================


@pytest.fixture
def sample_observability_context() -> P03ObservabilityContext:
    """
    P03ObservabilityContext with sample timing and metrics.

    Simulates a cycle that has completed several phases.
    """
    obs = P03ObservabilityContext.create(
        log_context={"tenant_id": "tenant-test-001", "space_id": "family-test-abc"}
    )

    # Simulate phase timings
    obs.start_phase("R0")
    obs.end_phase("R0")
    obs.start_phase("R1")
    obs.end_phase("R1")
    obs.start_phase("R2")
    obs.end_phase("R2")

    # Add some metrics
    obs.increment("events_loaded", 5)
    obs.increment("events_scored", 5)
    obs.increment("clusters_created", 2)
    obs.record_histogram("importance_scores", 0.8)
    obs.record_histogram("importance_scores", 0.7)
    obs.record_histogram("importance_scores", 0.9)

    return obs


@pytest.fixture
def observability_with_errors() -> P03ObservabilityContext:
    """Observability context with recorded errors."""
    obs = P03ObservabilityContext.create()

    obs.record_error(
        phase="R2",
        stage_id="clustering",
        error_type="ValidationError",
        error_message="Invalid embedding dimension",
        recoverable=True,
    )

    obs.record_error(
        phase="R3",
        stage_id="dedup",
        error_type="DatabaseError",
        error_message="Connection timeout",
        recoverable=False,
    )

    return obs


@pytest.fixture
def fresh_observability_context() -> P03ObservabilityContext:
    """Fresh observability context with no activity."""
    return P03ObservabilityContext.create()


# =============================================================================
# SERIALIZER FIXTURES
# =============================================================================


@pytest.fixture
def sample_checkpoint() -> PhaseCheckpoint:
    """Sample phase checkpoint."""
    return PhaseCheckpoint.create(
        phase="R3",
        events_count=5,
        staged_writes_count=3,
        errors_count=0,
        phase_timings_ms={"R0": 10, "R1": 50, "R2": 80},
        summary={"dedup_merges": 1, "archive_candidates": 0},
    )


@pytest.fixture
def sample_checkpoints() -> List[PhaseCheckpoint]:
    """List of checkpoints for multiple phases."""
    return [
        PhaseCheckpoint.create(
            phase="R0",
            events_count=5,
            staged_writes_count=0,
            errors_count=0,
            phase_timings_ms={"R0": 10},
            summary={"events_loaded": 5},
        ),
        PhaseCheckpoint.create(
            phase="R1",
            events_count=5,
            staged_writes_count=0,
            errors_count=0,
            phase_timings_ms={"R0": 10, "R1": 50},
            summary={"events_scored": 5, "avg_importance": 0.75},
        ),
        PhaseCheckpoint.create(
            phase="R2",
            events_count=5,
            staged_writes_count=0,
            errors_count=0,
            phase_timings_ms={"R0": 10, "R1": 50, "R2": 80},
            summary={"cluster_count": 2, "noise_count": 1},
        ),
    ]
