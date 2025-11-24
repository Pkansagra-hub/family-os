"""
Pipeline Runner - Generic DAG Executor

Executes declarative pipelines by orchestrating module calls through a DAG.
Implements PipelineProtocol for seamless integration with existing kernel.

Related:
- MIGRATION_PLAN.md: Phase 2 - Generic Runner
- k0/pipelines/protocol.py: PipelineProtocol interface
- k0/runtime/dag_builder.py: DAG construction
- k0/runtime/module_registry.py: Module lookup
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from k0.bus.core import BusMessage
from k0.pipelines.protocol import PipelineContext

from .dag_builder import build_dag
from .module_registry import ModuleRegistry
from .schemas import PipelineSpec, StageSpec

if TYPE_CHECKING:
    from typing import Dict

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Generic pipeline executor for declarative YAML-based pipelines.

    Implements PipelineProtocol via instance properties for seamless kernel integration.
    Orchestrates module execution through topological DAG traversal.

    Usage:
        >>> spec = PipelineSpec.load("p02_write.v1.yaml")
        >>> registry = ModuleRegistry()
        >>> await registry.load_contracts("k0/contracts/modules")
        >>> runner = PipelineRunner(spec, registry)
        >>> await runner.on_startup(context)
        >>> await runner.handle(bus_message)
    """

    def __init__(self, spec: PipelineSpec, registry: ModuleRegistry) -> None:
        """
        Initialize pipeline runner from specification.

        Args:
            spec: Validated pipeline specification
            registry: Module registry for dynamic module lookup
        """
        self._spec = spec
        self._registry = registry
        self._dag = build_dag(spec)
        self._context: PipelineContext | None = None

        # Execution tracking
        self._completed_stages: set[str] = set()
        self._failed_stages: set[str] = set()
        self._execution_count = 0

        # Compute parallel execution plan
        self._level_groups = self._dag.get_level_groups()
        self._max_parallelism = (
            max(len(group) for group in self._level_groups) if self._level_groups else 0
        )

        logger.info(
            f"Initialized pipeline runner: {spec.pipeline_id}",
            extra={
                "pipeline_id": spec.pipeline_id,
                "version": spec.version,
                "stage_count": len(self._dag),
                "execution_levels": len(self._level_groups),
                "max_parallelism": self._max_parallelism,
                "subscribed_topics": list(spec.declared_topics),
            },
        )

    # ===== PipelineProtocol Implementation (Instance Properties) =====

    @property
    def pipeline_id(self) -> str:
        """Unique identifier for this pipeline."""
        return self._spec.pipeline_id

    @property
    def contract_version(self) -> int:
        """Schema version for compatibility checking."""
        return self._spec.contract_version

    @property
    def declared_topics(self) -> tuple[str, ...]:
        """Topics this pipeline subscribes to."""
        return self._spec.declared_topics

    @property
    def concurrency(self) -> int:
        """Max concurrent handlers for this pipeline."""
        return self._spec.concurrency

    @property
    def max_queue(self) -> int:
        """Max pending messages before backpressure."""
        return self._spec.max_queue

    @property
    def required_caps(self) -> tuple[str, ...]:
        """Capability requirements (computed from spec)."""
        return self._spec.required_caps

    # ===== Lifecycle Methods (PipelineProtocol) =====

    async def on_startup(self, ctx: PipelineContext) -> None:
        """
        Initialize pipeline resources (called once at kernel boot).

        Args:
            ctx: PipelineContext with syscalls, config, logger
        """
        self._context = ctx

        ctx.logger.info(
            f"Pipeline startup: {self.pipeline_id}",
            extra={"pipeline_id": self.pipeline_id, "version": self._spec.version},
        )

        # Future: Pre-load modules, warm caches, validate registry

    async def on_shutdown(self) -> None:
        """Pipeline cleanup (called by kernel at shutdown)."""
        if self._context:
            self._context.logger.info(
                f"Pipeline shutdown: {self.pipeline_id}",
                extra={
                    "pipeline_id": self.pipeline_id,
                    "total_executions": self._execution_count,
                },
            )

        # Future: Flush buffers, close connections

    async def handle(self, message: BusMessage) -> None:
        """
        Execute pipeline for incoming message (PipelineProtocol requirement).

        Args:
            message: Bus message triggering pipeline execution
        """
        if message.topic not in self.declared_topics:
            if self._context:
                self._context.logger.warning(
                    f"Ignoring message - topic not subscribed: {message.topic}",
                    extra={
                        "pipeline_id": self.pipeline_id,
                        "topic": message.topic,
                        "trace_id": message.trace_id,
                    },
                )
            return

        self._execution_count += 1
        start_time = datetime.now(UTC)

        # Reset per-execution state
        self._completed_stages.clear()
        self._failed_stages.clear()
        self._enriched_envelope = None  # Track enriched envelope across stages
        self._stage_timings = {}  # Track per-stage latency for profiling

        if self._context:
            self._context.logger.debug(
                f"Starting pipeline execution: {self.pipeline_id}",
                extra={
                    "pipeline_id": self.pipeline_id,
                    "topic": message.topic,
                    "trace_id": message.trace_id,
                    "space_id": message.space_id,
                },
            )

        try:
            # Execute DAG levels: stages within each level run in parallel
            for level_idx, level_stages in enumerate(self._level_groups):
                level_start = datetime.now(UTC)

                if self._context:
                    self._context.logger.debug(
                        f"Executing level {level_idx}: {len(level_stages)} stages in parallel",
                        extra={
                            "pipeline_id": self.pipeline_id,
                            "level": level_idx,
                            "stage_count": len(level_stages),
                            "stage_ids": [s.id for s in level_stages],
                            "trace_id": message.trace_id,
                        },
                    )

                # Execute all stages in this level concurrently
                if len(level_stages) == 1:
                    # Optimization: single stage, no need for gather overhead
                    await self._execute_stage(level_stages[0], message)
                else:
                    # Parallel execution within level
                    await asyncio.gather(
                        *[self._execute_stage(stage, message) for stage in level_stages],
                        return_exceptions=False,  # Propagate first exception immediately
                    )

                level_duration_ms = (datetime.now(UTC) - level_start).total_seconds() * 1000

                if self._context:
                    self._context.logger.debug(
                        f"Level {level_idx} completed",
                        extra={
                            "pipeline_id": self.pipeline_id,
                            "level": level_idx,
                            "duration_ms": round(level_duration_ms, 3),
                            "completed_stages": [s.id for s in level_stages],
                            "trace_id": message.trace_id,
                        },
                    )

            # Success
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            if self._context:
                self._context.logger.info(
                    f"Pipeline completed: {self.pipeline_id}",
                    extra={
                        "pipeline_id": self.pipeline_id,
                        "trace_id": message.trace_id,
                        "duration_ms": round(duration_ms, 3),
                        "completed_stages": len(self._completed_stages),
                        "execution_levels": len(self._level_groups),
                        "stage_timings_ms": {
                            k: round(v, 3) for k, v in self._stage_timings.items()
                        },
                    },
                )

        except Exception as e:
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            if self._context:
                self._context.logger.error(
                    f"Pipeline failed: {self.pipeline_id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self.pipeline_id,
                        "trace_id": message.trace_id,
                        "error": str(e),
                        "duration_ms": duration_ms,
                        "completed_stages": len(self._completed_stages),
                        "failed_stages": len(self._failed_stages),
                    },
                )

            # Re-raise to allow kernel error handling
            raise

    # ===== Stage Execution =====

    async def _execute_stage(self, stage: StageSpec, message: BusMessage) -> None:
        """
        Execute a single DAG stage.

        Parallel-safe: Multiple stages can execute concurrently, each reading from
        the shared enriched envelope and writing their outputs back atomically.

        Args:
            stage: Stage specification
            message: Bus message context (original message from bus)

        Raises:
            Exception: Stage execution failures (propagated to caller)
        """
        stage_start = datetime.now(UTC)

        if self._context:
            self._context.logger.debug(
                f"Executing stage: {stage.id}",
                extra={
                    "pipeline_id": self.pipeline_id,
                    "stage_id": stage.id,
                    "module_id": stage.module,
                    "trace_id": message.trace_id,
                },
            )

        try:
            # Get module implementation
            module_fn = self._registry.get(stage.module)

            # Parse envelope: use enriched version (shared across parallel stages)
            if self._enriched_envelope is not None:
                envelope_dict = self._enriched_envelope
            else:
                import json

                try:
                    envelope_dict = json.loads(message.payload.decode("utf-8"))
                except (json.JSONDecodeError, AttributeError) as e:
                    if self._context:
                        self._context.logger.error(
                            f"Failed to decode BusMessage payload for stage {stage.id}",
                            exc_info=True,
                            extra={
                                "stage_id": stage.id,
                                "module_id": stage.module,
                                "error": str(e),
                            },
                        )
                    raise

            # Prepare arguments (merge stage config + message context + envelope)
            args = dict(stage.config)
            args["message"] = message  # BusMessage with .payload (bytes)
            args["context"] = self._context
            # Pass the enriched envelope if available, otherwise use original
            args["envelope"] = (
                self._enriched_envelope if self._enriched_envelope is not None else envelope_dict
            )

            # Debug: log what envelope is being passed
            if self._context and stage.id == "stage_70_atomic_writer":
                has_hipp_row = "hipp_events_row" in args["envelope"]
                self._context.logger.debug(
                    f"Stage_70 receiving envelope: has_hipp_events_row={has_hipp_row}, total_keys={len(args['envelope'])}, enriched_envelope_id={id(self._enriched_envelope)}, args_envelope_id={id(args['envelope'])}",
                    extra={
                        "stage_id": stage.id,
                        "has_hipp_events_row": has_hipp_row,
                        "envelope_keys": list(args["envelope"].keys())[:20],
                    },
                )

            # Execute module with timing
            module_start = datetime.now(UTC)
            result = await module_fn(**args)
            module_duration_ms = (datetime.now(UTC) - module_start).total_seconds() * 1000

            # Track stage timing for latency profiling
            self._stage_timings[stage.id] = module_duration_ms

            # Merge module result back into shared enriched envelope
            # This allows parallel stages to contribute independently
            if isinstance(result, dict):
                if self._enriched_envelope is None:
                    self._enriched_envelope = envelope_dict.copy()
                # Deep merge: module outputs are overlaid onto enriched envelope
                self._enriched_envelope.update(result)

                # Debug logging for enrichment tracking
                if self._context:
                    self._context.logger.debug(
                        f"Stage {stage.id} enriched envelope with {len(result)} keys: {list(result.keys())}",
                        extra={
                            "stage_id": stage.id,
                            "enrichment_keys": list(result.keys()),
                            "total_envelope_keys": len(self._enriched_envelope),
                        },
                    )

            # Track completion
            self._completed_stages.add(stage.id)

        except Exception as e:
            self._failed_stages.add(stage.id)

            if self._context:
                self._context.logger.error(
                    f"Stage failed: {stage.id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self.pipeline_id,
                        "stage_id": stage.id,
                        "module_id": stage.module,
                        "error": str(e),
                    },
                )

            # Re-raise to caller for pipeline-level error handling
            raise

    # ===== Observability Helpers =====

    def get_metrics(self) -> Dict[str, Any]:
        """Get pipeline execution metrics (for monitoring)."""
        return {
            "pipeline_id": self.pipeline_id,
            "version": self._spec.version,
            "total_executions": self._execution_count,
            "stage_count": len(self._dag),
            "execution_levels": len(self._level_groups),
            "max_parallelism": self._max_parallelism,
            "last_completed_stages": len(self._completed_stages),
            "last_failed_stages": len(self._failed_stages),
        }


# ===== Factory Function =====


async def create_pipeline_runner(
    spec_path: str,
    registry: ModuleRegistry,
) -> PipelineRunner:
    """
    Factory for creating pipeline runners from YAML specifications.

    Args:
        spec_path: Path to pipeline YAML spec
        registry: Initialized module registry

    Returns:
        PipelineRunner ready for on_startup() call

    Usage:
        >>> registry = ModuleRegistry()
        >>> await registry.load_contracts("k0/contracts/modules")
        >>> runner = await create_pipeline_runner("p02_write.v1.yaml", registry)
        >>> await runner.on_startup(context)
    """
    spec = PipelineSpec.load(spec_path)
    return PipelineRunner(spec, registry)
