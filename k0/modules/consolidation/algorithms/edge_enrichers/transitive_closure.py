"""
TransitiveClosureEnricher - GAP-007 Epic 3.4

Infers new edges via short paths (2-hop) in the knowledge graph.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from k0.modules.consolidation.algorithms.edge_enrichers.fusion import canonical_edge_key
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate

if TYPE_CHECKING:
    from k0.pipelines.p03.phases.r4_config import TransitiveClosureConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    source_entity_id: str
    target_entity_id: str
    weight: float
    confidence: float
    relationship_type: Optional[str] = None


@dataclass
class PathAggregate:
    paths: List[List[str]]
    weights: List[float]
    confidences: List[float]


class TransitiveClosureEnricher:
    """Infer edges via 2-hop paths in the local KG subgraph."""

    def __init__(self, config: Optional["TransitiveClosureConfig"]) -> None:
        self.config = config or TransitiveClosureConfig()

    async def enrich(
        self,
        batch_entities: Sequence[str],
        existing_edges: Mapping[object, object],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        if not self.config.enabled:
            return [], []

        if not batch_entities:
            return [], []

        if self.config.max_hops < 2:
            return [], []

        normalized_edges = self._normalize_existing_edges(existing_edges, set(batch_entities))
        adjacency = self._build_adjacency(normalized_edges)

        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []
        created_keys: set[Tuple[str, str]] = set()
        aggregated_paths: Dict[Tuple[str, str], PathAggregate] = {}

        for entity_a in batch_entities:
            neighbors = adjacency.get(entity_a)
            if not neighbors:
                continue

            for neighbor, weight_ab, conf_ab, rel_ab in neighbors:
                neighbor_neighbors = adjacency.get(neighbor)
                if not neighbor_neighbors:
                    continue

                for entity_c, weight_bc, conf_bc, rel_bc in neighbor_neighbors:
                    if entity_c == entity_a:
                        continue

                    edge_key = canonical_edge_key(entity_a, entity_c)
                    if edge_key in normalized_edges:
                        continue

                    path_types = [rel_ab, rel_bc]
                    attenuation = self._path_attenuation(path_types)
                    inferred_weight = attenuation * min(weight_ab, weight_bc)
                    inferred_conf = attenuation * min(conf_ab, conf_bc)

                    if inferred_conf < self.config.min_confidence:
                        continue

                    entry = aggregated_paths.setdefault(
                        edge_key,
                        PathAggregate(paths=[], weights=[], confidences=[]),
                    )
                    entry.paths.append([entity_a, neighbor, entity_c])
                    entry.weights.append(inferred_weight)
                    entry.confidences.append(inferred_conf)

        for edge_key, data in aggregated_paths.items():
            if edge_key in created_keys:
                continue

            combined_confidence = self._combine_confidences(data.confidences)
            combined_weight = self._combine_weights(data.weights)

            if combined_confidence < self.config.min_confidence:
                continue

            inference_chain = {
                "paths": data.paths,
                "hop_count": 2,
                "attenuation": self.config.attenuation_factor,
                "path_count": len(data.paths),
                "combined_confidence": combined_confidence,
            }

            new_edges.append(
                KGEdge(
                    edge_id=self._edge_id_for_pair(edge_key),
                    source_entity_id=edge_key[0],
                    target_entity_id=edge_key[1],
                    relationship_type=self.config.relation_type,
                    weight=combined_weight,
                    confidence=combined_confidence,
                    source_algorithm="transitive_closure",
                    inference_chain_json=json.dumps(inference_chain),
                )
            )
            created_keys.add(edge_key)

        return new_edges, updates

    def _edge_id_for_pair(self, pair: Tuple[str, str]) -> str:
        return f"edge_{pair[0]}_{pair[1]}"

    def _build_adjacency(
        self,
        edges: Mapping[Tuple[str, str], ExistingEdgeInfo],
    ) -> Dict[str, List[Tuple[str, float, float, Optional[str]]]]:
        adjacency: Dict[str, List[Tuple[str, float, float, Optional[str]]]] = {}
        for info in edges.values():
            adjacency.setdefault(info.source_entity_id, []).append(
                (info.target_entity_id, info.weight, info.confidence, info.relationship_type)
            )
            adjacency.setdefault(info.target_entity_id, []).append(
                (info.source_entity_id, info.weight, info.confidence, info.relationship_type)
            )
        return adjacency

    def _normalize_existing_edges(
        self,
        existing_edges: Mapping[object, object],
        batch_set: set[str],
    ) -> Dict[Tuple[str, str], ExistingEdgeInfo]:
        normalized: Dict[Tuple[str, str], ExistingEdgeInfo] = {}

        for raw_key, raw_value in existing_edges.items():
            source_id: Optional[str] = None
            target_id: Optional[str] = None
            weight = 0.5
            confidence = 0.5
            edge_id: Optional[str] = None

            relationship_type: Optional[str] = None
            if isinstance(raw_value, dict):
                edge_id = raw_value.get("edge_id") or raw_value.get("id")
                source_id = raw_value.get("source_entity_id")
                target_id = raw_value.get("target_entity_id")
                relationship_type = raw_value.get("relationship_type") or raw_value.get(
                    "relation_type"
                )
                weight = float(
                    raw_value.get("edge_weight")
                    or raw_value.get("weight")
                    or raw_value.get("confidence_score")
                    or raw_value.get("confidence")
                    or 0.5
                )
                confidence = float(
                    raw_value.get("confidence_score") or raw_value.get("confidence") or weight
                )
            else:
                edge_id = getattr(raw_value, "edge_id", None)
                source_id = getattr(raw_value, "source_entity_id", None)
                target_id = getattr(raw_value, "target_entity_id", None)
                relationship_type = getattr(raw_value, "relationship_type", None) or getattr(
                    raw_value, "relation_type", None
                )
                weight = float(getattr(raw_value, "edge_weight", None) or 0.5)
                confidence = float(getattr(raw_value, "confidence_score", None) or weight)

            if not source_id or not target_id or not edge_id:
                if isinstance(raw_key, tuple) and len(raw_key) == 2:
                    source_id = str(raw_key[0])
                    target_id = str(raw_key[1])
                elif isinstance(raw_key, str) and ":" in raw_key:
                    source_id, target_id = raw_key.split(":", 1)

            if not source_id or not target_id or not edge_id:
                continue

            if batch_set and source_id not in batch_set and target_id not in batch_set:
                continue

            pair = canonical_edge_key(source_id, target_id)
            normalized[pair] = ExistingEdgeInfo(
                edge_id=edge_id,
                source_entity_id=source_id,
                target_entity_id=target_id,
                weight=weight,
                confidence=confidence,
                relationship_type=relationship_type,
            )

        return normalized

    def _path_attenuation(self, path_types: List[Optional[str]]) -> float:
        """Adjust attenuation based on relationship types in the path."""
        attenuation = self.config.attenuation_factor
        normalized = [t for t in path_types if t]

        if any(t in ("MANAGES", "PARENT", "FAMILY", "SPOUSE") for t in normalized):
            attenuation = max(attenuation, 0.9)
        elif any(t in ("FRIEND", "COLLEAGUE", "ACQUAINTANCE") for t in normalized):
            attenuation = min(attenuation, 0.7)

        return attenuation

    def _combine_confidences(self, confidences: List[float]) -> float:
        """Combine multiple path confidences (noisy-or)."""
        product = 1.0
        for conf in confidences:
            product *= 1.0 - max(0.0, min(1.0, conf))
        return 1.0 - product

    def _combine_weights(self, weights: List[float]) -> float:
        """Combine multiple path weights (mean)."""
        if not weights:
            return 0.0
        return min(1.0, sum(weights) / len(weights))
