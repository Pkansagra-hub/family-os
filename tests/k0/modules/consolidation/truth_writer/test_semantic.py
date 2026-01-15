"""
Tests for SemanticLayerWriter — Issue 5.2.4

Tests for st_sem layer write operations including action-based updates.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.semantic import (
    PatternAction,
    PatternWriteData,
    SemanticLayerWriter,
    _parse_rows_affected,
    create_semantic_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_SEM, StagedWrite

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
def semantic_writer():
    """Create a SemanticLayerWriter."""
    return SemanticLayerWriter()


@pytest.fixture
def sample_insert_write():
    """Create a sample INSERT StagedWrite for st_sem."""
    return StagedWrite.insert(
        layer=LAYER_ST_SEM,
        record_id="pat_001",
        data={
            "pattern_id": "pat_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "pattern_type": "temporal",
            "canonical_name": "morning_routine",
            "source_episodes_json": '["epi_1", "epi_2"]',
            "initial_confidence": 0.8,
            "current_confidence": 0.8,
            "observation_count": 2,
            "is_canonical": True,
        },
        phase="R3",
    )


@pytest.fixture
def sample_reinforce_write():
    """Create a sample REINFORCE UPDATE StagedWrite for st_sem."""
    return StagedWrite.update(
        layer=LAYER_ST_SEM,
        record_id="pat_001",
        data={
            "_action": PatternAction.REINFORCE,
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_extend_write():
    """Create a sample EXTEND UPDATE StagedWrite for st_sem."""
    return StagedWrite.update(
        layer=LAYER_ST_SEM,
        record_id="pat_001",
        data={
            "_action": PatternAction.EXTEND,
            "new_episodes": ["epi_3", "epi_4"],
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_evolve_write():
    """Create a sample EVOLVE UPDATE StagedWrite for st_sem."""
    return StagedWrite.update(
        layer=LAYER_ST_SEM,
        record_id="pat_001",
        data={
            "_action": PatternAction.EVOLVE,
            "parent_pattern_id": "pat_002",
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_archive_write():
    """Create a sample ARCHIVE StagedWrite for st_sem."""
    return StagedWrite.archive(
        layer=LAYER_ST_SEM,
        record_id="pat_001",
        reason="pattern no longer relevant",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_semantic_writer_returns_instance(self):
        """Factory should return a SemanticLayerWriter instance."""
        writer = create_semantic_writer()
        assert isinstance(writer, SemanticLayerWriter)

    def test_layer_property(self, semantic_writer):
        """Layer property should return LAYER_ST_SEM."""
        assert semantic_writer.layer == LAYER_ST_SEM

    def test_reinforce_boost_constant(self, semantic_writer):
        """REINFORCE_BOOST should be defined."""
        assert semantic_writer.REINFORCE_BOOST == 0.05


# ============================================================================
# PatternWriteData Tests
# ============================================================================


class TestPatternWriteData:
    """Tests for PatternWriteData dataclass."""

    def test_defaults(self):
        """Dataclass should have sensible defaults."""
        data = PatternWriteData(
            pattern_id="pat_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
        )
        assert data.pattern_type == "general"
        assert data.canonical_name == ""
        assert data.source_episodes_json == "[]"
        assert data.initial_confidence == 1.0
        assert data.current_confidence == 1.0
        assert data.observation_count == 1
        assert data.is_canonical is True
        assert data.parent_pattern_id is None

    def test_full_initialization(self):
        """Dataclass should accept all fields."""
        data = PatternWriteData(
            pattern_id="pat_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            pattern_type="temporal",
            canonical_name="morning_routine",
            source_episodes_json='["epi_1"]',
            initial_confidence=0.8,
            current_confidence=0.85,
            observation_count=5,
            last_observed_at_ms=1704067200000,
            is_canonical=True,
            parent_pattern_id=None,
        )
        assert data.pattern_id == "pat_001"
        assert data.pattern_type == "temporal"
        assert data.observation_count == 5


# ============================================================================
# PatternAction Tests
# ============================================================================


class TestPatternAction:
    """Tests for PatternAction enum."""

    def test_action_values(self):
        """PatternAction should have correct values."""
        assert PatternAction.REINFORCE.value == "REINFORCE"
        assert PatternAction.EXTEND.value == "EXTEND"
        assert PatternAction.EVOLVE.value == "EVOLVE"

    def test_action_is_string_enum(self):
        """PatternAction should be a string enum."""
        assert PatternAction.REINFORCE == "REINFORCE"
        assert PatternAction.EXTEND == "EXTEND"


# ============================================================================
# Write Method Tests
# ============================================================================


class TestWriteMethod:
    """Tests for the main write() method."""

    @pytest.mark.asyncio
    async def test_write_insert_success(self, semantic_writer, mock_uow, sample_insert_write):
        """INSERT should succeed and return LayerWriteResult."""
        result = await semantic_writer.write([sample_insert_write], mock_uow)

        assert result.layer == LAYER_ST_SEM
        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        assert result.failed_ids == []
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_write_skips_other_layers(self, semantic_writer, mock_uow):
        """Writer should skip writes for other layers."""
        other_layer_write = StagedWrite.insert(
            layer="st_epi",  # Different layer
            record_id="epi_001",
            data={"episode_id": "epi_001"},
            phase="R2",
        )

        result = await semantic_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        assert mock_uow.connection.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_write_multiple_operations(self, semantic_writer, mock_uow, sample_insert_write):
        """Writer should handle multiple writes."""
        writes = [
            sample_insert_write,
            StagedWrite.insert(
                layer=LAYER_ST_SEM,
                record_id="pat_002",
                data={
                    "pattern_id": "pat_002",
                    "tenant_id": "tenant_abc",
                    "space_id": "space_xyz",
                },
                phase="R3",
            ),
        ]

        result = await semantic_writer.write(writes, mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 2
        assert mock_uow.connection.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_write_continues_on_failure(self, semantic_writer, mock_uow):
        """Writer should continue processing after a failure."""
        # First call fails, second succeeds
        mock_uow.connection.execute.side_effect = [
            Exception("Database error"),
            "INSERT 0 1",
        ]

        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_SEM,
                record_id="pat_001",
                data={"pattern_id": "pat_001", "tenant_id": "t", "space_id": "s"},
                phase="R3",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_SEM,
                record_id="pat_002",
                data={"pattern_id": "pat_002", "tenant_id": "t", "space_id": "s"},
                phase="R3",
            ),
        ]

        result = await semantic_writer.write(writes, mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "pat_001" in result.failed_ids
        assert result.error_message is not None


# ============================================================================
# Insert Tests
# ============================================================================


class TestInsert:
    """Tests for INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_calls_execute(self, semantic_writer, mock_uow, sample_insert_write):
        """INSERT should call connection.execute with correct SQL."""
        await semantic_writer.write([sample_insert_write], mock_uow)

        mock_uow.connection.execute.assert_called_once()
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "INSERT INTO st_sem" in sql
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_insert_provides_all_columns(
        self, semantic_writer, mock_uow, sample_insert_write
    ):
        """INSERT should provide all required column values."""
        await semantic_writer.write([sample_insert_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        # Check positional args after SQL
        values = call_args[0][1:]

        assert "pat_001" in values  # pattern_id
        assert "tenant_abc" in values  # tenant_id
        assert "space_xyz" in values  # space_id
        assert "temporal" in values  # pattern_type


# ============================================================================
# Reinforce Action Tests
# ============================================================================


class TestReinforceAction:
    """Tests for REINFORCE action."""

    @pytest.mark.asyncio
    async def test_reinforce_boosts_confidence(
        self, semantic_writer, mock_uow, sample_reinforce_write
    ):
        """REINFORCE should boost confidence and increment observation_count."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await semantic_writer.write([sample_reinforce_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_sem" in sql
        assert "current_confidence = LEAST(current_confidence +" in sql
        assert "observation_count = observation_count + 1" in sql

    @pytest.mark.asyncio
    async def test_reinforce_updates_last_observed(
        self, semantic_writer, mock_uow, sample_reinforce_write
    ):
        """REINFORCE should update last_observed_at."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await semantic_writer.write([sample_reinforce_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "last_observed_at" in sql

    @pytest.mark.asyncio
    async def test_reinforce_version_conflict(
        self, semantic_writer, mock_uow, sample_reinforce_write
    ):
        """REINFORCE should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await semantic_writer.write([sample_reinforce_write], mock_uow)

        assert result.writes_failed == 1
        assert "pat_001" in result.failed_ids
        assert "Version conflict" in result.error_message


# ============================================================================
# Extend Action Tests
# ============================================================================


class TestExtendAction:
    """Tests for EXTEND action."""

    @pytest.mark.asyncio
    async def test_extend_merges_episodes(self, semantic_writer, mock_uow, sample_extend_write):
        """EXTEND should merge new episodes into source_episodes_json."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await semantic_writer.write([sample_extend_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_sem" in sql
        assert "source_episodes_json" in sql
        assert "jsonb_agg" in sql or "jsonb_array_elements" in sql

    @pytest.mark.asyncio
    async def test_extend_empty_episodes_returns_early(self, semantic_writer, mock_uow):
        """EXTEND with empty new_episodes should not execute."""
        write = StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id="pat_001",
            data={
                "_action": PatternAction.EXTEND,
                "new_episodes": [],  # Empty
            },
            phase="R3",
            expected_version=1,
        )

        result = await semantic_writer.write([write], mock_uow)

        # Should succeed without calling execute
        assert result.writes_succeeded == 1
        assert mock_uow.connection.execute.call_count == 0


# ============================================================================
# Evolve Action Tests
# ============================================================================


class TestEvolveAction:
    """Tests for EVOLVE action."""

    @pytest.mark.asyncio
    async def test_evolve_marks_non_canonical(self, semantic_writer, mock_uow, sample_evolve_write):
        """EVOLVE should set is_canonical to FALSE."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await semantic_writer.write([sample_evolve_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_sem" in sql
        assert "is_canonical = FALSE" in sql

    @pytest.mark.asyncio
    async def test_evolve_sets_parent(self, semantic_writer, mock_uow, sample_evolve_write):
        """EVOLVE should set parent_pattern_id."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await semantic_writer.write([sample_evolve_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        values = call_args[0][1:]

        assert "parent_pattern_id" in sql
        assert "pat_002" in values  # parent_pattern_id value


# ============================================================================
# Archive Tests
# ============================================================================


class TestArchive:
    """Tests for ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_sets_status(self, semantic_writer, mock_uow, sample_archive_write):
        """ARCHIVE should set archival_status and archived_at."""
        await semantic_writer.write([sample_archive_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_sem" in sql
        assert "archival_status = 'ARCHIVED'" in sql
        assert "archived_at" in sql
        assert "archived_reason" in sql


# ============================================================================
# Tombstone Tests
# ============================================================================


class TestTombstone:
    """Tests for TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_sets_status(self, semantic_writer, mock_uow):
        """TOMBSTONE should set archival_status to TOMBSTONE."""
        write = StagedWrite.tombstone(
            layer=LAYER_ST_SEM,
            record_id="pat_001",
            phase="R6",
        )

        await semantic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "archival_status = 'TOMBSTONE'" in sql


# ============================================================================
# Generic Update Tests
# ============================================================================


class TestGenericUpdate:
    """Tests for generic UPDATE (no action)."""

    @pytest.mark.asyncio
    async def test_generic_update_with_optimistic_lock(self, semantic_writer, mock_uow):
        """Generic UPDATE should use optimistic locking."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id="pat_001",
            data={
                "canonical_name": "updated_name",
            },
            phase="R3",
            expected_version=1,
        )

        await semantic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_sem" in sql
        assert "version = version + 1" in sql
        assert "AND version =" in sql


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
