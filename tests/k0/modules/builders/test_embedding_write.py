"""
Unit tests for M23: builders.embedding_write

Tests for direct embedding write to st_vec table.

Contract: k0/contracts/modules/builders.embedding_write.v1.yaml
ADR: ADR-K003 (Inline Embedding via UltraBERT)
"""

import struct
import time
import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from k0.modules.builders import embedding_write


@pytest.fixture(autouse=True)
def reset_module_metrics():
    """Reset module metrics before each test."""
    embedding_write.reset_metrics()
    yield
    embedding_write.reset_metrics()


@pytest.fixture
def mock_envelope():
    """Standard test envelope with required headers."""
    return {
        "header": {
            "envelope_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "trace_id": str(uuid.uuid4()),
        },
        "body": {"text": "Mom picked up the kids from school today!"},
        "metadata": {},
    }


@pytest.fixture
def mock_enriched():
    """Enriched data from M22 with embedding."""
    return {
        "extract_from_cache": {
            "embedding": [0.1] * 768,
            "embedding_id": str(uuid.uuid4()),
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "source": "cache_hit",
        }
    }


@pytest.fixture
def mock_context():
    """Mock execution context with syscalls."""
    context = Mock()
    context.config = {
        "emit_stored_event": True,
        "validate_vector_dim": True,
        "set_pending_on_missing": True,
        "stored_event_topic": "cognitive.vector.stored.v1",
    }
    context.syscalls = Mock()
    context.syscalls.vec_write = AsyncMock(return_value={"inserted": True, "status": "INSERTED"})
    context.syscalls.outbox_emit_batch = AsyncMock()
    return context


@pytest.fixture
def test_embedding():
    """768-dimensional test embedding vector."""
    return [0.1] * 768


# =============================================================================
# Test Class 1: Successful Write Path
# =============================================================================


class TestSuccessfulWrite:
    """Test successful embedding write to st_vec."""

    @pytest.mark.asyncio
    async def test_writes_embedding_to_st_vec(self, mock_envelope, mock_enriched, mock_context):
        """Test successful embedding write calls vec_write syscall."""
        result = await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        assert result["written"] is True
        assert result["embedding_status"] == "READY"
        assert result["vector_dim"] == 768
        assert result["embedding_id"] is not None

        # Verify vec_write was called with correct arguments
        mock_context.syscalls.vec_write.assert_called_once()
        call_kwargs = mock_context.syscalls.vec_write.call_args[1]
        assert call_kwargs["embedding_id"] == mock_enriched["extract_from_cache"]["embedding_id"]
        assert call_kwargs["event_id"] == mock_envelope["header"]["event_id"]
        assert call_kwargs["tenant_id"] == "tenant_test"
        assert call_kwargs["space_id"] == "space_home"
        assert call_kwargs["vector_dim"] == 768
        assert call_kwargs["model_id"] == "ultrabert_v2.1.0"
        assert call_kwargs["status"] == "READY"
        assert len(call_kwargs["vector"]) == 3072  # 768 * 4 bytes

        metrics = embedding_write.get_metrics()
        assert metrics["embeddings_written"] == 1

    @pytest.mark.asyncio
    async def test_converts_embedding_to_bytes(self, mock_envelope, mock_enriched, mock_context):
        """Test embedding vector is correctly packed to bytes."""
        await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        call_kwargs = mock_context.syscalls.vec_write.call_args[1]
        vector_bytes = call_kwargs["vector"]

        # Verify byte packing
        assert len(vector_bytes) == 3072  # 768 floats * 4 bytes
        unpacked = struct.unpack("768f", vector_bytes)
        assert len(unpacked) == 768
        assert all(abs(v - 0.1) < 0.001 for v in unpacked)

    @pytest.mark.asyncio
    async def test_emits_cognitive_vector_stored_event(
        self, mock_envelope, mock_enriched, mock_context
    ):
        """Test cognitive.vector.stored.v1 event is emitted."""
        await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        # Verify outbox_emit_batch was called
        mock_context.syscalls.outbox_emit_batch.assert_called_once()
        call_kwargs = mock_context.syscalls.outbox_emit_batch.call_args[1]
        events = call_kwargs["events"]

        assert len(events) == 1
        event = events[0]
        assert event["topic"] == "cognitive.vector.stored.v1"
        assert event["tenant_id"] == "tenant_test"

        payload = event["payload"]
        assert payload["embedding_id"] == mock_enriched["extract_from_cache"]["embedding_id"]
        assert payload["event_id"] == mock_envelope["header"]["event_id"]
        assert payload["tenant_id"] == "tenant_test"
        assert payload["space_id"] == "space_home"
        assert payload["model_id"] == "ultrabert_v2.1.0"
        assert payload["vector_dim"] == 768
        assert payload["status"] == "READY"
        assert "stored_at" in payload

        metrics = embedding_write.get_metrics()
        assert metrics["events_emitted"] == 1

    @pytest.mark.asyncio
    async def test_handles_duplicate_embedding_id(self, mock_envelope, mock_enriched, mock_context):
        """Test graceful handling of duplicate embedding_id."""
        mock_context.syscalls.vec_write.return_value = {
            "inserted": False,
            "status": "SKIPPED_DUPLICATE",
        }

        result = await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        assert result["written"] is True
        assert result["embedding_status"] == "READY"
        # Duplicate is not an error, module completes successfully


# =============================================================================
# Test Class 2: Missing/Invalid Embedding Data
# =============================================================================


class TestMissingEmbeddingData:
    """Test handling of missing or invalid embedding data."""

    @pytest.mark.asyncio
    async def test_no_embedding_returns_pending(self, mock_envelope, mock_context):
        """Test missing embedding returns PENDING status for P08 backfill."""
        enriched = {"extract_from_cache": {"embedding": None, "embedding_id": None}}

        result = await embedding_write.run(mock_envelope, enriched, mock_context)

        assert result["written"] is False
        assert result["embedding_status"] == "PENDING"
        assert result["embedding_id"] is None
        assert result["vector_dim"] == 768

        # Verify vec_write was NOT called
        mock_context.syscalls.vec_write.assert_not_called()

        metrics = embedding_write.get_metrics()
        assert metrics["embeddings_pending"] == 1

    @pytest.mark.asyncio
    async def test_no_embedding_id_returns_pending(
        self, mock_envelope, mock_context, test_embedding
    ):
        """Test missing embedding_id returns PENDING."""
        enriched = {"extract_from_cache": {"embedding": test_embedding, "embedding_id": None}}

        result = await embedding_write.run(mock_envelope, enriched, mock_context)

        assert result["embedding_status"] == "PENDING"
        mock_context.syscalls.vec_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_vector_dimension_raises_error(self, mock_envelope, mock_context):
        """Test invalid embedding dimension raises ValueError."""
        enriched = {
            "extract_from_cache": {
                "embedding": [0.1] * 384,  # Wrong dimension
                "embedding_id": str(uuid.uuid4()),
            }
        }

        with pytest.raises(ValueError, match="Invalid embedding dimension"):
            await embedding_write.run(mock_envelope, enriched, mock_context)

        metrics = embedding_write.get_metrics()
        assert metrics["invalid_dimensions"] == 1

    @pytest.mark.asyncio
    async def test_set_pending_on_missing_false_skips(self, mock_envelope, mock_context):
        """Test set_pending_on_missing=False skips write without error."""
        mock_context.config["set_pending_on_missing"] = False
        enriched = {"extract_from_cache": {"embedding": None, "embedding_id": None}}

        result = await embedding_write.run(mock_envelope, enriched, mock_context)

        assert result["written"] is False
        assert result["embedding_status"] == "SKIPPED"


# =============================================================================
# Test Class 3: Validation & Error Handling
# =============================================================================


class TestValidationErrorHandling:
    """Test validation and error handling."""

    @pytest.mark.asyncio
    async def test_missing_event_id_raises_error(self, mock_enriched, mock_context):
        """Test missing event_id raises ValueError."""
        envelope = {"header": {"tenant_id": "tenant_test", "space_id": "space_home"}}

        with pytest.raises(ValueError, match="event_id required"):
            await embedding_write.run(envelope, mock_enriched, mock_context)

    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises_error(self, mock_enriched, mock_context):
        """Test missing tenant_id raises ValueError."""
        envelope = {"header": {"event_id": str(uuid.uuid4()), "space_id": "space_home"}}

        with pytest.raises(ValueError, match="tenant_id required"):
            await embedding_write.run(envelope, mock_enriched, mock_context)

    @pytest.mark.asyncio
    async def test_missing_space_id_raises_error(self, mock_enriched, mock_context):
        """Test missing space_id raises ValueError."""
        envelope = {"header": {"event_id": str(uuid.uuid4()), "tenant_id": "tenant_test"}}

        with pytest.raises(ValueError, match="space_id required"):
            await embedding_write.run(envelope, mock_enriched, mock_context)

    @pytest.mark.asyncio
    async def test_vec_write_failure_propagates(self, mock_envelope, mock_enriched, mock_context):
        """Test vec_write failure propagates exception."""
        mock_context.syscalls.vec_write.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        metrics = embedding_write.get_metrics()
        assert metrics["write_failures"] == 1

    @pytest.mark.asyncio
    async def test_event_emission_failure_non_fatal(
        self, mock_envelope, mock_enriched, mock_context
    ):
        """Test event emission failure is non-fatal (embedding still written)."""
        mock_context.syscalls.outbox_emit_batch.side_effect = Exception("Event bus error")

        # Should not raise, embedding write succeeds
        result = await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        assert result["written"] is True
        assert result["embedding_status"] == "READY"


# =============================================================================
# Test Class 4: Configuration Options
# =============================================================================


class TestConfigurationOptions:
    """Test module configuration options."""

    @pytest.mark.asyncio
    async def test_emit_stored_event_false_skips_emission(
        self, mock_envelope, mock_enriched, mock_context
    ):
        """Test emit_stored_event=False skips event emission."""
        mock_context.config["emit_stored_event"] = False

        result = await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        assert result["written"] is True
        mock_context.syscalls.outbox_emit_batch.assert_not_called()

        metrics = embedding_write.get_metrics()
        assert metrics["events_emitted"] == 0

    @pytest.mark.asyncio
    async def test_validate_vector_dim_false_skips_validation(self, mock_envelope, mock_context):
        """Test validate_vector_dim=False skips early dimension validation."""
        mock_context.config["validate_vector_dim"] = False
        enriched = {
            "extract_from_cache": {
                "embedding": [0.1] * 384,  # Wrong dimension
                "embedding_id": str(uuid.uuid4()),
            }
        }

        # Module won't validate early, but struct.pack will still fail
        with pytest.raises(ValueError, match="Failed to pack embedding vector"):
            await embedding_write.run(mock_envelope, enriched, mock_context)

        # Verify it skipped the early validation (different error path)
        metrics = embedding_write.get_metrics()
        assert metrics["invalid_dimensions"] == 1

    @pytest.mark.asyncio
    async def test_custom_stored_event_topic(self, mock_envelope, mock_enriched, mock_context):
        """Test custom stored_event_topic configuration."""
        mock_context.config["stored_event_topic"] = "custom.vector.stored.v1"

        await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        call_kwargs = mock_context.syscalls.outbox_emit_batch.call_args[1]
        events = call_kwargs["events"]
        assert events[0]["topic"] == "custom.vector.stored.v1"


# =============================================================================
# Test Class 5: Contract Compliance
# =============================================================================


class TestContractCompliance:
    """Test module adheres to YAML contract."""

    @pytest.mark.asyncio
    async def test_output_schema_compliance(self, mock_envelope, mock_enriched, mock_context):
        """Test output matches contract schema."""
        result = await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        # Contract requires these fields
        assert "written" in result
        assert "embedding_id" in result
        assert "embedding_status" in result
        assert "vector_dim" in result

        # Type checks
        assert isinstance(result["written"], bool)
        assert isinstance(result["embedding_id"], str)
        assert isinstance(result["embedding_status"], str)
        assert isinstance(result["vector_dim"], int)

    @pytest.mark.asyncio
    async def test_embedding_status_enum_values(self, mock_envelope, mock_context):
        """Test embedding_status uses contract-defined enum values."""
        # Test READY
        enriched_ready = {
            "extract_from_cache": {
                "embedding": [0.1] * 768,
                "embedding_id": str(uuid.uuid4()),
            }
        }
        result = await embedding_write.run(mock_envelope, enriched_ready, mock_context)
        assert result["embedding_status"] in ["READY", "PENDING", "SKIPPED"]

        # Test PENDING
        enriched_pending = {"extract_from_cache": {"embedding": None, "embedding_id": None}}
        result = await embedding_write.run(mock_envelope, enriched_pending, mock_context)
        assert result["embedding_status"] in ["READY", "PENDING", "SKIPPED"]

    @pytest.mark.asyncio
    async def test_vector_dim_always_768(self, mock_envelope, mock_enriched, mock_context):
        """Test vector_dim is always 768 in output."""
        result = await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        assert result["vector_dim"] == 768

    @pytest.mark.asyncio
    async def test_idempotency(self, mock_envelope, mock_enriched, mock_context):
        """Test module is idempotent (duplicate embedding_id handled gracefully)."""
        # First call succeeds
        result1 = await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        assert result1["written"] is True

        # Second call with duplicate embedding_id
        mock_context.syscalls.vec_write.return_value = {
            "inserted": False,
            "status": "SKIPPED_DUPLICATE",
        }
        result2 = await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        assert result2["written"] is True
        assert result2["embedding_status"] == "READY"


# =============================================================================
# Test Class 6: Performance & Observability
# =============================================================================


class TestPerformanceObservability:
    """Test performance characteristics and metrics."""

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, mock_envelope, mock_enriched, mock_context):
        """Test metrics correctly track all operations."""
        # Successful write
        await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        metrics = embedding_write.get_metrics()
        assert metrics["embeddings_written"] == 1
        assert metrics["events_emitted"] == 1

        # Pending embedding
        enriched_pending = {"extract_from_cache": {"embedding": None, "embedding_id": None}}
        await embedding_write.run(mock_envelope, enriched_pending, mock_context)
        metrics = embedding_write.get_metrics()
        assert metrics["embeddings_pending"] == 1

        # Invalid dimension
        enriched_invalid = {
            "extract_from_cache": {"embedding": [0.1] * 384, "embedding_id": str(uuid.uuid4())}
        }
        try:
            await embedding_write.run(mock_envelope, enriched_invalid, mock_context)
        except ValueError:
            pass
        metrics = embedding_write.get_metrics()
        assert metrics["invalid_dimensions"] == 1

        # Write failure
        mock_context.syscalls.vec_write.side_effect = Exception("DB error")
        try:
            await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        except Exception:
            pass
        metrics = embedding_write.get_metrics()
        assert metrics["write_failures"] == 1

    @pytest.mark.asyncio
    async def test_metrics_reset(self, mock_envelope, mock_enriched, mock_context):
        """Test metrics can be reset."""
        await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        metrics = embedding_write.get_metrics()
        assert metrics["embeddings_written"] == 1

        embedding_write.reset_metrics()
        metrics = embedding_write.get_metrics()
        assert metrics["embeddings_written"] == 0

    @pytest.mark.asyncio
    async def test_latency_budget_compliance(self, mock_envelope, mock_enriched, mock_context):
        """Test module completes within <5ms P95 latency budget."""
        start = time.perf_counter()
        await embedding_write.run(mock_envelope, mock_enriched, mock_context)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Module should be <5ms (contract requirement)
        # Allow 10ms buffer for test overhead and mocking
        assert elapsed_ms < 10.0


# =============================================================================
# Test Class 7: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    @pytest.mark.asyncio
    async def test_missing_extract_from_cache_key(self, mock_envelope, mock_context):
        """Test missing extract_from_cache key in enriched data."""
        enriched = {}

        result = await embedding_write.run(mock_envelope, enriched, mock_context)

        assert result["written"] is False
        assert result["embedding_status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_trace_id_included_in_syscall(self, mock_envelope, mock_enriched, mock_context):
        """Test trace_id from envelope is passed to vec_write."""
        trace_id = str(uuid.uuid4())
        mock_envelope["header"]["trace_id"] = trace_id

        await embedding_write.run(mock_envelope, mock_enriched, mock_context)

        call_kwargs = mock_context.syscalls.vec_write.call_args[1]
        assert call_kwargs["cognitive_trace_id"] == trace_id

    @pytest.mark.asyncio
    async def test_missing_model_id_uses_default(self, mock_envelope, mock_context):
        """Test missing model_id uses default 'ultrabert_v2.1.0'."""
        enriched = {
            "extract_from_cache": {
                "embedding": [0.1] * 768,
                "embedding_id": str(uuid.uuid4()),
                # model_id missing
            }
        }

        await embedding_write.run(mock_envelope, enriched, mock_context)

        call_kwargs = mock_context.syscalls.vec_write.call_args[1]
        assert call_kwargs["model_id"] == "ultrabert_v2.1.0"

    @pytest.mark.asyncio
    async def test_empty_config_uses_defaults(self, mock_envelope, mock_enriched):
        """Test empty config uses default values."""
        context = Mock()
        context.config = {}  # Empty config
        context.syscalls = Mock()
        context.syscalls.vec_write = AsyncMock(return_value={"inserted": True})
        context.syscalls.outbox_emit_batch = AsyncMock()

        result = await embedding_write.run(mock_envelope, mock_enriched, context)

        assert result["written"] is True
        # Event should be emitted (default: True)
        context.syscalls.outbox_emit_batch.assert_called_once()
