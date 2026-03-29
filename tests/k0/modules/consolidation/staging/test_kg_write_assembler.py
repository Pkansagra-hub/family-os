"""
Unit tests for KGWriteAssembler — Issue 5.1.7

Tests KG (Knowledge Graph) layer write assembly from R4 phase outputs.

Spec Reference:
    - Dossier §4.8.7 (st_kg_dom / st_kg_edges KG Writes)
    - M5_EXECUTION.md Issue 5.1.7
"""

from __future__ import annotations

import json

import pytest

from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.kg_write_assembler import (
    KGWriteAssembler,
    count_kg_writes,
    summarize_kg_assembly,
)
from k0.pipelines.p03.phase_outputs import (
    CausalEdge,
    KGEdge,
    KGEdgeUpdate,
    KGEntity,
    KGEntityUpdate,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES, WriteOperation

# =============================================================================
# Fixtures
# =============================================================================

TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"


@pytest.fixture
def idempotency_gen() -> IdempotencyKeyGenerator:
    """Provide idempotency key generator."""
    return IdempotencyKeyGenerator(cycle_ulid=TEST_ULID)


@pytest.fixture
def assembler(idempotency_gen: IdempotencyKeyGenerator) -> KGWriteAssembler:
    """Provide assembler instance."""
    return KGWriteAssembler(idempotency_gen=idempotency_gen)


def make_entity(
    entity_id: str,
    name: str,
    entity_type: str = "PERSON",
    is_new: bool = True,
) -> KGEntity:
    """Create test KG entity."""
    return KGEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type=entity_type,
        aliases_json='["alias1"]',
        confidence=0.9,
        embedding_id=f"emb_{entity_id}",
        source_event_ids=["evt_001"],
        is_new=is_new,
    )


def make_edge(
    edge_id: str,
    source_id: str,
    target_id: str,
    rel_type: str = "KNOWS",
    is_new: bool = True,
) -> KGEdge:
    """Create test KG edge."""
    return KGEdge(
        edge_id=edge_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relationship_type=rel_type,
        relation_subtype="FRIEND",
        weight=0.8,
        confidence=0.9,
        is_causal=False,
        evidence_event_ids=["evt_001", "evt_002"],
        evidence_episode_ids=["epi_001"],
        last_observed_at=1700000000000,
        is_new=is_new,
    )


def make_causal_edge(
    cause_id: str,
    effect_id: str,
    lag_days: int = 7,
) -> CausalEdge:
    """Create test causal edge."""
    return CausalEdge(
        cause_entity_id=cause_id,
        effect_entity_id=effect_id,
        lag_days=lag_days,
        granger_p_value=0.01,
        effect_size=0.6,
        confidence=0.95,
    )


# =============================================================================
# Test: Assembler Initialization
# =============================================================================


class TestAssemblerInit:
    """Tests for assembler initialization."""

    def test_init_with_idempotency_gen(self, idempotency_gen: IdempotencyKeyGenerator):
        """Initialize with idempotency generator."""
        assembler = KGWriteAssembler(idempotency_gen=idempotency_gen)

        assert assembler.idempotency is idempotency_gen
        assert assembler.source_phase == "R6"

    def test_init_custom_phase(self, idempotency_gen: IdempotencyKeyGenerator):
        """Initialize with custom source phase."""
        assembler = KGWriteAssembler(
            idempotency_gen=idempotency_gen,
            source_phase="R4",
        )

        assert assembler.source_phase == "R4"


# =============================================================================
# Test: Entity Writes
# =============================================================================


class TestAssembleEntityWrites:
    """Tests for st_kg_dom (entity) assembly."""

    def test_empty_entities_returns_empty(self, assembler: KGWriteAssembler):
        """No entities produces no writes."""
        writes = assembler.assemble_entity_writes([])

        assert writes == []

    def test_new_entity_insert(self, assembler: KGWriteAssembler):
        """New entity (is_new=True) produces INSERT."""
        entity = make_entity("ent_001", "John Doe")

        writes = assembler.assemble_entity_writes([entity])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_KG_DOM
        assert write.operation == WriteOperation.INSERT
        assert write.record_id == "ent_001"

    def test_existing_entity_skipped(self, assembler: KGWriteAssembler):
        """Existing entity (is_new=False) without update is skipped."""
        entity = make_entity("ent_001", "John Doe", is_new=False)

        writes = assembler.assemble_entity_writes([entity])

        assert writes == []

    def test_entity_record_data_fields(self, assembler: KGWriteAssembler):
        """Entity write has correct record_data fields."""
        entity = make_entity("ent_001", "John Doe", "PERSON")

        writes = assembler.assemble_entity_writes([entity])

        data = writes[0].record_data
        assert data["entity_id"] == "ent_001"
        assert data["canonical_name"] == "John Doe"
        assert data["entity_type"] == "PERSON"
        assert data["attributes_json"] == "{}"
        assert data["confidence_score"] == 0.9
        assert data["embedding_id"] == "emb_ent_001"
        assert data["first_mentioned_event_id"] == "evt_001"
        assert isinstance(data["last_observed_at"], int)
        assert data["decay_factor"] == 1.0
        assert "source_episodes_json" in data
        assert "created_at" in data

    def test_entity_idempotency_key_format(self, assembler: KGWriteAssembler):
        """Entity write has correct idempotency key."""
        entity = make_entity("ent_001", "John Doe")

        writes = assembler.assemble_entity_writes([entity])

        expected = f"p03:write:{TEST_ULID}:st_kg_dom:ent_001"
        assert writes[0].idempotency_key == expected

    def test_entity_update(self, assembler: KGWriteAssembler):
        """Entity update produces UPDATE write."""
        update = KGEntityUpdate(
            entity_id="ent_001",
            field_updates={"canonical_name": "John Smith"},
            confidence_delta=0.05,
            new_aliases=["Johnny"],
        )

        writes = assembler.assemble_entity_writes([], [update])

        assert len(writes) == 1
        write = writes[0]
        assert write.operation == WriteOperation.UPDATE
        assert write.record_id == "ent_001"

    def test_multiple_entities(self, assembler: KGWriteAssembler):
        """Multiple entities produce multiple writes."""
        entities = [
            make_entity("ent_001", "John"),
            make_entity("ent_002", "Jane"),
            make_entity("ent_003", "Bob"),
        ]

        writes = assembler.assemble_entity_writes(entities)

        assert len(writes) == 3
        assert {w.record_id for w in writes} == {"ent_001", "ent_002", "ent_003"}


# =============================================================================
# Test: Edge Writes
# =============================================================================


class TestAssembleEdgeWrites:
    """Tests for st_kg_edges (relationship) assembly."""

    def test_empty_edges_returns_empty(self, assembler: KGWriteAssembler):
        """No edges produces no writes."""
        writes = assembler.assemble_edge_writes([])

        assert writes == []

    def test_new_edge_insert(self, assembler: KGWriteAssembler):
        """New edge (is_new=True) produces INSERT."""
        edge = make_edge("edge_001", "ent_001", "ent_002")

        writes = assembler.assemble_edge_writes([edge])

        assert len(writes) == 1
        write = writes[0]
        assert write.layer == LAYER_ST_KG_EDGES
        assert write.operation == WriteOperation.INSERT
        assert write.record_id == "edge_001"

    def test_edge_record_data_fields(self, assembler: KGWriteAssembler):
        """Edge write has correct record_data fields."""
        edge = make_edge("edge_001", "ent_001", "ent_002", "KNOWS")

        writes = assembler.assemble_edge_writes([edge])

        data = writes[0].record_data
        assert data["edge_id"] == "edge_001"
        assert data["source_entity_id"] == "ent_001"
        assert data["target_entity_id"] == "ent_002"
        assert data["relation_type"] == "KNOWS"
        assert data["relation_subtype"] == "FRIEND"
        assert data["edge_weight"] == 0.8
        assert data["confidence_score"] == 0.9
        assert data["co_occurrence_count"] == 2
        assert data["observation_count"] == 2
        assert data["last_observed_at"] == 1700000000000
        assert data["decay_factor"] == 1.0
        assert data["evidence_episode_ids"] == ["epi_001"]
        assert "source_episodes_json" in data

    def test_edge_idempotency_key_format(self, assembler: KGWriteAssembler):
        """Edge write has correct idempotency key."""
        edge = make_edge("edge_001", "ent_001", "ent_002")

        writes = assembler.assemble_edge_writes([edge])

        expected = f"p03:write:{TEST_ULID}:st_kg_edges:edge_001"
        assert writes[0].idempotency_key == expected

    def test_causal_edge_insert(self, assembler: KGWriteAssembler):
        """CausalEdge produces INSERT with is_causal=True."""
        causal = make_causal_edge("ent_001", "ent_002")

        writes = assembler.assemble_edge_writes([], causal_edges=[causal])

        assert len(writes) == 1
        write = writes[0]
        assert write.operation == WriteOperation.INSERT
        data = write.record_data
        assert data["relation_type"] == "CAUSES"
        assert data["edge_weight"] == 0.6
        assert data["confidence_score"] == 0.95
        props = json.loads(data["properties_json"])
        assert props["is_causal"] is True
        assert props["granger_p_value"] == 0.01
        assert props["lag_days"] == 7

    def test_causal_edge_id_format(self, assembler: KGWriteAssembler):
        """CausalEdge generates deterministic edge ID."""
        causal = make_causal_edge("cause_001", "effect_001")

        writes = assembler.assemble_edge_writes([], causal_edges=[causal])

        assert writes[0].record_id == "causal_cause_001_effect_001"

    def test_duplicate_edges_are_merged(self, assembler: KGWriteAssembler):
        """Duplicate edge_ids in the same batch are merged into one staged write."""
        e1 = KGEdge(
            edge_id="edge_dup",
            source_entity_id="ent_001",
            target_entity_id="ent_002",
            relationship_type="KNOWS",
            weight=0.4,
            confidence=0.7,
            evidence_event_ids=["evt_001"],
            is_new=True,
        )
        e2 = KGEdge(
            edge_id="edge_dup",
            source_entity_id="ent_001",
            target_entity_id="ent_002",
            relationship_type="KNOWS",
            weight=0.6,
            confidence=0.9,
            evidence_event_ids=["evt_002"],
            is_new=True,
        )

        writes = assembler.assemble_edge_writes([e1, e2])
        assert len(writes) == 1
        data = writes[0].record_data
        assert data["edge_id"] == "edge_dup"
        # non-causal reinforcement sums weights
        assert data["edge_weight"] == pytest.approx(1.0)
        # confidence preserves the strongest signal
        assert data["confidence_score"] == pytest.approx(0.9)
        # evidence ids unioned
        evidence = set(json.loads(data["source_episodes_json"]))
        assert evidence.issuperset({"evt_001", "evt_002"})

    def test_duplicate_causal_edges_are_merged(self, assembler: KGWriteAssembler):
        """Duplicate causal edges in the same batch are merged into one staged write."""
        c1 = CausalEdge(
            cause_entity_id="cluster_PERSON_michael",
            effect_entity_id="cluster_PERSON_sarah",
            lag_days=7,
            granger_p_value=0.05,
            effect_size=0.4,
            confidence=0.6,
        )
        c2 = CausalEdge(
            cause_entity_id="cluster_PERSON_michael",
            effect_entity_id="cluster_PERSON_sarah",
            lag_days=7,
            granger_p_value=0.01,
            effect_size=0.7,
            confidence=0.9,
        )

        writes = assembler.assemble_edge_writes([], causal_edges=[c1, c2])
        assert len(writes) == 1
        assert writes[0].record_id == "causal_cluster_PERSON_michael_cluster_PERSON_sarah"
        data = writes[0].record_data
        # CAUSES keeps the strongest effect size
        assert data["edge_weight"] == pytest.approx(0.7)
        assert data["confidence_score"] == pytest.approx(0.9)

    def test_edge_update(self, assembler: KGWriteAssembler):
        """Edge update produces UPDATE write."""
        update = KGEdgeUpdate(
            edge_id="edge_001",
            weight_delta=0.1,
            confidence_delta=0.05,
            new_evidence_ids=["evt_003"],
        )

        writes = assembler.assemble_edge_writes([], edge_updates=[update])

        assert len(writes) == 1
        write = writes[0]
        assert write.operation == WriteOperation.UPDATE
        assert write.record_id == "edge_001"


# =============================================================================
# Test: Foreign Key Validation
# =============================================================================


class TestValidateForeignKeys:
    """Tests for FK validation."""

    def test_valid_edges_pass(self, assembler: KGWriteAssembler):
        """Edges with valid FKs pass validation."""
        entity_ids = {"ent_001", "ent_002", "ent_003"}
        edges = [
            make_edge("edge_001", "ent_001", "ent_002"),
            make_edge("edge_002", "ent_002", "ent_003"),
        ]

        result = assembler.validate_foreign_keys(entity_ids, edges)

        assert result.is_valid
        assert result.errors == []
        assert result.orphan_edges == []

    def test_orphan_source_detected(self, assembler: KGWriteAssembler):
        """Edge with missing source entity is detected."""
        entity_ids = {"ent_002"}
        edges = [make_edge("edge_001", "ent_001", "ent_002")]

        result = assembler.validate_foreign_keys(entity_ids, edges)

        assert not result.is_valid
        assert "edge_001" in result.orphan_edges
        assert "ent_001" in result.errors[0]

    def test_orphan_target_detected(self, assembler: KGWriteAssembler):
        """Edge with missing target entity is detected."""
        entity_ids = {"ent_001"}
        edges = [make_edge("edge_001", "ent_001", "ent_002")]

        result = assembler.validate_foreign_keys(entity_ids, edges)

        assert not result.is_valid
        assert "edge_001" in result.orphan_edges
        assert "ent_002" in result.errors[0]

    def test_causal_edge_validation(self, assembler: KGWriteAssembler):
        """CausalEdge FKs are validated."""
        entity_ids = {"ent_001"}  # Missing ent_002
        causal = make_causal_edge("ent_001", "ent_002")

        result = assembler.validate_foreign_keys(entity_ids, [], [causal])

        assert not result.is_valid
        assert "causal_ent_001_ent_002" in result.orphan_edges


# =============================================================================
# Test: assemble_all
# =============================================================================


class TestAssembleAll:
    """Tests for aggregate assembly."""

    def test_assemble_all_empty(self, assembler: KGWriteAssembler):
        """No inputs produces empty lists."""
        entity_writes, edge_writes = assembler.assemble_all()

        assert entity_writes == []
        assert edge_writes == []

    def test_assemble_all_entities_only(self, assembler: KGWriteAssembler):
        """Entities without edges work."""
        entities = [make_entity("ent_001", "John")]

        entity_writes, edge_writes = assembler.assemble_all(entities=entities)

        assert len(entity_writes) == 1
        assert len(edge_writes) == 0

    def test_assemble_all_full(self, assembler: KGWriteAssembler):
        """Full assembly with entities, edges, causal."""
        entities = [make_entity("ent_001", "John"), make_entity("ent_002", "Jane")]
        edges = [make_edge("edge_001", "ent_001", "ent_002")]
        causal = [make_causal_edge("ent_001", "ent_002")]

        entity_writes, edge_writes = assembler.assemble_all(
            entities=entities,
            edges=edges,
            causal_edges=causal,
        )

        assert len(entity_writes) == 2
        assert len(edge_writes) == 2  # 1 regular + 1 causal

    def test_get_new_entity_ids(self, assembler: KGWriteAssembler):
        """get_new_entity_ids extracts IDs from new entities."""
        entities = [
            make_entity("ent_001", "John", is_new=True),
            make_entity("ent_002", "Jane", is_new=False),
            make_entity("ent_003", "Bob", is_new=True),
        ]

        new_ids = assembler.get_new_entity_ids(entities)

        assert new_ids == {"ent_001", "ent_003"}


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_count_kg_writes(self, assembler: KGWriteAssembler):
        """count_kg_writes returns correct counts."""
        entities = [make_entity("ent_001", "John")]
        edges = [make_edge("edge_001", "ent_001", "ent_002")]
        entity_writes, edge_writes = assembler.assemble_all(entities=entities, edges=edges)

        counts = count_kg_writes(entity_writes, edge_writes)

        assert counts["entity_inserts"] == 1
        assert counts["entity_updates"] == 0
        assert counts["edge_inserts"] == 1
        assert counts["edge_updates"] == 0

    def test_summarize_kg_assembly(self, assembler: KGWriteAssembler):
        """summarize_kg_assembly produces readable output."""
        entities = [make_entity("ent_001", "John")]
        edges = [make_edge("edge_001", "ent_001", "ent_002")]
        entity_writes, edge_writes = assembler.assemble_all(entities=entities, edges=edges)

        summary = summarize_kg_assembly(entity_writes, edge_writes)

        assert "st_kg_dom" in summary
        assert "st_kg_edges" in summary
        assert "1 inserts" in summary


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_entity_with_empty_aliases(self, assembler: KGWriteAssembler):
        """Entity with no aliases still works."""
        entity = KGEntity(
            entity_id="ent_001",
            canonical_name="John",
            entity_type="PERSON",
            aliases_json="[]",
            confidence=0.5,
            is_new=True,
        )

        writes = assembler.assemble_entity_writes([entity])

        assert len(writes) == 1
        assert writes[0].record_data["aliases_json"] == "[]"

    def test_edge_with_no_evidence(self, assembler: KGWriteAssembler):
        """Edge with empty evidence still works."""
        edge = KGEdge(
            edge_id="edge_001",
            source_entity_id="ent_001",
            target_entity_id="ent_002",
            relationship_type="KNOWS",
            evidence_event_ids=[],
            is_new=True,
        )

        writes = assembler.assemble_edge_writes([edge])

        assert len(writes) == 1
        assert writes[0].record_data["source_episodes_json"] == "[]"

    def test_empty_update_id_skipped(self, assembler: KGWriteAssembler):
        """Update with empty ID is skipped."""
        update = KGEntityUpdate(entity_id="")

        writes = assembler.assemble_entity_writes([], [update])

        assert writes == []
