"""
P02 Integration Test Fixtures

Provides test data, mock infrastructure, and helper utilities for P02 pipeline
end-to-end integration tests.

Related:
- Epic 6.1.1: P02 End-to-End Integration Test Suite
- P02 Pipeline: k0/contracts/pipelines/p02_write.v1.yaml
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# =============================================================================
# Test Envelope Factories
# =============================================================================


def create_minimal_envelope(
    tenant_id: str = "test_tenant_123",
    space_id: str = "test_space_456",
    text: str = "Test memory event",
) -> dict[str, Any]:
    """
    Create minimal valid envelope for P02 pipeline.

    Mimics cognitive.memory.write.committed.v1 event structure.
    Matches P02 dossier canonical format (flat structure, not nested header).
    """
    cognitive_trace_id = str(uuid.uuid4())
    timestamp = int(datetime.now(timezone.utc).timestamp())

    return {
        # Identity & Trace (flat structure per P02 dossier)
        "cognitive_trace_id": cognitive_trace_id,
        "wal_pos": 1000 + hash(cognitive_trace_id) % 9000,  # Realistic WAL position
        "tenant_id": tenant_id,
        "space_id": space_id,
        "topic": "memory.episodic.formation",
        "schema_version": "1.0.0",
        # Policy
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        # Actor
        "actor_id": "test_actor",
        "device_id": "test_device",
        # Timestamps
        "ts": timestamp,
        "ingested_at": timestamp,
        # Body
        "body": {
            "text": text,
            "activity_type": "routine",
            "content_type": "episodic",
        },
    }


def create_enriched_envelope(
    tenant_id: str = "test_tenant_123",
    space_id: str = "test_space_456",
    text: str = "Family dinner at home with kids",
    **overrides,
) -> dict[str, Any]:
    """
    Create fully enriched envelope with realistic data.

    Useful for testing downstream stages that expect enriched context.
    """
    base = create_minimal_envelope(tenant_id, space_id, text)

    # Add realistic enrichments
    base["body"].update(
        {
            "participants": ["parent_user_1", "child_user_2"],
            "location": {
                "place_name": "Home",
                "lat": 37.7749,
                "lng": -122.4194,
                "geohash": "9q8yyk",
            },
            "device_kind": "phone",
            "device_os": "iOS",
            "client_version": "2.1.0",
        }
    )

    # Apply any overrides
    for key, value in overrides.items():
        if "." in key:  # Nested path like "body.text"
            parts = key.split(".")
            target = base
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        else:
            base[key] = value

    return base


# =============================================================================
# Mock Infrastructure Fixtures
# =============================================================================


@pytest.fixture
def mock_syscalls():
    """
    Mock syscalls adapter for testing.

    Provides in-memory implementations of storage operations without
    requiring real database connections.
    """
    syscalls = MagicMock()

    # Storage state (in-memory)
    _hipp_events = {}
    _embedding_queue = {}
    _pipeline_processed = {}
    _outbox = []

    # Mock hipp_events_upsert
    async def _hipp_events_upsert(**kwargs):
        event_id = kwargs["event_id"]
        if event_id in _hipp_events:
            return {"inserted": False, "event_id": event_id, "status": "SKIPPED_DUPLICATE"}
        _hipp_events[event_id] = kwargs
        return {"inserted": True, "event_id": event_id, "status": "INSERTED"}

    syscalls.hipp_events_upsert = AsyncMock(side_effect=_hipp_events_upsert)

    # Mock embedding_queue_upsert
    async def _embedding_queue_upsert(**kwargs):
        embed_id = kwargs["embedding_id"]
        _embedding_queue[embed_id] = kwargs
        return {"inserted": True, "embedding_id": embed_id}

    syscalls.embedding_queue_upsert = AsyncMock(side_effect=_embedding_queue_upsert)

    # Mock pipeline_processed_upsert
    async def _pipeline_processed_upsert(**kwargs):
        wal_pos = kwargs["wal_pos"]
        _pipeline_processed[wal_pos] = kwargs
        return {"inserted": True, "wal_pos": wal_pos}

    syscalls.pipeline_processed_upsert = AsyncMock(side_effect=_pipeline_processed_upsert)

    # Mock outbox_emit_batch
    async def _outbox_emit_batch(events):
        _outbox.extend(events)
        return {
            "events_inserted": len(events),
            "batch_size": len(events),
            "operation": "outbox_emit_batch",
            "status": "success",
        }

    syscalls.outbox_emit_batch = AsyncMock(side_effect=_outbox_emit_batch)

    # Expose storage state for test assertions
    syscalls._storage = {
        "hipp_events": _hipp_events,
        "embedding_queue": _embedding_queue,
        "pipeline_processed": _pipeline_processed,
        "outbox": _outbox,
    }

    return syscalls


@pytest.fixture
def mock_context(mock_syscalls):
    """
    Mock PipelineContext for module execution.

    Provides syscalls adapter and structured logger.
    """
    context = MagicMock()
    context.syscalls = mock_syscalls
    context.logger = Mock()
    return context


# =============================================================================
# Assertion Helpers
# =============================================================================


def assert_row_in_hipp_events(
    syscalls,
    event_id: str,
    expected_fields: dict[str, Any] | None = None,
):
    """
    Assert that a row exists in st_hipp_events with expected values.

    Args:
        syscalls: Mock syscalls fixture
        event_id: Event ID to check
        expected_fields: Optional dict of field_name -> expected_value

    Raises:
        AssertionError: Row not found or fields don't match
    """
    storage = syscalls._storage["hipp_events"]
    assert event_id in storage, f"Event {event_id} not found in st_hipp_events"

    if expected_fields:
        row = storage[event_id]
        for field, expected_value in expected_fields.items():
            actual_value = row.get(field)
            assert (
                actual_value == expected_value
            ), f"Field {field}: expected {expected_value}, got {actual_value}"


def assert_exit_events_emitted(
    syscalls,
    expected_topics: list[str],
    tenant_id: str | None = None,
):
    """
    Assert that exit events were emitted to st_outbox.

    Args:
        syscalls: Mock syscalls fixture
        expected_topics: List of expected event topics (driver field)
        tenant_id: Optional tenant filter

    Raises:
        AssertionError: Events not found or topics missing
    """
    outbox = syscalls._storage["outbox"]

    if tenant_id:
        outbox = [e for e in outbox if e.get("tenant_id") == tenant_id]

    emitted_topics = {event["driver"] for event in outbox}

    for topic in expected_topics:
        assert (
            topic in emitted_topics
        ), f"Topic {topic} not found in outbox. Emitted: {emitted_topics}"


def assert_embedding_job_created(
    syscalls,
    text_hash: str,
    expected_priority: str = "NORMAL",
):
    """
    Assert that embedding job was created in st_embedding_queue.

    Args:
        syscalls: Mock syscalls fixture
        text_hash: Text hash to look for
        expected_priority: Expected priority level

    Raises:
        AssertionError: Job not found or priority mismatch
    """
    queue = syscalls._storage["embedding_queue"]

    # Find job by text_hash
    job = next((j for j in queue.values() if j.get("text_hash") == text_hash), None)
    assert job is not None, f"Embedding job for text_hash {text_hash} not found"
    assert (
        job.get("priority") == expected_priority
    ), f"Priority: expected {expected_priority}, got {job.get('priority')}"


# =============================================================================
# Test Data Samples
# =============================================================================


SAMPLE_ENVELOPES = {
    "minimal": create_minimal_envelope(),
    "family_dinner": create_enriched_envelope(
        text="Family dinner at home with everyone",
    ),
    "solo_reflection": create_enriched_envelope(
        text="Quiet morning reflection time",
    ),
    "multi_tenant_a": create_minimal_envelope(
        tenant_id="tenant_a",
        text="Tenant A event",
    ),
    "multi_tenant_b": create_minimal_envelope(
        tenant_id="tenant_b",
        text="Tenant B event",
    ),
}
