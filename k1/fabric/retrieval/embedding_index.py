"""
k1.fabric.retrieval.embedding_index -- FAISS-backed vector index (4.1.1).

Provides semantic search over capability contracts using FAISS.
Text to embed: ``f"{contract.description} | {' '.join(contract.capabilities)}"``.

Operations:
  add_vector(contract_id, vector)   -- incremental on register
  remove_vector(contract_id)        -- incremental on unregister
  search(query_vector, k)           -- top-K nearest neighbours
  rebuild(vectors_dict)             -- full rebuild on startup / reload

Index strategy:
  - Flat L2 (IndexFlatL2) for <=IVF_THRESHOLD contracts  -- exact search
  - IVF (IndexIVFFlat)  for  >IVF_THRESHOLD contracts  -- approximate search

Thread safety:
  All mutations acquire _lock (RLock).  Reads (search) acquire _lock
  briefly to snapshot the index reference, then run search outside the lock.

References:
  - fabric_discussion.md Section 8 (Retrieval Pipeline)
  - Epic 4.1.1 spec in fabric-implementation-plan.md
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

# ---------------------------------------------------------------------------
# Protocols -- declared locally to avoid circular imports
# ---------------------------------------------------------------------------


class IEmbeddingPort(Protocol):
    """
    Port for computing text embeddings.

    Production: delegates to the model gateway (same model used for indexing).
    Test: any callable returning a float32 array of correct dimensionality.
    """

    def embed(self, text: str) -> np.ndarray:
        """Return a 1-D float32 embedding vector for *text*."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DIMENSION: int = 384
"""Default embedding dimension (MiniLM-L6 output size)."""

IVF_THRESHOLD: int = 10_000
"""Switch from flat L2 to IVF when the index exceeds this many vectors."""

IVF_NLIST: int = 100
"""Number of Voronoi cells for IVF index (sqrt(N) rule-of-thumb capped)."""

IVF_NPROBE: int = 10
"""Number of cells to probe during IVF search (tradeoff: accuracy vs speed)."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EmbeddingIndexError(Exception):
    """Base exception for EmbeddingIndex operations."""


class DuplicateVectorError(EmbeddingIndexError):
    """Raised when adding a vector for an already-indexed contract_id."""

    def __init__(self, contract_id: str) -> None:
        self.contract_id = contract_id
        super().__init__(f"Vector already exists for contract_id={contract_id!r}")


class VectorNotFoundError(EmbeddingIndexError):
    """Raised when removing a vector for an unknown contract_id."""

    def __init__(self, contract_id: str) -> None:
        self.contract_id = contract_id
        super().__init__(f"No vector for contract_id={contract_id!r}")


class DimensionMismatchError(EmbeddingIndexError):
    """Raised when a vector's dimensionality does not match the index."""

    def __init__(self, expected: int, got: int) -> None:
        self.expected = expected
        self.got = got
        super().__init__(f"Dimension mismatch: index expects {expected}, got {got}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingIndexConfig:
    """
    Configuration for the EmbeddingIndex.

    Attributes:
        dimension: Embedding vector dimensionality.
        ivf_threshold: Switch to IVF index above this count.
        ivf_nlist: Number of Voronoi cells for IVF.
        ivf_nprobe: Number of cells probed during IVF search.
    """

    dimension: int = DEFAULT_DIMENSION
    ivf_threshold: int = IVF_THRESHOLD
    ivf_nlist: int = IVF_NLIST
    ivf_nprobe: int = IVF_NPROBE


# ---------------------------------------------------------------------------
# Search result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchHit:
    """
    A single search result from the embedding index.

    Attributes:
        contract_id: Capability contract name/id.
        score: Similarity score.  For L2 distance this is the *negative*
            distance (higher = more similar).  For cosine, 1 - dist.
        distance: Raw L2 distance from the query vector.
    """

    contract_id: str = ""
    score: float = 0.0
    distance: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "score": self.score,
            "distance": self.distance,
        }


# ---------------------------------------------------------------------------
# EmbeddingIndex
# ---------------------------------------------------------------------------


class EmbeddingIndex:
    """
    FAISS-backed vector index for semantic capability search.

    The index maps ``contract_id`` strings to float32 embedding vectors.
    FAISS stores vectors by sequential integer IDs; an internal mapping
    (``_id_to_pos`` / ``_pos_to_id``) translates between contract_id and
    FAISS position.

    Constructor Args:
        config: Optional ``EmbeddingIndexConfig``.

    Thread Safety:
        All mutations (add/remove/rebuild) acquire ``_lock``.
        ``search()`` snapshots the current index reference under the lock,
        then performs the (potentially slow) FAISS search outside the lock.
    """

    __slots__ = (
        "_config",
        "_lock",
        "_dimension",
        "_vectors",
        "_id_to_pos",
        "_pos_to_id",
        "_index",
        "_dirty",
    )

    def __init__(self, config: Optional[EmbeddingIndexConfig] = None) -> None:
        self._config = config or EmbeddingIndexConfig()
        self._lock = threading.RLock()
        self._dimension = self._config.dimension

        # contract_id -> vector (source of truth)
        self._vectors: Dict[str, np.ndarray] = {}

        # Bidirectional mapping: contract_id <-> FAISS row position
        self._id_to_pos: Dict[str, int] = {}
        self._pos_to_id: Dict[int, str] = {}

        # FAISS index -- rebuilt on structural changes
        self._index: Any = None  # faiss.Index (typed Any to avoid top-level import)
        self._dirty: bool = True  # needs rebuild before next search

        self._rebuild_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_vector(
        self,
        contract_id: str,
        vector: np.ndarray,
    ) -> None:
        """
        Add a single vector for *contract_id*.

        Args:
            contract_id: Unique capability identifier.
            vector: 1-D float32 array of shape ``(dimension,)``.

        Raises:
            DuplicateVectorError: contract_id already indexed.
            DimensionMismatchError: vector dimension != index dimension.
            ValueError: contract_id is empty.
        """
        if not contract_id:
            raise ValueError("contract_id must be non-empty")
        vector = self._coerce_vector(vector)

        with self._lock:
            if contract_id in self._vectors:
                raise DuplicateVectorError(contract_id)
            self._vectors[contract_id] = vector
            self._dirty = True
            self._rebuild_index()

    def remove_vector(self, contract_id: str) -> None:
        """
        Remove the vector for *contract_id*.

        Args:
            contract_id: Capability identifier to remove.

        Raises:
            VectorNotFoundError: contract_id not in the index.
        """
        with self._lock:
            if contract_id not in self._vectors:
                raise VectorNotFoundError(contract_id)
            del self._vectors[contract_id]
            self._dirty = True
            self._rebuild_index()

    def update_vector(
        self,
        contract_id: str,
        vector: np.ndarray,
    ) -> None:
        """
        Replace the vector for an existing *contract_id*.

        If not present, adds it (upsert semantics).

        Args:
            contract_id: Capability identifier.
            vector: New embedding vector.
        """
        if not contract_id:
            raise ValueError("contract_id must be non-empty")
        vector = self._coerce_vector(vector)

        with self._lock:
            self._vectors[contract_id] = vector
            self._dirty = True
            self._rebuild_index()

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
    ) -> List[SearchHit]:
        """
        Search for the *k* nearest vectors to *query_vector*.

        Returns results sorted by ascending distance (best match first).
        If fewer than *k* vectors exist, returns all available.

        Args:
            query_vector: 1-D float32 embedding.
            k: Number of results (clamped to index size).

        Returns:
            List of ``SearchHit`` in descending similarity order.
        """
        query_vector = self._coerce_vector(query_vector)
        k = max(1, k)

        with self._lock:
            if self._dirty:
                self._rebuild_index()
            index = self._index
            pos_to_id = dict(self._pos_to_id)
            n = len(self._vectors)

        if n == 0 or index is None:
            return []

        k = min(k, n)
        query = query_vector.reshape(1, -1).astype(np.float32)
        distances, indices = index.search(query, k)

        hits: List[SearchHit] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue  # FAISS sentinel for "no result"
            cid = pos_to_id.get(int(idx))
            if cid is None:
                continue
            # Convert L2 distance to a similarity-like score:
            # score = 1 / (1 + distance)  -- bounded (0, 1]
            score = 1.0 / (1.0 + float(dist))
            hits.append(
                SearchHit(
                    contract_id=cid,
                    score=score,
                    distance=float(dist),
                )
            )
        return hits

    def rebuild(
        self,
        vectors: Dict[str, np.ndarray],
    ) -> None:
        """
        Full rebuild from a map of contract_id -> vector.

        Used on startup or registry reload.

        Args:
            vectors: Complete set of vectors to index.

        Raises:
            DimensionMismatchError: Any vector has wrong dimension.
        """
        coerced: Dict[str, np.ndarray] = {}
        for cid, vec in vectors.items():
            coerced[cid] = self._coerce_vector(vec)

        with self._lock:
            self._vectors = coerced
            self._dirty = True
            self._rebuild_index()

    def contains(self, contract_id: str) -> bool:
        """Check if a contract_id is in the index."""
        return contract_id in self._vectors

    def get_vectors_snapshot(self) -> Dict[str, np.ndarray]:
        """
        Return a thread-safe copy of all stored vectors.

        Acquires ``_lock`` and returns a shallow copy of ``_vectors`` so
        callers can read vectors without holding the lock.  Fixes Issue 3:
        ``RetrievalEngine`` previously accessed ``_vectors`` directly via
        ``getattr()``, bypassing the lock entirely.

        Returns:
            Dict mapping contract_id -> embedding vector (copies of references;
            ndarray values are immutable after insertion so no deep-copy needed).
        """
        with self._lock:
            return dict(self._vectors)

    @property
    def size(self) -> int:
        """Number of indexed vectors."""
        return len(self._vectors)

    @property
    def dimension(self) -> int:
        """Embedding dimensionality."""
        return self._dimension

    @property
    def config(self) -> EmbeddingIndexConfig:
        """Current configuration."""
        return self._config

    @property
    def is_ivf(self) -> bool:
        """True if the current index strategy is IVF (approximate search)."""
        with self._lock:
            return len(self._vectors) > self._config.ivf_threshold

    def __repr__(self) -> str:
        strategy = "IVF" if self.is_ivf else "FlatL2"
        return f"EmbeddingIndex(size={self.size}, dim={self._dimension}, " f"strategy={strategy})"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _coerce_vector(self, vector: np.ndarray) -> np.ndarray:
        """Validate and coerce vector to float32 with correct dimension."""
        vector = np.asarray(vector, dtype=np.float32).ravel()
        if vector.shape[0] != self._dimension:
            raise DimensionMismatchError(self._dimension, vector.shape[0])
        return vector

    def _rebuild_index(self) -> None:
        """
        Rebuild the FAISS index from ``_vectors``.

        MUST be called with ``_lock`` held.
        """
        import faiss  # lazy import -- heavy C library

        n = len(self._vectors)
        dim = self._dimension

        if n == 0:
            self._index = faiss.IndexFlatL2(dim)
            self._id_to_pos = {}
            self._pos_to_id = {}
            self._dirty = False
            return

        # Build position mappings
        id_to_pos: Dict[str, int] = {}
        pos_to_id: Dict[int, str] = {}
        matrix = np.empty((n, dim), dtype=np.float32)

        for pos, (cid, vec) in enumerate(self._vectors.items()):
            id_to_pos[cid] = pos
            pos_to_id[pos] = cid
            matrix[pos] = vec

        # Choose index strategy
        if n > self._config.ivf_threshold:
            nlist = min(self._config.ivf_nlist, n)
            quantizer = faiss.IndexFlatL2(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, nlist)
            index.train(matrix)
            index.add(matrix)
            index.nprobe = self._config.ivf_nprobe
        else:
            index = faiss.IndexFlatL2(dim)
            index.add(matrix)

        self._index = index
        self._id_to_pos = id_to_pos
        self._pos_to_id = pos_to_id
        self._dirty = False
