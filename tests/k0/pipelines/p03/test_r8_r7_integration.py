"""
Tests for R8 R7 WriteResult Integration — Issue 5.2.W4

Tests that R8 correctly uses R7 WriteResult in completion payload.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.result import LayerWriteResult, WriteResult
from k0.pipelines.p03 import P03BatchEnvelope, P03CycleContext, P03EventState
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
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
def sample_write_result() -> WriteResult:
    """Create sample WriteResult from R7."""
    return WriteResult(
        total_attempted=5,
        total_succeeded=4,
        total_failed=1,
        by_layer={
            "st_epi": LayerWriteResult.success("st_epi", 2),
            "st_sem": LayerWriteResult.success("st_sem", 1),
            "st_kg": LayerWriteResult.partial(
                layer="st_kg",
                succeeded=1,
                failed_ids=["entity-fail-001"],
                error="Version conflict",
            ),
        },
        failed_decision_ids=["entity-fail-001"],
        total_duration_ms=50,
    )


@pytest.fixture
def sample_envelope(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
) -> P03BatchEnvelope:
    """Create sample envelope without R7 result."""
    envelope = P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )
    # Add r6_summary mock for legacy path
    r6_summary = MagicMock()
    r6_summary.total_processed = 10
    envelope.phases.r6_summary = r6_summary
    return envelope


@pytest.fixture
def sample_envelope_with_r7(
    sample_envelope: P03BatchEnvelope,
    sample_write_result: WriteResult,
) -> P03BatchEnvelope:
    """Create sample envelope with R7 WriteResult."""
    sample_envelope.phases.r7_result = sample_write_result
    return sample_envelope


@pytest.fixture
def r8_emitter() -> R8EventEmitter:
    """Create R8EventEmitter with legacy path."""
    emitter = R8EventEmitter()
    emitter.USE_M5_EMITTERS = False  # Use legacy for simpler test
    return emitter


# =============================================================================
# R7RESULT FIELD TESTS
# =============================================================================


class TestR7ResultField:
    """Tests for r7_result field in P03PhaseOutputs."""

    def test_r7_result_field_exists(self, sample_envelope: P03BatchEnvelope) -> None:
        """P03PhaseOutputs should have r7_result field."""
        assert hasattr(sample_envelope.phases, "r7_result")

    def test_r7_result_defaults_to_none(self, sample_envelope: P03BatchEnvelope) -> None:
        """r7_result should default to None."""
        assert sample_envelope.phases.r7_result is None

    def test_r7_result_can_be_set(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_write_result: WriteResult,
    ) -> None:
        """r7_result can be assigned a WriteResult."""
        sample_envelope.phases.r7_result = sample_write_result
        assert sample_envelope.phases.r7_result is sample_write_result


# =============================================================================
# R8 _BUILD_SUMMARY TESTS
# =============================================================================


class TestR8BuildSummary:
    """Tests for R8 _build_summary using R7 WriteResult."""

    def test_build_summary_includes_r7_stats(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope_with_r7: P03BatchEnvelope,
    ) -> None:
        """_build_summary should include R7 write statistics."""
        summary = r8_emitter._build_summary(sample_envelope_with_r7)

        assert "truth_writes" in summary
        assert summary["truth_writes"]["writes_succeeded"] == 4
        assert summary["truth_writes"]["writes_failed"] == 1
        assert "st_epi" in summary["truth_writes"]["layers_touched"]
        assert "st_sem" in summary["truth_writes"]["layers_touched"]
        assert "st_kg" in summary["truth_writes"]["layers_touched"]
        assert summary["truth_writes"]["failed_decision_ids"] == ["entity-fail-001"]

    def test_build_summary_empty_r7_stats_when_none(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """_build_summary should have empty truth_writes when r7_result is None."""
        summary = r8_emitter._build_summary(sample_envelope)

        assert "truth_writes" in summary
        assert summary["truth_writes"] == {}

    def test_build_summary_still_includes_other_fields(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope_with_r7: P03BatchEnvelope,
    ) -> None:
        """_build_summary should still include other standard fields."""
        summary = r8_emitter._build_summary(sample_envelope_with_r7)

        assert "events_processed" in summary
        assert "clusters_created" in summary
        assert "duplicates_found" in summary
        assert "entities_created" in summary
        assert "edges_created" in summary
        assert "gaps_detected" in summary
        assert "patterns_updated" in summary
        assert "salience_changes" in summary


# =============================================================================
# R8 INTEGRATION TESTS
# =============================================================================


class TestR8Integration:
    """Integration tests for R8 with R7 WriteResult."""

    @pytest.mark.asyncio
    async def test_r8_completes_with_r7_result(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope_with_r7: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R8 should complete successfully with R7 result."""
        result = await r8_emitter.run(sample_envelope_with_r7, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

    @pytest.mark.asyncio
    async def test_r8_completes_without_r7_result(
        self,
        r8_emitter: R8EventEmitter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """R8 should complete successfully without R7 result."""
        result = await r8_emitter.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
