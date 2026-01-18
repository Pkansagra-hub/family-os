"""
UnionIndexSearcher - GAP-001 Milestone 4 (Issue 4.3)

Searches FAISS union index and returns cross-layer results.
Translates FAISS indices back to (layer, record_id, score).

GAP Reference: GAP_001 Section 6 (Query Flow)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np

from .union_index_metadata import UnionIndexMetadata

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """
    Single search result with layer attribution.

    Represents a match from the union index search, including
    the source layer, record ID, and similarity score.

    Attributes:
        layer: Source table (st_epi, st_sem, etc.)
        record_id: Primary key in source layer
        score: Similarity score (0-1, higher is better for cosine)
        tenant_id: Tenant that owns this record
        space_id: ACL space for this record
    """

    layer: str
    record_id: str
    score: float
    tenant_id: str
    space_id: str

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "layer": self.layer,
            "record_id": self.record_id,
            "score": self.score,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
        }


class UnionIndexSearcher:
    """
    Searches FAISS union index for similar vectors.

    Wraps a FAISS index and its metadata to provide semantic search
    across all truth layers with proper result attribution.

    Supports filtering by:
    - Layer (e.g., only search st_epi and st_sem)
    - Tenant (multi-tenancy isolation)
    - Space (ACL filtering)

    Usage:
        searcher = UnionIndexSearcher(faiss_index, metadata)
        results = searcher.search(query_vector, k=10)
        for result in results:
            print(f"{result.layer}:{result.record_id} = {result.score:.3f}")
    """

    def __init__(self, index: Any, metadata: UnionIndexMetadata):
        """
        Initialize searcher with index and metadata.

        Args:
            index: FAISS index (IndexFlatIP with normalized vectors)
            metadata: UnionIndexMetadata with layer/id mappings
        """
        self._index = index
        self._metadata = metadata

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 20,
        layer_filter: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search for similar vectors across all truth layers.

        The query vector is normalized before search (for cosine similarity
        via inner product). Results are filtered by layer/tenant/space
        if specified.

        Args:
            query_vector: 768-dim query embedding
            k: Maximum number of results to return
            layer_filter: Optional list of layers to search (e.g., ["st_epi", "st_sem"])
            tenant_id: Optional tenant filter
            space_id: Optional space filter

        Returns:
            List of SearchResult sorted by score descending
        """
        import faiss

        if self._index.ntotal == 0:
            logger.debug("UnionIndexSearcher: empty index")
            return []

        # Reshape and normalize query vector
        query = query_vector.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)

        # Search with extra results for post-filtering
        has_filters = layer_filter or tenant_id or space_id
        search_k = min(k * 3, self._index.ntotal) if has_filters else min(k, self._index.ntotal)

        scores, indices = self._index.search(query, search_k)

        # Convert to SearchResults with filtering
        results: List[SearchResult] = []

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS returns -1 for empty slots
                continue

            meta = self._metadata.get(int(idx))
            if not meta:
                continue

            # Apply filters
            if layer_filter and meta.layer not in layer_filter:
                continue
            if tenant_id and meta.tenant_id != tenant_id:
                continue
            if space_id and meta.space_id != space_id:
                continue

            results.append(
                SearchResult(
                    layer=meta.layer,
                    record_id=meta.record_id,
                    score=float(score),
                    tenant_id=meta.tenant_id,
                    space_id=meta.space_id,
                )
            )

            if len(results) >= k:
                break

        return results

    def search_text(
        self,
        query_text: str,
        k: int = 20,
        layer_filter: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search using a text query (generates embedding automatically).

        Convenience method that embeds the query text using UltraBERT
        before performing vector search.

        Args:
            query_text: Text to search for
            k: Maximum number of results
            layer_filter: Optional layer filter
            tenant_id: Optional tenant filter
            space_id: Optional space filter

        Returns:
            List of SearchResult sorted by score descending
        """
        # Get embedding for query text
        try:
            from k0.runtime.ultrabert_adapter import get_embedding

            embedding = get_embedding(query_text)
            if embedding is None:
                logger.warning("UnionIndexSearcher: failed to embed query text")
                return []

            query_vector = np.array(embedding, dtype=np.float32)
            return self.search(
                query_vector,
                k=k,
                layer_filter=layer_filter,
                tenant_id=tenant_id,
                space_id=space_id,
            )
        except ImportError:
            logger.error("UnionIndexSearcher: UltraBERT adapter not available")
            return []
        except Exception as e:
            logger.error(f"UnionIndexSearcher: search failed: {e}")
            return []

    def search_by_record(
        self,
        source_layer: str,
        source_record_id: str,
        k: int = 20,
        layer_filter: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """
        Find records similar to an existing record.

        Looks up the vector for the given record and searches for
        similar vectors (excluding the source record itself).

        Args:
            source_layer: Layer of the source record
            source_record_id: Record ID to find similar to
            k: Maximum number of results
            layer_filter: Optional layer filter

        Returns:
            List of SearchResult (excluding the source record)
        """
        # Find the source record's vector
        source_idx = None
        for i, meta in enumerate(self._metadata.entries):
            if meta.layer == source_layer and meta.record_id == source_record_id:
                source_idx = i
                break

        if source_idx is None:
            logger.warning(
                "UnionIndexSearcher: source record not found",
                extra={"layer": source_layer, "record_id": source_record_id},
            )
            return []

        # Reconstruct the vector from FAISS
        vector = self._index.reconstruct(source_idx)

        # Search (request one extra since we'll exclude source)
        results = self.search(
            vector,
            k=k + 1,
            layer_filter=layer_filter,
        )

        # Exclude the source record
        return [
            r for r in results if not (r.layer == source_layer and r.record_id == source_record_id)
        ][:k]

    @property
    def total_vectors(self) -> int:
        """Total vectors in index."""
        return self._metadata.total_vectors

    @property
    def layer_counts(self) -> dict:
        """Vector counts per layer."""
        return dict(self._metadata.layer_counts)

    @property
    def build_timestamp(self) -> int:
        """Timestamp when index was built (Unix ms)."""
        return self._metadata.build_timestamp

    @property
    def model_version(self) -> str:
        """Embedding model version."""
        return self._metadata.model_version

    def get_stats(self) -> dict:
        """
        Get index statistics for monitoring.

        Returns:
            Dictionary with index stats
        """
        return {
            "total_vectors": self.total_vectors,
            "layer_counts": self.layer_counts,
            "build_timestamp": self.build_timestamp,
            "model_version": self.model_version,
            "faiss_ntotal": self._index.ntotal if self._index else 0,
        }
