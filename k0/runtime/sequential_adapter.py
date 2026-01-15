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
from typing import TYPE_CHECKING, Any, Type

if TYPE_CHECKING:
    from k0.bus.core import BusMessage
    from k0.pipelines.protocol import PipelineContext
    from k0.runtime.module_registry import ModuleRegistry
    from k0.runtime.schemas import PipelineSpec

logger = logging.getLogger(__name__)


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
        Execute a consolidation cycle.

        This method handles the full R0→R8 execution flow.
        For sequential runners (like P03), R0 is responsible for creating
        the actual envelope. We create a minimal "seed" envelope that R0
        will populate with events from the database.
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

            if context_class is not None and envelope_class is not None:
                # Create a minimal seed context for R0
                # R0 will replace this with the actual context after fetching events
                # Extract tenant/space from trigger_context.options (admin trigger)
                # or fall back to top-level config (legacy/direct)
                trigger_context_cfg = runner_ctx.get_config("trigger_context", {})
                trigger_options = trigger_context_cfg.get("options", {})
                seed_context = context_class.create(
                    tenant_id=trigger_options.get(
                        "tenant_id", runner_ctx.get_config("tenant_id", "default")
                    ),
                    space_id=trigger_options.get(
                        "space_id", runner_ctx.get_config("space_id", "default")
                    ),
                    event_ids=[],  # Empty - R0 will populate
                    trigger_type="MANUAL",
                    trigger_reason=trigger_context_cfg.get("reason", "Sequential runner triggered"),
                )
                # Create envelope with seed context
                envelope = envelope_class.create(seed_context)
            else:
                logger.warning(
                    f"Could not create seed envelope for {pipeline_id}",
                    extra={"pipeline_id": pipeline_id},
                )
                envelope = None

        except ImportError as e:
            logger.debug(
                f"Cannot import envelope/context for {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id},
            )
            envelope = None

        # Run the cycle
        if hasattr(self._runner, "run"):
            # P03SequentialRunner.run(envelope, ctx) -> P03CycleResult
            result = await self._runner.run(envelope, runner_ctx)
        elif hasattr(self._runner, "run_cycle"):
            # Alternative interface
            result = await self._runner.run_cycle(envelope, runner_ctx)
        else:
            raise RuntimeError(
                f"Sequential runner for {pipeline_id} has no run() or run_cycle() method"
            )

        return result

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
