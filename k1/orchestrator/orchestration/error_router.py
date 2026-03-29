"""
ErrorRouter -- Stateless error classification service (Issue 2.1.7).

Classifies AdapterError instances into ErrorAction decisions.
ErrorRouter does NOT execute recovery actions -- it classifies and
returns.  Caller (OrchestratorService, DAGExecutor, StepRunner)
executes the ErrorAction.

Classification matrix (per WB S7):
  Mailbox     + RECOVERABLE -> RETRY(1)
  DeltaEmit   + RECOVERABLE -> RETRY(1)
  BridgeWrite + RECOVERABLE -> RETRY(1)
  EventSub    + RECOVERABLE -> RETRY(1)
  FabricGW    + DEGRADED    -> DEGRADE (partial result)
  Planner     + DEGRADED    -> FALLBACK (degrade HIGH to MEDIUM)
  StateRead   + DEGRADED    -> DEGRADE (empty snapshot)
  Any         + TERMINAL    -> ABORT

After classification, emits ORCH_ERROR_ROUTED diagnostic delta
(fire-and-forget) when route_error() is called.

Stateless: no mutable internal state.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

from k1.orchestrator.events import ORCH_ERROR_ROUTED
from k1.orchestrator.tracing import trace_phase
from k1.orchestrator.types import AdapterError, ErrorAction, ErrorSeverity, ProcessingContext

if TYPE_CHECKING:
    from k1.orchestrator.orchestration.orchestrator_service import AdapterException

log = logging.getLogger(__name__)

# Adapters whose RECOVERABLE errors warrant a retry.
_RECOVERABLE_RETRY_ADAPTERS: frozenset = frozenset(
    {"mailbox", "delta_emit", "bridge_write", "event_sub"}
)


class ErrorRouter:
    """Stateless error classification service.

    Constructor-injected with IDeltaEmitPort for diagnostic deltas.
    No mutable internal state.

    Two interfaces:
      route_error() -- async, returns ErrorAction, emits diagnostic delta.
      classify()    -- sync, returns ErrorSeverity only (no delta emission).
                       Used by OrchestratorService catch blocks (2.1.1-2.1.4).
    """

    __slots__ = ("_delta_port",)

    def __init__(self, delta_port: Any) -> None:
        """Construct ErrorRouter.

        Args:
            delta_port: IDeltaEmitPort for diagnostic delta emission.
        """
        self._delta_port = delta_port

    # ------------------------------------------------------------------
    # Primary interface (async, with delta emission)
    # ------------------------------------------------------------------

    async def route_error(
        self,
        error: AdapterError,
        context: Dict[str, Any],
    ) -> ErrorAction:
        """Classify an AdapterError and return an ErrorAction.

        Emits ORCH_ERROR_ROUTED diagnostic delta after classification.

        Args:
            error: Structured error from a port adapter.
            context: Contextual information (must include ``trace_id``).

        Returns:
            ErrorAction with action, retry_count, fallback_value, reason.
        """
        action = self._classify_error(error)
        trace_id = context.get("trace_id", error.trace_id or "")

        # Diagnostic delta (fire-and-forget).
        try:
            await self._delta_port.emit(
                event_topic=ORCH_ERROR_ROUTED,
                payload={
                    "adapter": error.adapter_name,
                    "severity": error.severity.value,
                    "action": action.action,
                    "retry_count": action.retry_count,
                    "reason": action.reason,
                    "error_code": error.error_code,
                    "error_message": error.error_message,
                    "operation": error.operation,
                    "trace_id": trace_id,
                },
                trace_id=trace_id,
            )
        except Exception:
            # Delta emission itself failed -- log and continue.
            # ErrorRouter must not amplify failures.
            log.debug(
                "error_router.delta_emission_failed",
                exc_info=True,
                extra={"trace_id": trace_id},
            )

        return action

    # ------------------------------------------------------------------
    # Sync convenience interface (backward compat for OrchestratorService)
    # ------------------------------------------------------------------

    def classify(
        self,
        error: "AdapterException",
        ctx: ProcessingContext,
    ) -> ErrorSeverity:
        """Sync severity-only classification.

        Used by OrchestratorService catch blocks where the caller already
        handles severity -> ProcessResult mapping.  Does NOT emit
        diagnostic delta (callers do their own structured logging).

        Args:
            error: AdapterException wrapping an AdapterError.
            ctx: Processing context (unused in V1, reserved for future
                 context-aware classification).

        Returns:
            ErrorSeverity from the wrapped AdapterError.
        """
        trace_phase(
            log,
            "error",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            tier=ctx.tier,
            success=False,
            level=logging.ERROR,
            extra={
                "adapter": error.adapter_name,
                "operation": error.operation,
                "classification": error.severity.value,
                "error_code": error.error_code,
            },
        )
        return error.severity

    # ------------------------------------------------------------------
    # Internal classification logic
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_error(error: AdapterError) -> ErrorAction:
        """Pure classification: AdapterError -> ErrorAction.

        Classification matrix (per plan spec 2.1.7):

        RECOVERABLE severity:
          adapter in {mailbox, delta_emit, bridge_write, event_sub}
            -> RETRY(retry_count=1, reason="transient error")
          unknown adapter (defensive)
            -> RETRY(retry_count=1, reason="transient error (unknown adapter)")

        DEGRADED severity:
          fabric_gateway -> DEGRADE(fallback_value=None, reason="Fabric step failed")
          planner        -> FALLBACK(fallback_value=None, reason="degrade HIGH to MEDIUM")
          state_read     -> DEGRADE(fallback_value={}, reason="stale context")
          unknown adapter (defensive)
            -> DEGRADE(fallback_value=None, reason="degraded (unknown adapter)")

        TERMINAL severity:
          Any adapter -> ABORT(reason=error.error_message)
        """
        severity = error.severity

        if severity == ErrorSeverity.TERMINAL:
            return ErrorAction(
                action="ABORT",
                retry_count=0,
                fallback_value=None,
                reason=error.error_message,
            )

        if severity == ErrorSeverity.RECOVERABLE:
            if error.adapter_name in _RECOVERABLE_RETRY_ADAPTERS:
                return ErrorAction(
                    action="RETRY",
                    retry_count=1,
                    fallback_value=None,
                    reason="transient error",
                )
            # Defensive: unknown adapter but RECOVERABLE -> still retry.
            return ErrorAction(
                action="RETRY",
                retry_count=1,
                fallback_value=None,
                reason=f"transient error (unknown adapter: {error.adapter_name})",
            )

        if severity == ErrorSeverity.DEGRADED:
            adapter = error.adapter_name
            if adapter == "fabric_gateway":
                return ErrorAction(
                    action="DEGRADE",
                    retry_count=0,
                    fallback_value=None,
                    reason="Fabric step failed",
                )
            if adapter == "planner":
                return ErrorAction(
                    action="FALLBACK",
                    retry_count=0,
                    fallback_value=None,
                    reason="degrade HIGH to MEDIUM",
                )
            if adapter == "state_read":
                return ErrorAction(
                    action="DEGRADE",
                    retry_count=0,
                    fallback_value={},
                    reason="stale context",
                )
            # Defensive: unknown adapter but DEGRADED -> degrade.
            return ErrorAction(
                action="DEGRADE",
                retry_count=0,
                fallback_value=None,
                reason=f"degraded (unknown adapter: {error.adapter_name})",
            )

        # Defensive: unknown severity -> abort.
        return ErrorAction(
            action="ABORT",
            retry_count=0,
            fallback_value=None,
            reason=f"unknown severity: {error.severity}",
        )
