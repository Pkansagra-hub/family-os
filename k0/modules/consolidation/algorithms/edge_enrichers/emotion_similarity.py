"""
EmotionSimilarityEnricher - GAP-007 Epic 3.3

Creates edges between entities that share similar emotional profiles.
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
    from k0.pipelines.p03.phases.r4_config import EmotionSimilarityConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    relationship_type: Optional[str] = None


class EmotionSimilarityEnricher:
    """Creates KG edges based on emotional similarity between entities."""

    def __init__(self, config: Optional["EmotionSimilarityConfig"]) -> None:
        self.config = config or EmotionSimilarityConfig()

    async def enrich(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
        existing_edges: Mapping[object, object],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        if not self.config.enabled:
            return [], []

        emotion_vectors = self._build_emotion_vectors(entity_contexts)
        if not emotion_vectors:
            return [], []

        normalized_existing = self._normalize_existing_edges(existing_edges)
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(emotion_vectors.keys())
        for i, entity_a in enumerate(entity_ids):
            edges_for_entity = 0
            for entity_b in entity_ids[i + 1 :]:
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                vector_a = emotion_vectors[entity_a]
                vector_b = emotion_vectors[entity_b]

                if not vector_a or not vector_b:
                    continue

                similarity = self._compute_emotion_similarity(vector_a, vector_b)

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
                            source_algorithm="emotion_similarity",
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
                            source_algorithm="emotion_similarity",
                            evidence_event_ids=evidence_event_ids,
                            properties_json=json.dumps(
                                {
                                    "emotion_similarity": similarity,
                                    "shared_emotions": self._shared_emotions(vector_a, vector_b),
                                }
                            ),
                            algorithm_params_json=json.dumps(
                                {
                                    "similarity_threshold": self.config.similarity_threshold,
                                    "arousal_weight": self.config.arousal_weight,
                                }
                            ),
                            observation_context=context,
                        )
                    )
                    edges_for_entity += 1

        return new_edges, updates

    def _build_emotion_vectors(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
    ) -> Dict[str, Dict[str, float]]:
        """Build emotion vectors for each entity from their observation contexts."""
        emotion_vectors: Dict[str, Dict[str, float]] = {}

        for entity_id, contexts in entity_contexts.items():
            emotion_counter: Counter[str] = Counter()
            total_arousal = 0.0
            context_count = 0

            for ctx in contexts:
                if ctx.dominant_emotions_json:
                    try:
                        emotions = json.loads(ctx.dominant_emotions_json)
                        if isinstance(emotions, list):
                            emotion_counter.update(emotions)
                            context_count += 1
                            if ctx.affect_arousal is not None:
                                total_arousal += ctx.affect_arousal
                    except (json.JSONDecodeError, TypeError):
                        continue

            if emotion_counter:
                # Normalize emotion frequencies to probabilities
                total_emotions = sum(emotion_counter.values())
                vector = {
                    emotion: count / total_emotions for emotion, count in emotion_counter.items()
                }

                # Add arousal intensity as a weighted feature
                avg_arousal = total_arousal / context_count if context_count > 0 else 0.0
                vector["_arousal_intensity"] = avg_arousal * self.config.arousal_weight

                emotion_vectors[entity_id] = vector

        return emotion_vectors

    def _compute_emotion_similarity(
        self,
        vector_a: Dict[str, float],
        vector_b: Dict[str, float],
    ) -> float:
        """Compute cosine similarity between two emotion vectors."""
        # Get all unique emotions across both vectors
        all_emotions = set(vector_a.keys()) | set(vector_b.keys())

        # Create aligned vectors
        vec_a = [vector_a.get(emotion, 0.0) for emotion in all_emotions]
        vec_b = [vector_b.get(emotion, 0.0) for emotion in all_emotions]

        # Compute cosine similarity
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def _shared_emotions(
        self,
        vector_a: Dict[str, float],
        vector_b: Dict[str, float],
    ) -> List[str]:
        """Return list of emotions present in both vectors (excluding special keys)."""
        shared = []
        for emotion in vector_a.keys():
            if emotion.startswith("_"):
                continue  # Skip special keys like _arousal_intensity
            if emotion in vector_b and vector_a[emotion] > 0 and vector_b[emotion] > 0:
                shared.append(emotion)
        return sorted(shared)

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
