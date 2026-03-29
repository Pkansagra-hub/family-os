"""
Tests for IntentSimilarityEnricher (GAP-007 Epic 3.3).
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.intent_similarity import (
    IntentSimilarityEnricher,
)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phases.r4_config import IntentSimilarityConfig


def _context(event_id: str, **kwargs) -> ObservationContext:
    return ObservationContext(observed_at=1234, source_event_id=event_id, **kwargs)


@pytest.mark.asyncio
async def test_creates_edge_for_complementary_intents():
    config = IntentSimilarityConfig(similarity_threshold=0.4)
    enricher = IntentSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", intent_ultrabert="seek_advice", intent_confidence=0.8)],
        "entity_b": [_context("evt2", intent_ultrabert="express_feeling", intent_confidence=0.9)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert updates == []
    assert new_edges[0].relationship_type == config.relation_type


@pytest.mark.asyncio
async def test_respects_threshold():
    config = IntentSimilarityConfig(similarity_threshold=0.9)
    enricher = IntentSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", intent_ultrabert="seek_advice", intent_confidence=0.8)],
        "entity_b": [
            _context("evt2", intent_ultrabert="other", intent_confidence=0.9)
        ],  # Not complementary
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 0
    assert updates == []


@pytest.mark.asyncio
async def test_handles_empty_intents():
    config = IntentSimilarityConfig(similarity_threshold=0.5)
    enricher = IntentSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", intent_ultrabert="seek_advice", intent_confidence=0.8)],
        "entity_b": [_context("evt2", intent_ultrabert="", intent_confidence=0.0)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 0
    assert updates == []


@pytest.mark.asyncio
async def test_multiple_entities():
    config = IntentSimilarityConfig(similarity_threshold=0.3)
    enricher = IntentSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", intent_ultrabert="set_reminder", intent_confidence=0.8)],
        "entity_b": [_context("evt2", intent_ultrabert="log_memory", intent_confidence=0.9)],
        "entity_c": [
            _context("evt3", intent_ultrabert="other", intent_confidence=0.7)
        ],  # Not complementary with others
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    # Should create edge between a and b (complementary), but not with c
    assert len(new_edges) == 1
    assert new_edges[0].source_entity_id in ["entity_a", "entity_b"]
    assert new_edges[0].target_entity_id in ["entity_a", "entity_b"]
    assert updates == []


@pytest.mark.asyncio
async def test_no_self_edges():
    config = IntentSimilarityConfig(similarity_threshold=0.1)
    enricher = IntentSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [
            _context("evt1", intent_ultrabert="seek_advice", intent_confidence=0.8),
            _context("evt2", intent_ultrabert="express_feeling", intent_confidence=0.9),
        ],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    # Should not create self-edges even with complementary intents in same entity
    assert len(new_edges) == 0
    assert updates == []
