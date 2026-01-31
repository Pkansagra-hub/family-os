"""
SemanticSimilarityEnricher - GAP-007 Epic 3.1

Creates edges between semantically similar KG entities using embedding similarity
from the union index (st_kg_dom layer).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from k0.modules.consolidation.algorithms.edge_enrichers.fusion import canonical_edge_key
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate, KGEntity

if TYPE_CHECKING:
    from k0.pipelines.p03.phases.r4_config import SemanticSimilarityConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    relationship_type: Optional[str] = None


class SemanticSimilarityEnricher:
    """Creates KG edges for semantically similar entities."""

    def __init__(
        self,
        config: Optional["SemanticSimilarityConfig"],
        syscalls,
    ) -> None:
        self.config = config or SemanticSimilarityConfig()
        self._syscalls = syscalls

    async def enrich(
        self,
        entities: Sequence[KGEntity],
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
        existing_edges: Mapping[object, object],
        tenant_id: str,
        space_id: str,
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        logger.info(
            "SemanticSimilarityEnricher.enrich called",
            extra={
                "entity_count": len(entities) if entities else 0,
                "config_enabled": self.config.enabled,
                "k_neighbors": self.config.k_neighbors,
                "similarity_threshold": self.config.similarity_threshold,
                "tenant_id": tenant_id,
                "space_id": space_id,
            },
        )

        if not entities:
            logger.warning("SemanticSimilarityEnricher: no entities provided")
            return [], []

        if not self._syscalls:
            logger.warning("SemanticSimilarityEnricher: syscalls unavailable")
            return [], []

        normalized_existing = self._normalize_existing_edges(existing_edges)
        embeddings = await self._resolve_embeddings(entities)

        logger.info(
            "SemanticSimilarityEnricher: embeddings resolved",
            extra={
                "entities_with_embeddings": len(embeddings),
                "total_entities": len(entities),
            },
        )

        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []
        created_keys: set[Tuple[str, str]] = set()
        updated_keys: set[Tuple[str, str]] = set()

        if not self.config.enabled:
            logger.info("SemanticSimilarityEnricher: disabled by config")
            return new_edges, updates

        # Compare entities within this batch against each other using cosine similarity
        # This works for first cycle when st_kg_dom is empty - no FAISS needed
        entities_with_vectors = [
            (e, embeddings[e.entity_id]) for e in entities if e.entity_id in embeddings
        ]

        logger.info(
            "SemanticSimilarityEnricher: comparing %d entities within batch",
            len(entities_with_vectors),
        )

        for i, (entity_a, vec_a) in enumerate(entities_with_vectors):
            edges_for_entity = 0
            for j, (entity_b, vec_b) in enumerate(entities_with_vectors):
                if i >= j:  # Skip self and already-compared pairs
                    continue
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                # Cosine similarity between vectors
                similarity = self._cosine_similarity(vec_a, vec_b)

                if similarity < self.config.similarity_threshold:
                    continue

                edge_key = canonical_edge_key(entity_a.entity_id, entity_b.entity_id)
                if edge_key in created_keys or edge_key in updated_keys:
                    continue

                existing = normalized_existing.get(edge_key)
                context = self._select_best_context(entity_contexts.get(entity_a.entity_id, []))
                evidence_event_ids = self._context_event_ids(context)

                if existing:
                    updates.append(
                        KGEdgeUpdate(
                            edge_id=existing.edge_id,
                            weight_delta=similarity * 0.1,
                            confidence_delta=similarity * 0.1,
                            source_algorithm="semantic_similarity",
                            new_evidence_event_ids=evidence_event_ids,
                            observation_context=context,
                        )
                    )
                    updated_keys.add(edge_key)
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
                            source_algorithm="semantic_similarity",
                            evidence_event_ids=evidence_event_ids,
                            properties_json=json.dumps(
                                {
                                    "similarity_score": similarity,
                                    "threshold": self.config.similarity_threshold,
                                }
                            ),
                            algorithm_params_json=json.dumps(
                                {
                                    "similarity_threshold": self.config.similarity_threshold,
                                }
                            ),
                            observation_context=context,
                        )
                    )
                    created_keys.add(edge_key)
                    edges_for_entity += 1

        logger.info(
            "SemanticSimilarityEnricher.enrich complete",
            extra={
                "new_edges": len(new_edges),
                "updated_edges": len(updates),
                "entities_processed": len(entities),
                "entities_with_vectors": len(entities_with_vectors),
            },
        )

        return new_edges, updates

    def _cosine_similarity(self, vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def _search_neighbors(
        self,
        query_vector: Sequence[float],
        tenant_id: str,
        space_id: str,
    ) -> List[dict]:
        try:
            logger.debug(
                "SemanticSimilarityEnricher: calling union_index_search",
                extra={
                    "k_neighbors": self.config.k_neighbors,
                    "layer_filter": ["st_kg_dom"],
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "vector_len": len(query_vector) if query_vector else 0,
                },
            )
            result = await self._syscalls.union_index_search(
                query_vector=list(query_vector),
                k=self.config.k_neighbors,
                layer_filter=["st_kg_dom"],
                tenant_id=tenant_id,
                space_id=space_id,
            )
            results = list(result.get("results", []))
            logger.debug(
                "SemanticSimilarityEnricher: union_index_search returned",
                extra={
                    "result_count": len(results),
                    "first_result": results[0] if results else None,
                },
            )
            return results
        except Exception as exc:
            logger.warning("SemanticSimilarityEnricher search failed: %s", exc)
            return []

    async def _resolve_embeddings(
        self,
        entities: Sequence[KGEntity],
    ) -> Dict[str, List[float]]:
        """
        Resolve embeddings for entities by querying st_vec directly.

        GAP-007 Fix: Query st_vec using source_event_ids instead of relying
        on embeddings passed through KGEntity objects. The embeddings are
        already in st_vec from P02 UltraBERT processing.
        """
        embedding_map: Dict[str, List[float]] = {}

        # Step 1: Use entity.embedding if already populated
        entities_needing_fetch: List[KGEntity] = []
        for entity in entities:
            if entity.embedding:
                embedding_map[entity.entity_id] = list(entity.embedding)
            else:
                entities_needing_fetch.append(entity)

        if not entities_needing_fetch:
            logger.info(
                "SemanticSimilarityEnricher: all entities have embeddings",
                extra={"count": len(embedding_map)},
            )
            return embedding_map

        # Step 2: Collect source_event_ids from entities that need embeddings
        event_id_to_entity: Dict[str, str] = {}
        all_event_ids: List[str] = []

        for entity in entities_needing_fetch:
            if entity.source_event_ids:
                for event_id in entity.source_event_ids:
                    if event_id not in event_id_to_entity:
                        event_id_to_entity[event_id] = entity.entity_id
                        all_event_ids.append(event_id)

        logger.info(
            "SemanticSimilarityEnricher: resolving embeddings from st_vec",
            extra={
                "from_entity_embedding": len(embedding_map),
                "entities_needing_fetch": len(entities_needing_fetch),
                "event_ids_to_query": len(all_event_ids),
            },
        )

        if not all_event_ids:
            logger.warning("SemanticSimilarityEnricher: no source_event_ids to query")
            return embedding_map

        # Step 3: Query st_vec by event_ids
        try:
            result = await self._syscalls.embeddings_by_event_ids(all_event_ids)
            embeddings = result.get("embeddings", {})

            logger.info(
                "SemanticSimilarityEnricher: st_vec query returned",
                extra={
                    "requested": len(all_event_ids),
                    "found": len(embeddings),
                },
            )

            # Map event embeddings back to entities
            for event_id, vector in embeddings.items():
                entity_id = event_id_to_entity.get(event_id)
                if entity_id and entity_id not in embedding_map:
                    if isinstance(vector, list) and len(vector) == 768:
                        embedding_map[entity_id] = vector

        except Exception as exc:
            logger.warning("SemanticSimilarityEnricher: st_vec query failed: %s", exc)

        logger.info(
            "SemanticSimilarityEnricher: embeddings resolved",
            extra={
                "entities_with_embeddings": len(embedding_map),
                "total_entities": len(entities),
            },
        )

        return embedding_map

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
        context: Optional[ObservationContext],
    ) -> List[str]:
        if not context or not context.source_event_id:
            return []
        return [context.source_event_id]

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
