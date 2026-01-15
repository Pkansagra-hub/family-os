"""
Tests for VectorLayerWriter — Issue 5.2.9

Tests for st_vec layer write operations with P08 coordination.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.vector import (
    P08_EMBEDDING_CREATED,
    P08_EMBEDDING_UPDATED,
    EmbeddingWriteData,
    P08CircuitBreakerConfig,
    VectorLayerWriter,
    create_vector_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_VEC, StagedWrite

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork with async connection and outbox staging."""
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.execute = AsyncMock(return_value="INSERT 0 1")
    uow.stage_outbox = MagicMock()
    return uow


@pytest.fixture
def vector_writer():
    """Create a VectorLayerWriter with default config."""
    return VectorLayerWriter()


@pytest.fixture
def vector_writer_with_config():
    """Create a VectorLayerWriter with custom config."""
    config = P08CircuitBreakerConfig(
        failure_threshold=3,
        reset_timeout_ms=30000,
        use_cached_on_failure=True,
    )
    return VectorLayerWriter(p08_config=config)


@pytest.fixture
def sample_embedding():
    """Create a sample embedding bytes."""
    import struct

    # 4 float32 values
    return struct.pack("4f", 0.1, 0.2, 0.3, 0.4)


@pytest.fixture
def sample_insert_write(sample_embedding):
    """Create a sample INSERT StagedWrite for st_vec."""
    return StagedWrite.insert(
        layer=LAYER_ST_VEC,
        record_id="emb_001",
        data={
            "embedding_id": "emb_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "source_type": "entity",
            "source_id": "entity_001",
            "embedding": sample_embedding,
            "model_version": "text-embedding-3-small-v1",
            "source_count": 5,
            "aggregation_method": "mean",
        },
        phase="R5",
    )


@pytest.fixture
def sample_update_write(sample_embedding):
    """Create a sample UPDATE StagedWrite for st_vec."""
    return StagedWrite.update(
        layer=LAYER_ST_VEC,
        record_id="emb_001",
        data={
            "embedding_id": "emb_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "embedding": sample_embedding,
            "source_count": 10,
            "model_version": "text-embedding-3-small-v1",
            "aggregation_method": "weighted_mean",
        },
        phase="R5",
        expected_version=1,
    )


@pytest.fixture
def sample_archive_write():
    """Create a sample ARCHIVE StagedWrite for st_vec."""
    return StagedWrite.archive(
        layer=LAYER_ST_VEC,
        record_id="emb_001",
        reason="stale",
        phase="R6",
    )


@pytest.fixture
def sample_tombstone_write():
    """Create a sample TOMBSTONE StagedWrite for st_vec."""
    return StagedWrite.tombstone(
        layer=LAYER_ST_VEC,
        record_id="emb_001",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_vector_writer_returns_instance(self):
        """Factory should return a VectorLayerWriter instance."""
        writer = create_vector_writer()
        assert isinstance(writer, VectorLayerWriter)

    def test_create_vector_writer_with_config(self):
        """Factory should accept P08 config."""
        config = P08CircuitBreakerConfig(failure_threshold=10)
        writer = create_vector_writer(p08_config=config)
        assert writer._p08_config.failure_threshold == 10

    def test_layer_property(self, vector_writer):
        """Layer property should return LAYER_ST_VEC."""
        assert vector_writer.layer == LAYER_ST_VEC


# ============================================================================
# EmbeddingWriteData Tests
# ============================================================================


class TestEmbeddingWriteData:
    """Tests for EmbeddingWriteData dataclass."""

    def test_create_with_all_fields(self, sample_embedding):
        """Should create with all fields."""
        data = EmbeddingWriteData(
            embedding_id="emb_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            source_type="entity",
            source_id="entity_001",
            embedding=sample_embedding,
            model_version="text-embedding-3-small-v1",
            source_count=5,
            aggregation_method="mean",
        )
        assert data.embedding_id == "emb_001"
        assert data.source_type == "entity"
        assert data.embedding == sample_embedding

    def test_create_with_defaults(self):
        """Should create with default values."""
        data = EmbeddingWriteData(
            embedding_id="emb_002",
            tenant_id="tenant_abc",
            space_id="space_xyz",
        )
        assert data.source_type == "entity"
        assert data.source_id == ""
        assert data.embedding == b""
        assert data.model_version == "unknown"
        assert data.source_count == 1
        assert data.aggregation_method == "mean"


# ============================================================================
# P08CircuitBreakerConfig Tests
# ============================================================================


class TestP08CircuitBreakerConfig:
    """Tests for P08CircuitBreakerConfig."""

    def test_default_values(self):
        """Should have correct defaults."""
        config = P08CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.reset_timeout_ms == 60000
        assert config.use_cached_on_failure is True

    def test_custom_values(self):
        """Should accept custom values."""
        config = P08CircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout_ms=120000,
            use_cached_on_failure=False,
        )
        assert config.failure_threshold == 10
        assert config.reset_timeout_ms == 120000
        assert config.use_cached_on_failure is False


# ============================================================================
# INSERT Tests
# ============================================================================


class TestInsert:
    """Tests for INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_embedding(self, vector_writer, mock_uow, sample_insert_write):
        """Should insert new embedding."""
        result = await vector_writer.write([sample_insert_write], mock_uow)

        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        mock_uow.connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_stages_p08_event(self, vector_writer, mock_uow, sample_insert_write):
        """Should stage P08 notification event on INSERT."""
        await vector_writer.write([sample_insert_write], mock_uow)

        # P08 notification should be staged
        mock_uow.stage_outbox.assert_called_once()
        staged_entry = mock_uow.stage_outbox.call_args[0][0]
        assert staged_entry.op_kind == P08_EMBEDDING_CREATED
        assert staged_entry.driver == "p08"

    @pytest.mark.asyncio
    async def test_insert_p08_payload_format(self, vector_writer, mock_uow, sample_insert_write):
        """Should format P08 payload correctly."""
        await vector_writer.write([sample_insert_write], mock_uow)

        staged_entry = mock_uow.stage_outbox.call_args[0][0]
        payload = json.loads(staged_entry.payload.decode("utf-8"))

        assert payload["embedding_id"] == "emb_001"
        assert payload["tenant_id"] == "tenant_abc"
        assert payload["source_type"] == "entity"
        assert payload["event_type"] == "created"
        assert "timestamp_ms" in payload

    @pytest.mark.asyncio
    async def test_insert_minimal_fields(self, vector_writer, mock_uow):
        """Should insert with minimal required fields."""
        write = StagedWrite.insert(
            layer=LAYER_ST_VEC,
            record_id="emb_min",
            data={
                "embedding_id": "emb_min",
                "tenant_id": "tenant",
                "space_id": "space",
            },
            phase="R5",
        )

        result = await vector_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "ON CONFLICT (embedding_id) DO NOTHING" in call_args[0][0]


# ============================================================================
# UPDATE Tests
# ============================================================================


class TestUpdate:
    """Tests for UPDATE operation."""

    @pytest.mark.asyncio
    async def test_update_embedding(self, vector_writer, mock_uow, sample_update_write):
        """Should update embedding with new vector."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await vector_writer.write([sample_update_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "embedding = COALESCE($1, embedding)" in sql
        assert "version = version + 1" in sql

    @pytest.mark.asyncio
    async def test_update_stages_p08_event(self, vector_writer, mock_uow, sample_update_write):
        """Should stage P08 notification event on UPDATE."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await vector_writer.write([sample_update_write], mock_uow)

        mock_uow.stage_outbox.assert_called_once()
        staged_entry = mock_uow.stage_outbox.call_args[0][0]
        assert staged_entry.op_kind == P08_EMBEDDING_UPDATED

    @pytest.mark.asyncio
    async def test_update_version_conflict(self, vector_writer, mock_uow, sample_update_write):
        """Should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await vector_writer.write([sample_update_write], mock_uow)

        assert result.writes_succeeded == 0
        assert result.writes_failed == 1
        assert "emb_001" in result.failed_ids


# ============================================================================
# ARCHIVE Tests
# ============================================================================


class TestArchive:
    """Tests for ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_embedding(self, vector_writer, mock_uow, sample_archive_write):
        """Should archive stale embedding."""
        result = await vector_writer.write([sample_archive_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "archival_status = 'ARCHIVED'" in sql
        assert "archived_reason = $2" in sql

    @pytest.mark.asyncio
    async def test_archive_does_not_notify_p08(self, vector_writer, mock_uow, sample_archive_write):
        """ARCHIVE should not notify P08."""
        await vector_writer.write([sample_archive_write], mock_uow)

        # No P08 event for archive
        mock_uow.stage_outbox.assert_not_called()


# ============================================================================
# TOMBSTONE Tests
# ============================================================================


class TestTombstone:
    """Tests for TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_embedding(self, vector_writer, mock_uow, sample_tombstone_write):
        """Should tombstone embedding for GDPR deletion."""
        result = await vector_writer.write([sample_tombstone_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "embedding = NULL" in sql
        assert "archival_status = 'TOMBSTONE'" in sql
        assert "gdpr_deletion" in sql


# ============================================================================
# Circuit Breaker Tests
# ============================================================================


class TestCircuitBreaker:
    """Tests for P08 circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_closed_initially(self, vector_writer, mock_uow, sample_insert_write):
        """Circuit should be closed initially."""
        await vector_writer.write([sample_insert_write], mock_uow)

        # Should attempt P08 notification
        mock_uow.stage_outbox.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(
        self, vector_writer_with_config, mock_uow, sample_insert_write
    ):
        """Circuit should open after failure threshold."""
        import time

        writer = vector_writer_with_config
        writer._p08_failures = 3  # At threshold
        writer._last_failure_ms = int(time.time() * 1000)  # Recent failure

        await writer.write([sample_insert_write], mock_uow)

        # Circuit open - should not attempt P08 notification
        mock_uow.stage_outbox.assert_not_called()

    def test_reset_circuit_breaker(self, vector_writer):
        """Should be able to manually reset circuit breaker."""
        vector_writer._p08_failures = 10
        vector_writer._last_failure_ms = 1000

        vector_writer.reset_circuit_breaker()

        assert vector_writer._p08_failures == 0
        assert vector_writer._last_failure_ms == 0

    def test_circuit_half_open_after_timeout(self, vector_writer_with_config):
        """Circuit should reset after timeout."""
        writer = vector_writer_with_config
        writer._p08_failures = 5
        # Set last failure to be beyond reset timeout
        writer._last_failure_ms = 0

        # Should be open due to failures, but timeout has passed
        assert not writer._is_circuit_open()
        assert writer._p08_failures == 0  # Reset on check


# ============================================================================
# Embedding Aggregation Tests
# ============================================================================


class TestEmbeddingAggregation:
    """Tests for embedding aggregation utility."""

    def test_aggregate_mean(self):
        """Should aggregate embeddings with mean."""
        import struct

        e1 = struct.pack("4f", 1.0, 2.0, 3.0, 4.0)
        e2 = struct.pack("4f", 2.0, 4.0, 6.0, 8.0)

        result = VectorLayerWriter.aggregate_embeddings([e1, e2], method="mean")

        # Unpack result
        import numpy as np

        arr = np.frombuffer(result, dtype=np.float32)
        np.testing.assert_array_almost_equal(arr, [1.5, 3.0, 4.5, 6.0])

    def test_aggregate_max(self):
        """Should aggregate embeddings with max."""
        import struct

        e1 = struct.pack("4f", 1.0, 4.0, 3.0, 8.0)
        e2 = struct.pack("4f", 2.0, 2.0, 6.0, 4.0)

        result = VectorLayerWriter.aggregate_embeddings([e1, e2], method="max")

        import numpy as np

        arr = np.frombuffer(result, dtype=np.float32)
        np.testing.assert_array_almost_equal(arr, [2.0, 4.0, 6.0, 8.0])

    def test_aggregate_weighted_mean(self):
        """Should aggregate embeddings with weighted mean."""
        import struct

        e1 = struct.pack("4f", 0.0, 0.0, 0.0, 0.0)
        e2 = struct.pack("4f", 2.0, 4.0, 6.0, 8.0)

        result = VectorLayerWriter.aggregate_embeddings(
            [e1, e2], method="weighted_mean", weights=[0.25, 0.75]
        )

        import numpy as np

        arr = np.frombuffer(result, dtype=np.float32)
        np.testing.assert_array_almost_equal(arr, [1.5, 3.0, 4.5, 6.0])

    def test_aggregate_empty_raises(self):
        """Should raise on empty embeddings list."""
        with pytest.raises(ValueError, match="empty"):
            VectorLayerWriter.aggregate_embeddings([])

    def test_aggregate_default_to_mean(self):
        """Unknown method should default to mean."""
        import struct

        e1 = struct.pack("4f", 1.0, 2.0, 3.0, 4.0)
        e2 = struct.pack("4f", 2.0, 4.0, 6.0, 8.0)

        result = VectorLayerWriter.aggregate_embeddings([e1, e2], method="unknown_method")

        import numpy as np

        arr = np.frombuffer(result, dtype=np.float32)
        np.testing.assert_array_almost_equal(arr, [1.5, 3.0, 4.5, 6.0])


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_continues_on_failure(self, vector_writer, mock_uow):
        """Should continue processing after failure."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_VEC,
                record_id="emb_001",
                data={
                    "embedding_id": "emb_001",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R5",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_VEC,
                record_id="emb_002",
                data={
                    "embedding_id": "emb_002",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R5",
            ),
        ]

        mock_uow.connection.execute.side_effect = [
            "INSERT 0 1",
            Exception("DB error"),
        ]

        result = await vector_writer.write(writes, mock_uow)

        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "emb_002" in result.failed_ids

    @pytest.mark.asyncio
    async def test_ignores_other_layers(self, vector_writer, mock_uow):
        """Should ignore writes for other layers."""
        from k0.pipelines.p03.staged_writes import LAYER_ST_EPI

        other_layer_write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="ep_001",
            data={"episode_id": "ep_001", "tenant_id": "t", "space_id": "s"},
            phase="R7",
        )

        result = await vector_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        mock_uow.connection.execute.assert_not_called()


# ============================================================================
# Multiple Writes Tests
# ============================================================================


class TestMultipleWrites:
    """Tests for processing multiple writes."""

    @pytest.mark.asyncio
    async def test_multiple_inserts(self, vector_writer, mock_uow, sample_embedding):
        """Should process multiple INSERTs with P08 notifications."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_VEC,
                record_id=f"emb_{i:03d}",
                data={
                    "embedding_id": f"emb_{i:03d}",
                    "tenant_id": "tenant",
                    "space_id": "space",
                    "source_type": "entity",
                    "source_id": f"entity_{i}",
                    "embedding": sample_embedding,
                },
                phase="R5",
            )
            for i in range(3)
        ]

        result = await vector_writer.write(writes, mock_uow)

        assert result.writes_attempted == 3
        assert result.writes_succeeded == 3
        assert mock_uow.connection.execute.call_count == 3
        assert mock_uow.stage_outbox.call_count == 3
