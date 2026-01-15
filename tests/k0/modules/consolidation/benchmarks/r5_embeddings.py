"""Embedding services for R5 benchmarks.

Provides UltraBERT-based embeddings (768-dim) and deterministic clustered
embeddings (64-dim) for fast/CI modes without GPU.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import TYPE_CHECKING, Dict, List, Protocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Embedding dimension constants
ULTRABERT_DIM = 768
CLUSTERED_DIM = 64


class EntityLike(Protocol):
    """Protocol for entity objects with name, type, category."""

    entity_id: str
    name: str
    entity_type: str
    category: str


# ─────────────────────────────────────────────────────────────────────────────
# UltraBERT Embedding Service (real ML embeddings)
# ─────────────────────────────────────────────────────────────────────────────


class UltraBERTEmbeddingService:
    """UltraBERT-backed 768-dim embedding service for BGT-SM.

    Uses the K0 ultrabert_adapter to generate real semantic embeddings.
    """

    def __init__(self) -> None:
        self.cache: Dict[str, List[float]] = {}
        self._client = None
        self._available: bool | None = None

    def _get_client(self):
        """Lazy-load UltraBERT client."""
        if self._client is None:
            try:
                from k0.runtime.ultrabert_adapter import get_ultrabert_client

                self._client = get_ultrabert_client()
                self._available = self._client is not None
            except ImportError:
                logger.warning("ultrabert_adapter not available")
                self._available = False
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if UltraBERT is available."""
        if self._available is None:
            self._get_client()
        return self._available or False

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        return ULTRABERT_DIM

    def embed_text(self, text: str) -> List[float]:
        """Embed raw text.

        Args:
            text: Text to embed.

        Returns:
            768-dimensional embedding vector.

        Raises:
            RuntimeError: If UltraBERT is not available.
        """
        if text in self.cache:
            return self.cache[text]

        client = self._get_client()
        if client is None:
            raise RuntimeError("UltraBERT not available for embedding")

        try:
            embedding = client.get_embedding(text)
            if embedding is None:
                raise RuntimeError(f"UltraBERT returned None for: {text[:50]}")
            self.cache[text] = list(embedding)
            return self.cache[text]
        except Exception as e:
            raise RuntimeError(f"UltraBERT embedding failed: {e}") from e

    def embed_entity(self, entity: EntityLike) -> List[float]:
        """Embed entity using name + type + category.

        Args:
            entity: Entity with name, entity_type, category attributes.

        Returns:
            768-dimensional embedding.
        """
        text = f"{entity.name} ({entity.entity_type}, {entity.category})"
        return self.embed_text(text)

    def embed_entities(self, entities: List[EntityLike]) -> Dict[str, List[float]]:
        """Embed multiple entities, returning entity_id -> embedding map."""
        result = {}
        for ent in entities:
            result[ent.entity_id] = self.embed_entity(ent)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Clustered Embedding Service (deterministic, no ML required)
# ─────────────────────────────────────────────────────────────────────────────


def _make_cluster_center(index: int, dim: int = CLUSTERED_DIM) -> List[float]:
    """Create a cluster center vector for a given category index.

    Uses a simple scheme: strong signal in a few dimensions based on index,
    with small values elsewhere for differentiation.
    """
    center = [0.1] * dim
    # Set a few dimensions to high values based on index
    primary_dims = [(index * 7 + i) % dim for i in range(5)]
    for d in primary_dims:
        center[d] = 0.8 + (index % 3) * 0.05
    # Normalize
    norm = math.sqrt(sum(x * x for x in center))
    return [x / norm for x in center]


class ClusteredEmbeddingService:
    """Deterministic clustered embeddings for CI and fast paths.

    Uses predefined cluster centers per category and adds small deterministic
    noise based on entity_id hash. No ML model required.
    """

    # 64-dimensional cluster centers (orthogonal-ish basis vectors)
    # Each category gets a unique center; entities within category cluster together
    CLUSTER_CENTERS: Dict[str, List[float]] = {
        "family": _make_cluster_center(0),
        "education": _make_cluster_center(1),
        "work": _make_cluster_center(2),
        "entertainment": _make_cluster_center(3),
        "finance": _make_cluster_center(4),
        "sports": _make_cluster_center(5),
        "health": _make_cluster_center(6),
        "social": _make_cluster_center(7),
        "travel": _make_cluster_center(8),
        "food": _make_cluster_center(9),
    }

    def __init__(self, dim: int = CLUSTERED_DIM, noise_scale: float = 0.1) -> None:
        self.dim = dim
        self.noise_scale = noise_scale
        self.cache: Dict[str, List[float]] = {}

    def _deterministic_noise(self, seed_str: str) -> List[float]:
        """Generate deterministic noise vector from string seed."""
        # Use hash to seed a simple PRNG
        h = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
        noise = []
        for i in range(self.dim):
            # Simple LCG-style pseudo-random
            h = (h * 1103515245 + 12345) & 0x7FFFFFFF
            # Map to [-1, 1]
            val = (h / 0x7FFFFFFF) * 2 - 1
            noise.append(val)
        return noise

    def embed_text(self, text: str, category: str | None = None) -> List[float]:
        """Embed text with optional category hint.

        Args:
            text: Text to embed (used for noise generation).
            category: Category for cluster center selection.

        Returns:
            64-dimensional embedding.
        """
        cache_key = f"{category}::{text}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Get cluster center (default to middle if unknown category)
        center = self.CLUSTER_CENTERS.get(category or "unknown", [0.5] * self.dim)

        # Add deterministic noise based on text
        noise = self._deterministic_noise(text)
        embedding = [c + n * self.noise_scale for c, n in zip(center, noise)]

        # Normalize to unit vector
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]

        self.cache[cache_key] = embedding
        return embedding

    def embed_entity(self, entity: EntityLike) -> List[float]:
        """Embed entity using its category for clustering.

        Args:
            entity: Entity with name, entity_type, category attributes.

        Returns:
            64-dimensional embedding.
        """
        text = f"{entity.name} ({entity.entity_type})"
        return self.embed_text(text, entity.category)

    def embed_entities(self, entities: List[EntityLike]) -> Dict[str, List[float]]:
        """Embed multiple entities, returning entity_id -> embedding map."""
        result = {}
        for ent in entities:
            result[ent.entity_id] = self.embed_entity(ent)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Factory function to get appropriate embedding service
# ─────────────────────────────────────────────────────────────────────────────


def get_embedding_service(
    use_ultrabert: bool | None = None,
) -> UltraBERTEmbeddingService | ClusteredEmbeddingService:
    """Get an embedding service instance.

    Args:
        use_ultrabert: If True, use UltraBERT (768-dim). If False, use clustered (64-dim).
                       If None, auto-detect: use UltraBERT if available, else clustered.

    Returns:
        Embedding service instance.
    """
    if use_ultrabert is None:
        # Auto-detect
        env_flag = os.getenv("R5_USE_ULTRABERT", "auto")
        if env_flag.lower() in ("1", "true", "yes"):
            use_ultrabert = True
        elif env_flag.lower() in ("0", "false", "no"):
            use_ultrabert = False
        else:
            # Try to use UltraBERT, fall back to clustered
            service = UltraBERTEmbeddingService()
            if service.is_available:
                logger.info("Using UltraBERT embeddings (768-dim)")
                return service
            logger.info("UltraBERT not available, using clustered embeddings (64-dim)")
            return ClusteredEmbeddingService()

    if use_ultrabert:
        service = UltraBERTEmbeddingService()
        if not service.is_available:
            raise RuntimeError("UltraBERT requested but not available")
        return service
    return ClusteredEmbeddingService()
