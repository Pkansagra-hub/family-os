"""Shared fixtures for K0 embedding module integration tests.

Provides FakeSyscalls with in-memory state, FakeContext, and FakeMessage.
These are principled test doubles (fakes) with real behavior, not mocks.
Tests exercise real module code end-to-end against in-memory storage.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import pytest

# =============================================================================
# FakeSyscalls -- in-memory storage backend
# =============================================================================


class FakeSyscalls:
    """In-memory syscall implementation backed by dict storage.

    Every method mirrors the real syscall interface but stores data
    in plain dicts. Tests seed data via direct attribute access, then
    call real module functions, then inspect the dict state.
    """

    def __init__(self) -> None:
        self.hipp_events: dict[str, dict[str, Any]] = {}
        self.vec_store: dict[str, dict[str, Any]] = {}
        self.pipeline_processed: dict[str, dict[str, Any]] = {}
        self.emitted_events: list[dict[str, Any]] = []

    # -- st_hipp_events -------------------------------------------------------

    async def hipp_events_query(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
        embedding_status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        events = [
            e
            for e in self.hipp_events.values()
            if (not tenant_id or e.get("tenant_id") == tenant_id)
            and (not space_id or e.get("space_id") == space_id)
            and (not embedding_status or e.get("embedding_status") == embedding_status)
        ]
        return {"events": events[:limit], "total_count": len(events)}

    async def hipp_events_update_embedding_status(
        self, event_id: str, embedding_status: str
    ) -> dict[str, Any]:
        if event_id in self.hipp_events:
            self.hipp_events[event_id]["embedding_status"] = embedding_status
        return {"updated": True}

    async def hipp_events_upsert(self, **kwargs: Any) -> dict[str, Any]:
        event_id = kwargs["event_id"]
        self.hipp_events[event_id] = kwargs
        return {"inserted": True, "event_id": event_id}

    async def hipp_events_missing_vectors(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        vec_event_ids = {row["event_id"] for row in self.vec_store.values()}
        count = sum(
            1
            for e in self.hipp_events.values()
            if e.get("embedding_status") == "READY" and e["event_id"] not in vec_event_ids
        )
        return {"count": count}

    async def hipp_events_reset_missing_embedding_status(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        vec_event_ids = {row["event_id"] for row in self.vec_store.values()}
        updated = 0
        for e in self.hipp_events.values():
            if e.get("embedding_status") == "READY" and e["event_id"] not in vec_event_ids:
                e["embedding_status"] = "PENDING"
                updated += 1
        return {"updated_count": updated}

    # -- st_vec ---------------------------------------------------------------

    async def vec_write(
        self,
        embedding_id: str,
        event_id: str,
        tenant_id: str,
        space_id: str,
        vector: list[float],
        vector_dim: int,
        model_id: str,
        status: str,
    ) -> dict[str, Any]:
        self.vec_store[embedding_id] = {
            "embedding_id": embedding_id,
            "event_id": event_id,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "vector": vector,
            "vector_dim": vector_dim,
            "model_id": model_id,
            "status": status,
        }
        return {"written": True}

    async def vec_count(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        return {"count": len(self.vec_store)}

    async def vec_orphan_count(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        orphans = [
            eid for eid, row in self.vec_store.items() if row["event_id"] not in self.hipp_events
        ]
        return {"count": len(orphans)}

    async def vec_delete_orphans(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        orphan_ids = [
            eid for eid, row in self.vec_store.items() if row["event_id"] not in self.hipp_events
        ][:limit]
        for eid in orphan_ids:
            del self.vec_store[eid]
        return {"deleted_count": len(orphan_ids)}

    async def vec_count_dimension_mismatches(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
        expected_dim: int = 768,
    ) -> dict[str, Any]:
        count = sum(1 for row in self.vec_store.values() if row["vector_dim"] != expected_dim)
        return {"count": count}

    async def vec_distinct_models(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        models = list({row["model_id"] for row in self.vec_store.values()})
        return {"models": models}

    # -- UltraBERT embedding --------------------------------------------------

    async def ultrabert_embed(
        self, text: str, model_id: str = "ultrabert_v2.1.0"
    ) -> dict[str, Any]:
        # Deterministic 768-dim embedding from text hash
        h = hashlib.md5(text.encode()).hexdigest()
        seed = int(h[:8], 16) / 0xFFFFFFFF
        embedding = [round(seed * (i + 1) % 1.0, 6) for i in range(768)]
        return {
            "embedding": embedding,
            "embedding_id": f"emb_{h[:16]}",
        }

    # -- Outbox ---------------------------------------------------------------

    async def outbox_emit_batch(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        self.emitted_events.extend(events)
        return {"emitted": len(events)}


# =============================================================================
# FakeContext -- execution context
# =============================================================================


class FakeContext:
    """Lightweight execution context with real logger and fake syscalls."""

    def __init__(
        self,
        syscalls: FakeSyscalls,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.syscalls = syscalls
        self.logger = logging.getLogger("test.embedding")
        self.config = config or {}


# =============================================================================
# FakeMessage -- bus message
# =============================================================================


class FakeMessage:
    """Lightweight bus message with payload and trace_id."""

    def __init__(
        self,
        payload: bytes | str | dict | None = None,
        trace_id: str = "test-trace-001",
    ) -> None:
        if payload is None:
            self.payload = b"{}"
        elif isinstance(payload, dict):
            import json

            self.payload = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            self.payload = payload.encode("utf-8")
        else:
            self.payload = payload
        self.trace_id = trace_id


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def syscalls() -> FakeSyscalls:
    """Fresh FakeSyscalls instance with empty stores."""
    return FakeSyscalls()


@pytest.fixture()
def context(syscalls: FakeSyscalls) -> FakeContext:
    """FakeContext wired to the FakeSyscalls fixture."""
    return FakeContext(syscalls=syscalls)


@pytest.fixture()
def message() -> FakeMessage:
    """Default empty FakeMessage."""
    return FakeMessage()


@pytest.fixture()
def sample_events(syscalls: FakeSyscalls) -> list[dict[str, Any]]:
    """Seed 5 PENDING events into hipp_events store."""
    events = []
    for i in range(5):
        event = {
            "event_id": f"evt_{i:04d}",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "event_text": f"Sample event text number {i} for embedding generation",
            "embedding_status": "PENDING",
        }
        syscalls.hipp_events[event["event_id"]] = event
        events.append(event)
    return events


@pytest.fixture()
def sample_vectors(syscalls: FakeSyscalls) -> list[dict[str, Any]]:
    """Seed 3 valid vectors into vec_store (matching hipp_events)."""
    for i in range(3):
        event_id = f"evt_{i:04d}"
        syscalls.hipp_events[event_id] = {
            "event_id": event_id,
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "event_text": f"Text {i}",
            "embedding_status": "READY",
        }
        syscalls.vec_store[f"emb_{i:04d}"] = {
            "embedding_id": f"emb_{i:04d}",
            "event_id": event_id,
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "vector": [0.01] * 768,
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "status": "READY",
        }
    vectors = list(syscalls.vec_store.values())
    return vectors
