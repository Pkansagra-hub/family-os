"""
Sequential Runner Adapter — Adapts Sequential Runners to RunnerProtocol

This adapter wraps pipeline-specific sequential runners (like P03SequentialRunner)
to conform to the generic RunnerProtocol expected by the kernel.

The kernel doesn't know about P03-specific concepts like phases, batch envelopes,
or runner contexts. This adapter translates between the generic kernel interface
and the pipeline-specific runner implementation.

Architecture:
    Kernel (generic) -> SequentialRunnerAdapter -> P03SequentialRunner (specific)

    Kernel calls: adapter.handle(BusMessage)
    Adapter calls: sequential_runner.run_cycle(P03RunnerContext)

Related:
- k0/runtime/runner_factory.py: Factory that creates this adapter
- k0/pipelines/p03/sequential_runner.py: Example sequential runner
- k0/pipelines/p03/phase_interface.py: Phase protocol and context
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Type

if TYPE_CHECKING:
    from k0.bus.core import BusMessage
    from k0.pipelines.protocol import PipelineContext
    from k0.runtime.module_registry import ModuleRegistry
    from k0.runtime.schemas import PipelineSpec

logger = logging.getLogger(__name__)


P03_SOURCE_SCOPE_TABLE = "st_hipp_events"


class SequentialRunnerAdapter:
    """
    Adapter that wraps a sequential runner for kernel compatibility.

    This adapter:
    1. Implements RunnerProtocol (handle, on_startup, on_shutdown)
    2. Translates BusMessage to pipeline-specific context
    3. Delegates actual execution to the wrapped sequential runner

    The adapter is instantiated by RunnerFactory when runner_type='sequential'.
    """

    def __init__(
        self,
        spec: "PipelineSpec",
        runner_class: Type[Any],
        registry: "ModuleRegistry",
    ) -> None:
        """
        Initialize the adapter.

        Args:
            spec: Pipeline specification
            runner_class: The sequential runner class to wrap
            registry: Module registry (may not be used by sequential runners)
        """
        self._spec = spec
        self._runner_class = runner_class
        self._registry = registry
        self._runner: Any = None
        self._ctx: Any = None
        self._phases: dict[str, Any] = {}

    @property
    def declared_topics(self) -> tuple[str, ...]:
        """Topics this runner subscribes to."""
        if self._spec.entry_topic:
            return (self._spec.entry_topic,)
        return ()

    async def on_startup(self, ctx: "PipelineContext") -> None:
        """
        Initialize the sequential runner.

        This method:
        1. Stores the pipeline context
        2. Loads phase implementations
        3. Instantiates the sequential runner with phases
        """
        self._ctx = ctx
        pipeline_id = self._spec.pipeline_id

        logger.info(
            f"Initializing sequential runner for {pipeline_id}",
            extra={"pipeline_id": pipeline_id},
        )

        # Load phase implementations based on pipeline
        # Convention: k0.pipelines.<prefix>.phases module exports PHASE_REGISTRY
        pipeline_prefix = pipeline_id.split("_")[0].lower()  # "P03_CONSOLIDATION" -> "p03"

        try:
            phases_module_path = f"k0.pipelines.{pipeline_prefix}.phases"
            import importlib

            phases_module = importlib.import_module(phases_module_path)

            # Look for PHASE_REGISTRY or phase classes
            phase_registry = getattr(phases_module, "PHASE_REGISTRY", None)
            if phase_registry:
                self._phases = phase_registry
                logger.info(
                    f"Loaded {len(self._phases)} phases from {phases_module_path}",
                    extra={
                        "pipeline_id": pipeline_id,
                        "phases": (
                            list(self._phases.keys()) if isinstance(self._phases, dict) else "list"
                        ),
                    },
                )
            else:
                # Try to collect phase classes directly
                self._phases = self._discover_phases(phases_module)
                logger.info(
                    f"Discovered {len(self._phases)} phases from {phases_module_path}",
                    extra={"pipeline_id": pipeline_id},
                )

        except ImportError as e:
            logger.warning(
                f"Cannot import phases module for {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id, "error": str(e)},
            )
            self._phases = {}

        # Instantiate the sequential runner
        # P03SequentialRunner expects phases: Dict[P03PhaseId, P03PhaseProtocol]
        try:
            self._runner = self._runner_class(phases=self._phases)
            logger.info(
                f"Instantiated {self._runner_class.__name__} for {pipeline_id}",
                extra={
                    "pipeline_id": pipeline_id,
                    "phase_count": len(self._phases),
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to instantiate sequential runner for {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id, "error": str(e)},
            )
            raise

    async def on_shutdown(self) -> None:
        """Cleanup the sequential runner."""
        pipeline_id = self._spec.pipeline_id
        logger.info(
            f"Shutting down sequential runner for {pipeline_id}",
            extra={"pipeline_id": pipeline_id},
        )
        self._runner = None
        self._ctx = None

    async def handle(self, message: "BusMessage") -> None:
        """
        Handle an incoming trigger message.

        This translates the generic BusMessage into a pipeline-specific
        execution context and delegates to the sequential runner.
        """
        import json
        import uuid

        pipeline_id = self._spec.pipeline_id

        if self._runner is None:
            logger.error(
                f"Sequential runner not initialized for {pipeline_id}",
                extra={"pipeline_id": pipeline_id},
            )
            return

        logger.info(
            f"Handling message for {pipeline_id}",
            extra={
                "pipeline_id": pipeline_id,
                "topic": message.topic,
                "trace_id": message.trace_id,
            },
        )

        # Parse trigger payload
        try:
            payload = (
                json.loads(message.payload)
                if isinstance(message.payload, (bytes, str))
                else message.payload
            )
        except (json.JSONDecodeError, TypeError):
            payload = {}

        # Extract trigger context (reason, options, etc.)
        trigger_context = payload.get("context", {}) if isinstance(payload, dict) else {}
        trigger_id = (
            payload.get("trigger_id", "unknown") if isinstance(payload, dict) else "unknown"
        )

        # Create pipeline-specific runner context
        # This is where we translate kernel abstractions to pipeline-specific ones
        runner_ctx = await self._create_runner_context(
            trigger_id=trigger_id,
            trigger_context=trigger_context,
            trace_id=message.trace_id or str(uuid.uuid4()),
        )

        # Execute the pipeline via sequential runner
        try:
            # P03SequentialRunner.run_cycle() expects (envelope, context)
            # But first we need to create a batch envelope via R0
            result = await self._execute_cycle(runner_ctx)

            logger.info(
                f"Sequential runner completed for {pipeline_id}",
                extra={
                    "pipeline_id": pipeline_id,
                    "trigger_id": trigger_id,
                    "success": result.success if hasattr(result, "success") else True,
                },
            )
        except Exception as e:
            logger.exception(
                f"Sequential runner failed for {pipeline_id}: {e}",
                extra={
                    "pipeline_id": pipeline_id,
                    "trigger_id": trigger_id,
                    "error": str(e),
                },
            )
            raise

    async def _create_runner_context(
        self,
        trigger_id: str,
        trigger_context: dict[str, Any],
        trace_id: str,
    ) -> Any:
        """
        Create the pipeline-specific runner context.

        For P03, this creates a P03RunnerContext with syscalls, logger, etc.
        """
        pipeline_prefix = self._spec.pipeline_id.split("_")[0].lower()

        try:
            # Import pipeline-specific context class
            context_module_path = f"k0.pipelines.{pipeline_prefix}.phase_interface"
            import importlib

            context_module = importlib.import_module(context_module_path)

            # Look for RunnerContext class
            context_class_name = f"{pipeline_prefix.upper()}RunnerContext"
            context_class = getattr(context_module, context_class_name, None)

            if context_class is None:
                context_class = getattr(context_module, "P03RunnerContext", None)

            if context_class is not None and hasattr(context_class, "create"):
                # Use the factory method with params it accepts
                # P03RunnerContext.create() accepts: syscalls, logger, qos_band, priority, etc.
                # It does NOT accept trigger_id, trigger_context, trace_id directly
                runner_ctx = context_class.create(
                    syscalls=self._ctx.syscalls,
                    logger=self._ctx.logger,
                    config={
                        "trigger_id": trigger_id,
                        "trigger_context": trigger_context,
                        "trace_id": trace_id,
                    },
                )
                return runner_ctx

        except ImportError as e:
            logger.debug(
                f"Cannot import context class for {self._spec.pipeline_id}: {e}",
                extra={"pipeline_id": self._spec.pipeline_id},
            )

        # Fallback: return the generic pipeline context
        return self._ctx

    async def _execute_cycle(self, runner_ctx: Any) -> Any:
        """
        Execute consolidation cycles until all pending events are drained.

        This method handles the full R0->R8 execution flow in a drain loop.
        For sequential runners (like P03), R0 is responsible for creating
        the actual envelope. Each cycle processes one batch of events.
        The loop continues creating fresh seed envelopes and running cycles
        until R0 reports no more eligible events (SKIP), ensuring all
        pending events in st_hipp_events are processed in a single trigger.
        """
        pipeline_id = self._spec.pipeline_id
        pipeline_prefix = pipeline_id.split("_")[0].lower()

        # Import pipeline-specific envelope and context classes
        try:
            context_module_path = f"k0.pipelines.{pipeline_prefix}.context"
            envelope_module_path = f"k0.pipelines.{pipeline_prefix}.envelope"
            import importlib

            context_module = importlib.import_module(context_module_path)
            envelope_module = importlib.import_module(envelope_module_path)

            # Get context and envelope classes
            context_class = getattr(context_module, f"{pipeline_prefix.upper()}CycleContext", None)
            if context_class is None:
                context_class = getattr(context_module, "P03CycleContext", None)

            envelope_class = getattr(
                envelope_module, f"{pipeline_prefix.upper()}BatchEnvelope", None
            )
            if envelope_class is None:
                envelope_class = getattr(envelope_module, "P03BatchEnvelope", None)

        except ImportError as e:
            logger.debug(
                f"Cannot import envelope/context for {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id},
            )
            context_class = None
            envelope_class = None

        if context_class is None or envelope_class is None:
            logger.warning(
                f"Could not resolve envelope/context classes for {pipeline_id}",
                extra={"pipeline_id": pipeline_id},
            )
            return SimpleNamespace(success=True, skipped=True, reason="NO_ENVELOPE_CLASSES")

        # Drain loop: keep running cycles until R0 finds no more events
        results: list[Any] = []
        batch_number = 0

        while True:
            batch_number += 1

            # Build fresh seed envelopes each iteration (offset advances after each cycle)
            seed_envelopes = await self._build_seed_envelopes(
                pipeline_prefix=pipeline_prefix,
                runner_ctx=runner_ctx,
                context_class=context_class,
                envelope_class=envelope_class,
            )

            if not seed_envelopes:
                logger.info(
                    "No execution scopes resolved for sequential runner",
                    extra={"pipeline_id": pipeline_id, "batch_number": batch_number},
                )
                break

            drained_all_scopes = True

            for envelope in seed_envelopes:
                if hasattr(self._runner, "run"):
                    result = await self._runner.run(envelope, runner_ctx)
                elif hasattr(self._runner, "run_cycle"):
                    result = await self._runner.run_cycle(envelope, runner_ctx)
                else:
                    raise RuntimeError(
                        f"Sequential runner for {pipeline_id} has no run() or run_cycle() method"
                    )

                results.append(result)

                # Check if R0 was skipped (no events found) — signals drain complete
                r0_skipped = self._is_r0_skipped(result)

                # If cycle failed, stop draining this scope
                cycle_failed = hasattr(result, "is_failed") and result.is_failed

                if cycle_failed:
                    logger.warning(
                        "P03 drain loop: cycle failed, stopping",
                        extra={
                            "pipeline_id": pipeline_id,
                            "batch_number": batch_number,
                            "dlq_reason": getattr(result, "dlq_reason", None),
                        },
                    )
                    drained_all_scopes = False
                    break

                if not r0_skipped:
                    # R0 found events and processed them — more may remain
                    drained_all_scopes = False

            logger.info(
                "P03 drain loop: batch complete",
                extra={
                    "pipeline_id": pipeline_id,
                    "batch_number": batch_number,
                    "drained_all_scopes": drained_all_scopes,
                    "total_cycles": len(results),
                },
            )

            if drained_all_scopes:
                # All scopes reported R0 SKIP — no more events anywhere
                break

            # Safety: if a cycle failed, stop the drain loop
            last = results[-1]
            if hasattr(last, "is_failed") and last.is_failed:
                break

        if results:
            return results[-1]

        return SimpleNamespace(success=True, skipped=True, reason="NO_EXECUTION_SCOPES")

    def _is_r0_skipped(self, result: Any) -> bool:
        """Check whether R0 was skipped (no eligible events) in a cycle result."""
        # P03CycleResult exposes phase_results dict keyed by P03PhaseId
        phase_results = getattr(result, "phase_results", None)
        if phase_results is None:
            return False
        for phase_id, phase_result in phase_results.items():
            phase_value = getattr(phase_id, "value", str(phase_id))
            if phase_value == "R0":
                return getattr(phase_result, "is_skipped", False)
        return False

    async def _build_seed_envelopes(
        self,
        *,
        pipeline_prefix: str,
        runner_ctx: Any,
        context_class: type[Any],
        envelope_class: type[Any],
    ) -> list[Any]:
        """Create one or more seed envelopes for the upcoming execution."""
        trigger_context_cfg = runner_ctx.get_config("trigger_context", {})
        trigger_options = trigger_context_cfg.get("options", {})
        trigger_reason = trigger_context_cfg.get("reason", "Sequential runner triggered")

        scopes = await self._resolve_execution_scopes(
            pipeline_prefix=pipeline_prefix,
            runner_ctx=runner_ctx,
            trigger_options=trigger_options,
        )
        if not scopes:
            return []

        return [
            envelope_class.create(
                context_class.create(
                    tenant_id=tenant_id,
                    space_id=space_id,
                    event_ids=[],
                    trigger_type="MANUAL",
                    trigger_reason=trigger_reason,
                )
            )
            for tenant_id, space_id in scopes
        ]

    async def _resolve_execution_scopes(
        self,
        *,
        pipeline_prefix: str,
        runner_ctx: Any,
        trigger_options: dict[str, Any],
    ) -> list[tuple[str, str]]:
        """Resolve tenant/space scopes for a sequential pipeline execution."""
        explicit_tenant_id = trigger_options.get("tenant_id")
        explicit_space_id = trigger_options.get("space_id")

        if explicit_tenant_id and explicit_space_id:
            return [(explicit_tenant_id, explicit_space_id)]

        legacy_tenant_id = runner_ctx.get_config("tenant_id")
        legacy_space_id = runner_ctx.get_config("space_id")
        if legacy_tenant_id and legacy_space_id:
            return [(legacy_tenant_id, legacy_space_id)]

        if pipeline_prefix != "p03":
            return []

        return await self._discover_p03_scopes(
            runner_ctx=runner_ctx,
            tenant_id=explicit_tenant_id or legacy_tenant_id,
            space_id=explicit_space_id or legacy_space_id,
        )

    async def _discover_p03_scopes(
        self,
        *,
        runner_ctx: Any,
        tenant_id: str | None,
        space_id: str | None,
    ) -> list[tuple[str, str]]:
        """Discover concrete P03 tenant/space scopes from st_hipp_events."""
        async with runner_ctx.syscalls.unit_of_work() as uow:
            conn = getattr(uow, "_connection", None)
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            rows = await conn.fetch(
                f"""
                SELECT DISTINCT tenant_id, space_id
                FROM {P03_SOURCE_SCOPE_TABLE}
                WHERE tenant_id IS NOT NULL
                  AND tenant_id <> ''
                  AND space_id IS NOT NULL
                  AND space_id <> ''
                  AND ($1::text IS NULL OR tenant_id = $1)
                  AND ($2::text IS NULL OR space_id = $2)
                ORDER BY tenant_id ASC, space_id ASC
                """,
                tenant_id,
                space_id,
            )

        return [(row["tenant_id"], row["space_id"]) for row in rows]

    def _discover_phases(self, phases_module: Any) -> dict[Any, Any]:
        """Discover phase classes from a module and build a registry dict."""
        phases = {}
        for name in dir(phases_module):
            obj = getattr(phases_module, name)
            # Look for classes with phase-like attributes
            if isinstance(obj, type) and hasattr(obj, "run") and hasattr(obj, "phase_id"):
                # Get phase_id from the class (class attribute or classmethod)
                phase_id = getattr(obj, "phase_id", None)
                if phase_id is not None:
                    phases[phase_id] = obj()
        return phases
