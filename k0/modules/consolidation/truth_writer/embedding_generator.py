"""
EmbeddingGenerator - GAP-001 Milestone 3 (Issue 3.2)

Generates 768-dim embeddings using UltraBERT.
Returns BYTEA-compatible bytes for inline storage in truth layers.

GAP Reference: GAP_001 Section 5.5 (Inline Vectors)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_3_R7_WRITER_UPDATES.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class GeneratedEmbedding:
    """
    Result of embedding generation.

    Attributes:
        vector_bytes: 768 × 4 = 3072 bytes (float32 as BYTEA)
        model_id: Model version identifier (e.g., "ultrabert-v2.1.0")
        dimension: Vector dimension (768 for UltraBERT)
    """

    vector_bytes: bytes
    model_id: str
    dimension: int

    def to_numpy(self) -> np.ndarray:
        """Convert bytes back to numpy array."""
        return np.frombuffer(self.vector_bytes, dtype=np.float32)


class EmbeddingGenerator:
    """
    Generates embeddings using UltraBERT.

    Wraps the UltraBERT client to produce 768-dimensional embeddings
    as BYTEA-compatible bytes for inline storage in truth layer tables.

    Usage:
        generator = EmbeddingGenerator()
        result = await generator.generate("Family dinner at home")
        print(len(result.vector_bytes))  # 3072 (768 × 4 bytes)
    """

    MODEL_ID = "ultrabert-v2.1.0"
    DIMENSION = 768
    BYTES_PER_VECTOR = DIMENSION * 4  # 3072 bytes for float32

    # Maximum text length before truncation (BERT limit ~512 tokens ≈ 2000 chars)
    MAX_TEXT_LENGTH = 2000

    def __init__(
        self,
        get_embedding_fn: Optional[Callable[[str], Optional[List[float]]]] = None,
    ):
        """
        Initialize with optional custom embedding function.

        Args:
            get_embedding_fn: Optional function that takes text and returns
                              768-dim float list. If None, uses UltraBERT.
        """
        self._get_embedding_fn = get_embedding_fn

    def _get_ultrabert_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from UltraBERT adapter."""
        # Import here to avoid circular imports and allow mocking
        try:
            from k0.runtime.ultrabert_adapter import get_embedding

            return get_embedding(text)
        except ImportError:
            logger.warning("UltraBERT adapter not available")
            return None
        except Exception as e:
            logger.error(f"UltraBERT embedding failed: {e}")
            return None

    async def generate(self, text: str) -> Optional[GeneratedEmbedding]:
        """
        Generate embedding for text.

        Args:
            text: Text to embed (max ~512 tokens for BERT)

        Returns:
            GeneratedEmbedding with vector bytes, or None on failure
        """
        if not text or not text.strip():
            logger.debug("EmbeddingGenerator: empty text, skipping")
            return None

        # Truncate if too long
        if len(text) > self.MAX_TEXT_LENGTH:
            logger.debug(
                f"EmbeddingGenerator: truncating text from {len(text)} to {self.MAX_TEXT_LENGTH} chars"
            )
            text = text[: self.MAX_TEXT_LENGTH]

        # Get embedding using configured function or UltraBERT
        try:
            if self._get_embedding_fn:
                embedding = self._get_embedding_fn(text)
            else:
                embedding = self._get_ultrabert_embedding(text)
        except Exception as e:
            logger.error(f"EmbeddingGenerator: embedding failed: {e}")
            return None

        if embedding is None:
            return None

        # Validate dimension
        if len(embedding) != self.DIMENSION:
            logger.error(
                f"EmbeddingGenerator: unexpected dimension {len(embedding)}, expected {self.DIMENSION}"
            )
            return None

        # Convert to bytes
        vector_bytes = self.vector_to_bytes(embedding)

        return GeneratedEmbedding(
            vector_bytes=vector_bytes,
            model_id=self.MODEL_ID,
            dimension=self.DIMENSION,
        )

    def generate_sync(self, text: str) -> Optional[GeneratedEmbedding]:
        """
        Synchronous version of generate().

        For use in non-async contexts. Same behavior as generate().
        """
        if not text or not text.strip():
            return None

        if len(text) > self.MAX_TEXT_LENGTH:
            text = text[: self.MAX_TEXT_LENGTH]

        try:
            if self._get_embedding_fn:
                embedding = self._get_embedding_fn(text)
            else:
                embedding = self._get_ultrabert_embedding(text)
        except Exception as e:
            logger.error(f"EmbeddingGenerator: embedding failed: {e}")
            return None

        if embedding is None:
            return None

        if len(embedding) != self.DIMENSION:
            logger.error(
                f"EmbeddingGenerator: unexpected dimension {len(embedding)}, expected {self.DIMENSION}"
            )
            return None

        vector_bytes = self.vector_to_bytes(embedding)

        return GeneratedEmbedding(
            vector_bytes=vector_bytes,
            model_id=self.MODEL_ID,
            dimension=self.DIMENSION,
        )

    @staticmethod
    def vector_to_bytes(vector: List[float]) -> bytes:
        """
        Convert float list to BYTEA-compatible bytes.

        Args:
            vector: List of floats (768-dim)

        Returns:
            3072 bytes (768 × 4 bytes per float32)
        """
        arr = np.array(vector, dtype=np.float32)
        return arr.tobytes()

    @staticmethod
    def bytes_to_vector(data: bytes) -> np.ndarray:
        """
        Convert BYTEA bytes back to numpy array.

        Args:
            data: 3072 bytes of float32 data

        Returns:
            768-dimensional numpy array
        """
        return np.frombuffer(data, dtype=np.float32)

    @staticmethod
    def bytes_to_list(data: bytes) -> List[float]:
        """
        Convert BYTEA bytes back to Python list.

        Args:
            data: 3072 bytes of float32 data

        Returns:
            768-element list of floats
        """
        arr = np.frombuffer(data, dtype=np.float32)
        return arr.tolist()
