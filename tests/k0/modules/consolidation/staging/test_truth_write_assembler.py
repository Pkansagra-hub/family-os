"""
Unit tests for TruthWriteAssembler — Issue 5.1.6

Tests truth layer write assembly from R2-R5 phase outputs.

Spec Reference:
    - Dossier §4.7.2 (R6 Staging — Truth Layer Assembly)
    - M5_EXECUTION.md Issue 5.1.6
"""

from __future__ import annotations

from typing import List

import pytest

from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.truth_write_assembler import (
    TruthWriteAssembler,
    flatten_writes,
    summarize_assembly,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_outputs import (
    EpisodeCluster,
    GapCandidate,
    ProspectiveMemory,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_LEARNING_QUEUE,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    WriteOperation,
)

# =============================================================================
# Fixtures
# =============================================================================

TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"


@pytest.fixture
def idempotency_gen() -> IdempotencyKeyGenerator:
    """Provide idempotency key generator."""
    return IdempotencyKeyGenerator(cycle_ulid=TEST_ULID)


@pytest.fixture
def assembler(idempotency_gen: IdempotencyKeyGenerator) -> TruthWriteAssembler:
    """Provide assembler instance."""
    return TruthWriteAssembler(idempotency_gen=idempotency_gen)


def make_cluster(cluster_id: str, event_ids: List[str]) -> EpisodeCluster:
    """Create test episode cluster."""
    return EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=event_ids,
        centroid_embedding_id="emb_001",
        dominant_sentiment=0.6,
        dominant_emotion="joy",
        temporal_start=1700000000000,
        temporal_end=1700003600000,
        location_hint="home",
        participants_json='["mom", "dad"]',
        activity_type="meal",
        cohesion_score=0.85,
        title="Family Dinner",
        summary="Had dinner with family",
    )


def make_event_state(
    event_id: str,
    action: ReconciliationAction,
    match_id: str | None = None,
) -> P03EventState:
    """Create test event state with reconciliation."""
    state = P03EventState(event_id=event_id)
    state.set_reconciliation(
        action=action,
        match_id=match_id,
        match_layer="st_sem" if match_id else None,
        similarity=0.85 if match_id else 0.0,
        confidence=0.9,
        reason="test reason",
    )
    return state


def make_gap(gap_id: str, entity_id: str) -> GapCandidate:
    """Create test gap candidate."""
    return GapCandidate(
        gap_id=gap_id,
        gap_type="AMBIGUITY",
        related_entity_id=entity_id,
        entropy_score=0.7,
        priority="HIGH",
        context_json='{"hint": "needs clarification"}',
        candidate_values=["option_a", "option_b"],
    )


def make_intention(prosp_id: str, desc: str) -> ProspectiveMemory:
    """Create test prospective memory."""
    return ProspectiveMemory(
        prosp_id=prosp_id,
        intention_type="REMINDER",
        description=desc,
        trigger_condition="tomorrow morning",
        action_to_take="call mom",
        deadline_ts=1700100000000,
        importance=0.8,
        source_episode_id="epi_001",
    )


# =============================================================================
# Test: Assembler Initialization
# =============================================================================


class TestAssemblerInit:
    """Tests for assembler initialization."""

    def test_init_with_idempotency_gen(self, idempotency_gen: IdempotencyKeyGenerator):
        """Initialize with idempotency generator."""
        assembler = TruthWriteAssembler(idempotency_gen=idempotency_gen)

        assert assembler.idempotency is idempotency_gen
        assert assembler.source_phase == "R6"

    def test_init_custom_phase(self, idempotency_gen: IdempotencyKeyGenerator):
        """Initialize with custom source phase."""
        assembler = TruthWriteAssembler(
            idempotency_gen=idempotency_gen,
            source_phase="R5",
        )

        assert assembler.source_phase == "R5"


# =============================================================================
# Test: st_epi Assembly
# =============================================================================


class TestAssembleEpiWrites:
    """Tests for st_epi (episodic memory) assembly."""

    def test_empty_clusters_returns_empty(self, assembler: TruthWriteAssembler):
        """No clusters produces no writes."""
        writes = assembler.assemble_epi_writes([], {})

        assert writes == []

    def test_single_cluster_insert(self, assembler: TruthWriteAssembler):
        """Single cluster produces INSERT write."""
        cluster = make_cluster("epi_001", ["evt_001", "evt_002"])

        writes = assembler.assemble_epi_writes([cluster], {})

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_EPI
        assert write.operation == WriteOperation.INSERT
        assert write.record_id == "epi_001"
        assert write.source_event_ids == ["evt_001", "evt_002"]

    def test_cluster_record_data_fields(self, assembler: TruthWriteAssembler):
        """Cluster write has correct record_data fields."""
        cluster = make_cluster("epi_001", ["evt_001"])

        writes = assembler.assemble_epi_writes([cluster], {})

        data = writes[0].record_data
        assert data["episode_id"] == "epi_001"
        assert data["title"] == "Family Dinner"
        assert data["summary"] == "Had dinner with family"
        assert data["start_ts"] == 1700000000000
        assert data["end_ts"] == 1700003600000
        assert data["location_hint"] == "home"
        assert data["dominant_emotion"] == "joy"
        assert data["cohesion_score"] == 0.85
        assert "member_event_ids_json" in data

    def test_cluster_idempotency_key_format(self, assembler: TruthWriteAssembler):
        """Cluster write has correct idempotency key."""
        cluster = make_cluster("epi_001", ["evt_001"])

        writes = assembler.assemble_epi_writes([cluster], {})

        assert f"p03:write:{TEST_ULID}:st_epi:epi_001" == writes[0].idempotency_key

    def test_multiple_clusters(self, assembler: TruthWriteAssembler):
        """Multiple clusters produce multiple writes."""
        clusters = [
            make_cluster("epi_001", ["evt_001"]),
            make_cluster("epi_002", ["evt_002", "evt_003"]),
        ]

        writes = assembler.assemble_epi_writes(clusters, {})

        assert len(writes) == 2
        assert {w.record_id for w in writes} == {"epi_001", "epi_002"}


# =============================================================================
# Test: st_sem Assembly
# =============================================================================


class TestAssembleSemWrites:
    """Tests for st_sem (semantic memory) assembly."""

    def test_empty_states_returns_empty(self, assembler: TruthWriteAssembler):
        """No event states produces no writes."""
        writes = assembler.assemble_sem_writes({})

        assert writes == []

    def test_create_action_produces_insert(self, assembler: TruthWriteAssembler):
        """CREATE action produces INSERT write."""
        state = make_event_state("evt_001", ReconciliationAction.CREATE)
        states = {"evt_001": state}

        writes = assembler.assemble_sem_writes(states)

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_SEM
        assert write.operation == WriteOperation.INSERT
        assert write.record_id == "sem_evt_001"

    def test_reinforce_action_produces_update(self, assembler: TruthWriteAssembler):
        """REINFORCE action produces UPDATE write."""
        state = make_event_state("evt_001", ReconciliationAction.REINFORCE, "pattern_001")
        states = {"evt_001": state}

        writes = assembler.assemble_sem_writes(states)

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_SEM
        assert write.operation == WriteOperation.UPDATE
        assert write.record_id == "pattern_001"

    def test_extend_action_produces_update(self, assembler: TruthWriteAssembler):
        """EXTEND action produces UPDATE write."""
        state = make_event_state("evt_001", ReconciliationAction.EXTEND, "pattern_002")
        states = {"evt_001": state}

        writes = assembler.assemble_sem_writes(states)

        assert len(writes) == 1
        assert writes[0].operation == WriteOperation.UPDATE

    def test_prune_action_produces_archive(self, assembler: TruthWriteAssembler):
        """PRUNE action produces ARCHIVE write."""
        state = make_event_state("evt_001", ReconciliationAction.PRUNE, "pattern_003")
        states = {"evt_001": state}

        writes = assembler.assemble_sem_writes(states)

        assert len(writes) == 1
        write = writes[0]
        assert write.operation == WriteOperation.ARCHIVE

    def test_skip_action_no_write(self, assembler: TruthWriteAssembler):
        """SKIP action produces no write."""
        state = make_event_state("evt_001", ReconciliationAction.SKIP)
        states = {"evt_001": state}

        writes = assembler.assemble_sem_writes(states)

        assert writes == []

    def test_pending_action_no_write(self, assembler: TruthWriteAssembler):
        """PENDING action produces no write."""
        state = P03EventState(event_id="evt_001")
        state.reconciliation_action = ReconciliationAction.PENDING
        states = {"evt_001": state}

        writes = assembler.assemble_sem_writes(states)

        assert writes == []


# =============================================================================
# Test: st_learning_queue Assembly
# =============================================================================


class TestAssembleLearningQueueWrites:
    """Tests for st_learning_queue (P06 gaps) assembly."""

    def test_empty_gaps_returns_empty(self, assembler: TruthWriteAssembler):
        """No gaps produces no writes."""
        writes = assembler.assemble_learning_queue_writes([])

        assert writes == []

    def test_single_gap_insert(self, assembler: TruthWriteAssembler):
        """Single gap produces INSERT write."""
        gap = make_gap("gap_001", "entity_001")

        writes = assembler.assemble_learning_queue_writes([gap])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_LEARNING_QUEUE
        assert write.operation == WriteOperation.INSERT
        assert write.record_id == "gap_001"

    def test_gap_record_data_fields(self, assembler: TruthWriteAssembler):
        """Gap write has correct record_data fields."""
        gap = make_gap("gap_001", "entity_001")

        writes = assembler.assemble_learning_queue_writes([gap])

        data = writes[0].record_data
        assert data["gap_id"] == "gap_001"
        assert data["gap_type"] == "AMBIGUITY"
        assert data["related_entity_id"] == "entity_001"
        assert data["entropy_score"] == 0.7
        assert data["priority"] == "HIGH"
        assert data["status"] == "PENDING"
        assert "candidate_values_json" in data

    def test_multiple_gaps(self, assembler: TruthWriteAssembler):
        """Multiple gaps produce multiple writes."""
        gaps = [make_gap("gap_001", "e1"), make_gap("gap_002", "e2")]

        writes = assembler.assemble_learning_queue_writes(gaps)

        assert len(writes) == 2


# =============================================================================
# Test: st_prospective Assembly
# =============================================================================


class TestAssembleProspectiveWrites:
    """Tests for st_prospective (future intentions) assembly."""

    def test_empty_intentions_returns_empty(self, assembler: TruthWriteAssembler):
        """No intentions produces no writes."""
        writes = assembler.assemble_prospective_writes([])

        assert writes == []

    def test_single_intention_insert(self, assembler: TruthWriteAssembler):
        """Single intention produces INSERT write."""
        intention = make_intention("prosp_001", "Call mom tomorrow")

        writes = assembler.assemble_prospective_writes([intention])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_PROSPECTIVE
        assert write.operation == WriteOperation.INSERT
        assert write.record_id == "prosp_001"

    def test_intention_record_data_fields(self, assembler: TruthWriteAssembler):
        """Intention write has correct record_data fields."""
        intention = make_intention("prosp_001", "Call mom tomorrow")

        writes = assembler.assemble_prospective_writes([intention])

        data = writes[0].record_data
        assert data["prosp_id"] == "prosp_001"
        assert data["intention_type"] == "REMINDER"
        assert data["description"] == "Call mom tomorrow"
        assert data["trigger_condition"] == "tomorrow morning"
        assert data["importance"] == 0.8


# =============================================================================
# Test: assemble_all
# =============================================================================


class TestAssembleAll:
    """Tests for aggregate assembly."""

    def test_assemble_all_empty(self, assembler: TruthWriteAssembler):
        """No inputs produces empty dict."""
        result = assembler.assemble_all()

        assert result == {}

    def test_assemble_all_with_clusters(self, assembler: TruthWriteAssembler):
        """Clusters appear in result."""
        clusters = [make_cluster("epi_001", ["evt_001"])]

        result = assembler.assemble_all(clusters=clusters)

        assert LAYER_ST_EPI in result
        assert len(result[LAYER_ST_EPI]) == 1

    def test_assemble_all_with_gaps(self, assembler: TruthWriteAssembler):
        """Gaps appear in result."""
        gaps = [make_gap("gap_001", "e1")]

        result = assembler.assemble_all(gaps=gaps)

        assert LAYER_ST_LEARNING_QUEUE in result

    def test_assemble_all_mixed(self, assembler: TruthWriteAssembler):
        """Multiple layer types work together."""
        clusters = [make_cluster("epi_001", ["evt_001"])]
        gaps = [make_gap("gap_001", "e1")]
        intentions = [make_intention("prosp_001", "test")]

        result = assembler.assemble_all(
            clusters=clusters,
            gaps=gaps,
            intentions=intentions,
        )

        assert len(result) == 3
        assert LAYER_ST_EPI in result
        assert LAYER_ST_LEARNING_QUEUE in result
        assert LAYER_ST_PROSPECTIVE in result

    def test_count_writes(self, assembler: TruthWriteAssembler):
        """count_writes returns correct counts."""
        clusters = [make_cluster("epi_001", []), make_cluster("epi_002", [])]
        gaps = [make_gap("gap_001", "e1")]

        assembled = assembler.assemble_all(clusters=clusters, gaps=gaps)
        counts = assembler.count_writes(assembled)

        assert counts[LAYER_ST_EPI] == 2
        assert counts[LAYER_ST_LEARNING_QUEUE] == 1


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_flatten_writes(self, assembler: TruthWriteAssembler):
        """flatten_writes returns flat list."""
        clusters = [make_cluster("epi_001", [])]
        gaps = [make_gap("gap_001", "e1")]

        assembled = assembler.assemble_all(clusters=clusters, gaps=gaps)
        flat = flatten_writes(assembled)

        assert len(flat) == 2
        assert all(hasattr(w, "write_id") for w in flat)

    def test_summarize_assembly(self, assembler: TruthWriteAssembler):
        """summarize_assembly produces readable output."""
        clusters = [make_cluster("epi_001", [])]
        gaps = [make_gap("gap_001", "e1")]

        assembled = assembler.assemble_all(clusters=clusters, gaps=gaps)
        summary = summarize_assembly(assembled)

        assert "st_epi: 1" in summary
        assert "st_learning_queue: 1" in summary
        assert "Total: 2" in summary
