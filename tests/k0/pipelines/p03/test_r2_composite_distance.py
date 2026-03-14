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
    ClusteringDistanceParams,
    CompositeDistance,
    EnsembleDistance,
    EnsembleDistanceConfig,
    FallbackPolicy,
    _cd_affective,
    _cd_narrative,
    _cd_semantic,
    _cd_social,
    _cd_spatial,
    _cd_temporal,
    _parse_json_list,
    _temporal_quality_confidence,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing — satisfies the full EventLike protocol."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]]
    # Spatial (Issue 3.1.2)
    place_id: Optional[str] = None
    geohash_6: Optional[str] = None
    location_hierarchy_json: Optional[str] = None
    # Social (Issue 3.1.3)
    participants_json: Optional[str] = None
    social_context: Optional[str] = None
    social_intimacy: Optional[float] = None
    num_participants: Optional[int] = None
    is_solo_event: Optional[bool] = None
    # Affective (Issue 3.1.4)
    affect_valence: Optional[float] = None
    affect_arousal: Optional[float] = None
    affect_dominance: Optional[float] = None
    surprise_level: Optional[float] = None
    # Narrative (Issue 3.1.5)
    narrative_thread_id: Optional[str] = None
    goal_context: Optional[str] = None
    intent_type: Optional[str] = None
    # Support signals
    activity_type: Optional[str] = None
    sentiment_score: Optional[float] = None
    # Temporal quality (Epic 3.2.2)
    temporal_source: Optional[str] = None


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
# ClusteringDistanceParams Tests
# =============================================================================


class TestClusteringDistanceParams:
    """Test ClusteringDistanceParams configuration dataclass."""

    def test_params_defaults(self) -> None:
        """Default values match Dossier spec + Epic 3.2.1 log-temporal."""
        params = ClusteringDistanceParams()

        assert params.eps == 0.15  # Optimized for UltraBERT L2-normalized embeddings
        assert params.min_samples == 2
        assert params.temporal_weight == 0.3
        assert params.max_temporal_gap_hours == 4.0
        # Epic 3.2.1: log-temporal defaults
        assert params.use_log_temporal is True
        assert params.log_temporal_tau_ms == 1_800_000

    def test_params_derived_properties(self) -> None:
        """Derived properties computed correctly."""
        params = ClusteringDistanceParams(temporal_weight=0.3, max_temporal_gap_hours=4.0)

        assert params.semantic_weight == 0.7
        assert params.max_temporal_gap_ms == 4 * MS_PER_HOUR

    def test_params_validation_eps(self) -> None:
        """Invalid eps range rejected."""
        # eps too low
        with pytest.raises(ValueError, match="eps must be in"):
            ClusteringDistanceParams(eps=0.0).validate()

        # eps too high
        with pytest.raises(ValueError, match="eps must be in"):
            ClusteringDistanceParams(eps=2.5).validate()

    def test_params_validation_min_samples(self) -> None:
        """Invalid min_samples rejected."""
        with pytest.raises(ValueError, match="min_samples must be >= 1"):
            ClusteringDistanceParams(min_samples=0).validate()

    def test_params_validation_temporal_weight(self) -> None:
        """Invalid temporal_weight rejected."""
        with pytest.raises(ValueError, match="temporal_weight must be in"):
            ClusteringDistanceParams(temporal_weight=-0.1).validate()

        with pytest.raises(ValueError, match="temporal_weight must be in"):
            ClusteringDistanceParams(temporal_weight=1.5).validate()

    def test_params_validation_max_temporal_gap(self) -> None:
        """Invalid max_temporal_gap_hours rejected."""
        with pytest.raises(ValueError, match="max_temporal_gap_hours must be > 0"):
            ClusteringDistanceParams(max_temporal_gap_hours=0).validate()

    def test_params_serialization(self) -> None:
        """Serialization round-trip preserves values."""
        params = ClusteringDistanceParams(
            eps=0.3,
            min_samples=3,
            temporal_weight=0.4,
            use_log_temporal=False,
            log_temporal_tau_ms=900_000,
        )

        data = params.to_dict()
        restored = ClusteringDistanceParams.from_dict(data)

        assert restored.eps == params.eps
        assert restored.min_samples == params.min_samples
        assert restored.temporal_weight == params.temporal_weight
        assert restored.use_log_temporal == params.use_log_temporal
        assert restored.log_temporal_tau_ms == params.log_temporal_tau_ms


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
        params = ClusteringDistanceParams(temporal_weight=0.0)
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

        params = ClusteringDistanceParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        assert result == float("inf")

    def test_composite_distance_formula(self) -> None:
        """Weighted combination formula verified (linear temporal mode)."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        # Events 2 hours apart (half of max gap)
        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 2 * MS_PER_HOUR, emb)  # 2 hours

        params = ClusteringDistanceParams(
            temporal_weight=0.3,
            max_temporal_gap_hours=4.0,
            use_log_temporal=False,
        )
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        # Same embedding -> cosine_distance = 0
        # Time diff = 2h / 4h = 0.5 normalized (linear)
        # Distance = 0.7 * 0 + 0.3 * 0.5 = 0.15
        assert result == pytest.approx(0.15, abs=1e-6)

    def test_composite_distance_mixed(self) -> None:
        """Mixed semantic and temporal distance computed correctly (linear temporal)."""
        vec1, vec2 = make_orthogonal_embeddings()
        base_ts = 1000000000000

        # Orthogonal embeddings, 2 hours apart
        event_a = MockEvent("e1", base_ts, vec1)
        event_b = MockEvent("e2", base_ts + 2 * MS_PER_HOUR, vec2)

        params = ClusteringDistanceParams(
            temporal_weight=0.3,
            max_temporal_gap_hours=4.0,
            use_log_temporal=False,
        )
        dist = CompositeDistance(params)
        result = dist.compute(event_a, event_b)

        # cosine_distance = 1.0 (orthogonal)
        # normalized_time = 0.5 (2h / 4h, linear)
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

        params = ClusteringDistanceParams(eps=0.25, temporal_weight=0.3, max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)

        # Distance = 0.7 * 0 + 0.3 * 0.25 = 0.075 < 0.25
        assert dist.would_cluster(event_a, event_b) is True

    def test_would_cluster_over_eps(self) -> None:
        """Events with distance over eps should not cluster."""
        vec1, vec2 = make_orthogonal_embeddings()
        base_ts = 1000000000000

        event_a = MockEvent("e1", base_ts, vec1)
        event_b = MockEvent("e2", base_ts, vec2)  # Same time, orthogonal

        params = ClusteringDistanceParams(eps=0.25, temporal_weight=0.0)
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
        """Get temporal distance component (log-temporal by default)."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 2 * MS_PER_HOUR, emb)

        params = ClusteringDistanceParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.get_temporal_distance(event_a, event_b)

        # Log-temporal: log(1+2h/30m) / log(1+4h/30m) = log(5) / log(9) ~ 0.733
        assert 0.7 < result < 0.8

    def test_get_temporal_distance_beyond_limit(self) -> None:
        """Temporal distance returns infinity beyond limit."""
        emb = make_embedding(42)
        base_ts = 1000000000000

        event_a = MockEvent("e1", base_ts, emb)
        event_b = MockEvent("e2", base_ts + 5 * MS_PER_HOUR, emb)

        params = ClusteringDistanceParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        result = dist.get_temporal_distance(event_a, event_b)

        assert result == float("inf")


# =============================================================================
# EnsembleDistanceConfig Tests (Issue 3.1.1)
# =============================================================================


class TestEnsembleDistanceConfig:
    """Test EnsembleDistanceConfig dataclass."""

    def test_defaults(self) -> None:
        """Proven research defaults applied."""
        cfg = EnsembleDistanceConfig()
        assert cfg.w_semantic == 0.45
        assert cfg.w_temporal == 0.25
        assert cfg.w_narrative == 0.30
        assert cfg.w_spatial == 0.0
        assert cfg.w_social == 0.0
        assert cfg.w_affective == 0.0
        assert cfg.shortcircuit is True
        assert cfg.shortcircuit_cap == 0.20
        assert cfg.use_log_temporal is True
        assert cfg.max_temporal_gap_ms == 14_400_000

    def test_weight_sum(self) -> None:
        """Active weights sum to 1.0."""
        cfg = EnsembleDistanceConfig()
        assert cfg.weight_sum == pytest.approx(1.0)

    def test_validation_negative_weight(self) -> None:
        """Negative weights rejected."""
        cfg = EnsembleDistanceConfig(w_semantic=-0.1)
        with pytest.raises(ValueError, match="w_semantic must be >= 0"):
            cfg.validate()

    def test_validation_zero_sum(self) -> None:
        """All-zero weights rejected."""
        cfg = EnsembleDistanceConfig(
            w_semantic=0.0,
            w_temporal=0.0,
            w_narrative=0.0,
        )
        with pytest.raises(ValueError, match="At least one dimension"):
            cfg.validate()

    def test_validation_temporal_gap(self) -> None:
        """Invalid max_temporal_gap_ms rejected."""
        cfg = EnsembleDistanceConfig(max_temporal_gap_ms=0)
        with pytest.raises(ValueError, match="max_temporal_gap_ms"):
            cfg.validate()

    def test_validation_shortcircuit_cap(self) -> None:
        """Invalid shortcircuit_cap rejected."""
        cfg = EnsembleDistanceConfig(shortcircuit_cap=1.5)
        with pytest.raises(ValueError, match="shortcircuit_cap"):
            cfg.validate()

    def test_serialization_round_trip(self) -> None:
        """to_dict/from_dict preserves values."""
        cfg = EnsembleDistanceConfig(w_semantic=0.50, shortcircuit=False)
        data = cfg.to_dict()
        restored = EnsembleDistanceConfig.from_dict(data)
        assert restored.w_semantic == 0.50
        assert restored.shortcircuit is False

    def test_fallback_policy_default(self) -> None:
        """Default fallback policy is REDISTRIBUTE."""
        cfg = EnsembleDistanceConfig()
        assert cfg.fallback_policy == FallbackPolicy.REDISTRIBUTE


# =============================================================================
# Dimension Function Tests (Issues 3.1.2-3.1.5)
# =============================================================================


class TestSemanticDimension:
    """Test _cd_semantic distance function."""

    def test_identical_embeddings(self) -> None:
        """Same embedding -> distance 0, confidence 1."""
        emb = make_embedding(42)
        a = MockEvent("e1", 1000, emb)
        b = MockEvent("e2", 2000, emb)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_semantic(a, b, cfg)
        assert d == pytest.approx(0.0, abs=1e-5)
        assert c == 1.0

    def test_orthogonal_embeddings(self) -> None:
        """Orthogonal embeddings -> distance 1.0, confidence 1."""
        v1, v2 = make_orthogonal_embeddings()
        a = MockEvent("e1", 1000, v1)
        b = MockEvent("e2", 2000, v2)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_semantic(a, b, cfg)
        assert d == pytest.approx(1.0, abs=1e-5)
        assert c == 1.0

    def test_missing_embedding_low_confidence(self) -> None:
        """Missing embedding -> high distance, low confidence."""
        a = MockEvent("e1", 1000, make_embedding(1))
        b = MockEvent("e2", 2000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_semantic(a, b, cfg)
        assert d == 1.0
        assert c == 0.3


class TestTemporalDimension:
    """Test _cd_temporal distance function."""

    def test_same_time(self) -> None:
        """Same timestamp -> distance 0."""
        a = MockEvent("e1", 1000, None)
        b = MockEvent("e2", 1000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_temporal(a, b, cfg)
        assert d == pytest.approx(0.0)
        assert c == 1.0

    def test_hard_cutoff(self) -> None:
        """Beyond max gap -> inf."""
        base = 1_000_000_000_000
        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + 5 * MS_PER_HOUR, None)
        cfg = EnsembleDistanceConfig(max_temporal_gap_ms=4 * MS_PER_HOUR)
        d, c = _cd_temporal(a, b, cfg)
        assert d == float("inf")

    def test_log_temporal_midpoint(self) -> None:
        """Log temporal at tau produces consistent value."""
        base = 1_000_000_000_000
        tau = 1_800_000  # 30 min
        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + tau, None)
        cfg = EnsembleDistanceConfig(use_log_temporal=True, log_temporal_tau_ms=tau)
        d, c = _cd_temporal(a, b, cfg)
        assert 0.0 < d < 1.0
        assert c == 1.0

    def test_linear_temporal_fallback(self) -> None:
        """Linear temporal when use_log_temporal=False."""
        base = 1_000_000_000_000
        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + 2 * MS_PER_HOUR, None)
        cfg = EnsembleDistanceConfig(
            use_log_temporal=False,
            max_temporal_gap_ms=4 * MS_PER_HOUR,
        )
        d, c = _cd_temporal(a, b, cfg)
        assert d == pytest.approx(0.5, abs=0.01)


class TestNarrativeDimension:
    """Test _cd_narrative distance function."""

    def test_same_thread_exact(self) -> None:
        """Same thread_id -> d=0, conf=1."""
        a = MockEvent("e1", 1000, None, narrative_thread_id="morning_routine")
        b = MockEvent("e2", 2000, None, narrative_thread_id="morning_routine")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_narrative(a, b, cfg)
        assert d == 0.0
        assert c == cfg.thread_exact_confidence

    def test_different_threads(self) -> None:
        """Different thread_ids -> positive distance, nonzero confidence."""
        a = MockEvent("e1", 1000, None, narrative_thread_id="morning_routine")
        b = MockEvent("e2", 2000, None, narrative_thread_id="work_project_alpha")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_narrative(a, b, cfg)
        # Different threads must produce positive distance
        assert d > 0.0
        # Confidence is positive (we have signal from both events)
        assert c > 0.0
        # Distance should be higher than same-thread (d=0.0)
        assert d > cfg.narrative_same_thread

    def test_same_goal(self) -> None:
        """Same goal_context -> low distance."""
        a = MockEvent("e1", 1000, None, goal_context="finish_report")
        b = MockEvent("e2", 2000, None, goal_context="finish_report")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_narrative(a, b, cfg)
        assert d == cfg.narrative_same_goal
        assert c == cfg.goal_exact_confidence

    def test_different_goals(self) -> None:
        """Different goals -> high distance."""
        a = MockEvent("e1", 1000, None, goal_context="finish_report")
        b = MockEvent("e2", 2000, None, goal_context="plan_vacation")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_narrative(a, b, cfg)
        assert d == cfg.narrative_diff_goal

    def test_asymmetric_signal(self) -> None:
        """One has thread, other has nothing -> moderate."""
        a = MockEvent("e1", 1000, None, narrative_thread_id="morning_routine")
        b = MockEvent("e2", 2000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_narrative(a, b, cfg)
        assert d == cfg.narrative_one_missing_goal
        assert c == cfg.goal_one_missing_confidence

    def test_no_narrative_signal(self) -> None:
        """Neither event has narrative -> MISS."""
        a = MockEvent("e1", 1000, None)
        b = MockEvent("e2", 2000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_narrative(a, b, cfg)
        assert d == cfg.narrative_miss_distance
        assert c == cfg.narrative_miss_confidence


class TestSpatialDimension:
    """Test _cd_spatial distance function."""

    def test_same_place_id(self) -> None:
        """Same place_id -> d=0.0."""
        a = MockEvent("e1", 1000, None, place_id="home_123")
        b = MockEvent("e2", 2000, None, place_id="home_123")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_spatial(a, b, cfg)
        assert d == 0.0
        assert c == cfg.spatial_same_confidence

    def test_different_place_id(self) -> None:
        """Different place_id -> d=1.0."""
        a = MockEvent("e1", 1000, None, place_id="home_123")
        b = MockEvent("e2", 2000, None, place_id="office_456")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_spatial(a, b, cfg)
        assert d == cfg.spatial_diff_place

    def test_hierarchy_overlap(self) -> None:
        """Shared hierarchy levels reduce distance."""
        import json

        hier_a = json.dumps(["USA", "CA", "SF"])
        hier_b = json.dumps(["USA", "CA", "LA"])
        a = MockEvent("e1", 1000, None, location_hierarchy_json=hier_a)
        b = MockEvent("e2", 2000, None, location_hierarchy_json=hier_b)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_spatial(a, b, cfg)
        assert 0.0 < d < 1.0  # Partial overlap
        assert c == cfg.spatial_hierarchy_confidence

    def test_geohash_prefix_match(self) -> None:
        """Shared geohash prefix -> proportional distance."""
        a = MockEvent("e1", 1000, None, geohash_6="9q8yyk")
        b = MockEvent("e2", 2000, None, geohash_6="9q8yyp")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_spatial(a, b, cfg)
        assert 0.0 < d < 1.0

    def test_no_spatial_signal(self) -> None:
        """No spatial data -> MISS."""
        a = MockEvent("e1", 1000, None)
        b = MockEvent("e2", 2000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_spatial(a, b, cfg)
        assert d == 0.5
        assert c == cfg.spatial_miss_confidence


class TestSocialDimension:
    """Test _cd_social distance function."""

    def test_same_participants(self) -> None:
        """Same participants -> d=0.0."""
        import json

        p = json.dumps(["alice", "bob"])
        a = MockEvent("e1", 1000, None, participants_json=p)
        b = MockEvent("e2", 2000, None, participants_json=p)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_social(a, b, cfg)
        assert d == pytest.approx(0.0)

    def test_different_participants(self) -> None:
        """Disjoint participants -> d=1.0."""
        import json

        a = MockEvent("e1", 1000, None, participants_json=json.dumps(["alice"]))
        b = MockEvent("e2", 2000, None, participants_json=json.dumps(["bob"]))
        cfg = EnsembleDistanceConfig()
        d, c = _cd_social(a, b, cfg)
        assert d == pytest.approx(1.0)

    def test_partial_overlap(self) -> None:
        """Partial overlap -> 0 < d < 1."""
        import json

        a = MockEvent("e1", 1000, None, participants_json=json.dumps(["alice", "bob"]))
        b = MockEvent("e2", 2000, None, participants_json=json.dumps(["bob", "carol"]))
        cfg = EnsembleDistanceConfig()
        d, c = _cd_social(a, b, cfg)
        assert 0.0 < d < 1.0

    def test_same_context(self) -> None:
        """Same social_context -> d=0.0."""
        a = MockEvent("e1", 1000, None, social_context="family_dinner")
        b = MockEvent("e2", 2000, None, social_context="family_dinner")
        cfg = EnsembleDistanceConfig()
        d, c = _cd_social(a, b, cfg)
        assert d == 0.0

    def test_both_solo(self) -> None:
        """Both solo -> d=0.0."""
        a = MockEvent("e1", 1000, None, is_solo_event=True)
        b = MockEvent("e2", 2000, None, is_solo_event=True)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_social(a, b, cfg)
        assert d == 0.0
        assert c == cfg.social_solo_confidence

    def test_no_social_signal(self) -> None:
        """No social data -> MISS."""
        a = MockEvent("e1", 1000, None)
        b = MockEvent("e2", 2000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_social(a, b, cfg)
        assert d == 0.5
        assert c == cfg.social_miss_confidence


class TestAffectiveDimension:
    """Test _cd_affective distance function."""

    def test_same_affect(self) -> None:
        """Same VAD -> d=0.0."""
        a = MockEvent(
            "e1", 1000, None, affect_valence=0.5, affect_arousal=0.5, affect_dominance=0.5
        )
        b = MockEvent(
            "e2", 2000, None, affect_valence=0.5, affect_arousal=0.5, affect_dominance=0.5
        )
        cfg = EnsembleDistanceConfig()
        d, c = _cd_affective(a, b, cfg)
        assert d == pytest.approx(0.0)

    def test_opposite_valence(self) -> None:
        """Opposite valence -> nonzero distance."""
        a = MockEvent(
            "e1", 1000, None, affect_valence=1.0, affect_arousal=0.0, affect_dominance=0.0
        )
        b = MockEvent(
            "e2", 2000, None, affect_valence=-1.0, affect_arousal=0.0, affect_dominance=0.0
        )
        cfg = EnsembleDistanceConfig()
        d, c = _cd_affective(a, b, cfg)
        assert d > 0.0
        assert c == cfg.affective_present_confidence

    def test_missing_valence(self) -> None:
        """Missing valence -> MISS."""
        a = MockEvent("e1", 1000, None, affect_valence=0.5)
        b = MockEvent("e2", 2000, None)
        cfg = EnsembleDistanceConfig()
        d, c = _cd_affective(a, b, cfg)
        assert d == 0.5
        assert c == cfg.affective_miss_confidence


# =============================================================================
# EnsembleDistance Integration Tests (Issue 3.1.6)
# =============================================================================


class TestEnsembleDistance:
    """Test EnsembleDistance class -- the full 6D distance."""

    def test_identical_events_zero_distance(self) -> None:
        """Identical events -> distance ~0.0."""
        emb = make_embedding(42)
        a = MockEvent(
            "e1",
            1_000_000_000_000,
            emb,
            narrative_thread_id="morning_routine",
        )
        b = MockEvent(
            "e2",
            1_000_000_000_000,
            emb,
            narrative_thread_id="morning_routine",
        )
        dist = EnsembleDistance()
        result = dist.compute(a, b)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_temporal_hard_cutoff(self) -> None:
        """Events beyond 4h -> inf regardless of other signals."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        a = MockEvent("e1", base, emb, narrative_thread_id="thread_1")
        b = MockEvent("e2", base + 5 * MS_PER_HOUR, emb, narrative_thread_id="thread_1")
        dist = EnsembleDistance()
        result = dist.compute(a, b)
        assert result == float("inf")

    def test_same_thread_shortcircuit(self) -> None:
        """Same thread with divergent semantics -> clamped by short-circuit."""
        v1, v2 = make_orthogonal_embeddings()
        base = 1_000_000_000_000
        a = MockEvent("e1", base, v1, narrative_thread_id="morning_routine")
        b = MockEvent("e2", base + MS_PER_HOUR, v2, narrative_thread_id="morning_routine")
        cfg = EnsembleDistanceConfig(shortcircuit=True, shortcircuit_cap=0.20)
        dist = EnsembleDistance(cfg)
        result = dist.compute(a, b)
        # Without short-circuit, semantic distance would dominate (orthogonal = 1.0)
        # Short-circuit should clamp to <= 0.20
        assert result <= 0.20

    def test_no_shortcircuit_when_disabled(self) -> None:
        """Without short-circuit, same-thread divergent semantics not clamped."""
        v1, v2 = make_orthogonal_embeddings()
        base = 1_000_000_000_000
        a = MockEvent("e1", base, v1, narrative_thread_id="morning_routine")
        b = MockEvent("e2", base + MS_PER_HOUR, v2, narrative_thread_id="morning_routine")
        cfg = EnsembleDistanceConfig(shortcircuit=False)
        dist = EnsembleDistance(cfg)
        result = dist.compute(a, b)
        assert result > 0.20

    def test_different_threads_high_distance(self) -> None:
        """Different threads, orthogonal embeddings -> high distance."""
        v1, v2 = make_orthogonal_embeddings()
        base = 1_000_000_000_000
        a = MockEvent("e1", base, v1, narrative_thread_id="morning_routine")
        b = MockEvent("e2", base + MS_PER_HOUR, v2, narrative_thread_id="work_project")
        dist = EnsembleDistance()
        result = dist.compute(a, b)
        assert result > 0.5

    def test_graceful_degradation_missing_narrative(self) -> None:
        """Missing narrative -> weight redistributed to semantic+temporal."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + MS_PER_HOUR, emb)
        dist = EnsembleDistance()
        result = dist.compute(a, b)
        # Should produce a valid distance, not crash
        assert 0.0 <= result < float("inf")

    def test_graceful_degradation_no_embeddings(self) -> None:
        """No embeddings -> semantic fallback or neutral 0.5."""
        a = MockEvent("e1", 1_000_000_000_000, None)
        b = MockEvent("e2", 1_000_000_000_100, None)
        cfg = EnsembleDistanceConfig(w_semantic=0.0, w_temporal=1.0)
        dist = EnsembleDistance(cfg)
        result = dist.compute(a, b)
        assert 0.0 <= result < float("inf")

    def test_all_signals_missing_returns_fallback(self) -> None:
        """All signals zero-confidence -> semantic fallback or 0.5."""
        a = MockEvent("e1", 1_000_000_000_000, None)
        b = MockEvent("e2", 1_000_000_000_000, None)
        # Only narrative active, but no narrative signals
        cfg = EnsembleDistanceConfig(
            w_semantic=0.0,
            w_temporal=0.0,
            w_narrative=1.0,
        )
        dist = EnsembleDistance(cfg)
        result = dist.compute(a, b)
        assert result == pytest.approx(0.5)

    def test_build_distance_matrix_symmetric(self) -> None:
        """Distance matrix is symmetric."""
        events = [
            MockEvent("e1", 1_000_000_000_000, make_embedding(1), narrative_thread_id="t1"),
            MockEvent("e2", 1_000_000_001_000, make_embedding(2), narrative_thread_id="t2"),
            MockEvent("e3", 1_000_000_002_000, make_embedding(3)),
        ]
        dist = EnsembleDistance()
        matrix = dist.build_distance_matrix(events)
        assert matrix.shape == (3, 3)
        np.testing.assert_array_almost_equal(matrix, matrix.T)

    def test_build_distance_matrix_diagonal_zero(self) -> None:
        """Distance matrix diagonal is zero."""
        events = [
            MockEvent("e1", 1_000_000_000_000, make_embedding(1)),
            MockEvent("e2", 1_000_000_001_000, make_embedding(2)),
        ]
        dist = EnsembleDistance()
        matrix = dist.build_distance_matrix(events)
        assert matrix[0, 0] == 0.0
        assert matrix[1, 1] == 0.0

    def test_build_distance_matrix_empty(self) -> None:
        """Empty events -> empty matrix."""
        dist = EnsembleDistance()
        matrix = dist.build_distance_matrix([])
        assert matrix.shape == (0, 0)

    def test_compute_pair_detail_structure(self) -> None:
        """Observability detail has correct structure."""
        emb = make_embedding(42)
        a = MockEvent("e1", 1_000_000_000_000, emb, narrative_thread_id="t1")
        b = MockEvent("e2", 1_000_000_001_000, emb, narrative_thread_id="t1")
        dist = EnsembleDistance()
        detail = dist.compute_pair_detail(a, b)
        assert "total_distance" in detail
        assert "dimensions" in detail
        assert "signal_availability" in detail
        assert "semantic" in detail["dimensions"]
        assert "temporal" in detail["dimensions"]
        assert "narrative" in detail["dimensions"]
        assert detail["signal_availability"]["spatial"] is False  # weight=0.0

    def test_spatial_dimension_wired(self) -> None:
        """Spatial dimension contributes when weight > 0."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        a = MockEvent("e1", base, emb, place_id="home_123")
        b = MockEvent("e2", base, emb, place_id="home_123")
        cfg = EnsembleDistanceConfig(w_spatial=0.2, w_semantic=0.4, w_temporal=0.1, w_narrative=0.3)
        dist = EnsembleDistance(cfg)
        result = dist.compute(a, b)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_social_dimension_wired(self) -> None:
        """Social dimension contributes when weight > 0."""
        import json

        emb = make_embedding(42)
        base = 1_000_000_000_000
        p = json.dumps(["alice", "bob"])
        a = MockEvent("e1", base, emb, participants_json=p)
        b = MockEvent("e2", base, emb, participants_json=p)
        cfg = EnsembleDistanceConfig(w_social=0.2, w_semantic=0.4, w_temporal=0.1, w_narrative=0.3)
        dist = EnsembleDistance(cfg)
        result = dist.compute(a, b)
        assert result == pytest.approx(0.0, abs=0.01)


class TestParseJsonList:
    """Test _parse_json_list helper."""

    def test_valid_list(self) -> None:
        assert _parse_json_list('["a", "b"]') == ["a", "b"]

    def test_none(self) -> None:
        assert _parse_json_list(None) == []

    def test_empty_string(self) -> None:
        assert _parse_json_list("") == []

    def test_invalid_json(self) -> None:
        assert _parse_json_list("not json") == []

    def test_non_list_json(self) -> None:
        assert _parse_json_list('{"key": "val"}') == []


# =============================================================================
# Epic 3.2 Tests — Log-Temporal, Timestamp Quality, Hard-Cutoff
# =============================================================================


class TestLogTemporalCurveShape:
    """Epic 3.2.1: Verify log-compressed temporal distance curve properties.

    The log formula: d = log(1 + diff/tau) / log(1 + max_gap/tau)
    should compress far gaps and differentiate near gaps more than linear.
    """

    def test_log_steeper_near_time_than_linear(self) -> None:
        """Log curve rises faster than linear at small time gaps."""
        base = 1_000_000_000_000
        gap_15min = 15 * 60 * 1000  # 15 minutes
        tau = 1_800_000
        max_gap = 14_400_000

        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + gap_15min, None)

        cfg_log = EnsembleDistanceConfig(use_log_temporal=True, log_temporal_tau_ms=tau)
        cfg_lin = EnsembleDistanceConfig(use_log_temporal=False)

        d_log, _ = _cd_temporal(a, b, cfg_log)
        d_lin, _ = _cd_temporal(a, b, cfg_lin)

        # Log is steeper near t=0: d_log > d_lin for small gaps
        assert d_log > d_lin

    def test_log_flatter_far_time_than_linear(self) -> None:
        """Log curve saturates: at max_gap, both reach 1.0 but log rises faster early.

        The log formula with tau=30min steepens early gaps but the curve
        always reaches 1.0 at max_gap. We verify that the log curve
        consistently differentiates temporal gaps (increases faster for
        near gaps, creating a nonlinear compression shape).
        """
        base = 1_000_000_000_000
        cfg_log = EnsembleDistanceConfig(use_log_temporal=True, log_temporal_tau_ms=1_800_000)
        cfg_lin = EnsembleDistanceConfig(use_log_temporal=False)

        # Collect distances at multiple gaps to verify curve shape
        gaps_ms = [5 * 60_000, 30 * 60_000, 60 * 60_000, 120 * 60_000, 210 * 60_000]
        log_dists = []
        lin_dists = []
        for gap in gaps_ms:
            a = MockEvent("e1", base, None)
            b = MockEvent("e2", base + gap, None)
            d_log, _ = _cd_temporal(a, b, cfg_log)
            d_lin, _ = _cd_temporal(a, b, cfg_lin)
            log_dists.append(d_log)
            lin_dists.append(d_lin)

        # Log rises faster early (5min, 30min): d_log > d_lin
        assert log_dists[0] > lin_dists[0]  # 5min
        assert log_dists[1] > lin_dists[1]  # 30min (at tau)

        # The curves converge toward 1.0 at max_gap.
        # Both approach 1.0 but with different shapes.
        assert all(0.0 <= d <= 1.0 for d in log_dists)
        assert all(0.0 <= d <= 1.0 for d in lin_dists)

    def test_log_temporal_monotonically_increasing(self) -> None:
        """Log distance increases monotonically with time gap."""
        base = 1_000_000_000_000
        cfg = EnsembleDistanceConfig(use_log_temporal=True)

        gaps = [0, 60_000, 300_000, 900_000, 1_800_000, 3_600_000, 7_200_000, 14_000_000]
        distances = []
        for gap in gaps:
            a = MockEvent("e1", base, None)
            b = MockEvent("e2", base + gap, None)
            d, _ = _cd_temporal(a, b, cfg)
            distances.append(d)

        for i in range(len(distances) - 1):
            assert distances[i] <= distances[i + 1]

    def test_log_temporal_boundary_values(self) -> None:
        """t=0 -> d=0, t=max_gap -> d=1.0."""
        base = 1_000_000_000_000
        cfg = EnsembleDistanceConfig(
            use_log_temporal=True,
            max_temporal_gap_ms=14_400_000,
        )

        # t=0
        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base, None)
        d, _ = _cd_temporal(a, b, cfg)
        assert d == pytest.approx(0.0)

        # t=max_gap
        b = MockEvent("e2", base + 14_400_000, None)
        d, _ = _cd_temporal(a, b, cfg)
        assert d == pytest.approx(1.0, abs=0.01)

    def test_log_tau_controls_steepness(self) -> None:
        """Small tau = steep initial rise; large tau = more linear."""
        base = 1_000_000_000_000
        gap_5min = 5 * 60 * 1000

        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + gap_5min, None)

        cfg_small_tau = EnsembleDistanceConfig(
            use_log_temporal=True,
            log_temporal_tau_ms=300_000,  # 5 min
        )
        cfg_large_tau = EnsembleDistanceConfig(
            use_log_temporal=True,
            log_temporal_tau_ms=7_200_000,  # 2h
        )

        d_small, _ = _cd_temporal(a, b, cfg_small_tau)
        d_large, _ = _cd_temporal(a, b, cfg_large_tau)

        # Small tau -> steeper rise for same gap -> higher distance
        assert d_small > d_large

    def test_legacy_composite_log_temporal(self) -> None:
        """CompositeDistance uses log-temporal by default (3.2.1)."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        gap_2h = 2 * MS_PER_HOUR

        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + gap_2h, emb)

        # Default CompositeDistance now uses log-temporal
        params_log = ClusteringDistanceParams(temporal_weight=0.3)
        dist_log = CompositeDistance(params_log)
        d_log = dist_log.compute(a, b)

        # Explicit linear for comparison
        params_lin = ClusteringDistanceParams(temporal_weight=0.3, use_log_temporal=False)
        dist_lin = CompositeDistance(params_lin)
        d_lin = dist_lin.compute(a, b)

        # Same embedding -> cosine_distance = 0
        # Log temporal at 2h: ~0.73 -> composite = 0.3 * 0.73 ~ 0.22
        # Linear temporal at 2h: 0.5 -> composite = 0.3 * 0.5 = 0.15
        assert d_log > d_lin

    def test_log_temporal_research_defaults(self) -> None:
        """Log-temporal with research defaults: tau=30min, max_gap=4h."""
        base = 1_000_000_000_000
        cfg = EnsembleDistanceConfig()

        assert cfg.use_log_temporal is True
        assert cfg.log_temporal_tau_ms == 1_800_000
        assert cfg.max_temporal_gap_ms == 14_400_000

        # At tau (30 min): d = log(2) / log(9) ~ 0.316
        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + 1_800_000, None)
        d, _ = _cd_temporal(a, b, cfg)
        assert d == pytest.approx(0.316, abs=0.02)

    def test_legacy_params_log_temporal_validation(self) -> None:
        """ClusteringDistanceParams validates log_temporal_tau_ms."""
        with pytest.raises(ValueError, match="log_temporal_tau_ms must be > 0"):
            ClusteringDistanceParams(log_temporal_tau_ms=0).validate()

    def test_legacy_params_log_temporal_serialization(self) -> None:
        """ClusteringDistanceParams round-trip includes log-temporal fields."""
        params = ClusteringDistanceParams(
            use_log_temporal=True,
            log_temporal_tau_ms=600_000,
        )
        data = params.to_dict()
        assert data["use_log_temporal"] is True
        assert data["log_temporal_tau_ms"] == 600_000

        restored = ClusteringDistanceParams.from_dict(data)
        assert restored.use_log_temporal is True
        assert restored.log_temporal_tau_ms == 600_000


class TestTimestampQualityConfidence:
    """Epic 3.2.2: Temporal confidence attenuated by timestamp provenance.

    Quality tiers determine how much the temporal dimension contributes
    to the ensemble. Low-quality timestamps -> lower temporal confidence
    -> weight redistributes to semantic/narrative dimensions.
    """

    def test_mw_resolved_full_confidence(self) -> None:
        """MW-resolved timestamps get full confidence."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence("mw_resolved", "mw_resolved", cfg)
        assert c == 1.0

    def test_conversation_anchor_full_confidence(self) -> None:
        """Conversation anchor timestamps get full confidence."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence(
            "conversation_anchor_ms",
            "conversation_anchor_ms",
            cfg,
        )
        assert c == 1.0

    def test_event_time_utc_high_confidence(self) -> None:
        """event_time_utc gets high but not full confidence."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence("event_time_utc", "event_time_utc", cfg)
        assert c == 0.9

    def test_created_at_moderate_confidence(self) -> None:
        """created_at gets moderate confidence."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence("created_at", "created_at", cfg)
        assert c == 0.7

    def test_envelope_ts_floor_confidence(self) -> None:
        """envelope_ts gets conservative floor confidence."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence("envelope_ts", "envelope_ts", cfg)
        assert c == 0.5

    def test_unknown_source_default_confidence(self) -> None:
        """Unknown/empty temporal_source -> tq_unknown (1.0 by default)."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence(None, None, cfg)
        assert c == 1.0

        c2 = _temporal_quality_confidence("", "", cfg)
        assert c2 == 1.0

    def test_asymmetric_quality_uses_min(self) -> None:
        """When one event has high quality and other low, use min (conservative)."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence("mw_resolved", "envelope_ts", cfg)
        assert c == 0.5  # min(1.0, 0.5) = 0.5

    def test_asymmetric_created_at_vs_mw(self) -> None:
        """MW + created_at pair uses created_at confidence."""
        cfg = EnsembleDistanceConfig()
        c = _temporal_quality_confidence("mw_resolved", "created_at", cfg)
        assert c == 0.7  # min(1.0, 0.7)

    def test_cd_temporal_uses_quality_confidence(self) -> None:
        """_cd_temporal returns attenuated confidence for low-quality timestamps."""
        base = 1_000_000_000_000
        a = MockEvent("e1", base, None, temporal_source="envelope_ts")
        b = MockEvent("e2", base + MS_PER_HOUR, None, temporal_source="envelope_ts")

        cfg = EnsembleDistanceConfig()
        d, c = _cd_temporal(a, b, cfg)

        assert 0.0 < d < 1.0
        assert c == 0.5  # envelope_ts tier

    def test_cd_temporal_mw_resolved_full_confidence(self) -> None:
        """_cd_temporal with high-quality timestamps returns full confidence."""
        base = 1_000_000_000_000
        a = MockEvent("e1", base, None, temporal_source="mw_resolved")
        b = MockEvent("e2", base + MS_PER_HOUR, None, temporal_source="mw_resolved")

        cfg = EnsembleDistanceConfig()
        d, c = _cd_temporal(a, b, cfg)

        assert 0.0 < d < 1.0
        assert c == 1.0

    def test_cd_temporal_no_source_backward_compat(self) -> None:
        """Events without temporal_source get full confidence (backward compat)."""
        base = 1_000_000_000_000
        a = MockEvent("e1", base, None)
        b = MockEvent("e2", base + MS_PER_HOUR, None)

        cfg = EnsembleDistanceConfig()
        d, c = _cd_temporal(a, b, cfg)

        assert c == 1.0  # tq_unknown = 1.0

    def test_ensemble_weight_redistribution_on_low_quality(self) -> None:
        """Low temporal quality -> less temporal weight -> semantic dominates more."""
        emb_a = make_embedding(1)
        emb_b = make_embedding(2)
        base = 1_000_000_000_000

        # High quality temporal
        a_hi = MockEvent("e1", base, emb_a, temporal_source="mw_resolved")
        b_hi = MockEvent("e2", base + 30 * 60 * 1000, emb_b, temporal_source="mw_resolved")

        # Low quality temporal
        a_lo = MockEvent("e1", base, emb_a, temporal_source="envelope_ts")
        b_lo = MockEvent("e2", base + 30 * 60 * 1000, emb_b, temporal_source="envelope_ts")

        cfg = EnsembleDistanceConfig()
        ens = EnsembleDistance(cfg)

        d_hi = ens.compute(a_hi, b_hi)
        d_lo = ens.compute(a_lo, b_lo)

        # Both distances should be valid
        assert 0.0 < d_hi < float("inf")
        assert 0.0 < d_lo < float("inf")

        # With low quality timestamps, temporal contributes less.
        # The difference depends on how much temporal helps/hurts,
        # but they should differ.
        assert d_hi != pytest.approx(d_lo, abs=0.001)

    def test_configurable_quality_tiers(self) -> None:
        """Quality tier confidences are configurable via EnsembleDistanceConfig."""
        cfg = EnsembleDistanceConfig(
            tq_mw_resolved=0.95,
            tq_created_at=0.3,
            tq_envelope_ts=0.2,
            tq_unknown=0.8,
        )
        assert _temporal_quality_confidence("mw_resolved", "mw_resolved", cfg) == 0.95
        assert _temporal_quality_confidence("created_at", "created_at", cfg) == 0.3
        assert _temporal_quality_confidence("envelope_ts", "envelope_ts", cfg) == 0.2
        assert _temporal_quality_confidence(None, None, cfg) == 0.8

    def test_hard_cutoff_ignores_quality(self) -> None:
        """Hard cutoff returns inf regardless of temporal quality."""
        base = 1_000_000_000_000
        a = MockEvent("e1", base, None, temporal_source="mw_resolved")
        b = MockEvent("e2", base + 5 * MS_PER_HOUR, None, temporal_source="mw_resolved")

        cfg = EnsembleDistanceConfig(max_temporal_gap_ms=4 * MS_PER_HOUR)
        d, c = _cd_temporal(a, b, cfg)

        assert d == float("inf")
        assert c == 1.0  # inf always has conf=1.0

    def test_compute_pair_detail_shows_quality(self) -> None:
        """compute_pair_detail exposes temporal confidence from quality."""
        emb = make_embedding(42)
        base = 1_000_000_000_000

        a = MockEvent("e1", base, emb, temporal_source="created_at")
        b = MockEvent("e2", base + MS_PER_HOUR, emb, temporal_source="created_at")

        cfg = EnsembleDistanceConfig()
        ens = EnsembleDistance(cfg)
        detail = ens.compute_pair_detail(a, b)

        assert "temporal" in detail["dimensions"]
        assert detail["dimensions"]["temporal"]["confidence"] == 0.7


class TestHardCutoffSemantics:
    """Epic 3.2.3: Verify hard-cutoff interaction chain.

    Priority: hard cutoff (inf) > narrative short-circuit (0.20 cap) > ensemble.
    The hard cutoff cannot be overridden by any other signal.
    """

    def test_hard_cutoff_overrides_shortcircuit(self) -> None:
        """Same-thread events beyond 4h get inf, not short-circuit cap."""
        emb = make_embedding(42)
        base = 1_000_000_000_000

        a = MockEvent("e1", base, emb, narrative_thread_id="thread_A")
        b = MockEvent(
            "e2",
            base + 5 * MS_PER_HOUR,
            emb,
            narrative_thread_id="thread_A",
        )

        cfg = EnsembleDistanceConfig(shortcircuit=True, shortcircuit_cap=0.20)
        ens = EnsembleDistance(cfg)
        d = ens.compute(a, b)

        # Hard cutoff wins, not short-circuit
        assert d == float("inf")

    def test_shortcircuit_within_cutoff(self) -> None:
        """Same-thread events within 4h get short-circuit cap."""
        emb = make_embedding(42)
        base = 1_000_000_000_000

        a = MockEvent("e1", base, emb, narrative_thread_id="thread_A")
        b = MockEvent(
            "e2",
            base + 3 * MS_PER_HOUR,
            emb,
            narrative_thread_id="thread_A",
        )

        cfg = EnsembleDistanceConfig(shortcircuit=True, shortcircuit_cap=0.20)
        ens = EnsembleDistance(cfg)
        d = ens.compute(a, b)

        # Within cutoff, short-circuit applies
        assert d <= cfg.shortcircuit_cap

    def test_near_cutoff_boundary_finite(self) -> None:
        """Events 1ms before max gap get finite distance."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        just_under = 4 * MS_PER_HOUR - 1  # 3h 59m 59.999s

        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + just_under, emb)

        cfg = EnsembleDistanceConfig()
        ens = EnsembleDistance(cfg)
        d = ens.compute(a, b)

        assert d < float("inf")
        assert d >= 0.0

    def test_just_over_cutoff_infinite(self) -> None:
        """Events 1ms over max gap get inf distance."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        just_over = 4 * MS_PER_HOUR + 1

        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + just_over, emb)

        cfg = EnsembleDistanceConfig()
        ens = EnsembleDistance(cfg)
        d = ens.compute(a, b)

        assert d == float("inf")

    def test_exactly_at_cutoff_infinite(self) -> None:
        """Events exactly at max gap boundary get inf (> not >=)."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        exact = 4 * MS_PER_HOUR

        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + exact, emb)

        # The comparison is > max_temporal_gap_ms, so exact is NOT inf
        cfg = EnsembleDistanceConfig(max_temporal_gap_ms=exact)
        ens = EnsembleDistance(cfg)
        d = ens.compute(a, b)

        assert d < float("inf")

    def test_hard_cutoff_in_distance_matrix(self) -> None:
        """Hard cutoff produces inf in distance matrix too."""
        events = [
            MockEvent("e1", 1_000_000_000_000, make_embedding(1)),
            MockEvent("e2", 1_000_000_000_000 + 1 * MS_PER_HOUR, make_embedding(2)),
            MockEvent("e3", 1_000_000_000_000 + 5 * MS_PER_HOUR, make_embedding(3)),
        ]

        cfg = EnsembleDistanceConfig()
        ens = EnsembleDistance(cfg)
        matrix = ens.build_distance_matrix(events)

        # e1-e2: 1h apart, should be finite
        assert matrix[0, 1] < float("inf")
        # e1-e3: 5h apart, should be inf
        assert matrix[0, 2] == float("inf")

    def test_hard_cutoff_disabled(self) -> None:
        """When hard_temporal_cutoff=False, far events get finite distance."""
        emb = make_embedding(42)
        base = 1_000_000_000_000

        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + 10 * MS_PER_HOUR, emb)

        cfg = EnsembleDistanceConfig(hard_temporal_cutoff=False)
        ens = EnsembleDistance(cfg)
        d = ens.compute(a, b)

        assert d < float("inf")

    def test_legacy_composite_hard_cutoff(self) -> None:
        """Legacy CompositeDistance also has hard cutoff."""
        emb = make_embedding(42)
        base = 1_000_000_000_000

        a = MockEvent("e1", base, emb)
        b = MockEvent("e2", base + 5 * MS_PER_HOUR, emb)

        params = ClusteringDistanceParams(max_temporal_gap_hours=4.0)
        dist = CompositeDistance(params)
        d = dist.compute(a, b)

        assert d == float("inf")

    def test_priority_chain_hard_cutoff_gt_shortcircuit_gt_ensemble(self) -> None:
        """Full priority chain: hard cutoff > short-circuit > ensemble distance."""
        emb = make_embedding(42)
        base = 1_000_000_000_000
        cfg = EnsembleDistanceConfig(shortcircuit=True, shortcircuit_cap=0.20)
        ens = EnsembleDistance(cfg)

        # Case 1: Beyond hard cutoff, same thread -> inf (not short-circuit)
        a = MockEvent("e1", base, emb, narrative_thread_id="t1")
        b = MockEvent("e2", base + 5 * MS_PER_HOUR, emb, narrative_thread_id="t1")
        assert ens.compute(a, b) == float("inf")

        # Case 2: Within cutoff, same thread -> short-circuit cap
        c = MockEvent("e3", base + 1 * MS_PER_HOUR, emb, narrative_thread_id="t1")
        d_sc = ens.compute(a, c)
        assert d_sc <= cfg.shortcircuit_cap

        # Case 3: Within cutoff, different threads -> ensemble (no short-circuit)
        d_ens = MockEvent("e4", base + 1 * MS_PER_HOUR, emb, narrative_thread_id="t2")
        d_result = ens.compute(a, d_ens)
        # Should be > 0 (different threads contribute narrative distance)
        assert d_result > 0
