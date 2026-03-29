"""CentroidRecomputer -- recomputes centroid embeddings for truth records (M9.6).

Two paths:
  1. EPISODIC (st_epi): Weighted mean centroid from member event embeddings.
  2. NON-EPISODIC: Re-embed the embedding_text via UltraBERT.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

VECTOR_DIM = 768
VECTOR_BYTES = VECTOR_DIM * 4  # float32


class CentroidCalculatorLike(Protocol):
    """Minimal interface matching CentroidCalculator.compute()."""

    def compute(self, events: Any, strategy: str | None = None) -> Any: ...


class EmbeddingGeneratorLike(Protocol):
    """Minimal interface matching EmbeddingGenerator.generate()."""

    async def generate(self, text: str) -> Any: ...


class EventEmbeddingFetcherLike(Protocol):
    """Fetches event embeddings from st_hipp_events for centroid computation."""

    async def fetch(self, event_ids: list[str], conn: Any) -> list[dict[str, Any]]: ...


class DefaultEventEmbeddingFetcher:
    """Fetches event_id + embedding_768 from st_hipp_events."""

    async def fetch(self, event_ids: list[str], conn: Any) -> list[dict[str, Any]]:
        if not event_ids:
            return []
        placeholders = ", ".join(f"${i + 1}" for i in range(len(event_ids)))
        sql = (
            "SELECT event_id, embedding_768, importance_score, "
            "conversation_anchor_ms "
            f"FROM st_hipp_events WHERE event_id IN ({placeholders})"  # noqa: S608
        )
        rows = await conn.fetch(sql, *event_ids)
        return [dict(r) for r in rows]


@dataclass
class CentroidResult:
    """Result of centroid recomputation."""

    embedding_vector: bytes | None  # 3072 bytes (768 x float32), or None
    embedding_model: str | None
    centroid_variance: float | None
    strategy_used: str
    member_count: int


def ndarray_to_bytes(arr: Any) -> bytes:
    """Convert numpy ndarray (float32, 768-dim) to bytes."""
    return struct.pack(f"{VECTOR_DIM}f", *arr.flat[:VECTOR_DIM])


class CentroidRecomputer:
    """Recomputes centroid embedding for truth records after R7 writes.

    EPISODIC: Weighted mean centroid from member event embeddings
              via CentroidCalculator.compute(strategy="hybrid").
    NON-EPISODIC: Re-embed the updated embedding_text via EmbeddingGenerator.

    REINFORCE on non-episodic: skipped if no new embedding_text provided
    (embedding_text unchanged -> no point re-embedding).
    EVOLVE: Fresh centroid for NEW record only.
    """

    def __init__(
        self,
        centroid_calculator: CentroidCalculatorLike | None = None,
        embedding_generator: EmbeddingGeneratorLike | None = None,
        event_fetcher: EventEmbeddingFetcherLike | None = None,
    ) -> None:
        self._centroid_calc = centroid_calculator
        self._embedding_gen = embedding_generator
        self._event_fetcher = event_fetcher or DefaultEventEmbeddingFetcher()

    async def recompute(
        self,
        layer: str,
        record_id: str,
        spec: Any,
        source_event_ids: list[str],
        embedding_text: str | None = None,
        conn: Any = None,
    ) -> CentroidResult:
        """Recompute embedding for a truth record.

        For st_epi: weighted mean of member event embeddings.
        For others: re-embed the embedding_text via EmbeddingGenerator.
        """
        if layer == "st_epi":
            return await self._recompute_episodic(source_event_ids, conn)
        return await self._recompute_text_based(embedding_text)

    async def _recompute_episodic(
        self,
        source_event_ids: list[str],
        conn: Any,
    ) -> CentroidResult:
        if self._centroid_calc is None:
            logger.warning("No CentroidCalculator configured; skipping episodic centroid")
            return CentroidResult(
                embedding_vector=None,
                embedding_model=None,
                centroid_variance=None,
                strategy_used="skipped",
                member_count=0,
            )

        event_rows = await self._event_fetcher.fetch(source_event_ids, conn)
        if not event_rows:
            return CentroidResult(
                embedding_vector=None,
                embedding_model=None,
                centroid_variance=None,
                strategy_used="no_events",
                member_count=0,
            )

        # Filter to events that have embeddings
        events_with_embeddings = [r for r in event_rows if r.get("embedding_768") is not None]
        if not events_with_embeddings:
            return CentroidResult(
                embedding_vector=None,
                embedding_model=None,
                centroid_variance=None,
                strategy_used="no_embeddings",
                member_count=0,
            )

        calc_result = self._centroid_calc.compute(events_with_embeddings, strategy="hybrid")

        vector_bytes = ndarray_to_bytes(calc_result.centroid)

        return CentroidResult(
            embedding_vector=vector_bytes,
            embedding_model="ultrabert-v2.1.0",
            centroid_variance=calc_result.variance,
            strategy_used=calc_result.strategy,
            member_count=calc_result.event_count,
        )

    async def _recompute_text_based(
        self,
        embedding_text: str | None,
    ) -> CentroidResult:
        if not embedding_text:
            return CentroidResult(
                embedding_vector=None,
                embedding_model=None,
                centroid_variance=None,
                strategy_used="text_embed_skipped",
                member_count=0,
            )

        if self._embedding_gen is None:
            logger.warning("No EmbeddingGenerator configured; skipping text-based centroid")
            return CentroidResult(
                embedding_vector=None,
                embedding_model=None,
                centroid_variance=None,
                strategy_used="skipped",
                member_count=0,
            )

        embedding = await self._embedding_gen.generate(embedding_text)
        if embedding is None:
            return CentroidResult(
                embedding_vector=None,
                embedding_model=None,
                centroid_variance=None,
                strategy_used="text_embed_failed",
                member_count=0,
            )

        return CentroidResult(
            embedding_vector=embedding.vector_bytes,
            embedding_model=embedding.model_id,
            centroid_variance=None,
            strategy_used="text_embed",
            member_count=1,
        )
