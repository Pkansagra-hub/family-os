"""
P03 Sequential Runner Tests.

Issue 1.2.3: Sequential runner core tests

Test Categories:
1. Phase Registration - Verify phase registration and lookup
2. Basic Execution - Run phases in order R0→R8
3. Skip Transitions - Test R2→R6 and R5→R6 skip paths
4. Phase Failure - Test failure handling and DLQ
5. Resume Support - Test resume from checkpoint
6. Timeline Recording - Test phase timeline for metrics
7. Callback Hooks - Test phase start/complete callbacks
8. Transition Validation - Test valid_transition checks
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03 import (
    P03BatchEnvelope,
    P03CycleContext,
    P03PhaseBase,
    P03PhaseId,
    P03PhaseProtocol,
    P03PhaseResult,
    P03PhaseStatus,
    P03RunnerContext,
    P03SequentialRunner,
    PhaseNotRegisteredError,
    PhaseTimelineEntry,
    create_runner,
    is_valid_transition,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create a sample cycle context."""
    return P03CycleContext.create(
        tenant_id="tenant-1",
        space_id="space-1",
        event_ids=["evt-1", "evt-2", "evt-3"],
        trigger_type="MANUAL",
        trigger_reason="Test run",
    )


@pytest.fixture
def sample_envelope(sample_context: P03CycleContext) -> P03BatchEnvelope:
    """Create a sample batch envelope."""
    return P03BatchEnvelope.create(sample_context)


@pytest.fixture
def mock_syscalls() -> MagicMock:
    """Create mock syscalls."""
    return MagicMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create mock logger."""
    return MagicMock()


@pytest.fixture
def sample_runner_context(mock_syscalls: MagicMock, mock_logger: MagicMock) -> P03RunnerContext:
    """Create a sample runner context."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=mock_logger,
        qos_band="GREEN",
        priority=50,
        config={"backlog_threshold": 1000},
    )


# =============================================================================
# STUB PHASE IMPLEMENTATIONS FOR TESTING
# =============================================================================


class StubPhase(P03PhaseBase):
    """Stub phase implementation for testing."""

    def __init__(
        self,
        phase_id: P03PhaseId,
        should_skip: bool = False,
        skip_reason: str = "",
        should_fail: bool = False,
        fail_error_type: str = "TestError",
        outputs: Optional[Dict[str, Any]] = None,
        execution_time_ms: int = 10,
    ):
        self._phase_id = phase_id
        self._should_skip = should_skip
        self._skip_reason = skip_reason
        self._should_fail = should_fail
        self._fail_error_type = fail_error_type
        self._outputs = outputs or {"processed": True}
        self._execution_time_ms = execution_time_ms
        self.run_count = 0

    @property
    def phase_id(self) -> P03PhaseId:
        return self._phase_id

    async def _execute(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> Dict[str, Any]:
        self.run_count += 1

        if self._should_fail:
            raise RuntimeError(f"Simulated {self._fail_error_type} failure")

        # Simulate execution time
        await asyncio.sleep(self._execution_time_ms / 1000)

        return self._outputs

    def should_skip(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> Tuple[bool, str]:
        if self._should_skip:
            return (True, self._skip_reason)
        return (False, "")


def create_stub_phases(
    phases_to_stub: Optional[list] = None,
    skip_phases: Optional[Dict[P03PhaseId, str]] = None,
    fail_phases: Optional[Dict[P03PhaseId, str]] = None,
) -> Dict[P03PhaseId, P03PhaseProtocol]:
    """
    Create stub phases for testing.

    Args:
        phases_to_stub: List of phase IDs to create stubs for. Defaults to all.
        skip_phases: Dict of phase_id -> skip_reason for phases that should skip.
        fail_phases: Dict of phase_id -> error_type for phases that should fail.

    Returns:
        Dict mapping phase IDs to stub implementations.
    """
    if phases_to_stub is None:
        phases_to_stub = list(P03PhaseId.execution_order())

    skip_phases = skip_phases or {}
    fail_phases = fail_phases or {}

    result = {}
    for phase_id in phases_to_stub:
        should_skip = phase_id in skip_phases
        skip_reason = skip_phases.get(phase_id, "")
        should_fail = phase_id in fail_phases
        fail_error_type = fail_phases.get(phase_id, "TestError")

        result[phase_id] = StubPhase(
            phase_id=phase_id,
            should_skip=should_skip,
            skip_reason=skip_reason,
            should_fail=should_fail,
            fail_error_type=fail_error_type,
        )

    return result


# =============================================================================
# 1. PHASE REGISTRATION TESTS
# =============================================================================


class TestPhaseRegistration:
    """Test phase registration and lookup."""

    def test_runner_with_empty_phases(self) -> None:
        """Runner can be created with empty phases dict."""
        runner = P03SequentialRunner(phases={})
        assert runner.registered_phases == []

    def test_runner_registers_phases(self) -> None:
        """Runner should track registered phases."""
        phases = create_stub_phases([P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE])
        runner = P03SequentialRunner(phases=phases)

        assert len(runner.registered_phases) == 2
        assert P03PhaseId.R0_INIT in runner.registered_phases
        assert P03PhaseId.R1_SCORE in runner.registered_phases

    def test_has_phase(self) -> None:
        """has_phase should return True for registered phases."""
        phases = create_stub_phases([P03PhaseId.R0_INIT])
        runner = P03SequentialRunner(phases=phases)

        assert runner.has_phase(P03PhaseId.R0_INIT) is True
        assert runner.has_phase(P03PhaseId.R1_SCORE) is False

    def test_create_runner_factory(self) -> None:
        """create_runner factory should work."""
        phases = create_stub_phases([P03PhaseId.R0_INIT])
        runner = create_runner(phases)

        assert isinstance(runner, P03SequentialRunner)
        assert runner.has_phase(P03PhaseId.R0_INIT)


# =============================================================================
# 2. BASIC EXECUTION TESTS
# =============================================================================


class TestBasicExecution:
    """Test basic phase execution in order."""

    @pytest.mark.asyncio
    async def test_run_single_phase(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Should execute a single registered phase."""
        phases = create_stub_phases([P03PhaseId.R0_INIT])
        # Only R0 registered, so run will fail on R1
        runner = P03SequentialRunner(phases=phases)

        with pytest.raises(PhaseNotRegisteredError) as exc_info:
            await runner.run(sample_envelope, sample_runner_context)

        assert exc_info.value.phase_id == P03PhaseId.R1_SCORE

    @pytest.mark.asyncio
    async def test_run_all_phases(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Should execute all phases in order R0→R8."""
        phases = create_stub_phases()  # All phases
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        assert result.is_success
        assert result.status == P03PhaseStatus.DONE
        assert len(result.phase_results) == 9  # R0-R8
        assert result.final_phase == P03PhaseId.R8_EMIT

        # Verify all phases executed
        for phase_id in P03PhaseId.execution_order():
            assert phase_id in result.phase_results
            phase_result = result.phase_results[phase_id]
            assert phase_result.status == P03PhaseStatus.DONE

    @pytest.mark.asyncio
    async def test_phase_execution_order(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Phases should execute in correct order."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)
        execution_order: list = []

        def track_start(env: P03BatchEnvelope, phase_id: P03PhaseId, ctx: P03RunnerContext) -> None:
            execution_order.append(phase_id)

        runner._on_phase_start = track_start

        await runner.run(sample_envelope, sample_runner_context)

        expected_order = list(P03PhaseId.execution_order())
        assert execution_order == expected_order

    @pytest.mark.asyncio
    async def test_envelope_updated_during_execution(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Envelope should be updated with phase statuses."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        await runner.run(sample_envelope, sample_runner_context)

        # All phases should be marked DONE
        for phase_id in P03PhaseId.execution_order():
            assert sample_envelope.get_phase_status(phase_id) == P03PhaseStatus.DONE


# =============================================================================
# 3. SKIP TRANSITION TESTS
# =============================================================================


class TestSkipTransitions:
    """Test skip transition logic."""

    @pytest.mark.asyncio
    async def test_r2_skip_to_r6(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """R2 skip should jump to R6, skipping R3-R5."""
        phases = create_stub_phases(skip_phases={P03PhaseId.R2_CLUSTER: "batch_size < 2"})
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        # R0, R1 should be DONE
        assert result.phase_results[P03PhaseId.R0_INIT].status == P03PhaseStatus.DONE
        assert result.phase_results[P03PhaseId.R1_SCORE].status == P03PhaseStatus.DONE

        # R2 should be SKIP
        assert result.phase_results[P03PhaseId.R2_CLUSTER].status == P03PhaseStatus.SKIP
        assert result.phase_results[P03PhaseId.R2_CLUSTER].skip_reason == "batch_size < 2"

        # R3, R4, R5 should be SKIP (cascaded from R2)
        assert result.phase_results[P03PhaseId.R3_PRUNE].status == P03PhaseStatus.SKIP
        assert result.phase_results[P03PhaseId.R4_KG].status == P03PhaseStatus.SKIP
        assert result.phase_results[P03PhaseId.R5_DREAM].status == P03PhaseStatus.SKIP

        # R6, R7, R8 should be DONE
        assert result.phase_results[P03PhaseId.R6_STAGE].status == P03PhaseStatus.DONE
        assert result.phase_results[P03PhaseId.R7_WRITE].status == P03PhaseStatus.DONE
        assert result.phase_results[P03PhaseId.R8_EMIT].status == P03PhaseStatus.DONE

    @pytest.mark.asyncio
    async def test_r5_skip(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """R5 skip should proceed to R6."""
        phases = create_stub_phases(skip_phases={P03PhaseId.R5_DREAM: "backlog_threshold exceeded"})
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        # R0-R4 should be DONE
        assert result.phase_results[P03PhaseId.R4_KG].status == P03PhaseStatus.DONE

        # R5 should be SKIP
        assert result.phase_results[P03PhaseId.R5_DREAM].status == P03PhaseStatus.SKIP

        # R6-R8 should be DONE
        assert result.phase_results[P03PhaseId.R6_STAGE].status == P03PhaseStatus.DONE
        assert result.is_success


# =============================================================================
# 4. PHASE FAILURE TESTS
# =============================================================================


class TestPhaseFailure:
    """Test phase failure handling."""

    @pytest.mark.asyncio
    async def test_phase_failure_stops_execution(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Failed phase should stop cycle execution."""
        phases = create_stub_phases(fail_phases={P03PhaseId.R2_CLUSTER: "CLUSTER_TIMEOUT"})
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        assert result.is_failed
        assert result.status == P03PhaseStatus.FAIL
        assert result.final_phase == P03PhaseId.R2_CLUSTER
        assert "R2" in (result.dlq_reason or "")

        # R0, R1 should be DONE
        assert result.phase_results[P03PhaseId.R0_INIT].status == P03PhaseStatus.DONE
        assert result.phase_results[P03PhaseId.R1_SCORE].status == P03PhaseStatus.DONE

        # R2 should be FAIL
        assert result.phase_results[P03PhaseId.R2_CLUSTER].status == P03PhaseStatus.FAIL

        # R3+ should not exist in results
        assert P03PhaseId.R3_PRUNE not in result.phase_results

    @pytest.mark.asyncio
    async def test_failed_phase_has_error_info(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Failed phase result should include error info."""
        phases = create_stub_phases(fail_phases={P03PhaseId.R1_SCORE: "P08_UNAVAILABLE"})
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        r1_result = result.phase_results[P03PhaseId.R1_SCORE]
        assert r1_result.is_failed
        assert r1_result.error_info is not None
        assert r1_result.error_info.error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_envelope_marked_on_failure(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Envelope should be marked with failure status."""
        phases = create_stub_phases(fail_phases={P03PhaseId.R3_PRUNE: "SIMHASH_ERROR"})
        runner = P03SequentialRunner(phases=phases)

        await runner.run(sample_envelope, sample_runner_context)

        assert sample_envelope.get_phase_status(P03PhaseId.R3_PRUNE) == P03PhaseStatus.FAIL
        assert len(sample_envelope.observability.errors) > 0


# =============================================================================
# 5. RESUME SUPPORT TESTS
# =============================================================================


class TestResumeSupport:
    """Test resume from checkpoint functionality."""

    @pytest.mark.asyncio
    async def test_run_from_specific_phase(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Should start execution from specified phase."""
        # Pre-populate required state for R3 resume
        sample_envelope.context  # Has event_ids and batch_id

        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)
        execution_order: list = []

        def track_start(env: P03BatchEnvelope, phase_id: P03PhaseId, ctx: P03RunnerContext) -> None:
            execution_order.append(phase_id)

        runner._on_phase_start = track_start

        result = await runner.run_from(
            sample_envelope, sample_runner_context, start_phase=P03PhaseId.R3_PRUNE
        )

        # Should start from R3
        assert execution_order[0] == P03PhaseId.R3_PRUNE
        assert P03PhaseId.R0_INIT not in execution_order
        assert P03PhaseId.R1_SCORE not in execution_order
        assert P03PhaseId.R2_CLUSTER not in execution_order

        # Should complete successfully
        assert result.is_success

    @pytest.mark.asyncio
    async def test_get_resume_phase_for_r7(self) -> None:
        """R7 failure should resume from R6 per RESUME_MATRIX."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        resume_from = runner.get_resume_phase(P03PhaseId.R7_WRITE)

        # R7 resume requires re-staging
        assert resume_from == P03PhaseId.R6_STAGE


# =============================================================================
# 6. TIMELINE RECORDING TESTS
# =============================================================================


class TestTimelineRecording:
    """Test phase timeline recording for metrics."""

    @pytest.mark.asyncio
    async def test_timeline_records_all_phases(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Timeline should record entry for each phase."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        await runner.run(sample_envelope, sample_runner_context)

        timeline = runner.get_timeline()
        assert len(timeline) == 9  # R0-R8

    @pytest.mark.asyncio
    async def test_timeline_entry_fields(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Timeline entries should have expected fields."""
        phases = create_stub_phases([P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE])
        # Will fail on R2 since not registered
        runner = P03SequentialRunner(phases=phases)

        with pytest.raises(PhaseNotRegisteredError):
            await runner.run(sample_envelope, sample_runner_context)

        timeline = runner.get_timeline()
        assert len(timeline) >= 2

        entry = timeline[0]
        assert isinstance(entry, PhaseTimelineEntry)
        assert entry.phase_id == P03PhaseId.R0_INIT
        assert entry.status == P03PhaseStatus.DONE
        assert entry.start_ts > 0
        assert entry.end_ts >= entry.start_ts
        assert entry.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_timeline_cleared_on_new_run(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Timeline should be cleared on each run."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        await runner.run(sample_envelope, sample_runner_context)
        first_timeline_len = len(runner.get_timeline())

        # Create fresh envelope for second run
        ctx2 = P03CycleContext.create(
            tenant_id="t2",
            space_id="s2",
            event_ids=["evt-x"],
        )
        env2 = P03BatchEnvelope.create(ctx2)

        await runner.run(env2, sample_runner_context)
        second_timeline_len = len(runner.get_timeline())

        # Should be same length (not accumulated)
        assert first_timeline_len == second_timeline_len

    @pytest.mark.asyncio
    async def test_timeline_to_dict(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Timeline entry to_dict should be serializable."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        await runner.run(sample_envelope, sample_runner_context)

        timeline = runner.get_timeline()
        entry_dict = timeline[0].to_dict()

        assert "phase_id" in entry_dict
        assert "status" in entry_dict
        assert "start_ts" in entry_dict
        assert "duration_ms" in entry_dict


# =============================================================================
# 7. CALLBACK HOOKS TESTS
# =============================================================================


class TestCallbackHooks:
    """Test phase start/complete callbacks."""

    @pytest.mark.asyncio
    async def test_on_phase_start_called(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """on_phase_start should be called before each phase."""
        phases = create_stub_phases()
        start_calls: list = []

        def on_start(env: P03BatchEnvelope, phase_id: P03PhaseId, ctx: P03RunnerContext) -> None:
            start_calls.append(phase_id)

        runner = create_runner(phases, on_phase_start=on_start)
        await runner.run(sample_envelope, sample_runner_context)

        assert len(start_calls) == 9
        assert start_calls[0] == P03PhaseId.R0_INIT
        assert start_calls[-1] == P03PhaseId.R8_EMIT

    @pytest.mark.asyncio
    async def test_on_phase_complete_called(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """on_phase_complete should be called after each phase."""
        phases = create_stub_phases()
        complete_calls: list = []

        def on_complete(
            env: P03BatchEnvelope,
            phase_id: P03PhaseId,
            result: P03PhaseResult,
            ctx: P03RunnerContext,
        ) -> None:
            complete_calls.append((phase_id, result.status))

        runner = create_runner(phases, on_phase_complete=on_complete)
        await runner.run(sample_envelope, sample_runner_context)

        assert len(complete_calls) == 9
        assert complete_calls[0] == (P03PhaseId.R0_INIT, P03PhaseStatus.DONE)

    @pytest.mark.asyncio
    async def test_on_checkpoint_called(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """on_checkpoint should be called after successful phases."""
        phases = create_stub_phases()
        checkpoint_calls: list = []

        def on_checkpoint(env: P03BatchEnvelope, phase_id: P03PhaseId, data: dict) -> None:
            checkpoint_calls.append(phase_id)

        runner = create_runner(phases, on_checkpoint=on_checkpoint)
        await runner.run(sample_envelope, sample_runner_context)

        # Checkpoints for all 9 phases
        assert len(checkpoint_calls) == 9


# =============================================================================
# 8. TRANSITION VALIDATION TESTS
# =============================================================================


class TestTransitionValidation:
    """Test transition validation logic."""

    def test_valid_normal_transitions(self) -> None:
        """Normal R0→R1→...→R8 transitions should be valid."""
        order = P03PhaseId.execution_order()
        for i in range(len(order) - 1):
            assert is_valid_transition(order[i], order[i + 1])

    def test_invalid_backward_transition(self) -> None:
        """Backward transitions should be invalid."""
        assert is_valid_transition(P03PhaseId.R3_PRUNE, P03PhaseId.R1_SCORE) is False

    def test_valid_skip_transitions(self) -> None:
        """Skip transitions should be valid."""
        # R2 → R6 (skip R3-R5)
        assert is_valid_transition(P03PhaseId.R2_CLUSTER, P03PhaseId.R6_STAGE)
        # R4 → R6 (skip R5)
        assert is_valid_transition(P03PhaseId.R4_KG, P03PhaseId.R6_STAGE)
        # R5 → R6 (skip R5 itself)
        assert is_valid_transition(P03PhaseId.R5_DREAM, P03PhaseId.R6_STAGE)

    def test_validate_phase_order(self) -> None:
        """validate_phase_order should check sequence."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        # Valid order
        valid_order = [P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R2_CLUSTER]
        is_valid, error = runner.validate_phase_order(valid_order)
        assert is_valid
        assert error is None

        # Invalid order (skip without transition)
        invalid_order = [P03PhaseId.R0_INIT, P03PhaseId.R3_PRUNE]
        is_valid, error = runner.validate_phase_order(invalid_order)
        assert not is_valid
        assert "Invalid transition" in (error or "")


# =============================================================================
# 9. EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_missing_phase_raises_error(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Missing phase implementation should raise PhaseNotRegisteredError."""
        # Only register R0
        phases = create_stub_phases([P03PhaseId.R0_INIT])
        runner = P03SequentialRunner(phases=phases)

        with pytest.raises(PhaseNotRegisteredError) as exc_info:
            await runner.run(sample_envelope, sample_runner_context)

        assert exc_info.value.phase_id == P03PhaseId.R1_SCORE

    @pytest.mark.asyncio
    async def test_cycle_result_phases_executed(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """CycleResult should track phases executed vs skipped."""
        phases = create_stub_phases(skip_phases={P03PhaseId.R5_DREAM: "backlog"})
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        assert result.phases_executed == 8  # All except R5
        assert result.phases_skipped == 1  # R5

    @pytest.mark.asyncio
    async def test_empty_timeline_after_clear(self) -> None:
        """clear_timeline should empty the timeline."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        # Manually add entry
        runner._timeline.append(
            PhaseTimelineEntry(
                phase_id=P03PhaseId.R0_INIT,
                status=P03PhaseStatus.DONE,
                start_ts=0,
                end_ts=0,
                duration_ms=0,
            )
        )

        runner.clear_timeline()
        assert len(runner.get_timeline()) == 0

    @pytest.mark.asyncio
    async def test_cycle_result_to_dict(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """CycleResult to_dict should be complete."""
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)
        result_dict = result.to_dict()

        assert "cycle_id" in result_dict
        assert "batch_id" in result_dict
        assert "status" in result_dict
        assert "total_duration_ms" in result_dict
        assert "phase_results" in result_dict
        assert len(result_dict["phase_results"]) == 9


# =============================================================================
# 9. PHASE TRANSITION LOGGING TESTS (Issue 1.2.4)
# =============================================================================


class TestPhaseTransitionLogging:
    """Test structured log emission for phase transitions."""

    @pytest.mark.asyncio
    async def test_transition_logger_records_start_events(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should record phase_start events."""
        from k0.pipelines.p03 import PhaseEventType, PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases, transition_logger=logger)

        await runner.run(sample_envelope, sample_runner_context)

        events = logger.events
        start_events = [e for e in events if e.event_type == PhaseEventType.PHASE_START]

        # Should have one start event per phase (9 phases)
        assert len(start_events) == 9

        # First start should be R0
        assert start_events[0].phase_id == "R0"
        assert start_events[0].status == "PROC"

    @pytest.mark.asyncio
    async def test_transition_logger_records_complete_events(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should record phase_complete events."""
        from k0.pipelines.p03 import PhaseEventType, PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases, transition_logger=logger)

        await runner.run(sample_envelope, sample_runner_context)

        events = logger.events
        complete_events = [e for e in events if e.event_type == PhaseEventType.PHASE_COMPLETE]

        # Should have one complete event per phase
        assert len(complete_events) == 9

        # Complete events should have duration_ms
        for event in complete_events:
            assert event.status == "DONE"
            assert event.duration_ms is not None

    @pytest.mark.asyncio
    async def test_transition_logger_records_skip_events(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should record phase_skip events for skip transitions."""
        from k0.pipelines.p03 import PhaseEventType, PhaseTransitionLogger

        logger = PhaseTransitionLogger()

        # Create phases where R2 skips to R6
        phases = create_stub_phases(skip_phases={P03PhaseId.R2_CLUSTER: "No changes - skip to R6"})

        runner = P03SequentialRunner(phases=phases, transition_logger=logger)
        await runner.run(sample_envelope, sample_runner_context)

        events = logger.events
        skip_events = [e for e in events if e.event_type == PhaseEventType.PHASE_SKIP]

        # R2 skips, and R3, R4, R5 are skipped as intermediate phases
        assert len(skip_events) >= 1

        # Check that skip events have skip_reason
        for event in skip_events:
            assert event.status == "SKIP"
            assert event.skip_reason is not None

    @pytest.mark.asyncio
    async def test_transition_logger_records_fail_events(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should record phase_fail events."""
        from k0.pipelines.p03 import PhaseEventType, PhaseTransitionLogger

        logger = PhaseTransitionLogger()

        # Create phases where R1 fails
        phases = create_stub_phases(fail_phases={P03PhaseId.R1_SCORE: "TestError"})

        runner = P03SequentialRunner(phases=phases, transition_logger=logger)
        await runner.run(sample_envelope, sample_runner_context)

        events = logger.events
        fail_events = [e for e in events if e.event_type == PhaseEventType.PHASE_FAIL]

        assert len(fail_events) == 1
        fail_event = fail_events[0]
        assert fail_event.phase_id == "R1"
        assert fail_event.status == "FAIL"
        assert fail_event.error_type is not None

    @pytest.mark.asyncio
    async def test_transition_event_contains_all_identifiers(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition events should contain cycle_id, batch_id, space_id, tenant_id."""
        from k0.pipelines.p03 import PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases, transition_logger=logger)

        await runner.run(sample_envelope, sample_runner_context)

        events = logger.events
        assert len(events) >= 1

        event = events[0]
        assert event.cycle_id == sample_envelope.context.cycle_id
        assert event.batch_id == sample_envelope.context.batch_id
        assert event.space_id == sample_envelope.context.space_id
        assert event.tenant_id == sample_envelope.context.tenant_id

    @pytest.mark.asyncio
    async def test_transition_event_to_dict(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition event to_dict should be JSON-serializable."""
        import json

        from k0.pipelines.p03 import PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases, transition_logger=logger)

        await runner.run(sample_envelope, sample_runner_context)

        events = logger.events
        for event in events:
            event_dict = event.to_dict()
            # Should be JSON serializable
            json_str = json.dumps(event_dict)
            assert json_str is not None
            assert "event" in event_dict
            assert "pipeline_id" in event_dict
            assert "phase_id" in event_dict

    @pytest.mark.asyncio
    async def test_phase_summary_generation(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should generate phase summary for audit."""
        from k0.pipelines.p03 import PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases, transition_logger=logger)

        await runner.run(sample_envelope, sample_runner_context)

        summary = logger.get_phase_summary()

        assert "phases" in summary
        assert "total_events" in summary
        assert "failed_phases" in summary
        assert "skipped_phases" in summary

        # All 9 phases should be in summary
        assert len(summary["phases"]) == 9
        assert "R0" in summary["phases"]
        assert "R8" in summary["phases"]

    @pytest.mark.asyncio
    async def test_transition_logger_accessible_via_property(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Runner should expose transition_logger property."""
        from k0.pipelines.p03 import PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases, transition_logger=logger)

        # Access via property
        assert runner.transition_logger is logger

    @pytest.mark.asyncio
    async def test_default_logger_created_if_not_provided(
        self,
    ) -> None:
        """Runner should create default logger if none provided."""
        from k0.pipelines.p03 import PhaseTransitionLoggerProtocol

        phases = create_stub_phases()
        runner = P03SequentialRunner(phases=phases)

        # Should have a default logger
        assert runner.transition_logger is not None
        assert isinstance(runner.transition_logger, PhaseTransitionLoggerProtocol)

    @pytest.mark.asyncio
    async def test_create_runner_accepts_transition_logger(self) -> None:
        """create_runner factory should accept transition_logger argument."""
        from k0.pipelines.p03 import PhaseTransitionLogger

        logger = PhaseTransitionLogger()
        phases = create_stub_phases()
        runner = create_runner(phases, transition_logger=logger)

        assert runner.transition_logger is logger
        assert runner.transition_logger is logger
