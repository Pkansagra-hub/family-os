"""
M5 TruthWriter Epic Integration Tests — Issue 5.2.W5

Full R0→R8 integration tests focusing on M5 wiring:
- R6 retry logic on VERSION_CONFLICT
- Full pipeline flow R0→R8
- Phase result propagation

References:
- Spec: docs/TEMP_EXECUTION_DOCS/M5_EXECUTION.md Issue 5.2.W5
- Sequential Runner: k0/pipelines/p03/sequential_runner.py
- R6 Retry: Issue 5.2.W6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.context import P03CycleContext
from k0.pipelines.p03.envelope import P03BatchEnvelope
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult, P03RunnerContext
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus
from k0.pipelines.p03.sequential_runner import P03SequentialRunner

# =============================================================================
# MOCK SYSCALLS
# =============================================================================


@dataclass
class MockSyscalls:
    """Mock syscalls for M5 integration testing."""

    async def get_event_versions(self, event_ids: List[str]) -> Dict[str, int]:
        return {eid: 1 for eid in event_ids}

    async def check_existing_staged(
        self, batch_id: str, event_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        return None


# =============================================================================
# MOCK PHASES
# =============================================================================


class MockPhase:
    """Generic mock phase for R0-R5."""

    def __init__(self, phase_id: P03PhaseId):
        self.phase_id = phase_id
        self.call_count = 0

    async def run(self, envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult:
        self.call_count += 1
        return P03PhaseResult.done(
            phase_id=self.phase_id,
            outputs_summary={"mock": True},
            duration_ms=1,
        )


class MockR6Phase:
    """Mock R6 phase that can fail with version conflicts."""

    def __init__(self, conflict_until: int = 0):
        """
        Args:
            conflict_until: Fail with version conflict this many times before succeeding.
        """
        self.conflict_until = conflict_until
        self.call_count = 0

    async def run(self, envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult:
        self.call_count += 1

        if self.call_count <= self.conflict_until:
            return P03PhaseResult.fail(
                phase_id=P03PhaseId.R6_STAGE,
                error=P03Error.create(
                    phase="R6_STAGE",
                    stage_id="staging",
                    error_type="VERSION_CONFLICT",
                    error_message="version conflict detected",
                    recoverable=True,
                ),
                duration_ms=5,
                retry_count=self.call_count - 1,
            )

        # Mark R6 as complete with output summary
        return P03PhaseResult.done(
            phase_id=P03PhaseId.R6_STAGE,
            outputs_summary={
                "total_staged": len(envelope.context.event_ids),
                "layers": ["st_epi", "st_sem"],
            },
            duration_ms=10,
        )


class MockR7Phase:
    """Mock R7 phase."""

    def __init__(self, success: bool = True):
        self.success = success
        self.call_count = 0

    async def run(self, envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult:
        self.call_count += 1

        if not self.success:
            return P03PhaseResult.fail(
                phase_id=P03PhaseId.R7_WRITE,
                error=P03Error.create(
                    phase="R7_WRITE",
                    stage_id="writing",
                    error_type="WRITE_ERROR",
                    error_message="failed to write",
                    recoverable=False,
                ),
                duration_ms=5,
            )

        return P03PhaseResult.done(
            phase_id=P03PhaseId.R7_WRITE,
            outputs_summary={
                "total_succeeded": 5,
                "total_failed": 0,
            },
            duration_ms=15,
        )


class MockR8Phase:
    """Mock R8 phase."""

    def __init__(self):
        self.call_count = 0

    async def run(self, envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult:
        self.call_count += 1

        return P03PhaseResult.done(
            phase_id=P03PhaseId.R8_EMIT,
            outputs_summary={
                "events_emitted": 1,
                "gaps_emitted": 0,
            },
            duration_ms=5,
        )


# =============================================================================
# TEST FIXTURES
# =============================================================================


def create_test_envelope(event_count: int = 100) -> P03BatchEnvelope:
    """Create envelope with specified event count."""
    event_ids = [f"evt-{i:04d}" for i in range(event_count)]
    ctx = P03CycleContext.create(
        tenant_id="test-tenant",
        space_id="test-space",
        event_ids=event_ids,
        trigger_type="MANUAL",
        trigger_reason="integration-test",
    )
    return P03BatchEnvelope.create(context=ctx)


def create_test_context() -> P03RunnerContext:
    """Create runner context for testing."""
    return P03RunnerContext.create(
        syscalls=MockSyscalls(),
        logger=MagicMock(),
        config={},
        checkpoint_enabled=False,
    )


def create_full_runner(
    r6_conflict_until: int = 0,
    r7_success: bool = True,
) -> tuple[P03SequentialRunner, MockR6Phase, MockR7Phase, MockR8Phase]:
    """Create runner with all phases and return phase references."""
    r6_phase = MockR6Phase(conflict_until=r6_conflict_until)
    r7_phase = MockR7Phase(success=r7_success)
    r8_phase = MockR8Phase()

    phases = {
        P03PhaseId.R0_INIT: MockPhase(P03PhaseId.R0_INIT),
        P03PhaseId.R1_SCORE: MockPhase(P03PhaseId.R1_SCORE),
        P03PhaseId.R2_CLUSTER: MockPhase(P03PhaseId.R2_CLUSTER),
        P03PhaseId.R3_PRUNE: MockPhase(P03PhaseId.R3_PRUNE),
        P03PhaseId.R4_KG: MockPhase(P03PhaseId.R4_KG),
        P03PhaseId.R5_DREAM: MockPhase(P03PhaseId.R5_DREAM),
        P03PhaseId.R6_STAGE: r6_phase,
        P03PhaseId.R7_WRITE: r7_phase,
        P03PhaseId.R8_EMIT: r8_phase,
    }

    runner = P03SequentialRunner(phases=phases)
    return runner, r6_phase, r7_phase, r8_phase


# =============================================================================
# M5 INTEGRATION TESTS
# =============================================================================


class TestM5FullPipelineFlow:
    """Tests for M5 full R0->R8 pipeline flow."""

    @pytest.mark.asyncio
    async def test_full_pipeline_happy_path(self):
        """Test complete R0->R8 flow succeeds."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope(event_count=50)
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # Full pipeline should succeed
        assert result.is_success

        # All 9 phases should have run
        assert len(result.phase_results) == 9

        # Each phase completed successfully
        for phase_id, phase_result in result.phase_results.items():
            assert phase_result.status == P03PhaseStatus.DONE, f"{phase_id} not DONE"

    @pytest.mark.asyncio
    async def test_r6_output_summary_captured(self):
        """Test that R6 output summary is captured in results."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope(event_count=75)
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # R6 outputs captured
        r6_result = result.phase_results[P03PhaseId.R6_STAGE]
        assert "total_staged" in r6_result.outputs_summary
        assert r6_result.outputs_summary["total_staged"] == 75

    @pytest.mark.asyncio
    async def test_r7_output_summary_captured(self):
        """Test that R7 output summary is captured in results."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # R7 outputs captured
        r7_result = result.phase_results[P03PhaseId.R7_WRITE]
        assert "total_succeeded" in r7_result.outputs_summary
        assert "total_failed" in r7_result.outputs_summary

    @pytest.mark.asyncio
    async def test_r8_output_summary_captured(self):
        """Test that R8 output summary is captured in results."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # R8 outputs captured
        r8_result = result.phase_results[P03PhaseId.R8_EMIT]
        assert "events_emitted" in r8_result.outputs_summary


class TestM5R6RetryIntegration:
    """Tests for M5 R6 retry logic integration with full pipeline."""

    @pytest.mark.asyncio
    async def test_r6_retry_success_continues_pipeline(self):
        """Test that R6 retry on VERSION_CONFLICT allows pipeline to continue."""
        # R6 fails once, then succeeds
        runner, r6_phase, r7_phase, r8_phase = create_full_runner(r6_conflict_until=1)
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # Pipeline should complete successfully
        assert result.is_success

        # R6 called twice (fail then success)
        assert r6_phase.call_count == 2

        # R7 and R8 should have run
        assert r7_phase.call_count == 1
        assert r8_phase.call_count == 1

    @pytest.mark.asyncio
    async def test_r6_multiple_retries_success(self):
        """Test that R6 can retry multiple times before succeeding."""
        # R6 fails twice, then succeeds (within max 3 retries)
        runner, r6_phase, r7_phase, r8_phase = create_full_runner(r6_conflict_until=2)
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        assert result.is_success
        assert r6_phase.call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_r6_max_retries_stops_pipeline(self):
        """Test that R6 max retries triggers DLQ and stops pipeline."""
        # R6 fails 10 times (exceeds max 3 retries)
        runner, r6_phase, r7_phase, r8_phase = create_full_runner(r6_conflict_until=10)
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # Pipeline should fail
        assert result.is_failed
        assert result.dlq_reason is not None

        # R7 and R8 should NOT have run
        assert r7_phase.call_count == 0
        assert r8_phase.call_count == 0


class TestM5FailureHandling:
    """Tests for M5 failure handling in pipeline."""

    @pytest.mark.asyncio
    async def test_r7_failure_stops_before_r8(self):
        """Test that R7 failure stops pipeline before R8."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner(r7_success=False)
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # Pipeline failed
        assert result.is_failed
        assert result.final_phase == P03PhaseId.R7_WRITE

        # R6 ran, R7 ran and failed, R8 did not run
        assert r6_phase.call_count == 1
        assert r7_phase.call_count == 1
        assert r8_phase.call_count == 0

    @pytest.mark.asyncio
    async def test_failure_includes_error_info(self):
        """Test that failure result includes error information."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner(r7_success=False)
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        r7_result = result.phase_results[P03PhaseId.R7_WRITE]
        assert r7_result.error_info is not None
        assert r7_result.error_info.error_type == "WRITE_ERROR"


class TestM5PipelineMetrics:
    """Tests for M5 pipeline metrics capture."""

    @pytest.mark.asyncio
    async def test_total_duration_calculated(self):
        """Test that total pipeline duration is calculated."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run(envelope, ctx)

        # Total duration should be positive
        assert result.total_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_pipeline_timeline_recorded(self):
        """Test that pipeline timeline is recorded for metrics."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        await runner.run(envelope, ctx)

        # Timeline should have entries for all phases
        timeline = runner.get_timeline()
        assert len(timeline) == 9

        # All entries have durations
        for entry in timeline:
            assert entry.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_phase_ids_in_execution_order(self):
        """Test that phase results are in execution order."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        await runner.run(envelope, ctx)

        timeline = runner.get_timeline()
        phase_order = [entry.phase_id for entry in timeline]

        expected_order = [
            P03PhaseId.R0_INIT,
            P03PhaseId.R1_SCORE,
            P03PhaseId.R2_CLUSTER,
            P03PhaseId.R3_PRUNE,
            P03PhaseId.R4_KG,
            P03PhaseId.R5_DREAM,
            P03PhaseId.R6_STAGE,
            P03PhaseId.R7_WRITE,
            P03PhaseId.R8_EMIT,
        ]

        assert phase_order == expected_order


class TestM5StartFromPhase:
    """Tests for starting pipeline from a specific phase."""

    @pytest.mark.asyncio
    async def test_start_from_r6(self):
        """Test starting pipeline from R6."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run_from(envelope, ctx, start_phase=P03PhaseId.R6_STAGE)

        assert result.is_success

        # Only R6, R7, R8 should have run
        assert r6_phase.call_count == 1
        assert r7_phase.call_count == 1
        assert r8_phase.call_count == 1

        # Only 3 phases in timeline
        timeline = runner.get_timeline()
        assert len(timeline) == 3

    @pytest.mark.asyncio
    async def test_start_from_r7(self):
        """Test starting pipeline from R7."""
        runner, r6_phase, r7_phase, r8_phase = create_full_runner()
        envelope = create_test_envelope()
        ctx = create_test_context()

        result = await runner.run_from(envelope, ctx, start_phase=P03PhaseId.R7_WRITE)

        assert result.is_success

        # Only R7, R8 should have run
        assert r6_phase.call_count == 0
        assert r7_phase.call_count == 1
        assert r8_phase.call_count == 1
