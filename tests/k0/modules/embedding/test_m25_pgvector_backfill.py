"""Integration tests for M25 embedding.backfill -- pgvector-native backfill.

Exercises the real M25 module code end-to-end against FakeSyscalls.
No module-level mocking -- tests call backfill.run() with real logic and
verify that PENDING events are correctly backfilled with 768-dim vectors.

Epic: M4 4.21
Module: k0/modules/embedding/backfill.py
Contract: k0/contracts/modules/embedding.backfill.v2.yaml
"""

from __future__ import annotations

from typing import Any

import pytest

from k0.modules.embedding import backfill
from tests.k0.modules.embedding.conftest import FakeContext, FakeMessage, FakeSyscalls


@pytest.fixture(autouse=True)
def _reset_backfill_metrics() -> None:
    """Reset M25 metrics before each test."""
    backfill.reset_metrics()


# =============================================================================
# Test Class 1: Happy Path -- PENDING Events Backfilled
# =============================================================================


class TestM25HappyPath:
    """M25 queries PENDING events, computes embeddings, writes to st_vec."""

    @pytest.mark.asyncio
    async def test_backfill_pending_events(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        result = await backfill.run(message, context)

        assert result["backfilled_count"] == 5
        assert result["batch_size"] == 5
        assert result["completed"] is True

    @pytest.mark.asyncio
    async def test_backfill_writes_to_vec_store(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context)

        assert len(syscalls.vec_store) == 5

    @pytest.mark.asyncio
    async def test_backfill_vectors_are_768_dim(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context)

        for vec_row in syscalls.vec_store.values():
            assert len(vec_row["vector"]) == 768
            assert vec_row["vector_dim"] == 768

    @pytest.mark.asyncio
    async def test_backfill_updates_embedding_status_to_ready(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context)

        for event in syscalls.hipp_events.values():
            assert event["embedding_status"] == "READY"

    @pytest.mark.asyncio
    async def test_backfill_uses_ultrabert_model(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context)

        for vec_row in syscalls.vec_store.values():
            assert vec_row["model_id"] == "ultrabert_v2.1.0"

    @pytest.mark.asyncio
    async def test_backfill_vec_links_to_event_id(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context)

        vec_event_ids = {v["event_id"] for v in syscalls.vec_store.values()}
        event_ids = {e["event_id"] for e in sample_events}
        assert vec_event_ids == event_ids


# =============================================================================
# Test Class 2: Empty Batch -- No PENDING Events
# =============================================================================


class TestM25EmptyBatch:
    """M25 handles empty batch gracefully (no PENDING events to process)."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_zero(
        self,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        # No events seeded -- store is empty
        result = await backfill.run(message, context)

        assert result["backfilled_count"] == 0
        assert result["completed"] is True

    @pytest.mark.asyncio
    async def test_empty_batch_no_vec_writes(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        result = await backfill.run(message, context)

        assert len(syscalls.vec_store) == 0
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_empty_batch_metric(
        self,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        await backfill.run(message, context)

        metrics = backfill.get_metrics()
        assert metrics["empty_batches"] == 1


# =============================================================================
# Test Class 3: Batch Size Configuration
# =============================================================================


class TestM25BatchSize:
    """M25 respects batch_size config from stage config or context."""

    @pytest.mark.asyncio
    async def test_batch_size_from_config(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        # Request batch_size=2 -- should only process 2 of 5
        result = await backfill.run(message, context, batch_size=2)

        assert result["backfilled_count"] == 2
        assert result["batch_size"] == 2

    @pytest.mark.asyncio
    async def test_batch_size_default_is_100(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        # With 5 events and default batch_size=100, all 5 get processed
        result = await backfill.run(message, context)
        assert result["backfilled_count"] == 5


# =============================================================================
# Test Class 4: Event Emission
# =============================================================================


class TestM25EventEmission:
    """M25 emits cognitive.embedding.backfilled.v1 event when configured."""

    @pytest.mark.asyncio
    async def test_event_emitted_when_enabled(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context, emit_completion_event=True)

        assert len(syscalls.emitted_events) == 1
        event = syscalls.emitted_events[0]
        assert event["topic"] == "cognitive.embedding.backfilled.v1"
        assert event["payload"]["backfilled_count"] == 5

    @pytest.mark.asyncio
    async def test_no_event_when_disabled(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await backfill.run(message, context, emit_completion_event=False)
        assert len(syscalls.emitted_events) == 0

    @pytest.mark.asyncio
    async def test_no_event_on_empty_batch(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        await backfill.run(message, context, emit_completion_event=True)
        assert len(syscalls.emitted_events) == 0


# =============================================================================
# Test Class 5: Envelope-Scoped Backfill (Event-Triggered Mode)
# =============================================================================


class TestM25EnvelopeScoped:
    """M25 scopes backfill to tenant/space from envelope payload."""

    @pytest.mark.asyncio
    async def test_scoped_to_tenant(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
    ) -> None:
        # Seed events for two tenants
        syscalls.hipp_events["evt_t1"] = {
            "event_id": "evt_t1",
            "tenant_id": "tenant_a",
            "space_id": "space_home",
            "event_text": "Tenant A event",
            "embedding_status": "PENDING",
        }
        syscalls.hipp_events["evt_t2"] = {
            "event_id": "evt_t2",
            "tenant_id": "tenant_b",
            "space_id": "space_home",
            "event_text": "Tenant B event",
            "embedding_status": "PENDING",
        }

        envelope = {"payload": {"tenant_id": "tenant_a", "space_id": "space_home"}}
        message = FakeMessage()
        result = await backfill.run(message, context, envelope=envelope)

        # Only tenant_a event should be backfilled
        assert result["backfilled_count"] == 1


# =============================================================================
# Test Class 6: Skip Events Without Text
# =============================================================================


class TestM25SkipEmptyText:
    """M25 skips events with no event_text (nothing to embed)."""

    @pytest.mark.asyncio
    async def test_skip_empty_text_event(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        syscalls.hipp_events["evt_no_text"] = {
            "event_id": "evt_no_text",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "event_text": "",
            "embedding_status": "PENDING",
        }

        result = await backfill.run(message, context)
        assert result["backfilled_count"] == 0
        assert len(syscalls.vec_store) == 0
