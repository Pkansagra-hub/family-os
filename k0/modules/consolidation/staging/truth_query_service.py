"""
TruthQueryService — Query truth layers for reconciliation candidates.

Provides similarity search across episodic, semantic, procedural, social,
and prospective memory layers. Uses embedding vectors stored in st_vec
with JOINs to truth tables.

Issue: 4.3.2 (ReconciliationEngine dependency)
Spec Reference:
    - Dossier §4.3.2 (Decision Engine — Truth Query)
    - P03_RECONCILIATION_ENGINE_INTEGRATION_PLAN.md Section 4.2
    - Migration 0025_st_vec.py (vector storage schema)
    - Migration 0027_st_epi.py (episodic memory schema)

Query Strategy:
    1. For each truth layer, JOIN to st_vec on embedding_id
    2. Load embeddings as numpy arrays
    3. Compute cosine similarity in Python (pgvector optional)
    4. Return top-k candidates sorted by similarity

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# =============================================================================
# Constants
# =============================================================================

# Layers and their embedding FK column names
LAYER_EMBEDDING_COLUMNS: Dict[str, str] = {
    "st_epi": "embedding_id",
    "st_sem": "embedding_id",
    "st_procedural": "embedding_id",
    "st_social": "embedding_id",
    "st_prospective": "embedding_id",
}

# Primary key columns for each layer
LAYER_PK_COLUMNS: Dict[str, str] = {
    "st_epi": "episode_id",
    "st_sem": "semantic_id",
    "st_procedural": "routine_id",
    "st_social": "relationship_id",
    "st_prospective": "intention_id",
}

# Confidence column (if available) for each layer
LAYER_CONFIDENCE_COLUMNS: Dict[str, Optional[str]] = {
    "st_epi": "confidence_score",
    "st_sem": "confidence_score",
    "st_procedural": "confidence",
    "st_social": "confidence",
    "st_prospective": "confidence",
}


# =============================================================================
# TruthCandidate Dataclass
# =============================================================================


@dataclass
class TruthCandidate:
    """
    A candidate match from truth layers.

    Attributes:
        record_id: Primary key of the truth record
        layer: Truth layer name (st_epi, st_sem, etc.)
        embedding: Vector embedding as numpy array
        similarity: Pre-computed similarity score (0 if not computed)
        confidence: Record confidence score [0, 1]
        last_accessed_ms: Last access timestamp in milliseconds (if available)
    """

    record_id: str
    layer: str
    embedding: np.ndarray
    similarity: float = 0.0
    confidence: float = 0.5
    last_accessed_ms: int = 0

    def __post_init__(self) -> None:
        """Validate fields."""
        if self.layer not in LAYER_PK_COLUMNS:
            raise ValueError(
                f"Unknown layer: {self.layer}. " f"Valid layers: {list(LAYER_PK_COLUMNS.keys())}"
            )
        self.similarity = max(0.0, min(1.0, self.similarity))
        self.confidence = max(0.0, min(1.0, self.confidence))


# =============================================================================
# DecayCandidate Dataclass
# =============================================================================


@dataclass
class DecayCandidate:
    """
    An entity from truth layers that needs decay evaluation.

    Used by R3 to query entities with decay_factor < 1.0 for retention decisions.

    Attributes:
        entity_id: Primary key of the truth record
        table_name: Truth layer name (st_epi, st_kg_dom, etc.)
        last_observed_at: Last observation timestamp (epoch ms)
        decay_factor: Current decay factor [0, 1]
        confidence_score: Confidence score [0, 1]
        observation_count: Number of times observed
        entity_type: Entity type (if available, e.g., PERSON, PLACE)
        attributes: Additional attributes dict (optional)
    """

    entity_id: str
    table_name: str
    last_observed_at: int
    decay_factor: float = 1.0
    confidence_score: float = 0.5
    observation_count: int = 1
    entity_type: str = ""
    attributes: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Validate fields and set defaults."""
        if self.attributes is None:
            self.attributes = {}
        self.decay_factor = max(0.0, min(1.0, self.decay_factor))
        self.confidence_score = max(0.0, min(1.0, self.confidence_score))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for R3 execute() consumption."""
        return {
            "entity_id": self.entity_id,
            "table_name": self.table_name,
            "last_observed_at": self.last_observed_at,
            "decay_factor": self.decay_factor,
            "confidence_score": self.confidence_score,
            "observation_count": self.observation_count,
            "entity_type": self.entity_type,
            "attributes": self.attributes,
        }


# Layers that support decay evaluation (have decay_factor column)
DECAY_LAYERS: Dict[str, str] = {
    "st_epi": "episode_id",
    "st_kg_dom": "entity_id",
    "st_sem": "semantic_id",
    "st_procedural": "routine_id",
    "st_social": "relationship_id",
}

# Entity type column for each layer (if available)
LAYER_ENTITY_TYPE_COLUMNS: Dict[str, Optional[str]] = {
    "st_epi": "episode_type",
    "st_kg_dom": "entity_type",
    "st_sem": None,
    "st_procedural": "routine_type",
    "st_social": "relationship_type",
}


# =============================================================================
# TruthQueryService
# =============================================================================


class TruthQueryService:
    """
    Queries truth layers for reconciliation candidates.

    Uses vector similarity search across:
        - st_epi (episodic memories)
        - st_sem (semantic patterns)
        - st_procedural (habits/routines)
        - st_social (relationships)
        - st_prospective (intentions)

    Query Strategy:
        1. For each layer, fetch records with embeddings via JOIN to st_vec
        2. Decode BYTEA vectors to numpy arrays
        3. Compute cosine similarity against query embedding
        4. Return top-k sorted by similarity

    Usage:
        service = TruthQueryService(conn_factory)
        candidates = await service.find_candidates(
            embedding=event_embedding,
            space_id="space_123",
            tenant_id="tenant_abc",
            top_k=10,
            min_similarity=0.35,
        )

    Spec Reference:
        - Dossier §4.3.2 (Decision Engine)
        - P03_RECONCILIATION_ENGINE_INTEGRATION_PLAN.md
    """

    def __init__(
        self,
        conn_factory: Callable[[], Any] = None,
        pool: Any = None,
        embedding_dim: int = 768,
    ) -> None:
        """
        Initialize TruthQueryService.

        Args:
            conn_factory: DEPRECATED - Factory function that returns async DB connection
            pool: AsyncPgPool instance for connection management (preferred)
            embedding_dim: Expected embedding dimension (default 768 for UltraBERT)
        """
        self._conn_factory = conn_factory
        self._pool = pool
        self._embedding_dim = embedding_dim

        # Query cache (optional optimization)
        self._query_count = 0
        self._total_candidates = 0

    # =========================================================================
    # Main Query Method
    # =========================================================================

    async def find_candidates(
        self,
        embedding: np.ndarray,
        space_id: str,
        tenant_id: str,
        top_k: int = 10,
        min_similarity: float = 0.35,
        layers: Optional[Tuple[str, ...]] = None,
    ) -> List[TruthCandidate]:
        """
        Find top-k candidates across all truth layers.

        Algorithm:
            1. Query each layer with JOIN to st_vec
            2. Decode embeddings from BYTEA
            3. Compute cosine similarity
            4. Filter by min_similarity
            5. Sort by similarity descending
            6. Return top-k

        Args:
            embedding: Query embedding vector (768-dim)
            space_id: Space context for filtering
            tenant_id: Tenant context for filtering
            top_k: Maximum candidates to return (per layer)
            min_similarity: Minimum similarity threshold
            layers: Layers to query (default: all 5)

        Returns:
            List of TruthCandidate sorted by similarity descending

        Raises:
            ValueError: If embedding dimension is wrong
        """
        # Validate embedding
        if embedding.shape[0] != self._embedding_dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._embedding_dim}, "
                f"got {embedding.shape[0]}"
            )

        # Default to all layers
        if layers is None:
            layers = tuple(LAYER_PK_COLUMNS.keys())

        all_candidates: List[TruthCandidate] = []

        # Query each layer
        for layer in layers:
            if layer not in LAYER_PK_COLUMNS:
                continue

            layer_candidates = await self._query_layer(
                layer=layer,
                embedding=embedding,
                space_id=space_id,
                tenant_id=tenant_id,
                limit=top_k * 2,  # Fetch more for filtering
            )
            all_candidates.extend(layer_candidates)

        # Compute similarities and filter
        result_candidates = []
        for candidate in all_candidates:
            similarity = self._cosine_similarity(embedding, candidate.embedding)
            if similarity >= min_similarity:
                candidate.similarity = similarity
                result_candidates.append(candidate)

        # Sort by similarity descending and limit to top_k
        result_candidates.sort(key=lambda c: c.similarity, reverse=True)
        result = result_candidates[:top_k]

        # Update metrics
        self._query_count += 1
        self._total_candidates += len(result)

        return result

    # =========================================================================
    # Layer Query
    # =========================================================================

    async def _query_layer(
        self,
        layer: str,
        embedding: np.ndarray,
        space_id: str,
        tenant_id: str,
        limit: int,
    ) -> List[TruthCandidate]:
        """
        Query a single truth layer for candidates.

        Executes:
            SELECT t.{pk}, v.vector, t.{confidence}
            FROM {layer} t
            JOIN st_vec v ON t.embedding_id = v.embedding_id
            WHERE t.tenant_id = $1
              AND t.space_id = $2
              AND t.archival_status = 'ACTIVE'
              AND t.embedding_id IS NOT NULL
            LIMIT $3

        Args:
            layer: Truth layer name
            embedding: Query embedding (unused here, for future pgvector)
            space_id: Space context
            tenant_id: Tenant context
            limit: Maximum rows to fetch

        Returns:
            List of TruthCandidate (unsorted)
        """
        pk_col = LAYER_PK_COLUMNS[layer]
        conf_col = LAYER_CONFIDENCE_COLUMNS.get(layer)
        emb_col = LAYER_EMBEDDING_COLUMNS.get(layer, "embedding_id")

        # Build query
        conf_select = f", t.{conf_col}" if conf_col else ", 0.5 as confidence_score"

        query = f"""
            SELECT
                t.{pk_col} as record_id,
                v.vector,
                v.vector_dim
                {conf_select}
            FROM {layer} t
            JOIN st_vec v ON t.{emb_col} = v.embedding_id
            WHERE t.tenant_id = $1
              AND t.space_id = $2
              AND v.vector IS NOT NULL
            LIMIT $3
        """

        # Check if archival_status column exists for this layer
        if layer in ("st_epi", "st_sem", "st_procedural"):
            query = f"""
                SELECT
                    t.{pk_col} as record_id,
                    v.vector,
                    v.vector_dim
                    {conf_select}
                FROM {layer} t
                JOIN st_vec v ON t.{emb_col} = v.embedding_id
                WHERE t.tenant_id = $1
                  AND t.space_id = $2
                  AND t.archival_status = 'ACTIVE'
                  AND v.vector IS NOT NULL
                LIMIT $3
            """

        candidates: List[TruthCandidate] = []

        try:
            # Use pool.acquire() if pool provided, else use conn_factory
            if self._pool is not None:
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(query, tenant_id, space_id, limit)
                    for row in rows:
                        record_id = row["record_id"]
                        vector_bytes = row["vector"]
                        vector_dim = row["vector_dim"]
                        confidence = row.get("confidence_score", 0.5)

                        embedding_array = self._decode_bytea_vector(vector_bytes, vector_dim)
                        if embedding_array is not None:
                            candidates.append(
                                TruthCandidate(
                                    record_id=record_id,
                                    layer=layer,
                                    embedding=embedding_array,
                                    similarity=0.0,
                                    confidence=float(confidence) if confidence else 0.5,
                                )
                            )
            elif self._conn_factory is not None:
                # Legacy conn_factory path
                conn = await self._conn_factory()
                try:
                    rows = await conn.fetch(query, tenant_id, space_id, limit)
                    for row in rows:
                        record_id = row["record_id"]
                        vector_bytes = row["vector"]
                        vector_dim = row["vector_dim"]
                        confidence = row.get("confidence_score", 0.5)

                        embedding_array = self._decode_bytea_vector(vector_bytes, vector_dim)
                        if embedding_array is not None:
                            candidates.append(
                                TruthCandidate(
                                    record_id=record_id,
                                    layer=layer,
                                    embedding=embedding_array,
                                    similarity=0.0,
                                    confidence=float(confidence) if confidence else 0.5,
                                )
                            )
                finally:
                    await conn.close()
        except Exception:
            # Log error but don't fail the query
            # In production, emit metric
            pass

        return candidates

    # =========================================================================
    # Vector Decoding
    # =========================================================================

    def _decode_bytea_vector(
        self,
        vector_bytes: bytes,
        vector_dim: int,
    ) -> Optional[np.ndarray]:
        """
        Decode BYTEA vector to numpy array.

        st_vec stores vectors as BYTEA (binary float32 array).
        Format: array of float32 values, little-endian.

        Args:
            vector_bytes: Raw bytes from st_vec.vector
            vector_dim: Expected dimension from st_vec.vector_dim

        Returns:
            numpy array of float64, or None if decoding fails
        """
        if vector_bytes is None:
            return None

        try:
            # PostgreSQL BYTEA is raw bytes, float32 = 4 bytes each
            expected_size = vector_dim * 4
            if len(vector_bytes) != expected_size:
                return None

            # Unpack as float32 array
            floats = struct.unpack(f"<{vector_dim}f", vector_bytes)
            return np.array(floats, dtype=np.float64)
        except (struct.error, ValueError):
            return None

    # =========================================================================
    # Similarity Computation
    # =========================================================================

    def _cosine_similarity(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two vectors.

        Same implementation as ReconciliationEngine and EntityDisambiguator.

        Returns:
            Cosine similarity in [0, 1]
        """
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        cos_sim = np.dot(vec1, vec2) / (norm1 * norm2)
        return float(max(0.0, min(1.0, cos_sim)))

    # =========================================================================
    # Decay Evaluation Query (R3)
    # =========================================================================

    async def query_entities_for_decay(
        self,
        space_id: str,
        tenant_id: str,
        max_decay_factor: float = 0.99,
        limit_per_layer: int = 100,
        layers: Optional[Tuple[str, ...]] = None,
    ) -> List[DecayCandidate]:
        """
        Query entities needing decay evaluation from truth layers.

        Fetches ACTIVE entities with decay_factor < max_decay_factor,
        ordered by last_observed_at ASC (oldest first for priority pruning).

        Args:
            space_id: Space context for filtering
            tenant_id: Tenant context for filtering
            max_decay_factor: Maximum decay factor to include (default 0.99 = any decayed)
            limit_per_layer: Maximum entities per layer (default 100)
            layers: Layers to query (default: all decay-supporting layers)

        Returns:
            List of DecayCandidate sorted by last_observed_at ASC (oldest first)
        """
        if layers is None:
            layers = tuple(DECAY_LAYERS.keys())

        all_candidates: List[DecayCandidate] = []

        for layer in layers:
            if layer not in DECAY_LAYERS:
                continue

            layer_candidates = await self._query_decay_layer(
                layer=layer,
                space_id=space_id,
                tenant_id=tenant_id,
                max_decay_factor=max_decay_factor,
                limit=limit_per_layer,
            )
            all_candidates.extend(layer_candidates)

        # Sort by last_observed_at ASC (oldest entities first for priority pruning)
        all_candidates.sort(key=lambda c: c.last_observed_at)

        return all_candidates

    async def _query_decay_layer(
        self,
        layer: str,
        space_id: str,
        tenant_id: str,
        max_decay_factor: float,
        limit: int,
    ) -> List[DecayCandidate]:
        """
        Query a single truth layer for entities needing decay evaluation.

        SQL:
            SELECT {pk}, last_observed_at, decay_factor, confidence_score,
                   observation_count, {entity_type_col}
            FROM {layer}
            WHERE tenant_id = $1
              AND space_id = $2
              AND archival_status = 'ACTIVE'
              AND decay_factor < $3
            ORDER BY last_observed_at ASC
            LIMIT $4
        """
        pk_col = DECAY_LAYERS[layer]
        entity_type_col = LAYER_ENTITY_TYPE_COLUMNS.get(layer)

        # Build SELECT clause
        entity_type_select = f", {entity_type_col}" if entity_type_col else ""

        query = f"""
            SELECT
                {pk_col} as entity_id,
                last_observed_at,
                decay_factor,
                confidence_score,
                observation_count
                {entity_type_select}
            FROM {layer}
            WHERE tenant_id = $1
              AND space_id = $2
              AND archival_status = 'ACTIVE'
              AND decay_factor < $3
            ORDER BY last_observed_at ASC
            LIMIT $4
        """

        candidates: List[DecayCandidate] = []

        try:
            if self._pool is not None:
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(query, tenant_id, space_id, max_decay_factor, limit)
                    for row in rows:
                        entity_type = row.get(entity_type_col, "") if entity_type_col else ""
                        candidates.append(
                            DecayCandidate(
                                entity_id=row["entity_id"],
                                table_name=layer,
                                last_observed_at=row["last_observed_at"] or 0,
                                decay_factor=row["decay_factor"] or 1.0,
                                confidence_score=row["confidence_score"] or 0.5,
                                observation_count=row["observation_count"] or 1,
                                entity_type=entity_type or "",
                            )
                        )
            elif self._conn_factory is not None:
                conn = await self._conn_factory()
                try:
                    rows = await conn.fetch(query, tenant_id, space_id, max_decay_factor, limit)
                    for row in rows:
                        entity_type = row.get(entity_type_col, "") if entity_type_col else ""
                        candidates.append(
                            DecayCandidate(
                                entity_id=row["entity_id"],
                                table_name=layer,
                                last_observed_at=row["last_observed_at"] or 0,
                                decay_factor=row["decay_factor"] or 1.0,
                                confidence_score=row["confidence_score"] or 0.5,
                                observation_count=row["observation_count"] or 1,
                                entity_type=entity_type or "",
                            )
                        )
                finally:
                    await conn.close()
        except Exception:
            # Log error but don't fail - decay evaluation is best-effort
            pass

        return candidates

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> Dict[str, Any]:
        """Get query metrics."""
        return {
            "query_count": self._query_count,
            "total_candidates": self._total_candidates,
            "avg_candidates_per_query": (
                self._total_candidates / self._query_count if self._query_count > 0 else 0.0
            ),
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        self._query_count = 0
        self._total_candidates = 0
