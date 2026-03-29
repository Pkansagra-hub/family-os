"""P08 Embedding Lifecycle Management -- 3-Stage Sequential Runner.

Custom pipeline runner for P08 that executes 3 maintenance stages
sequentially with stage-level fault isolation:

    stage_10_backfill  -> M25 embedding.backfill:v2
    stage_20_cleanup   -> M27 embedding.cleanup:v2
    stage_30_integrity -> M28 embedding.integrity_check:v1

Key design decisions:
    - Sequential execution (backfill first, then cleanup, then integrity)
    - Stage failure does NOT block subsequent stages (independent operations)
    - Each stage receives trigger context (tenant_id, space_id, batch_size)
    - Aggregate results returned with per-stage status

Contract: k0/contracts/pipelines/p08_embedding_management.v3.yaml
ADR: ADR-K003 v2.0 (pgvector Migration Decision)
Milestone: M4 Epic 4.20
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.runtime.module_registry import ModuleRegistry
    from k0.runtime.schemas import PipelineSpec

logger = logging.getLogger(__name__)


class P08Runner:
    """P08 Embedding Lifecycle Management -- 3-Stage Sequential Runner.

    Executes P08 maintenance stages sequentially with fault isolation.
    Each stage runs independently: a failure in stage_10 (backfill) does
    not prevent stage_20 (cleanup) or stage_30 (integrity) from running.

    This differs from the generic PipelineRunner which propagates stage
    failures and aborts the pipeline. P08 stages are independent maintenance
    operations that should all run regardless of individual failures.

    Usage (via runner_factory):
        # In p08_embedding_management.v3.yaml:
        #   runner_type: "custom"
        #   runner_class: "k0.pipelines.p08.runner:P08Runner"
        spec = PipelineSpec.load("p08_embedding_management.v3.yaml")
        runner = P08Runner(spec, registry)
        await runner.on_startup(ctx)
        await runner.handle(trigger_message)
    """

    def __init__(self, spec: PipelineSpec, registry: ModuleRegistry) -> None:
        self._spec = spec
        self._registry = registry
        self._context: Any = None
        self._execution_count = 0

        logger.info(
            "P08Runner initialized",
            extra={
                "pipeline_id": spec.pipeline_id,
                "version": spec.version,
                "stage_count": len(spec.dag),
                "stage_ids": [s.id for s in spec.dag],
            },
        )

    # -- PipelineProtocol properties --

    @property
    def pipeline_id(self) -> str:
        return self._spec.pipeline_id

    @property
    def declared_topics(self) -> tuple[str, ...]:
        return self._spec.declared_topics

    @property
    def concurrency(self) -> int:
        return self._spec.concurrency

    @property
    def max_queue(self) -> int:
        return self._spec.max_queue

    @property
    def required_caps(self) -> tuple[str, ...]:
        return self._spec.required_caps

    @property
    def contract_version(self) -> int:
        return self._spec.contract_version

    # -- Lifecycle --

    async def on_startup(self, ctx: Any) -> None:
        """Initialize pipeline context (called once at kernel boot)."""
        self._context = ctx
        logger.info(
            "P08Runner startup",
            extra={"pipeline_id": self.pipeline_id},
        )

    async def on_shutdown(self) -> None:
        """Cleanup on kernel shutdown."""
        logger.info(
            "P08Runner shutdown",
            extra={
                "pipeline_id": self.pipeline_id,
                "total_executions": self._execution_count,
            },
        )

    # -- Execution --

    async def handle(self, message: Any) -> dict[str, Any]:
        """Execute P08 3-stage DAG with stage-level fault isolation.

        Parses the trigger message, then runs each stage sequentially.
        Stage failures are caught and logged but do not block subsequent stages.

        Args:
            message: BusMessage from scheduler trigger (contains trigger context)

        Returns:
            Aggregate results dict with per-stage outcomes and pipeline summary.
        """
        self._execution_count += 1
        run_id = str(uuid.uuid4())
        pipeline_start = time.monotonic()

        # Parse trigger payload
        try:
            payload_bytes = message.payload
            if isinstance(payload_bytes, bytes):
                trigger_payload = json.loads(payload_bytes.decode("utf-8"))
            elif isinstance(payload_bytes, str):
                trigger_payload = json.loads(payload_bytes)
            else:
                trigger_payload = {}
        except (json.JSONDecodeError, AttributeError):
            trigger_payload = {}

        trigger_context = trigger_payload.get("context", {})
        tenant_id = trigger_context.get("tenant_id", "default")
        space_id = trigger_context.get("space_id", "default")

        logger.info(
            "P08 pipeline execution started",
            extra={
                "pipeline_id": self.pipeline_id,
                "run_id": run_id,
                "execution_count": self._execution_count,
                "trigger_id": trigger_payload.get("trigger_id"),
                "tenant_id": tenant_id,
                "space_id": space_id,
                "trace_id": getattr(message, "trace_id", None),
            },
        )

        # Build envelope for modules that need tenant/space context
        envelope = {
            "payload": {
                "tenant_id": tenant_id,
                "space_id": space_id,
            },
            "header": {
                "pipeline_id": self.pipeline_id,
                "run_id": run_id,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # Execute stages sequentially with fault isolation
        stage_results: dict[str, dict[str, Any]] = {}
        completed_count = 0
        failed_count = 0

        for stage in self._spec.dag:
            stage_start = time.monotonic()
            stage_id = stage.id

            try:
                # Resolve module from registry
                module_fn = self._registry.get(stage.module)

                # Call module with standard signature:
                #   run(message, context, envelope=None, **config)
                result = await module_fn(
                    message=message,
                    context=self._context,
                    envelope=envelope,
                    **stage.config,
                )

                stage_duration_ms = (time.monotonic() - stage_start) * 1000
                stage_results[stage_id] = {
                    "status": "completed",
                    "result": result,
                    "duration_ms": round(stage_duration_ms, 3),
                }
                completed_count += 1

                logger.info(
                    f"P08 stage completed: {stage_id}",
                    extra={
                        "pipeline_id": self.pipeline_id,
                        "run_id": run_id,
                        "stage_id": stage_id,
                        "stage_module": stage.module,
                        "duration_ms": round(stage_duration_ms, 3),
                        "result_keys": list(result.keys()) if isinstance(result, dict) else [],
                    },
                )

            except Exception as exc:
                stage_duration_ms = (time.monotonic() - stage_start) * 1000
                stage_results[stage_id] = {
                    "status": "failed",
                    "error": str(exc),
                    "duration_ms": round(stage_duration_ms, 3),
                }
                failed_count += 1

                logger.error(
                    f"P08 stage failed: {stage_id} (continuing to next stage)",
                    exc_info=True,
                    extra={
                        "pipeline_id": self.pipeline_id,
                        "run_id": run_id,
                        "stage_id": stage_id,
                        "stage_module": stage.module,
                        "error": str(exc),
                        "duration_ms": round(stage_duration_ms, 3),
                    },
                )
                # Stage failure does NOT block subsequent stages

        pipeline_duration_ms = (time.monotonic() - pipeline_start) * 1000
        pipeline_status = "completed" if failed_count == 0 else "partial"

        logger.info(
            f"P08 pipeline execution {pipeline_status}",
            extra={
                "pipeline_id": self.pipeline_id,
                "run_id": run_id,
                "status": pipeline_status,
                "completed_stages": completed_count,
                "failed_stages": failed_count,
                "total_stages": len(self._spec.dag),
                "duration_ms": round(pipeline_duration_ms, 3),
                "trace_id": getattr(message, "trace_id", None),
            },
        )

        return {
            "pipeline_id": self.pipeline_id,
            "run_id": run_id,
            "status": pipeline_status,
            "stages": stage_results,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "total_stages": len(self._spec.dag),
            "duration_ms": round(pipeline_duration_ms, 3),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
