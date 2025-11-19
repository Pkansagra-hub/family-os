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

        logger.info(
            f"Initialized pipeline runner: {spec.pipeline_id}",
            extra={
                "pipeline_id": spec.pipeline_id,
                "version": spec.version,
                "stage_count": len(self._dag),
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
            # Execute stages in topological order, passing enriched message forward
            current_message = message
            for stage in self._dag.topological_order():
                current_message = await self._execute_stage(stage, current_message)

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

    async def _execute_stage(self, stage: StageSpec, message: BusMessage) -> BusMessage:
        """
        Execute a single DAG stage.

        Args:
            stage: Stage specification
            message: Bus message context (may be enriched from previous stage)

        Returns:
            BusMessage: Updated message with enriched payload (or original if module returned non-dict)

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

            # Parse envelope: use enriched version from previous stage, or decode from message
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
            args["envelope"] = envelope_dict  # Pre-decoded envelope dict for convenience

            # Execute module with timing
            module_start = datetime.now(UTC)
            result = await module_fn(**args)
            module_duration_ms = (datetime.now(UTC) - module_start).total_seconds() * 1000

            # Track stage timing for latency profiling
            self._stage_timings[stage.id] = module_duration_ms

            # If module returned an enriched envelope, store it AND create new message with enriched payload
            # This ensures subsequent stages receive the enriched envelope when they parse message.payload
            if isinstance(result, dict):
                self._enriched_envelope = result  # Store for next stage
                # CRITICAL: Create new BusMessage with enriched payload (BusMessage is frozen)
                import json

                message = BusMessage(
                    topic=message.topic,
                    payload=json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    ),
                    offset=message.offset,
                    trace_id=message.trace_id,
                    space_id=message.space_id,
                    metadata=message.metadata,
                )

            # Track completion
            self._completed_stages.add(stage.id)

            # Return (possibly enriched) message for next stage
            return message

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

        # Return original message if stage failed (exception will propagate anyway)
        return message

    # ===== Observability Helpers =====

    def get_metrics(self) -> Dict[str, Any]:
        """Get pipeline execution metrics (for monitoring)."""
        return {
            "pipeline_id": self.pipeline_id,
            "version": self._spec.version,
            "total_executions": self._execution_count,
            "stage_count": len(self._dag),
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
