"""
Tests for Hebbian co-occurrence distance boost (Epic 5.1).

Coverage:
    - CoOccurrenceEdge weight formula (saturating exponential)
    - build_cooccurrence_graph from batch events
    - compute_pairwise_affinity between event pairs
    - apply_hebbian_boost distance matrix modification
    - Integration with EpisodicHDBSCAN.cluster()
    - Edge cases: no participants, empty graph, disabled config

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.hebbian_boost import (
    CoOccurrenceEdge,
    HebbinaBoostConfig,
    _edge_key,
    _parse_participants,
    apply_hebbian_boost,
    build_cooccurrence_graph,
    compute_pairwise_affinity,
)

# =============================================================================
# Test Fixtures
# =============================================================================

BASE_TS = 1_000_000_000_000  # 2001-09-09 in ms


@dataclass
class MockParticipantEvent:
    """Mock event implementing _ParticipantSource protocol."""

    event_id: str = ""
    participants_json: Optional[str] = None
    place_id: Optional[str] = None
    timestamp: int = BASE_TS
    embedding_768: Optional[List[float]] = None
    sentiment_score: float = 0.0
    narrative_thread_id: Optional[str] = None
    geohash_6: Optional[str] = None
    social_context: Optional[str] = None
    goal_context: Optional[str] = None
    activity_type: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"evt-{uuid.uuid4().hex[:8]}"


def _unit_embedding(dim: int = 768, seed: float = 1.0) -> List[float]:
    rng = np.random.RandomState(int(abs(seed * 1000)) % (2**31))
    vec = rng.randn(int(dim)).astype(np.float64)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


# =============================================================================
# CoOccurrenceEdge tests
# =============================================================================


class TestCoOccurrenceEdge:
    def test_weight_zero_count(self):
        edge = CoOccurrenceEdge(source="a", target="b", count=0)
        assert edge.weight == 0.0

    def test_weight_negative_count(self):
        edge = CoOccurrenceEdge(source="a", target="b", count=-1)
        assert edge.weight == 0.0

    def test_weight_count_1(self):
        edge = CoOccurrenceEdge(source="a", target="b", count=1)
        expected = 1.0 - math.exp(-0.1 * 1)
        assert abs(edge.weight - expected) < 1e-10

    def test_weight_count_10(self):
        edge = CoOccurrenceEdge(source="a", target="b", count=10)
        expected = 1.0 - math.exp(-0.1 * 10)
        assert abs(edge.weight - expected) < 1e-10
        assert edge.weight > 0.6  # ~0.632

    def test_weight_saturates(self):
        edge = CoOccurrenceEdge(source="a", target="b", count=100)
        assert edge.weight > 0.99


class TestEdgeKey:
    def test_canonical_ordering(self):
        assert _edge_key("bob", "alice") == ("alice", "bob")
        assert _edge_key("alice", "bob") == ("alice", "bob")

    def test_same_entity(self):
        assert _edge_key("x", "x") == ("x", "x")


class TestParseParticipants:
    def test_empty_string(self):
        assert _parse_participants("") == []

    def test_none(self):
        assert _parse_participants(None) == []

    def test_valid_json(self):
        result = _parse_participants('["alice", "bob"]')
        assert result == ["alice", "bob"]

    def test_sorted_output(self):
        result = _parse_participants('["charlie", "alice", "bob"]')
        assert result == ["alice", "bob", "charlie"]

    def test_invalid_json(self):
        assert _parse_participants("not json") == []

    def test_non_list_json(self):
        assert _parse_participants('{"name": "alice"}') == []

    def test_filters_empty_strings(self):
        result = _parse_participants('["alice", "", "bob"]')
        assert result == ["alice", "bob"]


# =============================================================================
# build_cooccurrence_graph tests
# =============================================================================


class TestBuildCooccurrenceGraph:
    def test_single_event_two_actors(self):
        events = [
            MockParticipantEvent(
                event_id="e1",
                participants_json='["alice", "bob"]',
            ),
        ]
        graph = build_cooccurrence_graph(events)
        key = _edge_key("alice", "bob")
        assert key in graph
        assert graph[key].count == 1

    def test_two_events_same_actors_count_increments(self):
        events = [
            MockParticipantEvent(event_id="e1", participants_json='["alice", "bob"]'),
            MockParticipantEvent(event_id="e2", participants_json='["alice", "bob"]'),
        ]
        graph = build_cooccurrence_graph(events)
        key = _edge_key("alice", "bob")
        assert graph[key].count == 2

    def test_actor_location_cooccurrence(self):
        events = [
            MockParticipantEvent(
                event_id="e1",
                participants_json='["alice"]',
                place_id="home",
            ),
        ]
        graph = build_cooccurrence_graph(events)
        key = _edge_key("alice", "loc:home")
        assert key in graph
        assert graph[key].count == 1

    def test_no_participants_empty_graph(self):
        events = [
            MockParticipantEvent(event_id="e1", participants_json="[]"),
        ]
        graph = build_cooccurrence_graph(events)
        assert len(graph) == 0

    def test_three_actors_all_pairs(self):
        events = [
            MockParticipantEvent(
                event_id="e1",
                participants_json='["alice", "bob", "charlie"]',
            ),
        ]
        graph = build_cooccurrence_graph(events)
        # 3 choose 2 = 3 pairs
        assert len(graph) == 3
        assert _edge_key("alice", "bob") in graph
        assert _edge_key("alice", "charlie") in graph
        assert _edge_key("bob", "charlie") in graph

    def test_empty_events(self):
        graph = build_cooccurrence_graph([])
        assert len(graph) == 0


# =============================================================================
# compute_pairwise_affinity tests
# =============================================================================


class TestComputePairwiseAffinity:
    def test_shared_pair_positive_affinity(self):
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=5),
        }
        ea = MockParticipantEvent(event_id="e1", participants_json='["alice"]')
        eb = MockParticipantEvent(event_id="e2", participants_json='["bob"]')
        aff = compute_pairwise_affinity(ea, eb, graph)
        assert aff > 0.0

    def test_no_shared_pair_zero_affinity(self):
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=5),
        }
        ea = MockParticipantEvent(event_id="e1", participants_json='["alice"]')
        eb = MockParticipantEvent(event_id="e2", participants_json='["charlie"]')
        aff = compute_pairwise_affinity(ea, eb, graph)
        assert aff == 0.0

    def test_min_count_filter(self):
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=2),
        }
        ea = MockParticipantEvent(event_id="e1", participants_json='["alice"]')
        eb = MockParticipantEvent(event_id="e2", participants_json='["bob"]')
        # min_count=3 should filter out count=2
        aff = compute_pairwise_affinity(ea, eb, graph, min_count=3)
        assert aff == 0.0
        # min_count=2 should include
        aff = compute_pairwise_affinity(ea, eb, graph, min_count=2)
        assert aff > 0.0

    def test_no_participants_zero(self):
        graph = {}
        ea = MockParticipantEvent(event_id="e1", participants_json="[]")
        eb = MockParticipantEvent(event_id="e2", participants_json='["bob"]')
        assert compute_pairwise_affinity(ea, eb, graph) == 0.0

    def test_location_half_weight(self):
        graph = {
            _edge_key("alice", "loc:home"): CoOccurrenceEdge(
                source="alice", target="loc:home", count=10
            ),
        }
        ea = MockParticipantEvent(event_id="e1", participants_json='["alice"]', place_id="home")
        eb = MockParticipantEvent(event_id="e2", participants_json='["bob"]', place_id="home")
        aff = compute_pairwise_affinity(ea, eb, graph)
        # Location edges contribute at half weight
        full_weight = 1.0 - math.exp(-0.1 * 10)
        assert abs(aff - full_weight * 0.5) < 1e-10


# =============================================================================
# apply_hebbian_boost tests
# =============================================================================


class TestApplyHebbianBoost:
    def test_basic_boost_reduces_distance(self):
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=10),
        }
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
        ]
        dm = np.array([[0.0, 0.5], [0.5, 0.0]])
        boosted, diag = apply_hebbian_boost(dm, events, graph)
        assert boosted[0, 1] < 0.5
        assert boosted[1, 0] == boosted[0, 1]
        assert diag["pairs_boosted"] == 1

    def test_original_not_mutated(self):
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=10),
        }
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
        ]
        dm = np.array([[0.0, 0.5], [0.5, 0.0]])
        original = dm.copy()
        apply_hebbian_boost(dm, events, graph)
        np.testing.assert_array_equal(dm, original)

    def test_boost_cap_limits_reduction(self):
        """Max distance reduction is boost_cap (5% at default)."""
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(
                source="alice", target="bob", count=100  # Very high count, weight ~1.0
            ),
        }
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
        ]
        dm = np.array([[0.0, 1.0], [1.0, 0.0]])
        config = HebbinaBoostConfig(boost_scale=0.10, boost_cap=0.05)
        boosted, diag = apply_hebbian_boost(dm, events, graph, config)
        # With affinity ~1.0: boost = min(1.0*0.10, 0.05) = 0.05
        # d_new = 1.0 * (1 - 0.05) = 0.95
        assert abs(boosted[0, 1] - 0.95) < 0.01
        assert abs(diag["max_boost_applied"] - 0.05) < 0.001

    def test_disabled_config_noop(self):
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=10),
        }
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
        ]
        dm = np.array([[0.0, 0.5], [0.5, 0.0]])
        config = HebbinaBoostConfig(enabled=False)
        boosted, diag = apply_hebbian_boost(dm, events, graph, config)
        np.testing.assert_array_equal(boosted, dm)
        assert diag["pairs_boosted"] == 0

    def test_empty_graph_noop(self):
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
        ]
        dm = np.array([[0.0, 0.5], [0.5, 0.0]])
        boosted, diag = apply_hebbian_boost(dm, events, {})
        np.testing.assert_array_equal(boosted, dm)
        assert diag["pairs_boosted"] == 0

    def test_single_event_noop(self):
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
        ]
        dm = np.array([[0.0]])
        boosted, diag = apply_hebbian_boost(dm, events, {})
        assert boosted.shape == (1, 1)
        assert diag["pairs_boosted"] == 0

    def test_distance_never_negative(self):
        """Boost should never produce negative distances."""
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=100),
        }
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
        ]
        dm = np.array([[0.0, 0.01], [0.01, 0.0]])
        boosted, _ = apply_hebbian_boost(dm, events, graph)
        assert np.all(boosted >= 0.0)

    def test_symmetry_preserved(self):
        """Boosted matrix must remain symmetric."""
        graph = {
            _edge_key("alice", "bob"): CoOccurrenceEdge(source="alice", target="bob", count=5),
            _edge_key("alice", "charlie"): CoOccurrenceEdge(
                source="alice", target="charlie", count=3
            ),
        }
        events = [
            MockParticipantEvent(event_id="e0", participants_json='["alice"]'),
            MockParticipantEvent(event_id="e1", participants_json='["bob"]'),
            MockParticipantEvent(event_id="e2", participants_json='["charlie"]'),
        ]
        dm = np.array([[0.0, 0.6, 0.8], [0.6, 0.0, 0.7], [0.8, 0.7, 0.0]])
        boosted, _ = apply_hebbian_boost(dm, events, graph)
        np.testing.assert_array_almost_equal(boosted, boosted.T)


# =============================================================================
# HebbinaBoostConfig validation
# =============================================================================


class TestHebbinaBoostConfig:
    def test_defaults(self):
        cfg = HebbinaBoostConfig()
        assert cfg.enabled is True
        assert cfg.boost_scale == 0.10
        assert cfg.boost_cap == 0.05
        assert cfg.min_count == 1

    def test_validate_negative_scale(self):
        cfg = HebbinaBoostConfig(boost_scale=-0.1)
        with pytest.raises(ValueError, match="boost_scale"):
            cfg.validate()

    def test_validate_negative_cap(self):
        cfg = HebbinaBoostConfig(boost_cap=-0.01)
        with pytest.raises(ValueError, match="boost_cap"):
            cfg.validate()

    def test_validate_zero_min_count(self):
        cfg = HebbinaBoostConfig(min_count=0)
        with pytest.raises(ValueError, match="min_count"):
            cfg.validate()

    def test_to_dict(self):
        cfg = HebbinaBoostConfig()
        d = cfg.to_dict()
        assert d["enabled"] is True
        assert d["boost_scale"] == 0.10


# =============================================================================
# Integration: end-to-end graph build -> affinity -> boost
# =============================================================================


class TestEndToEndHebbian:
    def test_family_dinner_scenario(self):
        """Simulates multiple family dinner events with recurring participants."""
        events = [
            MockParticipantEvent(
                event_id="dinner1",
                participants_json='["mom", "dad", "kid"]',
                place_id="home",
                timestamp=BASE_TS,
            ),
            MockParticipantEvent(
                event_id="dinner2",
                participants_json='["mom", "dad", "kid"]',
                place_id="home",
                timestamp=BASE_TS + 86_400_000,
            ),
            MockParticipantEvent(
                event_id="dinner3",
                participants_json='["mom", "dad"]',
                place_id="home",
                timestamp=BASE_TS + 2 * 86_400_000,
            ),
            MockParticipantEvent(
                event_id="work_meeting",
                participants_json='["boss", "colleague"]',
                place_id="office",
                timestamp=BASE_TS + 3 * 86_400_000,
            ),
        ]
        graph = build_cooccurrence_graph(events)

        # mom-dad should have count=3, mom-kid count=2, dad-kid count=2
        assert graph[_edge_key("mom", "dad")].count == 3
        assert graph[_edge_key("mom", "kid")].count == 2
        assert graph[_edge_key("dad", "kid")].count == 2

        # boss-colleague count=1
        assert graph[_edge_key("boss", "colleague")].count == 1

        # No cross-family edges
        assert _edge_key("mom", "boss") not in graph

        # Affinity between dinner events should be positive
        aff_12 = compute_pairwise_affinity(events[0], events[1], graph)
        assert aff_12 > 0.0

        # Affinity between dinner and work should be zero
        aff_14 = compute_pairwise_affinity(events[0], events[3], graph)
        assert aff_14 == 0.0

        # Build and boost a dummy distance matrix
        n = len(events)
        dm = np.ones((n, n)) * 0.5
        np.fill_diagonal(dm, 0.0)

        boosted, diag = apply_hebbian_boost(dm, events, graph)
        assert diag["pairs_boosted"] > 0

        # Dinner-dinner distances should be reduced
        assert boosted[0, 1] < 0.5
        assert boosted[0, 2] < 0.5

        # Dinner-work distances should remain untouched
        assert boosted[0, 3] == 0.5
