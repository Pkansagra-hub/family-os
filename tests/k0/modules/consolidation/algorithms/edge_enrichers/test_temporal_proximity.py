"""
Tests for TemporalProximityEnricher (GAP-007 Epic 3.2).
"""

from __future__ import annotations

from typing import Mapping, cast

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.temporal_proximity import (
    ExistingEdgeInfo,
    TemporalProximityEnricher,
)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phases.r4_config import TemporalProximityConfig


def _context(event_id: str, observed_at: int, salience: float) -> ObservationContext:
    return ObservationContext(
        observed_at=observed_at,
        salience_score=salience,
        source_event_id=event_id,
    )


@pytest.mark.asyncio
async def test_creates_edges_within_window():
    config = TemporalProximityConfig(window_ms=1000, tau_ms=500, min_weight=0.1)
    enricher = TemporalProximityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000, 0.2)],
        "entity_b": [_context("evt2", 1500, 0.3)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert updates == []
    assert new_edges[0].relationship_type == config.relation_type


@pytest.mark.asyncio
async def test_respects_window():
    config = TemporalProximityConfig(window_ms=1000, tau_ms=500, min_weight=0.1)
    enricher = TemporalProximityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000, 0.2)],
        "entity_b": [_context("evt2", 3005, 0.3)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_respects_min_weight():
    config = TemporalProximityConfig(window_ms=1000, tau_ms=1, min_weight=0.9)
    enricher = TemporalProximityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000, 0.2)],
        "entity_b": [_context("evt2", 1000, 0.3)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_updates_existing_edge():
    config = TemporalProximityConfig(window_ms=1000, tau_ms=500, min_weight=0.1)
    enricher = TemporalProximityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000, 0.2)],
        "entity_b": [_context("evt2", 1500, 0.3)],
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
    config = TemporalProximityConfig(window_ms=1000, tau_ms=500, min_weight=0.1)
    enricher = TemporalProximityEnricher(config=config)

    context_a = _context("evt1", 1000, 0.9)
    context_b = _context("evt2", 1500, 0.3)

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
    config = TemporalProximityConfig(window_ms=1000, tau_ms=500, min_weight=0.1)
    config.max_edges_per_entity = 1
    enricher = TemporalProximityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000, 0.2)],
        "entity_b": [_context("evt2", 1500, 0.3)],
        "entity_c": [_context("evt3", 1600, 0.4)],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
