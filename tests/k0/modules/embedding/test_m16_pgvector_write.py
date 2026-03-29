"""Integration tests for M16 hipp_events_writer -- pgvector vec_write path.

Validates that M16 writes 768-dim float list vectors to st_vec via vec_write
syscall, and correctly handles the FK ordering (st_hipp_events FIRST, st_vec
SECOND). Also tests the PENDING fallback when no embedding data is present.

Epic: M4 4.21
Module: k0/modules/core/hipp_events_writer.py
Contract: k0/contracts/modules/core.hipp_events_writer.v1.yaml
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from k0.modules.core import hipp_events_writer
from tests.k0.modules.embedding.conftest import FakeContext, FakeMessage, FakeSyscalls

# =============================================================================
# Extended FakeSyscalls with M16-specific methods
# =============================================================================


class M16Syscalls(FakeSyscalls):
    """FakeSyscalls extended with pipeline_processed_upsert for M16."""

    def __init__(self) -> None:
        super().__init__()
        self.call_order: list[str] = []

    async def hipp_events_upsert(self, **kwargs: Any) -> dict[str, Any]:
        self.call_order.append("hipp_events_upsert")
        event_id = kwargs["event_id"]
        self.hipp_events[event_id] = kwargs
        return {"inserted": True, "event_id": event_id, "status": "OK"}

    async def vec_write(self, **kwargs: Any) -> dict[str, Any]:
        self.call_order.append("vec_write")
        embedding_id = kwargs["embedding_id"]
        self.vec_store[embedding_id] = kwargs
        return {"written": True}

    async def pipeline_processed_upsert(self, **kwargs: Any) -> dict[str, Any]:
        self.call_order.append("pipeline_processed_upsert")
        key = f"{kwargs['pipeline_id']}:{kwargs['wal_pos']}"
        self.pipeline_processed[key] = kwargs
        return {"inserted": True, "status": "OK"}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def m16_syscalls() -> M16Syscalls:
    return M16Syscalls()


@pytest.fixture()
def m16_context(m16_syscalls: M16Syscalls) -> FakeContext:
    ctx = FakeContext(syscalls=m16_syscalls)
    ctx.logger = logging.getLogger("test.m16")
    return ctx


@pytest.fixture()
def full_envelope() -> dict[str, Any]:
    """Envelope with M13 hipp_events_row and M22 extract_from_cache data."""
    return {
        "hipp_events_row": {
            "event_id": "evt_m16_001",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "wal_pos": 42,
            "embedding_id": "emb_m22_001",
            "event_text": "Mom picked up the kids from school today!",
        },
        "extract_from_cache": {
            "embedding": [0.01] * 768,
            "embedding_id": "emb_m22_001",
            "model_id": "ultrabert_v2.1.0",
            "vector_dim": 768,
            "source": "cache_hit",
        },
        "wal_pos": 42,
        "tenant_id": "tenant_test",
        "space_id": "space_home",
    }


@pytest.fixture()
def envelope_no_embedding() -> dict[str, Any]:
    """Envelope without embedding data (M22 cache miss)."""
    return {
        "hipp_events_row": {
            "event_id": "evt_m16_002",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "wal_pos": 43,
            "embedding_id": "emb_pending_002",
            "event_text": "Dad cooked dinner for the family.",
        },
        "wal_pos": 43,
        "tenant_id": "tenant_test",
        "space_id": "space_home",
    }


@pytest.fixture(autouse=True)
def _reset_m16_metrics() -> None:
    """Reset M16 metrics before each test."""
    hipp_events_writer.reset_metrics()


# =============================================================================
# Test Class 1: Vector Write Path
# =============================================================================


class TestM16VecWritePath:
    """Test M16 writes 768-dim vectors to st_vec via vec_write syscall."""

    @pytest.mark.asyncio
    async def test_vec_write_receives_768_float_list(
        self, m16_context: FakeContext, m16_syscalls: M16Syscalls, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        result = await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        assert result["hipp_events_write"]["embedding_written"] is True

        vec = m16_syscalls.vec_store["emb_m22_001"]
        assert len(vec["vector"]) == 768
        assert all(isinstance(v, float) for v in vec["vector"])
        assert vec["vector_dim"] == 768

    @pytest.mark.asyncio
    async def test_vec_write_uses_correct_model_id(
        self, m16_context: FakeContext, m16_syscalls: M16Syscalls, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        vec = m16_syscalls.vec_store["emb_m22_001"]
        assert vec["model_id"] == "ultrabert_v2.1.0"

    @pytest.mark.asyncio
    async def test_vec_write_status_is_ready(
        self, m16_context: FakeContext, m16_syscalls: M16Syscalls, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        vec = m16_syscalls.vec_store["emb_m22_001"]
        assert vec["status"] == "READY"

    @pytest.mark.asyncio
    async def test_vec_write_links_to_event_id(
        self, m16_context: FakeContext, m16_syscalls: M16Syscalls, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        vec = m16_syscalls.vec_store["emb_m22_001"]
        assert vec["event_id"] == "evt_m16_001"

    @pytest.mark.asyncio
    async def test_embeddings_written_metric_incremented(
        self, m16_context: FakeContext, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        metrics = hipp_events_writer.get_metrics()
        assert metrics["embeddings_written"] == 1


# =============================================================================
# Test Class 2: FK Ordering (Parent Before Child)
# =============================================================================


class TestM16FKOrdering:
    """M16 must write st_hipp_events FIRST, then st_vec SECOND."""

    @pytest.mark.asyncio
    async def test_hipp_events_written_before_vec(
        self, m16_context: FakeContext, m16_syscalls: M16Syscalls, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        # Verify syscall order: hipp_events_upsert BEFORE vec_write
        assert m16_syscalls.call_order.index("hipp_events_upsert") < m16_syscalls.call_order.index(
            "vec_write"
        )

    @pytest.mark.asyncio
    async def test_three_table_transaction_order(
        self, m16_context: FakeContext, m16_syscalls: M16Syscalls, full_envelope: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=full_envelope)

        assert m16_syscalls.call_order == [
            "hipp_events_upsert",
            "vec_write",
            "pipeline_processed_upsert",
        ]


# =============================================================================
# Test Class 3: PENDING Fallback (No Embedding)
# =============================================================================


class TestM16PendingFallback:
    """When no embedding data, M16 skips vec_write, sets PENDING for P08 backfill."""

    @pytest.mark.asyncio
    async def test_no_vec_write_without_embedding(
        self,
        m16_context: FakeContext,
        m16_syscalls: M16Syscalls,
        envelope_no_embedding: dict,
    ) -> None:
        message = FakeMessage()
        result = await hipp_events_writer.run(message, m16_context, envelope=envelope_no_embedding)

        assert result["hipp_events_write"]["embedding_written"] is False
        assert len(m16_syscalls.vec_store) == 0

    @pytest.mark.asyncio
    async def test_embeddings_skipped_metric(
        self, m16_context: FakeContext, envelope_no_embedding: dict
    ) -> None:
        message = FakeMessage()
        await hipp_events_writer.run(message, m16_context, envelope=envelope_no_embedding)

        metrics = hipp_events_writer.get_metrics()
        assert metrics["embeddings_skipped"] == 1

    @pytest.mark.asyncio
    async def test_hipp_events_still_written_without_embedding(
        self,
        m16_context: FakeContext,
        m16_syscalls: M16Syscalls,
        envelope_no_embedding: dict,
    ) -> None:
        message = FakeMessage()
        result = await hipp_events_writer.run(message, m16_context, envelope=envelope_no_embedding)

        assert result["hipp_events_write"]["hipp_events_inserted"] is True
        assert "evt_m16_002" in m16_syscalls.hipp_events
