"""
Tests for R7TruthWriter phase.

M3 Issue 3.1.1: Wire P03StagedWrites to UnitOfWork to Truth Tables.

Tests cover:
- INSERT execution with ON CONFLICT DO NOTHING
- UPDATE execution with optimistic locking
- ARCHIVE (soft-delete) execution
- TOMBSTONE marker execution
- Outbox staging via UoW
- Status writeback to st_hipp_events
- Error handling and failure paths
- Layer PK mapping
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03 import (
    LAYER_ST_EPI,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_SEM,
    LAYER_ST_VEC,
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    P03StagedWrites,
    ReconciliationAction,
    StagedWrite,
)
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phases.r7_truth_writer import LAYER_PK_MAP, R7TruthWriter
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.storage.outbox import OutboxEntry

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MagicMock:
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return conn


@pytest.fixture
def mock_uow(mock_connection: MagicMock) -> MagicMock:
    """Create a mock UnitOfWork with connection."""
    uow = MagicMock()
    uow.connection = mock_connection
    uow.stage_outbox = MagicMock()
    return uow


@pytest.fixture
def mock_syscalls(mock_uow: MagicMock):
    """Create mock syscalls with unit_of_work factory."""

    @asynccontextmanager
    async def _unit_of_work():
        yield mock_uow

    syscalls = MagicMock()
    syscalls.unit_of_work = _unit_of_work
    return syscalls


@pytest.fixture
def mock_runner_context(mock_syscalls: MagicMock) -> P03RunnerContext:
    """Create a mock runner context."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=MagicMock(),
        qos_band="GREEN",
        priority=50,
        config={},
    )


@pytest.fixture
def sample_cycle_context() -> P03CycleContext:
    """Create sample cycle context."""
    return P03CycleContext.create(
        tenant_id="tenant-test-001",
        space_id="space-test-001",
        event_ids=["evt-001", "evt-002"],
        trigger_type="MANUAL",
        trigger_reason="Test",
    )


@pytest.fixture
def sample_event_states() -> List[P03EventState]:
    """Create sample event states with reconciliation actions."""
    events = []
    for i, action in enumerate([ReconciliationAction.REINFORCE, ReconciliationAction.CREATE]):
        evt = P03EventState(
            event_id=f"evt-00{i+1}",
            hipp_event_id=f"hipp-00{i+1}",
            content_text=f"Test content {i+1}",
            content_type="CHAT",
            content_hash=f"hash-{i+1}",
            timestamp=1000000 + (i * 1000),
            channel_id="test-channel",
            embedding_id=f"vec-00{i+1}",
        )
        evt.reconciliation_action = action
        events.append(evt)
    return events


@pytest.fixture
def sample_staged_writes() -> P03StagedWrites:
    """Create sample staged writes."""
    staged = P03StagedWrites()

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_VEC,
            record_id="vec-001",
            data={"embedding_id": "vec-001", "tensor_data": b"..."},
            phase="R6",
        )
    )

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id="entity-001",
            data={"entity_id": "entity-001", "name": "Emma", "type": "PERSON"},
            phase="R4",
        )
    )

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_KG_EDGES,
            record_id="edge-001",
            data={
                "edge_id": "edge-001",
                "source_entity_id": "entity-dad",
                "target_entity_id": "entity-001",
                "relationship_type": "PARENT_OF",
            },
            phase="R4",
        )
    )

    staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi-001",
            data={"episode_id": "epi-001", "title": "Soccer practice"},
            phase="R6",
        )
    )

    staged.add_write(
        StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id="sem-001",
            data={"decay_score": 0.85, "access_count": 5},
            phase="R6",
            expected_version=2,
        )
    )

    return staged


def _add_sample_outbox_events(staged: P03StagedWrites) -> None:
    """Add sample outbox events to staged writes."""
    staged.add_outbox_event(
        topic="p03.episode.created",
        payload={"episode_id": "epi-001"},
        phase="R6",
    )
    staged.add_outbox_event(
        topic="p03.entity.created",
        payload={"entity_id": "entity-001"},
        phase="R4",
    )


@pytest.fixture
def sample_envelope(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
    sample_staged_writes: P03StagedWrites,
) -> P03BatchEnvelope:
    """Create sample envelope with staged writes and outbox events."""
    envelope = P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )
    envelope.staged = sample_staged_writes

    _add_sample_outbox_events(envelope.staged)

    return envelope


@pytest.fixture
def r7_writer() -> R7TruthWriter:
    """Create R7TruthWriter instance."""
    return R7TruthWriter()


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestR7TruthWriterInit:
    """Tests for R7TruthWriter initialization and identity."""

    def test_phase_id_is_r7(self, r7_writer: R7TruthWriter) -> None:
        """R7TruthWriter should identify as R7_WRITE phase."""
        assert r7_writer.PHASE_ID == P03PhaseId.R7_WRITE


# =============================================================================
# LAYER PK MAPPING TESTS
# =============================================================================


class TestLayerPKMapping:
    """Tests for layer-to-primary-key mapping."""

    def test_all_layers_have_pk_mapping(self) -> None:
        """All known truth layers should have PK mappings."""
        expected_layers = [
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
            "st_kg_edges",
            "st_vec",
            "st_hipp_events",
            "st_learning_queue",
        ]
        for layer in expected_layers:
            assert layer in LAYER_PK_MAP, f"Missing PK mapping for {layer}"

    def test_pk_column_names_are_valid(self) -> None:
        """PK column names should follow naming convention."""
        for layer, pk_col in LAYER_PK_MAP.items():
            assert pk_col.endswith("_id"), f"PK for {layer} should end with _id"


# =============================================================================
# SUCCESS PATH TESTS
# =============================================================================


class TestR7SuccessPath:
    """Tests for successful R7 execution."""

    @pytest.mark.asyncio
    async def test_run_returns_done_on_success(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should return DONE status on successful execution."""
        result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert result.phase_id == P03PhaseId.R7_WRITE
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_includes_write_counts_in_summary(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should report write counts in outputs_summary."""
        result = await r7_writer.run(sample_envelope, mock_runner_context)

        summary = result.outputs_summary
        assert "writes_executed" in summary
        assert "writes_by_layer" in summary
        assert "outbox_staged" in summary
        assert "events_updated" in summary

        # Should match staged writes count
        assert summary["writes_executed"] == sample_envelope.staged.total_writes()
        assert summary["outbox_staged"] == sample_envelope.staged.total_outbox_events()
        assert summary["events_updated"] == len(sample_envelope.events)

    @pytest.mark.asyncio
    async def test_run_generates_idempotency_key(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should generate idempotency key with cycle_id."""
        result = await r7_writer.run(sample_envelope, mock_runner_context)

        expected_key = f"p03:r7:{sample_envelope.context.cycle_id}"
        assert result.idempotency_key == expected_key


# =============================================================================
# STAGED WRITE EXECUTION TESTS
# =============================================================================


class TestStagedWriteExecution:
    """Tests for executing staged writes via connection."""

    @pytest.mark.asyncio
    async def test_insert_uses_on_conflict_do_nothing(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """INSERT operations should use ON CONFLICT DO NOTHING for idempotency."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        # Check that execute was called with INSERT ... ON CONFLICT
        calls = mock_uow.connection.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT INTO" in str(c)]

        for call in insert_calls:
            sql = call[0][0]  # First positional arg is SQL
            assert "ON CONFLICT" in sql
            assert "DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_update_uses_optimistic_locking_when_version_set(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """UPDATE operations should include version check when expected_version is set."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        calls = mock_uow.connection.execute.call_args_list
        update_calls = [c for c in calls if "UPDATE" in str(c) and "st_sem" in str(c)]

        # Should have update with version check
        assert len(update_calls) >= 1
        sql = update_calls[0][0][0]
        assert "version = version + 1" in sql
        assert "AND version =" in sql

    @pytest.mark.asyncio
    async def test_update_raises_on_version_conflict(
        self,
        r7_writer: R7TruthWriter,
        mock_uow: MagicMock,
        mock_runner_context: P03RunnerContext,
        sample_cycle_context: P03CycleContext,
        sample_event_states: List[P03EventState],
    ) -> None:
        """UPDATE should raise OptimisticLockError when version doesn't match."""
        # Create envelope with only one update that will fail
        staged = P03StagedWrites()
        staged.add_write(
            StagedWrite.update(
                layer=LAYER_ST_SEM,
                record_id="sem-001",
                data={"decay_score": 0.5},
                phase="R6",
                expected_version=5,
            )
        )

        envelope = P03BatchEnvelope.create(
            context=sample_cycle_context,
            events=sample_event_states,
        )
        envelope.staged = staged

        # Simulate no rows affected (version mismatch)
        mock_uow.connection.execute = AsyncMock(return_value="UPDATE 0")

        result = await r7_writer.run(envelope, mock_runner_context)

        # Should fail with non-recoverable error
        assert result.status == P03PhaseStatus.FAIL
        assert result.error_info is not None
        assert "Version conflict" in result.error_info.error_message

    @pytest.mark.asyncio
    async def test_writes_execute_in_dependency_order(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Writes should execute in dependency order (vec -> kg -> epi -> sem)."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        calls = mock_uow.connection.execute.call_args_list

        # Extract table names from INSERT/UPDATE calls
        tables_in_order = []
        for call in calls:
            sql = call[0][0]
            if "INSERT INTO" in sql:
                table = sql.split("INSERT INTO")[1].split()[0]
                tables_in_order.append(table)
            elif "UPDATE" in sql and "st_hipp_events" not in sql:
                table = sql.split("UPDATE")[1].split()[0]
                tables_in_order.append(table)

        # vec should come before kg_dom which should come before epi
        if "st_vec" in tables_in_order and "st_kg_dom" in tables_in_order:
            assert tables_in_order.index("st_vec") < tables_in_order.index("st_kg_dom")

        if "st_kg_dom" in tables_in_order and "st_epi" in tables_in_order:
            assert tables_in_order.index("st_kg_dom") < tables_in_order.index("st_epi")


# =============================================================================
# ARCHIVE AND TOMBSTONE TESTS
# =============================================================================


class TestArchiveAndTombstone:
    """Tests for ARCHIVE and TOMBSTONE operations."""

    @pytest.mark.asyncio
    async def test_archive_sets_archival_status(
        self,
        r7_writer: R7TruthWriter,
        mock_uow: MagicMock,
        mock_runner_context: P03RunnerContext,
        sample_cycle_context: P03CycleContext,
        sample_event_states: List[P03EventState],
    ) -> None:
        """ARCHIVE should set archival_status='ARCHIVED'."""
        staged = P03StagedWrites()
        staged.add_write(
            StagedWrite.archive(
                layer=LAYER_ST_EPI,
                record_id="epi-old-001",
                reason="Decay below threshold",
                phase="R3",
            )
        )

        envelope = P03BatchEnvelope.create(
            context=sample_cycle_context,
            events=sample_event_states,
        )
        envelope.staged = staged

        await r7_writer.run(envelope, mock_runner_context)

        calls = mock_uow.connection.execute.call_args_list
        archive_calls = [c for c in calls if "archival_status = 'ARCHIVED'" in str(c)]

        assert len(archive_calls) >= 1

    @pytest.mark.asyncio
    async def test_tombstone_sets_tombstone_status(
        self,
        r7_writer: R7TruthWriter,
        mock_uow: MagicMock,
        mock_runner_context: P03RunnerContext,
        sample_cycle_context: P03CycleContext,
        sample_event_states: List[P03EventState],
    ) -> None:
        """TOMBSTONE should set archival_status='TOMBSTONE'."""
        staged = P03StagedWrites()
        staged.add_write(
            StagedWrite.tombstone(
                layer=LAYER_ST_KG_DOM,
                record_id="entity-deleted-001",
                phase="R3",
            )
        )

        envelope = P03BatchEnvelope.create(
            context=sample_cycle_context,
            events=sample_event_states,
        )
        envelope.staged = staged

        await r7_writer.run(envelope, mock_runner_context)

        calls = mock_uow.connection.execute.call_args_list
        tombstone_calls = [c for c in calls if "archival_status = 'TOMBSTONE'" in str(c)]

        assert len(tombstone_calls) >= 1


# =============================================================================
# OUTBOX STAGING TESTS
# =============================================================================


class TestOutboxStaging:
    """Tests for outbox event staging via UoW."""

    @pytest.mark.asyncio
    async def test_outbox_events_staged_via_uow(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Outbox events should be staged via UoW.stage_outbox()."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        assert mock_uow.stage_outbox.call_count == sample_envelope.staged.total_outbox_events()

    @pytest.mark.asyncio
    async def test_outbox_entry_has_correct_fields(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Staged OutboxEntry should have correct field values."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        staged_entries: List[OutboxEntry] = [
            call[0][0] for call in mock_uow.stage_outbox.call_args_list
        ]

        for entry in staged_entries:
            assert entry.driver == "p03"
            assert entry.tenant_id == sample_envelope.context.tenant_id
            assert entry.space_id == sample_envelope.context.space_id
            assert entry.retries == 0
            assert entry.requeue_seq == 0


# =============================================================================
# STATUS WRITEBACK TESTS
# =============================================================================


class TestStatusWriteback:
    """Tests for st_hipp_events status writeback."""

    @pytest.mark.asyncio
    async def test_writeback_updates_hipp_events(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Writeback should UPDATE st_hipp_events for each event."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        calls = mock_uow.connection.execute.call_args_list
        writeback_calls = [
            c
            for c in calls
            if "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
        ]

        assert len(writeback_calls) == len(sample_envelope.events)

    @pytest.mark.asyncio
    async def test_writeback_maps_actions_to_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        """_determine_status should map actions correctly."""
        # Test the status mapping
        from k0.pipelines.p03.event_state import ReconciliationAction as RA

        @dataclass
        class MockEvent:
            reconciliation_action: Optional[RA] = None

        # REINFORCE -> CONSOLIDATED
        evt = MockEvent(reconciliation_action=RA.REINFORCE)
        assert r7_writer._determine_status(evt) == "CONSOLIDATED"

        # CREATE -> CONSOLIDATED
        evt.reconciliation_action = RA.CREATE
        assert r7_writer._determine_status(evt) == "CONSOLIDATED"

        # SKIP -> DUPLICATE
        evt.reconciliation_action = RA.SKIP
        assert r7_writer._determine_status(evt) == "DUPLICATE"

        # PRUNE -> PRUNED
        evt.reconciliation_action = RA.PRUNE
        assert r7_writer._determine_status(evt) == "PRUNED"

        # CONTRADICT -> PENDING_REVIEW
        evt.reconciliation_action = RA.CONTRADICT
        assert r7_writer._determine_status(evt) == "PENDING_REVIEW"

        # PENDING -> PENDING
        evt.reconciliation_action = RA.PENDING
        assert r7_writer._determine_status(evt) == "PENDING"

    @pytest.mark.asyncio
    async def test_writeback_returns_status_distribution(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should include status_distribution in outputs_summary."""
        result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert "status_distribution" in result.outputs_summary
        status_dist = result.outputs_summary["status_distribution"]
        # All events without reconciliation_action default to CONSOLIDATED
        assert isinstance(status_dist, dict)

    @pytest.mark.asyncio
    async def test_writeback_records_metrics_in_observability(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """_writeback_status should record metrics in observability context."""
        await r7_writer.run(sample_envelope, mock_runner_context)

        # Check observability counters
        counters = sample_envelope.observability.counters
        # Should have at least one status metric recorded
        status_metrics = [k for k in counters if k.startswith("p03.r7.status.")]
        assert len(status_metrics) > 0


# =============================================================================
# STATUS TRANSITION VALIDATION TESTS
# =============================================================================


class TestStatusTransitionValidation:
    """Tests for status transition validation (Issue 3.2.2)."""

    @pytest.mark.asyncio
    async def test_valid_transition_from_null_to_consolidated(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Transition from NULL to CONSOLIDATED should be valid."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": None})

        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_valid_transition_from_pending_to_consolidated(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Transition from PENDING to CONSOLIDATED should be valid."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": "PENDING"})

        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_valid_transition_from_pending_review_to_consolidated(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Transition from PENDING_REVIEW to CONSOLIDATED should be valid."""
        mock_connection.fetchrow = AsyncMock(
            return_value={"consolidation_status": "PENDING_REVIEW"}
        )

        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_idempotent_same_status_transition(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Transition from CONSOLIDATED to CONSOLIDATED (idempotent) should be valid."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": "CONSOLIDATED"})

        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_transition_from_consolidated_to_pending(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Transition from CONSOLIDATED to PENDING should be invalid (final state)."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": "CONSOLIDATED"})

        result = await r7_writer._validate_status_transition(mock_connection, "evt-001", "PENDING")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_transition_from_duplicate_to_consolidated(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Transition from DUPLICATE to CONSOLIDATED should be invalid (final state)."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": "DUPLICATE"})

        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_valid_all_from_null_transitions(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """All status values should be reachable from NULL."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": None})

        for status in ["CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW", "PENDING"]:
            result = await r7_writer._validate_status_transition(mock_connection, "evt-001", status)
            assert result is True, f"Transition NULL -> {status} should be valid"


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for R7 error handling."""

    @pytest.mark.asyncio
    async def test_fail_returns_fail_status(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """run() should return FAIL status on exception."""
        mock_uow.connection.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.FAIL
        assert result.error_info is not None
        assert "DB connection lost" in result.error_info.error_message

    @pytest.mark.asyncio
    async def test_fail_error_is_not_recoverable(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """R7 failures should be marked as non-recoverable."""
        mock_uow.connection.execute = AsyncMock(side_effect=Exception("Failure"))

        result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert result.error_info is not None
        assert result.error_info.recoverable is False

    @pytest.mark.asyncio
    async def test_fail_includes_idempotency_key(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Failed result should still include idempotency_key."""
        mock_uow.connection.execute = AsyncMock(side_effect=Exception("Failure"))

        result = await r7_writer.run(sample_envelope, mock_runner_context)

        expected_key = f"p03:r7:{sample_envelope.context.cycle_id}"
        assert result.idempotency_key == expected_key


# =============================================================================
# EMPTY ENVELOPE TESTS
# =============================================================================


class TestEmptyEnvelope:
    """Tests for handling envelopes with no staged writes."""

    @pytest.mark.asyncio
    async def test_empty_staged_writes_succeeds(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        sample_cycle_context: P03CycleContext,
        sample_event_states: List[P03EventState],
    ) -> None:
        """Empty staged writes should still succeed."""
        envelope = P03BatchEnvelope.create(
            context=sample_cycle_context,
            events=sample_event_states,
        )
        # Empty staged writes (no add_write calls)
        envelope.staged = P03StagedWrites()

        result = await r7_writer.run(envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert result.outputs_summary["writes_executed"] == 0
        assert result.outputs_summary["outbox_staged"] == 0


# =============================================================================
# LAYER PK ERROR TESTS
# =============================================================================


class TestLayerPKErrors:
    """Tests for unknown layer handling."""

    def test_get_pk_column_raises_on_unknown_layer(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        """_get_pk_column should raise ValueError for unknown layers."""
        with pytest.raises(ValueError, match="Unknown layer"):
            r7_writer._get_pk_column("st_unknown_layer")
