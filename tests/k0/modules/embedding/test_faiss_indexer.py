"""
Unit Tests for M24: embedding.faiss_indexer

Tests FAISS indexing module that consumes cognitive.vector.stored.v1 events
and adds vectors to FAISS index.

Test Coverage:
- Successful indexing path
- Missing vector handling
- Invalid dimension handling
- Event emission
- Status updates (st_vec, st_hipp_events)
- Metrics tracking
- Contract compliance
- Performance benchmarks

Version: 1.0.0
Last Updated: 2025-12-13
"""

import asyncio
import struct
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.embedding import faiss_indexer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_event_envelope():
    """Sample cognitive.vector.stored.v1 event envelope"""
    return {
        "payload": {
            "embedding_id": "emb_test_12345",
            "event_id": "evt_test_67890",
            "tenant_id": "tenant_1",
            "space_id": "space_home",
            "model_id": "ultrabert_v2.1.0",
            "vector_dim": 768,
            "stored_at": 1702468800,
            "status": "READY",
        },
    }


@pytest.fixture
def sample_vector_768dim():
    """Sample 768-dim vector"""
    return [0.1 * i for i in range(768)]


@pytest.fixture
def sample_vector_bytes(sample_vector_768dim):
    """Sample 768-dim vector as bytes (3072 bytes)"""
    return struct.pack("768f", *sample_vector_768dim)


@pytest.fixture
def mock_context():
    """Mock execution context with syscalls"""
    context = MagicMock()
    context.config = {
        "emit_indexed_event": True,
        "indexed_event_topic": "cognitive.vector.indexed.v1",
        "update_hipp_events_status": True,
        "index_id": "ultrabert_v2.1.0_ivf256_pq64",
    }

    # Mock syscalls
    context.syscalls = MagicMock()
    context.syscalls.vec_read = AsyncMock()
    context.syscalls.faiss_add = AsyncMock()
    context.syscalls.vec_update = AsyncMock()
    context.syscalls.hipp_events_update_embedding_status = AsyncMock()
    context.syscalls.outbox_emit_batch = AsyncMock()

    return context


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test"""
    faiss_indexer.reset_metrics()
    yield
    faiss_indexer.reset_metrics()


# =============================================================================
# Test: Successful Indexing Path
# =============================================================================


class TestSuccessfulIndexing:
    """Test successful FAISS indexing flow"""

    @pytest.mark.asyncio
    async def test_successful_index_adds_to_faiss(
        self, sample_event_envelope, sample_vector_bytes, sample_vector_768dim, mock_context
    ):
        """Test: Successful indexing adds vector to FAISS"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {
            "added": True,
            "embedding_id": "emb_test_12345",
            "total_vectors": 12345,
        }

        # Act
        result = await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        assert result["indexed"] is True
        assert result["embedding_id"] == "emb_test_12345"
        assert result["total_vectors"] == 12345

        # Verify vec_read called
        mock_context.syscalls.vec_read.assert_called_once_with(embedding_id="emb_test_12345")

        # Verify faiss_add called with correct vector
        faiss_call = mock_context.syscalls.faiss_add.call_args
        assert faiss_call[1]["embedding_id"] == "emb_test_12345"
        assert len(faiss_call[1]["vector"]) == 768

    @pytest.mark.asyncio
    async def test_successful_index_updates_st_vec_timestamp(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Successful indexing updates st_vec.indexed_at"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Act
        result = await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        mock_context.syscalls.vec_update.assert_called_once()
        update_call = mock_context.syscalls.vec_update.call_args
        assert update_call[1]["embedding_id"] == "emb_test_12345"
        assert update_call[1]["status"] == "INDEXED"
        assert "indexed_at" in update_call[1]

    @pytest.mark.asyncio
    async def test_successful_index_updates_hipp_events_status(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Successful indexing updates st_hipp_events.embedding_status"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        mock_context.syscalls.hipp_events_update_embedding_status.assert_called_once_with(
            event_id="evt_test_67890",
            embedding_status="INDEXED",
        )

    @pytest.mark.asyncio
    async def test_successful_index_emits_indexed_event(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Successful indexing emits cognitive.vector.indexed.v1"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 200}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        mock_context.syscalls.outbox_emit_batch.assert_called_once()
        emit_call = mock_context.syscalls.outbox_emit_batch.call_args
        events = emit_call[1]["events"]
        assert len(events) == 1
        assert events[0]["topic"] == "cognitive.vector.indexed.v1"
        assert events[0]["payload"]["embedding_id"] == "emb_test_12345"
        assert events[0]["payload"]["total_vectors"] == 200


# =============================================================================
# Test: Missing/Invalid Vector Handling
# =============================================================================


class TestMissingInvalidVectors:
    """Test handling of missing or invalid vectors"""

    @pytest.mark.asyncio
    async def test_missing_vector_raises_error(self, sample_event_envelope, mock_context):
        """Test: Missing vector in st_vec raises RuntimeError"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": None}

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to read vector"):
            await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Verify metrics
        metrics = faiss_indexer.get_metrics()
        assert metrics["missing_vectors"] == 1

    @pytest.mark.asyncio
    async def test_invalid_dimension_raises_error(self, sample_event_envelope, mock_context):
        """Test: Invalid vector dimension raises RuntimeError"""
        # Arrange - create 384-dim vector instead of 768-dim
        invalid_vector = [0.1] * 384
        invalid_bytes = struct.pack("384f", *invalid_vector)
        mock_context.syscalls.vec_read.return_value = {"vector": invalid_bytes}

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to read vector"):
            await faiss_indexer.run(sample_event_envelope, {}, mock_context)

    @pytest.mark.asyncio
    async def test_vec_read_failure_raises_runtime_error(self, sample_event_envelope, mock_context):
        """Test: vec_read failure raises RuntimeError"""
        # Arrange
        mock_context.syscalls.vec_read.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to read vector"):
            await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Verify metrics
        metrics = faiss_indexer.get_metrics()
        assert metrics["indexing_failures"] == 1


# =============================================================================
# Test: Validation & Error Handling
# =============================================================================


class TestValidationErrorHandling:
    """Test validation and error handling"""

    @pytest.mark.asyncio
    async def test_missing_embedding_id_raises_error(self, mock_context):
        """Test: Missing embedding_id raises ValueError"""
        # Arrange
        envelope = {"payload": {"event_id": "evt_123"}}

        # Act & Assert
        with pytest.raises(ValueError, match="embedding_id required"):
            await faiss_indexer.run(envelope, {}, mock_context)

    @pytest.mark.asyncio
    async def test_missing_event_id_raises_error(self, mock_context):
        """Test: Missing event_id raises ValueError"""
        # Arrange
        envelope = {"payload": {"embedding_id": "emb_123"}}

        # Act & Assert
        with pytest.raises(ValueError, match="event_id required"):
            await faiss_indexer.run(envelope, {}, mock_context)

    @pytest.mark.asyncio
    async def test_faiss_add_failure_raises_runtime_error(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: FAISS add failure raises RuntimeError"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.side_effect = Exception("FAISS index full")

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to add to FAISS"):
            await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Verify metrics
        metrics = faiss_indexer.get_metrics()
        assert metrics["indexing_failures"] == 1

    @pytest.mark.asyncio
    async def test_vec_update_failure_non_fatal(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: vec_update failure is non-fatal (logs warning)"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}
        mock_context.syscalls.vec_update.side_effect = Exception("Update failed")

        # Act - should not raise
        result = await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert - indexing still succeeded
        assert result["indexed"] is True

    @pytest.mark.asyncio
    async def test_event_emission_failure_non_fatal(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Event emission failure is non-fatal"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}
        mock_context.syscalls.outbox_emit_batch.side_effect = Exception("Outbox full")

        # Act - should not raise
        result = await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert - indexing still succeeded
        assert result["indexed"] is True


# =============================================================================
# Test: Configuration Options
# =============================================================================


class TestConfigurationOptions:
    """Test configuration option handling"""

    @pytest.mark.asyncio
    async def test_emit_indexed_event_disabled(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Event emission can be disabled via config"""
        # Arrange
        mock_context.config["emit_indexed_event"] = False
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert - outbox_emit_batch not called
        mock_context.syscalls.outbox_emit_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_indexed_event_topic(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Custom event topic can be configured"""
        # Arrange
        mock_context.config["indexed_event_topic"] = "custom.indexed.v1"
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        emit_call = mock_context.syscalls.outbox_emit_batch.call_args
        assert emit_call[1]["events"][0]["topic"] == "custom.indexed.v1"

    @pytest.mark.asyncio
    async def test_update_hipp_events_disabled(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: st_hipp_events update can be disabled"""
        # Arrange
        mock_context.config["update_hipp_events_status"] = False
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert - hipp_events_update not called
        mock_context.syscalls.hipp_events_update_embedding_status.assert_not_called()


# =============================================================================
# Test: Metrics & Observability
# =============================================================================


class TestMetricsObservability:
    """Test metrics tracking and observability"""

    @pytest.mark.asyncio
    async def test_metrics_track_successful_indexing(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Metrics track successful indexing"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        metrics = faiss_indexer.get_metrics()
        assert metrics["vectors_indexed"] == 1
        assert metrics["events_emitted"] == 1
        assert metrics["indexing_failures"] == 0

    @pytest.mark.asyncio
    async def test_metrics_track_failures(self, sample_event_envelope, mock_context):
        """Test: Metrics track indexing failures"""
        # Arrange
        mock_context.syscalls.vec_read.side_effect = Exception("Read failed")

        # Act & Assert
        with pytest.raises(RuntimeError):
            await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        metrics = faiss_indexer.get_metrics()
        assert metrics["indexing_failures"] == 1
        assert metrics["vectors_indexed"] == 0

    @pytest.mark.asyncio
    async def test_metrics_reset(self):
        """Test: Metrics can be reset"""
        # Arrange
        faiss_indexer._metrics["vectors_indexed"] = 100
        faiss_indexer._metrics["indexing_failures"] = 10

        # Act
        faiss_indexer.reset_metrics()

        # Assert
        metrics = faiss_indexer.get_metrics()
        assert metrics["vectors_indexed"] == 0
        assert metrics["indexing_failures"] == 0


# =============================================================================
# Test: Contract Compliance
# =============================================================================


class TestContractCompliance:
    """Test compliance with module contract"""

    @pytest.mark.asyncio
    async def test_output_schema_compliance(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Output matches contract schema"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 500}

        # Act
        result = await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert - check required output fields
        assert "indexed" in result
        assert "embedding_id" in result
        assert "index_id" in result
        assert "total_vectors" in result
        assert "indexed_at" in result

        # Assert - check field types
        assert isinstance(result["indexed"], bool)
        assert isinstance(result["embedding_id"], str)
        assert isinstance(result["index_id"], str)
        assert isinstance(result["total_vectors"], int)
        assert isinstance(result["indexed_at"], int)

    @pytest.mark.asyncio
    async def test_indexed_event_schema_compliance(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: cognitive.vector.indexed.v1 event matches schema"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 300}

        # Act
        await faiss_indexer.run(sample_event_envelope, {}, mock_context)

        # Assert
        emit_call = mock_context.syscalls.outbox_emit_batch.call_args
        payload = emit_call[1]["events"][0]["payload"]

        # Check required fields
        required_fields = [
            "embedding_id",
            "event_id",
            "tenant_id",
            "space_id",
            "model_id",
            "index_id",
            "indexed_at",
            "total_vectors",
        ]
        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"


# =============================================================================
# Test: Performance
# =============================================================================


class TestPerformance:
    """Test performance characteristics"""

    @pytest.mark.asyncio
    async def test_single_indexing_latency_under_50ms(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Single indexing completes <50ms P95"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 1000}

        # Act - run 20 times and measure
        latencies = []
        for _ in range(20):
            start = time.perf_counter()
            await faiss_indexer.run(sample_event_envelope, {}, mock_context)
            latencies.append((time.perf_counter() - start) * 1000)  # ms

        # Assert - P95 < 50ms
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95_latency < 50, f"P95 latency {p95_latency:.2f}ms exceeds 50ms target"

    @pytest.mark.asyncio
    async def test_vector_unpacking_fast(self, sample_vector_bytes):
        """Test: Vector unpacking is fast (<1ms)"""
        # Act - unpack 100 times and measure
        start = time.perf_counter()
        for _ in range(100):
            vector = list(struct.unpack("768f", sample_vector_bytes))
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Assert - avg <1ms per unpack
        avg_latency = elapsed_ms / 100
        assert avg_latency < 1, f"Vector unpacking too slow: {avg_latency:.2f}ms"


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and unusual scenarios"""

    @pytest.mark.asyncio
    async def test_empty_payload_raises_error(self, mock_context):
        """Test: Empty payload raises ValueError"""
        # Arrange
        envelope = {"payload": {}}

        # Act & Assert
        with pytest.raises(ValueError):
            await faiss_indexer.run(envelope, {}, mock_context)

    @pytest.mark.asyncio
    async def test_concurrent_indexing_safe(
        self, sample_event_envelope, sample_vector_bytes, mock_context
    ):
        """Test: Concurrent indexing operations are safe"""
        # Arrange
        mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}
        mock_context.syscalls.faiss_add.return_value = {"added": True, "total_vectors": 100}

        # Create 10 unique envelopes
        envelopes = []
        for i in range(10):
            env = sample_event_envelope.copy()
            env["payload"] = env["payload"].copy()
            env["payload"]["embedding_id"] = f"emb_test_{i}"
            env["payload"]["event_id"] = f"evt_test_{i}"
            envelopes.append(env)

        # Act - run concurrently
        tasks = [faiss_indexer.run(env, {}, mock_context) for env in envelopes]
        results = await asyncio.gather(*tasks)

        # Assert - all succeeded
        assert len(results) == 10
        assert all(r["indexed"] for r in results)

        # Verify metrics
        metrics = faiss_indexer.get_metrics()
        assert metrics["vectors_indexed"] == 10
