"""
Test DecisionRouter — Issue 5.2.1

Tests for DecisionRouter and related classes.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.modules.consolidation.truth_writer.router import (
    DecisionRouter,
    DecisionRouterError,
    LayerWriterProtocol,
    WriteMode,
    create_decision_router,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_KG_DOM,
    LAYER_ST_SEM,
    P03StagedWrites,
    StagedWrite,
    WriteOperation,
)

# =============================================================================
# FIXTURES
# =============================================================================


class StubLayerWriter:
    """Stub layer writer for testing."""

    def __init__(
        self,
        layer: str,
        should_fail: bool = False,
        fail_ids: List[str] | None = None,
    ):
        self._layer = layer
        self._should_fail = should_fail
        self._fail_ids = fail_ids or []
        self.writes_received: List[StagedWrite] = []

    @property
    def layer(self) -> str:
        return self._layer

    async def write(
        self,
        writes: List[StagedWrite],
        uow: Any,  # Type as Any for testing with MagicMock
    ) -> LayerWriteResult:
        self.writes_received.extend(writes)

        if self._should_fail:
            raise RuntimeError(f"Write failed for {self._layer}")

        if self._fail_ids:
            succeeded = len(writes) - len(self._fail_ids)
            return LayerWriteResult.partial(
                layer=self._layer,
                succeeded=succeeded,
                failed_ids=self._fail_ids,
            )

        return LayerWriteResult.success(layer=self._layer, count=len(writes))


def create_test_write(
    layer: str,
    record_id: str,
    phase: str = "R1",
) -> StagedWrite:
    """Create a test StagedWrite."""
    return StagedWrite(
        write_id=f"write_{record_id}",
        layer=layer,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data={"id": record_id, "test": True},
        idempotency_key=f"{phase}:{layer}:{record_id}",
        source_phase=phase,
    )


def create_staged_writes_with_data() -> P03StagedWrites:
    """Create P03StagedWrites with test data."""
    staged = P03StagedWrites()

    # Add writes to different layers
    staged.add_write(create_test_write(LAYER_ST_EPI, "epi_1"))
    staged.add_write(create_test_write(LAYER_ST_EPI, "epi_2"))
    staged.add_write(create_test_write(LAYER_ST_SEM, "sem_1"))
    staged.add_write(create_test_write(LAYER_ST_KG_DOM, "kg_1"))

    return staged


@pytest.fixture
def mock_uow() -> MagicMock:
    """Create mock UnitOfWork."""
    return MagicMock()


@pytest.fixture
def writers() -> Dict[str, StubLayerWriter]:
    """Create default stub writers."""
    return {
        LAYER_ST_EPI: StubLayerWriter(LAYER_ST_EPI),
        LAYER_ST_SEM: StubLayerWriter(LAYER_ST_SEM),
        LAYER_ST_KG_DOM: StubLayerWriter(LAYER_ST_KG_DOM),
    }


# =============================================================================
# 1. CONSTRUCTION TESTS
# =============================================================================


class TestDecisionRouterConstruction:
    """Test DecisionRouter construction."""

    def test_create_with_writers(self, writers: Dict[str, StubLayerWriter]) -> None:
        """Router can be created with layer writers."""
        router = DecisionRouter(layer_writers=writers)

        assert len(router.registered_layers) == 3
        assert router.mode == WriteMode.ATOMIC

    def test_create_with_partial_mode(self, writers: Dict[str, StubLayerWriter]) -> None:
        """Router can be created with PARTIAL mode."""
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.PARTIAL)

        assert router.mode == WriteMode.PARTIAL

    def test_factory_function(self, writers: Dict[str, StubLayerWriter]) -> None:
        """create_decision_router factory works."""
        router = create_decision_router(layer_writers=writers, mode=WriteMode.PARTIAL)

        assert isinstance(router, DecisionRouter)
        assert router.mode == WriteMode.PARTIAL


class TestDecisionRouterProperties:
    """Test DecisionRouter properties."""

    def test_registered_layers(self, writers: Dict[str, StubLayerWriter]) -> None:
        """registered_layers returns all layer names."""
        router = DecisionRouter(layer_writers=writers)

        assert set(router.registered_layers) == {LAYER_ST_EPI, LAYER_ST_SEM, LAYER_ST_KG_DOM}

    def test_has_writer_true(self, writers: Dict[str, StubLayerWriter]) -> None:
        """has_writer returns True for registered layer."""
        router = DecisionRouter(layer_writers=writers)

        assert router.has_writer(LAYER_ST_EPI) is True

    def test_has_writer_false(self, writers: Dict[str, StubLayerWriter]) -> None:
        """has_writer returns False for unknown layer."""
        router = DecisionRouter(layer_writers=writers)

        assert router.has_writer("unknown_layer") is False

    def test_get_writer(self, writers: Dict[str, StubLayerWriter]) -> None:
        """get_writer returns writer for layer."""
        router = DecisionRouter(layer_writers=writers)

        writer = router.get_writer(LAYER_ST_EPI)

        assert writer is writers[LAYER_ST_EPI]


# =============================================================================
# 2. ROUTING TESTS — ATOMIC MODE
# =============================================================================


class TestRouteAtomic:
    """Test route() in ATOMIC mode."""

    @pytest.mark.asyncio
    async def test_route_empty_staged(
        self,
        writers: Dict[str, StubLayerWriter],
        mock_uow: MagicMock,
    ) -> None:
        """route() returns empty result for empty staged writes."""
        router = DecisionRouter(layer_writers=writers)
        staged = P03StagedWrites()

        result = await router.route(staged, mock_uow)

        assert result.total_attempted == 0
        assert result.is_success

    @pytest.mark.asyncio
    async def test_route_all_success(
        self,
        writers: Dict[str, StubLayerWriter],
        mock_uow: MagicMock,
    ) -> None:
        """route() returns success when all writes succeed."""
        router = DecisionRouter(layer_writers=writers)
        staged = create_staged_writes_with_data()

        result = await router.route(staged, mock_uow)

        assert result.total_succeeded == 4
        assert result.total_failed == 0
        assert result.is_success

    @pytest.mark.asyncio
    async def test_route_writes_to_correct_layers(
        self,
        writers: Dict[str, StubLayerWriter],
        mock_uow: MagicMock,
    ) -> None:
        """route() sends writes to correct layer writers."""
        router = DecisionRouter(layer_writers=writers)
        staged = create_staged_writes_with_data()

        await router.route(staged, mock_uow)

        assert len(writers[LAYER_ST_EPI].writes_received) == 2
        assert len(writers[LAYER_ST_SEM].writes_received) == 1
        assert len(writers[LAYER_ST_KG_DOM].writes_received) == 1

    @pytest.mark.asyncio
    async def test_route_raises_on_failure(
        self,
        mock_uow: MagicMock,
    ) -> None:
        """route() raises DecisionRouterError on failure in ATOMIC mode."""
        writers = {
            LAYER_ST_EPI: StubLayerWriter(LAYER_ST_EPI),
            LAYER_ST_SEM: StubLayerWriter(LAYER_ST_SEM, should_fail=True),
        }
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.ATOMIC)

        staged = P03StagedWrites()
        staged.add_write(create_test_write(LAYER_ST_EPI, "epi_1"))
        staged.add_write(create_test_write(LAYER_ST_SEM, "sem_1"))

        with pytest.raises(RuntimeError, match="Write failed for st_sem"):
            await router.route(staged, mock_uow)

    @pytest.mark.asyncio
    async def test_route_raises_for_unknown_layer(
        self,
        mock_uow: MagicMock,
    ) -> None:
        """route() raises ValueError for unknown layer in ATOMIC mode."""
        writers = {LAYER_ST_EPI: StubLayerWriter(LAYER_ST_EPI)}
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.ATOMIC)

        # Create staged writes and directly inject an unknown layer write
        staged = P03StagedWrites()
        unknown_write = create_test_write("unknown_layer", "x_1")
        # Directly append to a list that get_all_writes_ordered returns
        staged.st_epi_writes.append(unknown_write)  # Inject as epi write but with wrong layer

        with pytest.raises(ValueError, match="No writer registered for layer"):
            await router.route(staged, mock_uow)


# =============================================================================
# 3. ROUTING TESTS — PARTIAL MODE
# =============================================================================


class TestRoutePartial:
    """Test route() in PARTIAL mode."""

    @pytest.mark.asyncio
    async def test_route_continues_on_failure(
        self,
        mock_uow: MagicMock,
    ) -> None:
        """route() continues after failure in PARTIAL mode."""
        writers = {
            LAYER_ST_EPI: StubLayerWriter(LAYER_ST_EPI, should_fail=True),
            LAYER_ST_SEM: StubLayerWriter(LAYER_ST_SEM),
        }
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.PARTIAL)

        staged = P03StagedWrites()
        staged.add_write(create_test_write(LAYER_ST_EPI, "epi_1"))
        staged.add_write(create_test_write(LAYER_ST_SEM, "sem_1"))

        result = await router.route(staged, mock_uow)

        # Should have processed both layers
        assert LAYER_ST_EPI in result.by_layer
        assert LAYER_ST_SEM in result.by_layer
        assert result.total_failed == 1
        assert result.total_succeeded == 1

    @pytest.mark.asyncio
    async def test_route_handles_unknown_layer(
        self,
        mock_uow: MagicMock,
    ) -> None:
        """route() records failure for unknown layer in PARTIAL mode."""
        writers = {LAYER_ST_EPI: StubLayerWriter(LAYER_ST_EPI)}
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.PARTIAL)

        staged = P03StagedWrites()
        staged.add_write(create_test_write(LAYER_ST_EPI, "epi_1"))
        # Directly inject an unknown layer write
        unknown_write = create_test_write("unknown", "x_1")
        staged.st_epi_writes.append(unknown_write)  # Inject with wrong layer attr

        result = await router.route(staged, mock_uow)

        assert result.total_succeeded == 1  # Only the valid epi write
        assert result.total_failed == 1  # The unknown layer write
        assert "unknown" in result.failed_layers

    @pytest.mark.asyncio
    async def test_route_records_partial_failures(
        self,
        mock_uow: MagicMock,
    ) -> None:
        """route() records partial failures with IDs."""
        writers = {
            LAYER_ST_EPI: StubLayerWriter(LAYER_ST_EPI, fail_ids=["epi_2"]),
        }
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.PARTIAL)

        staged = P03StagedWrites()
        staged.add_write(create_test_write(LAYER_ST_EPI, "epi_1"))
        staged.add_write(create_test_write(LAYER_ST_EPI, "epi_2"))

        result = await router.route(staged, mock_uow)

        assert result.total_succeeded == 1
        assert result.total_failed == 1
        assert "epi_2" in result.failed_decision_ids


# =============================================================================
# 4. ROUTE_LAYER TESTS
# =============================================================================


class TestRouteLayer:
    """Test route_layer() for targeted writes."""

    @pytest.mark.asyncio
    async def test_route_layer_success(
        self,
        writers: Dict[str, StubLayerWriter],
        mock_uow: MagicMock,
    ) -> None:
        """route_layer() returns result for specific layer."""
        router = DecisionRouter(layer_writers=writers)
        writes = [
            create_test_write(LAYER_ST_EPI, "epi_1"),
            create_test_write(LAYER_ST_EPI, "epi_2"),
        ]

        result = await router.route_layer(LAYER_ST_EPI, writes, mock_uow)

        assert result.layer == LAYER_ST_EPI
        assert result.writes_succeeded == 2

    @pytest.mark.asyncio
    async def test_route_layer_unknown_raises(
        self,
        writers: Dict[str, StubLayerWriter],
        mock_uow: MagicMock,
    ) -> None:
        """route_layer() raises ValueError for unknown layer in ATOMIC."""
        router = DecisionRouter(layer_writers=writers, mode=WriteMode.ATOMIC)
        writes = [create_test_write("unknown", "x_1")]

        with pytest.raises(ValueError, match="No writer registered"):
            await router.route_layer("unknown", writes, mock_uow)


# =============================================================================
# 5. PROTOCOL TESTS
# =============================================================================


class TestLayerWriterProtocol:
    """Test LayerWriterProtocol compliance."""

    def test_stub_implements_protocol(self) -> None:
        """StubLayerWriter implements LayerWriterProtocol."""
        writer = StubLayerWriter(LAYER_ST_EPI)

        assert isinstance(writer, LayerWriterProtocol)
        assert writer.layer == LAYER_ST_EPI


# =============================================================================
# 6. DECISION ROUTER ERROR TESTS
# =============================================================================


class TestDecisionRouterError:
    """Test DecisionRouterError exception."""

    def test_error_properties(self) -> None:
        """DecisionRouterError exposes result properties."""
        result = LayerWriteResult.failure("st_sem", "error", ["id1", "id2"])
        error = DecisionRouterError("Write failed", result)

        assert error.failed_layer == "st_sem"
        assert error.failed_ids == ["id1", "id2"]
        assert str(error) == "Write failed"
