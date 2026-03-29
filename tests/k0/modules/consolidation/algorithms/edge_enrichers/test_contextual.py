"""
Tests for ContextualEdgeEnricher (GAP-007 Epic 3.3).
"""

from __future__ import annotations

from typing import Mapping, cast

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.contextual import (
    ContextualEdgeEnricher,
    ExistingEdgeInfo,
)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phases.r4_config import ContextualEdgeConfig


def _context(event_id: str, **kwargs) -> ObservationContext:
    return ObservationContext(observed_at=1234, source_event_id=event_id, **kwargs)


@pytest.mark.asyncio
async def test_creates_edge_for_shared_context():
    config = ContextualEdgeConfig(similarity_threshold=0.2, max_edges_per_entity=5)
    enricher = ContextualEdgeEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", location_type="home")],
        "entity_b": [_context("evt2", location_type="home")],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert updates == []
    assert new_edges[0].relationship_type == config.relation_type


@pytest.mark.asyncio
async def test_respects_threshold():
    config = ContextualEdgeConfig(similarity_threshold=0.9)
    enricher = ContextualEdgeEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", location_type="home")],
        "entity_b": [_context("evt2", location_type="work")],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_updates_existing_edge():
    config = ContextualEdgeConfig(similarity_threshold=0.2)
    enricher = ContextualEdgeEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", social_context="family")],
        "entity_b": [_context("evt2", social_context="family")],
    }

    existing: Mapping[object, object] = cast(
        Mapping[object, object],
        {("entity_a", "entity_b"): ExistingEdgeInfo(edge_id="edge_existing")},
    )

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges=existing)

    assert new_edges == []
    assert len(updates) == 1
    assert updates[0].edge_id == "edge_existing"


@pytest.mark.asyncio
async def test_attaches_context_and_evidence():
    config = ContextualEdgeConfig(similarity_threshold=0.2)
    enricher = ContextualEdgeEnricher(config=config)

    context_a = _context("evt1", social_context="family", salience_score=0.9)
    context_b = _context("evt2", social_context="family", salience_score=0.2)

    entity_contexts = {
        "entity_a": [context_a],
        "entity_b": [context_b],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert new_edges[0].observation_context == context_a
    assert new_edges[0].evidence_event_ids == ["evt1", "evt2"]


@pytest.mark.asyncio
async def test_respects_max_edges_per_entity():
    config = ContextualEdgeConfig(similarity_threshold=0.2, max_edges_per_entity=1)
    enricher = ContextualEdgeEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", location_type="home")],
        "entity_b": [_context("evt2", location_type="home")],
        "entity_c": [_context("evt3", location_type="home")],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 2  # entity_a->entity_b, entity_b->entity_c
