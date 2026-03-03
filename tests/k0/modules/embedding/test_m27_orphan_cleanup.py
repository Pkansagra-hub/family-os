"""Integration tests for M27 embedding.cleanup -- orphan deletion.

Exercises the real M27 module code against FakeSyscalls.
Validates orphan detection, batch deletion, dry-run mode, and event emission.

Epic: M4 4.21
Module: k0/modules/embedding/cleanup.py
Contract: k0/contracts/modules/embedding.cleanup.v2.yaml
"""

from __future__ import annotations

from typing import Any

import pytest

from k0.modules.embedding import cleanup
from tests.k0.modules.embedding.conftest import FakeContext, FakeMessage, FakeSyscalls


@pytest.fixture(autouse=True)
def _reset_cleanup_metrics() -> None:
    """Reset M27 metrics before each test."""
    cleanup.reset_metrics()


@pytest.fixture()
def orphaned_vectors(syscalls: FakeSyscalls) -> list[str]:
    """Seed 3 orphaned vectors (event_id not in hipp_events)."""
    orphan_ids = []
    for i in range(3):
        emb_id = f"orphan_emb_{i:03d}"
        syscalls.vec_store[emb_id] = {
            "embedding_id": emb_id,
            "event_id": f"deleted_evt_{i:03d}",  # no matching hipp_event
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "vector": [0.01] * 768,
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "status": "READY",
        }
        orphan_ids.append(emb_id)
    return orphan_ids


# =============================================================================
# Test Class 1: Orphan Detection and Deletion
# =============================================================================


class TestM27OrphanDeletion:
    """M27 finds and deletes orphaned st_vec rows."""

    @pytest.mark.asyncio
    async def test_orphans_deleted(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        result = await cleanup.run(message, context)

        assert result["cleaned_count"] == 3
        assert result["completed"] is True

    @pytest.mark.asyncio
    async def test_orphans_removed_from_vec_store(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        await cleanup.run(message, context)

        for orphan_id in orphaned_vectors:
            assert orphan_id not in syscalls.vec_store

    @pytest.mark.asyncio
    async def test_valid_vectors_preserved(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
        orphaned_vectors: list[str],
    ) -> None:
        # sample_vectors has 3 valid vectors with matching hipp_events
        # orphaned_vectors has 3 orphans -- only orphans should be deleted
        await cleanup.run(message, context)

        assert len(syscalls.vec_store) == 3  # valid vectors preserved


# =============================================================================
# Test Class 2: Empty Batch -- No Orphans
# =============================================================================


class TestM27EmptyBatch:
    """M27 handles no-orphans case gracefully."""

    @pytest.mark.asyncio
    async def test_no_orphans_returns_zero(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        # sample_vectors fixture has no orphans
        result = await cleanup.run(message, context)

        assert result["cleaned_count"] == 0
        assert result["completed"] is True
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_empty_batch_metric(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        await cleanup.run(message, context)

        metrics = cleanup.get_metrics()
        assert metrics["empty_batches"] == 1


# =============================================================================
# Test Class 3: Dry Run Mode
# =============================================================================


class TestM27DryRun:
    """M27 dry_run counts orphans but does not delete."""

    @pytest.mark.asyncio
    async def test_dry_run_no_deletes(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        result = await cleanup.run(message, context, dry_run=True)

        assert result["dry_run"] is True
        assert result["cleaned_count"] == 0
        assert result["remaining"] == 3  # orphans still there

    @pytest.mark.asyncio
    async def test_dry_run_preserves_vectors(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        await cleanup.run(message, context, dry_run=True)

        for orphan_id in orphaned_vectors:
            assert orphan_id in syscalls.vec_store


# =============================================================================
# Test Class 4: Batch Size Limiting
# =============================================================================


class TestM27BatchSize:
    """M27 respects batch_size limit for safety."""

    @pytest.mark.asyncio
    async def test_batch_size_limits_deletes(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        # 3 orphans but batch_size=1 -- only delete 1
        result = await cleanup.run(message, context, batch_size=1)

        assert result["cleaned_count"] == 1
        assert result["completed"] is False
        assert result["remaining"] == 2


# =============================================================================
# Test Class 5: Event Emission
# =============================================================================


class TestM27EventEmission:
    """M27 emits cognitive.embedding.cleaned.v1 event."""

    @pytest.mark.asyncio
    async def test_event_emitted_on_cleanup(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        await cleanup.run(message, context, emit_cleaned_event=True)

        assert len(syscalls.emitted_events) == 1
        event = syscalls.emitted_events[0]
        assert event["topic"] == "cognitive.embedding.cleaned.v1"
        assert event["payload"]["cleaned_count"] == 3

    @pytest.mark.asyncio
    async def test_no_event_on_zero_cleaned(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        await cleanup.run(message, context, emit_cleaned_event=True)
        assert len(syscalls.emitted_events) == 0


# =============================================================================
# Test Class 6: Return Value Contract
# =============================================================================


class TestM27ReturnContract:
    """M27 return dict matches cleanup module contract."""

    @pytest.mark.asyncio
    async def test_return_keys(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        orphaned_vectors: list[str],
    ) -> None:
        result = await cleanup.run(message, context)

        assert "cleaned_count" in result
        assert "batch_size" in result
        assert "remaining" in result
        assert "completed" in result
        assert "dry_run" in result
