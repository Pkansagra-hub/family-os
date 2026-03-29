"""
k1.fabric.providers.bridge_provider -- BridgeProvider (3.3.4).

Cross-kernel proxy that routes capabilities through the Bridge to K0
and external devices via IFL.

Execution flow (from fabric_discussion.md Section 11 -- Provider Type 3):
  1. Receive CapabilityRequest
  2. Map capability_name to bridge operation
  3. Send via Bridge Client (IBridgePort)
  4. K0 offline -> fallback to LOCAL COLD (K1 SQLite)
  5. Return CapabilityResult

Supported bridge operations:
  - memory.store   -- Write to K0 memory
  - memory.recall  -- Read from K0 memory
  - memory.delta   -- Apply delta to K0 memory
  - checkpoint      -- Checkpoint session state
  - feedback.signal -- Send feedback signal

IFL-routed operations:
  - tool.execute.home.*   -- Home automation devices (via IFL)
  - tool.execute.device.* -- Personal devices (via IFL)

K0 health modes (from bridge_architecture.mmd):
  - K0_FULL      -- Normal operation
  - K0_DEGRADED  -- Slow, may timeout
  - K0_OFFLINE   -- Fallback to LOCAL COLD (K1 SQLite)

Design:
  - K0 access is injected via ``IBridgePort`` (Protocol).
    Concrete implementation is BridgeConnectionAdapter (5.2.8).
  - BridgeProvider does NOT depend on Bridge internals at import time.
  - Stateless: no mutable state after construction.

References:
  - fabric_discussion.md Section 11 (Provider Type 3: Bridge Provider)
  - k1_cognitive_architecture_skeleton.mmd (CROSS_KERNEL_BRIDGE subgraph)
  - bridge_architecture.mmd (Bridge responsibilities & health modes)
  - whiteboard Section 7 (Fabric: Bridge operations)
  - Epic 3.3.4 in fabric-implementation-plan.md

Wiring (from plan):
  - Uses IBridgePort (5.1.3)
  - Routes via BridgeConnectionAdapter (5.2.8)
  - Wrapped by CircuitBreaker (10s timeout, 3 failures/min)
  - Gracefully degrades when Bridge unavailable

Exports:
  BridgeProvider            -- K0 connector proxy provider
  IBridgePort               -- Bridge access port protocol
  BridgeCommand             -- Command message for bridge
  BridgeResponse            -- Response message from bridge
  BridgeProviderError       -- Base Bridge exception
  BridgeUnavailableError    -- Bridge/K0 not reachable
  BridgeOperationError      -- Bridge operation failed
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Protocol

from k1.fabric.ports.bridge_port import (
    BridgeCommandResult,
    BridgeHealth,
    IBridgePort as CanonicalIBridgePort,
)
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


# ---------------------------------------------------------------------------
# K0 Health Modes (from bridge_architecture.mmd)
# ---------------------------------------------------------------------------


class K0HealthMode(str, Enum):
    """K0 health modes as observed through the Bridge."""

    K0_FULL = "K0_FULL"
    K0_DEGRADED = "K0_DEGRADED"
    K0_OFFLINE = "K0_OFFLINE"


# ---------------------------------------------------------------------------
# Bridge message types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeCommand:
    """
    Command message sent through the Bridge to K0.

    Attributes:
        operation: The bridge operation (e.g. "memory.store", "checkpoint").
        topic: Event bus topic for routing.
        body: Payload data.
        trace_id: Cognitive trace ID for observability.
        timeout_ms: Per-command timeout (0 = use provider default).
    """

    operation: str = ""
    topic: str = ""
    body: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    timeout_ms: int = 0


@dataclass(frozen=True)
class BridgeResponse:
    """
    Response message from Bridge/K0.

    Attributes:
        success: Whether the operation succeeded.
        data: Response payload.
        error_message: Error description if success=False.
        k0_health: Current K0 health mode at time of response.
        latency_ms: Round-trip latency to K0.
    """

    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    k0_health: str = K0HealthMode.K0_FULL.value
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Bridge port (Protocol)
# ---------------------------------------------------------------------------


# IBridgePort: Use canonical port from k1.fabric.ports.bridge_port.
# Kept as alias for backward compatibility in type hints.
IBridgePort = CanonicalIBridgePort

    # health_mode() removed -- use canonical get_health() from IBridgePort.


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BridgeProviderError(ProviderExecutionError):
    """Base exception for Bridge provider operations."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = True,
    ) -> None:
        super().__init__(
            provider_id,
            message,
            retriable=retriable,
            error_code="bridge_error",
        )


class BridgeUnavailableError(BridgeProviderError):
    """Bridge connection to K0 is unavailable."""

    def __init__(
        self,
        provider_id: str,
        reason: str = "",
        *,
        k0_health: str = K0HealthMode.K0_OFFLINE.value,
    ) -> None:
        self.k0_health = k0_health
        detail = f": {reason}" if reason else ""
        super().__init__(
            provider_id,
            f"Bridge unavailable (K0 health: {k0_health}){detail}",
            retriable=True,
        )


class BridgeOperationError(BridgeProviderError):
    """A bridge operation failed."""

    def __init__(
        self,
        provider_id: str,
        operation: str,
        reason: str = "",
        *,
        retriable: bool = True,
    ) -> None:
        self.operation = operation
        detail = f": {reason}" if reason else ""
        super().__init__(
            provider_id,
            f"Bridge operation '{operation}' failed{detail}",
            retriable=retriable,
        )


# ---------------------------------------------------------------------------
# Operation routing
# ---------------------------------------------------------------------------

# Known bridge operations that route to K0 directly
BRIDGE_OPERATIONS: FrozenSet[str] = frozenset(
    {
        "memory.store",
        "memory.recall",
        "memory.delta",
        "checkpoint",
        "feedback.signal",
    }
)

# IFL-routed prefixes (tool.execute.home.*, tool.execute.device.*)
IFL_PREFIXES = ("tool.execute.home.", "tool.execute.device.")


def _classify_operation(capability_name: str) -> str:
    """
    Map a capability name to a bridge operation.

    Direct bridge operations: memory.store, memory.recall, etc.
    IFL operations: tool.execute.home.*, tool.execute.device.*

    Args:
        capability_name: The capability name from the request.

    Returns:
        The operation string (bridge operation or IFL topic).
    """
    # Direct bridge operation match
    if capability_name in BRIDGE_OPERATIONS:
        return capability_name

    # IFL-routed tool execution
    for prefix in IFL_PREFIXES:
        if capability_name.startswith(prefix):
            return capability_name

    # Default: pass through as-is (BridgeProvider validates later)
    return capability_name


# ---------------------------------------------------------------------------
# BridgeProvider
# ---------------------------------------------------------------------------


class BridgeProvider(BaseProvider):
    """
    Cross-kernel proxy provider (3.3.4).

    Routes capabilities through the Bridge to K0 and external devices.
    Gracefully degrades when K0 is offline by falling back to LOCAL COLD.

    Constructor Args:
        config: ProviderConfig with bridge_endpoint, operations, limits.
        bridge: IBridgePort implementation for K0 access.
        capability_names: List of capability names this provider handles.
        fallback_fn: Optional async function for offline fallback
            (LOCAL COLD). Signature: (request, context) -> CapabilityResult.

    Usage::

        provider = BridgeProvider(
            config=ProviderConfig(
                provider_id="k0_memory_bridge",
                provider_type="BRIDGE",
                endpoint="bridge://k0",
                max_execution_ms=10000,
            ),
            bridge=my_bridge_port,
            capability_names=[
                "memory.store", "memory.recall", "memory.delta",
                "checkpoint", "feedback.signal",
            ],
        )
        result = await provider.execute(request, context, trace_id)

    Wrapped by CircuitBreaker (3.4.1): 10s timeout, 3 failures/min.
    """

    __slots__ = (
        "_bridge",
        "_capability_names",
        "_fallback_fn",
    )

    def __init__(
        self,
        config: ProviderConfig,
        *,
        bridge: IBridgePort,
        capability_names: Optional[List[str]] = None,
        fallback_fn: Any = None,
        **_kwargs: Any,
    ) -> None:
        """
        Args:
            config: Provider configuration (endpoint, limits).
            bridge: IBridgePort implementation (injected).
            capability_names: Capabilities this provider handles.
            fallback_fn: Optional async callable for LOCAL COLD fallback.
            **_kwargs: Ignored (ProviderFactory pass-through).
        """
        super().__init__(config)
        self._bridge = bridge
        self._capability_names: List[str] = list(capability_names or [])
        self._fallback_fn = fallback_fn

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of capability names this Bridge provider handles."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Check Bridge and K0 availability.

        Checks bridge connectivity and K0 health mode via get_health().
        Returns DEGRADED for K0_DEGRADED, UNHEALTHY for K0_OFFLINE.
        """
        start = time.monotonic()
        try:
            if not self._bridge.is_available():
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=ProviderStatus.UNHEALTHY.value,
                    error="Bridge not available",
                )

            health = self._bridge.get_health()
            mode_str = health.mode if hasattr(health, "mode") else "K0_OFFLINE"
            latency_ms = int((time.monotonic() - start) * 1000)

            if mode_str == K0HealthMode.K0_FULL.value:
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=ProviderStatus.HEALTHY.value,
                    latency_ms=latency_ms,
                )
            if mode_str == K0HealthMode.K0_DEGRADED.value:
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=ProviderStatus.DEGRADED.value,
                    latency_ms=latency_ms,
                    error="K0 degraded",
                )
            # K0_OFFLINE
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                latency_ms=latency_ms,
                error="K0 offline",
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("[%s] health_check failed: %s", self.provider_id, exc)
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                latency_ms=latency_ms,
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
        Bridge-specific execution logic.

        Flow:
          1. Check bridge availability and K0 health
          2. If K0_OFFLINE and fallback available -> use fallback
          3. Classify operation from capability_name
          4. Build BridgeCommand
          5. Send via IBridgePort (send_command or query)
          6. Parse response -> CapabilityResult
        """
        start = time.monotonic()

        # --- Step 1: Check bridge availability ---
        if not self._bridge.is_available():
            return await self._handle_offline(request, context, trace_id, start)

        health = self._bridge.get_health()
        mode_str = health.mode if hasattr(health, "mode") else "K0_OFFLINE"

        # --- Step 2: K0_OFFLINE fallback ---
        if mode_str == K0HealthMode.K0_OFFLINE.value:
            return await self._handle_offline(request, context, trace_id, start)

        # --- Step 3: Classify operation ---
        operation = _classify_operation(request.capability_name)

        logger.debug(
            "[%s] bridge exec: operation=%s, k0_health=%s, trace=%s",
            self.provider_id,
            operation,
            mode_str,
            trace_id,
        )

        # --- Step 4: Prepare command args (canonical IBridgePort signature) ---
        timeout = request.timeout_ms or self.config.max_execution_ms
        payload = dict(request.params)

        # --- Step 5: Send via bridge ---
        try:
            if self._is_query_operation(operation):
                response = await self._bridge.query(
                    operation=operation,
                    selectors=payload,
                    trace_id=trace_id,
                    timeout_ms=timeout,
                )
            else:
                response = await self._bridge.send_command(
                    operation=operation,
                    payload=payload,
                    trace_id=trace_id,
                    timeout_ms=timeout,
                )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Check timeout
            self._check_timeout(start)
            # Try fallback on bridge failure
            if self._fallback_fn is not None:
                logger.warning(
                    "[%s] bridge failed, falling back to LOCAL COLD: %s",
                    self.provider_id,
                    exc,
                )
                return await self._execute_fallback(request, context, trace_id, start)
            raise BridgeOperationError(
                self.provider_id,
                operation,
                str(exc),
                retriable=True,
            ) from exc

        # --- Step 6: Check timeout ---
        self._check_timeout(start)

        # --- Step 7: Parse response ---
        return self._parse_response(request, response, trace_id, start)

    # ======================================================================
    # Offline / fallback handling
    # ======================================================================

    async def _handle_offline(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
        start: float,
    ) -> CapabilityResult:
        """Handle K0_OFFLINE: try fallback or return failure."""
        if self._fallback_fn is not None:
            logger.info(
                "[%s] K0 offline, using LOCAL COLD fallback (trace=%s)",
                self.provider_id,
                trace_id,
            )
            return await self._execute_fallback(request, context, trace_id, start)

        raise BridgeUnavailableError(
            self.provider_id,
            "K0 offline and no fallback configured",
            k0_health=K0HealthMode.K0_OFFLINE.value,
        )

    async def _execute_fallback(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
        start: float,
    ) -> CapabilityResult:
        """Execute via LOCAL COLD fallback function."""
        try:
            result = await self._fallback_fn(request, context)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.debug(
                "[%s] fallback complete in %dms (success=%s)",
                self.provider_id,
                elapsed_ms,
                result.success,
            )
            return result
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            raise BridgeOperationError(
                self.provider_id,
                "local_cold_fallback",
                str(exc),
                retriable=False,
            ) from exc

    # ======================================================================
    # Private helpers
    # ======================================================================

    @staticmethod
    def _is_query_operation(operation: str) -> bool:
        """Whether an operation is read-only (uses query instead of command)."""
        return operation == "memory.recall"

    @staticmethod
    def _operation_to_topic(operation: str) -> str:
        """
        Map bridge operation to event bus topic.

        Direct bridge ops get a bridge.* prefix.
        IFL ops use the capability name directly as the topic.
        """
        if operation in BRIDGE_OPERATIONS:
            return f"bridge.{operation}"
        # IFL-routed: use as-is
        return operation

    def _parse_response(
        self,
        request: CapabilityRequest,
        response: Any,
        trace_id: str,
        start: float,
    ) -> CapabilityResult:
        """Convert bridge response (BridgeResponse or BridgeCommandResult) to CapabilityResult."""
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if not response.success:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="bridge_operation_error",
                error_message=response.error_message or "Bridge operation failed",
                retriable=True,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
                execution_time_ms=response.latency_ms,
            )

        return CapabilityResult.success_result(
            request_id=request.request_id,
            data=response.data if response.data else {"result": None},
            provider_id=self.provider_id,
            trace_id=trace_id,
            duration_ms=elapsed_ms,
            execution_time_ms=response.latency_ms,
        )

    def __repr__(self) -> str:
        return (
            f"BridgeProvider("
            f"provider_id={self.provider_id!r}, "
            f"capabilities={len(self._capability_names)}, "
            f"bridge_available={self._bridge.is_available()})"
        )
