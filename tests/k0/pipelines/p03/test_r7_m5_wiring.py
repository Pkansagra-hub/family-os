"""
Tests for R7 M5 Wiring — Issue 5.2.W1

Tests for R7 wiring to DecisionRouter and TransactionCoordinator.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.modules.consolidation.truth_writer.result import LayerWriteResult, WriteResult
from k0.modules.consolidation.truth_writer.transaction import (
    TransactionCoordinator,
    TransactionResult,
)
from k0.pipelines.p03 import (
    LAYER_ST_EPI,
    LAYER_ST_SEM,
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    ReconciliationAction,
    StagedWrite,
)
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phases.r7_truth_writer import R7TruthWriter

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
def sample_envelope(
    sample_cycle_context: P03CycleContext,
    sample_event_states: List[P03EventState],
) -> P03BatchEnvelope:
    """Create sample envelope with staged writes."""
    envelope = P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=sample_event_states,
    )

    # Add sample staged writes
    envelope.staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi-001",
            data={"episode_id": "epi-001", "content": "test"},
            phase="R5",
        )
    )
    envelope.staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id="sem-001",
            data={"pattern_id": "sem-001", "pattern_type": "test"},
            phase="R5",
        )
    )

    return envelope


@pytest.fixture
def r7_writer() -> R7TruthWriter:
    """Create R7TruthWriter with M5 router enabled."""
    writer = R7TruthWriter()
    writer.USE_M5_ROUTER = True
    return writer


@pytest.fixture
def r7_writer_legacy() -> R7TruthWriter:
    """Create R7TruthWriter with legacy path."""
    writer = R7TruthWriter()
    writer.USE_M5_ROUTER = False
    return writer


# =============================================================================
# M5 ROUTER FLAG TESTS
# =============================================================================


class TestM5RouterFlag:
    """Tests for M5 router toggle."""

    def test_m5_router_disabled_by_default(self) -> None:
        """USE_M5_ROUTER should be False by default during rollout."""
        writer = R7TruthWriter()
        assert writer.USE_M5_ROUTER is False

    def test_can_enable_m5_router(self, r7_writer: R7TruthWriter) -> None:
        """Can enable M5 router for new path."""
        assert r7_writer.USE_M5_ROUTER is True


# =============================================================================
# COORDINATOR INITIALIZATION TESTS
# =============================================================================


class TestCoordinatorInit:
    """Tests for coordinator lazy initialization."""

    def test_coordinator_not_initialized_on_creation(self, r7_writer: R7TruthWriter) -> None:
        """Coordinator should not be initialized until first use."""
        assert r7_writer._coordinator is None
        assert r7_writer._router is None

    def test_get_or_create_coordinator_creates_coordinator(self, r7_writer: R7TruthWriter) -> None:
        """_get_or_create_coordinator should create coordinator on first call."""
        coordinator = r7_writer._get_or_create_coordinator()

        assert coordinator is not None
        assert isinstance(coordinator, TransactionCoordinator)
        assert r7_writer._coordinator is coordinator
        assert r7_writer._router is not None

    def test_get_or_create_coordinator_reuses_instance(self, r7_writer: R7TruthWriter) -> None:
        """_get_or_create_coordinator should reuse coordinator on subsequent calls."""
        coordinator1 = r7_writer._get_or_create_coordinator()
        coordinator2 = r7_writer._get_or_create_coordinator()

        assert coordinator1 is coordinator2

    def test_coordinator_has_all_layer_writers(self, r7_writer: R7TruthWriter) -> None:
        """Coordinator's router should have all 8 layer writers."""
        coordinator = r7_writer._get_or_create_coordinator()

        # NOTE: KGLayerWriter handles both st_kg_dom and st_kg_edges,
        # registered as "st_kg" in the router
        expected_layers = {
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg",  # Single writer for both entity/edge tables
            "st_vec",
        }
        assert set(coordinator.router.registered_layers) == expected_layers


# =============================================================================
# M5 EXECUTE PATH TESTS
# =============================================================================


class TestM5ExecutePath:
    """Tests for M5 execution path."""

    @pytest.mark.asyncio
    async def test_m5_path_uses_coordinator(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """M5 path should use TransactionCoordinator."""
        # Create mock coordinator
        mock_result = WriteResult(
            total_attempted=2,
            total_succeeded=2,
            total_failed=0,
            by_layer={
                "st_epi": LayerWriteResult.success("st_epi", 1),
                "st_sem": LayerWriteResult.success("st_sem", 1),
            },
        )
        mock_tx_result = TransactionResult(
            write_result=mock_result,
            attempts=1,
            total_duration_ms=10,
            version_conflicts=0,
        )

        with patch.object(
            TransactionCoordinator,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_tx_result,
        ):
            result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert result.outputs_summary["writes_executed"] == 2

    @pytest.mark.asyncio
    async def test_m5_path_stores_result_in_envelope(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """M5 path should store WriteResult in envelope.phases.r7_result."""
        mock_result = WriteResult(
            total_attempted=2,
            total_succeeded=2,
            total_failed=0,
            by_layer={
                "st_epi": LayerWriteResult.success("st_epi", 1),
                "st_sem": LayerWriteResult.success("st_sem", 1),
            },
        )
        mock_tx_result = TransactionResult(
            write_result=mock_result,
            attempts=1,
            total_duration_ms=10,
            version_conflicts=0,
        )

        with patch.object(
            TransactionCoordinator,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_tx_result,
        ):
            await r7_writer.run(sample_envelope, mock_runner_context)

        # Check result stored for R8 consumption
        assert hasattr(sample_envelope.phases, "r7_result")
        assert sample_envelope.phases.r7_result is mock_result


# =============================================================================
# LEGACY PATH TESTS
# =============================================================================


class TestLegacyPath:
    """Tests for legacy execution path."""

    @pytest.mark.asyncio
    async def test_legacy_path_uses_inline_sql(
        self,
        r7_writer_legacy: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """Legacy path should use inline SQL via _execute_single_write."""
        result = await r7_writer_legacy.run(sample_envelope, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        # Legacy returns Dict[str, int] not WriteResult
        assert isinstance(result.outputs_summary["writes_by_layer"], dict)

    @pytest.mark.asyncio
    async def test_legacy_path_emits_deprecation_warning(
        self,
        r7_writer_legacy: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """Legacy path should emit DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="deprecated"):
            await r7_writer_legacy.run(sample_envelope, mock_runner_context)


# =============================================================================
# WRITE RESULT HANDLING TESTS
# =============================================================================


class TestWriteResultHandling:
    """Tests for WriteResult vs Dict handling."""

    @pytest.mark.asyncio
    async def test_m5_result_format(
        self,
        r7_writer: R7TruthWriter,
        sample_envelope: P03BatchEnvelope,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """M5 path outputs should use WriteResult format."""
        mock_result = WriteResult(
            total_attempted=6,
            total_succeeded=5,
            total_failed=1,
            by_layer={
                "st_epi": LayerWriteResult.success("st_epi", 3),
                "st_sem": LayerWriteResult(
                    layer="st_sem",
                    writes_attempted=3,
                    writes_succeeded=2,
                    writes_failed=1,
                    failed_ids=["sem-fail"],
                ),
            },
        )
        mock_tx_result = TransactionResult(
            write_result=mock_result,
            attempts=1,
            total_duration_ms=10,
            version_conflicts=0,
        )

        with patch.object(
            TransactionCoordinator,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_tx_result,
        ):
            result = await r7_writer.run(sample_envelope, mock_runner_context)

        assert result.outputs_summary["writes_executed"] == 5
        assert result.outputs_summary["writes_by_layer"]["st_epi"] == 3
        assert result.outputs_summary["writes_by_layer"]["st_sem"] == 2
