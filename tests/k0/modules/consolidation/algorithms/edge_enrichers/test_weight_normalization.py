"""
Tests for EdgeWeightNormalizer (GAP-007 Epic 3.6).
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.edge_enrichers.weight_normalization import (
    EdgeWeightNormalizer,
)
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate
from k0.pipelines.p03.phases.r4_config import WeightNormalizationConfig


def _edge(edge_id: str, source: str, target: str, weight: float) -> KGEdge:
    return KGEdge(
        edge_id=edge_id,
        source_entity_id=source,
        target_entity_id=target,
        relationship_type="TEST_EDGE",
        weight=weight,
        confidence=0.5,
        source_algorithm="test",
    )


@pytest.mark.asyncio
async def test_sum_to_one_strategy():
    """Test that sum_to_one normalizes all edges from an entity to sum to 1.0."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 2.0),
            _edge("edge2", "entity_a", "entity_c", 3.0),
        ]
    }

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    assert len(updates) == 2
    # Total weight = 5.0, so edge1 = 2/5 = 0.4, edge2 = 3/5 = 0.6
    weights = {u.edge_id: u.new_weight for u in updates}
    assert "edge1" in weights and "edge2" in weights
    assert abs(weights["edge1"] - 0.4) < 0.001  # type: ignore
    assert abs(weights["edge2"] - 0.6) < 0.001  # type: ignore


@pytest.mark.asyncio
async def test_cap_strategy():
    """Test that cap strategy limits weights to max/min bounds."""
    config = WeightNormalizationConfig(strategy="cap", max_weight=1.0, min_weight=0.1)
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 2.5),  # Exceeds max
            _edge("edge2", "entity_a", "entity_c", 0.05),  # Below min
            _edge("edge3", "entity_a", "entity_d", 0.5),  # Within bounds
        ]
    }

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    assert len(updates) == 2  # Only edge1 and edge2 need capping
    weights = {u.edge_id: u.new_weight for u in updates}
    assert weights["edge1"] == 1.0
    assert weights["edge2"] == 0.1


@pytest.mark.asyncio
async def test_softmax_strategy():
    """Test that softmax normalizes weights to probability distribution."""
    config = WeightNormalizationConfig(strategy="softmax")
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 1.0),
            _edge("edge2", "entity_a", "entity_c", 2.0),
        ]
    }

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    assert len(updates) == 2
    weights = {u.edge_id: u.new_weight for u in updates}

    # Softmax: exp(1)/(exp(1) + exp(2)) and exp(2)/(exp(1) + exp(2))
    import math

    exp1 = math.exp(1.0)
    exp2 = math.exp(2.0)
    total = exp1 + exp2

    assert "edge1" in weights and "edge2" in weights
    assert abs(weights["edge1"] - (exp1 / total)) < 0.001  # type: ignore
    assert abs(weights["edge2"] - (exp2 / total)) < 0.001  # type: ignore


@pytest.mark.asyncio
async def test_single_edge_no_normalization():
    """Test that single edge is not normalized."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {"entity_a": [_edge("edge1", "entity_a", "entity_b", 5.0)]}

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    assert len(updates) == 0  # No normalization needed for single edge


@pytest.mark.asyncio
async def test_no_edges_no_normalization():
    """Test that empty edge set produces no updates."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges={},
    )

    assert len(updates) == 0


@pytest.mark.asyncio
async def test_includes_new_edges():
    """Test that new edges are included in normalization."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {"entity_a": [_edge("edge1", "entity_a", "entity_b", 1.0)]}

    new_edges = [_edge("edge2", "entity_a", "entity_c", 2.0)]

    updates = normalizer.normalize(
        new_edges=new_edges,
        updates=[],
        existing_edges=existing_edges,
    )

    # Total weight = 3.0, so edge1 = 1/3, edge2 = 2/3
    assert len(updates) == 2
    weights = {u.edge_id: u.new_weight for u in updates}
    assert "edge1" in weights and "edge2" in weights
    assert abs(weights["edge1"] - (1.0 / 3.0)) < 0.001  # type: ignore
    assert abs(weights["edge2"] - (2.0 / 3.0)) < 0.001  # type: ignore


@pytest.mark.asyncio
async def test_applies_pending_updates():
    """Test that pending updates are applied before normalization."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 1.0),
            _edge("edge2", "entity_a", "entity_c", 1.0),
        ]
    }

    pending_updates = [
        KGEdgeUpdate(
            edge_id="edge1",
            weight_delta=2.0,  # 1.0 + 2.0 = 3.0
            source_algorithm="test",
        )
    ]

    updates = normalizer.normalize(
        new_edges=[],
        updates=pending_updates,
        existing_edges=existing_edges,
    )

    # After delta: edge1 = 3.0, edge2 = 1.0, total = 4.0
    # Normalized: edge1 = 3/4 = 0.75, edge2 = 1/4 = 0.25
    weights = {u.edge_id: u.new_weight for u in updates}
    assert "edge1" in weights and "edge2" in weights
    assert abs(weights["edge1"] - 0.75) < 0.001  # type: ignore
    assert abs(weights["edge2"] - 0.25) < 0.001  # type: ignore


@pytest.mark.asyncio
async def test_disabled_config():
    """Test that disabled config produces no updates."""
    config = WeightNormalizationConfig(enabled=False)
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 2.0),
            _edge("edge2", "entity_a", "entity_c", 3.0),
        ]
    }

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    assert len(updates) == 0


@pytest.mark.asyncio
async def test_multiple_entities_independent():
    """Test that normalization is independent per entity."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 1.0),
            _edge("edge2", "entity_a", "entity_c", 1.0),
        ],
        "entity_x": [
            _edge("edge3", "entity_x", "entity_y", 3.0),
            _edge("edge4", "entity_x", "entity_z", 6.0),
        ],
    }

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    weights = {u.edge_id: u.new_weight for u in updates}

    # entity_a: total = 2.0, so each = 0.5
    assert "edge1" in weights and "edge2" in weights
    assert abs(weights["edge1"] - 0.5) < 0.001  # type: ignore
    assert abs(weights["edge2"] - 0.5) < 0.001  # type: ignore

    # entity_x: total = 9.0, so edge3 = 3/9 = 0.333, edge4 = 6/9 = 0.666
    assert "edge3" in weights and "edge4" in weights
    assert abs(weights["edge3"] - (3.0 / 9.0)) < 0.001  # type: ignore
    assert abs(weights["edge4"] - (6.0 / 9.0)) < 0.001  # type: ignore


@pytest.mark.asyncio
async def test_no_change_for_small_differences():
    """Test that sum_to_one skips updates when change is negligible."""
    config = WeightNormalizationConfig(strategy="sum_to_one")
    normalizer = EdgeWeightNormalizer(config=config)

    # Weights already sum to ~1.0
    existing_edges = {
        "entity_a": [
            _edge("edge1", "entity_a", "entity_b", 0.5),
            _edge("edge2", "entity_a", "entity_c", 0.5),
        ]
    }

    updates = normalizer.normalize(
        new_edges=[],
        updates=[],
        existing_edges=existing_edges,
    )

    # No updates because weights already sum to 1.0
    assert len(updates) == 0
