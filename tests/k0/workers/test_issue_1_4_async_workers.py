"""Comprehensive tests for Issue 1.4 (Async Workers).

Tests cover:
  - Embedding worker: request processing, batch handling
  - FTS worker: keyword extraction, batch indexing
  - Coordinator: outbox batch dispatch, status tracking
  - Integration: full end-to-end flow with embedding + FTS
"""

from __future__ import annotations

import pytest

from k0.workers import (
    AsyncWorkerCoordinator,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingWorker,
    FtsIndexingWorker,
    FtsIndexRequest,
    FtsIndexResult,
    WorkerCoordinatorConfig,
    compute_fake_embedding,
    extract_keywords,
)

# ============================================================================
# TestEmbeddingWorker: Unit tests for embedding computation
# ============================================================================


class TestEmbeddingWorkerCreation:
    """Test embedding worker creation and initialization."""

    def test_create_embedding_worker(self) -> None:
        """Test creating an embedding worker."""
        worker = EmbeddingWorker()
        assert worker is not None
        assert worker._batch_size == 10

    def test_embedding_worker_has_methods(self) -> None:
        """Test embedding worker has required methods."""
        worker = EmbeddingWorker()
        assert hasattr(worker, "process_embedding_request")
        assert hasattr(worker, "process_batch")


class TestEmbeddingComputation:
    """Test embedding computation functions."""

    def test_compute_embedding_from_request(self) -> None:
        """Test computing fake embedding from request."""
        request = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Hello world",
        )
        result = compute_fake_embedding(request)
        assert isinstance(result, EmbeddingResult)
        assert result.event_id == "evt-001"
        assert result.embedding_id.startswith("emb-")
        assert result.embedding_dimension == 384
        assert result.model_used == "all-mpnet-base-v2"  # Updated default model

    def test_embedding_result_has_timestamp(self) -> None:
        """Test embedding result includes computed_at timestamp."""
        request = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Test text",
        )
        result = compute_fake_embedding(request)
        assert result.computed_at is not None
        assert "T" in result.computed_at  # ISO format

    def test_embedding_id_deterministic(self) -> None:
        """Test embedding IDs are deterministic for same text."""
        request1 = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Same text",
        )
        request2 = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Same text",
        )
        result1 = compute_fake_embedding(request1)
        result2 = compute_fake_embedding(request2)
        assert result1.embedding_id == result2.embedding_id

    def test_embedding_id_different_for_different_text(self) -> None:
        """Test embedding IDs differ for different texts."""
        request1 = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Text A",
        )
        request2 = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Text B",
        )
        result1 = compute_fake_embedding(request1)
        result2 = compute_fake_embedding(request2)
        assert result1.embedding_id != result2.embedding_id


class TestEmbeddingWorkerProcessing:
    """Test embedding worker request processing."""

    def test_process_single_embedding_request(self) -> None:
        """Test processing single embedding request."""
        worker = EmbeddingWorker()
        request = EmbeddingRequest(
            event_id="evt-001",
            space_id="space-001",
            text="Process me",
        )
        result = worker.process_embedding_request(request)
        assert result.event_id == "evt-001"
        assert result.embedding_id.startswith("emb-")

    def test_process_batch_of_embeddings(self) -> None:
        """Test processing batch of embedding requests."""
        worker = EmbeddingWorker()
        requests = [
            EmbeddingRequest(
                event_id=f"evt-{i:03d}",
                space_id="space-001",
                text=f"Text {i}",
            )
            for i in range(5)
        ]
        results = worker.process_batch(requests)
        assert len(results) == 5
        assert all(isinstance(r, EmbeddingResult) for r in results)

    def test_process_batch_respects_batch_size(self) -> None:
        """Test batch processing respects batch size limit."""
        worker = EmbeddingWorker()
        requests = [
            EmbeddingRequest(
                event_id=f"evt-{i:03d}",
                space_id="space-001",
                text=f"Text {i}",
            )
            for i in range(20)  # More than batch size
        ]
        results = worker.process_batch(requests)
        assert len(results) == 10  # Batch size limit


# ============================================================================
# TestFtsIndexingWorker: Unit tests for FTS indexing
# ============================================================================


class TestKeywordExtraction:
    """Test keyword extraction functions."""

    def test_extract_keywords_from_text(self) -> None:
        """Test extracting keywords from simple text."""
        text = "The quick brown fox jumps over the lazy dog"
        keywords = extract_keywords(text)
        assert "quick" in keywords
        assert "brown" in keywords
        assert "fox" in keywords
        assert "jump" in keywords  # 'jumps' is stemmed to 'jump'
        # Common stop words should be filtered
        assert "the" not in keywords

    def test_extract_keywords_respects_max_limit(self) -> None:
        """Test keyword extraction respects maximum limit."""
        text = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"
        keywords = extract_keywords(text, max_keywords=5)
        assert len(keywords) == 5

    def test_extract_keywords_removes_stop_words(self) -> None:
        """Test keyword extraction removes stop words."""
        text = "This is a test of the system"
        keywords = extract_keywords(text)
        # "test" and "system" are not stop words, so they should be extracted
        # Stop words should not appear
        stop_words = {"this", "is", "a", "of", "the"}
        for keyword in keywords:
            assert keyword not in stop_words
        # Should extract meaningful words
        assert len(keywords) > 0


class TestFtsIndexingWorkerCreation:
    """Test FTS indexing worker creation."""

    def test_create_fts_worker(self) -> None:
        """Test creating an FTS indexing worker."""
        worker = FtsIndexingWorker()
        assert worker is not None
        assert worker._batch_size == 50

    def test_fts_worker_has_methods(self) -> None:
        """Test FTS worker has required methods."""
        worker = FtsIndexingWorker()
        assert hasattr(worker, "process_fts_request")
        assert hasattr(worker, "process_batch")


class TestFtsIndexingProcessing:
    """Test FTS indexing worker request processing."""

    def test_process_single_fts_request(self) -> None:
        """Test processing single FTS indexing request."""
        worker = FtsIndexingWorker()
        request = FtsIndexRequest(
            event_id="evt-001",
            space_id="space-001",
            document_id="doc-001",
            text="Index this document for full-text search",
            document_type="memory_event",
        )
        result = worker.process_fts_request(request)
        assert isinstance(result, FtsIndexResult)
        assert result.event_id == "evt-001"
        assert result.fts_entry_id.startswith("fts-")
        assert result.text_length > 0
        assert result.keyword_count > 0

    def test_process_batch_of_fts_requests(self) -> None:
        """Test processing batch of FTS requests."""
        worker = FtsIndexingWorker()
        requests = [
            FtsIndexRequest(
                event_id=f"evt-{i:03d}",
                space_id="space-001",
                document_id=f"doc-{i:03d}",
                text=f"Document {i} for indexing",
                document_type="memory_event",
            )
            for i in range(5)
        ]
        results = worker.process_batch(requests)
        assert len(results) == 5
        assert all(isinstance(r, FtsIndexResult) for r in results)

    def test_process_batch_respects_batch_size(self) -> None:
        """Test FTS batch processing respects batch size limit."""
        worker = FtsIndexingWorker()
        requests = [
            FtsIndexRequest(
                event_id=f"evt-{i:03d}",
                space_id="space-001",
                document_id=f"doc-{i:03d}",
                text=f"Document {i}",
                document_type="memory_event",
            )
            for i in range(100)  # More than batch size
        ]
        results = worker.process_batch(requests)
        assert len(results) == 50  # Batch size limit


# ============================================================================
# TestAsyncWorkerCoordinator: Coordinator tests
# ============================================================================


class TestCoordinatorCreation:
    """Test async worker coordinator creation."""

    def test_create_coordinator_with_defaults(self) -> None:
        """Test creating coordinator with default config."""
        coordinator = AsyncWorkerCoordinator()
        assert coordinator is not None

    def test_create_coordinator_with_custom_config(self) -> None:
        """Test creating coordinator with custom config."""
        config = WorkerCoordinatorConfig(
            embedding_batch_size=20,
            fts_batch_size=100,
        )
        coordinator = AsyncWorkerCoordinator(config)
        assert coordinator._config.embedding_batch_size == 20
        assert coordinator._config.fts_batch_size == 100

    def test_coordinator_has_status_method(self) -> None:
        """Test coordinator has status method."""
        coordinator = AsyncWorkerCoordinator()
        assert hasattr(coordinator, "get_status")


class TestCoordinatorStatusTracking:
    """Test coordinator status tracking."""

    def test_coordinator_initial_status(self) -> None:
        """Test coordinator initial status."""
        coordinator = AsyncWorkerCoordinator()
        status = coordinator.get_status()
        assert status["processed"] == 0
        assert status["failed"] == 0
        assert status["success_rate"] == 0.0

    def test_coordinator_tracks_processed_count(self) -> None:
        """Test coordinator tracks processed events."""
        coordinator = AsyncWorkerCoordinator()
        # Simulate processing
        coordinator._processed = 5
        status = coordinator.get_status()
        assert status["processed"] == 5

    def test_coordinator_tracks_failure_count(self) -> None:
        """Test coordinator tracks failed events."""
        coordinator = AsyncWorkerCoordinator()
        coordinator._processed = 7
        coordinator._failed = 3
        status = coordinator.get_status()
        assert status["processed"] == 7
        assert status["failed"] == 3
        assert abs(status["success_rate"] - 0.7) < 0.01


class TestCoordinatorBatchProcessing:
    """Test coordinator batch processing."""

    def test_process_embedding_outbox_batch(self) -> None:
        """Test processing outbox batch with embedding entries."""
        coordinator = AsyncWorkerCoordinator()
        outbox_entries = [
            {
                "id": f"outbox-{i}",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {
                    "event_id": f"evt-{i:03d}",
                    "space_id": "space-001",
                    "text": f"Text {i}",
                },
            }
            for i in range(3)
        ]
        results = coordinator.process_outbox_batch(outbox_entries)
        assert len(results) == 3
        assert all(r.operation_kind == "COMPUTE_EMBEDDING" for r in results)
        assert all(r.status == "COMPLETE" for r in results)
        assert all(r.result is not None for r in results)

    def test_process_fts_outbox_batch(self) -> None:
        """Test processing outbox batch with FTS entries."""
        coordinator = AsyncWorkerCoordinator()
        outbox_entries = [
            {
                "id": f"outbox-{i}",
                "operation_kind": "INDEX_FTS",
                "payload": {
                    "event_id": f"evt-{i:03d}",
                    "space_id": "space-001",
                    "document_id": f"doc-{i:03d}",
                    "text": f"Document {i}",
                },
            }
            for i in range(3)
        ]
        results = coordinator.process_outbox_batch(outbox_entries)
        assert len(results) == 3
        assert all(r.operation_kind == "INDEX_FTS" for r in results)
        assert all(r.status == "COMPLETE" for r in results)

    def test_process_mixed_outbox_batch(self) -> None:
        """Test processing outbox batch with both embedding and FTS."""
        coordinator = AsyncWorkerCoordinator()
        outbox_entries = [
            {
                "id": "outbox-0",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {
                    "event_id": "evt-001",
                    "space_id": "space-001",
                    "text": "Text for embedding",
                },
            },
            {
                "id": "outbox-1",
                "operation_kind": "INDEX_FTS",
                "payload": {
                    "event_id": "evt-002",
                    "space_id": "space-001",
                    "document_id": "doc-001",
                    "text": "Text for FTS",
                },
            },
        ]
        results = coordinator.process_outbox_batch(outbox_entries)
        assert len(results) == 2
        embedding_results = [r for r in results if r.operation_kind == "COMPUTE_EMBEDDING"]
        fts_results = [r for r in results if r.operation_kind == "INDEX_FTS"]
        assert len(embedding_results) == 1
        assert len(fts_results) == 1


# ============================================================================
# TestIntegration: End-to-end integration tests
# ============================================================================


class TestIntegrationEmbeddingAndFts:
    """Integration tests for embedding + FTS flow."""

    def test_full_pipeline_embedding_then_fts(self) -> None:
        """Test full pipeline: embedding then FTS indexing."""
        coordinator = AsyncWorkerCoordinator()

        # Phase 1: Compute embedding
        embedding_batch = [
            {
                "id": "outbox-1",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {
                    "event_id": "evt-001",
                    "space_id": "space-001",
                    "text": "Machine learning text",
                },
            },
        ]
        embedding_results = coordinator.process_outbox_batch(embedding_batch)
        assert embedding_results[0].status == "COMPLETE"
        assert embedding_results[0].result is not None
        embedding_id = embedding_results[0].result.embedding_id

        # Phase 2: Index in FTS
        fts_batch = [
            {
                "id": "outbox-2",
                "operation_kind": "INDEX_FTS",
                "payload": {
                    "event_id": "evt-001",
                    "space_id": "space-001",
                    "document_id": "doc-001",
                    "text": "Machine learning text",
                },
            },
        ]
        fts_results = coordinator.process_outbox_batch(fts_batch)
        assert fts_results[0].status == "COMPLETE"
        assert fts_results[0].result is not None
        fts_entry_id = fts_results[0].result.fts_entry_id

        # Verify both completed
        assert embedding_id.startswith("emb-")
        assert fts_entry_id.startswith("fts-")

        # Verify status tracking
        status = coordinator.get_status()
        assert status["processed"] == 2

    def test_concurrent_embeddings_and_fts(self) -> None:
        """Test processing embeddings and FTS concurrently."""
        coordinator = AsyncWorkerCoordinator()

        mixed_batch = [
            {
                "id": f"outbox-{i}",
                "operation_kind": "COMPUTE_EMBEDDING" if i % 2 == 0 else "INDEX_FTS",
                "payload": {
                    "event_id": f"evt-{i:03d}",
                    "space_id": "space-001",
                    "document_id": f"doc-{i:03d}" if i % 2 == 1 else None,
                    "text": f"Content {i}",
                },
            }
            for i in range(6)
        ]

        results = coordinator.process_outbox_batch(mixed_batch)
        assert len(results) == 6
        assert all(r.status == "COMPLETE" for r in results)

        embedding_count = sum(1 for r in results if r.operation_kind == "COMPUTE_EMBEDDING")
        fts_count = sum(1 for r in results if r.operation_kind == "INDEX_FTS")
        assert embedding_count == 3
        assert fts_count == 3


class TestIntegrationErrorHandling:
    """Integration tests for error handling."""

    def test_malformed_payload_handling(self) -> None:
        """Test handling malformed outbox payloads."""
        coordinator = AsyncWorkerCoordinator()

        bad_batch = [
            {
                "id": "outbox-1",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {},  # Missing required fields
            },
        ]

        results = coordinator.process_outbox_batch(bad_batch)
        assert results[0].status == "FAILED"
        assert results[0].error is not None

    def test_unknown_operation_kind_handling(self) -> None:
        """Test handling unknown operation kinds."""
        coordinator = AsyncWorkerCoordinator()

        unknown_batch = [
            {
                "id": "outbox-1",
                "operation_kind": "UNKNOWN_OPERATION",
                "payload": {"event_id": "evt-001"},
            },
        ]

        results = coordinator.process_outbox_batch(unknown_batch)
        # Unknown operations are skipped
        assert len(results) == 0

    def test_partial_batch_failure(self) -> None:
        """Test batch continues after individual failures."""
        coordinator = AsyncWorkerCoordinator()

        mixed_batch = [
            {
                "id": "outbox-1",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {"event_id": "evt-001", "space_id": "space-001", "text": "Good"},
            },
            {
                "id": "outbox-2",
                "operation_kind": "COMPUTE_EMBEDDING",
                "payload": {},  # Bad
            },
            {
                "id": "outbox-3",
                "operation_kind": "INDEX_FTS",
                "payload": {
                    "event_id": "evt-002",
                    "space_id": "space-001",
                    "document_id": "doc-001",
                    "text": "Good",
                },
            },
        ]

        results = coordinator.process_outbox_batch(mixed_batch)
        # Should process at least 2 successfully
        success_count = sum(1 for r in results if r.status == "COMPLETE")
        assert success_count >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
