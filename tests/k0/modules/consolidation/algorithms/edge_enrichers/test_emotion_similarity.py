"""
Tests for EmotionSimilarityEnricher (GAP-007 Epic 3.3).
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.emotion_similarity import (
    EmotionSimilarityEnricher,
)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phases.r4_config import EmotionSimilarityConfig


def _context(event_id: str, **kwargs) -> ObservationContext:
    return ObservationContext(observed_at=1234, source_event_id=event_id, **kwargs)


@pytest.mark.asyncio
async def test_creates_edge_for_similar_emotions():
    config = EmotionSimilarityConfig(similarity_threshold=0.4, arousal_weight=0.3)
    enricher = EmotionSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", dominant_emotions_json='["joy","excitement"]')],
        "entity_b": [_context("evt2", dominant_emotions_json='["joy","happiness"]')],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert updates == []
    assert new_edges[0].relationship_type == config.relation_type


@pytest.mark.asyncio
async def test_respects_threshold():
    config = EmotionSimilarityConfig(similarity_threshold=0.9)
    enricher = EmotionSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", dominant_emotions_json='["joy","excitement"]')],
        "entity_b": [_context("evt2", dominant_emotions_json='["sadness","anger"]')],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 0
    assert updates == []


@pytest.mark.asyncio
async def test_handles_empty_emotions():
    config = EmotionSimilarityConfig(similarity_threshold=0.5)
    enricher = EmotionSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", dominant_emotions_json='["joy"]')],
        "entity_b": [_context("evt2", dominant_emotions_json="[]")],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 0
    assert updates == []


@pytest.mark.asyncio
async def test_multiple_entities():
    config = EmotionSimilarityConfig(similarity_threshold=0.3)
    enricher = EmotionSimilarityEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", dominant_emotions_json='["joy","excitement","pride"]')],
        "entity_b": [_context("evt2", dominant_emotions_json='["joy","happiness","contentment"]')],
        "entity_c": [_context("evt3", dominant_emotions_json='["sadness","disappointment"]')],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    # Should create edge between a and b, but not a and c or b and c
    assert len(new_edges) == 1
    assert new_edges[0].source_entity_id in ["entity_a", "entity_b"]
    assert new_edges[0].target_entity_id in ["entity_a", "entity_b"]
    assert updates == []
