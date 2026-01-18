"""
UnionIndexMetadata - GAP-001 Milestone 4 (Issue 4.1)

Tracks source layer and record ID for each vector in FAISS union index.
Enables cross-layer vector search with proper result attribution.

GAP Reference: GAP_001 Section 6 (FAISS Union Index)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class VectorMetadata:
    """
    Metadata for a single vector in the union index.

    Tracks the source layer and record ID so FAISS search results
    can be attributed back to their origin table.

    Attributes:
        layer: Source table (st_epi, st_sem, st_procedural, etc.)
        record_id: Primary key in source layer
        tenant_id: Multi-tenancy support
        space_id: ACL filtering
        faiss_idx: Position in FAISS index (set by UnionIndexMetadata.add)
    """

    layer: str
    record_id: str
    tenant_id: str
    space_id: str
    faiss_idx: int = -1


@dataclass
class UnionIndexMetadata:
    """
    Metadata store for FAISS union index.

    Maintains a parallel list of metadata entries that corresponds
    1:1 with vectors in the FAISS index. Supports:
    - Adding new vectors with metadata
    - Looking up metadata by FAISS index position
    - Converting FAISS search results to (layer, record_id, score) tuples
    - JSON serialization for persistence

    Usage:
        metadata = UnionIndexMetadata()
        idx = metadata.add(VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
        ))
        # idx now matches the position in the FAISS index

    Attributes:
        entries: List of VectorMetadata for each indexed vector
        layer_counts: Count of vectors per layer
        total_vectors: Total vectors in index
        build_timestamp: Unix milliseconds when index was built
        model_version: Embedding model version (e.g., "ultrabert-v2.1.0")
    """

    entries: List[VectorMetadata] = field(default_factory=list)
    layer_counts: Dict[str, int] = field(default_factory=dict)
    total_vectors: int = 0
    build_timestamp: int = 0
    model_version: str = "ultrabert-v2.1.0"

    def add(self, meta: VectorMetadata) -> int:
        """
        Add metadata entry, return FAISS index position.

        The returned index matches the position this vector should have
        in the FAISS index (0-indexed).

        Args:
            meta: VectorMetadata to add

        Returns:
            FAISS index position for this entry
        """
        meta.faiss_idx = len(self.entries)
        self.entries.append(meta)
        self.layer_counts[meta.layer] = self.layer_counts.get(meta.layer, 0) + 1
        self.total_vectors += 1
        return meta.faiss_idx

    def get(self, faiss_idx: int) -> Optional[VectorMetadata]:
        """
        Get metadata by FAISS index position.

        Args:
            faiss_idx: Position in FAISS index

        Returns:
            VectorMetadata if found, None otherwise
        """
        if 0 <= faiss_idx < len(self.entries):
            return self.entries[faiss_idx]
        return None

    def search_results_to_layer_ids(
        self,
        faiss_indices: List[int],
        scores: List[float],
    ) -> List[Tuple[str, str, float]]:
        """
        Convert FAISS indices to (layer, record_id, score) tuples.

        Used to translate raw FAISS search results back to
        meaningful layer references.

        Args:
            faiss_indices: List of FAISS index positions from search
            scores: Corresponding similarity scores

        Returns:
            List of (layer, record_id, score) tuples
        """
        results = []
        for idx, score in zip(faiss_indices, scores):
            meta = self.get(idx)
            if meta:
                results.append((meta.layer, meta.record_id, score))
        return results

    def get_layer_count(self, layer: str) -> int:
        """
        Get count of vectors for a specific layer.

        Args:
            layer: Layer name (e.g., "st_epi")

        Returns:
            Number of vectors from that layer
        """
        return self.layer_counts.get(layer, 0)

    def to_json(self) -> str:
        """
        Serialize to JSON for persistence.

        Returns:
            JSON string representation
        """
        return json.dumps(
            {
                "entries": [
                    {
                        "layer": e.layer,
                        "record_id": e.record_id,
                        "tenant_id": e.tenant_id,
                        "space_id": e.space_id,
                        "faiss_idx": e.faiss_idx,
                    }
                    for e in self.entries
                ],
                "layer_counts": self.layer_counts,
                "total_vectors": self.total_vectors,
                "build_timestamp": self.build_timestamp,
                "model_version": self.model_version,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> UnionIndexMetadata:
        """
        Deserialize from JSON.

        Args:
            data: JSON string

        Returns:
            UnionIndexMetadata instance
        """
        obj = json.loads(data)
        meta = cls(
            layer_counts=obj.get("layer_counts", {}),
            total_vectors=obj.get("total_vectors", 0),
            build_timestamp=obj.get("build_timestamp", 0),
            model_version=obj.get("model_version", "ultrabert-v2.1.0"),
        )
        for e in obj.get("entries", []):
            meta.entries.append(
                VectorMetadata(
                    layer=e["layer"],
                    record_id=e["record_id"],
                    tenant_id=e["tenant_id"],
                    space_id=e["space_id"],
                    faiss_idx=e["faiss_idx"],
                )
            )
        return meta

    def to_dict(self) -> Dict:
        """
        Convert to dictionary for logging/debugging.

        Returns:
            Dictionary representation
        """
        return {
            "total_vectors": self.total_vectors,
            "layer_counts": self.layer_counts,
            "build_timestamp": self.build_timestamp,
            "model_version": self.model_version,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"UnionIndexMetadata("
            f"total={self.total_vectors}, "
            f"layers={self.layer_counts}, "
            f"timestamp={self.build_timestamp})"
        )
