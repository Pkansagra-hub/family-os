"""
Tests for SocialLayerWriter — Issue 5.2.6

Tests for st_social layer write operations including relationship tracking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.social import (
    RelationshipAction,
    RelationshipWriteData,
    SocialLayerWriter,
    _parse_rows_affected,
    create_social_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_SOCIAL, StagedWrite

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
def social_writer():
    """Create a SocialLayerWriter."""
    return SocialLayerWriter()


@pytest.fixture
def sample_insert_write():
    """Create a sample INSERT StagedWrite for st_social."""
    return StagedWrite.insert(
        layer=LAYER_ST_SOCIAL,
        record_id="rel_001",
        data={
            "relationship_id": "rel_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "actor_a_id": "person_alice",
            "actor_b_id": "person_bob",
            "relationship_type": "friend",
            "strength": 0.7,
            "interaction_count": 5,
            "sentiment_avg": 0.6,
            "interaction_types_json": '["chat", "meeting"]',
        },
        phase="R3",
    )


@pytest.fixture
def sample_reinforce_write():
    """Create a sample REINFORCE UPDATE StagedWrite for st_social."""
    return StagedWrite.update(
        layer=LAYER_ST_SOCIAL,
        record_id="rel_001",
        data={
            "_action": RelationshipAction.REINFORCE,
            "new_sentiment": 0.8,
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_extend_write():
    """Create a sample EXTEND UPDATE StagedWrite for st_social."""
    return StagedWrite.update(
        layer=LAYER_ST_SOCIAL,
        record_id="rel_001",
        data={
            "_action": RelationshipAction.EXTEND,
            "new_types_json": '["call", "email"]',
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_decay_write():
    """Create a sample DECAY UPDATE StagedWrite for st_social."""
    return StagedWrite.update(
        layer=LAYER_ST_SOCIAL,
        record_id="rel_001",
        data={
            "_action": RelationshipAction.DECAY,
        },
        phase="R3",
        expected_version=1,
    )


@pytest.fixture
def sample_archive_write():
    """Create a sample ARCHIVE StagedWrite for st_social."""
    return StagedWrite.archive(
        layer=LAYER_ST_SOCIAL,
        record_id="rel_001",
        reason="no recent interactions",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_social_writer_returns_instance(self):
        """Factory should return a SocialLayerWriter instance."""
        writer = create_social_writer()
        assert isinstance(writer, SocialLayerWriter)

    def test_layer_property(self, social_writer):
        """Layer property should return LAYER_ST_SOCIAL."""
        assert social_writer.layer == LAYER_ST_SOCIAL

    def test_constants_defined(self, social_writer):
        """Writer constants should be defined."""
        assert social_writer.REINFORCE_FACTOR == 1.1
        assert social_writer.DECAY_FACTOR == 0.95
        assert social_writer.SENTIMENT_NEW_WEIGHT == 0.1
        assert social_writer.SENTIMENT_OLD_WEIGHT == 0.9


# ============================================================================
# RelationshipWriteData Tests
# ============================================================================


class TestRelationshipWriteData:
    """Tests for RelationshipWriteData dataclass."""

    def test_defaults(self):
        """Dataclass should have sensible defaults."""
        data = RelationshipWriteData(
            relationship_id="rel_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            actor_a_id="alice",
            actor_b_id="bob",
        )
        assert data.relationship_type == "unknown"
        assert data.strength == 0.5
        assert data.interaction_count == 1
        assert data.last_interaction_at_ms == 0
        assert data.sentiment_avg == 0.0
        assert data.interaction_types_json == "[]"

    def test_full_initialization(self):
        """Dataclass should accept all fields."""
        data = RelationshipWriteData(
            relationship_id="rel_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            actor_a_id="alice",
            actor_b_id="bob",
            relationship_type="friend",
            strength=0.8,
            interaction_count=10,
            last_interaction_at_ms=1704067200000,
            sentiment_avg=0.7,
            interaction_types_json='["chat", "call"]',
        )
        assert data.relationship_id == "rel_001"
        assert data.relationship_type == "friend"
        assert data.strength == 0.8
        assert data.interaction_count == 10


# ============================================================================
# RelationshipAction Tests
# ============================================================================


class TestRelationshipAction:
    """Tests for RelationshipAction enum."""

    def test_action_values(self):
        """RelationshipAction should have correct values."""
        assert RelationshipAction.REINFORCE.value == "REINFORCE"
        assert RelationshipAction.EXTEND.value == "EXTEND"
        assert RelationshipAction.DECAY.value == "DECAY"

    def test_action_is_string_enum(self):
        """RelationshipAction should be a string enum."""
        assert RelationshipAction.REINFORCE == "REINFORCE"
        assert RelationshipAction.DECAY == "DECAY"


# ============================================================================
# Write Method Tests
# ============================================================================


class TestWriteMethod:
    """Tests for the main write() method."""

    @pytest.mark.asyncio
    async def test_write_insert_success(self, social_writer, mock_uow, sample_insert_write):
        """INSERT should succeed and return LayerWriteResult."""
        result = await social_writer.write([sample_insert_write], mock_uow)

        assert result.layer == LAYER_ST_SOCIAL
        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        assert result.failed_ids == []
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_write_skips_other_layers(self, social_writer, mock_uow):
        """Writer should skip writes for other layers."""
        other_layer_write = StagedWrite.insert(
            layer="st_epi",  # Different layer
            record_id="epi_001",
            data={"episode_id": "epi_001"},
            phase="R2",
        )

        result = await social_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        assert mock_uow.connection.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_write_continues_on_failure(self, social_writer, mock_uow):
        """Writer should continue processing after a failure."""
        # First call fails, second succeeds
        mock_uow.connection.execute.side_effect = [
            Exception("Database error"),
            "INSERT 0 1",
        ]

        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_SOCIAL,
                record_id="rel_001",
                data={
                    "relationship_id": "rel_001",
                    "tenant_id": "t",
                    "space_id": "s",
                    "actor_a_id": "a",
                    "actor_b_id": "b",
                },
                phase="R3",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_SOCIAL,
                record_id="rel_002",
                data={
                    "relationship_id": "rel_002",
                    "tenant_id": "t",
                    "space_id": "s",
                    "actor_a_id": "c",
                    "actor_b_id": "d",
                },
                phase="R3",
            ),
        ]

        result = await social_writer.write(writes, mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "rel_001" in result.failed_ids


# ============================================================================
# Insert Tests
# ============================================================================


class TestInsert:
    """Tests for INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_calls_execute(self, social_writer, mock_uow, sample_insert_write):
        """INSERT should call connection.execute with correct SQL."""
        await social_writer.write([sample_insert_write], mock_uow)

        mock_uow.connection.execute.assert_called_once()
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "INSERT INTO st_social" in sql
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_insert_provides_all_columns(self, social_writer, mock_uow, sample_insert_write):
        """INSERT should provide all required column values."""
        await social_writer.write([sample_insert_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        # Check positional args after SQL
        values = call_args[0][1:]

        assert "rel_001" in values  # relationship_id
        assert "tenant_abc" in values  # tenant_id
        assert "person_alice" in values  # actor_a_id
        assert "person_bob" in values  # actor_b_id
        assert "friend" in values  # relationship_type


# ============================================================================
# Reinforce Action Tests
# ============================================================================


class TestReinforceAction:
    """Tests for REINFORCE action."""

    @pytest.mark.asyncio
    async def test_reinforce_boosts_strength(self, social_writer, mock_uow, sample_reinforce_write):
        """REINFORCE should boost strength and update sentiment."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await social_writer.write([sample_reinforce_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_social" in sql
        # Column renamed from 'strength' to 'relationship_strength' in migration
        assert "relationship_strength = LEAST(relationship_strength *" in sql
        assert "avg_sentiment" in sql
        assert "interaction_count = interaction_count + 1" in sql
        # New UltraBERT-derived fields
        assert "emotional_valence_avg" in sql
        assert "emotional_valence_trend" in sql

    @pytest.mark.asyncio
    async def test_reinforce_version_conflict(
        self, social_writer, mock_uow, sample_reinforce_write
    ):
        """REINFORCE should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await social_writer.write([sample_reinforce_write], mock_uow)

        assert result.writes_failed == 1
        assert "rel_001" in result.failed_ids
        assert "Version conflict" in result.error_message


# ============================================================================
# Extend Action Tests
# ============================================================================


class TestExtendAction:
    """Tests for EXTEND action."""

    @pytest.mark.asyncio
    async def test_extend_adds_interaction_types(
        self, social_writer, mock_uow, sample_extend_write
    ):
        """EXTEND should add interaction types to interaction_types_json."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await social_writer.write([sample_extend_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_social" in sql
        assert "interaction_types_json" in sql
        assert "jsonb_agg" in sql or "jsonb_array_elements" in sql


# ============================================================================
# Decay Action Tests
# ============================================================================


class TestDecayAction:
    """Tests for DECAY action."""

    @pytest.mark.asyncio
    async def test_decay_reduces_strength(self, social_writer, mock_uow, sample_decay_write):
        """DECAY should reduce relationship strength."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        await social_writer.write([sample_decay_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_social" in sql
        assert "strength = strength *" in sql

    @pytest.mark.asyncio
    async def test_decay_uses_default_factor(self, social_writer, mock_uow):
        """DECAY should use DECAY_FACTOR by default."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_SOCIAL,
            record_id="rel_001",
            data={
                "_action": "DECAY",
            },
            phase="R3",
            expected_version=1,
        )

        await social_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        values = call_args[0][1:]

        # Check that DECAY_FACTOR (0.95) is in the values
        assert 0.95 in values

    @pytest.mark.asyncio
    async def test_decay_custom_factor(self, social_writer, mock_uow):
        """DECAY should allow custom decay_factor."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_SOCIAL,
            record_id="rel_001",
            data={
                "_action": "DECAY",
                "decay_factor": 0.8,  # Custom factor
            },
            phase="R3",
            expected_version=1,
        )

        await social_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        values = call_args[0][1:]

        # Check that custom factor 0.8 is in the values
        assert 0.8 in values


# ============================================================================
# Archive Tests
# ============================================================================


class TestArchive:
    """Tests for ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_sets_status(self, social_writer, mock_uow, sample_archive_write):
        """ARCHIVE should set archival_status and archived_at."""
        await social_writer.write([sample_archive_write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_social" in sql
        assert "archival_status = 'ARCHIVED'" in sql
        assert "archived_at" in sql

    @pytest.mark.asyncio
    async def test_archive_default_reason(self, social_writer, mock_uow):
        """ARCHIVE without reason should use 'inactive' as default."""
        write = StagedWrite.archive(
            layer=LAYER_ST_SOCIAL,
            record_id="rel_001",
            reason="",  # Empty reason
            phase="R6",
        )

        await social_writer.write([write], mock_uow)

        # The SQL should still work with empty reason
        mock_uow.connection.execute.assert_called_once()


# ============================================================================
# Tombstone Tests
# ============================================================================


class TestTombstone:
    """Tests for TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_sets_status(self, social_writer, mock_uow):
        """TOMBSTONE should set archival_status to TOMBSTONE."""
        write = StagedWrite.tombstone(
            layer=LAYER_ST_SOCIAL,
            record_id="rel_001",
            phase="R6",
        )

        await social_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "archival_status = 'TOMBSTONE'" in sql


# ============================================================================
# Generic Update Tests
# ============================================================================


class TestGenericUpdate:
    """Tests for generic UPDATE (no action)."""

    @pytest.mark.asyncio
    async def test_generic_update_with_optimistic_lock(self, social_writer, mock_uow):
        """Generic UPDATE should use optimistic locking."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_SOCIAL,
            record_id="rel_001",
            data={
                "relationship_type": "colleague",
            },
            phase="R3",
            expected_version=1,
        )

        await social_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "UPDATE st_social" in sql
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
