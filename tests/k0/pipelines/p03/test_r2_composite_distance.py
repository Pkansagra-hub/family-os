"""
Tests for CompositeDistance — semantic + temporal distance metric.

Issue 4.2.1: Composite distance function (semantic + temporal)

Tests:
    1. test_dbscan_params_defaults: Default values match spec
    2. test_dbscan_params_validation: Invalid ranges rejected
    3. test_cosine_distance_identical: Identical embeddings → 0.0
    4. test_cosine_distance_orthogonal: Orthogonal embeddings → 1.0
    5. test_temporal_hard_limit: Events >4h apart → infinity
    6. test_composite_distance_formula: Weighted combination correct
    7. test_distance_matrix_symmetric: Matrix is symmetric
    8. test_distance_matrix_diagonal_zero: Diagonal is zero
    9. test_would_cluster_under_eps: Events under eps should cluster
    10. test_compute_from_arrays: Array-based computation matches
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.composite_distance import (
    MS_PER_HOUR,
    CompositeDistance,
    DBSCANParams,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]]


def make_embedding(seed: int, dim: int = 768) -> List[float]:
    """Create deterministic embedding from seed."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / norm).tolist()  # L2-normalized


def make_orthogonal_embeddings(dim: int = 768) -> tuple[List[float], List[float]]:
    """Create two orthogonal embeddings."""
    # First vector: [1, 0, 0, ...]
    vec1 = [0.0] * dim
    vec1[0] = 1.0
    # Second vector: [0, 1, 0, ...]
    vec2 = [0.0] * dim
    vec2[1] = 1.0
    return vec1, vec2


# =============================================================================
# DBSCANParams Tests
# =============================================================================


class TestDBSCANParams:
    """Test DBSCANParams configuration dataclass."""

    def test_dbscan_params_defaults(self) -> None:
        """Default values match Dossier spec."""
        params = DBSCANParams()

        assert params.eps == 0.15  # Optimized for UltraBERT L2-normalized embeddings
        assert params.min_samples == 2
        assert params.temporal_weight == 0.3
        assert params.max_temporal_gap_hours == 4.0

    def test_dbscan_params_derived_properties(self) -> None:
        """Derived properties computed correctly."""
        params = DBSCANParams(temporal_weight=0.3, max_temporal_gap_hours=4.0)

        assert params.semantic_weight == 0.7
        assert params.max_temporal_gap_ms == 4 * MS_PER_HOUR

    def test_dbscan_params_validation_eps(self) -> None:
        """Invalid eps range rejected."""
        # eps too low
        with pytest.raises(ValueError, match="eps must be in"):
            DBSCANParams(eps=0.0).validate()

        # eps too high
        with pytest.raises(ValueError, match="eps must be in"):
            DBSCANParams(eps=2.5).validate()

    def test_dbscan_params_validation_min_samples(self) -> None:
        """Invalid min_samples rejected."""
        with pytest.raises(ValueError, match="min_samples must be >= 1"):
            DBSCANParams(min_samples=0).validate()

    def test_dbscan_params_validation_temporal_weight(self) -> None:
        """Invalid temporal_weight rejected."""
        with pytest.raises(ValueError, match="temporal_weight must be in"):
            DBSCANParams(temporal_weight=-0.1).validate()

        with pytest.raises(ValueError, match="temporal_weight must be in"):
            DBSCANParams(temporal_weight=1.5).validate()

    def test_dbscan_params_validation_max_temporal_gap(self) -> None:
        """Invalid max_temporal_gap_hours rejected."""
        with pytest.raises(ValueError, match="max_temporal_gap_hours must be > 0"):
            DBSCANParams(max_temporal_gap_hours=0).validate()

    def test_dbscan_params_serialization(self) -> None:
        """Serialization round-trip preserves values."""
        params = DBSCANParams(eps=0.3, min_samples=3, temporal_weight=0.4)

        data = params.to_dict()
        restored = DBSCANParams.from_dict(data)

        assert restored.eps == params.eps
        assert restored.min_samples == params.min_samples
        assert restored.temporal_weight == params.temporal_weight


# =============================================================================
# CompositeDistance Tests
# =============================================================================


class TestCompositeDistance:
    """Test CompositeDistance class."""

    def test_cosine_distance_identical(self) -> None:
        """Identical embeddings produce distance ~0.0."""
        emb = make_embedding(42)
        event_a = MockEvent("e1", 1000, emb)
        event_b = MockEvent("e2", 1000, emb)

        dist = CompositeDistance()
        result = dist.compute(event_a, event_b)

        # Should be 0 (same embedding, same time)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_cosine_distance_orthogonal(self) -> None:
        """Orthogonal embeddings produce cosine distance = 1.0."""
        vec1, vec2 = make_orthogonal_embeddings()
        event_a = MockEvent("e1", 1000, vec1)
        event_b = MockEvent("e2", 1000, vec2)

        # Use pure semantic weight to isolate cosine distance
        params = DBSCANParams(temporal_weight=0.0)
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        # Should be 1.0 (orthogonal vectors, same time, no temporal weight)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_temporal_hard_limit(self) -> None:
        """Events beyond max_temporal_gap return infinity."""
        emb = make_embedding(42)
        base_ts = 1000000000000  # ~2001

        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 5 * MS_PER_HOUR, emb)  # 5 hours later

        params = DBSCANParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        assert result == float("inf")

    def test_composite_distance_formula(self) -> None:
        """Weighted combination formula verified."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        # Events 2 hours apart (half of max gap)
        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 2 * MS_PER_HOUR, emb)  # 2 hours

        params = DBSCANParams(temporal_weight=0.3, max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        # Same embedding → cosine_distance = 0
        # Time diff = 2h / 4h = 0.5 normalized
        # Distance = 0.7 * 0 + 0.3 * 0.5 = 0.15
        assert result == pytest.approx(0.15, abs=1e-6)

    def test_composite_distance_mixed(self) -> None:
        """Mixed semantic and temporal distance computed correctly."""
        vec1, vec2 = make_orthogonal_embeddings()
        base_ts = 1000000000000

        # Orthogonal embeddings, 2 hours apart
        event_a = MockEvent("e1", base_ts, vec1)
        event_b = MockEvent("e2", base_ts + 2 * MS_PER_HOUR, vec2)

        params = DBSCANParams(temporal_weight=0.3, max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        # cosine_distance = 1.0 (orthogonal)
        # normalized_time = 0.5 (2h / 4h)
        # Distance = 0.7 * 1.0 + 0.3 * 0.5 = 0.85
        assert result == pytest.approx(0.85, abs=1e-6)

    def test_distance_matrix_symmetric(self) -> None:
        """Distance matrix is symmetric."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
            MockEvent("e3", 3000, make_embedding(3)),
        ]

        dist = CompositeDistance()
        matrix = dist.build_distance_matrix(events)

        # Check symmetry
        assert matrix.shape == (3, 3)
        np.testing.assert_array_almost_equal(matrix, matrix.T)

    def test_distance_matrix_diagonal_zero(self) -> None:
        """Distance matrix diagonal is zero."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
        ]

        dist = CompositeDistance()
        matrix = dist.build_distance_matrix(events)

        # Diagonal should be zero
        assert matrix[0, 0] == 0.0
        assert matrix[1, 1] == 0.0

    def test_distance_matrix_empty(self) -> None:
        """Empty event list produces empty matrix."""
        dist = CompositeDistance()
        matrix = dist.build_distance_matrix([])

        assert matrix.shape == (0, 0)

    def test_would_cluster_under_eps(self) -> None:
        """Events with distance under eps should cluster."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        # Events 1 hour apart, same embedding
        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + MS_PER_HOUR, emb)  # 1 hour

        params = DBSCANParams(eps=0.25, temporal_weight=0.3, max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)

        # Distance = 0.7 * 0 + 0.3 * 0.25 = 0.075 < 0.25
        assert dist.would_cluster(event_a, event_b) is True

    def test_would_cluster_over_eps(self) -> None:
        """Events with distance over eps should not cluster."""
        vec1, vec2 = make_orthogonal_embeddings()
        base_ts = 1000000000000

        event_a = MockEvent("e1", base_ts, vec1)
        event_b = MockEvent("e2", base_ts, vec2)  # Same time, orthogonal

        params = DBSCANParams(eps=0.25, temporal_weight=0.0)
        dist = CompositeDistance(params)

        # Distance = 1.0 * 1.0 = 1.0 > 0.25
        assert dist.would_cluster(event_a, event_b) is False

    def test_compute_from_arrays(self) -> None:
        """Array-based computation matches event-based computation."""
        emb_a = make_embedding(1)
        emb_b = make_embedding(2)
        ts_a = 1000000000000
        ts_b = ts_a + MS_PER_HOUR

        event_a = MockEvent("e1", ts_a, emb_a)
        event_b = MockEvent("e2", ts_b, emb_b)

        dist = CompositeDistance()

        result_events = dist.compute(event_a, event_b)
        result_arrays = dist.compute_from_arrays(
            np.asarray(emb_a, dtype=np.float32),
            np.asarray(emb_b, dtype=np.float32),
            ts_a,
            ts_b,
        )

        assert result_events == pytest.approx(result_arrays, abs=1e-6)

    def test_missing_embedding_raises(self) -> None:
        """Missing embedding raises ValueError."""
        event_a = MockEvent("e1", 1000, make_embedding(1))
        event_b = MockEvent("e2", 2000, None)

        dist = CompositeDistance()

        with pytest.raises(ValueError, match="has no embedding_768"):
            dist.compute(event_a, event_b)

    def test_get_semantic_distance(self) -> None:
        """Get semantic distance component only."""
        vec1, vec2 = make_orthogonal_embeddings()
        event_a = MockEvent("e1", 1000, vec1)
        event_b = MockEvent("e2", 2000, vec2)

        dist = CompositeDistance()
        result = dist.get_semantic_distance(event_a, event_b)

        assert result == pytest.approx(1.0, abs=1e-6)

    def test_get_temporal_distance(self) -> None:
        """Get temporal distance component only."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 2 * MS_PER_HOUR, emb)

        params = DBSCANParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.get_temporal_distance(event_a, event_b)

        assert result == pytest.approx(0.5, abs=1e-6)  # 2h / 4h

    def test_get_temporal_distance_beyond_limit(self) -> None:
        """Temporal distance returns infinity beyond limit."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 5 * MS_PER_HOUR, emb)

        params = DBSCANParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.get_temporal_distance(event_a, event_b)

        assert result == float("inf")
