"""
EdgeWeightNormalizer - GAP-007 Epic 3.6

Normalizes edge weights to prevent hub dominance and keep weights in stable ranges.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Dict, List, Tuple

from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate
from k0.pipelines.p03.phases.r4_config import WeightNormalizationConfig

logger = logging.getLogger(__name__)


class EdgeWeightNormalizer:
    """Normalizes edge weights to prevent hub dominance."""

    def __init__(self, config: WeightNormalizationConfig) -> None:
        self.config = config

    def normalize(
        self,
        new_edges: List[KGEdge],
        updates: List[KGEdgeUpdate],
        existing_edges: Dict[str, List[KGEdge]],
    ) -> List[KGEdgeUpdate]:
        """
        Apply normalization to edges.

        Args:
            new_edges: New edges to be created in this cycle
            updates: Edge updates from enrichment algorithms
            existing_edges: Existing edges grouped by source entity ID

        Returns:
            List of normalization updates to apply
        """
        if not self.config.enabled:
            return []

        normalization_updates: List[KGEdgeUpdate] = []

        # Group all edges by source entity
        entity_edges: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

        # Add existing edges
        for entity_id, edges in existing_edges.items():
            for edge in edges:
                weight = getattr(edge, "weight", None) or getattr(edge, "edge_weight", 1.0)
                entity_edges[entity_id].append((edge.edge_id, float(weight)))

        # Add new edges
        for edge in new_edges:
            weight = getattr(edge, "weight", None) or getattr(edge, "edge_weight", 1.0)
            entity_edges[edge.source_entity_id].append((edge.edge_id, float(weight)))

        # Apply pending updates to get current weights
        edge_id_to_weight: Dict[str, float] = {}
        for entity_id, edges_list in entity_edges.items():
            for edge_id, weight in edges_list:
                edge_id_to_weight[edge_id] = weight

        for update in updates:
            if update.edge_id in edge_id_to_weight:
                current_weight = edge_id_to_weight[update.edge_id]
                if hasattr(update, "weight_delta") and update.weight_delta is not None:
                    edge_id_to_weight[update.edge_id] = current_weight + update.weight_delta
                elif hasattr(update, "new_weight") and update.new_weight is not None:
                    edge_id_to_weight[update.edge_id] = update.new_weight

        # Rebuild entity_edges with updated weights
        entity_edges = defaultdict(list)
        for entity_id, edges_list in list(existing_edges.items()) if existing_edges else []:
            for edge in edges_list:
                if edge.edge_id in edge_id_to_weight:
                    entity_edges[entity_id].append((edge.edge_id, edge_id_to_weight[edge.edge_id]))

        for edge in new_edges:
            if edge.edge_id in edge_id_to_weight:
                entity_edges[edge.source_entity_id].append(
                    (edge.edge_id, edge_id_to_weight[edge.edge_id])
                )

        # Normalize per entity
        for entity_id, edges_list in entity_edges.items():
            if len(edges_list) <= 1:
                continue

            weights = [w for _, w in edges_list]
            total_weight = sum(weights)

            if total_weight == 0:
                continue

            if self.config.strategy == "sum_to_one":
                for edge_id, old_weight in edges_list:
                    new_weight = old_weight / total_weight
                    if abs(new_weight - old_weight) > 0.001:
                        normalization_updates.append(
                            KGEdgeUpdate(
                                edge_id=edge_id,
                                new_weight=new_weight,
                                source_algorithm="weight_normalization",
                            )
                        )

            elif self.config.strategy == "cap":
                for edge_id, old_weight in edges_list:
                    if old_weight > self.config.max_weight:
                        normalization_updates.append(
                            KGEdgeUpdate(
                                edge_id=edge_id,
                                new_weight=self.config.max_weight,
                                source_algorithm="weight_normalization",
                            )
                        )
                    elif old_weight < self.config.min_weight:
                        normalization_updates.append(
                            KGEdgeUpdate(
                                edge_id=edge_id,
                                new_weight=self.config.min_weight,
                                source_algorithm="weight_normalization",
                            )
                        )

            elif self.config.strategy == "softmax":
                try:
                    exp_weights = [math.exp(min(w, 700)) for w in weights]  # Prevent overflow
                    exp_sum = sum(exp_weights)
                    if exp_sum > 0:
                        for (edge_id, _), exp_w in zip(edges_list, exp_weights):
                            new_weight = exp_w / exp_sum
                            normalization_updates.append(
                                KGEdgeUpdate(
                                    edge_id=edge_id,
                                    new_weight=new_weight,
                                    source_algorithm="weight_normalization",
                                )
                            )
                except OverflowError:
                    logger.warning(
                        "EdgeWeightNormalizer: softmax overflow for entity %s", entity_id
                    )
                    continue

        return normalization_updates
