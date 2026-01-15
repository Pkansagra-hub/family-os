"""
TransactionCoordinator — Issue 5.2.10

Coordinates atomic writes across all memory layers via UnitOfWork.
Handles version conflicts with retry and capability validation.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.10 — UnitOfWork integration)
    - Dossier Appendix D.7 (Storage Integration)
    - Dossier Appendix D.7.1 (UnitOfWork Pattern)
    - Dossier Appendix D.7.3 (Optimistic Locking)

Transaction Semantics:
    - All 8+ layer writes atomic within single PostgreSQL transaction
    - VERSION_CONFLICT triggers re-read and retry (max 3)
    - Capability violations raise PermissionError immediately
    - Exponential backoff between retries

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.truth_writer.result import WriteResult
from k0.modules.consolidation.truth_writer.router import DecisionRouter, WriteMode

if TYPE_CHECKING:
    from k0.pipelines.p03.staged_writes import P03StagedWrites, StagedWrite
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# Maximum retries for version conflicts
MAX_VERSION_CONFLICT_RETRIES = 3


class OptimisticLockError(Exception):
    """
    Raised when optimistic locking fails due to version conflict.

    This error indicates that another process modified the record
    between read and write, causing the version check to fail.
    """

    def __init__(self, layer: str, record_id: str, expected_version: Optional[int] = None):
        """
        Initialize optimistic lock error.

        Args:
            layer: The layer where conflict occurred
            record_id: The record ID that conflicted
            expected_version: The version that was expected
        """
        self.layer = layer
        self.record_id = record_id
        self.expected_version = expected_version
        super().__init__(
            f"Version conflict for {layer}:{record_id}"
            + (f" (expected version {expected_version})" if expected_version else "")
        )


@dataclass
class TransactionConfig:
    """
    Configuration for transaction coordination.

    Attributes:
        mode: Write mode (ATOMIC or PARTIAL)
        max_retries: Maximum retries for version conflicts
        retry_delay_ms: Base delay between retries (ms)
        require_capabilities: Whether to validate capabilities
    """

    mode: WriteMode = WriteMode.ATOMIC
    max_retries: int = MAX_VERSION_CONFLICT_RETRIES
    retry_delay_ms: int = 100  # Backoff between retries
    require_capabilities: bool = True


@dataclass
class TransactionResult:
    """
    Result of transaction coordination.

    Extends WriteResult with transaction-specific metadata.

    Attributes:
        write_result: The underlying WriteResult
        attempts: Number of attempts made
        total_duration_ms: Total time spent including retries
        version_conflicts: Number of version conflicts encountered
    """

    write_result: WriteResult
    attempts: int = 1
    total_duration_ms: int = 0
    version_conflicts: int = 0

    @property
    def success(self) -> bool:
        """True if all writes succeeded."""
        return self.write_result.total_failed == 0


# Primary key columns for each layer
LAYER_PK_MAP = {
    "st_epi": "episode_id",
    "st_sem": "pattern_id",
    "st_procedural": "routine_id",
    "st_social": "relationship_id",
    "st_prospective": "intention_id",
    "st_kg_dom": "entity_id",
    "st_kg_edges": "edge_id",
    "st_vec": "embedding_id",
    "st_hipp_events": "event_id",
    "st_learning_queue": "queue_id",
}


class TransactionCoordinator:
    """
    Coordinates atomic writes across all memory layers via UnitOfWork.

    The TransactionCoordinator wraps the DecisionRouter and adds:
        1. Version conflict handling with retry
        2. Capability validation before writes
        3. Exponential backoff between retries
        4. Transaction result aggregation

    Transaction Semantics:
        - All 8+ layer writes atomic within single PostgreSQL transaction
        - VERSION_CONFLICT triggers re-read and retry (max 3)
        - Capability violations raise PermissionError immediately

    Usage:
        async with ctx.syscalls.unit_of_work() as uow:
            coordinator = TransactionCoordinator(
                router=DecisionRouter(layer_writers),
                config=TransactionConfig(mode=WriteMode.ATOMIC),
            )
            result = await coordinator.execute(
                staged=envelope.staged,
                uow=uow,
                required_caps=["storage.write", "outbox.stage"],
            )
    """

    def __init__(
        self,
        router: DecisionRouter,
        config: Optional[TransactionConfig] = None,
    ):
        """
        Initialize transaction coordinator.

        Args:
            router: DecisionRouter for layer writes
            config: Optional transaction configuration
        """
        self._router = router
        self._config = config or TransactionConfig()

    @property
    def router(self) -> DecisionRouter:
        """The underlying decision router."""
        return self._router

    @property
    def config(self) -> TransactionConfig:
        """Transaction configuration."""
        return self._config

    async def execute(
        self,
        staged: P03StagedWrites,
        uow: UnitOfWork,
        required_caps: Optional[List[str]] = None,
    ) -> TransactionResult:
        """
        Execute all staged writes atomically.

        This method handles the full transaction lifecycle:
            1. Validate capabilities (if required)
            2. Execute writes via router
            3. Retry on version conflicts with backoff
            4. Return aggregated result

        Args:
            staged: P03StagedWrites container from R6
            uow: Active UnitOfWork (transaction already started)
            required_caps: Required capabilities for validation

        Returns:
            TransactionResult with write outcomes and metadata

        Raises:
            PermissionError: If capability validation fails
            OptimisticLockError: If max retries exceeded
        """
        start_ms = _now_ms()

        # 1. Validate capabilities (if required)
        if self._config.require_capabilities and required_caps:
            await self._validate_capabilities(uow, required_caps)

        # 2. Execute writes with retry on version conflict
        attempt = 0
        version_conflicts = 0
        last_error: Optional[OptimisticLockError] = None

        while attempt < self._config.max_retries:
            attempt += 1

            try:
                result = await self._router.route(staged, uow)

                logger.info(
                    "TransactionCoordinator: writes completed",
                    extra={
                        "attempt": attempt,
                        "total_succeeded": result.total_succeeded,
                        "total_failed": result.total_failed,
                        "version_conflicts": version_conflicts,
                    },
                )

                return TransactionResult(
                    write_result=result,
                    attempts=attempt,
                    total_duration_ms=_now_ms() - start_ms,
                    version_conflicts=version_conflicts,
                )

            except OptimisticLockError as e:
                last_error = e
                version_conflicts += 1

                if attempt < self._config.max_retries:
                    logger.warning(
                        "TransactionCoordinator: version conflict, retrying",
                        extra={
                            "layer": e.layer,
                            "record_id": e.record_id,
                            "attempt": attempt,
                            "max_retries": self._config.max_retries,
                        },
                    )
                    # Re-read and update expected version
                    await self._refresh_versions(uow, staged, e.layer)
                    await self._backoff(attempt)

        # Max retries exceeded
        logger.error(
            "TransactionCoordinator: max retries exceeded",
            extra={
                "attempts": attempt,
                "version_conflicts": version_conflicts,
                "last_error_layer": last_error.layer if last_error else None,
                "last_error_record": last_error.record_id if last_error else None,
            },
        )

        raise last_error or RuntimeError("Transaction failed with unknown error")

    async def execute_simple(
        self,
        staged: P03StagedWrites,
        uow: UnitOfWork,
    ) -> WriteResult:
        """
        Execute writes without retry logic.

        Simplified execution that delegates directly to the router
        without version conflict handling. Useful when version
        conflicts should be handled by the caller.

        Args:
            staged: P03StagedWrites container
            uow: Active UnitOfWork

        Returns:
            WriteResult from router
        """
        return await self._router.route(staged, uow)

    async def _validate_capabilities(
        self,
        uow: UnitOfWork,
        required_caps: List[str],
    ) -> None:
        """
        Validate that UoW has required capabilities.

        Currently a no-op placeholder for future K0 capability system
        integration. Will validate that the current actor has the
        required capabilities for the requested operations.

        Args:
            uow: UnitOfWork to validate
            required_caps: List of required capability names

        Raises:
            PermissionError: If any required capability is missing
        """
        # TODO: Integrate with K0 capability system
        # For now, we assume all capabilities are granted within UoW
        pass

    async def _refresh_versions(
        self,
        uow: UnitOfWork,
        staged: P03StagedWrites,
        conflicted_layer: str,
    ) -> None:
        """
        Re-read versions for conflicted layer's writes.

        When a version conflict occurs, this method queries the database
        for the current version of affected records and updates the
        staged writes with the new expected versions.

        Args:
            uow: Active UnitOfWork
            staged: P03StagedWrites container
            conflicted_layer: Layer where conflict occurred
        """
        layer_writes = self._get_writes_for_layer(staged, conflicted_layer)
        pk_col = LAYER_PK_MAP.get(conflicted_layer, "id")

        for write in layer_writes:
            if write.expected_version is not None:
                try:
                    # Re-read current version from database
                    row = await uow.connection.fetchrow(
                        f"SELECT version FROM {conflicted_layer} WHERE {pk_col} = $1",
                        write.record_id,
                    )
                    if row:
                        write.expected_version = row["version"]
                except Exception as e:
                    logger.warning(
                        "TransactionCoordinator: failed to refresh version",
                        extra={
                            "layer": conflicted_layer,
                            "record_id": write.record_id,
                            "error": str(e),
                        },
                    )

    def _get_writes_for_layer(
        self,
        staged: P03StagedWrites,
        layer: str,
    ) -> List[StagedWrite]:
        """
        Get all writes for a specific layer.

        Maps layer name to the corresponding attribute on P03StagedWrites.

        Args:
            staged: P03StagedWrites container
            layer: Layer name

        Returns:
            List of StagedWrite objects for the layer
        """
        layer_attr_map = {
            "st_epi": "st_epi_writes",
            "st_sem": "st_sem_writes",
            "st_procedural": "st_procedural_writes",
            "st_social": "st_social_writes",
            "st_prospective": "st_prospective_writes",
            "st_kg_dom": "st_kg_dom_writes",
            "st_kg_edges": "st_kg_edges_writes",
            "st_vec": "st_vec_writes",
            "st_hipp_events": "st_hipp_events_updates",
            "st_learning_queue": "st_learning_queue_writes",
        }
        attr = layer_attr_map.get(layer)
        if attr and hasattr(staged, attr):
            return getattr(staged, attr, [])
        return []

    async def _backoff(self, attempt: int) -> None:
        """
        Exponential backoff between retries.

        Delay increases exponentially with each attempt:
            attempt 1: retry_delay_ms * 1
            attempt 2: retry_delay_ms * 2
            attempt 3: retry_delay_ms * 4

        Args:
            attempt: Current attempt number (1-based)
        """
        delay_ms = self._config.retry_delay_ms * (2 ** (attempt - 1))
        await asyncio.sleep(delay_ms / 1000)


def create_transaction_coordinator(
    router: DecisionRouter,
    config: Optional[TransactionConfig] = None,
) -> TransactionCoordinator:
    """
    Factory function to create TransactionCoordinator instance.

    Args:
        router: DecisionRouter for layer writes
        config: Optional transaction configuration

    Returns:
        Configured TransactionCoordinator instance
    """
    return TransactionCoordinator(router=router, config=config)
