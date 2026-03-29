"""
Epic 6.1: Wire Ensemble Distance Into Production R2.

Tests that R2Config correctly controls ensemble distance wiring and that
EpisodicHDBSCAN uses ensemble distance when configured (default) vs
legacy 2D composite distance when disabled.

Issues covered:
    6.1.1: Wire ensemble_config in _initialize_components
    6.1.2: R2Config fields for ensemble control
    6.1.3: Legacy fallback when enable_ensemble_distance=False
    6.1.4: Integration tests with ensemble distance path
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms import (
    EnsembleDistanceConfig,
    EpisodicHDBSCAN,
    HDBSCANParams,
)
from k0.modules.consolidation.algorithms.composite_distance import (
    CompositeDistance,
    EnsembleDistance,
)
from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event satisfying both ClusterableEvent and EventLike protocols."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]] = None
    importance_score: float = 0.5
    sentiment_score: float = 0.5
    geohash_6: Optional[str] = "9q8yyz"
    activity_type: Optional[str] = "general"
    place_id: Optional[str] = None
    narrative_thread_id: Optional[str] = None
    goal_context: Optional[str] = None
    participants_json: Optional[str] = None
    social_context: Optional[str] = None
    temporal_source: Optional[str] = None

    # Mutable clustering fields
    cluster_id: Optional[str] = None
    cluster_label: int = -1
    is_noise: bool = False
    centroid_distance: float = 0.0


def _make_embedding(seed: int, dim: int = 768) -> List[float]:
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype(np.float32)
    return (vec / np.linalg.norm(vec)).tolist()


def _similar_events(
    count: int,
    thread_id: Optional[str] = None,
    base_seed: int = 42,
    base_ts: int = 1_000_000_000_000,
    gap_ms: int = 60_000,
) -> List[MockEvent]:
    """Events with similar embeddings and optional shared thread."""
    base_emb = _make_embedding(base_seed)
    events = []
    for i in range(count):
        rng = np.random.default_rng(base_seed + i + 1000)
        noise = rng.standard_normal(768).astype(np.float32) * 0.05
        emb = (np.array(base_emb) + noise).tolist()
        events.append(
            MockEvent(
                event_id=f"sim-{i}",
                timestamp=base_ts + i * gap_ms,
                embedding_768=emb,
                narrative_thread_id=thread_id,
            )
        )
    return events


def _dissimilar_events(
    count: int,
    base_ts: int = 1_000_000_000_000,
    gap_ms: int = 60_000,
) -> List[MockEvent]:
    """Events with completely different embeddings."""
    return [
        MockEvent(
            event_id=f"dis-{i}",
            timestamp=base_ts + i * gap_ms,
            embedding_768=_make_embedding(i * 1000),
        )
        for i in range(count)
    ]


# =============================================================================
# 6.1.2: R2Config fields for ensemble control
# =============================================================================


class TestR2ConfigEnsembleFields:
    """Issue 6.1.2: R2Config has ensemble distance control fields."""

    def test_default_enables_ensemble(self):
        cfg = R2Config()
        assert cfg.enable_ensemble_distance is True

    def test_default_config_is_none(self):
        cfg = R2Config()
        assert cfg.ensemble_distance_config is None

    def test_explicit_disable(self):
        cfg = R2Config(enable_ensemble_distance=False)
        assert cfg.enable_ensemble_distance is False

    def test_custom_config_override(self):
        custom = EnsembleDistanceConfig(w_semantic=0.50, w_temporal=0.20, w_narrative=0.30)
        cfg = R2Config(ensemble_distance_config=custom)
        assert cfg.ensemble_distance_config is custom
        assert cfg.ensemble_distance_config.w_semantic == 0.50

    def test_legacy_weights_still_exist(self):
        """Legacy semantic_weight/temporal_weight remain for fallback."""
        cfg = R2Config()
        assert cfg.semantic_weight == 0.7
        assert cfg.temporal_weight == 0.3


# =============================================================================
# 6.1.1 / 6.1.3: EpisodicHDBSCAN uses ensemble vs legacy distance
# =============================================================================


class TestEnsembleDistanceWiring:
    """Issue 6.1.1: ensemble_config wired to EpisodicHDBSCAN."""

    def test_ensemble_config_creates_ensemble_distance(self):
        """When ensemble_config is provided, distance calculator is EnsembleDistance."""
        ens_config = EnsembleDistanceConfig()
        clusterer = EpisodicHDBSCAN(ensemble_config=ens_config)
        assert isinstance(clusterer.distance_calculator, EnsembleDistance)

    def test_no_ensemble_config_creates_composite_distance(self):
        """When ensemble_config is None, falls back to legacy CompositeDistance."""
        clusterer = EpisodicHDBSCAN()
        assert isinstance(clusterer.distance_calculator, CompositeDistance)

    def test_default_config_uses_proven_weights(self):
        """Default EnsembleDistanceConfig has proven research weights."""
        cfg = EnsembleDistanceConfig()
        assert cfg.w_semantic == 0.45
        assert cfg.w_temporal == 0.25
        assert cfg.w_narrative == 0.30
        assert cfg.shortcircuit is True
        assert cfg.shortcircuit_cap == 0.20

    def test_ensemble_config_validates(self):
        """Invalid config raises ValueError."""
        with pytest.raises(ValueError):
            EnsembleDistanceConfig(w_semantic=-0.1).validate()

    def test_ensemble_config_weight_sum(self):
        cfg = EnsembleDistanceConfig()
        assert abs(cfg.weight_sum - 1.0) < 1e-9


# =============================================================================
# 6.1.4: Integration tests — ensemble distance produces valid clusters
# =============================================================================


class TestEnsembleClusteringIntegration:
    """Issue 6.1.4: R2 integration tests use ensemble distance path."""

    def test_similar_events_cluster_with_ensemble(self):
        """Semantically similar events cluster together under ensemble distance."""
        events = _similar_events(6, thread_id="morning_routine")
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(
                min_cluster_size=2,
                min_samples=1,
                cluster_selection_epsilon=0.3,
                allow_single_cluster=True,
                cluster_selection_method="eom",
            ),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster(events)
        assert result.cluster_count >= 1

    def test_dissimilar_events_separate_with_ensemble(self):
        """Very different events do not all merge into one cluster."""
        events = _dissimilar_events(8)
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster(events)
        # Should NOT be all in one cluster
        assert result.noise_count > 0 or result.cluster_count > 1

    def test_same_thread_shortcircuit_clusters_together(self):
        """Events with same narrative_thread_id cluster via shortcircuit."""
        events = _similar_events(5, thread_id="family_dinner")
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(
                min_cluster_size=2,
                min_samples=1,
                cluster_selection_epsilon=0.3,
                allow_single_cluster=True,
                cluster_selection_method="eom",
            ),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster(events)
        assert result.cluster_count >= 1
        # Most events should be in clusters (shortcircuit forces low distance)
        clustered_count = result.total_events - result.noise_count
        assert clustered_count >= 4  # at least 4 of 5

    def test_different_threads_separate(self):
        """Events from different narrative threads should not merge."""
        thread_a = _similar_events(4, thread_id="morning_routine", base_seed=10)
        thread_b = _similar_events(4, thread_id="work_meeting", base_seed=999)
        # Give thread_b different timestamps
        for i, e in enumerate(thread_b):
            e.event_id = f"b-{i}"
            e.timestamp += 7_200_000  # 2 hours later

        events = thread_a + thread_b
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster(events)
        # Expect at least 2 separate clusters for the two threads
        assert result.cluster_count >= 2

    def test_ensemble_produces_distance_matrix(self):
        """Ensemble distance path returns a valid distance matrix."""
        events = _similar_events(5, thread_id="test_thread")
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster(events)
        assert result.distance_matrix is not None
        n = len(events)
        assert result.distance_matrix.shape == (n, n)
        # Symmetric
        np.testing.assert_array_almost_equal(
            result.distance_matrix, result.distance_matrix.T, decimal=10
        )
        # Zero diagonal
        np.testing.assert_array_almost_equal(
            np.diag(result.distance_matrix), np.zeros(n), decimal=10
        )

    def test_legacy_fallback_still_works(self):
        """When ensemble is disabled, legacy CompositeDistance is used."""
        events = _similar_events(5)
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            # No ensemble_config → legacy path
        )
        result = clusterer.cluster(events)
        assert isinstance(clusterer.distance_calculator, CompositeDistance)
        assert result.distance_matrix is not None

    def test_ensemble_vs_legacy_different_distances(self):
        """Ensemble distance matrix differs from legacy composite distance."""
        events = _similar_events(5, thread_id="morning_routine")

        clusterer_ens = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result_ens = clusterer_ens.cluster(events)

        clusterer_legacy = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
        )
        result_legacy = clusterer_legacy.cluster(events)

        # Distance matrices should differ because ensemble adds narrative dimension
        assert not np.allclose(result_ens.distance_matrix, result_legacy.distance_matrix)

    def test_hebbian_boost_compatible_with_ensemble(self):
        """Hebbian boost works on top of ensemble distance."""
        from k0.modules.consolidation.algorithms.hebbian_boost import (
            HebbinaBoostConfig,
            build_cooccurrence_graph,
        )

        events = _similar_events(5, thread_id="test")
        for e in events:
            e.participants_json = '["alice", "bob"]'

        graph = build_cooccurrence_graph(events)
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
            hebbian_config=HebbinaBoostConfig(),
        )
        result = clusterer.cluster(events, cooccurrence_graph=graph)
        assert result.distance_matrix is not None
        assert result.cluster_count >= 1

    def test_empty_events(self):
        """Empty event list returns empty result with ensemble."""
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster([])
        assert result.total_events == 0
        assert result.cluster_count == 0

    def test_single_event(self):
        """Single event returns all-noise result with ensemble."""
        events = _similar_events(1)
        clusterer = EpisodicHDBSCAN(
            params=HDBSCANParams(min_cluster_size=2, min_samples=1),
            ensemble_config=EnsembleDistanceConfig(),
        )
        result = clusterer.cluster(events)
        assert result.total_events == 1
        assert result.cluster_count == 0
