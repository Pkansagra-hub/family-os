"""
k1.fabric.fabric -- FabricFacade, FabricRetrieval, CapabilityRegistryAPI (5.3.2-5.3.4).

Public API surface for the Capability Fabric.

Three classes:
  - CapabilityFabric (FabricFacade): Main execution API (Role 2).
    Methods: execute(request), execute_batch(requests, strategy).
  - FabricRetrieval: Discovery API (Role 1).
    Methods: discover_capabilities(), find_relevant_prompts().
  - CapabilityRegistryAPI: Registry management API.
    Methods: register, unregister, lookup, etc.
  - Fabric: Container holding all three plus internal components.

Execution pipeline (9 steps) for execute():
  1. Emit invoked event
  2. Resolve provider (Registry -> Policy -> Selector)
  3. Build context (SessionState + prompts + budget)
  4. Instantiate provider via ProviderFactory
  5. Execute via CircuitBreaker
  6. Validate output (3-tier pipeline)
  7. Emit completed/failed event
  8. Update metrics
  9. Emit learning signal

BatchStrategy (execute_batch):
  PARALLEL   -- All at once (default), for Orchestrator DAG wave execution
  SEQUENTIAL -- Ordered execution
  DAG        -- Dependency-aware (from request metadata)

Constraints enforced:
  FAB-03: Stateless per-request (no instance state between execute() calls)
  FAB-04: Circuit breaker timeout (per-provider)
  FAB-09: Event emission with cognitive_trace_id

References:
  - fabric_discussion.md Section 15 (CapabilityFabric)
  - Epic 5.3.2, 5.3.3, 5.3.4 in fabric-implementation-plan.md
  - fabric-wiring-guide.md Section 6 (FabricFacade Execution Pipeline)

Exports:
  CapabilityFabric     -- Main execution API (FabricFacade)
  FabricRetrieval      -- Discovery/retrieval API
  CapabilityRegistryAPI -- Registry management wrapper
  Fabric               -- Container for all APIs + internal components
  BatchStrategy        -- Execution strategy enum
  FabricError          -- Base exception
  BatchSizeExceededError -- Batch too large
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from k1.fabric.concurrency.dispatcher import (
    DispatcherOverloadedError,
    DispatcherShutdownError,
    FabricDispatcher,
)
from k1.fabric.events.event_emitter import EventEmitter
from k1.fabric.logging import get_default_logger as get_fabric_logger
from k1.fabric.metrics import get_default_metrics
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    RetrievalResult,
    SafetyBand,
)

if TYPE_CHECKING:
    # Imported only for typing -- runtime import would create a fabric -> kernel
    # cycle. The actual IHILPort instance is duck-typed at the call site.
    from k1.kernel.ports.hil_port import IHILPort
    from k1.selfmodel.ports.conscience import IConsciencePort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BatchStrategy(str, Enum):
    """Execution strategy for execute_batch()."""

    PARALLEL = "PARALLEL"
    SEQUENTIAL = "SEQUENTIAL"
    DAG = "DAG"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FabricError(Exception):
    """Base exception for Fabric API operations."""


class BatchSizeExceededError(FabricError):
    """Raised when batch size exceeds max_batch_size."""

    def __init__(self, actual: int, maximum: int):
        self.actual = actual
        self.maximum = maximum
        super().__init__(f"Batch size {actual} exceeds maximum {maximum}")


# ---------------------------------------------------------------------------
# Protocol declarations (avoid circular imports)
# ---------------------------------------------------------------------------


class IResolver(Protocol):
    """Minimal resolver interface for FabricFacade."""

    def resolve(self, request: CapabilityRequest) -> Any: ...


class IContextBuilder(Protocol):
    """Minimal context builder interface for FabricFacade."""

    def build(
        self,
        contract: Any,
        params: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        trace_id: str = "",
        prompt_template_name: Optional[str] = None,
        prompt_variables: Optional[Dict[str, Any]] = None,
        context_override: Optional[Dict[str, Any]] = None,
    ) -> Any: ...


class IOutputValidationPipeline(Protocol):
    """Minimal output validation interface."""

    def validate(
        self,
        result: Any,
        contract: Any,
        provider_type: str,
        session_id: Optional[str] = None,
        execution_context: Optional[Dict[str, Any]] = None,
        request_id: str = "",
        provider_id: str = "",
        trace_id: str = "",
    ) -> Any: ...


class IProviderFactory(Protocol):
    """Minimal provider factory interface."""

    def create(self, config: Any) -> Any: ...


class ICircuitBreaker(Protocol):
    """Minimal circuit breaker interface."""

    async def call(
        self,
        execute_fn: Any,
        request: CapabilityRequest,
        context: Any,
        trace_id: str,
    ) -> CapabilityResult: ...


class IRegistry(Protocol):
    """Minimal registry interface for metrics updates."""

    def update_metrics(self, name: str, latency_ms: float, success: bool) -> None: ...

    def lookup(self, name: str) -> Any: ...


class IRetrievalEngine(Protocol):
    """Minimal retrieval engine interface."""

    def discover_capabilities(
        self,
        domain: Optional[List[str]],
        intent: str,
        safety_band: str,
        session_context: Optional[Dict[str, Any]],
        top_k: Optional[int],
    ) -> Any: ...

    def find_relevant_prompts(
        self,
        intent: str,
        domain: Optional[List[str]],
        safety_band: str,
        top_k: Optional[int],
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FabricConfig:
    """Configuration for the CapabilityFabric."""

    #: Maximum batch size for execute_batch().
    max_batch_size: int = 50

    #: Default timeout for execute() in milliseconds.
    default_timeout_ms: int = 30000

    #: Default timeout for the HIL pre-execution gate (E3). Pass-through
    #: to ``IHILPort.gate_capability``. Ignored when ``hil_port`` is None.
    hil_gate_timeout_ms: int = 120_000


# ---------------------------------------------------------------------------
# 5.3.2 -- CapabilityFabric (FabricFacade)
# ---------------------------------------------------------------------------


class CapabilityFabric:
    """
    Main execution API for the Capability Fabric (Role 2).

    Stateless, deterministic, policy-driven capability execution.
    Each execute() call is independent -- no instance state is held
    between calls (FAB-03).

    execute() pipeline (9 steps):
      1. Emit k1.capability.invoked.v1
      2. Resolve provider via Resolver (Registry -> Policy -> Selector)
      3. Build execution context (SessionState + prompts + budget)
      4. Instantiate provider via ProviderFactory
      5. Execute via CircuitBreaker (timeout enforcement, FAB-04)
      6. Validate output (3-tier: structural -> schema -> semantic)
      7. Emit k1.capability.completed.v1 or k1.capability.failed.v1
      8. Update registry metrics
      9. Emit k1.fabric.learning.signal.v1

    execute_batch() strategies:
      PARALLEL:   asyncio.gather() all requests (default)
      SEQUENTIAL: Execute one-by-one in order
      DAG:        Dependency-aware topological execution

    Constructor Args:
        resolver: Provider resolution pipeline (3.1.5).
        context_builder: Context assembly (4.2.1).
        validation_pipeline: Output validation (3.5.5).
        event_emitter: Event emission wrapper (5.4.2).
        registry: Capability registry for metrics (2.2.1).
        provider_factory: Provider instantiation (3.1.4).
        circuit_breakers: Dict of provider_id -> CircuitBreaker (3.4.1).
        config: FabricConfig.

    Thread Safety:
        All public methods are stateless per-call.  Internal components
        handle their own thread safety.

    References:
        - fabric_discussion.md Section 15
        - Epic 5.3.2
    """

    __slots__ = (
        "_resolver",
        "_context_builder",
        "_validation_pipeline",
        "_event_emitter",
        "_registry",
        "_provider_factory",
        "_circuit_breakers",
        "_dispatcher",
        "_config",
        "_hil_port",
        "_conscience_port",
    )

    def __init__(
        self,
        *,
        resolver: Any,
        context_builder: Any,
        validation_pipeline: Any,
        event_emitter: EventEmitter,
        registry: Any,
        provider_factory: Any,
        circuit_breakers: Optional[Dict[str, Any]] = None,
        dispatcher: Optional[FabricDispatcher] = None,
        config: Optional[FabricConfig] = None,
        hil_port: Optional["IHILPort"] = None,
        conscience_port: Optional["IConsciencePort"] = None,
    ) -> None:
        self._resolver = resolver
        self._context_builder = context_builder
        self._validation_pipeline = validation_pipeline
        self._event_emitter = event_emitter
        self._registry = registry
        self._provider_factory = provider_factory
        self._circuit_breakers: Dict[str, Any] = circuit_breakers or {}
        self._dispatcher = dispatcher
        self._config = config or FabricConfig()
        # E3.M1.1 -- HIL gate port. None disables the gate (test/legacy harness).
        self._hil_port: Optional["IHILPort"] = hil_port
        # M12.E4.I1 -- Conscience pre-HIL gate. None disables the gate.
        self._conscience_port: Optional["IConsciencePort"] = conscience_port

    # ==================================================================
    # Properties
    # ==================================================================

    @property
    def config(self) -> FabricConfig:
        """Current configuration."""
        return self._config

    @property
    def max_batch_size(self) -> int:
        """Maximum batch size for execute_batch()."""
        return self._config.max_batch_size

    # ==================================================================
    # Public API: execute (single request)
    # ==================================================================

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute a single capability request.

        If a FabricDispatcher is configured, execution is routed through
        the dispatcher to enforce bounded parallelism (FAB-003).
        """
        if self._dispatcher is None:
            return await self._execute_impl(request)

        start_time = time.monotonic()
        try:
            dispatch_result = await self._dispatcher.dispatch(request, self._execute_impl)
            return dispatch_result.result
        except DispatcherOverloadedError as exc:
            elapsed_ms = _elapsed_ms(start_time)
            result = CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="dispatcher_overloaded",
                error_message=str(exc),
                retriable=True,
                trace_id=request.trace_id,
                duration_ms=elapsed_ms,
            )
            self._emit_failure(request, result, start_time)
            self._emit_learning(
                request=request,
                provider_id="",
                success=False,
                duration_ms=elapsed_ms,
                error_code="dispatcher_overloaded",
            )
            return result
        except DispatcherShutdownError as exc:
            elapsed_ms = _elapsed_ms(start_time)
            result = CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="dispatcher_shutdown",
                error_message=str(exc),
                retriable=True,
                trace_id=request.trace_id,
                duration_ms=elapsed_ms,
            )
            self._emit_failure(request, result, start_time)
            self._emit_learning(
                request=request,
                provider_id="",
                success=False,
                duration_ms=elapsed_ms,
                error_code="dispatcher_shutdown",
            )
            return result
        except Exception as exc:
            elapsed_ms = _elapsed_ms(start_time)
            result = CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="dispatcher_error",
                error_message=str(exc),
                retriable=True,
                trace_id=request.trace_id,
                duration_ms=elapsed_ms,
            )
            self._emit_failure(request, result, start_time)
            self._emit_learning(
                request=request,
                provider_id="",
                success=False,
                duration_ms=elapsed_ms,
                error_code="dispatcher_error",
            )
            return result

    async def _execute_impl(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute a single capability request.

        9-step pipeline:
          1. Emit invoked event
          2. Resolve provider
          3. Build context
          4. Instantiate provider
          5. Execute via CircuitBreaker
          6. Validate output
          7. Emit completed/failed
          8. Update metrics
          9. Emit learning signal

        Args:
            request: The capability request to execute.

        Returns:
            CapabilityResult -- success with data, or failure with error.
            Never raises; all errors are wrapped in failure results.
        """
        trace_id = request.trace_id
        capability_name = request.capability_name
        start_time = time.monotonic()
        exec_start = time.perf_counter()
        provider_id = ""
        provider_type = "unknown"
        metrics = get_default_metrics()
        fabric_logger = get_fabric_logger()

        try:
            metrics.inc_active_executions()
        except Exception:
            logger.warning("Failed to increment active executions", exc_info=True)

        try:
            # --- Step 1: Emit invoked event ---
            self._event_emitter.emit_invoked(
                capability_name=capability_name,
                request_id=request.request_id,
                trace_id=trace_id,
                caller=request.caller,
                session_id=request.session_id,
                priority=request.wfq_priority,
            )

            # --- Step 2: Resolve provider ---
            resolve_start = time.perf_counter()
            resolved = self._resolve(request)
            resolve_ms = (time.perf_counter() - resolve_start) * 1000.0
            fabric_logger.resolve(
                trace_id=trace_id,
                request_id=request.request_id,
                capability_name=capability_name,
                duration_ms=round(resolve_ms, 3),
                success=resolved is not None,
            )
            if resolved is None:
                # Resolution returned a failure result
                elapsed_ms = _elapsed_ms(start_time)
                result = CapabilityResult.failure_result(
                    request_id=request.request_id,
                    error_code="resolution_failed",
                    error_message=f"Failed to resolve provider for '{capability_name}'",
                    retriable=True,
                    trace_id=trace_id,
                    duration_ms=elapsed_ms,
                    resolution_time_ms=elapsed_ms,
                )
                self._emit_failure(request, result, start_time)
                fabric_logger.result_return(
                    trace_id=trace_id,
                    request_id=request.request_id,
                    capability_name=capability_name,
                    duration_ms=elapsed_ms,
                    success=False,
                    error_code=result.error.code if result.error else "unknown",
                )
                return self._finalize_execution_metrics(
                    request=request,
                    result=result,
                    provider_type=provider_type,
                    exec_start=exec_start,
                )

            provider_id = resolved.provider_config.provider_id
            provider_type = resolved.provider_config.provider_type
            contract = resolved.contract

            # --- Step 2.4: Conscience gate (M12.E4.I1) ---
            # Runs BEFORE the HIL gate. If the contract carries a
            # ``social_act`` and the actor's conscience digest forbids
            # it, short-circuit with ``conscience_forbidden``. Returning
            # ``None`` lets the HIL gate decide must-ask cases.
            conscience_failure = self._run_conscience_gate(request, contract, trace_id)
            if conscience_failure is not None:
                elapsed_ms = _elapsed_ms(start_time)
                conscience_failure = CapabilityResult.failure_result(
                    request_id=request.request_id,
                    error_code=(
                        conscience_failure.error.code
                        if conscience_failure.error
                        else "conscience_forbidden"
                    ),
                    error_message=(
                        conscience_failure.error.message
                        if conscience_failure.error
                        else "Capability forbidden by conscience"
                    ),
                    retriable=False,
                    provider_id=provider_id,
                    trace_id=trace_id,
                    duration_ms=elapsed_ms,
                    resolution_time_ms=resolve_ms,
                )
                self._emit_failure(request, conscience_failure, start_time, provider_id)
                fabric_logger.result_return(
                    trace_id=trace_id,
                    request_id=request.request_id,
                    capability_name=capability_name,
                    provider_id=provider_id,
                    duration_ms=elapsed_ms,
                    success=False,
                    error_code=(
                        conscience_failure.error.code
                        if conscience_failure.error
                        else "conscience_forbidden"
                    ),
                )
                self._update_metrics(capability_name, elapsed_ms, success=False)
                return self._finalize_execution_metrics(
                    request=request,
                    result=conscience_failure,
                    provider_type=provider_type,
                    exec_start=exec_start,
                )

            # --- Step 2.5: HIL gate (E3.M2.2) ---
            gate_start = time.perf_counter()
            gate_failure = await self._run_hil_gate(request, contract, trace_id)
            gate_ms = (time.perf_counter() - gate_start) * 1000.0

            if gate_failure is not None:
                elapsed_ms = _elapsed_ms(start_time)
                # Re-stamp with provider_id + timing now that we know them.
                gate_failure = CapabilityResult.failure_result(
                    request_id=request.request_id,
                    error_code=gate_failure.error.code if gate_failure.error else "hil_unknown",
                    error_message=(
                        gate_failure.error.message
                        if gate_failure.error
                        else "Capability blocked by Human-in-the-Loop gate"
                    ),
                    retriable=False,
                    provider_id=provider_id,
                    trace_id=trace_id,
                    duration_ms=elapsed_ms,
                    resolution_time_ms=resolve_ms,
                )
                self._emit_failure(request, gate_failure, start_time, provider_id)
                fabric_logger.result_return(
                    trace_id=trace_id,
                    request_id=request.request_id,
                    capability_name=capability_name,
                    provider_id=provider_id,
                    duration_ms=elapsed_ms,
                    success=False,
                    error_code=gate_failure.error.code if gate_failure.error else "hil_unknown",
                )
                self._update_metrics(capability_name, elapsed_ms, success=False)
                self._emit_learning(
                    request=request,
                    provider_id=provider_id,
                    success=False,
                    duration_ms=elapsed_ms,
                    error_code=gate_failure.error.code if gate_failure.error else "hil_unknown",
                )
                return self._finalize_execution_metrics(
                    request=request,
                    result=gate_failure,
                    provider_type=provider_type,
                    exec_start=exec_start,
                )

            if self._hil_port is not None:
                logger.info(
                    "hil_gate trace_id=%s capability=%s duration_ms=%.3f decision=allow",
                    trace_id,
                    capability_name,
                    gate_ms,
                )

            # --- Step 3: Build context ---
            context_start = time.perf_counter()
            context = self._build_context(request, contract)
            context_ms = (time.perf_counter() - context_start) * 1000.0
            fabric_logger.context_build(
                trace_id=trace_id,
                request_id=request.request_id,
                capability_name=capability_name,
                provider_id=provider_id,
                duration_ms=round(context_ms, 3),
                success=True,
            )

            # --- Step 4: Instantiate provider ---
            provider = self._provider_factory.create(resolved.provider_config)

            # --- Step 5: Execute via CircuitBreaker ---
            execute_start = time.perf_counter()
            result = await self._execute_with_breaker(
                provider=provider,
                provider_id=provider_id,
                request=request,
                context=context,
                trace_id=trace_id,
            )
            execute_ms = (time.perf_counter() - execute_start) * 1000.0
            fabric_logger.execute(
                trace_id=trace_id,
                request_id=request.request_id,
                capability_name=capability_name,
                provider_id=provider_id,
                duration_ms=round(execute_ms, 3),
                success=result.success,
            )

            # --- Step 6: Validate output ---
            if result.success:
                result = self._validate_output(
                    result=result,
                    contract=contract,
                    provider_type=resolved.provider_config.provider_type,
                    request=request,
                    execution_context=context,
                )

            # --- Steps 7-9: Post-execution ---
            elapsed_ms = _elapsed_ms(start_time)

            if result.success:
                self._emit_success(request, result, provider_id, elapsed_ms)
            else:
                self._emit_failure(request, result, start_time, provider_id)

            fabric_logger.result_return(
                trace_id=trace_id,
                request_id=request.request_id,
                capability_name=capability_name,
                provider_id=provider_id,
                duration_ms=elapsed_ms,
                success=result.success,
                error_code=result.error.code if result.error else "",
            )

            # Step 8: Update metrics
            self._update_metrics(capability_name, elapsed_ms, result.success)

            # Step 9: Emit learning signal
            self._emit_learning(
                request=request,
                provider_id=provider_id,
                success=result.success,
                duration_ms=elapsed_ms,
                error_code=result.error.code if result.error else None,
            )

            return self._finalize_execution_metrics(
                request=request,
                result=result,
                provider_type=provider_type,
                exec_start=exec_start,
            )

        except Exception as exc:
            elapsed_ms = _elapsed_ms(start_time)
            logger.error(
                "Fabric execute error for '%s': %s",
                capability_name,
                exc,
                exc_info=True,
            )

            # Wrap all unexpected errors in failure result
            result = CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="execution_error",
                error_message=str(exc),
                retriable=True,
                provider_id=provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
            )
            self._emit_failure(request, result, start_time, provider_id)
            self._emit_learning(
                request=request,
                provider_id=provider_id,
                success=False,
                duration_ms=elapsed_ms,
                error_code="execution_error",
            )
            fabric_logger.result_return(
                trace_id=trace_id,
                request_id=request.request_id,
                capability_name=capability_name,
                provider_id=provider_id,
                duration_ms=elapsed_ms,
                success=False,
                error_code="execution_error",
            )
            return self._finalize_execution_metrics(
                request=request,
                result=result,
                provider_type=provider_type,
                exec_start=exec_start,
            )

    # ==================================================================
    # Public API: execute_batch
    # ==================================================================

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
        strategy: BatchStrategy = BatchStrategy.PARALLEL,
    ) -> List[CapabilityResult]:
        """
        Execute a batch of requests with the specified strategy.

        Partial failure handling:
          - Each request is independent.
          - Failed requests return CapabilityResult.failure() without
            blocking other requests.

        Ordering guarantee:
          - Results list matches input order regardless of execution order.

        Backpressure:
          - Batch size capped at max_batch_size (default 50).

        Args:
            requests: List of capability requests to execute.
            strategy: Execution strategy (PARALLEL, SEQUENTIAL, DAG).

        Returns:
            List of CapabilityResults matching input order.

        Raises:
            BatchSizeExceededError: If len(requests) > max_batch_size.
        """
        if not requests:
            return []

        if len(requests) > self._config.max_batch_size:
            raise BatchSizeExceededError(
                actual=len(requests),
                maximum=self._config.max_batch_size,
            )

        if strategy == BatchStrategy.PARALLEL:
            return await self._execute_batch_parallel(requests)
        elif strategy == BatchStrategy.SEQUENTIAL:
            return await self._execute_batch_sequential(requests)
        elif strategy == BatchStrategy.DAG:
            return await self._execute_batch_dag(requests)
        else:
            raise FabricError(f"Unknown batch strategy: {strategy}")

    # ==================================================================
    # Internal: Resolution
    # ==================================================================

    def _resolve(self, request: CapabilityRequest) -> Any:
        """
        Resolve provider for request.

        Returns ResolvedProvider on success, None on failure.
        Catches ResolutionFailedError gracefully.
        """
        try:
            return self._resolver.resolve(request)
        except Exception as exc:
            logger.warning(
                "Resolution failed for '%s': %s",
                request.capability_name,
                exc,
            )
            return None

    # ==================================================================
    # Internal: Context building
    # ==================================================================

    # ==================================================================
    # Internal: HIL pre-execution gate (E3.M2.1)
    # ==================================================================

    def _run_conscience_gate(
        self,
        request: CapabilityRequest,
        contract: Any,
        trace_id: str,
    ) -> Optional[CapabilityResult]:
        """Pre-HIL conscience gate (M12.E4.I1).

        Reads ``contract.social_act`` and asks the conscience port
        whether the act is forbidden for ``request.caller_id``.

        Returns ``None`` to allow execution to continue (and the HIL
        gate to decide must-ask), otherwise a ``conscience_forbidden``
        ``CapabilityResult.failure_result``.

        Skips entirely (returns ``None``) when:

        * ``self._conscience_port is None`` -- gate disabled (legacy /
          test harness path), or
        * the contract has no ``social_act`` -- there is nothing for
          the conscience to forbid, or
        * the request has no ``caller_id`` -- without an actor we
          cannot resolve a digest; HIL gate may still apply.
        """
        if self._conscience_port is None:
            return None
        social_act = getattr(contract, "social_act", None)
        if not social_act:
            return None
        caller_id = getattr(request, "caller_id", "") or ""
        if not caller_id:
            return None

        try:
            digest = self._conscience_port.get_digest(
                caller_id,
                T_ms=int(time.time() * 1000),
            )
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "conscience_gate trace_id=%s capability=%s: digest lookup failed; "
                "allowing through to HIL",
                trace_id,
                getattr(contract, "name", ""),
                exc_info=True,
            )
            return None

        if digest.is_forbidden(social_act):
            logger.info(
                "conscience_gate trace_id=%s capability=%s social_act=%s decision=forbid",
                trace_id,
                getattr(contract, "name", ""),
                social_act,
            )
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="conscience_forbidden",
                error_message=(
                    f"social_act '{social_act}' is forbidden for actor "
                    f"'{caller_id}' by conscience"
                ),
                retriable=False,
                trace_id=trace_id,
                duration_ms=0,
            )
        return None

    async def _run_hil_gate(
        self,
        request: CapabilityRequest,
        contract: Any,
        trace_id: str,
    ) -> Optional[CapabilityResult]:
        """Pre-execution HIL gate.

        Returns ``None`` to allow execution to proceed, or a failure
        ``CapabilityResult`` to short-circuit the pipeline.

        Skips entirely (returns ``None``) when ``self._hil_port is None`` --
        this preserves the legacy/test harness path where no kernel HIL
        wiring exists.
        """
        if self._hil_port is None:
            return None  # gate disabled -- allow execution

        # Lazy imports to avoid module-import cycles between
        # k1.fabric and k1.hil.
        from k1.hil.types import (
            CapabilityGateRequest,
            GateOutcome,
            view_from_capability_contract,
        )

        gate_req = CapabilityGateRequest(
            caller_key=f"fabric:{contract.name}",
            trace_id=trace_id,
            capability_name=contract.name,
            contract=view_from_capability_contract(contract),
            params=dict(request.params or {}),
            params_summary=self._summarize_params(request.params),
            timeout_ms=self._config.hil_gate_timeout_ms,
        )
        decision = await self._hil_port.gate_capability(gate_req)

        if decision.outcome in (GateOutcome.ALLOW, GateOutcome.ASK_APPROVED):
            return None  # proceed to execution

        error_code = {
            GateOutcome.DENY: "hil_denied",
            GateOutcome.ASK_REJECTED: "hil_rejected_by_user",
            GateOutcome.TIMEOUT: "hil_timeout",
        }.get(decision.outcome, "hil_unknown")

        return CapabilityResult.failure_result(
            request_id=request.request_id,
            error_code=error_code,
            error_message=decision.reason or "Capability blocked by Human-in-the-Loop gate",
            retriable=False,
            trace_id=trace_id,
            duration_ms=0,
        )

    @staticmethod
    def _summarize_params(params: Optional[Dict[str, Any]]) -> str:
        """One-line summary of params for user-facing prompt.

        Truncates long values (>60 chars) and caps key count at 5.
        """
        if not params:
            return "(no parameters)"
        pairs = []
        for k, v in params.items():
            s = str(v)
            if len(s) > 60:
                s = s[:57] + "..."
            pairs.append(f"{k}={s}")
        truncated = len(pairs) > 5
        head = pairs[:5]
        return ", ".join(head) + ("..." if truncated else "")

    # ==================================================================
    # Internal: Context building
    # ==================================================================

    def _build_context(self, request: CapabilityRequest, contract: Any) -> Any:
        """
        Build execution context for the request.

        Delegates to ContextBuilder.build() with request params and
        session context.
        """
        build_result = self._context_builder.build(
            contract=contract,
            params=request.params,
            session_id=request.session_id,
            trace_id=request.trace_id,
            prompt_template_name=request.prompt_template,
            context_override=request.context_override,
        )
        return build_result.context

    # ==================================================================
    # Internal: Execution with CircuitBreaker
    # ==================================================================

    async def _execute_with_breaker(
        self,
        provider: Any,
        provider_id: str,
        request: CapabilityRequest,
        context: Any,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Execute via CircuitBreaker if available, else direct.

        If a CircuitBreaker is registered for this provider_id, wraps
        the execution.  Otherwise executes directly.

        Returns CapabilityResult (never raises).
        """
        breaker = self._circuit_breakers.get(provider_id)

        if breaker is not None:
            try:
                return await breaker.call(
                    provider.execute,
                    request,
                    context,
                    trace_id,
                )
            except Exception as exc:
                return CapabilityResult.failure_result(
                    request_id=request.request_id,
                    error_code="circuit_breaker_error",
                    error_message=str(exc),
                    retriable=True,
                    provider_id=provider_id,
                    trace_id=trace_id,
                )
        else:
            # Direct execution (no circuit breaker for this provider)
            try:
                return await provider.execute(request, context, trace_id)
            except Exception as exc:
                return CapabilityResult.failure_result(
                    request_id=request.request_id,
                    error_code="provider_error",
                    error_message=str(exc),
                    retriable=True,
                    provider_id=provider_id,
                    trace_id=trace_id,
                )

    # ==================================================================
    # Internal: Output validation
    # ==================================================================

    def _validate_output(
        self,
        result: CapabilityResult,
        contract: Any,
        provider_type: str,
        request: CapabilityRequest,
        execution_context: Any,
    ) -> CapabilityResult:
        """
        Run 3-tier output validation pipeline.

        On hard failure (structural/schema), returns a failure result.
        On soft failure (semantic), annotates but passes through.
        """
        try:
            outcome = self._validation_pipeline.validate(
                result=result,
                contract=contract,
                provider_type=provider_type,
                session_id=request.session_id,
                execution_context=(
                    execution_context.to_dict()
                    if hasattr(execution_context, "to_dict")
                    else execution_context
                ),
                request_id=request.request_id,
                provider_id=result.provider_id,
                trace_id=request.trace_id,
            )
        except Exception as exc:
            logger.warning(
                "Output validation error: %s",
                exc,
                exc_info=True,
            )
            # Validation error should not block result delivery
            return result

        if outcome.rejected:
            tier = ""
            if outcome.tier_results:
                tier_value = outcome.tier_results[-1].tier
                tier = getattr(tier_value, "value", str(tier_value))
            self._event_emitter.emit_output_validation_failed(
                capability_name=request.capability_name,
                request_id=request.request_id,
                provider_id=result.provider_id,
                validation_tier=tier,
                rejection_reason=outcome.rejection_reason,
                trace_id=request.trace_id,
            )
            return CapabilityResult.failure_result(
                request_id=result.request_id,
                error_code="output_validation_failed",
                error_message=outcome.rejection_reason,
                retriable=False,
                provider_id=result.provider_id,
                trace_id=result.trace_id,
                duration_ms=result.duration_ms,
            )

        # If coercion was applied, rebuild the result with corrected data
        if outcome.coerced_data is not None:
            return CapabilityResult.success_result(
                request_id=result.request_id,
                data=outcome.coerced_data,
                provider_id=result.provider_id,
                trace_id=result.trace_id,
                duration_ms=result.duration_ms,
                retrieval_time_ms=result.retrieval_time_ms,
                resolution_time_ms=result.resolution_time_ms,
                execution_time_ms=result.execution_time_ms,
            )

        return result

    # ==================================================================
    # Internal: Event emission helpers
    # ==================================================================

    def _emit_success(
        self,
        request: CapabilityRequest,
        result: CapabilityResult,
        provider_id: str,
        duration_ms: int,
    ) -> None:
        """Emit completed event."""
        self._event_emitter.emit_completed(
            capability_name=request.capability_name,
            request_id=request.request_id,
            trace_id=request.trace_id,
            provider_id=provider_id,
            duration_ms=duration_ms,
        )

    def _emit_failure(
        self,
        request: CapabilityRequest,
        result: CapabilityResult,
        start_time: float,
        provider_id: str = "",
    ) -> None:
        """Emit failed event."""
        elapsed_ms = _elapsed_ms(start_time)
        error = result.error
        self._event_emitter.emit_failed(
            capability_name=request.capability_name,
            request_id=request.request_id,
            trace_id=request.trace_id,
            error_code=error.code if error else "unknown",
            error_message=error.message if error else "Unknown error",
            provider_id=provider_id,
            duration_ms=elapsed_ms,
        )

    def _emit_learning(
        self,
        request: CapabilityRequest,
        provider_id: str,
        success: bool,
        duration_ms: int,
        error_code: Optional[str] = None,
    ) -> None:
        """Emit learning signal for K0 P09 feedback loop."""
        self._event_emitter.emit_learning_signal(
            capability_name=request.capability_name,
            provider_id=provider_id,
            success=success,
            duration_ms=duration_ms,
            trace_id=request.trace_id,
            error_code=error_code,
            context_quality_score=0.0,
        )

    def _update_metrics(
        self,
        capability_name: str,
        duration_ms: int,
        success: bool,
    ) -> None:
        """Update registry metrics (fault-isolated).

        ``CapabilityRegistry.update_metrics`` declares ``success`` /
        ``latency_ms`` as keyword-only, but the legacy ``IRegistry``
        protocol used positional args. Try the keyword-only signature
        first (production path), then fall back to positional for
        tests / alt registries.
        """
        try:
            self._registry.update_metrics(
                capability_name,
                latency_ms=int(duration_ms),
                success=success,
            )
        except TypeError:
            try:
                self._registry.update_metrics(  # type: ignore[call-arg]
                    capability_name,
                    float(duration_ms),
                    success,
                )
            except Exception:
                logger.warning(
                    "Failed to update metrics for '%s' (positional fallback)",
                    capability_name,
                    exc_info=True,
                )
        except Exception:
            logger.warning(
                "Failed to update metrics for '%s'",
                capability_name,
                exc_info=True,
            )

    def _finalize_execution_metrics(
        self,
        *,
        request: CapabilityRequest,
        result: CapabilityResult,
        provider_type: str,
        exec_start: float,
    ) -> CapabilityResult:
        """Finalize execution metrics and active execution gauge."""
        metrics = get_default_metrics()
        duration_s = time.perf_counter() - exec_start
        try:
            metrics.observe_execution_duration(
                capability_name=request.capability_name,
                provider_type=provider_type or "unknown",
                tier=request.tier,
                duration_seconds=duration_s,
            )
            metrics.inc_executions("success" if result.success else "failure")
        except Exception:
            logger.warning("Failed to record execution metrics", exc_info=True)
        finally:
            try:
                metrics.dec_active_executions()
            except Exception:
                logger.warning("Failed to decrement active executions", exc_info=True)
        return result

    # ==================================================================
    # Internal: Batch strategies
    # ==================================================================

    async def _execute_batch_parallel(
        self,
        requests: List[CapabilityRequest],
    ) -> List[CapabilityResult]:
        """
        Execute all requests concurrently via asyncio.gather().

        Results are returned in the same order as requests.
        Exceptions per-request are caught and returned as failure results.
        """
        tasks = [self.execute(req) for req in requests]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: List[CapabilityResult] = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, BaseException):
                results.append(
                    CapabilityResult.failure_result(
                        request_id=requests[i].request_id,
                        error_code="batch_execution_error",
                        error_message=str(raw),
                        retriable=True,
                        trace_id=requests[i].trace_id,
                    )
                )
            elif isinstance(raw, CapabilityResult):
                results.append(raw)
            else:
                results.append(
                    CapabilityResult.failure_result(
                        request_id=requests[i].request_id,
                        error_code="batch_unexpected_result",
                        error_message=f"Unexpected result type: {type(raw)}",
                        retriable=True,
                        trace_id=requests[i].trace_id,
                    )
                )

        return results

    async def _execute_batch_sequential(
        self,
        requests: List[CapabilityRequest],
    ) -> List[CapabilityResult]:
        """
        Execute requests sequentially in order.

        Each request completes before the next starts.
        Failed requests do not block subsequent requests.
        """
        results: List[CapabilityResult] = []
        for req in requests:
            result = await self.execute(req)
            results.append(result)
        return results

    async def _execute_batch_dag(
        self,
        requests: List[CapabilityRequest],
    ) -> List[CapabilityResult]:
        """
        Execute requests with dependency-aware ordering.

        Dependencies are extracted from request.params["_depends_on"],
        which is a list of request_ids that must complete before this
        request can execute.

        Requests without dependencies execute immediately.
        Results are returned in the ORIGINAL input order.
        """
        # Build dependency graph
        # request_id -> index in requests list
        id_to_idx: Dict[str, int] = {req.request_id: i for i, req in enumerate(requests)}

        # request_id -> set of request_ids it depends on
        deps: Dict[str, set] = {}
        for req in requests:
            depends_on = req.params.get("_depends_on", [])
            if isinstance(depends_on, list):
                deps[req.request_id] = {d for d in depends_on if d in id_to_idx}
            else:
                deps[req.request_id] = set()

        # Results array (ordered by input)
        results: List[Optional[CapabilityResult]] = [None] * len(requests)

        # Completed request_ids
        completed: set = set()

        # Topological execution in waves
        max_iterations = len(requests) + 1  # Guard against infinite loops
        iteration = 0

        while len(completed) < len(requests) and iteration < max_iterations:
            iteration += 1

            # Find ready requests (all deps satisfied)
            ready = []
            for req in requests:
                rid = req.request_id
                if rid in completed:
                    continue
                if deps.get(rid, set()).issubset(completed):
                    ready.append(req)

            if not ready:
                # Circular dependency or all remaining have unmet deps
                for req in requests:
                    if req.request_id not in completed:
                        idx = id_to_idx[req.request_id]
                        results[idx] = CapabilityResult.failure_result(
                            request_id=req.request_id,
                            error_code="dag_cycle_detected",
                            error_message="Circular dependency in DAG",
                            retriable=False,
                            trace_id=req.trace_id,
                        )
                        completed.add(req.request_id)
                break

            # Execute ready wave in parallel
            wave_tasks = [self.execute(req) for req in ready]
            wave_results = await asyncio.gather(*wave_tasks, return_exceptions=True)

            for req, raw in zip(ready, wave_results):
                idx = id_to_idx[req.request_id]
                if isinstance(raw, BaseException):
                    results[idx] = CapabilityResult.failure_result(
                        request_id=req.request_id,
                        error_code="batch_execution_error",
                        error_message=str(raw),
                        retriable=True,
                        trace_id=req.trace_id,
                    )
                elif isinstance(raw, CapabilityResult):
                    results[idx] = raw
                else:
                    results[idx] = CapabilityResult.failure_result(
                        request_id=req.request_id,
                        error_code="batch_unexpected_result",
                        error_message=f"Unexpected result type: {type(raw)}",
                        retriable=True,
                        trace_id=req.trace_id,
                    )
                completed.add(req.request_id)

        # Type narrowing: all slots should be filled
        return [
            (
                r
                if r is not None
                else CapabilityResult.failure_result(
                    request_id=requests[i].request_id,
                    error_code="dag_incomplete",
                    error_message="Request not executed",
                    retriable=True,
                    trace_id=requests[i].trace_id,
                )
            )
            for i, r in enumerate(results)
        ]


# ---------------------------------------------------------------------------
# 5.3.3 -- FabricRetrieval
# ---------------------------------------------------------------------------


class FabricRetrieval:
    """
    Discovery/retrieval API for the Capability Fabric (Role 1).

    Thin delegate over the RetrievalEngine (4.1.5).

    Methods:
      discover_capabilities() -- Find capabilities matching domain + intent
      find_relevant_prompts() -- Find prompt templates for intent

    Constructor Args:
        retrieval_engine: RetrievalEngine instance.

    Thread Safety:
        Stateless -- safe for concurrent calls.
    """

    __slots__ = ("_retrieval_engine",)

    def __init__(self, retrieval_engine: Any) -> None:
        self._retrieval_engine = retrieval_engine

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = SafetyBand.GREEN.value,
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """
        Discover capabilities matching domain + intent.

        Pipeline:
          1. Embed query (domain + intent)
          2. HardFilter (safety, availability, input satisfiability)
          3. SoftRank (semantic + domain + success + cost/latency)
          4. TopK selection

        Args:
            domain: Domain tag filter(s).
            intent: Natural-language description of desired capability.
            safety_band: Caller's safety band (default GREEN).
            session_context: Available session keys + param names.
            top_k: Number of results (default 10, max 25).

        Returns:
            RetrievalResult with list of ScoredCapability.
        """
        return self._retrieval_engine.discover_capabilities(
            domain=domain,
            intent=intent,
            safety_band=safety_band,
            session_context=session_context,
            top_k=top_k,
        )

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = SafetyBand.GREEN.value,
        top_k: int = 10,
    ) -> RetrievalResult:
        """
        Find relevant prompt templates for intent.

        Same pipeline as discover_capabilities, filtered to prompt-type
        contracts only.

        Args:
            intent: Natural-language description.
            domain: Domain tag filter(s).
            safety_band: Caller's safety band.
            top_k: Number of results.

        Returns:
            RetrievalResult with list of ScoredCapability (prompt-type only).
        """
        return self._retrieval_engine.find_relevant_prompts(
            intent=intent,
            domain=domain,
            safety_band=safety_band,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Diagnostics (observability-only; never called from production code)
    # ------------------------------------------------------------------

    def describe_capabilities(self) -> list[dict]:
        """Return a snapshot of all registered capabilities and their CB state.

        Intended exclusively for PORT-IDENTITY / SUBSCRIPTION-TOPOLOGY probes
        in ``tests/integration/k1/live/``.  Never call from production code.

        Returns:
            List of dicts with keys:
                name:          Capability name (str).
                contract_type: Type prefix or None.
                provider_id:   Provider identifier (str).
                availability:  Availability string (e.g. "ONLINE").
                cb_state:      CircuitBreaker state string or None.
        """
        results: list[dict] = []
        for contract in self._registry.list_all():
            name = getattr(contract, "name", "") or ""
            provider_id: str = getattr(contract, "provider_id", "") or ""
            contract_type = getattr(contract, "type", None) or getattr(
                contract, "contract_type", None
            )
            availability = getattr(contract, "availability", None)
            cb = self._circuit_breakers.get(provider_id)
            if cb is not None:
                cb_state = str(getattr(cb, "state", getattr(cb, "get_state", lambda: cb)()))
            else:
                cb_state = None
            results.append(
                {
                    "name": name,
                    "contract_type": str(contract_type) if contract_type else None,
                    "provider_id": provider_id,
                    "availability": str(availability) if availability else None,
                    "cb_state": cb_state,
                }
            )
        return results


# ---------------------------------------------------------------------------
# 5.3.4 -- CapabilityRegistryAPI
# ---------------------------------------------------------------------------


class CapabilityRegistryAPI:
    """
    Registry management API.

    Thin wrapper over the core CapabilityRegistry (2.2.1).
    Provides a clean public surface for external consumers
    (Orchestrator, Planner, Concierge).

    Constructor Args:
        registry: CapabilityRegistry instance.

    Thread Safety:
        Delegates to Registry which is internally thread-safe (RLock).
    """

    __slots__ = ("_registry",)

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def register(self, contract: Any) -> None:
        """Register a capability contract (validates first)."""
        self._registry.register(contract)

    def unregister(self, name: str) -> None:
        """Unregister a capability by name."""
        self._registry.unregister(name)

    def lookup(self, name: str, *, version: Optional[str] = None) -> Any:
        """O(1) exact lookup by capability name. Returns None if not found.

        Args:
            name: Canonical capability name.
            version: Optional exact version string (e.g. "2.1.0").
                When provided, looks up the exact version.
        """
        return self._registry.lookup(name, version=version)

    def contains(self, name: str) -> bool:
        """Check if a capability name is registered."""
        return self._registry.contains(name)

    def list_all(self) -> List[Any]:
        """List all registered capability contracts."""
        return self._registry.list_all()

    def list_by_domain(self, domain: str) -> List[Any]:
        """List all capabilities in a domain."""
        return self._registry.list_by_domain(domain)

    def list_by_type(self, type_prefix: str) -> List[Any]:
        """List by type prefix (e.g., 'agent.', 'tool.')."""
        return self._registry.list_by_type(type_prefix)

    def update_availability(self, name: str, status: str) -> None:
        """Update availability status for a capability."""
        self._registry.update_availability(name, status)

    def update_metrics(self, name: str, latency_ms: float, success: bool) -> None:
        """Update running metrics for a capability."""
        self._registry.update_metrics(name, latency_ms, success)

    def reload(self) -> None:
        """Full reload from disk."""
        self._registry.reload()

    def health(self) -> Any:
        """Registry health snapshot."""
        return self._registry.health()


# ---------------------------------------------------------------------------
# Fabric container
# ---------------------------------------------------------------------------


@dataclass
class Fabric:
    """
    Container for the complete Fabric system.

    Holds all public APIs and internal components.
    Created by FabricFactory (5.3.1).

    Attributes:
        facade: CapabilityFabric -- main execution API.
        retrieval: FabricRetrieval -- discovery API.
        registry_api: CapabilityRegistryAPI -- registry management.
        registry: Core CapabilityRegistry instance (for internal access).
        module_loader: ModuleLoader instance (for lifecycle management).
        health_checker: HealthChecker instance (for lifecycle management).
        event_port: Event port (for lifecycle management).
        event_emitter: EventEmitter (for direct event emission if needed).
    """

    facade: CapabilityFabric
    retrieval: FabricRetrieval
    registry_api: CapabilityRegistryAPI
    registry: Any = None
    module_loader: Any = None
    health_checker: Any = None
    event_port: Any = None
    event_emitter: Optional[EventEmitter] = None
    gap_detector: Any = None

    # ------------------------------------------------------------------
    # Convenience delegates
    # ------------------------------------------------------------------

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Delegate to facade.execute()."""
        return await self.facade.execute(request)

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
        strategy: BatchStrategy = BatchStrategy.PARALLEL,
    ) -> List[CapabilityResult]:
        """Delegate to facade.execute_batch()."""
        return await self.facade.execute_batch(requests, strategy)

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = SafetyBand.GREEN.value,
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Delegate to retrieval.discover_capabilities()."""
        return await self.retrieval.discover_capabilities(
            domain=domain,
            intent=intent,
            safety_band=safety_band,
            session_context=session_context,
            top_k=top_k,
        )

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = SafetyBand.GREEN.value,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Delegate to retrieval.find_relevant_prompts()."""
        return await self.retrieval.find_relevant_prompts(
            intent=intent,
            domain=domain,
            safety_band=safety_band,
            top_k=top_k,
        )

    def register(self, contract: Any) -> None:
        """Register a capability and emit registry event via EventEmitter (FAB-09)."""
        self.registry_api.register(contract)

        # 5.4.3: Emit through EventEmitter (adds cognitive_trace_id)
        if self.event_emitter is not None:
            cap_name = getattr(contract, "name", "")
            version = getattr(contract, "version", "")
            domain = getattr(contract, "domain", "")
            provider_type = getattr(contract, "provider_type", "")
            self.event_emitter.emit_registered(
                capability_name=cap_name,
                version=version,
                domain=domain,
                provider_type=provider_type,
            )

    def unregister(self, name: str) -> None:
        """Unregister a capability and emit registry event via EventEmitter (FAB-09)."""
        self.registry_api.unregister(name)

        # 5.4.3: Emit through EventEmitter (adds cognitive_trace_id)
        if self.event_emitter is not None:
            self.event_emitter.emit_unregistered(capability_name=name)

    def lookup(self, name: str, *, version: Optional[str] = None) -> Any:
        """Delegate to registry_api.lookup()."""
        return self.registry_api.lookup(name, version=version)

    def health(self) -> Any:
        """Delegate to registry_api.health()."""
        return self.registry_api.health()

    async def start_health_checker(self) -> None:
        """
        Start the HealthChecker periodic loop.

        Call after construction if you need active health monitoring
        (typically in production mode).  Standalone/testing modes can
        skip this.
        """
        if self.health_checker is not None:
            try:
                await self.health_checker.start()
                logger.info("HealthChecker started")
            except Exception:
                logger.warning("HealthChecker start failed", exc_info=True)

    async def shutdown(self) -> None:
        """
        Gracefully shut down all Fabric components.

        Stops the health checker loop, stops the module loader watcher,
        and cleans up resources.
        """
        if self.health_checker is not None:
            try:
                await self.health_checker.stop()
            except Exception:
                logger.warning("Health checker stop failed", exc_info=True)

        if self.module_loader is not None:
            try:
                self.module_loader.stop()
            except Exception:
                logger.warning("Module loader stop failed", exc_info=True)

        if self.gap_detector is not None:
            try:
                self.gap_detector.stop()
            except Exception:
                logger.warning("Proactive gap detector stop failed", exc_info=True)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _elapsed_ms(start_time: float) -> int:
    """Calculate elapsed milliseconds since start_time (monotonic)."""
    return int((time.monotonic() - start_time) * 1000)
