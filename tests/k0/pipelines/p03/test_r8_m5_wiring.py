"""
Tests for R8 M5 Wiring — Issue 5.2.W2

Tests for R8 wiring to EventEmitter and GapEmitterModule.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.modules.consolidation.emission.emitter import EmitResult, EventEmitter
from k0.modules.consolidation.emission.gap_emitter import GapEmitStats, GapEmitterModule
from k0.pipelines.p03 import (
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    ReconciliationAction,
)
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phase_outputs import GapCandidate
from k0.pipelines.p03.phases.r8_event_emitter import R8EventEmitter

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MagicMock:
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    conn.fetchrow = AsyncMock(return_value=None)
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
        event_ids=["evt-001", "evt-002"],
        trigger_type="MANUAL",
        trigger_reason="Test",
    )


@pytest.fixture
def sample_event_states() -> List[P03EventState]:
    """Create sample event states."""
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
def sample_gaps() -> List[GapCandidate]:
    """Create sample gap candidates."""
    return [
        GapCandidate(
            gap_id="gap-001",
            gap_type="AMBIGUOUS_ENTITY",
            related_entity_id="entity-001",
            entropy_score=0.7,
            priority=80,
            context_json="{}",
            candidate_values=["value_a", "value_b"],
        ),
        GapCandidate(
            gap_id="gap-002",
            gap_type="CONTRADICTION",
            related_entity_id="entity-002",
            entropy_score=0.9,
            priority=100,
            context_json="{}",
            candidate_values=["true", "false"],
        ),
    ]


@pytest.fixture
def sample_envelope(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
    sample_gaps: List[GapCandidate],
) -> P03BatchEnvelope:
    """Create sample envelope with gaps and summary."""
    envelope = P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )

    # Set R4 gap candidates
    envelope.phases.r4_gap_candidates = sample_gaps

    # Set R6 summary with required attribute for legacy path
    r6_summary = MagicMock()
    r6_summary.total_processed = 10  # Required by _build_summary
    envelope.phases.r6_summary = r6_summary

    return envelope


@pytest.fixture
def r8_emitter() -> R8EventEmitter:
    """Create R8EventEmitter with M5 emitters enabled."""
    emitter = R8EventEmitter()
    emitter.USE_M5_EMITTERS = True
    return emitter


@pytest.fixture
def r8_emitter_legacy() -> R8EventEmitter:
    """Create R8EventEmitter with legacy path."""
    emitter = R8EventEmitter()
    emitter.USE_M5_EMITTERS = False
    return emitter


# =============================================================================
# M5 EMITTER FLAG TESTS
# =============================================================================


class TestM5EmitterFlag:
    """Tests for M5 emitter toggle."""

    def test_m5_emitters_disabled_by_default(self) -> None:
        """USE_M5_EMITTERS should be False by default during rollout."""
        emitter = R8EventEmitter()
        assert emitter.USE_M5_EMITTERS is False

    def test_can_enable_m5_emitters(self, r8_emitter: R8EventEmitter) -> None:
        """Can enable M5 emitters for new path."""
        assert r8_emitter.USE_M5_EMITTERS is True


# =============================================================================
# EMITTER INITIALIZATION TESTS
# =============================================================================


class TestEmitterInit:
    """Tests for emitter initialization."""

    def test_event_emitter_initialized(self, r8_emitter: R8EventEmitter) -> None:
        """EventEmitter should be initialized on construction."""
        assert r8_emitter._event_emitter is not None
        assert isinstance(r8_emitter._event_emitter, EventEmitter)

    def test_gap_emitter_initialized(self, r8_emitter: R8EventEmitter) -> None:
        """GapEmitterModule should be initialized on construction."""
        assert r8_emitter._gap_emitter is not None
        assert isinstance(r8_emitter._gap_emitter, GapEmitterModule)

    def test_gap_emitter_has_correct_config(self, r8_emitter: R8EventEmitter) -> None:
        """GapEmitterModule should have correct config."""
        config = r8_emitter._gap_emitter.config
        assert config.max_gaps_per_cycle == 50
        assert config.ttl_hours == 168


# =============================================================================
# M5 EXECUTE PATH TESTS
# =============================================================================


class TestM5ExecutePath:
    """Tests for M5 execution path."""

    @pytest.mark.asyncio
    async def test_m5_path_uses_event_emitter(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """M5 path should use EventEmitter."""
        mock_emit_result = EmitResult(
            total_emitted=5,
            by_topic={
                "p03.consolidation.complete.v1": 1,
                "p03.truth.reinforced.v1": 1,
                "p03.truth.created.v1": 1,
            },
        )
        mock_gap_stats = GapEmitStats(
            total_received=2,
            emitted=2,
            deduplicated=0,
            capped=0,
        )

        with (
            patch.object(
                EventEmitter,
                "emit_all",
                new_callable=AsyncMock,
                return_value=mock_emit_result,
            ),
            patch.object(
                GapEmitterModule,
                "emit",
                new_callable=AsyncMock,
                return_value=mock_gap_stats,
            ),
        ):
            result = await r8_emitter.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert result.outputs_summary["events_emitted"] == 5
        assert result.outputs_summary["gaps_emitted"] == 2

    @pytest.mark.asyncio
    async def test_m5_path_resets_gap_emitter_cycle(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """M5 path should reset gap emitter at start of cycle."""
        reset_called = False
        original_reset = r8_emitter._gap_emitter.reset_cycle

        def mock_reset():
            nonlocal reset_called
            reset_called = True
            original_reset()

        r8_emitter._gap_emitter.reset_cycle = mock_reset

        mock_emit_result = EmitResult(total_emitted=1)
        mock_gap_stats = GapEmitStats()

        with (
            patch.object(
                EventEmitter,
                "emit_all",
                new_callable=AsyncMock,
                return_value=mock_emit_result,
            ),
            patch.object(
                GapEmitterModule,
                "emit",
                new_callable=AsyncMock,
                return_value=mock_gap_stats,
            ),
        ):
            await r8_emitter.run(sample_envelope, mock_runner_context)

        assert reset_called is True

    @pytest.mark.asyncio
    async def test_m5_path_outputs_summary(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """M5 path should include detailed output summary."""
        mock_emit_result = EmitResult(
            total_emitted=5,
            by_topic={
                "p03.consolidation.complete.v1": 1,
                "p03.truth.reinforced.v1": 1,
            },
        )
        mock_gap_stats = GapEmitStats(
            total_received=5,
            emitted=3,
            deduplicated=1,
            capped=1,
            by_type={"AMBIGUOUS_ENTITY": 2, "CONTRADICTION": 1},
        )

        with (
            patch.object(
                EventEmitter,
                "emit_all",
                new_callable=AsyncMock,
                return_value=mock_emit_result,
            ),
            patch.object(
                GapEmitterModule,
                "emit",
                new_callable=AsyncMock,
                return_value=mock_gap_stats,
            ),
        ):
            result = await r8_emitter.run(sample_envelope, mock_runner_context)

        summary = result.outputs_summary
        assert summary["events_emitted"] == 5
        assert summary["gaps_emitted"] == 3
        assert summary["gaps_deduplicated"] == 1
        assert summary["gaps_capped"] == 1
        assert summary["gaps_by_type"] == {"AMBIGUOUS_ENTITY": 2, "CONTRADICTION": 1}


# =============================================================================
# LEGACY PATH TESTS
# =============================================================================


class TestLegacyPath:
    """Tests for legacy execution path."""

    @pytest.mark.asyncio
    async def test_legacy_path_uses_inline_methods(
        self,
        r8_emitter_legacy: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """Legacy path should use inline _build_completion_payload."""
        result = await r8_emitter_legacy.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        # Legacy output format
        assert "completion_status" in result.outputs_summary
        assert "gaps_persisted" in result.outputs_summary


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_error_returns_recoverable_failure(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """Errors should return recoverable failure (R8 can retry)."""
        with patch.object(
            EventEmitter,
            "emit_all",
            new_callable=AsyncMock,
            side_effect=Exception("Emit failed"),
        ):
            result = await r8_emitter.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.FAIL
        assert result.error_info.error_type == "R8_EMISSION_ERROR"
        assert result.error_info.recoverable is True


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker integration."""

    def test_event_emitter_has_circuit_breaker(self, r8_emitter: R8EventEmitter) -> None:
        """EventEmitter should have circuit breaker configured."""
        config = r8_emitter._event_emitter._circuit_config
        assert config.failure_threshold == 5
        assert config.reset_timeout_ms == 60000
