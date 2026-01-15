"""
Test OutboxWriter — Issue 5.2.2

Tests for OutboxWriter and transactional outbox pattern.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.truth_writer.outbox import (
    OutboxStagingResult,
    OutboxWriteConfig,
    OutboxWriter,
    create_outbox_writer,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    StagedOutboxEvent,
    StagedWrite,
    WriteOperation,
)
from k0.storage.outbox import OutboxEntry

# =============================================================================
# FIXTURES
# =============================================================================


def create_test_write(
    layer: str = LAYER_ST_EPI,
    record_id: str = "rec_1",
    phase: str = "R1",
) -> StagedWrite:
    """Create test StagedWrite."""
    return StagedWrite(
        write_id=f"write_{record_id}",
        layer=layer,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data={"id": record_id, "value": 42},
        idempotency_key=f"{phase}:{layer}:{record_id}",
        source_phase=phase,
    )


def create_test_event(
    topic: str = "p03.event.test",
    phase: str = "R8",
) -> StagedOutboxEvent:
    """Create test StagedOutboxEvent."""
    return StagedOutboxEvent(
        event_id="evt_123",
        topic=topic,
        payload={"type": "test", "data": 123},
        source_phase=phase,
        idempotency_key=f"{phase}:event:evt_123",  # Issue 8.1.13
        priority=50,
    )


@pytest.fixture
def mock_uow() -> MagicMock:
    """Create mock UnitOfWork with stage_outbox method."""
    uow = MagicMock()
    uow.staged_entries = []  # List[OutboxEntry]

    def capture_outbox(entry: OutboxEntry) -> None:
        uow.staged_entries.append(entry)

    uow.stage_outbox = MagicMock(side_effect=capture_outbox)
    return uow


# =============================================================================
# 1. CONFIGURATION TESTS
# =============================================================================


class TestOutboxWriteConfig:
    """Test OutboxWriteConfig dataclass."""

    def test_default_values(self) -> None:
        """Default config values are correct."""
        config = OutboxWriteConfig()

        assert config.driver_prefix == "p03"
        assert config.max_batch_size == 100
        assert config.retry_backoff_base_ms == 1000
        assert config.enable_fingerprint is True

    def test_custom_values(self) -> None:
        """Custom config values are applied."""
        config = OutboxWriteConfig(
            driver_prefix="custom",
            max_batch_size=50,
            retry_backoff_base_ms=500,
            enable_fingerprint=False,
        )

        assert config.driver_prefix == "custom"
        assert config.max_batch_size == 50
        assert config.retry_backoff_base_ms == 500
        assert config.enable_fingerprint is False


# =============================================================================
# 2. CONSTRUCTION TESTS
# =============================================================================


class TestOutboxWriterConstruction:
    """Test OutboxWriter construction."""

    def test_default_construction(self) -> None:
        """OutboxWriter can be created with defaults."""
        writer = OutboxWriter()

        assert writer.config.max_batch_size == 100
        assert writer.max_batch_size == 100

    def test_custom_config(self) -> None:
        """OutboxWriter accepts custom config."""
        config = OutboxWriteConfig(max_batch_size=25)
        writer = OutboxWriter(config=config)

        assert writer.max_batch_size == 25

    def test_factory_function(self) -> None:
        """create_outbox_writer factory works."""
        writer = create_outbox_writer()

        assert isinstance(writer, OutboxWriter)


# =============================================================================
# 3. STAGE_WRITE TESTS
# =============================================================================


class TestStageWrite:
    """Test stage_write method."""

    def test_stages_write_entry(self, mock_uow: MagicMock) -> None:
        """stage_write creates and stages OutboxEntry."""
        writer = OutboxWriter()
        write = create_test_write()

        writer.stage_write(
            uow=mock_uow,
            write=write,
            tenant_id="t1",
            space_id="s1",
        )

        mock_uow.stage_outbox.assert_called_once()
        entry = mock_uow.staged_entries[0]
        assert entry.tenant_id == "t1"
        assert entry.space_id == "s1"
        assert entry.driver == LAYER_ST_EPI

    def test_stages_correct_operation(self, mock_uow: MagicMock) -> None:
        """stage_write captures operation type."""
        writer = OutboxWriter()
        write = create_test_write()

        writer.stage_write(mock_uow, write, "t1", "s1")

        entry = mock_uow.staged_entries[0]
        assert entry.op_kind == "INSERT"

    def test_stages_payload_as_json(self, mock_uow: MagicMock) -> None:
        """stage_write serializes record_data as JSON bytes."""
        writer = OutboxWriter()
        write = create_test_write()

        writer.stage_write(mock_uow, write, "t1", "s1")

        entry = mock_uow.staged_entries[0]
        payload = json.loads(entry.payload.decode("utf-8"))
        assert payload["id"] == "rec_1"
        assert payload["value"] == 42

    def test_uses_idempotency_key_as_fingerprint(self, mock_uow: MagicMock) -> None:
        """stage_write uses write's idempotency_key as fingerprint."""
        writer = OutboxWriter()
        write = create_test_write()

        fingerprint = writer.stage_write(mock_uow, write, "t1", "s1")

        assert fingerprint == "R1:st_epi:rec_1"
        entry = mock_uow.staged_entries[0]
        assert entry.fingerprint == "R1:st_epi:rec_1"

    def test_generates_fingerprint_with_cycle(self, mock_uow: MagicMock) -> None:
        """stage_write generates fingerprint from cycle_ulid if no key."""
        writer = OutboxWriter()
        write = StagedWrite(
            write_id="w1",
            layer=LAYER_ST_EPI,
            operation=WriteOperation.INSERT,
            record_id="rec_1",
            record_data={},
            idempotency_key="",  # Empty key
            source_phase="R1",
        )

        fingerprint = writer.stage_write(mock_uow, write, "t1", "s1", cycle_ulid="01ABC")

        assert fingerprint == "p03:write:01ABC:st_epi:rec_1"

    def test_returns_fingerprint(self, mock_uow: MagicMock) -> None:
        """stage_write returns the fingerprint."""
        writer = OutboxWriter()
        write = create_test_write()

        result = writer.stage_write(mock_uow, write, "t1", "s1")

        assert result == "R1:st_epi:rec_1"


# =============================================================================
# 4. STAGE_BATCH TESTS
# =============================================================================


class TestStageBatch:
    """Test stage_batch method."""

    def test_stages_multiple_writes(self, mock_uow: MagicMock) -> None:
        """stage_batch stages all writes."""
        writer = OutboxWriter()
        writes = [
            create_test_write(record_id="r1"),
            create_test_write(record_id="r2"),
            create_test_write(record_id="r3"),
        ]

        result = writer.stage_batch(mock_uow, writes, "t1", "s1")

        assert result.writes_staged == 3
        assert len(mock_uow.staged_entries) == 3

    def test_respects_max_batch_size(self, mock_uow: MagicMock) -> None:
        """stage_batch respects max_batch_size limit."""
        config = OutboxWriteConfig(max_batch_size=2)
        writer = OutboxWriter(config=config)
        writes = [
            create_test_write(record_id="r1"),
            create_test_write(record_id="r2"),
            create_test_write(record_id="r3"),
        ]

        result = writer.stage_batch(mock_uow, writes, "t1", "s1")

        assert result.writes_staged == 2
        assert len(mock_uow.staged_entries) == 2

    def test_returns_staging_result(self, mock_uow: MagicMock) -> None:
        """stage_batch returns OutboxStagingResult."""
        writer = OutboxWriter()
        writes = [create_test_write(record_id="r1")]

        result = writer.stage_batch(mock_uow, writes, "t1", "s1")

        assert isinstance(result, OutboxStagingResult)
        assert result.writes_staged == 1
        assert len(result.fingerprints) == 1

    def test_empty_batch(self, mock_uow: MagicMock) -> None:
        """stage_batch handles empty batch."""
        writer = OutboxWriter()

        result = writer.stage_batch(mock_uow, [], "t1", "s1")

        assert result.writes_staged == 0
        assert result.fingerprints == []


# =============================================================================
# 5. STAGE_EVENT TESTS
# =============================================================================


class TestStageEvent:
    """Test stage_event method."""

    def test_stages_event_entry(self, mock_uow: MagicMock) -> None:
        """stage_event creates outbox entry for event."""
        writer = OutboxWriter()
        event = create_test_event()

        writer.stage_event(mock_uow, event, "t1", "s1")

        mock_uow.stage_outbox.assert_called_once()
        entry = mock_uow.staged_entries[0]
        assert entry.driver == "bus"
        assert entry.op_kind == "EMIT"

    def test_event_payload_includes_topic(self, mock_uow: MagicMock) -> None:
        """stage_event includes topic in payload."""
        writer = OutboxWriter()
        event = create_test_event(topic="p03.cycle.completed")

        writer.stage_event(mock_uow, event, "t1", "s1")

        entry = mock_uow.staged_entries[0]
        payload = json.loads(entry.payload.decode("utf-8"))
        assert payload["topic"] == "p03.cycle.completed"
        assert payload["priority"] == 50

    def test_event_fingerprint(self, mock_uow: MagicMock) -> None:
        """stage_event generates event fingerprint."""
        writer = OutboxWriter()
        event = create_test_event()

        fingerprint = writer.stage_event(mock_uow, event, "t1", "s1")

        assert fingerprint == "p03:event:evt_123"


# =============================================================================
# 6. STAGE_EVENTS_BATCH TESTS
# =============================================================================


class TestStageEventsBatch:
    """Test stage_events_batch method."""

    def test_stages_multiple_events(self, mock_uow: MagicMock) -> None:
        """stage_events_batch stages all events."""
        writer = OutboxWriter()
        events = [
            create_test_event(topic="t1"),
            create_test_event(topic="t2"),
        ]

        result = writer.stage_events_batch(mock_uow, events, "t1", "s1")

        assert result.events_staged == 2
        assert len(mock_uow.staged_entries) == 2

    def test_returns_staging_result(self, mock_uow: MagicMock) -> None:
        """stage_events_batch returns OutboxStagingResult."""
        writer = OutboxWriter()
        events = [create_test_event()]

        result = writer.stage_events_batch(mock_uow, events, "t1", "s1")

        assert isinstance(result, OutboxStagingResult)
        assert result.events_staged == 1


# =============================================================================
# 7. OUTBOX STAGING RESULT TESTS
# =============================================================================


class TestOutboxStagingResult:
    """Test OutboxStagingResult dataclass."""

    def test_total_staged_property(self) -> None:
        """total_staged combines writes and events."""
        result = OutboxStagingResult(
            writes_staged=5,
            events_staged=3,
        )

        assert result.total_staged == 8

    def test_default_values(self) -> None:
        """Default values are correct."""
        result = OutboxStagingResult()

        assert result.writes_staged == 0
        assert result.events_staged == 0
        assert result.fingerprints == []
