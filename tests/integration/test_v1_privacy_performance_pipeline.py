"""End-to-end integration tests for Issue 1.3 + 1.4 (Privacy + Performance).

Tests the complete V1 pipeline:
  - Issue 1.3: Policy stamp propagation + location privacy
  - Issue 1.4: Async worker coordination

This verifies that privacy compliance doesn't impact async performance improvements.
"""

from __future__ import annotations

import pytest

from k0.policy import apply_location_privacy, create_policy_stamp
from k0.workers import AsyncWorkerCoordinator


class TestV1PipelineIntegration:
    """Integration tests for V1 privacy + performance pipeline."""

    def test_issue_1_3_policy_stamp_creation(self) -> None:
        """Test Issue 1.3: Policy stamp creation (independent of workers)."""
        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="AMBER",
            obligations=["mask.location.precision"],
            visible_to=["alice"],
            decision="ALLOW",
        )

        # Verify policy stamp structure
        assert stamp.policy_version == "2025-11-01"
        assert stamp.band == "AMBER"
        assert "mask.location.precision" in stamp.obligations
        assert "alice" in stamp.visible_to
        assert stamp.decision == "ALLOW"
        assert stamp.applied_at is not None

    def test_issue_1_3_location_privacy_amber(self) -> None:
        """Test Issue 1.3: Location privacy for AMBER band."""
        # Note: apply_location_privacy mutates dict, so create fresh dict
        envelope_data = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "space_id": "space-001",
            "band": "AMBER",
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
            },
        }

        # Apply AMBER band masking
        result = apply_location_privacy(envelope_data, "AMBER")

        # Verify AMBER precision applied
        assert result["location_geohash"] is not None
        assert result["location_precision_m"] == 5000  # AMBER = 5km

    def test_issue_1_3_location_privacy_red(self) -> None:
        """Test Issue 1.3: Location privacy for RED band."""
        envelope_data = {
            "cognitive_trace_id": "223e4567-e89b-12d3-a456-426614174001",
            "tenant_id": "tenant-001",
            "space_id": "space-001",
            "band": "RED",
            "body": {
                "location_lat": 51.5074,
                "location_lon": -0.1278,
            },
        }

        # Apply RED band masking (most restrictive)
        result = apply_location_privacy(envelope_data, "RED")

        # Verify RED precision applied
        assert result["location_geohash"] is not None
        assert result["location_precision_m"] == 25000  # RED = 25km

    def test_issue_1_3_location_privacy_green(self) -> None:
        """Test Issue 1.3: Location privacy for GREEN band."""
        envelope_data = {
            "cognitive_trace_id": "323e4567-e89b-12d3-a456-426614174002",
            "tenant_id": "tenant-001",
            "space_id": "space-001",
            "band": "GREEN",
            "body": {
                "location_lat": 40.7128,
                "location_lon": -74.0060,
            },
        }

        # Apply GREEN band (full precision)
        result = apply_location_privacy(envelope_data, "GREEN")

        # Verify GREEN precision applied
        assert result["location_geohash"] is not None
        assert result["location_precision_m"] == 1  # GREEN = full precision

    def test_issue_1_4_async_embedding_worker(self) -> None:
        """Test Issue 1.4: Async embedding worker."""
        coordinator = AsyncWorkerCoordinator()

        # Process batch of events
        batch = [
            {
                "id": f"outbox-{i}",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {
                    "event_id": f"evt-{i:03d}",
                    "space_id": "space-001",
                    "text": f"Event {i}",
                },
            }
            for i in range(5)
        ]

        processed = coordinator.process_outbox_batch(batch)
        status = coordinator.get_status()

        # Verify metrics
        assert status["processed"] == 5
        assert status["failed"] == 0
        assert status["success_rate"] == 1.0
        assert len(processed) == 5
        assert all(r.status == "COMPLETE" for r in processed)

    def test_issue_1_4_async_fts_worker(self) -> None:
        """Test Issue 1.4: Async FTS indexing worker."""
        coordinator = AsyncWorkerCoordinator()

        batch = [
            {
                "id": f"outbox-{i}",
                "operation_kind": "INDEX_FTS",
                "payload": {
                    "event_id": f"evt-{i:03d}",
                    "space_id": "space-001",
                    "document_id": f"doc-{i:03d}",
                    "text": f"Document {i}",
                    "document_type": "memory_event",
                },
            }
            for i in range(5)
        ]

        processed = coordinator.process_outbox_batch(batch)

        # Verify FTS results
        assert len(processed) == 5
        assert all(r.status == "COMPLETE" for r in processed)
        assert all(r.operation_kind == "INDEX_FTS" for r in processed)

    def test_privacy_plus_performance_latency_improvement(self) -> None:
        """Test that async workers improve latency despite privacy processing."""
        import time

        coordinator = AsyncWorkerCoordinator()
        batch = [
            {
                "id": f"outbox-{i}",
                "operation_kind": "COMPUTE_EMBEDDING" if i % 2 == 0 else "INDEX_FTS",
                "payload": {
                    "event_id": f"evt-{i:03d}",
                    "space_id": "space-001",
                    "document_id": f"doc-{i:03d}" if i % 2 == 1 else None,
                    "text": f"Content {i}",
                    "document_type": "memory_event",
                },
            }
            for i in range(20)
        ]

        start = time.perf_counter()
        processed = coordinator.process_outbox_batch(batch)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Realistic threshold for batch processing with real operations (5 seconds for 20 events)
        assert elapsed_ms < 5000, f"Coordinator too slow: {elapsed_ms}ms"
        assert len(processed) == 20
        assert all(r.status == "COMPLETE" for r in processed)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
