"""
DecisionRouter — Issue 5.2.1

Routes consolidation decisions to appropriate layer writers
based on ReconciliationAction and target layer.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.1 — M24 TruthWriter module scaffolding)
    - Dossier §4.8 (R7 — Memory Layer Writes / Truth Update)
    - Dossier §7.4.7 (M24 — TruthWriter module)

DESIGN DECISIONS:
    - Writes grouped by layer for batch execution efficiency
    - ATOMIC mode rolls back entire batch on any failure
    - PARTIAL mode continues on failure, records failed IDs
    - Dependency order enforced by P03StagedWrites.get_all_writes_ordered()

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Mapping, Protocol, runtime_checkable

from k0.modules.consolidation.truth_writer.result import LayerWriteResult, WriteResult
from k0.pipelines.p03.staged_writes import StagedWrite

if TYPE_CHECKING:
    from k0.pipelines.p03.staged_writes import P03StagedWrites
    from k0.uow.unit_of_work import UnitOfWork


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


class WriteMode(Enum):
    """
    Write mode for decision routing.

    ATOMIC: Rollback entire batch on any failure (default)
    PARTIAL: Continue on failure, record failed IDs for retry
    """

    ATOMIC = "ATOMIC"
    PARTIAL = "PARTIAL"


@runtime_checkable
class LayerWriterProtocol(Protocol):
    """
    Protocol for layer-specific writers.

    Each layer writer implements this protocol to handle
    writes to a specific truth layer table (st_epi, st_sem, etc.).
    """

    @property
    def layer(self) -> str:
        """Target layer name (e.g., 'st_epi')."""
        ...

    async def write(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Execute writes to this layer.

        Args:
            writes: List of StagedWrite objects for this layer
            uow: UnitOfWork for transactional context

        Returns:
            LayerWriteResult with success/failure counts
        """
        ...


class DecisionRouter:
    """
    Route consolidation decisions to appropriate layer writers.

    The router takes staged writes from P03StagedWrites and distributes
    them to registered layer writers. Writes are executed in dependency
    order (from get_all_writes_ordered) to satisfy foreign key constraints.

    Write Modes:
        ATOMIC: All or nothing - any failure rolls back entire batch
        PARTIAL: Continue on failure, record failed IDs for retry

    ReconciliationAction → Layer Mapping:
        CREATE: st_epi, st_sem, st_kg_dom (new truth records)
        EXTEND: st_epi, st_sem, st_kg_dom, st_kg_edges (append to existing)
        REINFORCE: st_sem, st_procedural (increment observation_count)
        EVOLVE: st_sem, st_kg_dom (new version, mark old non-canonical)
        PRUNE: All layers (soft-delete with reason)
        SKIP: st_hipp_events only (mark as DUPLICATE)
    """

    def __init__(
        self,
        layer_writers: Mapping[str, LayerWriterProtocol],
        mode: WriteMode = WriteMode.ATOMIC,
    ):
        """
        Initialize decision router.

        Args:
            layer_writers: Dict mapping layer name to writer implementation
            mode: Write mode (ATOMIC or PARTIAL)
        """
        self._writers = dict(layer_writers)
        self._mode = mode

    @property
    def registered_layers(self) -> List[str]:
        """List of registered layer names."""
        return list(self._writers.keys())

    @property
    def mode(self) -> WriteMode:
        """Current write mode."""
        return self._mode

    def has_writer(self, layer: str) -> bool:
        """Check if a writer is registered for the given layer."""
        return layer in self._writers

    def get_writer(self, layer: str) -> LayerWriterProtocol | None:
        """Get the writer for a specific layer."""
        return self._writers.get(layer)

    async def route(
        self,
        staged: P03StagedWrites,
        uow: UnitOfWork,
    ) -> WriteResult:
        """
        Route all staged writes to layer writers in dependency order.

        Dependency order (from P03StagedWrites.get_all_writes_ordered):
            vec → kg_dom → kg_edges → epi → sem →
            procedural → social → prospective →
            learning_queue → hipp_events

        Args:
            staged: P03StagedWrites container with accumulated writes
            uow: UnitOfWork for transactional context

        Returns:
            WriteResult aggregating all layer outcomes

        Raises:
            ValueError: If write targets unknown layer (in ATOMIC mode)
            Exception: Any write error (in ATOMIC mode, triggers rollback)
        """
        results: List[LayerWriteResult] = []
        all_writes = staged.get_all_writes_ordered()

        if not all_writes:
            return WriteResult.empty()

        # Group writes by layer for efficient batch processing
        writes_by_layer = self._group_by_layer(all_writes)

        # Process in the order they appear (already dependency-ordered)
        layer_order = self._extract_layer_order(all_writes)

        for layer in layer_order:
            layer_writes = writes_by_layer.get(layer, [])
            if not layer_writes:
                continue

            result = await self._process_layer(layer, layer_writes, uow)
            results.append(result)

            # In ATOMIC mode, stop on first failure
            if self._mode == WriteMode.ATOMIC and not result.is_success:
                # Rollback is handled by UoW context manager
                raise DecisionRouterError(
                    f"Write failed for layer {layer}: {result.error_message}",
                    result,
                )

        return WriteResult.from_layer_results(results)

    async def route_layer(
        self,
        layer: str,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Route writes to a specific layer (for targeted writes).

        Args:
            layer: Target layer name
            writes: List of writes for this layer
            uow: UnitOfWork for transactional context

        Returns:
            LayerWriteResult for this layer

        Raises:
            ValueError: If layer has no registered writer
        """
        return await self._process_layer(layer, writes, uow)

    async def _process_layer(
        self,
        layer: str,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Process writes for a single layer.

        Args:
            layer: Target layer name
            writes: Writes to process
            uow: UnitOfWork for transactional context

        Returns:
            LayerWriteResult with outcomes
        """
        # Skip layers that are handled externally (e.g., st_hipp_events is updated
        # directly in R7 via _update_event_consolidation_status)
        EXTERNALLY_HANDLED_LAYERS = {"st_hipp_events"}
        if layer in EXTERNALLY_HANDLED_LAYERS:
            return LayerWriteResult(
                layer=layer,
                writes_attempted=len(writes),
                writes_succeeded=len(writes),  # Pretend success - handled elsewhere
                writes_failed=0,
                failed_ids=[],
                error_message=None,
            )

        writer = self._writers.get(layer)
        if writer is None:
            if self._mode == WriteMode.ATOMIC:
                raise ValueError(f"No writer registered for layer: {layer}")
            # PARTIAL mode: record as failure
            return LayerWriteResult.failure(
                layer=layer,
                error=f"No writer registered for layer: {layer}",
                failed_ids=[w.record_id for w in writes],
            )

        start_ms = _now_ms()
        try:
            result = await writer.write(writes, uow)
            result.duration_ms = _now_ms() - start_ms
            return result
        except Exception as e:
            if self._mode == WriteMode.ATOMIC:
                raise
            # PARTIAL mode: record failure and continue
            return LayerWriteResult.failure(
                layer=layer,
                error=str(e),
                failed_ids=[w.record_id for w in writes],
            )

    def _group_by_layer(
        self,
        writes: List[StagedWrite],
    ) -> Dict[str, List[StagedWrite]]:
        """Group writes by target layer."""
        result: Dict[str, List[StagedWrite]] = {}
        for write in writes:
            if write.layer not in result:
                result[write.layer] = []
            result[write.layer].append(write)
        return result

    def _extract_layer_order(self, writes: List[StagedWrite]) -> List[str]:
        """Extract unique layers in order of first appearance."""
        seen: set[str] = set()
        order: List[str] = []
        for write in writes:
            if write.layer not in seen:
                seen.add(write.layer)
                order.append(write.layer)
        return order


class DecisionRouterError(Exception):
    """
    Error raised when decision routing fails in ATOMIC mode.

    Includes the partial result for diagnostics.
    """

    def __init__(self, message: str, result: LayerWriteResult):
        super().__init__(message)
        self.result = result

    @property
    def failed_layer(self) -> str:
        """Layer that caused the failure."""
        return self.result.layer

    @property
    def failed_ids(self) -> List[str]:
        """Record IDs that failed."""
        return self.result.failed_ids


def create_decision_router(
    layer_writers: Mapping[str, LayerWriterProtocol],
    mode: WriteMode = WriteMode.ATOMIC,
) -> DecisionRouter:
    """
    Factory function to create a DecisionRouter.

    Args:
        layer_writers: Dict mapping layer name to writer implementation
        mode: Write mode (ATOMIC or PARTIAL)

    Returns:
        Configured DecisionRouter
    """
    return DecisionRouter(layer_writers=layer_writers, mode=mode)
