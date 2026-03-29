"""
IntentSimilarityEnricher - GAP-007 Epic 3.3

Creates edges between entities with complementary intents.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from k0.modules.consolidation.algorithms.edge_enrichers.fusion import canonical_edge_key
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate

if TYPE_CHECKING:
    from k0.pipelines.p03.phases.r4_config import IntentSimilarityConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    relationship_type: Optional[str] = None


class IntentSimilarityEnricher:
    """Creates KG edges based on complementary intent relationships."""

    def __init__(self, config: Optional["IntentSimilarityConfig"]) -> None:
        self.config = config or IntentSimilarityConfig()

        # Define complementary intent mappings
        # These are intents that naturally pair together
        self.complementary_intents = {
            "seek_advice": ["express_feeling", "share_news", "reflect"],
            "express_feeling": ["seek_advice", "share_news", "log_memory"],
            "set_reminder": ["log_memory", "share_news"],
            "log_memory": ["set_reminder", "reflect", "share_news"],
            "query_memory": ["share_news", "log_memory"],
            "share_news": ["seek_advice", "express_feeling", "query_memory", "log_memory"],
            "reflect": ["log_memory", "express_feeling"],
            "other": [],  # No strong complements for generic category
        }

    async def enrich(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
        existing_edges: Mapping[object, object],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        """
        Create edges between entities with complementary intents.

        Args:
            entity_contexts: Entity ID -> list of observation contexts
            existing_edges: Existing edges (for updates vs new edges)

        Returns:
            Tuple of (new_edges, edge_updates)
        """
        if not self.config.enabled:
            return [], []

        # Build intent profiles for each entity
        intent_profiles = self._build_intent_profiles(entity_contexts)
        if not intent_profiles:
            return [], []

        # Normalize existing edges for lookup
        normalized_existing = self._normalize_existing_edges(existing_edges)

        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(intent_profiles.keys())
        for i, entity_a in enumerate(entity_ids):
            edges_for_entity = 0
            for entity_b in entity_ids[i + 1 :]:
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                profile_a = intent_profiles[entity_a]
                profile_b = intent_profiles[entity_b]

                if not profile_a or not profile_b:
                    continue

                complementarity_score = self._compute_intent_complementarity(profile_a, profile_b)

                if complementarity_score < self.config.similarity_threshold:
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
                            weight_delta=complementarity_score * 0.1,
                            confidence_delta=complementarity_score * 0.1,
                            source_algorithm="intent_similarity",
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
                            weight=complementarity_score,
                            confidence=complementarity_score,
                            source_algorithm="intent_similarity",
                            evidence_event_ids=evidence_event_ids,
                            observation_context=context,
                            properties_json=json.dumps(
                                {
                                    "complementarity_score": complementarity_score,
                                    "intent_profile_a": profile_a,
                                    "intent_profile_b": profile_b,
                                }
                            ),
                            algorithm_params_json=json.dumps(
                                {
                                    "similarity_threshold": self.config.similarity_threshold,
                                }
                            ),
                        )
                    )
                    edges_for_entity += 1

        logger.debug(
            f"IntentSimilarityEnricher: Created {len(new_edges)} new edges, "
            f"{len(updates)} updates from {len(entity_contexts)} entities"
        )
        return new_edges, updates

    def _build_intent_profiles(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
    ) -> Dict[str, Dict[str, float]]:
        """
        Build intent frequency profiles for each entity.

        Args:
            entity_contexts: Entity ID -> list of observation contexts

        Returns:
            Entity ID -> intent frequency dict (normalized to probabilities)
        """
        intent_profiles: Dict[str, Dict[str, float]] = {}

        for entity_id, contexts in entity_contexts.items():
            intent_counter: Counter[str] = Counter()

            for ctx in contexts:
                if ctx.intent_ultrabert:
                    intent_counter[ctx.intent_ultrabert] += 1

            if intent_counter:
                # Normalize to probabilities
                total_intents = sum(intent_counter.values())
                profile = {
                    intent: count / total_intents for intent, count in intent_counter.items()
                }
                intent_profiles[entity_id] = profile

        return intent_profiles

    def _compute_intent_complementarity(
        self,
        profile_a: Dict[str, float],
        profile_b: Dict[str, float],
    ) -> float:
        """
        Compute complementarity score between two intent profiles.

        Higher scores for complementary intent pairs rather than similar ones.

        Args:
            profile_a: Intent frequency dict for entity A
            profile_b: Intent frequency dict for entity B

        Returns:
            Complementarity score [0, 1]
        """
        total_complementarity = 0.0
        total_weight = 0.0

        # For each intent in profile A, check complementarity with profile B
        for intent_a, weight_a in profile_a.items():
            complements = self.complementary_intents.get(intent_a, [])

            # Check if any complementary intents are present in profile B
            complement_match = 0.0
            for complement in complements:
                if complement in profile_b:
                    complement_match += profile_b[complement]

            if complement_match > 0:
                # Weight by confidence in both intents
                intent_confidence = min(weight_a, complement_match)
                total_complementarity += intent_confidence
                total_weight += weight_a

        # Also check reverse direction (B's intents complementary to A)
        for intent_b, weight_b in profile_b.items():
            complements = self.complementary_intents.get(intent_b, [])

            complement_match = 0.0
            for complement in complements:
                if complement in profile_a:
                    complement_match += profile_a[complement]

            if complement_match > 0:
                intent_confidence = min(weight_b, complement_match)
                total_complementarity += intent_confidence
                total_weight += weight_b

        if total_weight == 0:
            return 0.0

        # Normalize by total intent weight
        return min(total_complementarity / total_weight, 1.0)

    def _normalize_existing_edges(
        self,
        existing_edges: Mapping[object, object],
    ) -> Dict[Tuple[str, str], "ExistingEdgeInfo"]:
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
                info = ExistingEdgeInfo(
                    edge_id=str(edge_id),
                    relationship_type=getattr(raw_value, "relationship_type", None),
                )

            normalized[pair] = info

        return normalized

    def _select_best_context(
        self,
        contexts: Sequence[ObservationContext],
    ) -> Optional[ObservationContext]:
        """Select the most representative context from a collection."""
        if not contexts:
            return None

        # Prefer contexts with higher intent confidence
        sorted_contexts = sorted(
            contexts,
            key=lambda ctx: ctx.intent_confidence or 0.0,
            reverse=True,
        )
        return sorted_contexts[0]

    def _context_event_ids(self, contexts: Sequence[ObservationContext]) -> List[str]:
        """Extract event IDs from contexts."""
        return [ctx.source_event_id for ctx in contexts if ctx.source_event_id]

    def _edge_id_for_pair(self, edge_key: Tuple[str, str]) -> str:
        """Generate deterministic edge ID for an entity pair."""
        import hashlib

        key_str = f"{edge_key[0]}:{edge_key[1]}:intent_similarity"
        return hashlib.md5(key_str.encode()).hexdigest()
