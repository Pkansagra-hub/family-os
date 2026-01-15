"""
Tests for P03 Offset Manager (Issue 1.2.6)

Tests cover:
- Offset decision logic (COMMIT, CHECKPOINT_ONLY, DLQ, SKIP)
- Idempotency checking
- Standalone offset commit
- UoW offset commit integration
- Helper functions
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03.checkpoint import P03Checkpoint
from k0.pipelines.p03.context import P03CycleContext
from k0.pipelines.p03.envelope import P03BatchEnvelope
from k0.pipelines.p03.offset_manager import (
    InMemoryOffset,
    InMemoryOffsetStore,
    OffsetAction,
    OffsetDecision,
    OffsetIdempotencyError,
    OffsetManagerError,
    OffsetWriteError,
    P03OffsetManager,
    create_offset_from_checkpoint,
    should_advance_offset,
)
from k0.pipelines.p03.phase_interface import P03CycleResult, P03PhaseResult
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create a sample cycle context."""
    return P03CycleContext.create(
        space_id="space-123",
        tenant_id="tenant-456",
        event_ids=["evt-001", "evt-002", "evt-003"],
    )


@pytest.fixture
def sample_envelope(sample_context: P03CycleContext) -> P03BatchEnvelope:
    """Create a sample envelope."""
    envelope = P03BatchEnvelope(context=sample_context)
    return envelope


@pytest.fixture
def sample_wal_pos() -> int:
    """Sample WAL position for testing."""
    return 12345


@pytest.fixture
def successful_cycle_result(sample_envelope: P03BatchEnvelope) -> P03CycleResult:
    """Create a successful cycle result (R8 DONE)."""
    # Build phase results for all phases
    phase_results = {}
    for phase_id in P03PhaseId.execution_order():
        phase_results[phase_id] = P03PhaseResult.done(
            phase_id=phase_id,
            duration_ms=100,
        )

    return P03CycleResult.success(
        cycle_id=sample_envelope.context.cycle_id,
        batch_id=sample_envelope.context.batch_id,
        phase_results=phase_results,
        total_duration_ms=1000,
    )


@pytest.fixture
def failed_resumable_cycle_result(sample_envelope: P03BatchEnvelope) -> P03CycleResult:
    """Create a failed cycle result at resumable phase (R3_PRUNE)."""
    from k0.pipelines.p03.observability import P03Error

    error = P03Error.create(
        phase="R3_PRUNE",
        stage_id="prune_engine",
        error_type="TransientError",
        error_message="Database connection timeout",
    )

    phase_results = {
        P03PhaseId.R0_INIT: P03PhaseResult.done(P03PhaseId.R0_INIT, duration_ms=50),
        P03PhaseId.R1_SCORE: P03PhaseResult.done(P03PhaseId.R1_SCORE, duration_ms=50),
        P03PhaseId.R2_CLUSTER: P03PhaseResult.done(P03PhaseId.R2_CLUSTER, duration_ms=50),
        P03PhaseId.R3_PRUNE: P03PhaseResult.fail(
            phase_id=P03PhaseId.R3_PRUNE,
            error=error,
            duration_ms=100,
        ),
    }

    return P03CycleResult.fail(
        cycle_id=sample_envelope.context.cycle_id,
        batch_id=sample_envelope.context.batch_id,
        phase_results=phase_results,
        total_duration_ms=250,
        failed_phase=P03PhaseId.R3_PRUNE,
        dlq_reason="R3_PRUNE failed: TransientError",
    )


@pytest.fixture
def failed_non_resumable_cycle_result(sample_envelope: P03BatchEnvelope) -> P03CycleResult:
    """Create a failed cycle result at a phase with can_resume=False.

    Note: In the real P03 pipeline, all phases have can_resume=True.
    This fixture tests the DLQ path for when a phase is NOT resumable.
    We use R0_INIT and patch RESUME_MATRIX in the test.
    """
    from k0.pipelines.p03.observability import P03Error

    error = P03Error.create(
        phase="R0_INIT",
        stage_id="validation",
        error_type="ValidationError",
        error_message="Invalid batch",
    )

    phase_results = {
        P03PhaseId.R0_INIT: P03PhaseResult.fail(
            phase_id=P03PhaseId.R0_INIT,
            error=error,
            duration_ms=10,
        ),
    }

    return P03CycleResult.fail(
        cycle_id=sample_envelope.context.cycle_id,
        batch_id=sample_envelope.context.batch_id,
        phase_results=phase_results,
        total_duration_ms=10,
        failed_phase=P03PhaseId.R0_INIT,
        dlq_reason="R0_INIT failed: ValidationError",
    )


@pytest.fixture
def offset_store() -> InMemoryOffsetStore:
    """Create an in-memory offset store."""
    return InMemoryOffsetStore()


@pytest.fixture
def offset_manager(offset_store: InMemoryOffsetStore) -> P03OffsetManager:
    """Create an offset manager with in-memory store."""
    return P03OffsetManager(offset_store=offset_store)


# =============================================================================
# TEST: OFFSET DECISION LOGIC
# =============================================================================


class TestOffsetDecisionLogic:
    """Tests for offset decision logic."""

    def test_successful_cycle_returns_commit_action(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Successful cycle (R8 DONE) should return COMMIT action."""
        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        assert decision.action == OffsetAction.COMMIT
        assert decision.phase_id == P03PhaseId.R8_EMIT
        assert decision.phase_status == P03PhaseStatus.DONE
        assert decision.offset_value == sample_wal_pos
        assert "R8 DONE" in decision.reason

    def test_successful_cycle_with_explicit_wal_pos(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Explicit WAL position should be used in decision."""
        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=99999,
        )

        assert decision.action == OffsetAction.COMMIT
        assert decision.offset_value == 99999

    def test_successful_cycle_without_wal_pos_returns_skip(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_context: P03CycleContext,
    ) -> None:
        """Successful cycle without WAL position should return SKIP."""
        envelope = P03BatchEnvelope(context=sample_context)

        decision = offset_manager.decide_action(
            successful_cycle_result,
            envelope,
            # No last_wal_pos provided
        )

        assert decision.action == OffsetAction.SKIP
        assert "No WAL position" in decision.reason

    def test_failed_resumable_phase_returns_checkpoint_only(
        self,
        offset_manager: P03OffsetManager,
        failed_resumable_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Failed cycle at resumable phase should return CHECKPOINT_ONLY."""
        decision = offset_manager.decide_action(
            failed_resumable_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        assert decision.action == OffsetAction.CHECKPOINT_ONLY
        assert decision.phase_id == P03PhaseId.R3_PRUNE
        assert decision.phase_status == P03PhaseStatus.FAIL
        assert decision.checkpoint is not None
        assert "resumable" in decision.reason.lower()

    def test_checkpoint_only_includes_checkpoint_data(
        self,
        offset_manager: P03OffsetManager,
        failed_resumable_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """CHECKPOINT_ONLY decision should include valid checkpoint."""
        decision = offset_manager.decide_action(
            failed_resumable_cycle_result,
            sample_envelope,
            last_wal_pos=5000,
        )

        checkpoint = decision.checkpoint
        assert checkpoint is not None
        assert checkpoint.cycle_id == failed_resumable_cycle_result.cycle_id
        assert checkpoint.batch_id == failed_resumable_cycle_result.batch_id
        assert checkpoint.phase_id == P03PhaseId.R3_PRUNE
        assert checkpoint.phase_status == P03PhaseStatus.FAIL
        assert checkpoint.last_wal_pos == 5000
        assert checkpoint.space_id == sample_envelope.context.space_id
        assert checkpoint.tenant_id == sample_envelope.context.tenant_id

    def test_failed_non_resumable_phase_returns_dlq(
        self,
        offset_manager: P03OffsetManager,
        failed_non_resumable_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Failed cycle at non-resumable phase should return DLQ.

        Note: All P03 phases are actually resumable (can_resume=True).
        This test patches RESUME_MATRIX to simulate a non-resumable phase.
        """
        from unittest.mock import patch

        from k0.pipelines.p03.runner_contract import ResumePolicy

        # Create a patched RESUME_MATRIX where R0_INIT has can_resume=False
        non_resumable_policy = ResumePolicy(
            phase_id=P03PhaseId.R0_INIT,
            can_resume=False,  # <-- Key: make it non-resumable
            resume_from=P03PhaseId.R0_INIT,
            requires_state=(),
            notes="Test non-resumable case",
        )

        with patch(
            "k0.pipelines.p03.runner_contract.RESUME_MATRIX",
            {P03PhaseId.R0_INIT: non_resumable_policy},
        ):
            decision = offset_manager.decide_action(
                failed_non_resumable_cycle_result,
                sample_envelope,
            )

        assert decision.action == OffsetAction.DLQ
        assert decision.phase_id == P03PhaseId.R0_INIT
        assert decision.phase_status == P03PhaseStatus.FAIL
        assert "non-resumable" in decision.reason.lower()

    def test_decision_to_dict(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Decision should serialize to dict for logging."""
        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        d = decision.to_dict()
        assert d["action"] == "COMMIT"
        assert d["phase_id"] == "R8"  # P03PhaseId.R8_EMIT.value is "R8"
        assert d["phase_status"] == "DONE"
        assert d["offset_value"] == sample_wal_pos


# =============================================================================
# TEST: IDEMPOTENCY
# =============================================================================


class TestIdempotency:
    """Tests for idempotency checking."""

    def test_same_cycle_returns_skip(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Second decision for same cycle should return SKIP."""
        # First call - mark as committed
        offset_manager._committed_cycles[successful_cycle_result.cycle_id] = sample_wal_pos

        # Second call (retry) should detect idempotency
        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        assert decision.action == OffsetAction.SKIP
        assert decision.idempotent is True
        assert decision.offset_value == sample_wal_pos

    def test_is_cycle_committed(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """is_cycle_committed should track committed cycles."""
        assert not offset_manager.is_cycle_committed("cycle-001")

        offset_manager._committed_cycles["cycle-001"] = 100
        assert offset_manager.is_cycle_committed("cycle-001")

    def test_get_committed_offset(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """get_committed_offset should return stored offset."""
        assert offset_manager.get_committed_offset("cycle-001") is None

        offset_manager._committed_cycles["cycle-001"] = 500
        assert offset_manager.get_committed_offset("cycle-001") == 500

    def test_clear_idempotency_cache(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """clear_idempotency_cache should clear all tracked cycles."""
        offset_manager._committed_cycles["cycle-001"] = 100
        offset_manager._committed_cycles["cycle-002"] = 200

        offset_manager.clear_idempotency_cache()

        assert not offset_manager.is_cycle_committed("cycle-001")
        assert not offset_manager.is_cycle_committed("cycle-002")

    def test_idempotency_disabled(
        self,
        offset_store: InMemoryOffsetStore,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """With check_idempotency=False, always return decision."""
        manager = P03OffsetManager(
            offset_store=offset_store,
            check_idempotency=False,
        )

        # Mark as committed
        manager._committed_cycles[successful_cycle_result.cycle_id] = sample_wal_pos

        # Should NOT return SKIP because idempotency is disabled
        decision = manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        assert decision.action == OffsetAction.COMMIT


# =============================================================================
# TEST: STANDALONE OFFSET COMMIT
# =============================================================================


class TestStandaloneOffsetCommit:
    """Tests for standalone (non-UoW) offset commit."""

    @pytest.mark.asyncio
    async def test_commit_offset_success(
        self,
        offset_manager: P03OffsetManager,
        offset_store: InMemoryOffsetStore,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Successful commit should write offset to store."""
        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        result = await offset_manager.commit_offset(decision, sample_envelope)

        assert result is True
        assert offset_store.count == 1

        stored = await offset_store.fetch(
            subscriber_id=offset_manager.subscriber_id,
            topic=offset_manager.topic,
            space_id=sample_envelope.context.space_id,
            tenant_id=sample_envelope.context.tenant_id,
        )
        assert stored is not None
        assert stored.offset == sample_wal_pos

    @pytest.mark.asyncio
    async def test_commit_offset_non_commit_action_returns_false(
        self,
        offset_manager: P03OffsetManager,
        failed_resumable_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Non-COMMIT action should return False without writing."""
        decision = offset_manager.decide_action(
            failed_resumable_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        result = await offset_manager.commit_offset(decision, sample_envelope)

        assert result is False

        assert result is False

    @pytest.mark.asyncio
    async def test_commit_offset_no_store_raises_error(
        self,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Commit without store should raise OffsetWriteError."""
        manager = P03OffsetManager(offset_store=None)

        decision = OffsetDecision(
            action=OffsetAction.COMMIT,
            reason="test",
            offset_value=100,
        )

        with pytest.raises(OffsetWriteError) as exc_info:
            await manager.commit_offset(decision, sample_envelope)

        assert "No offset store configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_offset_no_value_raises_error(
        self,
        offset_manager: P03OffsetManager,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Commit without offset value should raise OffsetWriteError."""
        decision = OffsetDecision(
            action=OffsetAction.COMMIT,
            reason="test",
            offset_value=None,
        )

        with pytest.raises(OffsetWriteError) as exc_info:
            await offset_manager.commit_offset(decision, sample_envelope)

        assert "No offset value" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_offset_existing_higher_offset_skips(
        self,
        offset_manager: P03OffsetManager,
        offset_store: InMemoryOffsetStore,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """If existing offset is >= new offset, should skip."""
        # Pre-populate with higher offset
        existing = InMemoryOffset(
            subscriber_id=offset_manager.subscriber_id,
            topic=offset_manager.topic,
            space_id=sample_envelope.context.space_id,
            tenant_id=sample_envelope.context.tenant_id,
            offset=99999,  # Higher than sample_wal_pos
            updated_ts="2024-01-01T00:00:00Z",
        )
        await offset_store.upsert(existing)

        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        result = await offset_manager.commit_offset(decision, sample_envelope)

        assert result is False
        # Should track the existing offset
        assert offset_manager.get_committed_offset(sample_envelope.context.cycle_id) == 99999

    @pytest.mark.asyncio
    async def test_commit_offset_tracks_idempotency(
        self,
        offset_manager: P03OffsetManager,
        offset_store: InMemoryOffsetStore,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Commit should track cycle for idempotency."""
        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        await offset_manager.commit_offset(decision, sample_envelope)

        assert offset_manager.is_cycle_committed(sample_envelope.context.cycle_id)
        assert (
            offset_manager.get_committed_offset(sample_envelope.context.cycle_id) == sample_wal_pos
        )


# =============================================================================
# TEST: UoW OFFSET COMMIT
# =============================================================================


class TestUoWOffsetCommit:
    """Tests for UnitOfWork offset commit."""

    @pytest.mark.asyncio
    async def test_commit_offset_in_uow_success(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """UoW commit should call upsert_offset on UoW."""
        # Create mock UoW
        mock_uow = MagicMock()
        mock_uow.upsert_offset = AsyncMock()

        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        result = await offset_manager.commit_offset_in_uow(
            decision,
            sample_envelope,
            mock_uow,
        )

        assert result is True
        mock_uow.upsert_offset.assert_called_once()

        # Verify offset record
        call_args = mock_uow.upsert_offset.call_args[0][0]
        assert call_args.subscriber_id == offset_manager.subscriber_id
        assert call_args.topic == offset_manager.topic
        assert call_args.offset == sample_wal_pos

    @pytest.mark.asyncio
    async def test_commit_offset_in_uow_non_commit_returns_false(
        self,
        offset_manager: P03OffsetManager,
        failed_resumable_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """Non-COMMIT action should return False without calling UoW."""
        mock_uow = MagicMock()
        mock_uow.upsert_offset = AsyncMock()

        decision = offset_manager.decide_action(
            failed_resumable_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        result = await offset_manager.commit_offset_in_uow(
            decision,
            sample_envelope,
            mock_uow,
        )

        assert result is False
        mock_uow.upsert_offset.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_offset_in_uow_no_value_raises_error(
        self,
        offset_manager: P03OffsetManager,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """UoW commit without offset value should raise OffsetWriteError."""
        mock_uow = MagicMock()

        decision = OffsetDecision(
            action=OffsetAction.COMMIT,
            reason="test",
            offset_value=None,
        )

        with pytest.raises(OffsetWriteError) as exc_info:
            await offset_manager.commit_offset_in_uow(decision, sample_envelope, mock_uow)

        assert "No offset value" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_offset_in_uow_tracks_idempotency(
        self,
        offset_manager: P03OffsetManager,
        successful_cycle_result: P03CycleResult,
        sample_envelope: P03BatchEnvelope,
        sample_wal_pos: int,
    ) -> None:
        """UoW commit should track cycle for idempotency."""
        mock_uow = MagicMock()
        mock_uow.upsert_offset = AsyncMock()

        decision = offset_manager.decide_action(
            successful_cycle_result,
            sample_envelope,
            last_wal_pos=sample_wal_pos,
        )

        await offset_manager.commit_offset_in_uow(decision, sample_envelope, mock_uow)

        assert offset_manager.is_cycle_committed(sample_envelope.context.cycle_id)


# =============================================================================
# TEST: OFFSET QUERY
# =============================================================================


class TestOffsetQuery:
    """Tests for offset query functionality."""

    @pytest.mark.asyncio
    async def test_get_current_offset_returns_value(
        self,
        offset_manager: P03OffsetManager,
        offset_store: InMemoryOffsetStore,
    ) -> None:
        """get_current_offset should return stored offset."""
        record = InMemoryOffset(
            subscriber_id=offset_manager.subscriber_id,
            topic=offset_manager.topic,
            space_id="space-123",
            tenant_id="tenant-456",
            offset=5000,
            updated_ts="2024-01-01T00:00:00Z",
        )
        await offset_store.upsert(record)

        offset = await offset_manager.get_current_offset("space-123", "tenant-456")

        assert offset == 5000

    @pytest.mark.asyncio
    async def test_get_current_offset_returns_none_if_not_found(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """get_current_offset should return None if not found."""
        offset = await offset_manager.get_current_offset("space-999", "tenant-999")

        assert offset is None

    @pytest.mark.asyncio
    async def test_get_current_offset_no_store_returns_none(
        self,
    ) -> None:
        """get_current_offset without store should return None."""
        manager = P03OffsetManager(offset_store=None)

        offset = await manager.get_current_offset("space-123", "tenant-456")

        assert offset is None


# =============================================================================
# TEST: IN-MEMORY OFFSET STORE
# =============================================================================


class TestInMemoryOffsetStore:
    """Tests for InMemoryOffsetStore."""

    @pytest.mark.asyncio
    async def test_upsert_and_fetch(self) -> None:
        """Should upsert and fetch offset records."""
        store = InMemoryOffsetStore()

        record = InMemoryOffset(
            subscriber_id="P03",
            topic="events",
            space_id="s1",
            tenant_id="t1",
            offset=100,
            updated_ts="2024-01-01T00:00:00Z",
        )
        await store.upsert(record)

        fetched = await store.fetch("P03", "events", "s1", "t1")
        assert fetched is not None
        assert fetched.offset == 100

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self) -> None:
        """Should update existing record on upsert."""
        store = InMemoryOffsetStore()

        record1 = InMemoryOffset(
            subscriber_id="P03",
            topic="events",
            space_id="s1",
            tenant_id="t1",
            offset=100,
            updated_ts="2024-01-01T00:00:00Z",
        )
        await store.upsert(record1)

        record2 = InMemoryOffset(
            subscriber_id="P03",
            topic="events",
            space_id="s1",
            tenant_id="t1",
            offset=200,
            updated_ts="2024-01-02T00:00:00Z",
        )
        await store.upsert(record2)

        assert store.count == 1
        fetched = await store.fetch("P03", "events", "s1", "t1")
        assert fetched is not None
        assert fetched.offset == 200

    @pytest.mark.asyncio
    async def test_fetch_not_found_returns_none(self) -> None:
        """Should return None for non-existent records."""
        store = InMemoryOffsetStore()

        fetched = await store.fetch("P03", "events", "s1", "t1")
        assert fetched is None

    def test_clear(self) -> None:
        """Should clear all records."""
        store = InMemoryOffsetStore()
        store._offsets["key1"] = InMemoryOffset("a", "b", "c", "d", 100, "ts")
        store._offsets["key2"] = InMemoryOffset("e", "f", "g", "h", 200, "ts")

        store.clear()

        assert store.count == 0

    def test_get_all(self) -> None:
        """Should return all records."""
        store = InMemoryOffsetStore()
        offset1 = InMemoryOffset("a", "b", "c", "d", 100, "ts")
        offset2 = InMemoryOffset("e", "f", "g", "h", 200, "ts")
        store._offsets["key1"] = offset1
        store._offsets["key2"] = offset2

        all_offsets = store.get_all()

        assert len(all_offsets) == 2


# =============================================================================
# TEST: HELPER FUNCTIONS
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_should_advance_offset_true_for_success(
        self,
        successful_cycle_result: P03CycleResult,
    ) -> None:
        """should_advance_offset returns True for successful cycle."""
        assert should_advance_offset(successful_cycle_result) is True

    def test_should_advance_offset_false_for_failure(
        self,
        failed_resumable_cycle_result: P03CycleResult,
    ) -> None:
        """should_advance_offset returns False for failed cycle."""
        assert should_advance_offset(failed_resumable_cycle_result) is False

    def test_create_offset_from_checkpoint_with_wal_pos(self) -> None:
        """create_offset_from_checkpoint returns offset when WAL pos exists."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-001",
            batch_id="batch-001",
            space_id="space-123",
            tenant_id="tenant-456",
            phase_id=P03PhaseId.R8_EMIT,
            phase_status=P03PhaseStatus.DONE,
            last_wal_pos=5000,
        )

        offset = create_offset_from_checkpoint(checkpoint)

        assert offset is not None
        assert offset.offset == 5000
        assert offset.space_id == "space-123"
        assert offset.tenant_id == "tenant-456"

    def test_create_offset_from_checkpoint_without_wal_pos(self) -> None:
        """create_offset_from_checkpoint returns None when no WAL pos."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-001",
            batch_id="batch-001",
            space_id="space-123",
            tenant_id="tenant-456",
            phase_id=P03PhaseId.R8_EMIT,
            phase_status=P03PhaseStatus.DONE,
        )

        offset = create_offset_from_checkpoint(checkpoint)

        assert offset is None

    def test_create_offset_from_checkpoint_with_overrides(self) -> None:
        """create_offset_from_checkpoint respects subscriber/topic overrides."""
        checkpoint = P03Checkpoint.create(
            cycle_id="cycle-001",
            batch_id="batch-001",
            space_id="space-123",
            tenant_id="tenant-456",
            phase_id=P03PhaseId.R8_EMIT,
            phase_status=P03PhaseStatus.DONE,
            last_wal_pos=5000,
        )

        offset = create_offset_from_checkpoint(
            checkpoint,
            subscriber_id="CUSTOM_SUB",
            topic="custom_topic",
        )

        assert offset is not None
        assert offset.subscriber_id == "CUSTOM_SUB"
        assert offset.topic == "custom_topic"


# =============================================================================
# TEST: MANAGER STATISTICS
# =============================================================================


class TestManagerStatistics:
    """Tests for manager statistics."""

    def test_get_stats(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """get_stats should return manager statistics."""
        offset_manager._committed_cycles["c1"] = 100
        offset_manager._committed_cycles["c2"] = 200

        stats = offset_manager.get_stats()

        assert stats["subscriber_id"] == "P03_CONSOLIDATE"
        assert stats["topic"] == "st_hipp_events"
        assert stats["check_idempotency"] is True
        assert stats["committed_cycles_count"] == 2

    def test_subscriber_id_property(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """subscriber_id property should return configured value."""
        assert offset_manager.subscriber_id == "P03_CONSOLIDATE"

    def test_topic_property(
        self,
        offset_manager: P03OffsetManager,
    ) -> None:
        """topic property should return configured value."""
        assert offset_manager.topic == "st_hipp_events"

    def test_custom_subscriber_and_topic(self) -> None:
        """Should accept custom subscriber_id and topic."""
        manager = P03OffsetManager(
            subscriber_id="CUSTOM_P03",
            topic="custom_events",
        )

        assert manager.subscriber_id == "CUSTOM_P03"
        assert manager.topic == "custom_events"


# =============================================================================
# TEST: ERROR CLASSES
# =============================================================================


class TestErrorClasses:
    """Tests for error classes."""

    def test_offset_manager_error(self) -> None:
        """OffsetManagerError is base error."""
        err = OffsetManagerError("test error")
        assert str(err) == "test error"

    def test_offset_write_error_without_cycle(self) -> None:
        """OffsetWriteError without cycle_id."""
        err = OffsetWriteError("connection failed")
        assert "connection failed" in str(err)
        assert err.reason == "connection failed"
        assert err.cycle_id is None

    def test_offset_write_error_with_cycle(self) -> None:
        """OffsetWriteError with cycle_id."""
        err = OffsetWriteError("timeout", cycle_id="cycle-001")
        assert "cycle-001" in str(err)
        assert "timeout" in str(err)
        assert err.cycle_id == "cycle-001"

    def test_offset_idempotency_error(self) -> None:
        """OffsetIdempotencyError stores cycle and offset."""
        err = OffsetIdempotencyError("cycle-001", 5000)
        assert err.cycle_id == "cycle-001"
        assert err.existing_offset == 5000
        assert "cycle-001" in str(err)
        assert "5000" in str(err)
        assert "5000" in str(err)
