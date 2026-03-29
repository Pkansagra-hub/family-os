"""Tests for CentroidRecomputer (M9.6 D9)."""

from __future__ import annotations

import asyncio
import struct
from typing import Any, Sequence

import numpy as np

from k0.modules.consolidation.reconciliation.hooks.centroid_recompute import (
    VECTOR_BYTES,
    VECTOR_DIM,
    CentroidRecomputer,
    CentroidResult,
    ndarray_to_bytes,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _make_embedding(dim: int = 768) -> np.ndarray:
    rng = np.random.default_rng(42)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeCentroidCalculator:
    """Mimics CentroidCalculator.compute()."""

    def __init__(self, centroid: np.ndarray | None = None, variance: float = 0.05):
        self._centroid = centroid if centroid is not None else _make_embedding()
        self._variance = variance
        self.calls: list[dict] = []

    def compute(self, events: Sequence, strategy: str | None = None):
        self.calls.append({"event_count": len(events), "strategy": strategy})
        s = strategy or "hybrid"
        c = self._centroid
        v = self._variance
        n = len(events)

        class _Result:
            centroid = c
            variance = v
            weights = np.ones(n, dtype=np.float32)
            event_count = n

        _Result.strategy = s
        return _Result()


class FakeEmbeddingGenerator:
    """Mimics EmbeddingGenerator.generate()."""

    def __init__(self, vector: np.ndarray | None = None, model: str = "ultrabert-v2.1.0"):
        self._vector = vector if vector is not None else _make_embedding()
        self._model = model
        self.calls: list[str] = []

    async def generate(self, text: str):
        self.calls.append(text)
        vector_bytes = ndarray_to_bytes(self._vector)

        class _Result:
            vector_bytes_val = vector_bytes
            model_id = self._model
            dimension = VECTOR_DIM

        _Result.vector_bytes = _Result.vector_bytes_val
        return _Result()


class FakeEventEmbeddingFetcher:
    """Returns pre-built event embedding rows."""

    def __init__(self, rows: list[dict[str, Any]] | None = None):
        if rows is None:
            emb = _make_embedding()
            self._rows = [
                {
                    "event_id": "ev-1",
                    "embedding_768": emb.tolist(),
                    "importance_score": 0.8,
                    "conversation_anchor_ms": 1710500000000,
                },
            ]
        else:
            self._rows = rows
        self.calls: list[list[str]] = []

    async def fetch(self, event_ids, conn):
        self.calls.append(event_ids)
        return self._rows


# ===========================================================================
# Test: ndarray_to_bytes
# ===========================================================================


class TestNdarrayToBytes:
    def test_correct_length(self) -> None:
        v = _make_embedding()
        b = ndarray_to_bytes(v)
        assert len(b) == VECTOR_BYTES

    def test_roundtrip(self) -> None:
        v = _make_embedding()
        b = ndarray_to_bytes(v)
        restored = np.array(struct.unpack(f"<{VECTOR_DIM}f", b), dtype=np.float32)
        np.testing.assert_array_almost_equal(v, restored, decimal=6)

    def test_zero_vector(self) -> None:
        v = np.zeros(VECTOR_DIM, dtype=np.float32)
        b = ndarray_to_bytes(v)
        assert len(b) == VECTOR_BYTES
        assert all(x == 0 for x in b)


# ===========================================================================
# Test: CentroidResult
# ===========================================================================


class TestCentroidResult:
    def test_fields(self) -> None:
        v = ndarray_to_bytes(_make_embedding())
        r = CentroidResult(
            embedding_vector=v,
            embedding_model="ultrabert-v2.1.0",
            centroid_variance=0.05,
            strategy_used="hybrid",
            member_count=5,
        )
        assert len(r.embedding_vector) == VECTOR_BYTES
        assert r.member_count == 5
        assert r.strategy_used == "hybrid"


# ===========================================================================
# Test: CentroidRecomputer — episodic layer
# ===========================================================================


class TestCentroidRecomputerEpisodic:
    def test_episodic_uses_centroid_calculator(self) -> None:
        calc = FakeCentroidCalculator()
        fetcher = FakeEventEmbeddingFetcher()
        recomp = CentroidRecomputer(
            centroid_calculator=calc,
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=fetcher,
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute(
                layer="st_epi",
                record_id="ep-1",
                spec=None,
                source_event_ids=["ev-1"],
                embedding_text="some text",
            )
        )
        assert result is not None
        assert result.member_count == 1
        assert len(result.embedding_vector) == VECTOR_BYTES
        assert calc.calls[0]["event_count"] == 1

    def test_episodic_fetches_event_embeddings(self) -> None:
        fetcher = FakeEventEmbeddingFetcher()
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=fetcher,
        )
        asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_epi", "ep-1", None, ["ev-1", "ev-2"], "text")
        )
        assert fetcher.calls == [["ev-1", "ev-2"]]

    def test_episodic_no_events_returns_none(self) -> None:
        fetcher = FakeEventEmbeddingFetcher(rows=[])
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=fetcher,
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_epi", "ep-1", None, [], "text")
        )
        assert result is not None
        assert result.embedding_vector is None

    def test_episodic_variance_captured(self) -> None:
        calc = FakeCentroidCalculator(variance=0.123)
        fetcher = FakeEventEmbeddingFetcher()
        recomp = CentroidRecomputer(
            centroid_calculator=calc,
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=fetcher,
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_epi", "ep-1", None, ["ev-1"], "text")
        )
        assert result is not None
        assert result.centroid_variance == 0.123

    def test_episodic_multiple_events(self) -> None:
        emb1 = _make_embedding()
        emb2 = _make_embedding()
        rows = [
            {
                "event_id": "ev-1",
                "embedding_768": emb1.tolist(),
                "importance_score": 0.8,
                "conversation_anchor_ms": 1000,
            },
            {
                "event_id": "ev-2",
                "embedding_768": emb2.tolist(),
                "importance_score": 0.6,
                "conversation_anchor_ms": 2000,
            },
        ]
        fetcher = FakeEventEmbeddingFetcher(rows=rows)
        calc = FakeCentroidCalculator()
        recomp = CentroidRecomputer(
            centroid_calculator=calc,
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=fetcher,
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_epi", "ep-1", None, ["ev-1", "ev-2"], "text")
        )
        assert result is not None
        assert calc.calls[0]["event_count"] == 2


# ===========================================================================
# Test: CentroidRecomputer — non-episodic layers
# ===========================================================================


class TestCentroidRecomputerGeneric:
    def test_text_based_uses_embedding_generator(self) -> None:
        gen = FakeEmbeddingGenerator()
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=gen,
            event_fetcher=FakeEventEmbeddingFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_sem", "sem-1", None, ["ev-1"], "semantic text")
        )
        assert result is not None
        assert gen.calls == ["semantic text"]
        assert result.strategy_used == "text_embed"

    def test_text_based_no_embedding_text_returns_none(self) -> None:
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=FakeEventEmbeddingFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_sem", "sem-1", None, ["ev-1"], None)
        )
        assert result is not None
        assert result.embedding_vector is None

    def test_text_based_empty_embedding_text_returns_none(self) -> None:
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=FakeEmbeddingGenerator(),
            event_fetcher=FakeEventEmbeddingFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_sem", "sem-1", None, ["ev-1"], "")
        )
        assert result is not None
        assert result.embedding_vector is None

    def test_procedural_uses_text_based(self) -> None:
        gen = FakeEmbeddingGenerator()
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=gen,
            event_fetcher=FakeEventEmbeddingFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_procedural", "rout-1", None, ["ev-1"], "routine text")
        )
        assert result is not None
        assert gen.calls == ["routine text"]

    def test_social_uses_text_based(self) -> None:
        gen = FakeEmbeddingGenerator()
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=gen,
            event_fetcher=FakeEventEmbeddingFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_social", "soc-1", None, ["ev-1"], "social text")
        )
        assert result is not None
        assert gen.calls == ["social text"]


# ===========================================================================
# Test: CentroidRecomputer — no generator
# ===========================================================================


class TestCentroidRecomputerNoGenerator:
    def test_no_generator_non_episodic_returns_none(self) -> None:
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=None,
            event_fetcher=FakeEventEmbeddingFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_sem", "sem-1", None, ["ev-1"], "some text")
        )
        assert result is not None
        assert result.embedding_vector is None

    def test_no_generator_episodic_still_works(self) -> None:
        """Episodic path uses CentroidCalculator, not EmbeddingGenerator."""
        fetcher = FakeEventEmbeddingFetcher()
        recomp = CentroidRecomputer(
            centroid_calculator=FakeCentroidCalculator(),
            embedding_generator=None,
            event_fetcher=fetcher,
        )
        result = asyncio.get_event_loop().run_until_complete(
            recomp.recompute("st_epi", "ep-1", None, ["ev-1"], "text")
        )
        assert result is not None


# ===========================================================================
# Test: vector bytes constant
# ===========================================================================


class TestVectorConstants:
    def test_dim(self) -> None:
        assert VECTOR_DIM == 768

    def test_bytes(self) -> None:
        assert VECTOR_BYTES == 768 * 4
