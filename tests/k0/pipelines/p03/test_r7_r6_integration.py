"""
Tests for R7 R6Output Integration — Issue 5.2.W3

Tests that R7 correctly consumes R6Output when available.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.modules.consolidation.staging.r6_output import R6Output, ReconciliationSummary
from k0.pipelines.p03 import P03BatchEnvelope, P03CycleContext, P03EventState
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phases.r7_truth_writer import R7TruthWriter

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MagicMock:
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    conn.fetchrow = AsyncMock(return_value=None)
    conn.executemany = AsyncMock()
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
    for i in range(2):
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
        events.append(evt)
    return events


@pytest.fixture
def sample_r6_output(sample_cycle_context: P03CycleContext) -> R6Output:
    """Create sample R6Output."""
    return R6Output(
        cycle_ulid=sample_cycle_context.cycle_id,
        batch_id="batch-123",
        staged_event_updates=(),
        staged_truth_writes=(),
        staged_kg_writes=(),
        staged_outbox_events=(),
        reconciliation_summary=ReconciliationSummary(),
        created_at_ms=1000000,
        r6_idempotency_key=f"p03:r6:{sample_cycle_context.cycle_id}",
    )


@pytest.fixture
def sample_envelope(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
) -> P03BatchEnvelope:
    """Create sample envelope without R6Output."""
    return P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )


@pytest.fixture
def sample_envelope_with_r6(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
    sample_r6_output: R6Output,
) -> P03BatchEnvelope:
    """Create sample envelope with R6Output."""
    envelope = P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )
    envelope.phases.r6_output = sample_r6_output
    return envelope


@pytest.fixture
def r7_writer() -> R7TruthWriter:
    """Create R7TruthWriter."""
    writer = R7TruthWriter()
    writer.USE_M5_ROUTER = False  # Use legacy for simpler test
    return writer


# =============================================================================
# R6OUTPUT FIELD TESTS
# =============================================================================


class TestR6OutputField:
    """Tests for R6Output field in P03PhaseOutputs."""

    def test_r6_output_field_exists(self, sample_envelope: P03BatchEnvelope) -> None:
        """P03PhaseOutputs should have r6_output field."""
        assert hasattr(sample_envelope.phases, "r6_output")

    def test_r6_output_defaults_to_none(self, sample_envelope: P03BatchEnvelope) -> None:
        """r6_output should default to None."""
        assert sample_envelope.phases.r6_output is None

    def test_r6_output_can_be_set(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_r6_output: R6Output,
    ) -> None:
        """r6_output can be assigned an R6Output."""
        sample_envelope.phases.r6_output = sample_r6_output
        assert sample_envelope.phases.r6_output is sample_r6_output


# =============================================================================
# R7 CONSUMES R6OUTPUT TESTS
# =============================================================================


class TestR7ConsumesR6Output:
    """Tests for R7 consuming R6Output."""

    @pytest.mark.asyncio
    async def test_r7_uses_r6_output_when_available(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope_with_r6: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R7 should use R6Output when available."""
        result = await r7_writer.run(sample_envelope_with_r6, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

    @pytest.mark.asyncio
    async def test_r7_falls_back_to_staged_without_r6(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R7 should use envelope.staged when R6Output is None."""
        # Ensure no R6Output
        assert sample_envelope.phases.r6_output is None

        result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

    @pytest.mark.asyncio
    async def test_r7_logs_has_r6_output_true(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope_with_r6: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R7 should log has_r6_output=True when R6Output is available."""
        with patch("k0.pipelines.p03.phases.r7_truth_writer.logger") as mock_logger:
            await r7_writer.run(sample_envelope_with_r6, mock_runner_context)

            # Check that info was called with has_r6_output in extra
            call_args_list = mock_logger.info.call_args_list
            assert any(
                call.kwargs.get("extra", {}).get("has_r6_output") is True for call in call_args_list
            )

    @pytest.mark.asyncio
    async def test_r7_logs_has_r6_output_false(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R7 should log has_r6_output=False without R6Output."""
        with patch("k0.pipelines.p03.phases.r7_truth_writer.logger") as mock_logger:
            await r7_writer.run(sample_envelope, mock_runner_context)

            call_args_list = mock_logger.info.call_args_list
            assert any(
                call.kwargs.get("extra", {}).get("has_r6_output") is False
                for call in call_args_list
            )
