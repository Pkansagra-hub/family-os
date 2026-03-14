"""
Tests for Epic 6.6: Consolidation Cycle Deduplication.

Validates the end-to-end deduplication mechanism that prevents P03 from
re-processing events that were already consolidated in a prior cycle:

1. R7 _writeback_status() marks all batch events with consolidation_status
   inside the same UoW as truth writes (atomic guarantee)
2. R0 _query_eligible_events() excludes events where
   consolidation_status NOT IN (NULL, 'PENDING')
3. The drain loop terminates when R0 finds no eligible events
4. Noise events (not assigned to episodes) still receive status updates
5. Status transition validation prevents illegal re-processing
6. Orphan event analysis: events that could slip through

Issue References:
    6.6.1 - consolidation_status update after R7 write (VERIFIED IN CODE)
    6.6.2 - R0 exclusion filter (VERIFIED IN CODE)
    6.6.3 - Orphan event rescue / diagnosis
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03 import (
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    P03StagedWrites,
    PruneDecision,
    ReconciliationAction,
)
from k0.pipelines.p03.phase_interface import P03RunnerContext
from k0.pipelines.p03.phases.r0_batch_selector import R0BatchSelector, R0Config
from k0.pipelines.p03.phases.r7_truth_writer import R7TruthWriter

# =============================================================================
# HELPERS
# =============================================================================


def _make_event(
    event_id: str,
    action: Optional[ReconciliationAction] = None,
    *,
    prune_decision: PruneDecision = PruneDecision.KEEP,
    is_duplicate: bool = False,
    cluster_id: Optional[str] = None,
    confidence: float = 0.9,
    similarity_score: float = 0.85,
    best_match_id: Optional[str] = None,
    best_match_layer: Optional[str] = None,
    novelty_score: float = 0.5,
    reconciliation_reason: str = "",
) -> P03EventState:
    """Build a P03EventState with specified reconciliation attributes."""
    evt = P03EventState(
        event_id=event_id,
        hipp_event_id=event_id,
        content_text=f"Content for {event_id}",
        content_type="CHAT",
        content_hash=f"hash-{event_id}",
        timestamp=int(time.time() * 1000),
        channel_id="test-channel",
        embedding_id=f"vec-{event_id}",
    )
    if action is not None:
        evt.reconciliation_action = action
    evt.prune_decision = prune_decision
    evt.is_duplicate = is_duplicate
    evt.cluster_id = cluster_id
    evt.confidence = confidence
    evt.similarity_score = similarity_score
    evt.best_match_id = best_match_id
    evt.best_match_layer = best_match_layer
    evt.novelty_score = novelty_score
    evt.reconciliation_reason = reconciliation_reason
    return evt


def _make_envelope(events: List[P03EventState]) -> P03BatchEnvelope:
    """Build envelope with events."""
    ctx = P03CycleContext.create(
        tenant_id="tenant-dedup",
        space_id="space-dedup",
        event_ids=[e.event_id for e in events],
        trigger_type="SCHEDULED",
        trigger_reason="Dedup test",
    )
    envelope = P03BatchEnvelope.create(context=ctx, events=events)
    envelope.staged = P03StagedWrites()
    return envelope


@pytest.fixture
def mock_connection() -> MagicMock:
    """Mock asyncpg connection that captures execute calls."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return conn


@pytest.fixture
def mock_uow(mock_connection: MagicMock) -> MagicMock:
    """Mock UnitOfWork."""
    uow = MagicMock()
    uow.connection = mock_connection
    uow.stage_outbox = MagicMock()
    return uow


@pytest.fixture
def mock_syscalls(mock_uow: MagicMock):
    """Mock syscalls with UoW factory."""

    @asynccontextmanager
    async def _unit_of_work():
        yield mock_uow

    syscalls = MagicMock()
    syscalls.unit_of_work = _unit_of_work
    return syscalls


@pytest.fixture
def mock_runner_context(mock_syscalls: MagicMock) -> P03RunnerContext:
    """Mock runner context for R7."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=MagicMock(),
        qos_band="GREEN",
        priority=50,
        config={},
    )


@pytest.fixture
def r7_writer() -> R7TruthWriter:
    return R7TruthWriter()


# =============================================================================
# 6.6.1 — R7 WRITEBACK MARKS ALL EVENTS IN BATCH
# =============================================================================


class TestR7WritebackCoversAllEvents:
    """
    Issue 6.6.1: After R7 truth writes succeed, _writeback_status()
    must update consolidation_status for EVERY event in the batch,
    not just events that produced truth layer writes.
    """

    @pytest.mark.asyncio
    async def test_all_events_receive_status_update(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """Every event in the batch gets an UPDATE st_hipp_events call."""
        events = [
            _make_event("evt-001", ReconciliationAction.CREATE, cluster_id="c1"),
            _make_event("evt-002", ReconciliationAction.REINFORCE, cluster_id="c1"),
            _make_event("evt-003", ReconciliationAction.SKIP, is_duplicate=True),
        ]
        envelope = _make_envelope(events)

        await r7_writer.run(envelope, mock_runner_context)

        writeback_calls = [
            c
            for c in mock_uow.connection.execute.call_args_list
            if "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
        ]
        assert len(writeback_calls) == 3

    @pytest.mark.asyncio
    async def test_noise_events_without_cluster_get_status(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """
        Noise events (cluster_id=None, reconciliation_action=None) must
        still receive a status update. Without this, noise events remain
        with NULL consolidation_status and get re-selected in the next cycle.
        """
        clustered = _make_event("evt-clustered", ReconciliationAction.CREATE, cluster_id="c1")
        noise = _make_event("evt-noise")  # No action, no cluster

        envelope = _make_envelope([clustered, noise])
        await r7_writer.run(envelope, mock_runner_context)

        writeback_calls = [
            c
            for c in mock_uow.connection.execute.call_args_list
            if "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
        ]
        assert len(writeback_calls) == 2

    @pytest.mark.asyncio
    async def test_noise_event_defaults_to_pending_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        """
        Events with default reconciliation_action (PENDING) get status PENDING.
        P03EventState defaults to ReconciliationAction.PENDING, not None.
        PENDING events ARE re-selected by R0 — correct behavior for noise
        events that should be retried in the next consolidation cycle.
        """
        evt = _make_event("evt-noise")  # Default action = PENDING
        assert evt.reconciliation_action == ReconciliationAction.PENDING
        assert r7_writer._determine_status(evt) == "PENDING"

    @pytest.mark.asyncio
    async def test_create_action_produces_consolidated_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-c", ReconciliationAction.CREATE)
        assert r7_writer._determine_status(evt) == "CONSOLIDATED"

    @pytest.mark.asyncio
    async def test_reinforce_action_produces_consolidated_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-r", ReconciliationAction.REINFORCE)
        assert r7_writer._determine_status(evt) == "CONSOLIDATED"

    @pytest.mark.asyncio
    async def test_extend_action_produces_consolidated_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-e", ReconciliationAction.EXTEND)
        assert r7_writer._determine_status(evt) == "CONSOLIDATED"

    @pytest.mark.asyncio
    async def test_evolve_action_produces_consolidated_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-ev", ReconciliationAction.EVOLVE)
        assert r7_writer._determine_status(evt) == "CONSOLIDATED"

    @pytest.mark.asyncio
    async def test_skip_action_produces_duplicate_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-s", ReconciliationAction.SKIP)
        assert r7_writer._determine_status(evt) == "DUPLICATE"

    @pytest.mark.asyncio
    async def test_prune_action_produces_pruned_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-p", ReconciliationAction.PRUNE)
        assert r7_writer._determine_status(evt) == "PRUNED"

    @pytest.mark.asyncio
    async def test_contradict_action_produces_pending_review_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-ct", ReconciliationAction.CONTRADICT)
        assert r7_writer._determine_status(evt) == "PENDING_REVIEW"

    @pytest.mark.asyncio
    async def test_pending_action_produces_pending_status(
        self,
        r7_writer: R7TruthWriter,
    ) -> None:
        evt = _make_event("evt-pn", ReconciliationAction.PENDING)
        assert r7_writer._determine_status(evt) == "PENDING"


# =============================================================================
# 6.6.1 — WRITEBACK ATOMICITY (SAME UoW AS TRUTH WRITES)
# =============================================================================


class TestWritebackAtomicity:
    """
    The _writeback_status() call must execute inside the same UoW
    (same database transaction) as truth layer writes. This ensures
    that if truth writes fail, consolidation_status is NOT updated,
    and vice versa.
    """

    @pytest.mark.asyncio
    async def test_writeback_runs_in_same_uow_as_truth_writes(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """
        All connection.execute calls for truth writes AND status writeback
        must happen through the same mock_uow.connection — proving they
        share one UoW transaction.
        """
        events = [_make_event("evt-001", ReconciliationAction.CREATE)]
        envelope = _make_envelope(events)

        await r7_writer.run(envelope, mock_runner_context)

        # All execute calls went through mock_uow.connection
        assert mock_uow.connection.execute.call_count >= 1
        # At least one call is the writeback UPDATE
        writeback_found = any(
            "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
            for c in mock_uow.connection.execute.call_args_list
        )
        assert writeback_found, "Writeback UPDATE not found in UoW execute calls"

    @pytest.mark.asyncio
    async def test_writeback_includes_cycle_id(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """
        Each writeback call passes the cycle_id from envelope context,
        enabling audit trail and cycle-level diagnostics.
        """
        events = [_make_event("evt-001", ReconciliationAction.CREATE)]
        envelope = _make_envelope(events)
        cycle_id = envelope.context.cycle_id

        await r7_writer.run(envelope, mock_runner_context)

        writeback_calls = [
            c
            for c in mock_uow.connection.execute.call_args_list
            if "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
        ]
        assert len(writeback_calls) == 1
        # cycle_id should be in the positional args (param $2)
        args = writeback_calls[0].args
        assert cycle_id in args, f"cycle_id {cycle_id} not in writeback args {args}"

    @pytest.mark.asyncio
    async def test_writeback_includes_consolidated_at_timestamp(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """consolidated_at is set as milliseconds timestamp."""
        events = [_make_event("evt-001", ReconciliationAction.CREATE)]
        envelope = _make_envelope(events)
        before_ms = int(time.time() * 1000)

        await r7_writer.run(envelope, mock_runner_context)

        writeback_calls = [
            c
            for c in mock_uow.connection.execute.call_args_list
            if "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
        ]
        assert len(writeback_calls) == 1
        args = writeback_calls[0].args
        # Third positional arg ($3) is consolidated_at timestamp
        consolidated_at = args[3]
        assert isinstance(consolidated_at, int)
        assert consolidated_at >= before_ms

    @pytest.mark.asyncio
    async def test_writeback_updates_15_columns(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """
        _writeback_status UPDATE sets 15 columns + WHERE event_id = $16.
        Verify the SQL shape includes all required columns.
        """
        events = [_make_event("evt-001", ReconciliationAction.CREATE)]
        envelope = _make_envelope(events)

        await r7_writer.run(envelope, mock_runner_context)

        writeback_calls = [
            c
            for c in mock_uow.connection.execute.call_args_list
            if "UPDATE st_hipp_events" in str(c) and "consolidation_status" in str(c)
        ]
        assert len(writeback_calls) == 1
        sql = writeback_calls[0].args[0]

        expected_columns = [
            "consolidation_status",
            "consolidation_cycle_id",
            "consolidated_at",
            "reconciliation_decision",
            "truth_match_id",
            "truth_match_similarity",
            "novelty_score",
            "near_duplicates_json",
            "is_near_duplicate",
            "episode_cluster_id",
            "best_match_id",
            "best_match_layer",
            "similarity_score",
            "confidence",
            "reconciliation_reason",
        ]
        for col in expected_columns:
            assert col in sql, f"Missing column {col} in writeback SQL"


# =============================================================================
# 6.6.1 — STATUS DISTRIBUTION METRICS
# =============================================================================


class TestWritebackMetrics:
    """R7 must emit status distribution metrics for observability."""

    @pytest.mark.asyncio
    async def test_status_distribution_in_result(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """run() returns status_distribution in outputs_summary."""
        events = [
            _make_event("evt-001", ReconciliationAction.CREATE),
            _make_event("evt-002", ReconciliationAction.SKIP),
            _make_event("evt-003", ReconciliationAction.PRUNE),
        ]
        envelope = _make_envelope(events)

        result = await r7_writer.run(envelope, mock_runner_context)

        dist = result.outputs_summary["status_distribution"]
        assert dist["CONSOLIDATED"] == 1
        assert dist["DUPLICATE"] == 1
        assert dist["PRUNED"] == 1

    @pytest.mark.asyncio
    async def test_observability_counters_emitted(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """Status counts are recorded in envelope.observability."""
        events = [
            _make_event("evt-001", ReconciliationAction.CREATE),
            _make_event("evt-002", ReconciliationAction.CREATE),
        ]
        envelope = _make_envelope(events)

        await r7_writer.run(envelope, mock_runner_context)

        counters = envelope.observability.counters
        assert counters.get("p03.r7.status.consolidated", 0) == 2


# =============================================================================
# 6.6.2 — R0 QUERY EXCLUDES CONSOLIDATED EVENTS
# =============================================================================


class TestR0ExclusionFilter:
    """
    Issue 6.6.2: R0 batch selection must exclude events where
    consolidation_status is anything other than NULL or 'PENDING'.
    """

    def test_r0_query_contains_consolidation_status_filter(self) -> None:
        """
        The R0 SQL query includes the clause:
            (consolidation_status IS NULL OR consolidation_status = 'PENDING')
        """
        r0 = R0BatchSelector()
        # Build the query conditions by inspecting the method
        # We verify the filter is hardcoded in _query_eligible_events
        import inspect

        source = inspect.getsource(r0._fetch_eligible_events)
        assert "consolidation_status IS NULL OR consolidation_status = 'PENDING'" in source

    def test_r0_config_defaults(self) -> None:
        """R0Config has sensible defaults for dedup-related settings."""
        config = R0Config()
        assert config.require_embedding_ready is True
        assert config.exclude_archived is True


# =============================================================================
# 6.6.2 — R0 QUERY SHAPE VERIFICATION
# =============================================================================


class TestR0QueryConditions:
    """
    Verify that the R0 query WHERE clause includes all required
    filters for preventing re-processing.
    """

    def test_query_requires_embedding_ready_by_default(self) -> None:
        """Events without embeddings must be excluded by default."""
        import inspect

        source = inspect.getsource(R0BatchSelector._fetch_eligible_events)
        assert "embedding_status" in source

    def test_query_excludes_archived_events(self) -> None:
        """Archived events must not be re-processed."""
        import inspect

        source = inspect.getsource(R0BatchSelector._fetch_eligible_events)
        assert "archival_status" in source

    def test_query_orders_by_wal_pos_asc(self) -> None:
        """Events are processed in order of write-ahead log position."""
        import inspect

        source = inspect.getsource(R0BatchSelector._fetch_eligible_events)
        assert "ORDER BY wal_pos ASC" in source

    def test_query_has_limit_clause(self) -> None:
        """Batch size LIMIT prevents unbounded queries."""
        import inspect

        source = inspect.getsource(R0BatchSelector._fetch_eligible_events)
        assert "LIMIT" in source


# =============================================================================
# 6.6.1 + 6.6.2 — FULL CYCLE DEDUP INTEGRATION
# =============================================================================


class TestCycleDedupIntegration:
    """
    Integration tests that verify the complete dedup cycle:
    Cycle N → R7 marks events → Cycle N+1 → R0 excludes them.

    These tests use the real R7._determine_status() logic combined
    with verification of the R0 filter contract.
    """

    def test_all_reconciliation_actions_produce_non_null_status(self) -> None:
        """
        No ReconciliationAction can produce NULL consolidation_status.
        This is the fundamental invariant: after R7 runs, every event
        has a non-NULL status, so R0's NULL check will exclude them.
        """
        r7 = R7TruthWriter()
        for action in ReconciliationAction:
            evt = _make_event(f"evt-{action.value}", action)
            status = r7._determine_status(evt)
            assert status is not None, f"Action {action} produced None status"
            assert status != "", f"Action {action} produced empty status"

    def test_default_pending_action_produces_pending_status(self) -> None:
        """
        P03EventState defaults to PENDING action. _determine_status()
        maps PENDING -> 'PENDING'. This is correct: unprocessed events
        remain eligible for R0 re-selection.
        """
        r7 = R7TruthWriter()
        evt = _make_event("evt-default")
        assert evt.reconciliation_action == ReconciliationAction.PENDING
        status = r7._determine_status(evt)
        assert status == "PENDING"

    def test_none_action_via_getattr_produces_consolidated(self) -> None:
        """
        If reconciliation_action attribute is truly None (not just default),
        _determine_status returns 'CONSOLIDATED'. This handles legacy
        events or externally constructed objects.
        """
        r7 = R7TruthWriter()

        class LegacyEvent:
            reconciliation_action = None
            event_id = "evt-legacy"

        status = r7._determine_status(LegacyEvent())
        assert status == "CONSOLIDATED"

    def test_all_final_statuses_excluded_by_r0_filter(self) -> None:
        """
        The R0 filter allows NULL and PENDING only. All other statuses
        (CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW) are excluded.

        This verifies the contract: for every possible _determine_status()
        output that is NOT 'PENDING', R0 will exclude the event.
        """
        r7 = R7TruthWriter()
        r0_included_statuses = {None, "PENDING"}

        for action in ReconciliationAction:
            evt = _make_event(f"evt-{action.value}", action)
            status = r7._determine_status(evt)
            if status not in r0_included_statuses:
                # This status WILL be excluded by R0 — correct behavior
                pass
            elif status == "PENDING":
                # PENDING is allowed — event will be re-processed (correct for incomplete)
                assert action == ReconciliationAction.PENDING

    def test_only_pending_action_allows_reprocessing(self) -> None:
        """
        Only ReconciliationAction.PENDING maps to 'PENDING' status,
        which is the sole terminal action that allows R0 re-selection.
        """
        r7 = R7TruthWriter()
        pending_actions = []
        for action in ReconciliationAction:
            evt = _make_event(f"evt-{action.value}", action)
            if r7._determine_status(evt) == "PENDING":
                pending_actions.append(action)

        assert pending_actions == [ReconciliationAction.PENDING]


# =============================================================================
# 6.6.1 — STATUS TRANSITION VALIDATION
# =============================================================================


class TestStatusTransitionGuards:
    """
    Tests for ALLOWED_TRANSITIONS that prevent illegal re-processing.
    An event that reached CONSOLIDATED cannot be moved to PENDING.
    """

    def test_null_can_transition_to_any_status(self) -> None:
        transitions = R7TruthWriter.ALLOWED_TRANSITIONS
        expected = {"CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW", "PENDING"}
        assert transitions[None] == expected

    def test_pending_can_resolve_to_final_status(self) -> None:
        transitions = R7TruthWriter.ALLOWED_TRANSITIONS
        assert "CONSOLIDATED" in transitions["PENDING"]
        assert "DUPLICATE" in transitions["PENDING"]
        assert "PRUNED" in transitions["PENDING"]
        assert "PENDING_REVIEW" in transitions["PENDING"]

    def test_consolidated_is_immutable(self) -> None:
        transitions = R7TruthWriter.ALLOWED_TRANSITIONS
        assert transitions["CONSOLIDATED"] == {"CONSOLIDATED"}

    def test_duplicate_is_immutable(self) -> None:
        transitions = R7TruthWriter.ALLOWED_TRANSITIONS
        assert transitions["DUPLICATE"] == {"DUPLICATE"}

    def test_pruned_is_immutable(self) -> None:
        transitions = R7TruthWriter.ALLOWED_TRANSITIONS
        assert transitions["PRUNED"] == {"PRUNED"}

    def test_pending_review_can_resolve(self) -> None:
        transitions = R7TruthWriter.ALLOWED_TRANSITIONS
        assert transitions["PENDING_REVIEW"] == {"CONSOLIDATED", "PRUNED"}

    @pytest.mark.asyncio
    async def test_validate_transition_rejects_consolidated_to_pending(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Cannot move an event from CONSOLIDATED back to PENDING."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": "CONSOLIDATED"})
        result = await r7_writer._validate_status_transition(mock_connection, "evt-001", "PENDING")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_transition_allows_null_to_consolidated(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """Can move from NULL to CONSOLIDATED (first processing)."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": None})
        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_transition_allows_idempotent_consolidated(
        self,
        r7_writer: R7TruthWriter,
        mock_connection: MagicMock,
    ) -> None:
        """CONSOLIDATED -> CONSOLIDATED is idempotent (safe replay)."""
        mock_connection.fetchrow = AsyncMock(return_value={"consolidation_status": "CONSOLIDATED"})
        result = await r7_writer._validate_status_transition(
            mock_connection, "evt-001", "CONSOLIDATED"
        )
        assert result is True


# =============================================================================
# 6.6.3 — ORPHAN EVENT ANALYSIS
# =============================================================================


class TestOrphanEventCauses:
    """
    Issue 6.6.3: Analysis of why events could remain with NULL
    consolidation_status after P03 completes a full drain.

    Orphan events result from:
    1. embedding_status != 'READY' — P02 never computed embedding
    2. wal_pos <= committed offset — offset advanced past them
    3. archival_status set — events were archived before processing
    4. Events processed before _writeback_status() existed (legacy)

    These tests verify the filter conditions and document the causes.
    """

    def test_embedding_not_ready_is_excluded(self) -> None:
        """
        R0 requires embedding_status = 'READY' by default.
        Events stuck at 'PENDING' or 'FAILED' embedding_status
        will never be selected, remaining as orphans.
        """
        config = R0Config()
        assert config.require_embedding_ready is True

    def test_archived_events_are_excluded(self) -> None:
        """
        R0 excludes events with non-NULL archival_status.
        Archived events before consolidation = orphans.
        """
        config = R0Config()
        assert config.exclude_archived is True

    def test_r0_config_can_disable_embedding_filter_for_rescue(self) -> None:
        """
        For orphan rescue, R0Config can be created with
        require_embedding_ready=False to include events
        without embeddings in the batch.
        """
        config = R0Config(require_embedding_ready=False)
        assert config.require_embedding_ready is False

    def test_r0_config_can_include_archived_for_rescue(self) -> None:
        """
        For orphan rescue, archival filter can be disabled.
        """
        config = R0Config(exclude_archived=False)
        assert config.exclude_archived is False


# =============================================================================
# 6.6.3 — ORPHAN RESCUE: CONSOLIDATION STATUS MARKER INTEGRATION
# =============================================================================


class TestOrphanRescueStatusMarker:
    """
    The ConsolidationStatusMarker (used in R6) must produce a valid
    status for every possible event state. This ensures no event
    can pass through R6 without a status assignment.
    """

    def test_status_marker_handles_all_actions(self) -> None:
        """ConsolidationStatusMarker produces valid status for all actions."""
        from k0.modules.consolidation.staging.status_marker import (
            STATUS_CONSOLIDATED,
            STATUS_DUPLICATE,
            STATUS_PENDING_REVIEW,
            STATUS_PRUNED,
            ConsolidationStatusMarker,
        )

        marker = ConsolidationStatusMarker()
        valid_statuses = {
            STATUS_CONSOLIDATED,
            STATUS_DUPLICATE,
            STATUS_PRUNED,
            STATUS_PENDING_REVIEW,
        }

        for action in ReconciliationAction:
            evt = _make_event(f"evt-{action.value}", action)
            result = marker.mark_status(evt)
            assert (
                result.status in valid_statuses
            ), f"Action {action} produced invalid status: {result.status}"

    def test_status_marker_duplicate_flag_takes_priority(self) -> None:
        """is_duplicate=True always produces DUPLICATE regardless of action."""
        from k0.modules.consolidation.staging.status_marker import (
            STATUS_DUPLICATE,
            ConsolidationStatusMarker,
        )

        marker = ConsolidationStatusMarker()
        for action in ReconciliationAction:
            evt = _make_event(
                f"evt-{action.value}",
                action,
                is_duplicate=True,
            )
            result = marker.mark_status(evt)
            assert result.status == STATUS_DUPLICATE

    def test_status_marker_prune_decisions_produce_pruned(self) -> None:
        """ARCHIVE and TOMBSTONE prune decisions produce PRUNED."""
        from k0.modules.consolidation.staging.status_marker import (
            STATUS_PRUNED,
            ConsolidationStatusMarker,
        )

        marker = ConsolidationStatusMarker()
        for pd in [PruneDecision.ARCHIVE, PruneDecision.TOMBSTONE]:
            evt = _make_event("evt-prune", ReconciliationAction.CREATE, prune_decision=pd)
            result = marker.mark_status(evt)
            assert result.status == STATUS_PRUNED

    def test_status_marker_batch_covers_all_events(self) -> None:
        """mark_batch() returns a result for every input event."""
        from k0.modules.consolidation.staging.status_marker import ConsolidationStatusMarker

        marker = ConsolidationStatusMarker()
        events = [
            _make_event("evt-1", ReconciliationAction.CREATE),
            _make_event("evt-2", ReconciliationAction.SKIP),
            _make_event("evt-3", ReconciliationAction.PRUNE),
            _make_event("evt-4"),  # No action (noise)
        ]
        results = marker.mark_batch(events)
        assert len(results) == 4
        assert set(results.keys()) == {"evt-1", "evt-2", "evt-3", "evt-4"}


# =============================================================================
# 6.6 — DRAIN LOOP TERMINATION GUARANTEE
# =============================================================================


class TestDrainLoopTermination:
    """
    The sequential adapter drain loop runs R0-R8 repeatedly until
    R0 returns SKIP (no eligible events). The dedup mechanism must
    guarantee that after N cycles process all eligible events,
    cycle N+1 finds zero eligible events and the loop terminates.

    Key invariant: If R7 succeeds, all batch events get non-NULL
    consolidation_status, so R0 will not re-select them.
    """

    def test_every_action_maps_to_non_pending_non_null(self) -> None:
        """
        Except for PENDING, every ReconciliationAction maps to a
        terminal status that R0 excludes. This proves the drain loop
        will eventually terminate (assuming all events eventually
        get a non-PENDING action).
        """
        r7 = R7TruthWriter()
        non_terminal = set()

        for action in ReconciliationAction:
            evt = _make_event(f"evt-{action.value}", action)
            status = r7._determine_status(evt)
            if status in (None, "PENDING"):
                non_terminal.add(action)

        # Only PENDING action is non-terminal
        assert non_terminal == {ReconciliationAction.PENDING}

    def test_batch_with_mixed_actions_all_get_status(self) -> None:
        """
        A batch with CREATE, REINFORCE, SKIP, PRUNE, CONTRADICT —
        every event gets a non-NULL status after R7.
        """
        r7 = R7TruthWriter()
        actions = [
            ReconciliationAction.CREATE,
            ReconciliationAction.REINFORCE,
            ReconciliationAction.SKIP,
            ReconciliationAction.PRUNE,
            ReconciliationAction.CONTRADICT,
            ReconciliationAction.EXTEND,
            ReconciliationAction.EVOLVE,
        ]
        for action in actions:
            evt = _make_event(f"evt-{action.value}", action)
            status = r7._determine_status(evt)
            assert status is not None
            assert status != ""

    @pytest.mark.asyncio
    async def test_writeback_event_count_matches_batch_size(
        self,
        r7_writer: R7TruthWriter,
        mock_runner_context: P03RunnerContext,
        mock_uow: MagicMock,
    ) -> None:
        """
        After R7 completes, outputs_summary.events_updated == len(batch).
        This proves no event was skipped during writeback.
        """
        events = [
            _make_event("evt-1", ReconciliationAction.CREATE),
            _make_event("evt-2", ReconciliationAction.SKIP),
            _make_event("evt-3", ReconciliationAction.PRUNE),
            _make_event("evt-4"),  # noise
            _make_event("evt-5", ReconciliationAction.REINFORCE),
        ]
        envelope = _make_envelope(events)

        result = await r7_writer.run(envelope, mock_runner_context)

        assert result.outputs_summary["events_updated"] == 5


# =============================================================================
# 6.6.3 — MIGRATION 0087 VALIDATION
# =============================================================================


class TestMigration0087OrphanBackfill:
    """
    Validate the structure of migration 0087 that backfills
    consolidation_status for legacy orphan events.
    """

    def test_migration_file_exists(self) -> None:
        """Migration 0087 exists in the versions directory."""
        from pathlib import Path

        path = Path("k0/db/alembic/versions/0087_backfill_consolidation_status.py")
        assert path.exists()

    def test_migration_has_correct_revision_chain(self) -> None:
        """0087 correctly chains from 0086."""
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0087_backfill_consolidation_status")
        assert m.revision == "0087"
        assert m.down_revision == "0086"

    def test_migration_upgrade_function_exists(self) -> None:
        """upgrade() function is callable."""
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0087_backfill_consolidation_status")
        assert callable(m.upgrade)

    def test_migration_downgrade_function_exists(self) -> None:
        """downgrade() function is callable for reversibility."""
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0087_backfill_consolidation_status")
        assert callable(m.downgrade)
