"""
Tests for ProspectiveLayerWriter — Issue 5.2.7

Tests for st_prospective layer write operations including intention/goal tracking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.prospective import (
    IntentionAction,
    IntentionWriteData,
    ProspectiveLayerWriter,
    create_prospective_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_PROSPECTIVE, StagedWrite

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
def prospective_writer():
    """Create a ProspectiveLayerWriter."""
    return ProspectiveLayerWriter()


@pytest.fixture
def sample_insert_write():
    """Create a sample INSERT StagedWrite for st_prospective."""
    return StagedWrite.insert(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        data={
            "intention_id": "intent_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "intention_type": "goal",
            "description": "Complete project by Friday",
            "trigger_time_ms": 1700000000000,
            "trigger_context_json": '{"when": "friday"}',
            "goal_inference_json": '{"source": "R5"}',
            "confidence": 0.8,
            "status": "pending",
            "source_episodes_json": '["ep_001", "ep_002"]',
        },
        phase="R5",
    )


@pytest.fixture
def sample_reminder_insert():
    """Create a sample INSERT StagedWrite for reminder intention."""
    return StagedWrite.insert(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_002",
        data={
            "intention_id": "intent_002",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "intention_type": "reminder",
            "description": "Call mom on Sunday",
            "trigger_time_ms": 1700500000000,
            "trigger_context_json": '{"when": "sunday", "priority": "high"}',
            "confidence": 0.9,
            "status": "pending",
        },
        phase="R5",
    )


@pytest.fixture
def sample_extend_write():
    """Create a sample EXTEND UPDATE StagedWrite for st_prospective."""
    return StagedWrite.update(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        data={
            "_action": IntentionAction.EXTEND,
            "goal_inference_json": '{"source": "R5", "refined": true}',
            "new_triggers_json": '{"additional": "context"}',
            "confidence": 0.85,
            "new_episodes_json": '["ep_003"]',
        },
        phase="R5",
        expected_version=1,
    )


@pytest.fixture
def sample_complete_write():
    """Create a sample COMPLETE UPDATE StagedWrite for st_prospective."""
    return StagedWrite.update(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        data={
            "_action": IntentionAction.COMPLETE,
        },
        phase="R5",
        expected_version=1,
    )


@pytest.fixture
def sample_counterfactual_write():
    """Create a sample COUNTERFACTUAL UPDATE StagedWrite for st_prospective."""
    return StagedWrite.update(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        data={
            "_action": IntentionAction.COUNTERFACTUAL,
            "counterfactual_json": '{"what_if": "scenario_a", "outcome": 0.7}',
        },
        phase="R5",
        expected_version=1,
    )


@pytest.fixture
def sample_archive_expired():
    """Create a sample ARCHIVE StagedWrite for expired intention."""
    return StagedWrite.archive(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        reason="expired",
        phase="R6",
    )


@pytest.fixture
def sample_archive_cancelled():
    """Create a sample ARCHIVE StagedWrite for cancelled intention."""
    return StagedWrite.archive(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        reason="cancelled",
        phase="R6",
    )


@pytest.fixture
def sample_tombstone_write():
    """Create a sample TOMBSTONE StagedWrite for st_prospective."""
    return StagedWrite.tombstone(
        layer=LAYER_ST_PROSPECTIVE,
        record_id="intent_001",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_prospective_writer_returns_instance(self):
        """Factory should return a ProspectiveLayerWriter instance."""
        writer = create_prospective_writer()
        assert isinstance(writer, ProspectiveLayerWriter)

    def test_layer_property(self, prospective_writer):
        """Layer property should return LAYER_ST_PROSPECTIVE."""
        assert prospective_writer.layer == LAYER_ST_PROSPECTIVE


# ============================================================================
# IntentionWriteData Tests
# ============================================================================


class TestIntentionWriteData:
    """Tests for IntentionWriteData dataclass."""

    def test_create_with_all_fields(self):
        """Should create with all fields."""
        data = IntentionWriteData(
            intention_id="intent_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            intention_type="goal",
            description="Complete project",
            trigger_time_ms=1700000000000,
            trigger_context_json='{"when": "friday"}',
            goal_inference_json='{"source": "R5"}',
            confidence=0.8,
            status="pending",
            source_episodes_json='["ep_001"]',
            counterfactual_json='{"what_if": "scenario"}',
        )
        assert data.intention_id == "intent_001"
        assert data.intention_type == "goal"
        assert data.trigger_time_ms == 1700000000000
        assert data.counterfactual_json is not None

    def test_create_with_defaults(self):
        """Should create with default values."""
        data = IntentionWriteData(
            intention_id="intent_002",
            tenant_id="tenant_abc",
            space_id="space_xyz",
        )
        assert data.intention_type == "intention"
        assert data.description == ""
        assert data.trigger_time_ms is None
        assert data.trigger_context_json == "{}"
        assert data.goal_inference_json == "{}"
        assert data.confidence == 0.5
        assert data.status == "pending"
        assert data.source_episodes_json == "[]"
        assert data.counterfactual_json is None


# ============================================================================
# IntentionAction Tests
# ============================================================================


class TestIntentionAction:
    """Tests for IntentionAction enum."""

    def test_extend_action(self):
        """EXTEND action should have correct value."""
        assert IntentionAction.EXTEND == "EXTEND"
        assert IntentionAction.EXTEND.value == "EXTEND"

    def test_complete_action(self):
        """COMPLETE action should have correct value."""
        assert IntentionAction.COMPLETE == "COMPLETE"
        assert IntentionAction.COMPLETE.value == "COMPLETE"

    def test_counterfactual_action(self):
        """COUNTERFACTUAL action should have correct value."""
        assert IntentionAction.COUNTERFACTUAL == "COUNTERFACTUAL"
        assert IntentionAction.COUNTERFACTUAL.value == "COUNTERFACTUAL"


# ============================================================================
# INSERT Tests
# ============================================================================


class TestInsert:
    """Tests for INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_goal(self, prospective_writer, mock_uow, sample_insert_write):
        """Should insert new goal intention."""
        result = await prospective_writer.write([sample_insert_write], mock_uow)

        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        mock_uow.connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_reminder(self, prospective_writer, mock_uow, sample_reminder_insert):
        """Should insert new reminder intention."""
        result = await prospective_writer.write([sample_reminder_insert], mock_uow)

        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0

    @pytest.mark.asyncio
    async def test_insert_with_minimal_fields(self, prospective_writer, mock_uow):
        """Should insert with minimal required fields."""
        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id="intent_minimal",
            data={
                "intention_id": "intent_minimal",
                "tenant_id": "tenant",
                "space_id": "space",
            },
            phase="R5",
        )

        result = await prospective_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "ON CONFLICT (intention_id) DO NOTHING" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_insert_with_counterfactual(self, prospective_writer, mock_uow):
        """Should insert intention with counterfactual data."""
        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id="intent_cf",
            data={
                "intention_id": "intent_cf",
                "tenant_id": "tenant",
                "space_id": "space",
                "counterfactual_json": '{"scenario": "what_if"}',
            },
            phase="R5",
        )

        result = await prospective_writer.write([write], mock_uow)
        assert result.writes_succeeded == 1


# ============================================================================
# UPDATE Tests
# ============================================================================


class TestUpdate:
    """Tests for UPDATE operation."""

    @pytest.mark.asyncio
    async def test_update_extend(self, prospective_writer, mock_uow, sample_extend_write):
        """Should update intention with EXTEND action."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await prospective_writer.write([sample_extend_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "goal_inference_json" in call_args[0][0]
        assert "trigger_context_json" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_complete(self, prospective_writer, mock_uow, sample_complete_write):
        """Should mark intention as completed."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await prospective_writer.write([sample_complete_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "status = 'completed'" in call_args[0][0]
        assert "completed_at" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_counterfactual(
        self, prospective_writer, mock_uow, sample_counterfactual_write
    ):
        """Should store counterfactual from R5 CPN."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await prospective_writer.write([sample_counterfactual_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "counterfactual_json" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_version_conflict(self, prospective_writer, mock_uow, sample_extend_write):
        """Should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await prospective_writer.write([sample_extend_write], mock_uow)

        assert result.writes_succeeded == 0
        assert result.writes_failed == 1
        assert "intent_001" in result.failed_ids

    @pytest.mark.asyncio
    async def test_update_default_action(self, prospective_writer, mock_uow):
        """Should default to EXTEND for unknown action."""
        write = StagedWrite.update(
            layer=LAYER_ST_PROSPECTIVE,
            record_id="intent_001",
            data={
                "_action": "UNKNOWN_ACTION",
                "confidence": 0.9,
            },
            phase="R5",
            expected_version=1,
        )
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await prospective_writer.write([write], mock_uow)

        # Should default to EXTEND and succeed
        assert result.writes_succeeded == 1


# ============================================================================
# ARCHIVE Tests
# ============================================================================


class TestArchive:
    """Tests for ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_expired(self, prospective_writer, mock_uow, sample_archive_expired):
        """Should archive with expired status."""
        result = await prospective_writer.write([sample_archive_expired], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "archival_status = 'ARCHIVED'" in sql
        assert "status = $1" in sql

    @pytest.mark.asyncio
    async def test_archive_cancelled(self, prospective_writer, mock_uow, sample_archive_cancelled):
        """Should archive with cancelled status."""
        result = await prospective_writer.write([sample_archive_cancelled], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        # Cancelled maps to a status update
        assert "archived_reason" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_archive_custom_reason(self, prospective_writer, mock_uow):
        """Should archive with custom reason (no status update)."""
        write = StagedWrite.archive(
            layer=LAYER_ST_PROSPECTIVE,
            record_id="intent_001",
            reason="user_dismissed",
            phase="R6",
        )

        result = await prospective_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1
        # Custom reason should not map to a status change

    @pytest.mark.asyncio
    async def test_archive_idempotent(self, prospective_writer, mock_uow):
        """Should be idempotent (no error on already archived)."""
        write = StagedWrite.archive(
            layer=LAYER_ST_PROSPECTIVE,
            record_id="intent_001",
            reason="expired",
            phase="R6",
        )

        # First archive
        await prospective_writer.write([write], mock_uow)
        # Second archive (already archived)
        result = await prospective_writer.write([write], mock_uow)

        # Should still succeed (SQL has WHERE clause for not-already-archived)
        assert result.writes_succeeded == 1


# ============================================================================
# TOMBSTONE Tests
# ============================================================================


class TestTombstone:
    """Tests for TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_clears_data(
        self, prospective_writer, mock_uow, sample_tombstone_write
    ):
        """Should clear all sensitive data."""
        result = await prospective_writer.write([sample_tombstone_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "description = ''" in sql
        assert "trigger_time = NULL" in sql
        assert "trigger_context_json = '{}'" in sql
        assert "goal_inference_json = '{}'" in sql
        assert "source_episodes_json = '[]'" in sql
        assert "counterfactual_json = NULL" in sql
        assert "archival_status = 'TOMBSTONE'" in sql
        assert "gdpr_deletion" in sql


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_continues_on_failure(self, prospective_writer, mock_uow):
        """Should continue processing after failure."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id="intent_001",
                data={
                    "intention_id": "intent_001",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R5",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id="intent_002",
                data={
                    "intention_id": "intent_002",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R5",
            ),
        ]

        # First call succeeds, second fails
        mock_uow.connection.execute.side_effect = [
            "INSERT 0 1",
            Exception("DB error"),
        ]

        result = await prospective_writer.write(writes, mock_uow)

        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "intent_002" in result.failed_ids

    @pytest.mark.asyncio
    async def test_ignores_other_layers(self, prospective_writer, mock_uow):
        """Should ignore writes for other layers."""
        from k0.pipelines.p03.staged_writes import LAYER_ST_EPI

        other_layer_write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="ep_001",
            data={"episode_id": "ep_001", "tenant_id": "t", "space_id": "s"},
            phase="R7",
        )

        result = await prospective_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        mock_uow.connection.execute.assert_not_called()


# ============================================================================
# Multiple Writes Tests
# ============================================================================


class TestMultipleWrites:
    """Tests for processing multiple writes."""

    @pytest.mark.asyncio
    async def test_multiple_inserts(self, prospective_writer, mock_uow):
        """Should process multiple INSERTs."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id=f"intent_{i:03d}",
                data={
                    "intention_id": f"intent_{i:03d}",
                    "tenant_id": "tenant",
                    "space_id": "space",
                    "intention_type": "goal",
                },
                phase="R5",
            )
            for i in range(5)
        ]

        result = await prospective_writer.write(writes, mock_uow)

        assert result.writes_attempted == 5
        assert result.writes_succeeded == 5
        assert mock_uow.connection.execute.call_count == 5

    @pytest.mark.asyncio
    async def test_mixed_operations(self, prospective_writer, mock_uow):
        """Should handle mixed INSERT/UPDATE/ARCHIVE operations."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id="intent_001",
                data={
                    "intention_id": "intent_001",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R5",
            ),
            StagedWrite.update(
                layer=LAYER_ST_PROSPECTIVE,
                record_id="intent_002",
                data={
                    "_action": IntentionAction.COMPLETE,
                },
                phase="R5",
                expected_version=1,
            ),
            StagedWrite.archive(
                layer=LAYER_ST_PROSPECTIVE,
                record_id="intent_003",
                reason="expired",
                phase="R6",
            ),
        ]
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await prospective_writer.write(writes, mock_uow)

        assert result.writes_attempted == 3
        assert result.writes_succeeded == 3


# ============================================================================
# Status Lifecycle Tests
# ============================================================================


class TestStatusLifecycle:
    """Tests for intention status lifecycle."""

    @pytest.mark.asyncio
    async def test_pending_to_completed(self, prospective_writer, mock_uow, sample_complete_write):
        """Should transition from pending to completed."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await prospective_writer.write([sample_complete_write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "status = 'completed'" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_pending_to_expired(self, prospective_writer, mock_uow, sample_archive_expired):
        """Should transition from pending to expired via archive."""
        result = await prospective_writer.write([sample_archive_expired], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        # Check that status is updated via positional arg
        assert "expired" in call_args[0]

    @pytest.mark.asyncio
    async def test_pending_to_cancelled(
        self, prospective_writer, mock_uow, sample_archive_cancelled
    ):
        """Should transition from pending to cancelled via archive."""
        result = await prospective_writer.write([sample_archive_cancelled], mock_uow)

        assert result.writes_succeeded == 1
