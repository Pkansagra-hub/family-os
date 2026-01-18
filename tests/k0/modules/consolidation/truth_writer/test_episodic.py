"""
Tests for EpisodicLayerWriter — Issue 5.2.3

Tests for st_epi layer write operations.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.episodic import (
    EpisodeWriteData,
    EpisodicLayerWriter,
    _parse_rows_affected,
    create_episodic_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_EPI, StagedWrite

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork with async connection."""
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.execute = AsyncMock(return_value="INSERT 0 1")
    return uow


@pytest.fixture
def episodic_writer():
    """Create an EpisodicLayerWriter."""
    return EpisodicLayerWriter()


@pytest.fixture
def sample_insert_write():
    """Create a sample INSERT StagedWrite for st_epi."""
    return StagedWrite.insert(
        layer=LAYER_ST_EPI,
        record_id="epi_001",
        data={
            "episode_id": "epi_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "cluster_id": "cluster_001",
            "source_events_json": '["evt_1", "evt_2"]',
            "started_at": 1704067200000,
            "ended_at": 1704070800000,
            "temporal_spread_ms": 3600000,
            "confidence": 0.85,
            "observation_count": 5,
        },
        phase="R2",
    )


@pytest.fixture
def sample_update_write():
    """Create a sample UPDATE StagedWrite for st_epi."""
    return StagedWrite.update(
        layer=LAYER_ST_EPI,
        record_id="epi_001",
        data={
            "confidence": 0.95,
            "observation_count": 6,
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_archive_write():
    """Create a sample ARCHIVE StagedWrite for st_epi."""
    return StagedWrite.archive(
        layer=LAYER_ST_EPI,
        record_id="epi_001",
        reason="superseded by newer episode",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_episodic_writer_returns_instance(self):
        """Factory should return an EpisodicLayerWriter instance."""
        writer = create_episodic_writer()
        assert isinstance(writer, EpisodicLayerWriter)

    def test_layer_property(self, episodic_writer):
        """Layer property should return LAYER_ST_EPI."""
        assert episodic_writer.layer == LAYER_ST_EPI


# ============================================================================
# EpisodeWriteData Tests
# ============================================================================


class TestEpisodeWriteData:
    """Tests for EpisodeWriteData dataclass."""

    def test_defaults(self):
        """Dataclass should have sensible defaults."""
        data = EpisodeWriteData(
            episode_id="epi_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
        )
        assert data.cluster_id is None
        assert data.source_events_json == "[]"
        assert data.started_at_ms == 0
        assert data.ended_at_ms == 0
        assert data.temporal_spread_ms == 0
        assert data.confidence == 1.0
        assert data.observation_count == 1

    def test_full_initialization(self):
        """Dataclass should accept all fields."""
        data = EpisodeWriteData(
            episode_id="epi_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            cluster_id="cluster_001",
            source_events_json='["evt_1"]',
            started_at_ms=1704067200000,
            ended_at_ms=1704070800000,
            temporal_spread_ms=3600000,
            confidence=0.85,
            observation_count=5,
        )
        assert data.episode_id == "epi_001"
        assert data.cluster_id == "cluster_001"
        assert data.temporal_spread_ms == 3600000


# ============================================================================
# Write Method Tests
# ============================================================================


class TestWriteMethod:
    """Tests for the main write() method."""

    @pytest.mark.asyncio
    async def test_write_insert_success(self, episodic_writer, mock_uow, sample_insert_write):
        """INSERT should succeed and return LayerWriteResult."""
        result = await episodic_writer.write([sample_insert_write], mock_uow)

        assert result.layer == LAYER_ST_EPI
        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        assert result.failed_ids == []
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_write_skips_other_layers(self, episodic_writer, mock_uow):
        """Writer should skip writes for other layers."""
        other_layer_write = StagedWrite.insert(
            layer="st_sem",  # Different layer
            record_id="pattern_001",
            data={"pattern_id": "pattern_001"},
            phase="R3",
        )

        result = await episodic_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        assert mock_uow.connection.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_write_multiple_operations(self, episodic_writer, mock_uow, sample_insert_write):
        """Writer should handle multiple writes."""
        writes = [
            sample_insert_write,
            StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id="epi_002",
                data={
                    "episode_id": "epi_002",
                    "tenant_id": "tenant_abc",
                    "space_id": "space_xyz",
                },
                phase="R2",
            ),
        ]

        result = await episodic_writer.write(writes, mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 2
        # With observation recording: 2 INSERTs + observation INSERTs
        assert mock_uow.connection.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_write_continues_on_failure(self, episodic_writer, mock_uow):
        """Writer should continue processing after a failure."""
        # First call fails, second succeeds
        mock_uow.connection.execute.side_effect = [
            Exception("Database error"),
            "INSERT 0 1",
        ]

        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id="epi_001",
                data={"episode_id": "epi_001", "tenant_id": "t", "space_id": "s"},
                phase="R2",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id="epi_002",
                data={"episode_id": "epi_002", "tenant_id": "t", "space_id": "s"},
                phase="R2",
            ),
        ]

        result = await episodic_writer.write(writes, mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "epi_001" in result.failed_ids
        assert result.error_message is not None


# ============================================================================
# Insert Tests
# ============================================================================


class TestInsert:
    """Tests for INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_calls_execute(self, episodic_writer, mock_uow, sample_insert_write):
        """INSERT should call connection.execute with correct SQL."""
        await episodic_writer.write([sample_insert_write], mock_uow)

        # Issue 7.5: Now 2 calls - INSERT + observation recording
        assert mock_uow.connection.execute.call_count >= 1
        # First call should be the INSERT
        call_args = mock_uow.connection.execute.call_args_list[0]
        sql = call_args[0][0]

        assert "INSERT INTO st_epi" in sql
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_insert_provides_all_columns(
        self, episodic_writer, mock_uow, sample_insert_write
    ):
        """INSERT should provide all required column values."""
        await episodic_writer.write([sample_insert_write], mock_uow)

        # Issue 7.5: First call is the INSERT
        call_args = mock_uow.connection.execute.call_args_list[0]
        # Check positional args after SQL
        values = call_args[0][1:]

        assert "epi_001" in values  # episode_id
        assert "tenant_abc" in values  # tenant_id
        assert "space_xyz" in values  # space_id
        assert "cluster_001" in values  # cluster_id


# ============================================================================
# Update Tests
# ============================================================================


class TestUpdate:
    """Tests for UPDATE operation."""

    @pytest.mark.asyncio
    async def test_update_with_optimistic_lock(
        self, episodic_writer, mock_uow, sample_update_write
    ):
        """UPDATE should use optimistic locking."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await episodic_writer.write([sample_update_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_epi" in sql
        assert "version = version + 1" in sql
        assert "AND version =" in sql

    @pytest.mark.asyncio
    async def test_update_version_conflict_raises(
        self, episodic_writer, mock_uow, sample_update_write
    ):
        """UPDATE should raise OptimisticLockError on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await episodic_writer.write([sample_update_write], mock_uow)

        assert result.writes_failed == 1
        assert "epi_001" in result.failed_ids
        assert "Version conflict" in result.error_message

    @pytest.mark.asyncio
    async def test_update_empty_data_returns_early(self, episodic_writer, mock_uow):
        """UPDATE with no updatable fields should return early."""
        write = StagedWrite.update(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",  # Primary key, excluded
            },
            phase="R3",
            expected_version=1,
        )

        result = await episodic_writer.write([write], mock_uow)

        # Should succeed but not call execute (no fields to update)
        assert result.writes_succeeded == 1
        assert mock_uow.connection.execute.call_count == 0


# ============================================================================
# Archive Tests
# ============================================================================


class TestArchive:
    """Tests for ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_sets_status(self, episodic_writer, mock_uow, sample_archive_write):
        """ARCHIVE should set archival_status and archived_at."""
        await episodic_writer.write([sample_archive_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_epi" in sql
        assert "archival_status = 'ARCHIVED'" in sql
        assert "archived_at" in sql
        assert "archived_reason" in sql


# ============================================================================
# Tombstone Tests
# ============================================================================


class TestTombstone:
    """Tests for TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_sets_status(self, episodic_writer, mock_uow):
        """TOMBSTONE should set archival_status to TOMBSTONE."""
        write = StagedWrite.tombstone(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            phase="R6",
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "archival_status = 'TOMBSTONE'" in sql


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestParseRowsAffected:
    """Tests for _parse_rows_affected helper."""

    def test_parse_update_result(self):
        """Should parse UPDATE result."""
        assert _parse_rows_affected("UPDATE 1") == 1
        assert _parse_rows_affected("UPDATE 0") == 0
        assert _parse_rows_affected("UPDATE 15") == 15

    def test_parse_insert_result(self):
        """Should parse INSERT result."""
        assert _parse_rows_affected("INSERT 0 1") == 1
        assert _parse_rows_affected("INSERT 0 0") == 0

    def test_parse_none_result(self):
        """Should handle None result."""
        assert _parse_rows_affected(None) == 0

    def test_parse_empty_result(self):
        """Should handle empty result."""
        assert _parse_rows_affected("") == 0

    def test_parse_invalid_result(self):
        """Should handle invalid result."""
        assert _parse_rows_affected("invalid") == 0
