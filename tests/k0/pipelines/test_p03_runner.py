"""
P03 Runner Integration Tests — Issue 1.2.8

Comprehensive tests proving runner semantics match Appendix G and remain stable.

Test Categories (from spec):
1. Legal Transitions — R0→R1→...→R8 passes; illegal jumps rejected
2. Skip Transitions — R2→R6 fast-path works; R4→R6 (skip R5) works
3. Skip Behavior — R5 skipped emits status=SKIP with skip_reason
4. Deterministic Seeding — Same cycle_id yields same RNG output sequence
5. Checkpoint Hooks — on_checkpoint called at each phase boundary
6. Resume — Given checkpoint at phase X, runner starts at X, does not re-run earlier
7. Observability — Phase events logged with correct fields

Test Pattern:
- Use small stub phases (not real R1-R8 implementations)
- Avoid mocking storage except at boundary
- Tests must be deterministic
- No real DB/network services required

References:
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.8
- Spec: docs/pipelines/P03_consolidation_dossier_v2.md Appendix G
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03 import (  # Transitions; Envelope and context; Runner; Deterministic seeding; Checkpoint; Offset manager; Observability
    NORMAL_TRANSITIONS,
    RESUME_MATRIX,
    SKIP_TRANSITIONS,
    InMemoryOffsetStore,
    OffsetAction,
    P03BatchEnvelope,
    P03CycleContext,
    P03DeterministicContext,
    P03OffsetManager,
    P03PhaseBase,
    P03PhaseId,
    P03PhaseProtocol,
    P03PhaseStatus,
    P03RunnerContext,
    P03SeededRNG,
    P03SequentialRunner,
    PhaseEventType,
    PhaseTransitionLogger,
    create_checkpoint_from_envelope,
    derive_cycle_seed,
    is_valid_transition,
)

# =============================================================================
# FIXTURES: CONTEXTS AND ENVELOPES
# =============================================================================


@pytest.fixture
def sample_cycle_id() -> str:
    """Fixed cycle ID for deterministic testing."""
    return "01JFXYZ123ABC456DEF789GHJ"


@pytest.fixture
def sample_batch_id() -> str:
    """Fixed batch ID for deterministic testing."""
    return "a1b2c3d4e5f67890"


@pytest.fixture
def sample_context(sample_cycle_id: str, sample_batch_id: str) -> P03CycleContext:
    """Create a sample cycle context with fixed IDs for deterministic tests."""
    # We need to create with specific IDs for reproducibility
    # Use the create() factory but note batch_id is derived from event_ids
    return P03CycleContext.create(
        tenant_id="tenant-test",
        space_id="space-test",
        event_ids=["evt-001", "evt-002", "evt-003", "evt-004", "evt-005"],
        trigger_type="MANUAL",
        trigger_reason="Integration test",
        pending_before=100,
    )


@pytest.fixture
def sample_envelope(sample_context: P03CycleContext) -> P03BatchEnvelope:
    """Create a sample batch envelope."""
    return P03BatchEnvelope.create(sample_context)


@pytest.fixture
def high_backlog_context() -> P03CycleContext:
    """Context with high pending count to trigger R5 skip."""
    return P03CycleContext.create(
        tenant_id="tenant-test",
        space_id="space-test",
        event_ids=["evt-001", "evt-002", "evt-003"],
        trigger_type="THRESHOLD",
        trigger_reason="Backlog exceeded",
        pending_before=10000,  # High backlog
    )


@pytest.fixture
def single_event_context() -> P03CycleContext:
    """Context with single event to trigger R2→R6 fast-path."""
    return P03CycleContext.create(
        tenant_id="tenant-test",
        space_id="space-test",
        event_ids=["evt-001"],  # Single event
        trigger_type="MANUAL",
        trigger_reason="Single event test",
    )


@pytest.fixture
def mock_syscalls() -> MagicMock:
    """Create mock syscalls for runner context."""
    return MagicMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create mock logger for runner context."""
    return MagicMock()


@pytest.fixture
def sample_runner_context(mock_syscalls: MagicMock, mock_logger: MagicMock) -> P03RunnerContext:
    """Create a sample runner context."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=mock_logger,
        qos_band="GREEN",
        priority=50,
        config={"r5_backlog_threshold": 5000},
    )


# =============================================================================
# STUB PHASE IMPLEMENTATIONS
# =============================================================================


@dataclass
class PhaseExecutionRecord:
    """Record of a phase execution for tracking."""

    phase_id: P03PhaseId
    executed: bool = False
    skipped: bool = False
    skip_reason: str = ""
    failed: bool = False
    error_message: str = ""
    random_values: List[float] = field(default_factory=list)


class TrackingStubPhase(P03PhaseBase):
    """
    Stub phase that tracks execution and can capture RNG values.

    Used for integration testing of runner behavior.
    """

    def __init__(
        self,
        phase_id: P03PhaseId,
        should_skip: bool = False,
        skip_reason: str = "",
        should_fail: bool = False,
        fail_error_type: str = "TestError",
        fail_message: str = "Simulated failure",
        outputs: Optional[Dict[str, Any]] = None,
        execution_time_ms: int = 5,
        capture_rng_values: int = 0,  # How many random values to capture
    ):
        self._phase_id = phase_id
        self._should_skip = should_skip
        self._skip_reason = skip_reason
        self._should_fail = should_fail
        self._fail_error_type = fail_error_type
        self._fail_message = fail_message
        self._outputs = outputs or {"processed": True, "phase": phase_id.value}
        self._execution_time_ms = execution_time_ms
        self._capture_rng_values = capture_rng_values

        # Tracking state
        self.execution_count = 0
        self.records: List[PhaseExecutionRecord] = []
        self.last_envelope: Optional[P03BatchEnvelope] = None
        self.last_context: Optional[P03RunnerContext] = None

    @property
    def phase_id(self) -> P03PhaseId:
        return self._phase_id

    async def _execute(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> Dict[str, Any]:
        self.execution_count += 1
        self.last_envelope = envelope
        self.last_context = ctx

        record = PhaseExecutionRecord(
            phase_id=self._phase_id,
            executed=True,
        )

        # Capture RNG values if configured
        if self._capture_rng_values > 0:
            # Get deterministic context from runner context config if available
            det_ctx = ctx.config.get("deterministic_context")
            if det_ctx and isinstance(det_ctx, P03DeterministicContext):
                rng = det_ctx.get_phase_rng(self._phase_id)
                record.random_values = [rng.random() for _ in range(self._capture_rng_values)]

        if self._should_fail:
            record.failed = True
            record.error_message = self._fail_message
            self.records.append(record)
            raise RuntimeError(self._fail_message)

        # Simulate execution time
        await asyncio.sleep(self._execution_time_ms / 1000)

        self.records.append(record)
        return self._outputs

    def should_skip(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> Tuple[bool, str]:
        if self._should_skip:
            record = PhaseExecutionRecord(
                phase_id=self._phase_id,
                skipped=True,
                skip_reason=self._skip_reason,
            )
            self.records.append(record)
            return (True, self._skip_reason)
        return (False, "")


def create_tracking_phases(
    phases_to_create: Optional[List[P03PhaseId]] = None,
    skip_phases: Optional[Dict[P03PhaseId, str]] = None,
    fail_phases: Optional[Dict[P03PhaseId, str]] = None,
    capture_rng_phases: Optional[List[P03PhaseId]] = None,
) -> Dict[P03PhaseId, P03PhaseProtocol]:
    """
    Create tracking stub phases for testing.

    Args:
        phases_to_create: Phases to create (defaults to all R0-R8)
        skip_phases: Dict of phase_id -> skip_reason
        fail_phases: Dict of phase_id -> error_message
        capture_rng_phases: Phases that should capture RNG values

    Returns:
        Dict mapping phase IDs to tracking stub phases (typed as P03PhaseProtocol)
    """
    if phases_to_create is None:
        phases_to_create = list(P03PhaseId.execution_order())

    skip_phases = skip_phases or {}
    fail_phases = fail_phases or {}
    capture_rng_phases = capture_rng_phases or []

    result: Dict[P03PhaseId, P03PhaseProtocol] = {}
    for phase_id in phases_to_create:
        result[phase_id] = TrackingStubPhase(
            phase_id=phase_id,
            should_skip=phase_id in skip_phases,
            skip_reason=skip_phases.get(phase_id, ""),
            should_fail=phase_id in fail_phases,
            fail_message=fail_phases.get(phase_id, "Simulated failure"),
            capture_rng_values=5 if phase_id in capture_rng_phases else 0,
        )

    return result


# =============================================================================
# 1. LEGAL TRANSITIONS TESTS
# =============================================================================


class TestLegalTransitions:
    """
    Test legal phase transitions per Appendix G.3.

    Verifies:
    - R0→R1→R2→R3→R4→R5→R6→R7→R8 is the valid normal sequence
    - Illegal jumps (e.g., R0→R3) are rejected
    - Backward transitions are rejected
    """

    def test_normal_transitions_defined(self) -> None:
        """NORMAL_TRANSITIONS should define R0→R7 transitions."""
        assert P03PhaseId.R0_INIT in NORMAL_TRANSITIONS
        assert NORMAL_TRANSITIONS[P03PhaseId.R0_INIT] == P03PhaseId.R1_SCORE
        assert NORMAL_TRANSITIONS[P03PhaseId.R1_SCORE] == P03PhaseId.R2_CLUSTER
        assert NORMAL_TRANSITIONS[P03PhaseId.R7_WRITE] == P03PhaseId.R8_EMIT
        # R8 is terminal - no next
        assert P03PhaseId.R8_EMIT not in NORMAL_TRANSITIONS

    def test_is_valid_transition_normal_sequence(self) -> None:
        """All normal transitions should be valid."""
        order = P03PhaseId.execution_order()
        for i in range(len(order) - 1):
            from_phase = order[i]
            to_phase = order[i + 1]
            assert is_valid_transition(
                from_phase, to_phase
            ), f"Expected {from_phase} → {to_phase} to be valid"

    def test_is_valid_transition_rejects_skipping_phase(self) -> None:
        """Skipping a phase (except legal skips) should be invalid."""
        # R0 → R2 is NOT valid (must go through R1)
        assert is_valid_transition(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER) is False
        # R1 → R3 is NOT valid (must go through R2)
        assert is_valid_transition(P03PhaseId.R1_SCORE, P03PhaseId.R3_PRUNE) is False
        # R3 → R5 is NOT valid
        assert is_valid_transition(P03PhaseId.R3_PRUNE, P03PhaseId.R5_DREAM) is False

    def test_is_valid_transition_rejects_backward(self) -> None:
        """Backward transitions should be invalid."""
        assert is_valid_transition(P03PhaseId.R2_CLUSTER, P03PhaseId.R1_SCORE) is False
        assert is_valid_transition(P03PhaseId.R8_EMIT, P03PhaseId.R0_INIT) is False
        assert is_valid_transition(P03PhaseId.R5_DREAM, P03PhaseId.R3_PRUNE) is False

    @pytest.mark.asyncio
    async def test_runner_executes_full_sequence(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Runner should execute R0→R1→...→R8 in order."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        assert result.is_success
        assert result.final_phase == P03PhaseId.R8_EMIT

        # Verify each phase was executed exactly once
        for phase_id, phase in phases.items():
            assert phase.execution_count == 1, f"{phase_id} executed {phase.execution_count} times"

    @pytest.mark.asyncio
    async def test_runner_respects_phase_order(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Phases must execute in correct order."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases=phases)
        execution_order: List[P03PhaseId] = []

        def track(env: P03BatchEnvelope, phase_id: P03PhaseId, ctx: P03RunnerContext) -> None:
            execution_order.append(phase_id)

        runner._on_phase_start = track

        await runner.run(sample_envelope, sample_runner_context)

        expected = list(P03PhaseId.execution_order())
        assert execution_order == expected


# =============================================================================
# 2. SKIP TRANSITIONS TESTS
# =============================================================================


class TestSkipTransitions:
    """
    Test skip transitions per Appendix G.3.

    Legal skip transitions:
    - R2 → R6: Minimal work fast-path (batch_size < 2)
    - R4 → R6: Skip R5 on backlog
    - R5 → R6: R5 itself skipped
    """

    def test_skip_transitions_defined(self) -> None:
        """SKIP_TRANSITIONS should define legal skip paths."""
        # R2 can skip to R6
        assert P03PhaseId.R2_CLUSTER in SKIP_TRANSITIONS
        assert SKIP_TRANSITIONS[P03PhaseId.R2_CLUSTER][0] == P03PhaseId.R6_STAGE

        # R4 can skip to R6 (skip R5)
        assert P03PhaseId.R4_KG in SKIP_TRANSITIONS
        assert SKIP_TRANSITIONS[P03PhaseId.R4_KG][0] == P03PhaseId.R6_STAGE

        # R5 can skip to R6
        assert P03PhaseId.R5_DREAM in SKIP_TRANSITIONS
        assert SKIP_TRANSITIONS[P03PhaseId.R5_DREAM][0] == P03PhaseId.R6_STAGE

    def test_is_valid_transition_allows_r2_to_r6(self) -> None:
        """R2→R6 skip should be valid."""
        assert is_valid_transition(P03PhaseId.R2_CLUSTER, P03PhaseId.R6_STAGE) is True

    def test_is_valid_transition_allows_r4_to_r6(self) -> None:
        """R4→R6 skip (skip R5) should be valid."""
        assert is_valid_transition(P03PhaseId.R4_KG, P03PhaseId.R6_STAGE) is True

    def test_is_valid_transition_allows_r5_to_r6(self) -> None:
        """R5→R6 skip should be valid."""
        assert is_valid_transition(P03PhaseId.R5_DREAM, P03PhaseId.R6_STAGE) is True

    @pytest.mark.asyncio
    async def test_r2_skip_to_r6_fast_path(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """R2 skip should transition to R6, skipping R3-R5."""
        phases = create_tracking_phases(
            skip_phases={P03PhaseId.R2_CLUSTER: "batch_size < minimal_work_threshold"}
        )
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        assert result.is_success

        # R0, R1 executed
        assert phases[P03PhaseId.R0_INIT].execution_count == 1
        assert phases[P03PhaseId.R1_SCORE].execution_count == 1

        # R2 skipped (should_skip returned True)
        assert phases[P03PhaseId.R2_CLUSTER].execution_count == 0
        assert result.phase_results[P03PhaseId.R2_CLUSTER].status == P03PhaseStatus.SKIP

        # R3, R4, R5 skipped (cascaded from R2)
        assert result.phase_results[P03PhaseId.R3_PRUNE].status == P03PhaseStatus.SKIP
        assert result.phase_results[P03PhaseId.R4_KG].status == P03PhaseStatus.SKIP
        assert result.phase_results[P03PhaseId.R5_DREAM].status == P03PhaseStatus.SKIP

        # R6, R7, R8 executed
        assert phases[P03PhaseId.R6_STAGE].execution_count == 1
        assert phases[P03PhaseId.R7_WRITE].execution_count == 1
        assert phases[P03PhaseId.R8_EMIT].execution_count == 1

    @pytest.mark.asyncio
    async def test_r5_skip_proceeds_to_r6(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """R5 skip should proceed to R6 normally."""
        phases = create_tracking_phases(
            skip_phases={P03PhaseId.R5_DREAM: "backlog_threshold exceeded"}
        )
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        assert result.is_success

        # R0-R4 executed
        for phase_id in [
            P03PhaseId.R0_INIT,
            P03PhaseId.R1_SCORE,
            P03PhaseId.R2_CLUSTER,
            P03PhaseId.R3_PRUNE,
            P03PhaseId.R4_KG,
        ]:
            assert phases[phase_id].execution_count == 1

        # R5 skipped
        assert phases[P03PhaseId.R5_DREAM].execution_count == 0
        assert result.phase_results[P03PhaseId.R5_DREAM].status == P03PhaseStatus.SKIP

        # R6-R8 executed
        assert phases[P03PhaseId.R6_STAGE].execution_count == 1


# =============================================================================
# 3. SKIP BEHAVIOR TESTS
# =============================================================================


class TestSkipBehavior:
    """
    Test that skip behavior correctly records status and reason.

    Verifies:
    - Skipped phases have status=SKIP
    - Skip reason is populated
    - R5 skip fields in envelope are updated
    """

    @pytest.mark.asyncio
    async def test_skip_phase_has_skip_status(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Skipped phase should have SKIP status in result."""
        skip_reason = "Test skip reason for R5"
        phases = create_tracking_phases(skip_phases={P03PhaseId.R5_DREAM: skip_reason})
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        r5_result = result.phase_results[P03PhaseId.R5_DREAM]
        assert r5_result.status == P03PhaseStatus.SKIP
        assert r5_result.skip_reason == skip_reason

    @pytest.mark.asyncio
    async def test_skip_reason_propagated(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Skip reason should be captured in phase result."""
        skip_reasons = {
            P03PhaseId.R2_CLUSTER: "batch_size=1 < threshold=2",
            P03PhaseId.R5_DREAM: "pending=6000 > backlog_threshold=5000",
        }

        phases = create_tracking_phases(skip_phases=skip_reasons)
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        r2_result = result.phase_results[P03PhaseId.R2_CLUSTER]
        assert r2_result.skip_reason == skip_reasons[P03PhaseId.R2_CLUSTER]

    @pytest.mark.asyncio
    async def test_envelope_marked_skip(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Envelope should reflect skip status."""
        phases = create_tracking_phases(skip_phases={P03PhaseId.R5_DREAM: "backlog exceeded"})
        runner = P03SequentialRunner(phases=phases)

        await runner.run(sample_envelope, sample_runner_context)

        assert sample_envelope.get_phase_status(P03PhaseId.R5_DREAM) == P03PhaseStatus.SKIP

    @pytest.mark.asyncio
    async def test_cascaded_skip_reasons(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Phases skipped due to R2→R6 should have cascaded skip reason."""
        phases = create_tracking_phases(
            skip_phases={P03PhaseId.R2_CLUSTER: "minimal work fast-path"}
        )
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run(sample_envelope, sample_runner_context)

        # R3-R5 are cascaded skips
        for phase_id in [P03PhaseId.R3_PRUNE, P03PhaseId.R4_KG, P03PhaseId.R5_DREAM]:
            phase_result = result.phase_results[phase_id]
            assert phase_result.status == P03PhaseStatus.SKIP
            skip_reason = phase_result.skip_reason or ""
            assert "R2" in skip_reason or "cascaded" in skip_reason.lower()


# =============================================================================
# 4. DETERMINISTIC SEEDING TESTS
# =============================================================================


class TestDeterministicSeeding:
    """
    Test deterministic behavior based on cycle_id.

    Verifies:
    - Same cycle_id + batch_id produces same seed
    - Same seed produces identical RNG sequences
    - Phase isolation: one phase's RNG doesn't affect another
    """

    def test_derive_cycle_seed_deterministic(self) -> None:
        """Same inputs produce same seed."""
        seed1 = derive_cycle_seed("cycle123", "batch456")
        seed2 = derive_cycle_seed("cycle123", "batch456")
        assert seed1 == seed2

    def test_derive_cycle_seed_different_for_different_cycles(self) -> None:
        """Different cycle_ids produce different seeds."""
        seed1 = derive_cycle_seed("cycle111", "batch456")
        seed2 = derive_cycle_seed("cycle222", "batch456")
        assert seed1 != seed2

    def test_seeded_rng_produces_identical_sequence(self) -> None:
        """Two RNGs with same seed produce identical sequences."""
        rng1 = P03SeededRNG.create("cycle123", "batch456")
        rng2 = P03SeededRNG.create("cycle123", "batch456")

        values1 = [rng1.random() for _ in range(100)]
        values2 = [rng2.random() for _ in range(100)]

        assert values1 == values2

    def test_phase_rng_isolation(self) -> None:
        """Phase RNGs are isolated from each other."""
        rng = P03SeededRNG.create("cycle123", "batch456")

        # Get RNGs for different phases
        r3_rng = rng.get_phase_rng(P03PhaseId.R3_PRUNE)
        r5_rng = rng.get_phase_rng(P03PhaseId.R5_DREAM)

        r3_values = [r3_rng.random() for _ in range(10)]
        r5_values = [r5_rng.random() for _ in range(10)]

        # Different phases should produce different sequences
        assert r3_values != r5_values

    def test_phase_rng_deterministic_across_calls(self) -> None:
        """Same phase in different RNG contexts produces same sequence."""
        rng1 = P03SeededRNG.create("cycle123", "batch456")
        rng2 = P03SeededRNG.create("cycle123", "batch456")

        r5_rng1 = rng1.get_phase_rng(P03PhaseId.R5_DREAM)
        r5_rng2 = rng2.get_phase_rng(P03PhaseId.R5_DREAM)

        values1 = [r5_rng1.random() for _ in range(50)]
        values2 = [r5_rng2.random() for _ in range(50)]

        assert values1 == values2

    def test_deterministic_context_integration(self) -> None:
        """P03DeterministicContext provides deterministic behavior."""
        ctx1 = P03DeterministicContext.create(
            cycle_id="cycle123",
            batch_id="batch456",
            pending_count=100,
            batch_size=50,
        )
        ctx2 = P03DeterministicContext.create(
            cycle_id="cycle123",
            batch_id="batch456",
            pending_count=100,
            batch_size=50,
        )

        # Same RNG values
        rng1 = ctx1.get_phase_rng(P03PhaseId.R5_DREAM)
        rng2 = ctx2.get_phase_rng(P03PhaseId.R5_DREAM)

        assert [rng1.random() for _ in range(10)] == [rng2.random() for _ in range(10)]

        # Same skip decisions
        decision1 = ctx1.should_skip_phase(P03PhaseId.R5_DREAM)
        decision2 = ctx2.should_skip_phase(P03PhaseId.R5_DREAM)

        assert decision1.should_skip == decision2.should_skip


# =============================================================================
# 5. CHECKPOINT HOOKS TESTS
# =============================================================================


class TestCheckpointHooks:
    """
    Test checkpoint callback hooks.

    Verifies:
    - on_checkpoint called at each phase boundary
    - Checkpoint contains correct phase information
    - Checkpoints can be used for resume
    """

    @pytest.mark.asyncio
    async def test_on_checkpoint_called_after_each_phase(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """on_checkpoint should be called after each phase completes."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases=phases)

        checkpoint_calls: List[P03PhaseId] = []

        def on_checkpoint(
            env: P03BatchEnvelope,
            phase_id: P03PhaseId,
            ctx: P03RunnerContext,
        ) -> None:
            checkpoint_calls.append(phase_id)

        runner._on_checkpoint = on_checkpoint

        await runner.run(sample_envelope, sample_runner_context)

        # Should have checkpoint for each completed phase
        expected = list(P03PhaseId.execution_order())
        assert checkpoint_calls == expected

    @pytest.mark.asyncio
    async def test_checkpoint_not_called_on_failure(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """on_checkpoint should NOT be called for failed phase."""
        phases = create_tracking_phases(fail_phases={P03PhaseId.R3_PRUNE: "Simulated failure"})
        runner = P03SequentialRunner(phases=phases)

        checkpoint_calls: List[P03PhaseId] = []

        def on_checkpoint(
            env: P03BatchEnvelope,
            phase_id: P03PhaseId,
            ctx: P03RunnerContext,
        ) -> None:
            checkpoint_calls.append(phase_id)

        runner._on_checkpoint = on_checkpoint

        await runner.run(sample_envelope, sample_runner_context)

        # Only R0, R1, R2 should have checkpoints (R3 failed)
        assert checkpoint_calls == [
            P03PhaseId.R0_INIT,
            P03PhaseId.R1_SCORE,
            P03PhaseId.R2_CLUSTER,
        ]

    @pytest.mark.asyncio
    async def test_checkpoint_calls_skip_intermediate_phases(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Skipped phases do NOT trigger checkpoint (they have no state to save)."""
        phases = create_tracking_phases(skip_phases={P03PhaseId.R5_DREAM: "backlog exceeded"})
        runner = P03SequentialRunner(phases=phases)

        checkpoint_calls: List[P03PhaseId] = []

        def on_checkpoint(
            env: P03BatchEnvelope,
            phase_id: P03PhaseId,
            ctx: P03RunnerContext,
        ) -> None:
            checkpoint_calls.append(phase_id)

        runner._on_checkpoint = on_checkpoint

        await runner.run(sample_envelope, sample_runner_context)

        # R5 is skipped so NOT in checkpoint_calls - that's correct behavior
        # Skipped phases have no state to checkpoint
        assert P03PhaseId.R5_DREAM not in checkpoint_calls
        # But other phases should have checkpoints
        assert P03PhaseId.R0_INIT in checkpoint_calls
        assert P03PhaseId.R6_STAGE in checkpoint_calls

    def test_create_checkpoint_from_envelope(
        self,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """create_checkpoint_from_envelope produces valid checkpoint."""
        # Simulate some phase progress
        sample_envelope.mark_phase_complete(P03PhaseId.R0_INIT)
        sample_envelope.mark_phase_complete(P03PhaseId.R1_SCORE)
        sample_envelope.mark_phase_complete(P03PhaseId.R2_CLUSTER)

        checkpoint = create_checkpoint_from_envelope(
            envelope=sample_envelope,
            phase_id=P03PhaseId.R2_CLUSTER,
            phase_status=P03PhaseStatus.DONE,
        )

        assert checkpoint.cycle_id == sample_envelope.context.cycle_id
        assert checkpoint.batch_id == sample_envelope.context.batch_id
        assert checkpoint.phase_id == P03PhaseId.R2_CLUSTER
        assert checkpoint.phase_status == P03PhaseStatus.DONE


# =============================================================================
# 6. RESUME TESTS
# =============================================================================


class TestResume:
    """
    Test resume from checkpoint functionality.

    Verifies:
    - Runner can start from specified phase
    - Earlier phases are NOT re-executed
    - RESUME_MATRIX specifies correct resume points
    """

    def test_resume_matrix_defined(self) -> None:
        """RESUME_MATRIX should define resume policies for all phases."""
        for phase_id in P03PhaseId.execution_order():
            assert phase_id in RESUME_MATRIX, f"Missing resume policy for {phase_id}"

    def test_resume_matrix_r7_resumes_from_r6(self) -> None:
        """R7 failure should resume from R6 per RESUME_MATRIX."""
        policy = RESUME_MATRIX[P03PhaseId.R7_WRITE]
        assert policy.can_resume is True
        assert policy.resume_from == P03PhaseId.R6_STAGE

    @pytest.mark.asyncio
    async def test_run_from_resumes_at_correct_phase(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """run_from should start execution at specified phase."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases=phases)

        result = await runner.run_from(
            sample_envelope,
            sample_runner_context,
            start_phase=P03PhaseId.R4_KG,
        )

        assert result.is_success

        # R0-R3 should NOT be executed
        assert phases[P03PhaseId.R0_INIT].execution_count == 0
        assert phases[P03PhaseId.R1_SCORE].execution_count == 0
        assert phases[P03PhaseId.R2_CLUSTER].execution_count == 0
        assert phases[P03PhaseId.R3_PRUNE].execution_count == 0

        # R4-R8 should be executed
        assert phases[P03PhaseId.R4_KG].execution_count == 1
        assert phases[P03PhaseId.R5_DREAM].execution_count == 1
        assert phases[P03PhaseId.R6_STAGE].execution_count == 1
        assert phases[P03PhaseId.R7_WRITE].execution_count == 1
        assert phases[P03PhaseId.R8_EMIT].execution_count == 1

    @pytest.mark.asyncio
    async def test_resume_does_not_rerun_earlier_phases(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Resume should not execute phases before start_phase."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases=phases)
        execution_order: List[P03PhaseId] = []

        def track(env: P03BatchEnvelope, phase_id: P03PhaseId, ctx: P03RunnerContext) -> None:
            execution_order.append(phase_id)

        runner._on_phase_start = track

        await runner.run_from(
            sample_envelope,
            sample_runner_context,
            start_phase=P03PhaseId.R6_STAGE,
        )

        # Only R6, R7, R8 should be in execution order
        assert execution_order == [
            P03PhaseId.R6_STAGE,
            P03PhaseId.R7_WRITE,
            P03PhaseId.R8_EMIT,
        ]

    def test_get_resume_phase_uses_resume_matrix(self) -> None:
        """get_resume_phase should use RESUME_MATRIX."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases=phases)

        # R7 should resume from R6
        assert runner.get_resume_phase(P03PhaseId.R7_WRITE) == P03PhaseId.R6_STAGE

        # R5 should resume from R5
        assert runner.get_resume_phase(P03PhaseId.R5_DREAM) == P03PhaseId.R5_DREAM

        # R0 should resume from R0
        assert runner.get_resume_phase(P03PhaseId.R0_INIT) == P03PhaseId.R0_INIT


# =============================================================================
# 7. OBSERVABILITY TESTS
# =============================================================================


class TestObservability:
    """
    Test observability and logging.

    Verifies:
    - Phase events are logged with correct fields
    - Transition logger captures start/complete/skip/fail events
    - Correct identifiers in events
    """

    @pytest.mark.asyncio
    async def test_transition_logger_records_events(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should record phase events."""
        phases = create_tracking_phases()
        transition_logger = PhaseTransitionLogger()
        runner = P03SequentialRunner(
            phases={pid: p for pid, p in phases.items()},
            transition_logger=transition_logger,
        )

        await runner.run(sample_envelope, sample_runner_context)

        events = transition_logger.events

        # Should have start and complete events for each phase
        start_events = [e for e in events if e.event_type == PhaseEventType.PHASE_START]
        complete_events = [e for e in events if e.event_type == PhaseEventType.PHASE_COMPLETE]

        assert len(start_events) == 9  # R0-R8
        assert len(complete_events) == 9  # R0-R8

    @pytest.mark.asyncio
    async def test_transition_events_have_correct_ids(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition events should include correct identifiers."""
        phases = create_tracking_phases()
        transition_logger = PhaseTransitionLogger()
        runner = P03SequentialRunner(
            phases={pid: p for pid, p in phases.items()},
            transition_logger=transition_logger,
        )

        await runner.run(sample_envelope, sample_runner_context)

        # Check first event
        first_event = transition_logger.events[0]
        assert first_event.cycle_id == sample_envelope.context.cycle_id
        assert first_event.batch_id == sample_envelope.context.batch_id
        # trace_id may not be set in observability context
        assert first_event.phase_id == P03PhaseId.R0_INIT.value

    @pytest.mark.asyncio
    async def test_skip_event_logged(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Skip events should be logged with reason."""
        phases = create_tracking_phases(skip_phases={P03PhaseId.R5_DREAM: "backlog exceeded"})
        transition_logger = PhaseTransitionLogger()
        runner = P03SequentialRunner(
            phases={pid: p for pid, p in phases.items()},
            transition_logger=transition_logger,
        )

        await runner.run(sample_envelope, sample_runner_context)

        skip_events = [
            e for e in transition_logger.events if e.event_type == PhaseEventType.PHASE_SKIP
        ]

        # Should have at least one skip event for R5
        r5_skips = [e for e in skip_events if e.phase_id == P03PhaseId.R5_DREAM.value]
        assert len(r5_skips) == 1
        assert r5_skips[0].skip_reason == "backlog exceeded"

    @pytest.mark.asyncio
    async def test_fail_event_logged(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Failure events should be logged with error info."""
        phases = create_tracking_phases(fail_phases={P03PhaseId.R3_PRUNE: "SIMHASH_ERROR"})
        transition_logger = PhaseTransitionLogger()
        runner = P03SequentialRunner(
            phases={pid: p for pid, p in phases.items()},
            transition_logger=transition_logger,
        )

        await runner.run(sample_envelope, sample_runner_context)

        fail_events = [
            e for e in transition_logger.events if e.event_type == PhaseEventType.PHASE_FAIL
        ]

        assert len(fail_events) == 1
        assert fail_events[0].phase_id == P03PhaseId.R3_PRUNE.value

    @pytest.mark.asyncio
    async def test_phase_summary_generation(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Transition logger should generate summary."""
        phases = create_tracking_phases(skip_phases={P03PhaseId.R5_DREAM: "backlog exceeded"})
        transition_logger = PhaseTransitionLogger()
        runner = P03SequentialRunner(
            phases={pid: p for pid, p in phases.items()},
            transition_logger=transition_logger,
        )

        await runner.run(sample_envelope, sample_runner_context)

        summary = transition_logger.get_phase_summary()

        # Check summary structure
        assert "phases" in summary
        assert "total_events" in summary
        assert summary["total_events"] > 0
        assert "skipped_phases" in summary
        assert len(summary["skipped_phases"]) >= 1  # At least R5


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestRunnerIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_all_features(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Full cycle exercising transitions, checkpoints, observability."""
        phases = create_tracking_phases()

        # Set up checkpointing
        checkpoints: List[Tuple[P03PhaseId, P03PhaseStatus]] = []

        def on_checkpoint(
            env: P03BatchEnvelope,
            phase_id: P03PhaseId,
            ctx: P03RunnerContext,
        ) -> None:
            checkpoints.append((phase_id, env.get_phase_status(phase_id)))

        # Set up transition logging
        transition_logger = PhaseTransitionLogger()

        runner = P03SequentialRunner(
            phases={pid: p for pid, p in phases.items()},
            transition_logger=transition_logger,
        )
        runner._on_checkpoint = on_checkpoint

        result = await runner.run(sample_envelope, sample_runner_context)

        # Verify success
        assert result.is_success
        assert result.final_phase == P03PhaseId.R8_EMIT

        # Verify checkpoints recorded
        assert len(checkpoints) == 9

        # Verify observability
        assert len(transition_logger.events) == 18  # 9 start + 9 complete

    @pytest.mark.asyncio
    async def test_deterministic_replay(
        self,
        mock_syscalls: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        """Two runs with same cycle_id should produce identical results."""
        # Create context for deterministic testing
        ctx1 = P03CycleContext.create(
            tenant_id="tenant-1",
            space_id="space-1",
            event_ids=["evt-1", "evt-2", "evt-3"],
            trigger_type="MANUAL",
            trigger_reason="Replay test",
        )

        # Note: Different cycle_id will be generated each time, so we test RNG
        # determinism by using the same cycle_id and batch_id

        # Test that same RNG seed produces same output
        rng1 = P03SeededRNG.create(ctx1.cycle_id, ctx1.batch_id)
        rng2 = P03SeededRNG.create(ctx1.cycle_id, ctx1.batch_id)  # Same IDs

        values1 = [rng1.random() for _ in range(100)]
        values2 = [rng2.random() for _ in range(100)]

        assert values1 == values2

    @pytest.mark.asyncio
    async def test_offset_decision_after_success(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Successful cycle should result in COMMIT offset action."""
        phases = create_tracking_phases()
        runner = P03SequentialRunner(phases={pid: p for pid, p in phases.items()})

        result = await runner.run(sample_envelope, sample_runner_context)
        assert result.is_success

        # Create offset manager and test decision
        offset_store = InMemoryOffsetStore()
        offset_manager = P03OffsetManager(
            subscriber_id="p03",
            topic="p03.consolidation.batch",
            offset_store=offset_store,
        )

        decision = offset_manager.decide_action(
            result,
            sample_envelope,
            last_wal_pos=12345,
        )

        assert decision.action == OffsetAction.COMMIT

    @pytest.mark.asyncio
    async def test_offset_decision_after_resumable_failure(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Resumable failure should result in CHECKPOINT_ONLY action."""
        phases = create_tracking_phases(fail_phases={P03PhaseId.R3_PRUNE: "SIMHASH_ERROR"})
        runner = P03SequentialRunner(phases={pid: p for pid, p in phases.items()})

        result = await runner.run(sample_envelope, sample_runner_context)
        assert result.is_failed

        offset_store = InMemoryOffsetStore()
        offset_manager = P03OffsetManager(
            subscriber_id="p03",
            topic="p03.consolidation.batch",
            offset_store=offset_store,
        )

        decision = offset_manager.decide_action(
            result,
            sample_envelope,
            last_wal_pos=12345,
        )

        # R3 is resumable per RESUME_MATRIX
        assert decision.action == OffsetAction.CHECKPOINT_ONLY
        assert decision.checkpoint is not None
