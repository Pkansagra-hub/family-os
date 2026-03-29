"""
Tests for TransitiveClosureEnricher (GAP-007 Epic 3.4).
"""

from __future__ import annotations

import json
from typing import Mapping, cast

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.transitive_closure import (
    TransitiveClosureEnricher,
)
from k0.pipelines.p03.phases.r4_config import TransitiveClosureConfig


@pytest.mark.asyncio
async def test_infers_two_hop_edge():
    config = TransitiveClosureConfig(attenuation_factor=0.5, min_confidence=0.2)
    enricher = TransitiveClosureEnricher(config=config)

    existing_edges: Mapping[object, object] = cast(
        Mapping[object, object],
        {
            "A:B": {
                "edge_id": "edge_a_b",
                "source_entity_id": "A",
                "target_entity_id": "B",
                "confidence_score": 0.8,
            },
            "B:C": {
                "edge_id": "edge_b_c",
                "source_entity_id": "B",
                "target_entity_id": "C",
                "confidence_score": 0.7,
            },
        },
    )

    new_edges, updates = await enricher.enrich(
        batch_entities=["A", "B", "C"],
        existing_edges=existing_edges,
    )

    assert updates == []
    assert len(new_edges) == 1
    assert new_edges[0].source_algorithm == "transitive_closure"
    chain = json.loads(new_edges[0].inference_chain_json or "{}")
    assert chain.get("hop_count") == 2
    assert chain.get("paths")
    assert chain.get("paths")[0] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_skips_when_direct_edge_exists():
    config = TransitiveClosureConfig(attenuation_factor=0.5, min_confidence=0.2)
    enricher = TransitiveClosureEnricher(config=config)

    existing_edges: Mapping[object, object] = cast(
        Mapping[object, object],
        {
            "A:B": {
                "edge_id": "edge_a_b",
                "source_entity_id": "A",
                "target_entity_id": "B",
                "confidence_score": 0.8,
            },
            "B:C": {
                "edge_id": "edge_b_c",
                "source_entity_id": "B",
                "target_entity_id": "C",
                "confidence_score": 0.7,
            },
            "A:C": {
                "edge_id": "edge_a_c",
                "source_entity_id": "A",
                "target_entity_id": "C",
                "confidence_score": 0.9,
            },
        },
    )

    new_edges, updates = await enricher.enrich(
        batch_entities=["A", "B", "C"],
        existing_edges=existing_edges,
    )

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_respects_min_confidence():
    config = TransitiveClosureConfig(attenuation_factor=0.1, min_confidence=0.5)
    enricher = TransitiveClosureEnricher(config=config)

    existing_edges: Mapping[object, object] = cast(
        Mapping[object, object],
        {
            "A:B": {
                "edge_id": "edge_a_b",
                "source_entity_id": "A",
                "target_entity_id": "B",
                "confidence_score": 0.6,
            },
            "B:C": {
                "edge_id": "edge_b_c",
                "source_entity_id": "B",
                "target_entity_id": "C",
                "confidence_score": 0.6,
            },
        },
    )

    new_edges, updates = await enricher.enrich(
        batch_entities=["A", "B", "C"],
        existing_edges=existing_edges,
    )

    assert new_edges == []
    assert updates == []


@pytest.mark.asyncio
async def test_canonical_ordering():
    config = TransitiveClosureConfig(attenuation_factor=0.5, min_confidence=0.2)
    enricher = TransitiveClosureEnricher(config=config)

    existing_edges: Mapping[object, object] = cast(
        Mapping[object, object],
        {
            "B:A": {
                "edge_id": "edge_b_a",
                "source_entity_id": "B",
                "target_entity_id": "A",
                "confidence_score": 0.8,
            },
            "B:C": {
                "edge_id": "edge_b_c",
                "source_entity_id": "B",
                "target_entity_id": "C",
                "confidence_score": 0.7,
            },
        },
    )

    new_edges, _ = await enricher.enrich(
        batch_entities=["A", "B", "C"],
        existing_edges=existing_edges,
    )

    assert len(new_edges) == 1
    assert new_edges[0].edge_id == "edge_A_C"
