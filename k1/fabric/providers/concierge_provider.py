"""
k1.fabric.providers.concierge_provider -- ConciergeProvider (3.3.6).

Handles concierge.state.* capabilities by routing to the Concierge
FSM state handlers.

Execution flow (from fabric_discussion.md Section 11 -- Provider Type 6):
  1. Receive CapabilityRequest (e.g. "concierge.state.interrupt_check")
  2. Route to corresponding FSM state handler
  3. Handler processes the state transition
  4. Return CapabilityResult

Design:
  - All FSM interactions go through the ``IConciergeRouter`` port.
    Concrete implementation is the Concierge FSM dispatcher.
  - Lightweight provider -- no heavy computation or external I/O.
  - Stateless: no mutable state after construction.
  - The concierge.state.* namespace covers:
    - concierge.state.interrupt_check
    - concierge.state.greeting
    - concierge.state.farewell
    - concierge.state.clarify
    - concierge.state.handoff
    (extensible via IConciergeRouter)

References:
  - fabric_discussion.md Section 11 (Provider Type 6: Concierge Provider)
  - k1_cognitive_architecture_skeleton.mmd (Concierge subgraph)
  - whiteboard Section 3 (Concierge FSM states)
  - Epic 3.3.6 in fabric-implementation-plan.md

Wiring (from plan):
  - Routes to FSM state handlers
  - Lightweight -- no CircuitBreaker needed (local in-process)
  - Consumed by ProviderFactory (3.1.4)

Exports:
  ConciergeProvider          -- Concierge FSM routing provider
  IConciergeRouter           -- FSM routing port protocol
  ConciergeStateRequest      -- State handler request
  ConciergeStateResponse     -- State handler response
  ConciergeProviderError     -- Base concierge exception
  ConciergeStateNotFoundError -- Unknown FSM state
  ConciergeHandlerError      -- State handler failed
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.providers.base_provider import BaseProvider, ProviderExecutionError
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)

# Capability namespace prefix for concierge state operations
CONCIERGE_STATE_PREFIX: str = "concierge.state."


# ---------------------------------------------------------------------------
# Concierge message types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConciergeStateRequest:
    """
    Request message for a Concierge FSM state handler.

    Attributes:
        state_name: The FSM state to invoke (e.g. "interrupt_check").
        params: Parameters from CapabilityRequest.params.
        session_id: Current session identifier.
        trace_id: Cognitive trace ID for observability.
    """

    state_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class ConciergeStateResponse:
    """
    Response from a Concierge FSM state handler.

    Attributes:
        success: Whether the state operation succeeded.
        data: Response payload (FSM state data, transition info).
        next_state: Optional next FSM state (if transition occurred).
        error_message: Error description if success=False.
    """

    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    next_state: Optional[str] = None
    error_message: str = ""


# ---------------------------------------------------------------------------
# Concierge router port (Protocol)
# ---------------------------------------------------------------------------


class IConciergeRouter(Protocol):
    """
    Port protocol for routing to Concierge FSM state handlers.

    Concrete implementation dispatches to the appropriate FSM state
    handler based on state_name. Injected by FabricFactory.
    """

    async def route(
        self,
        request: ConciergeStateRequest,
    ) -> ConciergeStateResponse:
        """
        Route a state request to the appropriate FSM handler.

        Args:
            request: The state request with state_name and params.

        Returns:
            ConciergeStateResponse from the handler.

        Raises:
            Exception if the state handler fails or state is unknown.
        """
        ...

    def known_states(self) -> List[str]:
        """
        List of known FSM state names this router can handle.

        Returns:
            List of state names (e.g. ["interrupt_check", "greeting"]).
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConciergeProviderError(ProviderExecutionError):
    """Base exception for concierge provider operations."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(
            provider_id,
            message,
            retriable=retriable,
            error_code="concierge_error",
        )


class ConciergeStateNotFoundError(ConciergeProviderError):
    """Unknown FSM state requested."""

    def __init__(self, provider_id: str, state_name: str) -> None:
        self.state_name = state_name
        super().__init__(
            provider_id,
            f"Unknown concierge state: '{state_name}'",
            retriable=False,
        )


class ConciergeHandlerError(ConciergeProviderError):
    """FSM state handler failed during execution."""

    def __init__(
        self,
        provider_id: str,
        state_name: str,
        cause: str,
    ) -> None:
        self.state_name = state_name
        self.cause = cause
        super().__init__(
            provider_id,
            f"Concierge handler '{state_name}' failed: {cause}",
            retriable=False,
        )


# ---------------------------------------------------------------------------
# ConciergeProvider
# ---------------------------------------------------------------------------


class ConciergeProvider(BaseProvider):
    """
    Concierge FSM routing provider (3.3.6).

    Routes ``concierge.state.*`` capabilities to the corresponding
    FSM state handler via the injected ``IConciergeRouter`` port.

    Lightweight -- no heavy computation, no external I/O beyond
    the in-process concierge FSM dispatcher.

    Constructor Args:
        config: ProviderConfig with provider_id and type.
        router: IConciergeRouter for FSM state dispatch.
        capability_names: List of concierge.state.* capabilities.

    Usage::

        provider = ConciergeProvider(
            config=ProviderConfig(
                provider_id="concierge",
                provider_type="CONCIERGE",
            ),
            router=my_concierge_router,
            capability_names=[
                "concierge.state.interrupt_check",
                "concierge.state.greeting",
            ],
        )
        result = await provider.execute(request, context, trace_id)
    """

    __slots__ = ("_router", "_capability_names")

    def __init__(
        self,
        config: ProviderConfig,
        *,
        router: IConciergeRouter,
        capability_names: Optional[List[str]] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(config)
        self._router = router
        self._capability_names: List[str] = list(capability_names or [])

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of concierge.state.* capabilities."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Concierge health: verify router is available.

        In-process, so usually always healthy.
        """
        try:
            states = self._router.known_states()
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.HEALTHY.value,
            )
        except Exception as exc:
            logger.warning("[%s] health_check failed: %s", self.provider_id, exc)
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                error=str(exc),
            )

    # ======================================================================
    # Internal execution (BaseProvider._execute)
    # ======================================================================

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Concierge-specific execution logic.

        Flow:
          1. Extract state_name from capability_name
          2. Build ConciergeStateRequest
          3. Route to FSM handler
          4. Parse response into CapabilityResult
        """
        start = time.monotonic()

        # --- Step 1: Extract state name ---
        state_name = self._extract_state_name(request.capability_name)

        # --- Step 2: Build state request ---
        state_request = ConciergeStateRequest(
            state_name=state_name,
            params=dict(request.params),
            session_id=request.session_id,
            trace_id=trace_id,
        )

        logger.debug(
            "[%s] routing to state: %s (trace=%s)",
            self.provider_id,
            state_name,
            trace_id,
        )

        # --- Step 3: Route to FSM handler ---
        try:
            state_response = await self._router.route(state_request)
        except Exception as exc:
            raise ConciergeHandlerError(self.provider_id, state_name, str(exc)) from exc

        # --- Step 4: Parse response ---
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if not state_response.success:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="concierge_state_error",
                error_message=state_response.error_message or f"State '{state_name}' failed",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
            )

        data: Dict[str, Any] = dict(state_response.data)
        if state_response.next_state is not None:
            data["next_state"] = state_response.next_state

        return CapabilityResult.success_result(
            request_id=request.request_id,
            data=data,
            provider_id=self.provider_id,
            trace_id=trace_id,
            duration_ms=elapsed_ms,
        )

    # ======================================================================
    # Private helpers
    # ======================================================================

    @staticmethod
    def _extract_state_name(capability_name: str) -> str:
        """
        Extract FSM state name from capability name.

        "concierge.state.interrupt_check" -> "interrupt_check"
        """
        if capability_name.startswith(CONCIERGE_STATE_PREFIX):
            return capability_name[len(CONCIERGE_STATE_PREFIX) :]
        return capability_name

    def __repr__(self) -> str:
        return (
            f"ConciergeProvider("
            f"provider_id={self.provider_id!r}, "
            f"capabilities={len(self._capability_names)})"
        )
