"""
k1.orchestrator.adapters.planner_adapter -- PlannerAdapter (6.1.3).

Production adapter for IPlannerPort.

Design:
  - Wraps a ``planner_mailbox`` (async interface to the Planner module).
  - OWNS ``CB_PLANNER`` (CircuitBreaker instance from k1.fabric.circuit_breaker).
  - ``request_plan()``: CB gate -> enqueue PlanRequest -> PlanAck.
  - ``cancel_plan()``: best-effort cancel via mailbox.
  - ``micro_replan()``: synchronous 10s timeout via ``asyncio.wait_for``.

CB_PLANNER ownership rationale:
  Orchestrator is the direct caller to Planner's mailbox.  The CB wraps
  outbound calls from Orchestrator to Planner.  This is distinct from
  CB_FABRIC (owned by Concierge per PROTOCOL-4).

Error Mapping:
  - CB OPEN          -> AdapterException(DEGRADED, "CB_PLANNER open")
  - Planner rejection -> PlanAck(REJECTED) (not an error)
  - Enqueue failure   -> AdapterException(RECOVERABLE, "enqueue failed")
  - micro_replan timeout -> returns None (not an error)
  - micro_replan failure -> AdapterException(DEGRADED, "micro_replan failed")

References:
  - Issue 6.1.3 in orchestrator-implementation-plan.md
  - PROTOCOL-3 (micro-replan synchronous 10s timeout)
  - ADR ORCH-012 (event-driven plan delivery)

Exports:
  PlannerAdapter
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Protocol

from k1.fabric.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerState
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import (
    AdapterError,
    CommittedPlan,
    ErrorSeverity,
    MicroReplanRequest,
    PlanAck,
    PlanRequest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Planner mailbox protocol (structural typing for the Planner module)
# ---------------------------------------------------------------------------

_MICRO_REPLAN_TIMEOUT_S: float = 10.0


class IPlannerMailbox(Protocol):
    """Structural protocol for the Planner's inbound mailbox.

    The Planner module will expose an object satisfying this protocol.
    PlannerAdapter depends on it via structural subtyping (duck typing).
    """

    async def enqueue(self, request: PlanRequest) -> None:
        """Enqueue a plan request for asynchronous processing."""
        ...  # pragma: no cover

    async def send_cancel(self, request_id: str) -> None:
        """Signal cancellation for an in-flight plan request."""
        ...  # pragma: no cover

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        """Synchronous micro-replan (Planner responds inline)."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# 6.1.3 -- PlannerAdapter
# ---------------------------------------------------------------------------


class PlannerAdapter:
    """
    Production IPlannerPort adapter wrapping the Planner mailbox.

    Owns CB_PLANNER: checks circuit state before every outbound call
    and records success/failure to maintain the breaker.

    Constructor Args:
        planner_mailbox: Object satisfying ``IPlannerMailbox`` protocol
            (structural typing -- Planner module provides this).
        cb_planner: ``CircuitBreaker`` instance configured for Planner
            (timeout_s=45, failure_threshold=2, reset_interval_s=60).

    Thread Safety:
        Safe for concurrent ``request_plan()`` / ``cancel_plan()`` calls.
        ``micro_replan()`` is called from a single DAGExecutor task.
    """

    __slots__ = ("_mailbox", "_cb")

    def __init__(
        self,
        planner_mailbox: Any,
        cb_planner: CircuitBreaker,
    ) -> None:
        self._mailbox = planner_mailbox
        self._cb = cb_planner

    # ==================================================================
    # IPlannerPort implementation
    # ==================================================================

    async def request_plan(self, request: PlanRequest) -> PlanAck:
        """
        Submit a plan request to the Planner (fire-and-forget).

        Flow:
          1. Check CB_PLANNER state -- if OPEN, raise AdapterException(DEGRADED).
          2. Enqueue PlanRequest to planner_mailbox.
          3. Return PlanAck(ACCEPTED).
          4. On enqueue failure: return PlanAck(REJECTED, reason).

        Args:
            request: PlanRequest with intent, constraints, context.

        Returns:
            PlanAck with status ACCEPTED or REJECTED.

        Raises:
            AdapterException: DEGRADED if CB_PLANNER is OPEN.
        """
        self._check_cb_open(request.trace_id, "request_plan")

        try:
            await self._mailbox.enqueue(request)
            self._cb.reset()  # Record success -- keep breaker healthy
            return PlanAck(
                request_id=request.request_id,
                status="ACCEPTED",
                estimated_duration_ms=request.timeout_ms,
            )
        except Exception as exc:
            self._cb.trip()  # Record failure
            logger.warning(
                "PlannerAdapter.request_plan enqueue failed: %s",
                exc,
            )
            return PlanAck(
                request_id=request.request_id,
                status="REJECTED",
            )

    async def cancel_plan(self, request_id: str) -> None:
        """
        Cancel an in-progress planning request.

        Best-effort: the Planner may have already committed the plan.
        Does not check CB (cancel should always be attempted).

        Args:
            request_id: The request_id from the original PlanRequest.
        """
        try:
            await self._mailbox.send_cancel(request_id)
        except Exception as exc:
            logger.warning(
                "PlannerAdapter.cancel_plan failed for %s: %s",
                request_id,
                exc,
            )

    async def micro_replan(
        self,
        request: MicroReplanRequest,
    ) -> Optional[CommittedPlan]:
        """
        Request a synchronous micro-replan during DAG execution.

        Blocks for up to 10s (PROTOCOL-3).  On timeout, returns None.
        CB_PLANNER records timeout as failure.

        Args:
            request: MicroReplanRequest with completed results,
                remaining steps, and optional discoveries.

        Returns:
            New CommittedPlan or None on timeout.

        Raises:
            AdapterException: DEGRADED if CB_PLANNER is OPEN or
                Planner is unreachable (non-timeout failure).
        """
        self._check_cb_open(request.trace_id, "micro_replan")

        try:
            plan = await asyncio.wait_for(
                self._mailbox.micro_replan(request),
                timeout=_MICRO_REPLAN_TIMEOUT_S,
            )
            self._cb.reset()  # Record success
            return plan
        except asyncio.TimeoutError:
            self._cb.trip()  # Record failure -- timeout counts
            logger.warning(
                "PlannerAdapter.micro_replan timed out after %.1fs for plan %s",
                _MICRO_REPLAN_TIMEOUT_S,
                request.original_plan_id,
            )
            return None
        except Exception as exc:
            self._cb.trip()  # Record failure
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="planner",
                    operation="micro_replan",
                    error_code="PLANNER_ERROR",
                    error_message=f"micro_replan failed: {exc}",
                    original_exception=exc,
                    trace_id=request.trace_id,
                )
            ) from exc

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _check_cb_open(self, trace_id: str, operation: str) -> None:
        """Raise AdapterException if CB_PLANNER is OPEN."""
        if self._cb.state == CircuitBreakerState.OPEN:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="planner",
                    operation=operation,
                    error_code="CB_PLANNER_OPEN",
                    error_message="CB_PLANNER is OPEN -- Planner unreachable",
                    trace_id=trace_id,
                )
            )
