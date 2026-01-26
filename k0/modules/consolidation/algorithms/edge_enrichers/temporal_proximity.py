"""
TemporalProximityEnricher - GAP-007 Epic 3.2

Creates edges between entities that co-occur within a temporal window.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from k0.modules.consolidation.algorithms.edge_enrichers.fusion import canonical_edge_key
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate
from k0.pipelines.p03.phases.r4_config import TemporalProximityConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    relationship_type: Optional[str] = None


class TemporalProximityEnricher:
    """Creates KG edges for temporally co-occurring entities."""

    def __init__(self, config: Optional[TemporalProximityConfig]) -> None:
        self.config = config or TemporalProximityConfig()

    async def enrich(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
        existing_edges: Mapping[object, object],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        if not self.config.enabled:
            return [], []

        entity_observations = self._build_entity_observations(entity_contexts)
        if not entity_observations:
            return [], []

        normalized_existing = self._normalize_existing_edges(existing_edges)
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(entity_observations.keys())
        for i, entity_a in enumerate(entity_ids):
            edges_for_entity = 0
            for entity_b in entity_ids[i + 1 :]:
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                occurrences = self._collect_occurrences(
                    entity_observations[entity_a],
                    entity_observations[entity_b],
                )
                if not occurrences:
                    continue

                weight = self._calculate_weight(occurrences)
                if weight < self.config.min_weight:
                    continue

                edge_key = canonical_edge_key(entity_a, entity_b)
                evidence_event_ids = self._evidence_event_ids(occurrences)
                context = self._select_best_context(occurrences)

                existing = normalized_existing.get(edge_key)
                if existing:
                    updates.append(
                        KGEdgeUpdate(
                            edge_id=existing.edge_id,
                            weight_delta=weight * 0.1,
                            confidence_delta=weight * 0.1,
                            source_algorithm="temporal_proximity",
                            new_evidence_event_ids=evidence_event_ids,
                            observation_context=context,
                        )
                    )
                else:
                    edge_id = self._edge_id_for_pair(edge_key)
                    new_edges.append(
                        KGEdge(
                            edge_id=edge_id,
                            source_entity_id=edge_key[0],
                            target_entity_id=edge_key[1],
                            relationship_type=self.config.relation_type,
                            weight=weight,
                            confidence=min(1.0, len(occurrences) / 5),
                            source_algorithm="temporal_proximity",
                            evidence_event_ids=evidence_event_ids,
                            properties_json=json.dumps(
                                {
                                    "co_occurrence_count": len(occurrences),
                                    "window_ms": self.config.window_ms,
                                    "tau_ms": self.config.tau_ms,
                                }
                            ),
                            algorithm_params_json=json.dumps(
                                {
                                    "window_ms": self.config.window_ms,
                                    "tau_ms": self.config.tau_ms,
                                    "min_weight": self.config.min_weight,
                                }
                            ),
                            observation_context=context,
                        )
                    )
                    edges_for_entity += 1

        return new_edges, updates

    def _build_entity_observations(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
    ) -> Dict[str, List[Tuple[int, ObservationContext]]]:
        observations: Dict[str, List[Tuple[int, ObservationContext]]] = {}
        for entity_id, contexts in entity_contexts.items():
            pairs: List[Tuple[int, ObservationContext]] = []
            for ctx in contexts:
                observed_at = ctx.observed_at
                if observed_at:
                    pairs.append((observed_at, ctx))
            if pairs:
                observations[entity_id] = pairs
        return observations

    def _collect_occurrences(
        self,
        a_obs: Sequence[Tuple[int, ObservationContext]],
        b_obs: Sequence[Tuple[int, ObservationContext]],
    ) -> List[Tuple[int, int, ObservationContext, ObservationContext]]:
        occurrences: List[Tuple[int, int, ObservationContext, ObservationContext]] = []
        for ts_a, ctx_a in a_obs:
            for ts_b, ctx_b in b_obs:
                delta = abs(ts_a - ts_b)
                if delta <= self.config.window_ms:
                    occurrences.append((ts_a, ts_b, ctx_a, ctx_b))
        return occurrences

    def _calculate_weight(
        self,
        occurrences: Sequence[Tuple[int, int, ObservationContext, ObservationContext]],
    ) -> float:
        tau = self.config.tau_ms
        if tau <= 0:
            return 0.0

        raw_weight = sum(math.exp(-abs(ts_a - ts_b) / tau) for ts_a, ts_b, _, _ in occurrences)
        normalized = raw_weight / len(occurrences)
        return min(1.0, normalized)

    def _select_best_context(
        self,
        occurrences: Sequence[Tuple[int, int, ObservationContext, ObservationContext]],
    ) -> Optional[ObservationContext]:
        contexts: List[ObservationContext] = []
        for _, _, ctx_a, ctx_b in occurrences:
            contexts.append(ctx_a)
            contexts.append(ctx_b)
        if not contexts:
            return None
        return max(
            contexts,
            key=lambda ctx: ctx.salience_score if ctx.salience_score is not None else 0.0,
        )

    def _evidence_event_ids(
        self,
        occurrences: Sequence[Tuple[int, int, ObservationContext, ObservationContext]],
    ) -> List[str]:
        event_ids = set()
        for _, _, ctx_a, ctx_b in occurrences:
            if ctx_a.source_event_id:
                event_ids.add(ctx_a.source_event_id)
            if ctx_b.source_event_id:
                event_ids.add(ctx_b.source_event_id)
        return sorted(event_ids)

    def _edge_id_for_pair(self, pair: Tuple[str, str]) -> str:
        return f"edge_{pair[0]}_{pair[1]}"

    def _normalize_existing_edges(
        self,
        existing_edges: Mapping[object, object],
    ) -> Dict[Tuple[str, str], ExistingEdgeInfo]:
        normalized: Dict[Tuple[str, str], ExistingEdgeInfo] = {}

        for raw_key, raw_value in existing_edges.items():
            if isinstance(raw_key, tuple) and len(raw_key) == 2:
                pair = canonical_edge_key(str(raw_key[0]), str(raw_key[1]))
            elif isinstance(raw_key, str) and ":" in raw_key:
                left, right = raw_key.split(":", 1)
                pair = canonical_edge_key(left, right)
            else:
                continue

            if isinstance(raw_value, ExistingEdgeInfo):
                info = raw_value
            elif isinstance(raw_value, str):
                info = ExistingEdgeInfo(edge_id=raw_value)
            elif isinstance(raw_value, dict):
                edge_id = raw_value.get("edge_id") or raw_value.get("id")
                if not edge_id:
                    continue
                info = ExistingEdgeInfo(
                    edge_id=str(edge_id),
                    relationship_type=raw_value.get("relationship_type")
                    or raw_value.get("relation_type"),
                )
            else:
                edge_id = getattr(raw_value, "edge_id", None)
                if not edge_id:
                    continue
                info = ExistingEdgeInfo(edge_id=str(edge_id))

            normalized[pair] = info

        return normalized
