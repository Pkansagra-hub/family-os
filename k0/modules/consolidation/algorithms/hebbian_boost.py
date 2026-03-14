"""
HebbinaBoost -- Hebbian co-occurrence distance boost for episodic clustering.

Applies a multiplicative distance reduction between events whose participants
frequently co-occur. Built from batch events (not from st_kg_edges).

Research Reference:
    - poc/r2_phase_research/m5_rsch01_02_hebbian_boost.py
    - R2_RESEARCH_FINAL.md Section 12.3 (RSCH-01+02)
    - R2_EPISODIC_INTEGRATION_EPIC_PLAN.md Epic 5.1

Proven formula:
    affinity = max(edge.weight for all participant-pair co-occurrences)
    where edge.weight = 1.0 - exp(-0.1 * count)
    boost = min(affinity * boost_scale, boost_cap)
    d_hebbian = d_ensemble * (1.0 - boost)

Production parameters (research-validated on 1360 events, 8/8 scenarios):
    boost_scale = 0.10
    boost_cap   = 0.05   (max 5% distance reduction)
    min_count   = 1
    use_recency = False

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class HebbinaBoostConfig:
    """Configuration for Hebbian co-occurrence distance boost.

    Research-validated defaults from M5-RSCH-01+02:
        boost_scale=0.10, boost_cap=0.05, min_count=1

    All scales >= 0.10 achieve 8/8 scenarios.
    All thresholds (1-20) achieve 8/8.
    Conservative cap of 0.05 bounds max distance reduction to 5%.
    """

    enabled: bool = True
    boost_scale: float = 0.10
    boost_cap: float = 0.05
    min_count: int = 1

    def validate(self) -> None:
        if self.boost_scale < 0.0:
            raise ValueError(f"boost_scale must be >= 0, got {self.boost_scale}")
        if self.boost_cap < 0.0:
            raise ValueError(f"boost_cap must be >= 0, got {self.boost_cap}")
        if self.min_count < 1:
            raise ValueError(f"min_count must be >= 1, got {self.min_count}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "boost_scale": self.boost_scale,
            "boost_cap": self.boost_cap,
            "min_count": self.min_count,
        }


# =============================================================================
# Co-occurrence graph
# =============================================================================


@dataclass
class CoOccurrenceEdge:
    """A single co-occurrence edge between two participant entities."""

    source: str
    target: str
    count: int = 0

    @property
    def weight(self) -> float:
        """Saturating weight: 1.0 - exp(-0.1 * count).

        Approaches 1.0 asymptotically. At count=1: 0.095, count=10: 0.632,
        count=50: 0.993. Matches POC CoEdge.weight formula.
        """
        if self.count <= 0:
            return 0.0
        return 1.0 - math.exp(-0.1 * self.count)


def _edge_key(a: str, b: str) -> Tuple[str, str]:
    """Canonical key: sorted pair so (a,b) == (b,a)."""
    return (min(a, b), max(a, b))


class _ParticipantSource(Protocol):
    """Minimal protocol for events that carry participant data."""

    @property
    def event_id(self) -> str: ...

    @property
    def participants_json(self) -> Optional[str]: ...

    @property
    def place_id(self) -> Optional[str]: ...


def _parse_participants(participants_json: Optional[str]) -> List[str]:
    """Parse participants JSON into sorted list of participant IDs."""
    if not participants_json:
        return []
    try:
        parsed = json.loads(participants_json)
        if isinstance(parsed, list):
            return sorted(str(p) for p in parsed if p)
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def build_cooccurrence_graph(
    events: Sequence[_ParticipantSource],
) -> Dict[Tuple[str, str], CoOccurrenceEdge]:
    """Build co-occurrence graph from batch events.

    Extracts participant pairs from each event and counts how many events
    each pair appears together in. Also counts actor-location co-occurrences.

    This mirrors the POC build_cooccurrence_graph() but works on production
    EventAdapter objects (which expose participants_json and place_id).

    Args:
        events: Sequence of events with participants_json and place_id.

    Returns:
        Dict mapping (entity_a, entity_b) -> CoOccurrenceEdge with count.
    """
    graph: Dict[Tuple[str, str], CoOccurrenceEdge] = {}

    for event in events:
        participants = _parse_participants(event.participants_json)
        if not participants:
            continue

        # Actor-Actor co-occurrences (combinations, not permutations)
        for i, actor_a in enumerate(participants):
            for actor_b in participants[i + 1 :]:
                key = _edge_key(actor_a, actor_b)
                if key not in graph:
                    graph[key] = CoOccurrenceEdge(source=key[0], target=key[1])
                graph[key].count += 1

        # Actor-Location co-occurrences
        place = event.place_id
        if place:
            for actor in participants:
                key = _edge_key(actor, f"loc:{place}")
                if key not in graph:
                    graph[key] = CoOccurrenceEdge(source=key[0], target=key[1])
                graph[key].count += 1

    return graph


# =============================================================================
# Affinity computation
# =============================================================================


def compute_pairwise_affinity(
    event_a: _ParticipantSource,
    event_b: _ParticipantSource,
    graph: Dict[Tuple[str, str], CoOccurrenceEdge],
    min_count: int = 1,
) -> float:
    """Compute Hebbian affinity in [0, 1] between two events.

    Takes the max co-occurrence weight across all participant pairs
    shared between the two events.

    Args:
        event_a: First event.
        event_b: Second event.
        graph: Co-occurrence graph from build_cooccurrence_graph().
        min_count: Minimum co-occurrence count for an edge to contribute.

    Returns:
        Affinity in [0.0, 1.0]. 0.0 if no shared participant pairs.
    """
    parts_a = _parse_participants(event_a.participants_json)
    parts_b = _parse_participants(event_b.participants_json)

    if not parts_a or not parts_b:
        return 0.0

    max_weight = 0.0

    # Check all actor-actor pair combinations between events
    for pa in parts_a:
        for pb in parts_b:
            if pa == pb:
                continue
            key = _edge_key(pa, pb)
            edge = graph.get(key)
            if edge and edge.count >= min_count:
                max_weight = max(max_weight, edge.weight)

    # Check actor-location co-occurrences (half-weighted like POC)
    place_a = event_a.place_id
    place_b = event_b.place_id
    if place_a and place_b and place_a == place_b:
        for pa in parts_a:
            key = _edge_key(pa, f"loc:{place_a}")
            edge = graph.get(key)
            if edge and edge.count >= min_count:
                max_weight = max(max_weight, edge.weight * 0.5)

    return max_weight


# =============================================================================
# Distance matrix modifier
# =============================================================================


def apply_hebbian_boost(
    distance_matrix: np.ndarray,
    events: Sequence[_ParticipantSource],
    graph: Dict[Tuple[str, str], CoOccurrenceEdge],
    config: Optional[HebbinaBoostConfig] = None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Apply Hebbian proximity boost to a precomputed distance matrix.

    Modifies distances in-place: d_hebbian = d * (1 - min(affinity * scale, cap)).
    Returns a copy; the input matrix is not mutated.

    Args:
        distance_matrix: NxN symmetric distance matrix from EnsembleDistance.
        events: Events in the same order as the distance matrix.
        graph: Co-occurrence graph from build_cooccurrence_graph().
        config: Boost configuration. Uses research defaults if None.

    Returns:
        Tuple of (boosted distance matrix, diagnostics dict).
    """
    cfg = config or HebbinaBoostConfig()

    n = len(events)
    diagnostics: Dict[str, Any] = {
        "pairs_boosted": 0,
        "total_pairs": n * (n - 1) // 2,
        "graph_edges": len(graph),
        "max_boost_applied": 0.0,
        "config": cfg.to_dict(),
    }

    if not cfg.enabled or n < 2 or not graph:
        return distance_matrix, diagnostics

    boosted = distance_matrix.copy()

    for i in range(n):
        for j in range(i + 1, n):
            affinity = compute_pairwise_affinity(
                events[i], events[j], graph, min_count=cfg.min_count
            )
            if affinity > 0.0:
                boost = min(affinity * cfg.boost_scale, cfg.boost_cap)
                boosted[i, j] = max(0.0, boosted[i, j] * (1.0 - boost))
                boosted[j, i] = boosted[i, j]
                diagnostics["pairs_boosted"] += 1
                diagnostics["max_boost_applied"] = max(diagnostics["max_boost_applied"], boost)

    if diagnostics["pairs_boosted"] > 0:
        logger.info(
            "Hebbian boost applied",
            extra={
                "pairs_boosted": diagnostics["pairs_boosted"],
                "total_pairs": diagnostics["total_pairs"],
                "graph_edges": diagnostics["graph_edges"],
                "max_boost": round(diagnostics["max_boost_applied"], 4),
            },
        )

    return boosted, diagnostics
