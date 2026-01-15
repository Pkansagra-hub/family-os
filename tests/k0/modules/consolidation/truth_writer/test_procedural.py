"""
Tests for ProceduralLayerWriter — Issue 5.2.5

Tests for st_procedural layer write operations.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.procedural import (
    ProceduralLayerWriter,
    RoutineAction,
    RoutineWriteData,
    _parse_rows_affected,
    create_procedural_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_PROCEDURAL, StagedWrite

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
def procedural_writer():
    """Create a ProceduralLayerWriter."""
    return ProceduralLayerWriter()


@pytest.fixture
def sample_insert_write():
    """Create a sample INSERT StagedWrite for st_procedural."""
    return StagedWrite.insert(
        layer=LAYER_ST_PROCEDURAL,
        record_id="rtn_001",
        data={
            "routine_id": "rtn_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "routine_name": "morning_coffee",
            "action_sequence_json": '["wake_up", "brew_coffee", "drink"]',
            "trigger_conditions_json": '{"time": "07:00"}',
            "expected_outcomes_json": '["caffeinated"]',
            "temporal_regularity": 0.85,
            "daily_pattern": "0 7 * * *",
            "confidence": 0.9,
        },
        phase="R3",
    )


@pytest.fixture
def sample_reinforce_write():
    """Create a sample REINFORCE UPDATE StagedWrite for st_procedural."""
    return StagedWrite.update(
        layer=LAYER_ST_PROCEDURAL,
        record_id="rtn_001",
        data={
            "_action": RoutineAction.REINFORCE,
            "new_regularity": 0.9,
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_extend_write():
    """Create a sample EXTEND UPDATE StagedWrite for st_procedural."""
    return StagedWrite.update(
        layer=LAYER_ST_PROCEDURAL,
        record_id="rtn_001",
        data={
            "_action": RoutineAction.EXTEND,
            "new_actions_json": '["read_news"]',
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_archive_write():
    """Create a sample ARCHIVE StagedWrite for st_procedural."""
    return StagedWrite.archive(
        layer=LAYER_ST_PROCEDURAL,
        record_id="rtn_001",
        reason="routine no longer followed",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_procedural_writer_returns_instance(self):
        """Factory should return a ProceduralLayerWriter instance."""
        writer = create_procedural_writer()
        assert isinstance(writer, ProceduralLayerWriter)

    def test_layer_property(self, procedural_writer):
        """Layer property should return LAYER_ST_PROCEDURAL."""
        assert procedural_writer.layer == LAYER_ST_PROCEDURAL

    def test_reinforce_factor_constant(self, procedural_writer):
        """REINFORCE_FACTOR should be defined."""
        assert procedural_writer.REINFORCE_FACTOR == 1.1


# ============================================================================
# RoutineWriteData Tests
# ============================================================================


class TestRoutineWriteData:
    """Tests for RoutineWriteData dataclass."""

    def test_defaults(self):
        """Dataclass should have sensible defaults."""
        data = RoutineWriteData(
            routine_id="rtn_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
        )
        assert data.routine_name == ""
        assert data.action_sequence_json == "[]"
        assert data.trigger_conditions_json == "{}"
        assert data.expected_outcomes_json == "[]"
        assert data.temporal_regularity == 0.0
        assert data.daily_pattern is None
        assert data.weekly_pattern is None
        assert data.confidence == 1.0
        assert data.value_function is None

    def test_full_initialization(self):
        """Dataclass should accept all fields."""
        data = RoutineWriteData(
            routine_id="rtn_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            routine_name="morning_coffee",
            action_sequence_json='["step1", "step2"]',
            trigger_conditions_json='{"time": "07:00"}',
            expected_outcomes_json='["outcome1"]',
            temporal_regularity=0.85,
            daily_pattern="0 7 * * *",
            weekly_pattern="0 7 * * 1-5",
            confidence=0.9,
            value_function=0.75,
        )
        assert data.routine_id == "rtn_001"
        assert data.routine_name == "morning_coffee"
        assert data.temporal_regularity == 0.85
        assert data.value_function == 0.75


# ============================================================================
# RoutineAction Tests
# ============================================================================


class TestRoutineAction:
    """Tests for RoutineAction enum."""

    def test_action_values(self):
        """RoutineAction should have correct values."""
        assert RoutineAction.REINFORCE.value == "REINFORCE"
        assert RoutineAction.EXTEND.value == "EXTEND"

    def test_action_is_string_enum(self):
        """RoutineAction should be a string enum."""
        assert RoutineAction.REINFORCE == "REINFORCE"
        assert RoutineAction.EXTEND == "EXTEND"


# ============================================================================
# Write Method Tests
# ============================================================================


class TestWriteMethod:
    """Tests for the main write() method."""

    @pytest.mark.asyncio
    async def test_write_insert_success(self, procedural_writer, mock_uow, sample_insert_write):
        """INSERT should succeed and return LayerWriteResult."""
        result = await procedural_writer.write([sample_insert_write], mock_uow)

        assert result.layer == LAYER_ST_PROCEDURAL
        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        assert result.failed_ids == []
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_write_skips_other_layers(self, procedural_writer, mock_uow):
        """Writer should skip writes for other layers."""
        other_layer_write = StagedWrite.insert(
            layer="st_epi",  # Different layer
            record_id="epi_001",
            data={"episode_id": "epi_001"},
            phase="R2",
        )

        result = await procedural_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        assert mock_uow.connection.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_write_continues_on_failure(self, procedural_writer, mock_uow):
        """Writer should continue processing after a failure."""
        # First call fails, second succeeds
        mock_uow.connection.execute.side_effect = [
            Exception("Database error"),
            "INSERT 0 1",
        ]

        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_PROCEDURAL,
                record_id="rtn_001",
                data={"routine_id": "rtn_001", "tenant_id": "t", "space_id": "s"},
                phase="R3",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_PROCEDURAL,
                record_id="rtn_002",
                data={"routine_id": "rtn_002", "tenant_id": "t", "space_id": "s"},
                phase="R3",
            ),
        ]

        result = await procedural_writer.write(writes, mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "rtn_001" in result.failed_ids


# ============================================================================
# Insert Tests
# ============================================================================


class TestInsert:
    """Tests for INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_calls_execute(self, procedural_writer, mock_uow, sample_insert_write):
        """INSERT should call connection.execute with correct SQL."""
        await procedural_writer.write([sample_insert_write], mock_uow)

        mock_uow.connection.execute.assert_called_once()
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "INSERT INTO st_procedural" in sql
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_insert_provides_all_columns(
        self, procedural_writer, mock_uow, sample_insert_write
    ):
        """INSERT should provide all required column values."""
        await procedural_writer.write([sample_insert_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        # Check positional args after SQL
        values = call_args[0][1:]

        assert "rtn_001" in values  # routine_id
        assert "tenant_abc" in values  # tenant_id
        assert "morning_coffee" in values  # routine_name


# ============================================================================
# Reinforce Action Tests
# ============================================================================


class TestReinforceAction:
    """Tests for REINFORCE action."""

    @pytest.mark.asyncio
    async def test_reinforce_boosts_confidence(
        self, procedural_writer, mock_uow, sample_reinforce_write
    ):
        """REINFORCE should boost confidence and update regularity."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await procedural_writer.write([sample_reinforce_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_procedural" in sql
        assert "confidence = LEAST(confidence *" in sql
        assert "temporal_regularity" in sql

    @pytest.mark.asyncio
    async def test_reinforce_version_conflict(
        self, procedural_writer, mock_uow, sample_reinforce_write
    ):
        """REINFORCE should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await procedural_writer.write([sample_reinforce_write], mock_uow)

        assert result.writes_failed == 1
        assert "rtn_001" in result.failed_ids
        assert "Version conflict" in result.error_message


# ============================================================================
# Extend Action Tests
# ============================================================================


class TestExtendAction:
    """Tests for EXTEND action."""

    @pytest.mark.asyncio
    async def test_extend_appends_actions(self, procedural_writer, mock_uow, sample_extend_write):
        """EXTEND should append actions to action_sequence_json."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await procedural_writer.write([sample_extend_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_procedural" in sql
        assert "action_sequence_json" in sql
        assert "jsonb_agg" in sql or "jsonb_array_elements" in sql


# ============================================================================
# Archive Tests
# ============================================================================


class TestArchive:
    """Tests for ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_sets_status(self, procedural_writer, mock_uow, sample_archive_write):
        """ARCHIVE should set archival_status and archived_at."""
        await procedural_writer.write([sample_archive_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_procedural" in sql
        assert "archival_status = 'ARCHIVED'" in sql
        assert "archived_at" in sql

    @pytest.mark.asyncio
    async def test_archive_default_reason(self, procedural_writer, mock_uow):
        """ARCHIVE without reason should use 'decay' as default."""
        write = StagedWrite.archive(
            layer=LAYER_ST_PROCEDURAL,
            record_id="rtn_001",
            reason="",  # Empty reason
            phase="R6",
        )

        await procedural_writer.write([write], mock_uow)

        # The SQL should still work with empty reason
        mock_uow.connection.execute.assert_called_once()


# ============================================================================
# Tombstone Tests
# ============================================================================


class TestTombstone:
    """Tests for TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_sets_status(self, procedural_writer, mock_uow):
        """TOMBSTONE should set archival_status to TOMBSTONE."""
        write = StagedWrite.tombstone(
            layer=LAYER_ST_PROCEDURAL,
            record_id="rtn_001",
            phase="R6",
        )

        await procedural_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "archival_status = 'TOMBSTONE'" in sql


# ============================================================================
# Generic Update Tests
# ============================================================================


class TestGenericUpdate:
    """Tests for generic UPDATE (no action)."""

    @pytest.mark.asyncio
    async def test_generic_update_with_optimistic_lock(self, procedural_writer, mock_uow):
        """Generic UPDATE should use optimistic locking."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_PROCEDURAL,
            record_id="rtn_001",
            data={
                "routine_name": "updated_routine",
            },
            phase="R3",
            expected_version=1,
        )

        await procedural_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_procedural" in sql
        assert "version = version + 1" in sql


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestParseRowsAffected:
    """Tests for _parse_rows_affected helper."""

    def test_parse_update_result(self):
        """Should parse UPDATE result."""
        assert _parse_rows_affected("UPDATE 1") == 1
        assert _parse_rows_affected("UPDATE 0") == 0

    def test_parse_insert_result(self):
        """Should parse INSERT result."""
        assert _parse_rows_affected("INSERT 0 1") == 1

    def test_parse_none_result(self):
        """Should handle None result."""
        assert _parse_rows_affected(None) == 0

    def test_parse_empty_result(self):
        """Should handle empty result."""
        assert _parse_rows_affected("") == 0
