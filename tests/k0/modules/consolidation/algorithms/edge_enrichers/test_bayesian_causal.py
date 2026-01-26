"""
Tests for BayesianCausalEnricher (GAP-007 Epic 3.5).
"""

from __future__ import annotations

from typing import Mapping, cast

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.bayesian_causal import (
    BayesianCausalEnricher,
    ExistingEdgeInfo,
)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phases.r4_config import BayesianCausalConfig


def _context(event_id: str, observed_at: int, salience: float = 0.5) -> ObservationContext:
    return ObservationContext(
        observed_at=observed_at,
        source_event_id=event_id,
        salience_score=salience,
    )


@pytest.mark.asyncio
async def test_creates_causal_edge_from_precedence():
    """Test that clear temporal precedence creates a causal edge."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=3,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    entity_contexts = {
        "entity_a": [
            _context("evt1", 1000),
            _context("evt2", 2000),
            _context("evt3", 3000),
        ],
        "entity_b": [
            _context("evt4", 1500),
            _context("evt5", 2500),
            _context("evt6", 3500),
        ],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert updates == []
    assert new_edges[0].relationship_type == "CAUSES"
    assert new_edges[0].source_entity_id == "entity_a"
    assert new_edges[0].target_entity_id == "entity_b"


@pytest.mark.asyncio
async def test_respects_min_evidence_count():
    """Test that insufficient evidence prevents edge creation."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=5,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000)],
        "entity_b": [_context("evt2", 1500)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_respects_posterior_threshold():
    """Test that low posterior probability prevents edge creation."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=2,
        posterior_threshold=0.95,  # Very high threshold
    )
    enricher = BayesianCausalEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000), _context("evt2", 2000)],
        "entity_b": [_context("evt3", 1500), _context("evt4", 2500)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    # With nearly equal evidence, posterior won't reach 0.95
    assert new_edges == []


@pytest.mark.asyncio
async def test_updates_existing_causal_edge():
    """Test that existing causal edges are strengthened."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=3,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    entity_contexts = {
        "entity_a": [
            _context("evt1", 1000),
            _context("evt2", 2000),
            _context("evt3", 3000),
        ],
        "entity_b": [
            _context("evt4", 1500),
            _context("evt5", 2500),
            _context("evt6", 3500),
        ],
    }

    existing: Mapping[object, object] = cast(
        Mapping[object, object],
        {("entity_a", "entity_b"): ExistingEdgeInfo(edge_id="edge_causal_existing")},
    )

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges=existing)

    assert new_edges == []
    assert len(updates) == 1
    assert updates[0].edge_id == "edge_causal_existing"
    assert updates[0].source_algorithm == "bayesian_causal"


@pytest.mark.asyncio
async def test_attaches_context_and_evidence():
    """Test that edges include observation context and evidence."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=3,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    context_a1 = _context("evt1", 1000, 0.9)
    context_a2 = _context("evt2", 2000, 0.7)
    context_a3 = _context("evt3", 3000, 0.8)

    entity_contexts = {
        "entity_a": [context_a1, context_a2, context_a3],
        "entity_b": [
            _context("evt4", 1500),
            _context("evt5", 2500),
            _context("evt6", 3500),
        ],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert new_edges[0].observation_context in [context_a1, context_a2, context_a3]
    assert len(new_edges[0].evidence_event_ids) > 0
    assert "evt1" in new_edges[0].evidence_event_ids or "evt4" in new_edges[0].evidence_event_ids


@pytest.mark.asyncio
async def test_directed_edge_creation():
    """Test that edges are directed from cause to effect."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=2,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    # B always follows A
    entity_contexts = {
        "entity_a": [_context("evt1", 1000), _context("evt2", 2000)],
        "entity_b": [_context("evt3", 1100), _context("evt4", 2100)],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert new_edges[0].source_entity_id == "entity_a"
    assert new_edges[0].target_entity_id == "entity_b"

    # Reverse: A always follows B
    entity_contexts_reversed = {
        "entity_a": [_context("evt1", 1100), _context("evt2", 2100)],
        "entity_b": [_context("evt3", 1000), _context("evt4", 2000)],
    }

    new_edges_rev, _ = await enricher.enrich(entity_contexts_reversed, existing_edges={})

    assert len(new_edges_rev) == 1
    assert new_edges_rev[0].source_entity_id == "entity_b"
    assert new_edges_rev[0].target_entity_id == "entity_a"


@pytest.mark.asyncio
async def test_skips_equal_evidence():
    """Test that equal precedence counts are skipped."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=2,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    # Equal precedence
    entity_contexts = {
        "entity_a": [_context("evt1", 1000), _context("evt2", 3000)],
        "entity_b": [_context("evt3", 2000), _context("evt4", 4000)],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    # With 2 observations each and alternating precedence, we get equal counts
    assert new_edges == []


@pytest.mark.asyncio
async def test_includes_properties():
    """Test that edge properties contain Bayesian metadata."""
    config = BayesianCausalConfig(
        prior_strength=0.1,
        min_evidence_count=2,
        posterior_threshold=0.6,
    )
    enricher = BayesianCausalEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000), _context("evt2", 2000)],
        "entity_b": [_context("evt3", 1500), _context("evt4", 2500)],
    }

    new_edges, _ = await enricher.enrich(entity_contexts, existing_edges={})

    assert len(new_edges) == 1
    assert new_edges[0].properties_json is not None

    import json

    props = json.loads(new_edges[0].properties_json)
    assert "precedence_count" in props
    assert "total_pairs" in props
    assert "posterior" in props
    assert "prior" in props
    assert "likelihood_ratio" in props


@pytest.mark.asyncio
async def test_disabled_config():
    """Test that disabled config produces no edges."""
    config = BayesianCausalConfig(enabled=False)
    enricher = BayesianCausalEnricher(config=config)

    entity_contexts = {
        "entity_a": [_context("evt1", 1000), _context("evt2", 2000)],
        "entity_b": [_context("evt3", 1500), _context("evt4", 2500)],
    }

    new_edges, updates = await enricher.enrich(entity_contexts, existing_edges={})

    assert new_edges == []
    assert updates == []
