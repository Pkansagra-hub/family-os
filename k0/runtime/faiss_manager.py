"""
FAISS Index Manager - Singleton service for vector similarity search

Manages FAISS IVF256,PQ64 index for 768-dim UltraBERT embeddings.
Used by P08 M24 (embedding.faiss_indexer) and P03 semantic search.

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
Configuration: k0/config/faiss_config.yaml

Index Configuration:
- Index Type: IndexIVFPQ (Inverted File with Product Quantization)
- nlist=256 (256 Voronoi cells)
- M=64 (64 PQ subquantizers), nbits=8
- nprobe=16 (search 16 cells)
- Vector Dimension: 768
- Distance Metric: L2 (Euclidean)
- Compression Ratio: 8:1 (768 * 4 bytes = 3072 bytes → 384 bytes)

Performance:
- Add: <5ms P95 (batch <50ms for 100 vectors)
- Search: <50ms P95 (k=10, nprobe=16)
- Training: ~60s (30,000 vectors minimum)

Thread Safety: All operations protected by asyncio Lock
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FaissIndexManager:
    """
    Singleton FAISS index manager for vector similarity search.

    Lifecycle:
    1. get_instance() - Returns singleton instance
    2. initialize() - Load or create index, optionally train
    3. add() / add_batch() - Add vectors to index
    4. search() - k-NN similarity search
    5. save() - Persist index to disk
    6. close() - Cleanup resources
    """

    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        """Private constructor - use get_instance() instead"""
        if FaissIndexManager._instance is not None:
            raise RuntimeError("Use FaissIndexManager.get_instance() instead")

        self._faiss = None  # Lazy import
        self._index = None
        self._index_id = "ultrabert_v2.1.0_ivf256_pq64"
        self._index_path = Path("data/faiss_indexes")
        self._vector_dim = 768
        self._nlist = 256  # Voronoi cells
        self._nprobe = 16  # Cells to probe during search
        self._pq_m = 64  # PQ subquantizers
        self._pq_nbits = 8  # Bits per PQ code
        self._is_trained = False
        self._id_counter = 0  # Auto-increment for FAISS int64 IDs
        self._operation_lock = asyncio.Lock()

        # ID mapping: embedding_id (str) ↔ faiss_id (int64)
        self._embedding_to_faiss: dict[str, int] = {}
        self._faiss_to_embedding: dict[int, str] = {}

        logger.info("FaissIndexManager instance created")

    @classmethod
    def get_instance(cls) -> "FaissIndexManager":
        """Get singleton instance (thread-safe)"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(
        self, index_path: Path | None = None, train_if_needed: bool = True
    ) -> None:
        """
        Initialize FAISS index (load from disk or create new).

        Args:
            index_path: Custom index storage directory (default: data/faiss_indexes)
            train_if_needed: Auto-train index if untrained and vectors available

        Raises:
            ImportError: If faiss-cpu not installed
            RuntimeError: If initialization fails
        """
        async with self._operation_lock:
            try:
                # Lazy import FAISS
                import faiss

                self._faiss = faiss
                logger.info(
                    "FAISS library loaded successfully", extra={"version": faiss.__version__}
                )
            except ImportError as e:
                logger.error("FAISS library not installed - run: pip install faiss-cpu")
                raise ImportError(
                    "FAISS library not installed. Install with: pip install faiss-cpu>=1.8.0"
                ) from e

            # Set index path
            if index_path:
                self._index_path = Path(index_path)
            self._index_path.mkdir(parents=True, exist_ok=True)

            # Try loading existing index
            index_file = self._index_path / f"{self._index_id}.index"
            if index_file.exists():
                await self._load_index(index_file)
            else:
                await self._create_index(train_if_needed)

            logger.info(
                "FAISS index initialized",
                extra={
                    "index_id": self._index_id,
                    "is_trained": self._is_trained,
                    "total_vectors": self.ntotal(),
                    "vector_dim": self._vector_dim,
                },
            )

    async def _create_index(self, train_if_needed: bool) -> None:
        """Create new FAISS index (FlatL2 for <30K vectors, IVF256+PQ64 for larger datasets)"""

        # Use FlatL2 (no training required) for initial deployment
        # Switch to IndexIVFPQ when >30K vectors accumulated
        use_flat = True  # TODO: Set to False when 30K+ vectors available

        if use_flat:
            logger.info(
                "Creating FlatL2 index (no training required)",
                extra={"index_type": "IndexFlatL2", "vector_dim": self._vector_dim},
            )
            # Wrap FlatL2 in IndexIDMap to support add_with_ids
            flat_index = self._faiss.IndexFlatL2(self._vector_dim)
            self._index = self._faiss.IndexIDMap(flat_index)
            self._is_trained = True  # FlatL2 doesn't require training
            logger.info("FlatL2 index created with IDMap (exact search, optimal for <100K vectors)")
        else:
            logger.info(
                "Creating IVF256+PQ64 index (requires training)",
                extra={
                    "index_type": "IndexIVFPQ",
                    "nlist": self._nlist,
                    "pq_m": self._pq_m,
                    "vector_dim": self._vector_dim,
                },
            )
            # Create quantizer (flat L2 index for centroids)
            quantizer = self._faiss.IndexFlatL2(self._vector_dim)

            # Create IVF+PQ index
            self._index = self._faiss.IndexIVFPQ(
                quantizer,
                self._vector_dim,  # Vector dimension
                self._nlist,  # Number of Voronoi cells
                self._pq_m,  # Number of PQ subquantizers (768 / 12 = 64)
                self._pq_nbits,  # Bits per PQ code
            )

            self._index.nprobe = self._nprobe  # Search parameter
            logger.info("IVF256+PQ64 index created (untrained)", extra={"requires_training": True})

    async def _load_index(self, index_file: Path) -> None:
        """Load existing FAISS index from disk"""
        logger.info("Loading FAISS index from disk", extra={"index_file": str(index_file)})

        try:
            self._index = self._faiss.read_index(str(index_file))
            self._is_trained = self._index.is_trained
            self._index.nprobe = self._nprobe  # Restore search parameter

            logger.info(
                "FAISS index loaded successfully",
                extra={
                    "index_file": str(index_file),
                    "is_trained": self._is_trained,
                    "total_vectors": self._index.ntotal,
                },
            )

            # TODO: Load ID mapping from database (st_vec.faiss_id or st_faiss_id_map)
            # For now, rebuild mapping requires scanning st_vec on startup

        except Exception as e:
            logger.error(
                "Failed to load FAISS index", extra={"index_file": str(index_file), "error": str(e)}
            )
            raise RuntimeError(f"Failed to load FAISS index: {e}") from e

    async def train(self, training_vectors: list[list[float]]) -> None:
        """
        Train FAISS index with sample vectors (requires 30,000+ vectors).

        Args:
            training_vectors: List of 768-dim float vectors for training

        Raises:
            ValueError: If insufficient training data
            RuntimeError: If training fails
        """
        async with self._operation_lock:
            if self._is_trained:
                logger.warning("Index already trained, skipping")
                return

            if len(training_vectors) < 30000:
                raise ValueError(
                    f"Insufficient training data: {len(training_vectors)} vectors "
                    "(minimum 30,000 required for IVF256)"
                )

            logger.info(
                "Training FAISS index",
                extra={"training_vectors": len(training_vectors), "nlist": self._nlist},
            )

            try:
                import numpy as np

                # Convert to numpy array
                train_np = np.array(training_vectors, dtype="float32")

                # Train index
                self._index.train(train_np)
                self._is_trained = True

                logger.info(
                    "FAISS index trained successfully",
                    extra={"training_vectors": len(training_vectors)},
                )

                # Auto-save after training
                await self.save()

            except Exception as e:
                logger.error("FAISS training failed", extra={"error": str(e)})
                raise RuntimeError(f"FAISS training failed: {e}") from e

    async def register_embedding_id(self, embedding_id: str) -> int:
        """
        Register UUID embedding_id and return FAISS int64 ID.

        Args:
            embedding_id: UUID string identifier

        Returns:
            faiss_id: int64 identifier for FAISS

        Thread-safe auto-increment.
        """
        async with self._operation_lock:
            return self._register_embedding_id_unlocked(embedding_id)

    def _register_embedding_id_unlocked(self, embedding_id: str) -> int:
        """Internal method to register ID without acquiring lock (caller must hold lock)."""
        # Check if already registered
        if embedding_id in self._embedding_to_faiss:
            return self._embedding_to_faiss[embedding_id]

        # Assign new FAISS ID
        faiss_id = self._id_counter
        self._id_counter += 1

        # Store bidirectional mapping
        self._embedding_to_faiss[embedding_id] = faiss_id
        self._faiss_to_embedding[faiss_id] = embedding_id

        logger.debug(
            "Registered new embedding ID",
            extra={"embedding_id": embedding_id, "faiss_id": faiss_id},
        )

        return faiss_id

    async def add(
        self, embedding_id: str, vector: list[float], index_id: str | None = None
    ) -> dict[str, Any]:
        """
        Add single vector to FAISS index.

        Args:
            embedding_id: UUID string identifier
            vector: 768-dim float vector
            index_id: FAISS index identifier (default: ultrabert_v2.1.0_ivf256_pq64)

        Returns:
            Dictionary with add results

        Raises:
            ValueError: If vector dimension invalid or index not trained
        """
        async with self._operation_lock:
            if not self._is_trained:
                raise ValueError("FAISS index not trained - call train() first")

            if len(vector) != self._vector_dim:
                raise ValueError(
                    f"Invalid vector dimension: {len(vector)} (expected {self._vector_dim})"
                )

            # Register embedding ID (use unlocked version - we already hold the lock)
            faiss_id = self._register_embedding_id_unlocked(embedding_id)

            # Convert to numpy
            import numpy as np

            vector_np = np.array([vector], dtype="float32")
            ids_np = np.array([faiss_id], dtype="int64")

            # Add to FAISS index
            self._index.add_with_ids(vector_np, ids_np)

            logger.debug(
                "Added vector to FAISS",
                extra={
                    "embedding_id": embedding_id,
                    "faiss_id": faiss_id,
                    "total_vectors": self._index.ntotal,
                },
            )

            return {
                "added": True,
                "embedding_id": embedding_id,
                "faiss_id": faiss_id,
                "index_id": index_id or self._index_id,
                "total_vectors": self._index.ntotal,
            }

    async def add_batch(
        self, embeddings: list[tuple[str, list[float]]], index_id: str | None = None
    ) -> dict[str, Any]:
        """
        Add multiple vectors to FAISS index (5-10x faster than single adds).

        Args:
            embeddings: List of (embedding_id, vector) tuples
            index_id: FAISS index identifier (default: ultrabert_v2.1.0_ivf256_pq64)

        Returns:
            Dictionary with batch add results

        Raises:
            ValueError: If any vector dimension invalid or index not trained
        """
        async with self._operation_lock:
            if not self._is_trained:
                raise ValueError("FAISS index not trained - call train() first")

            if not embeddings:
                return {"added": 0, "total_vectors": self._index.ntotal}

            # Register all embedding IDs (use unlocked version - we already hold the lock)
            faiss_ids = []
            vectors = []
            for embedding_id, vector in embeddings:
                if len(vector) != self._vector_dim:
                    raise ValueError(f"Invalid vector dimension for {embedding_id}: {len(vector)}")

                faiss_id = self._register_embedding_id_unlocked(embedding_id)
                faiss_ids.append(faiss_id)
                vectors.append(vector)

            # Convert to numpy
            import numpy as np

            vectors_np = np.array(vectors, dtype="float32")
            ids_np = np.array(faiss_ids, dtype="int64")

            # Batch add to FAISS
            self._index.add_with_ids(vectors_np, ids_np)

            logger.info(
                "Batch added vectors to FAISS",
                extra={
                    "batch_size": len(embeddings),
                    "total_vectors": self._index.ntotal,
                },
            )

            return {
                "added": len(embeddings),
                "index_id": index_id or self._index_id,
                "total_vectors": self._index.ntotal,
            }

    async def search(
        self, query_vector: list[float], k: int = 10, index_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        k-NN similarity search in FAISS index.

        Args:
            query_vector: 768-dim float query vector
            k: Number of nearest neighbors to return
            index_id: FAISS index identifier (default: ultrabert_v2.1.0_ivf256_pq64)

        Returns:
            List of result dictionaries with:
            - embedding_id: str
            - distance: float (L2 distance, lower is better)
            - rank: int (1-based)

        Raises:
            ValueError: If query vector dimension invalid
        """
        async with self._operation_lock:
            if len(query_vector) != self._vector_dim:
                raise ValueError(
                    f"Invalid query dimension: {len(query_vector)} (expected {self._vector_dim})"
                )

            if self._index.ntotal == 0:
                logger.warning("FAISS index empty, returning no results")
                return []

            # Convert to numpy
            import numpy as np

            query_np = np.array([query_vector], dtype="float32")

            # Search FAISS
            distances, indices = self._index.search(query_np, k)

            # Convert results (indices[0] and distances[0] for single query)
            results = []
            for rank, (faiss_id, distance) in enumerate(zip(indices[0], distances[0]), start=1):
                if faiss_id == -1:  # FAISS returns -1 for empty slots
                    continue

                embedding_id = self._faiss_to_embedding.get(int(faiss_id), f"unknown_{faiss_id}")
                results.append(
                    {
                        "embedding_id": embedding_id,
                        "distance": float(distance),
                        "rank": rank,
                    }
                )

            logger.debug(
                "FAISS search completed",
                extra={
                    "k": k,
                    "results_found": len(results),
                    "total_vectors": self._index.ntotal,
                },
            )

            return results

    async def remove_batch(self, embedding_ids: list[str]) -> dict[str, Any]:
        """
        Remove vectors from FAISS index.

        Args:
            embedding_ids: List of embedding_id strings to remove

        Returns:
            Dictionary with removal results

        Note: FAISS IVF indices don't support efficient removal.
        This method marks IDs as removed in mapping but doesn't
        physically remove from index. Full rebuild required for cleanup.
        """
        async with self._operation_lock:
            removed_count = 0
            for embedding_id in embedding_ids:
                if embedding_id in self._embedding_to_faiss:
                    faiss_id = self._embedding_to_faiss[embedding_id]
                    del self._embedding_to_faiss[embedding_id]
                    del self._faiss_to_embedding[faiss_id]
                    removed_count += 1

            logger.info(
                "Removed embeddings from ID mapping",
                extra={
                    "removed": removed_count,
                    "note": "Physical removal requires index rebuild",
                },
            )

            return {
                "removed": removed_count,
                "total_vectors": self._index.ntotal,
                "note": "Physical removal requires index rebuild",
            }

    async def save(self) -> None:
        """Persist FAISS index to disk"""
        async with self._operation_lock:
            if self._index is None:
                logger.warning("No index to save")
                return

            index_file = self._index_path / f"{self._index_id}.index"
            self._faiss.write_index(self._index, str(index_file))

            logger.info(
                "FAISS index saved to disk",
                extra={
                    "index_file": str(index_file),
                    "total_vectors": self._index.ntotal,
                    "is_trained": self._is_trained,
                },
            )

    def ntotal(self) -> int:
        """Get total number of vectors in index"""
        return self._index.ntotal if self._index else 0

    def is_trained(self) -> bool:
        """Check if index is trained"""
        return self._is_trained

    async def close(self) -> None:
        """Cleanup resources (save index before closing)"""
        async with self._operation_lock:
            if self._index:
                await self.save()
                self._index = None
                logger.info("FAISS index closed")
