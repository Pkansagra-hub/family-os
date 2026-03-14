"""
KG Relationship Boost -- KG edge weights feed back to R1 importance scoring.

ADR-K026: Events mentioning entities with strong KG relationships receive
a multiplicative boost in importance scoring. This closes the feedback loop
between Hebbian learning (R4) and importance scoring (R1).

Design (ADR-K026):
    relationship_boost = 1.0 + boost_scale * max_edge_weight
    - boost_scale: 0.15 (configurable)
    - max_edge_weight: highest edge weight among entity pairs in the event
    - Result range: [1.0, max_boost_cap + 1.0]
    - When disabled or no KG data: 1.0 (multiplicative identity)

Entity extraction:
    Parses event.ner_entities_json to extract entity IDs.
    Forms all pair combinations for edge lookup.

Edge lookup:
    Batch-loads all active edges for the space once per cycle via
    kg_edges_query syscall. Per-event lookup is O(1) dict access.

References:
    - ADR-K026: KG Relationship Boost for R1 Importance Scoring
    - Plan: PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md Epic 5.F.1
    - CONFIG_B formula: importance_scorer.py
    - KG edges: syscalls.kg_edges_query()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class KGBoostConfig:
    """
    Configuration for KG relationship boost in R1 importance scoring.

    Attributes:
        enabled: Master switch. When False, boost is always 1.0.
        boost_scale: Multiplier applied to max_edge_weight.
            boost = 1.0 + boost_scale * max_edge_weight.
            Default 0.15 means max edge_weight=1.0 gives 1.15x boost.
        max_boost_cap: Hard cap on boost value above 1.0.
            Prevents runaway even if boost_scale is misconfigured.
            Final boost <= 1.0 + max_boost_cap.
        min_edge_weight: Minimum edge weight to consider for boost.
            Edges below this threshold are ignored (noise filter).
        edge_types_included: Optional filter for which edge types
            contribute to boost. None means all types.
    """

    enabled: bool = False
    boost_scale: float = 0.15
    max_boost_cap: float = 0.20
    min_edge_weight: float = 0.05
    edge_types_included: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Edge Cache Protocol
# ---------------------------------------------------------------------------


class KGEdgeCacheProtocol(Protocol):
    """Protocol for KG edge weight lookup."""

    async def load_edges(
        self,
        tenant_id: str,
        space_id: str,
    ) -> None:
        """Load all active edges for a space into cache."""
        ...

    def get_edge_weight(
        self,
        entity_a: str,
        entity_b: str,
    ) -> Optional[float]:
        """Look up edge weight for an entity pair. Returns None if no edge."""
        ...


# ---------------------------------------------------------------------------
# Edge Cache Implementation
# ---------------------------------------------------------------------------


@dataclass
class KGEdgeCache:
    """
    In-memory cache of KG edge weights for a single P03 cycle.

    Loaded once per cycle via kg_edges_query syscall, then used for
    O(1) per-event lookups. Discarded at end of cycle.

    The cache keys edges by sorted (source_id, target_id) pairs
    to handle bidirectional lookup.
    """

    _edges: Dict[str, float] = field(default_factory=dict)
    _loaded: bool = False
    _edge_count: int = 0

    async def load_edges(
        self,
        tenant_id: str,
        space_id: str,
        syscalls: Any = None,
        relationship_types: Optional[List[str]] = None,
    ) -> None:
        """
        Load all active edges for a space into cache.

        Uses kg_edges_query syscall to batch-fetch all edges.
        Each edge is keyed by sorted entity pair for bidirectional lookup.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            syscalls: Syscalls instance with kg_edges_query
            relationship_types: Optional filter by edge types
        """
        if syscalls is None:
            logger.warning(
                "KGEdgeCache.load_edges called without syscalls, cache empty",
                extra={"tenant_id": tenant_id, "space_id": space_id},
            )
            self._loaded = True
            return

        try:
            result = await syscalls.kg_edges_query(
                tenant_id=tenant_id,
                space_id=space_id,
                limit=10000,
                relationship_types=relationship_types,
            )
            edges_list = result.get("edges", [])
            for edge in edges_list:
                source = edge.get("source_entity_id", "")
                target = edge.get("target_entity_id", "")
                weight = edge.get("weight", 0.0)
                if source and target and weight > 0:
                    key = _make_pair_key(source, target)
                    # Keep the highest weight if multiple edges between same pair
                    if key not in self._edges or weight > self._edges[key]:
                        self._edges[key] = weight

            self._edge_count = len(self._edges)
            self._loaded = True

            logger.debug(
                "KG edge cache loaded",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "edge_count": self._edge_count,
                    "raw_edges": len(edges_list),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to load KG edges, boost will be 1.0",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                },
            )
            self._loaded = True  # Mark loaded to prevent retry

    def get_edge_weight(
        self,
        entity_a: str,
        entity_b: str,
    ) -> Optional[float]:
        """
        Look up edge weight for an entity pair.

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID

        Returns:
            Edge weight [0, 1] or None if no edge exists
        """
        key = _make_pair_key(entity_a, entity_b)
        return self._edges.get(key)

    @property
    def loaded(self) -> bool:
        """Whether the cache has been loaded."""
        return self._loaded

    @property
    def edge_count(self) -> int:
        """Number of unique entity pairs in cache."""
        return self._edge_count


# ---------------------------------------------------------------------------
# Entity Extraction
# ---------------------------------------------------------------------------


def extract_entity_ids(ner_entities_json: str) -> List[str]:
    """
    Extract unique entity IDs from NER entities JSON.

    The ner_entities_json field contains a JSON array of entity objects.
    Each entity has at minimum an 'entity_id' or 'canonical_name' field.
    We extract unique identifiers for pair formation.

    Supported formats:
        - [{"entity_id": "e1", ...}, ...]  (preferred)
        - [{"canonical_name": "Mom", ...}, ...]  (fallback)
        - [{"text": "Mom", "label": "PERSON"}, ...]  (NER output)

    Args:
        ner_entities_json: JSON string of entity array

    Returns:
        List of unique entity identifiers (deduped, order preserved)
    """
    if not ner_entities_json or ner_entities_json == "[]":
        return []

    try:
        entities = json.loads(ner_entities_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(entities, list):
        return []

    seen: set[str] = set()
    ids: List[str] = []

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        # Priority: entity_id > canonical_name > text
        eid = ent.get("entity_id") or ent.get("canonical_name") or ent.get("text") or ""
        eid = str(eid).strip()
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    return ids


def extract_entity_pairs(entity_ids: List[str]) -> List[Tuple[str, str]]:
    """
    Form all unique entity pairs from a list of entity IDs.

    Args:
        entity_ids: List of entity identifiers

    Returns:
        List of (entity_a, entity_b) pairs (sorted for canonical ordering)
    """
    if len(entity_ids) < 2:
        return []
    return [
        tuple(sorted(pair)) for pair in combinations(entity_ids, 2)  # type: ignore[return-value]
    ]


# ---------------------------------------------------------------------------
# Boost Computation
# ---------------------------------------------------------------------------


def compute_relationship_boost(
    entity_ids: List[str],
    edge_cache: KGEdgeCache,
    config: KGBoostConfig,
) -> Tuple[float, float]:
    """
    Compute the relationship boost for an event given its entities.

    ADR-K026: boost = 1.0 + boost_scale * max_edge_weight

    Args:
        entity_ids: Entity IDs extracted from the event
        edge_cache: Loaded KG edge cache for the space
        config: Boost configuration

    Returns:
        Tuple of (boost_value, max_edge_weight_found)
        - boost_value: [1.0, 1.0 + max_boost_cap]
        - max_edge_weight_found: raw max edge weight (for audit)
    """
    if not config.enabled:
        return 1.0, 0.0

    if len(entity_ids) < 2:
        return 1.0, 0.0

    max_weight = 0.0
    pairs = extract_entity_pairs(entity_ids)

    for entity_a, entity_b in pairs:
        weight = edge_cache.get_edge_weight(entity_a, entity_b)
        if weight is not None and weight > config.min_edge_weight:
            max_weight = max(max_weight, weight)

    if max_weight <= 0:
        return 1.0, 0.0

    raw_boost = config.boost_scale * max_weight
    capped_boost = min(raw_boost, config.max_boost_cap)
    return 1.0 + capped_boost, max_weight


# ---------------------------------------------------------------------------
# Runaway Detection (5.F.2.3)
# ---------------------------------------------------------------------------


@dataclass
class RunawayDetectionConfig:
    """
    Configuration for edge weight velocity monitoring.

    Attributes:
        velocity_threshold: Max allowed weight increase per cycle.
            Alert if any edge weight increases more than this.
            Default 0.1 per cycle (from plan spec).
        window_size: Number of cycles to track velocity over.
        enabled: Master switch for velocity monitoring.
    """

    velocity_threshold: float = 0.1
    window_size: int = 5
    enabled: bool = True


@dataclass
class EdgeVelocityRecord:
    """Tracks weight change for a single entity pair across cycles."""

    pair_key: str
    previous_weight: float
    current_weight: float
    delta: float
    cycle_number: int


class EdgeWeightVelocityMonitor:
    """
    Monitors edge weight velocity (rate of change) across P03 cycles.

    Detects potential runaway reinforcement by tracking how fast
    edge weights increase. Emits alerts when velocity exceeds threshold.

    5.F.2.3: Alert if any edge weight increases > threshold per cycle.
    """

    def __init__(self, config: Optional[RunawayDetectionConfig] = None) -> None:
        self._config = config or RunawayDetectionConfig()
        # pair_key -> list of (cycle_number, weight) snapshots
        self._history: Dict[str, List[Tuple[int, float]]] = {}
        self._alerts: List[EdgeVelocityRecord] = []
        self._current_cycle: int = 0

    def record_cycle(self, edge_cache: KGEdgeCache, cycle_number: int) -> List[EdgeVelocityRecord]:
        """
        Record edge weights for a cycle and check for runaway.

        Args:
            edge_cache: Current cycle edge cache
            cycle_number: Monotonic cycle counter

        Returns:
            List of velocity alerts (empty if none)
        """
        if not self._config.enabled:
            return []

        self._current_cycle = cycle_number
        alerts: List[EdgeVelocityRecord] = []

        for pair_key, weight in edge_cache._edges.items():
            if pair_key in self._history:
                history = self._history[pair_key]
                if history:
                    prev_cycle, prev_weight = history[-1]
                    delta = weight - prev_weight
                    if delta > self._config.velocity_threshold:
                        record = EdgeVelocityRecord(
                            pair_key=pair_key,
                            previous_weight=prev_weight,
                            current_weight=weight,
                            delta=delta,
                            cycle_number=cycle_number,
                        )
                        alerts.append(record)
                        self._alerts.append(record)
                        logger.warning(
                            "Runaway detected: edge %s velocity %.4f exceeds threshold %.4f",
                            pair_key,
                            delta,
                            self._config.velocity_threshold,
                            extra={
                                "pair_key": pair_key,
                                "delta": delta,
                                "threshold": self._config.velocity_threshold,
                                "cycle": cycle_number,
                            },
                        )

            # Update history (keep window_size entries)
            if pair_key not in self._history:
                self._history[pair_key] = []
            self._history[pair_key].append((cycle_number, weight))
            if len(self._history[pair_key]) > self._config.window_size:
                self._history[pair_key] = self._history[pair_key][-self._config.window_size :]

        return alerts

    @property
    def total_alerts(self) -> int:
        """Total number of velocity alerts across all cycles."""
        return len(self._alerts)

    @property
    def all_alerts(self) -> List[EdgeVelocityRecord]:
        """All velocity alert records."""
        return list(self._alerts)

    def get_velocity(self, pair_key: str) -> Optional[float]:
        """Get most recent velocity for a pair (or None)."""
        history = self._history.get(pair_key, [])
        if len(history) < 2:
            return None
        _, w_prev = history[-2]
        _, w_curr = history[-1]
        return w_curr - w_prev


# ---------------------------------------------------------------------------
# Emergency Brake: Weight Reset (5.F.2.4)
# ---------------------------------------------------------------------------


@dataclass
class WeightResetResult:
    """Result of an emergency weight reset operation."""

    edges_reset: int
    previous_weights: Dict[str, float]
    reset_to: float
    reason: str


def emergency_weight_reset(
    edge_cache: KGEdgeCache,
    reset_value: float = 0.1,
    reason: str = "manual_reset",
) -> WeightResetResult:
    """
    Emergency brake: reset all edge weights in cache to initial value.

    Used when runaway reinforcement is detected and the feedback loop
    must be broken immediately. Resets all cached weights to a safe
    baseline value.

    This operates on the in-memory cache. The caller is responsible
    for persisting the reset to the database (via syscalls).

    Args:
        edge_cache: Edge cache to reset
        reset_value: Value to reset all weights to (default 0.1)
        reason: Audit reason for the reset

    Returns:
        WeightResetResult with details of the operation
    """
    previous = dict(edge_cache._edges)
    count = len(previous)

    for pair_key in edge_cache._edges:
        edge_cache._edges[pair_key] = reset_value

    logger.warning(
        "Emergency weight reset: %d edges reset to %.4f (reason: %s)",
        count,
        reset_value,
        reason,
        extra={
            "edges_reset": count,
            "reset_value": reset_value,
            "reason": reason,
        },
    )

    return WeightResetResult(
        edges_reset=count,
        previous_weights=previous,
        reset_to=reset_value,
        reason=reason,
    )


def selective_weight_reset(
    edge_cache: KGEdgeCache,
    pair_keys: List[str],
    reset_value: float = 0.1,
    reason: str = "selective_reset",
) -> WeightResetResult:
    """
    Reset specific edge weights identified as runaway.

    Less aggressive than full emergency_weight_reset: only resets
    the edges that triggered velocity alerts.

    Args:
        edge_cache: Edge cache to modify
        pair_keys: Specific pair keys to reset
        reset_value: Value to reset to
        reason: Audit reason

    Returns:
        WeightResetResult with details
    """
    previous: Dict[str, float] = {}
    count = 0

    for key in pair_keys:
        if key in edge_cache._edges:
            previous[key] = edge_cache._edges[key]
            edge_cache._edges[key] = reset_value
            count += 1

    logger.warning(
        "Selective weight reset: %d edges reset to %.4f (reason: %s)",
        count,
        reset_value,
        reason,
        extra={
            "edges_reset": count,
            "reset_value": reset_value,
            "reason": reason,
            "pair_keys": pair_keys,
        },
    )

    return WeightResetResult(
        edges_reset=count,
        previous_weights=previous,
        reset_to=reset_value,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pair_key(entity_a: str, entity_b: str) -> str:
    """Create canonical key for entity pair (sorted for bidirectional lookup)."""
    a, b = sorted([entity_a, entity_b])
    return f"{a}:{b}"
