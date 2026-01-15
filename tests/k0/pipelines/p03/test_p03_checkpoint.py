"""
P03 Checkpoint Contract Tests.

Issue 1.2.5: Checkpoint + resume contract tests

Test Categories:
1. P03Checkpoint Creation - Factory methods and defaults
2. P03Checkpoint Serialization - to_dict/from_dict roundtrip
3. P03Checkpoint Properties - is_terminal, is_resumable, resume_phase
4. CheckpointStore Protocol - InMemoryCheckpointStore tests
5. P03Offset Integration - Offset creation from checkpoint
6. Checkpoint Errors - Error classes
"""

from __future__ import annotations

import json
import time

import pytest

from k0.pipelines.p03 import (
    P03_CHECKPOINT_TOPIC,
    P03_SOURCE_TOPIC,
    P03_SUBSCRIBER_ID,
    CheckpointError,
    CheckpointLoadError,
    CheckpointNotFoundError,
    CheckpointSaveError,
    CheckpointStoreProtocol,
    InMemoryCheckpointStore,
    P03Checkpoint,
    P03Offset,
    P03PhaseId,
    P03PhaseStatus,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_checkpoint() -> P03Checkpoint:
    """Create a sample checkpoint for testing."""
    return P03Checkpoint.create(
        cycle_id="01HXY2ABC123DEF456GHI789",
        batch_id="batch-12345",
        space_id="space-1",
        tenant_id="tenant-1",
        phase_id=P03PhaseId.R3_PRUNE,
        phase_status=P03PhaseStatus.DONE,
        envelope_summary={"events_processed": 10, "staged_writes_count": 5},
        last_wal_pos=1000,
        last_event_id="event-999",
        event_ids=["event-1", "event-2", "event-3"],
        errors=[],
        metadata={"test": True},
    )


@pytest.fixture
def in_memory_store() -> InMemoryCheckpointStore:
    """Create an in-memory checkpoint store."""
    return InMemoryCheckpointStore()


# =============================================================================
# 1. P03CHECKPOINT CREATION TESTS
# =============================================================================


class TestCheckpointCreation:
    """Test P03Checkpoint creation and factory methods."""

    def test_create_minimal(self) -> None:
        """Create checkpoint with minimal required fields."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R0_INIT,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.cycle_id == "cycle-1"
        assert checkpoint.batch_id == "batch-1"
        assert checkpoint.space_id == "space-1"
        assert checkpoint.tenant_id == "tenant-1"
        assert checkpoint.phase_id == P03PhaseId.R0_INIT
        assert checkpoint.phase_status == P03PhaseStatus.DONE
        assert checkpoint.checkpoint_id is not None
        assert checkpoint.created_at_ms > 0

    def test_create_with_all_fields(self, sample_checkpoint: P03Checkpoint) -> None:
        """Create checkpoint with all optional fields."""
        assert sample_checkpoint.envelope_summary == {
            "events_processed": 10,
            "staged_writes_count": 5,
        }
        assert sample_checkpoint.last_wal_pos == 1000
        assert sample_checkpoint.last_event_id == "event-999"
        assert sample_checkpoint.event_ids == ["event-1", "event-2", "event-3"]
        assert sample_checkpoint.errors == []
        assert sample_checkpoint.metadata == {"test": True}

    def test_checkpoint_id_is_ulid(self) -> None:
        """Checkpoint ID should be a valid ULID."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R0_INIT,
            phase_status=P03PhaseStatus.DONE,
        )

        # ULID is 26 characters, alphanumeric
        assert len(checkpoint.checkpoint_id) == 26
        assert checkpoint.checkpoint_id.isalnum()

    def test_created_at_ms_is_current(self) -> None:
        """created_at_ms should be close to current time."""
        before = int(time.time() * 1000)
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R0_INIT,
            phase_status=P03PhaseStatus.DONE,
        )
        after = int(time.time() * 1000)

        assert before <= checkpoint.created_at_ms <= after


# =============================================================================
# 2. P03CHECKPOINT SERIALIZATION TESTS
# =============================================================================


class TestCheckpointSerialization:
    """Test P03Checkpoint serialization and deserialization."""

    def test_to_dict_basic(self, sample_checkpoint: P03Checkpoint) -> None:
        """to_dict should produce JSON-serializable output."""
        result = sample_checkpoint.to_dict()

        assert result["checkpoint_id"] == sample_checkpoint.checkpoint_id
        assert result["cycle_id"] == sample_checkpoint.cycle_id
        assert result["batch_id"] == sample_checkpoint.batch_id
        assert result["phase_id"] == "R3"
        assert result["phase_status"] == "DONE"

    def test_to_dict_is_json_serializable(self, sample_checkpoint: P03Checkpoint) -> None:
        """to_dict output should be JSON serializable."""
        result = sample_checkpoint.to_dict()
        json_str = json.dumps(result)
        assert json_str is not None

    def test_from_dict_roundtrip(self, sample_checkpoint: P03Checkpoint) -> None:
        """from_dict should reconstruct checkpoint from to_dict output."""
        dict_repr = sample_checkpoint.to_dict()
        reconstructed = P03Checkpoint.from_dict(dict_repr)

        assert reconstructed.checkpoint_id == sample_checkpoint.checkpoint_id
        assert reconstructed.cycle_id == sample_checkpoint.cycle_id
        assert reconstructed.batch_id == sample_checkpoint.batch_id
        assert reconstructed.phase_id == sample_checkpoint.phase_id
        assert reconstructed.phase_status == sample_checkpoint.phase_status
        assert reconstructed.last_wal_pos == sample_checkpoint.last_wal_pos
        assert reconstructed.event_ids == sample_checkpoint.event_ids

    def test_to_summary_dict(self, sample_checkpoint: P03Checkpoint) -> None:
        """to_summary_dict should return compact representation."""
        summary = sample_checkpoint.to_summary_dict()

        assert "checkpoint_id" in summary
        assert "cycle_id" in summary
        assert "phase_id" in summary
        assert "event_count" in summary
        assert summary["event_count"] == 3
        # Summary should NOT include full envelope
        assert "envelope_full" not in summary

    def test_optional_fields_omitted_when_none(self) -> None:
        """Optional fields should be omitted from to_dict when None."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R0_INIT,
            phase_status=P03PhaseStatus.DONE,
        )

        result = checkpoint.to_dict()

        assert "envelope_full" not in result
        assert "last_wal_pos" not in result
        assert "last_event_id" not in result


# =============================================================================
# 3. P03CHECKPOINT PROPERTIES TESTS
# =============================================================================


class TestCheckpointProperties:
    """Test P03Checkpoint computed properties."""

    def test_is_terminal_true(self) -> None:
        """is_terminal should be True for R8 DONE."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R8_EMIT,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.is_terminal is True

    def test_is_terminal_false(self) -> None:
        """is_terminal should be False for non-terminal states."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.is_terminal is False

    def test_is_failed_true(self) -> None:
        """is_failed should be True for FAIL status."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.FAIL,
        )

        assert checkpoint.is_failed is True

    def test_is_failed_false(self) -> None:
        """is_failed should be False for non-FAIL status."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.is_failed is False

    def test_is_resumable_true(self) -> None:
        """is_resumable should be True for completed non-terminal phases."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.is_resumable is True

    def test_is_resumable_false_for_terminal(self) -> None:
        """is_resumable should be False for terminal state."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R8_EMIT,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.is_resumable is False

    def test_is_resumable_false_for_failed(self) -> None:
        """is_resumable should be False for failed state."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.FAIL,
        )

        assert checkpoint.is_resumable is False

    def test_resume_phase_returns_next(self) -> None:
        """resume_phase should return next phase for resumable checkpoint."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.resume_phase == P03PhaseId.R4_KG

    def test_resume_phase_returns_none_for_non_resumable(self) -> None:
        """resume_phase should return None for non-resumable checkpoint."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R8_EMIT,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.resume_phase is None


# =============================================================================
# 4. CHECKPOINT STORE TESTS
# =============================================================================


class TestInMemoryCheckpointStore:
    """Test InMemoryCheckpointStore implementation."""

    @pytest.mark.asyncio
    async def test_store_implements_protocol(
        self, in_memory_store: InMemoryCheckpointStore
    ) -> None:
        """InMemoryCheckpointStore should implement CheckpointStoreProtocol."""
        assert isinstance(in_memory_store, CheckpointStoreProtocol)

    @pytest.mark.asyncio
    async def test_save_and_load_by_cycle(
        self,
        in_memory_store: InMemoryCheckpointStore,
        sample_checkpoint: P03Checkpoint,
    ) -> None:
        """Should save and load checkpoint by cycle ID."""
        await in_memory_store.save(sample_checkpoint)
        loaded = await in_memory_store.load_by_cycle(sample_checkpoint.cycle_id)

        assert loaded is not None
        assert loaded.checkpoint_id == sample_checkpoint.checkpoint_id

    @pytest.mark.asyncio
    async def test_load_latest(
        self,
        in_memory_store: InMemoryCheckpointStore,
    ) -> None:
        """Should load most recent checkpoint."""
        # Create two checkpoints
        cp1 = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R1_SCORE,
            phase_status=P03PhaseStatus.DONE,
        )
        await in_memory_store.save(cp1)

        # Small delay to ensure different timestamp
        import asyncio

        await asyncio.sleep(0.01)

        cp2 = P03Checkpoint.create(
            cycle_id="cycle-2",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
        )
        await in_memory_store.save(cp2)

        # Load latest should return cp2
        latest = await in_memory_store.load_latest("space-1", "tenant-1")
        assert latest is not None
        assert latest.cycle_id == "cycle-2"

    @pytest.mark.asyncio
    async def test_load_latest_with_batch_filter(
        self,
        in_memory_store: InMemoryCheckpointStore,
    ) -> None:
        """Should filter by batch_id when loading latest."""
        cp1 = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-A",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R1_SCORE,
            phase_status=P03PhaseStatus.DONE,
        )
        await in_memory_store.save(cp1)

        cp2 = P03Checkpoint.create(
            cycle_id="cycle-2",
            batch_id="batch-B",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
        )
        await in_memory_store.save(cp2)

        # Filter by batch-A
        latest = await in_memory_store.load_latest("space-1", "tenant-1", batch_id="batch-A")
        assert latest is not None
        assert latest.batch_id == "batch-A"

    @pytest.mark.asyncio
    async def test_load_latest_returns_none_when_empty(
        self,
        in_memory_store: InMemoryCheckpointStore,
    ) -> None:
        """Should return None when no matching checkpoints."""
        result = await in_memory_store.load_latest("space-1", "tenant-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(
        self,
        in_memory_store: InMemoryCheckpointStore,
        sample_checkpoint: P03Checkpoint,
    ) -> None:
        """Should delete checkpoint."""
        await in_memory_store.save(sample_checkpoint)
        assert in_memory_store.count == 1

        deleted = await in_memory_store.delete(sample_checkpoint.checkpoint_id)
        assert deleted is True
        assert in_memory_store.count == 0

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_missing(
        self,
        in_memory_store: InMemoryCheckpointStore,
    ) -> None:
        """Should return False when deleting non-existent checkpoint."""
        deleted = await in_memory_store.delete("nonexistent-id")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_clear(
        self,
        in_memory_store: InMemoryCheckpointStore,
        sample_checkpoint: P03Checkpoint,
    ) -> None:
        """Should clear all checkpoints."""
        await in_memory_store.save(sample_checkpoint)
        assert in_memory_store.count == 1

        in_memory_store.clear()
        assert in_memory_store.count == 0


# =============================================================================
# 5. P03OFFSET INTEGRATION TESTS
# =============================================================================


class TestP03Offset:
    """Test P03Offset and K0 offset integration."""

    def test_from_checkpoint(self, sample_checkpoint: P03Checkpoint) -> None:
        """Should create offset from checkpoint with WAL position."""
        offset = P03Offset.from_checkpoint(sample_checkpoint)

        assert offset is not None
        assert offset.subscriber_id == P03_SUBSCRIBER_ID
        assert offset.topic == P03_SOURCE_TOPIC
        assert offset.space_id == sample_checkpoint.space_id
        assert offset.tenant_id == sample_checkpoint.tenant_id
        assert offset.offset == sample_checkpoint.last_wal_pos

    def test_from_checkpoint_returns_none_without_wal_pos(self) -> None:
        """Should return None when checkpoint has no WAL position."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-1",
            batch_id="batch-1",
            space_id="space-1",
            tenant_id="tenant-1",
            phase_id=P03PhaseId.R0_INIT,
            phase_status=P03PhaseStatus.DONE,
            # No last_wal_pos
        )

        offset = P03Offset.from_checkpoint(checkpoint)
        assert offset is None

    def test_to_k0_offset(self, sample_checkpoint: P03Checkpoint) -> None:
        """Should convert to K0 OffsetStore compatible format."""
        offset = P03Offset.from_checkpoint(sample_checkpoint)
        assert offset is not None

        k0_offset = offset.to_k0_offset()

        assert k0_offset["subscriber_id"] == P03_SUBSCRIBER_ID
        assert k0_offset["topic"] == P03_SOURCE_TOPIC
        assert k0_offset["space_id"] == sample_checkpoint.space_id
        assert k0_offset["tenant_id"] == sample_checkpoint.tenant_id
        assert k0_offset["offset"] == sample_checkpoint.last_wal_pos
        assert "updated_ts" in k0_offset

    def test_constants_defined(self) -> None:
        """Constants should be defined correctly."""
        assert P03_SUBSCRIBER_ID == "P03_CONSOLIDATE"
        assert P03_SOURCE_TOPIC == "st_hipp_events"
        assert P03_CHECKPOINT_TOPIC == "p03_checkpoints"


# =============================================================================
# 6. CHECKPOINT ERROR TESTS
# =============================================================================


class TestCheckpointErrors:
    """Test checkpoint error classes."""

    def test_checkpoint_error_base(self) -> None:
        """CheckpointError should be base exception."""
        error = CheckpointError("test error")
        assert str(error) == "test error"

    def test_checkpoint_save_error(self) -> None:
        """CheckpointSaveError should include checkpoint_id."""
        error = CheckpointSaveError("cp-123", "database timeout")
        assert error.checkpoint_id == "cp-123"
        assert error.reason == "database timeout"
        assert "cp-123" in str(error)
        assert "database timeout" in str(error)

    def test_checkpoint_load_error(self) -> None:
        """CheckpointLoadError should include reason."""
        error = CheckpointLoadError("connection failed")
        assert error.reason == "connection failed"
        assert "connection failed" in str(error)

    def test_checkpoint_not_found_error(self) -> None:
        """CheckpointNotFoundError should include identifier."""
        error = CheckpointNotFoundError("cycle-999")
        assert error.identifier == "cycle-999"
        assert "cycle-999" in str(error)

    def test_errors_inherit_from_checkpoint_error(self) -> None:
        """All errors should inherit from CheckpointError."""
        assert issubclass(CheckpointSaveError, CheckpointError)
        assert issubclass(CheckpointLoadError, CheckpointError)
        assert issubclass(CheckpointNotFoundError, CheckpointError)
