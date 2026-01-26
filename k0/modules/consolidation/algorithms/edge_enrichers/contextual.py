"""
ContextualEdgeEnricher - GAP-007 Epic 3.3

Creates edges between entities that share contextual signals.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from k0.modules.consolidation.algorithms.edge_enrichers.fusion import canonical_edge_key
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate
from k0.pipelines.p03.phases.r4_config import ContextualEdgeConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    relationship_type: Optional[str] = None


class ContextualEdgeEnricher:
    """Creates KG edges based on shared context features."""

    def __init__(self, config: Optional[ContextualEdgeConfig]) -> None:
        self.config = config or ContextualEdgeConfig()
        self._weights = dict(self.config.context_weights or {})

    async def enrich(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
        existing_edges: Mapping[object, object],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        if not self.config.enabled:
            return [], []

        feature_map = self._build_feature_map(entity_contexts)
        if not feature_map:
            return [], []

        normalized_existing = self._normalize_existing_edges(existing_edges)
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(feature_map.keys())
        for i, entity_a in enumerate(entity_ids):
            edges_for_entity = 0
            for entity_b in entity_ids[i + 1 :]:
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                features_a = feature_map[entity_a]
                features_b = feature_map[entity_b]

                if not features_a or not features_b:
                    continue

                intersection = features_a & features_b
                union = features_a | features_b
                similarity = self._weighted_jaccard(intersection, union)

                if similarity < self.config.similarity_threshold:
                    continue

                edge_key = canonical_edge_key(entity_a, entity_b)
                context = self._select_best_context(
                    list(entity_contexts.get(entity_a, []))
                    + list(entity_contexts.get(entity_b, []))
                )
                evidence_event_ids = self._context_event_ids(
                    list(entity_contexts.get(entity_a, []))
                    + list(entity_contexts.get(entity_b, []))
                )

                existing = normalized_existing.get(edge_key)
                if existing:
                    updates.append(
                        KGEdgeUpdate(
                            edge_id=existing.edge_id,
                            weight_delta=similarity * 0.1,
                            confidence_delta=similarity * 0.1,
                            source_algorithm="contextual",
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
                            weight=similarity,
                            confidence=similarity,
                            source_algorithm="contextual",
                            evidence_event_ids=evidence_event_ids,
                            properties_json=json.dumps(
                                {
                                    "shared_features": sorted(intersection),
                                    "context_similarity": similarity,
                                }
                            ),
                            algorithm_params_json=json.dumps(
                                {
                                    "similarity_threshold": self.config.similarity_threshold,
                                    "weights": self._weights,
                                }
                            ),
                            observation_context=context,
                        )
                    )
                    edges_for_entity += 1

        return new_edges, updates

    def _build_feature_map(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
    ) -> Dict[str, set[str]]:
        feature_map: Dict[str, set[str]] = {}
        for entity_id, contexts in entity_contexts.items():
            features: set[str] = set()
            for ctx in contexts:
                if ctx.location_type:
                    features.add(f"location_type:{ctx.location_type}")
                if ctx.social_context:
                    features.add(f"social_context:{ctx.social_context}")
                if ctx.time_of_day_bucket:
                    features.add(f"time_of_day_bucket:{ctx.time_of_day_bucket}")
                if ctx.sentiment_label:
                    features.add(f"sentiment_label:{ctx.sentiment_label}")
                if ctx.ingress_channel:
                    features.add(f"ingress_channel:{ctx.ingress_channel}")
            if features:
                feature_map[entity_id] = features
        return feature_map

    def _weighted_jaccard(self, intersection: set[str], union: set[str]) -> float:
        if not union:
            return 0.0

        def weight(feature: str) -> float:
            prefix = feature.split(":", 1)[0]
            return float(self._weights.get(prefix, 1.0))

        intersection_weight = sum(weight(f) for f in intersection)
        union_weight = sum(weight(f) for f in union)
        if union_weight <= 0:
            return 0.0
        return intersection_weight / union_weight

    def _select_best_context(
        self,
        contexts: Sequence[ObservationContext],
    ) -> Optional[ObservationContext]:
        if not contexts:
            return None
        return max(
            contexts,
            key=lambda ctx: ctx.salience_score if ctx.salience_score is not None else 0.0,
        )

    def _context_event_ids(
        self,
        contexts: Sequence[ObservationContext],
    ) -> List[str]:
        event_ids = {ctx.source_event_id for ctx in contexts if ctx.source_event_id}
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
