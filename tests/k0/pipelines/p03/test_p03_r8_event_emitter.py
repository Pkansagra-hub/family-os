"""
Tests for R8EventEmitter phase.

M3 Issue 3.1.2: Build Completion Event + Emit via Outbox.

Tests cover:
- Completion payload schema compliance
- Gap persistence to st_learning_queue
- Gap event staging to outbox
- Offset commit on success
- Idempotency via fingerprints
- Error handling and recoverable failures
- Status determination (SUCCESS/PARTIAL/FAILED)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03 import (
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    P03PhaseOutputs,
    P03StagedWrites,
    ReconciliationAction,
)
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phase_outputs import GapCandidate
from k0.pipelines.p03.phases.r8_event_emitter import R8EventEmitter
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.storage.outbox import OutboxEntry

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MagicMock:
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="INSERT 1")
    conn.fetchrow = AsyncMock(return_value=None)  # No duplicates by default
    return conn


@pytest.fixture
def mock_uow(mock_connection: MagicMock) -> MagicMock:
    """Create a mock UnitOfWork with connection."""
    uow = MagicMock()
    uow.connection = mock_connection
    uow.stage_outbox = MagicMock()
    uow.upsert_offset = AsyncMock()
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
        event_ids=["01JFXYZ000000000000000001", "01JFXYZ000000000000000002"],
        trigger_type="MANUAL",
        trigger_reason="Test",
    )


@pytest.fixture
def sample_event_states() -> List[P03EventState]:
    """Create sample event states with reconciliation actions."""
    events = []
    for i, action in enumerate([ReconciliationAction.REINFORCE, ReconciliationAction.CREATE]):
        evt = P03EventState(
            event_id=f"01JFXYZ00000000000000000{i+1}",
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
def sample_gap_candidates() -> List[GapCandidate]:
    """Create sample gap candidates."""
    return [
        GapCandidate(
            gap_id="gap-001",
            gap_type="AMBIGUITY",
            related_entity_id="entity-001",
            entropy_score=0.85,
            priority="HIGH",
            context_json='{"question": "Who is this?"}',
            candidate_values=["Alice", "Bob"],
        ),
        GapCandidate(
            gap_id="gap-002",
            gap_type="LOW_CONFIDENCE",
            related_entity_id="entity-002",
            entropy_score=0.65,
            priority="MEDIUM",
            context_json="{}",
            candidate_values=[],
        ),
    ]


@pytest.fixture
def sample_phase_outputs(sample_gap_candidates: List[GapCandidate]) -> P03PhaseOutputs:
    """Create sample phase outputs with gaps."""
    outputs = P03PhaseOutputs()
    outputs.r2_cluster_count = 2
    outputs.r4_gap_candidates = sample_gap_candidates
    outputs.r7_success = True
    return outputs


@pytest.fixture
def sample_envelope(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
    sample_phase_outputs: P03PhaseOutputs,
) -> P03BatchEnvelope:
    """Create sample envelope with completed R0-R7."""
    envelope = P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )
    envelope.phases = sample_phase_outputs
    envelope.staged = P03StagedWrites()

    # Mark phases as complete
    envelope.phase_statuses[P03PhaseId.R0_INIT] = P03PhaseStatus.DONE
    envelope.phase_statuses[P03PhaseId.R7_WRITE] = P03PhaseStatus.DONE

    return envelope


@pytest.fixture
def r8_emitter() -> R8EventEmitter:
    """Create R8EventEmitter instance."""
    return R8EventEmitter()


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestR8EventEmitterInit:
    """Tests for R8EventEmitter initialization and identity."""

    def test_phase_id_is_r8(self, r8_emitter: R8EventEmitter) -> None:
        """R8EventEmitter should identify as R8_EMIT phase."""
        assert r8_emitter.PHASE_ID == P03PhaseId.R8_EMIT

    def test_topics_defined(self, r8_emitter: R8EventEmitter) -> None:
        """R8EventEmitter should define completion and gap topics."""
        assert r8_emitter.COMPLETION_TOPIC == "p03.consolidation.complete.v1"
        assert r8_emitter.GAP_TOPIC == "p03.gap.detected.v1"


# =============================================================================
# SUCCESS PATH TESTS
# =============================================================================


class TestR8SuccessPath:
    """Tests for successful R8 execution."""

    @pytest.mark.asyncio
    async def test_run_returns_done_on_success(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should return DONE status on successful execution."""
        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert result.phase_id == P03PhaseId.R8_EMIT
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_includes_summary_in_outputs(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should report counts in outputs_summary."""
        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        summary = result.outputs_summary
        assert "completion_status" in summary
        assert "gaps_persisted" in summary
        assert "events_emitted" in summary

        # 2 gaps + 1 completion = 3 events emitted
        assert summary["gaps_persisted"] == 2
        assert summary["events_emitted"] == 3

    @pytest.mark.asyncio
    async def test_run_generates_idempotency_key(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() should generate idempotency key with cycle_id."""
        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        expected_key = f"p03:r8:{sample_envelope.context.cycle_id}"
        assert result.idempotency_key == expected_key


# =============================================================================
# COMPLETION PAYLOAD TESTS
# =============================================================================


class TestCompletionPayload:
    """Tests for completion payload building."""

    def test_build_completion_payload_structure(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Payload should match expected schema structure."""
        payload = r8_emitter._build_completion_payload(sample_envelope)

        # Required fields
        assert "cycle_id" in payload
        assert "tenant_id" in payload
        assert "space_id" in payload
        assert "status" in payload
        assert "summary" in payload
        assert "duration_ms" in payload
        assert "completed_at" in payload
        assert "phase_durations" in payload
        assert "errors" in payload

        # Summary fields
        summary = payload["summary"]
        assert "events_processed" in summary
        assert "clusters_created" in summary
        assert "gaps_detected" in summary

    def test_build_completion_payload_values(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Payload should have correct values from envelope."""
        payload = r8_emitter._build_completion_payload(sample_envelope)

        assert payload["cycle_id"] == sample_envelope.context.cycle_id
        assert payload["tenant_id"] == sample_envelope.context.tenant_id
        assert payload["space_id"] == sample_envelope.context.space_id
        assert payload["summary"]["events_processed"] == 2
        assert payload["summary"]["gaps_detected"] == 2

    def test_status_is_success_when_all_done(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Status should be SUCCESS when all phases are DONE."""
        status = r8_emitter._determine_status(sample_envelope)
        assert status == "SUCCESS"

    def test_status_is_partial_when_some_failures(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Status should be PARTIAL when some phases failed but some succeeded."""
        sample_envelope.phase_statuses[P03PhaseId.R5_DREAM] = P03PhaseStatus.FAIL

        status = r8_emitter._determine_status(sample_envelope)
        assert status == "PARTIAL"

    def test_status_is_failed_when_all_fail(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Status should be FAILED when only failures exist."""
        # Clear all DONE statuses and set all to FAIL
        for phase_id in sample_envelope.phase_statuses:
            sample_envelope.phase_statuses[phase_id] = P03PhaseStatus.FAIL

        status = r8_emitter._determine_status(sample_envelope)
        assert status == "FAILED"


# =============================================================================
# OUTBOX STAGING TESTS
# =============================================================================


class TestOutboxStaging:
    """Tests for outbox event staging."""

    @pytest.mark.asyncio
    async def test_completion_event_staged(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Completion event should be staged to outbox."""
        await r8_emitter.run(sample_envelope, mock_runner_context)

        # Check that stage_outbox was called
        assert mock_uow.stage_outbox.call_count >= 1

        # Find completion event
        staged_entries: List[OutboxEntry] = [
            call[0][0] for call in mock_uow.stage_outbox.call_args_list
        ]
        completion_entries = [
            e for e in staged_entries if e.op_kind == "p03.consolidation.complete.v1"
        ]

        assert len(completion_entries) == 1
        entry = completion_entries[0]
        assert entry.driver == "p03"
        assert f"complete:{sample_envelope.context.cycle_id}" in entry.fingerprint

    @pytest.mark.asyncio
    async def test_gap_events_staged(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Gap events should be staged to outbox."""
        await r8_emitter.run(sample_envelope, mock_runner_context)

        staged_entries: List[OutboxEntry] = [
            call[0][0] for call in mock_uow.stage_outbox.call_args_list
        ]
        gap_entries = [e for e in staged_entries if e.op_kind == "p03.gap.detected.v1"]

        # Should have 2 gap events
        assert len(gap_entries) == 2

        # Check fingerprints use new format: p03:gap:{cycle_id}:{entity_id}:{gap_type}
        fingerprints = [e.fingerprint for e in gap_entries]
        cycle_id = sample_envelope.context.cycle_id
        assert any(f"p03:gap:{cycle_id}:entity-001:AMBIGUITY" in fp for fp in fingerprints)
        assert any(f"p03:gap:{cycle_id}:entity-002:LOW_CONFIDENCE" in fp for fp in fingerprints)


# =============================================================================
# GAP PERSISTENCE TESTS
# =============================================================================


class TestGapPersistence:
    """Tests for gap persistence to st_learning_queue."""

    @pytest.mark.asyncio
    async def test_gaps_persisted_to_learning_queue(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Gaps should be INSERT'd into st_learning_queue."""
        await r8_emitter.run(sample_envelope, mock_runner_context)

        # Check that execute was called with INSERT
        calls = mock_uow.connection.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT INTO st_learning_queue" in str(c)]

        # Should have 2 insert calls (one per gap)
        assert len(insert_calls) == 2

    @pytest.mark.asyncio
    async def test_gap_persistence_uses_on_conflict(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Gap persistence should use ON CONFLICT DO NOTHING for idempotency."""
        await r8_emitter.run(sample_envelope, mock_runner_context)

        calls = mock_uow.connection.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT INTO st_learning_queue" in str(c)]

        for call in insert_calls:
            sql = call[0][0]
            assert "ON CONFLICT" in sql
            assert "DO NOTHING" in sql


# =============================================================================
# OFFSET COMMIT TESTS
# =============================================================================


class TestOffsetCommit:
    """Tests for offset commit."""

    @pytest.mark.asyncio
    async def test_offset_committed_via_uow(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Offset should be committed via UoW."""
        await r8_emitter.run(sample_envelope, mock_runner_context)

        mock_uow.upsert_offset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_offset_record_has_correct_fields(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Offset record should have correct subscriber_id and topic."""
        await r8_emitter.run(sample_envelope, mock_runner_context)

        call_args = mock_uow.upsert_offset.call_args
        offset_record = call_args[0][0]

        assert offset_record.subscriber_id == "p03"
        assert offset_record.topic == "p02.hipp_events"
        assert offset_record.space_id == sample_envelope.context.space_id
        assert offset_record.tenant_id == sample_envelope.context.tenant_id

    @pytest.mark.asyncio
    async def test_no_offset_commit_with_no_events(
        self,
        r8_emitter: R8EventEmitter,
        sample_cycle_context: P03CycleContext,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """No offset should be committed if envelope has no events."""
        envelope = P03BatchEnvelope.create(
            context=sample_cycle_context,
            events=[],  # No events
        )

        await r8_emitter.run(envelope, mock_runner_context)

        # upsert_offset should not be called
        mock_uow.upsert_offset.assert_not_awaited()


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for R8 error handling."""

    @pytest.mark.asyncio
    async def test_fail_returns_fail_status(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """run() should return FAIL status on exception."""
        mock_uow.stage_outbox = MagicMock(side_effect=Exception("Outbox error"))

        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.FAIL
        assert result.error_info is not None
        assert "Outbox error" in result.error_info.error_message

    @pytest.mark.asyncio
    async def test_fail_error_is_recoverable(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """R8 failures should be marked as recoverable."""
        mock_uow.stage_outbox = MagicMock(side_effect=Exception("Failure"))

        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        assert result.error_info is not None
        assert result.error_info.recoverable is True

    @pytest.mark.asyncio
    async def test_fail_includes_idempotency_key(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Failed result should still include idempotency_key."""
        mock_uow.stage_outbox = MagicMock(side_effect=Exception("Failure"))

        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        expected_key = f"p03:r8:{sample_envelope.context.cycle_id}"
        assert result.idempotency_key == expected_key


# =============================================================================
# EMPTY/EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_no_gaps_succeeds(
        self,
        r8_emitter: R8EventEmitter,
        sample_cycle_context: P03CycleContext,
        sample_event_states: List[P03EventState],
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R8 should succeed with no gaps."""
        envelope = P03BatchEnvelope.create(
            context=sample_cycle_context,
            events=sample_event_states,
        )
        # phases.r4_gap_candidates is empty by default

        result = await r8_emitter.run(envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert result.outputs_summary["gaps_persisted"] == 0
        assert result.outputs_summary["events_emitted"] == 1  # Just completion


# =============================================================================
# GAP PAYLOAD TESTS
# =============================================================================


class TestGapPayload:
    """Tests for gap event payload building."""

    def test_build_gap_payload_structure(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        sample_gap_candidates: List[GapCandidate],
    ) -> None:
        """Gap payload should have correct structure."""
        gap = sample_gap_candidates[0]
        payload = r8_emitter._build_gap_payload(sample_envelope, gap)

        assert payload["cycle_id"] == sample_envelope.context.cycle_id
        assert payload["tenant_id"] == sample_envelope.context.tenant_id
        assert payload["space_id"] == sample_envelope.context.space_id
        assert payload["gap_id"] == gap.gap_id
        assert payload["gap_type"] == gap.gap_type
        assert payload["related_entity_id"] == gap.related_entity_id
        assert payload["entropy_score"] == gap.entropy_score
        assert payload["priority"] == gap.priority
        assert payload["candidate_values"] == gap.candidate_values
        assert "detected_at" in payload
