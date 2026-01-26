"""
Tests for SemanticSimilarityEnricher (GAP-007 Epic 3.1).
"""

from __future__ import annotations

from typing import Mapping, cast
from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.semantic_similarity import (
    ExistingEdgeInfo,
    SemanticSimilarityEnricher,
)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phase_outputs import KGEntity
from k0.pipelines.p03.phases.r4_config import SemanticSimilarityConfig


def _entity(entity_id: str, embedding: bool = True) -> KGEntity:
    return KGEntity(
        entity_id=entity_id,
        canonical_name=entity_id,
        entity_type="THING",
        embedding=[0.1] * 768 if embedding else None,
        embedding_id=None if embedding else f"emb_{entity_id}",
    )


def _syscalls_with_results(results_sequence: list[list[dict]]) -> AsyncMock:
    syscalls = AsyncMock()
    results_iter = iter(results_sequence)

    async def _search(**kwargs):
        query_vector = kwargs.get("query_vector")
        if not query_vector:
            return {"results": []}
        if kwargs.get("tenant_id") != "tenant" or kwargs.get("space_id") != "space":
            return {"results": []}
        try:
            return {"results": next(results_iter)}
        except StopIteration:
            return {"results": []}

    syscalls.union_index_search.side_effect = _search
    syscalls.embedding_vectors_batch_query.return_value = {"vectors": {}, "count": 0}
    return syscalls


@pytest.mark.asyncio
async def test_finds_similar_entities():
    config = SemanticSimilarityConfig(similarity_threshold=0.5, k_neighbors=5)
    entity_a = _entity("entity_a")
    entity_b = _entity("entity_b")

    syscalls = _syscalls_with_results(
        [
            [
                {
                    "record_id": "entity_b",
                    "score": 0.9,
                }
            ],
            [],
        ]
    )

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    new_edges, updates = await enricher.enrich(
        entities=[entity_a, entity_b],
        entity_contexts={},
        existing_edges={},
        tenant_id="tenant",
        space_id="space",
    )

    assert len(new_edges) == 1
    assert len(updates) == 0
    assert new_edges[0].relationship_type == config.relation_type


@pytest.mark.asyncio
async def test_respects_threshold():
    config = SemanticSimilarityConfig(similarity_threshold=0.95, k_neighbors=5)
    entity_a = _entity("entity_a")

    syscalls = _syscalls_with_results(
        [
            [
                {
                    "record_id": "entity_b",
                    "score": 0.5,
                }
            ]
        ]
    )

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    new_edges, updates = await enricher.enrich(
        entities=[entity_a],
        entity_contexts={},
        existing_edges={},
        tenant_id="tenant",
        space_id="space",
    )

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_respects_max_edges_limit():
    config = SemanticSimilarityConfig(
        similarity_threshold=0.1,
        k_neighbors=5,
        max_edges_per_entity=1,
    )
    entity_a = _entity("entity_a")

    syscalls = _syscalls_with_results(
        [
            [
                {"record_id": "entity_b", "score": 0.9},
                {"record_id": "entity_c", "score": 0.8},
            ]
        ]
    )

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    new_edges, _ = await enricher.enrich(
        entities=[entity_a],
        entity_contexts={},
        existing_edges={},
        tenant_id="tenant",
        space_id="space",
    )

    assert len(new_edges) == 1


@pytest.mark.asyncio
async def test_skips_self_edges():
    config = SemanticSimilarityConfig(similarity_threshold=0.1, k_neighbors=5)
    entity_a = _entity("entity_a")

    syscalls = _syscalls_with_results(
        [
            [
                {"record_id": "entity_a", "score": 0.9},
            ]
        ]
    )

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    new_edges, _ = await enricher.enrich(
        entities=[entity_a],
        entity_contexts={},
        existing_edges={},
        tenant_id="tenant",
        space_id="space",
    )

    assert new_edges == []


@pytest.mark.asyncio
async def test_updates_existing_edges():
    config = SemanticSimilarityConfig(similarity_threshold=0.1, k_neighbors=5)
    entity_a = _entity("entity_a")

    syscalls = _syscalls_with_results(
        [
            [
                {"record_id": "entity_b", "score": 0.9},
            ]
        ]
    )

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    existing: Mapping[object, object] = cast(
        Mapping[object, object],
        {("entity_a", "entity_b"): ExistingEdgeInfo(edge_id="edge_existing")},
    )

    new_edges, updates = await enricher.enrich(
        entities=[entity_a],
        entity_contexts={},
        existing_edges=existing,
        tenant_id="tenant",
        space_id="space",
    )

    assert new_edges == []
    assert len(updates) == 1
    assert updates[0].edge_id == "edge_existing"


@pytest.mark.asyncio
async def test_attaches_context():
    config = SemanticSimilarityConfig(similarity_threshold=0.1, k_neighbors=5)
    entity_a = _entity("entity_a")

    syscalls = _syscalls_with_results(
        [
            [
                {"record_id": "entity_b", "score": 0.9},
            ]
        ]
    )

    context = ObservationContext(observed_at=123456, salience_score=0.9, source_event_id="evt1")

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    new_edges, _ = await enricher.enrich(
        entities=[entity_a],
        entity_contexts={"entity_a": [context]},
        existing_edges={},
        tenant_id="tenant",
        space_id="space",
    )

    assert len(new_edges) == 1
    assert new_edges[0].observation_context == context
    assert new_edges[0].evidence_event_ids == ["evt1"]


@pytest.mark.asyncio
async def test_canonical_edge_ordering():
    config = SemanticSimilarityConfig(similarity_threshold=0.1, k_neighbors=5)
    entity_b = _entity("entity_b")
    entity_a = _entity("entity_a")

    syscalls = _syscalls_with_results(
        [
            [
                {"record_id": "entity_a", "score": 0.9},
            ],
            [],
        ]
    )

    enricher = SemanticSimilarityEnricher(config=config, syscalls=syscalls)

    new_edges, _ = await enricher.enrich(
        entities=[entity_b, entity_a],
        entity_contexts={},
        existing_edges={},
        tenant_id="tenant",
        space_id="space",
    )

    assert len(new_edges) == 1
    assert new_edges[0].edge_id == "edge_entity_a_entity_b"
