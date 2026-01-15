"""Tests for P03 DLQ Store (Issue 6.2.3).

Tests P03-specific DLQ record format and store operations.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock

import pytest

from k0.pipelines.p03.ops.dlq_store import P03DLQRecord, P03DLQStore


class TestP03DLQRecord:
    """Tests for P03DLQRecord dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating record with minimal fields."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Connection failed",
        )
        assert record.cycle_id == "cycle-456"
        assert record.phase == "R0"
        assert record.error_type == "TRANSIENT"
        assert record.error_message == "Connection failed"
        assert record.dlq_id is not None  # Auto-generated
        assert record.status == "PENDING"
        assert record.attempt_count == 1
        assert record.max_attempts == 3

    def test_create_full(self) -> None:
        """Test creating record with all fields."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R6",
            error_type="VALIDATION",
            error_message="Invalid manifest",
            event_id="evt-789",
            entity_id="entity-def",
            tenant_id="tenant-1",
            space_id="space-1",
            error_code="ValueError",
            stack_trace="Traceback...",
            payload={"key": "value"},
            attempt_count=2,
            max_attempts=5,
        )
        assert record.event_id == "evt-789"
        assert record.entity_id == "entity-def"
        assert record.tenant_id == "tenant-1"
        assert record.space_id == "space-1"
        assert record.error_code == "ValueError"
        assert record.stack_trace == "Traceback..."
        assert record.payload == {"key": "value"}
        assert record.attempt_count == 2
        assert record.max_attempts == 5

    def test_default_status_is_pending(self) -> None:
        """Test default status is PENDING."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Error",
        )
        assert record.status == "PENDING"

    def test_resolved_at_is_none_by_default(self) -> None:
        """Test resolved_at is None by default."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Error",
        )
        assert record.resolved_at is None


class TestP03DLQRecordConversion:
    """Tests for P03DLQRecord conversion methods."""

    def test_to_dead_letter(self) -> None:
        """Test conversion to DeadLetter format."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Connection failed",
            tenant_id="tenant-1",
            space_id="space-1",
            attempt_count=3,
        )
        dead_letter = record.to_dead_letter()

        assert dead_letter.driver == "p03_consolidation"
        assert dead_letter.op_kind == "R0"
        assert dead_letter.tenant_id == "tenant-1"
        assert dead_letter.space_id == "space-1"
        assert dead_letter.retries == 3

    def test_to_dead_letter_uses_phase_as_op_kind(self) -> None:
        """Test phase is used as op_kind."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R7",
            error_type="TRANSIENT",
            error_message="Error",
        )
        dead_letter = record.to_dead_letter()

        assert dead_letter.op_kind == "R7"

    def test_to_dead_letter_payload_contains_dlq_id(self) -> None:
        """Test payload contains dlq_id."""
        record = P03DLQRecord(
            cycle_id="cycle-456",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Error",
        )
        dead_letter = record.to_dead_letter()

        payload = json.loads(dead_letter.payload.decode("utf-8"))
        assert "dlq_id" in payload
        assert payload["dlq_id"] == record.dlq_id


class TestP03DLQStore:
    """Tests for P03DLQStore class."""

    @pytest.fixture
    def mock_dlq(self) -> Mock:
        """Create mock underlying DLQ."""
        mock = Mock()
        mock.record = AsyncMock(return_value=1)
        mock.list_pending = AsyncMock(return_value=[])
        mock.get = AsyncMock(return_value=None)
        mock.resolve = AsyncMock()
        return mock

    @pytest.fixture
    def store(self, mock_dlq: Mock) -> P03DLQStore:
        """Create store with mocked DLQ."""
        return P03DLQStore(dlq=mock_dlq)


class TestRecordPhaseError(TestP03DLQStore):
    """Tests for recording phase errors."""

    @pytest.mark.asyncio
    async def test_record_phase_error_creates_dlq_entry(
        self, store: P03DLQStore, mock_dlq: Mock
    ) -> None:
        """Test record_phase_error creates DLQ entry."""
        record = P03DLQRecord(
            cycle_id="cycle-123",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Connection refused",
            attempt_count=3,
        )
        result = await store.record_phase_error(record)

        assert result == 1
        mock_dlq.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_phase_error_sets_timestamps(
        self, store: P03DLQStore, mock_dlq: Mock
    ) -> None:
        """Test record_phase_error sets timestamps."""
        record = P03DLQRecord(
            cycle_id="cycle-123",
            phase="R0",
            error_type="TRANSIENT",
            error_message="Error",
        )
        await store.record_phase_error(record)

        # Record should have timestamps set
        assert record.first_failure_ts > 0
        assert record.last_failure_ts > 0


class TestRecordEventError(TestP03DLQStore):
    """Tests for recording event errors."""

    @pytest.mark.asyncio
    async def test_record_event_error_creates_entry(
        self, store: P03DLQStore, mock_dlq: Mock
    ) -> None:
        """Test record_event_error creates DLQ entry."""
        record = P03DLQRecord(
            cycle_id="cycle-123",
            phase="R1",
            error_type="VALIDATION",
            error_message="Invalid event",
            event_id="evt-456",
        )
        result = await store.record_event_error(record)

        assert result == 1
        mock_dlq.record.assert_called_once()


class TestRecordBatchError(TestP03DLQStore):
    """Tests for recording batch errors."""

    @pytest.mark.asyncio
    async def test_record_batch_error_clears_event_id(
        self, store: P03DLQStore, mock_dlq: Mock
    ) -> None:
        """Test record_batch_error clears event_id."""
        record = P03DLQRecord(
            cycle_id="cycle-123",
            phase="R6",
            error_type="LOGIC",
            error_message="Batch processing failed",
            event_id="evt-should-be-cleared",
        )
        await store.record_batch_error(record)

        # event_id should be cleared for batch errors
        assert record.event_id is None
        mock_dlq.record.assert_called_once()


class TestListPending(TestP03DLQStore):
    """Tests for listing pending records."""

    @pytest.mark.asyncio
    async def test_list_pending_empty(self, store: P03DLQStore, mock_dlq: Mock) -> None:
        """Test listing pending when empty."""
        mock_dlq.list_pending.return_value = []
        records = await store.list_pending()

        assert records == []
        mock_dlq.list_pending.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_pending_by_phase(self, store: P03DLQStore, mock_dlq: Mock) -> None:
        """Test listing pending by phase."""
        mock_dlq.list_pending.return_value = []
        records = await store.list_pending_by_phase("R0")

        assert records == []
        mock_dlq.list_pending.assert_called()

    @pytest.mark.asyncio
    async def test_list_pending_by_cycle(self, store: P03DLQStore, mock_dlq: Mock) -> None:
        """Test listing pending by cycle."""
        mock_dlq.list_pending.return_value = []
        records = await store.list_pending_by_cycle("cycle-123")

        assert records == []
        mock_dlq.list_pending.assert_called()


class TestDLQDriverConstant(TestP03DLQStore):
    """Tests for DLQ driver constant."""

    def test_driver_constant_value(self, store: P03DLQStore) -> None:
        """Test DRIVER constant value."""
        assert P03DLQStore.DRIVER == "p03_consolidation"

    @pytest.mark.asyncio
    async def test_record_uses_p03_driver(self, store: P03DLQStore, mock_dlq: Mock) -> None:
        """Test that P03 driver name is used in records."""
        record = P03DLQRecord(
            cycle_id="cycle-123",
            phase="R0",
            error_type="TRANSIENT",
            error_message="test",
        )
        await store.record_phase_error(record)

        # Verify the record was called
        mock_dlq.record.assert_called_once()
        # Get the DeadLetter that was passed
        call_args = mock_dlq.record.call_args
        dead_letter = call_args[0][0] if call_args[0] else call_args[1].get("letter")
        if dead_letter:
            assert dead_letter.driver == "p03_consolidation"

    @pytest.mark.asyncio
    async def test_phase_used_as_op_kind(self, store: P03DLQStore, mock_dlq: Mock) -> None:
        """Test that phase is used as op_kind."""
        record = P03DLQRecord(
            cycle_id="cycle-123",
            phase="R7",
            error_type="TRANSIENT",
            error_message="test",
        )
        await store.record_phase_error(record)

        mock_dlq.record.assert_called_once()
        call_args = mock_dlq.record.call_args
        dead_letter = call_args[0][0] if call_args[0] else call_args[1].get("letter")
        if dead_letter:
            assert dead_letter.op_kind == "R7"
