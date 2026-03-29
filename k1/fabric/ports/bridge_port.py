"""
k1.fabric.ports.bridge_port -- IBridgePort port (5.1.3).

K0 access for Fabric via the Cross-Kernel Bridge.

Design:
  - Gateway to K0 kernel services: memory, checkpoints, feedback.
  - IFL (Inter-Function-Language) routing for tool execution across
    address spaces (home.*, device.*).
  - Graceful offline handling: ``is_available()`` returns False when
    K0 is unreachable; all operations return fallback responses.
  - BridgeHealth: K0 health snapshot with mode classification.
  - BridgeCommandResult: standardized result from any bridge operation.
  - IFLRoute: routing descriptor for IFL-addressed tool execution.

Consumers:
  - BridgeProvider (3.3.4) -- exclusively uses this port for K0 access.

Production adapter: BridgeConnectionAdapter (5.2.8)
Test adapter: TestBridgeAdapter (5.2.4)

K0 operations:
  Memory:     memory.store, memory.recall, memory.delta
  Lifecycle:  checkpoint, feedback.signal
  Tools:      tool.execute.home.*, tool.execute.device.* (via IFL routing)

References:
  - bridge_architecture.mmd (IFL addressing, envelope format)
  - K0HealthMode enum (bridge_provider.py)
  - FAB-09 (trace_id on all operations)

Exports:
  IBridgePort
  BridgeHealth
  BridgeCommandResult
  IFLRoute
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeHealth:
    """
    K0 health snapshot as observed through the Bridge.

    Attributes:
        available: Whether K0 is reachable through the Bridge.
        mode: Health mode string -- one of:
            ``"K0_FULL"``     -- K0 fully operational
            ``"K0_DEGRADED"`` -- K0 reachable but degraded (slow/partial)
            ``"K0_OFFLINE"``  -- K0 unreachable, local-only operation
        last_heartbeat_ms: Epoch ms of last successful K0 heartbeat.
            0 if no heartbeat has been received.
        latency_ms: Last observed round-trip latency to K0 in ms.
            0 if unknown.
        error_message: Description of current issue, empty if healthy.
    """

    available: bool = False
    mode: str = "K0_OFFLINE"
    last_heartbeat_ms: int = 0
    latency_ms: int = 0
    error_message: str = ""

    def is_full(self) -> bool:
        """True when K0 is fully operational."""
        return self.available and self.mode == "K0_FULL"

    def is_degraded(self) -> bool:
        """True when K0 is reachable but degraded."""
        return self.available and self.mode == "K0_DEGRADED"

    def is_offline(self) -> bool:
        """True when K0 is unreachable."""
        return not self.available or self.mode == "K0_OFFLINE"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for event payloads and health reports."""
        return {
            "available": self.available,
            "mode": self.mode,
            "last_heartbeat_ms": self.last_heartbeat_ms,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class BridgeCommandResult:
    """
    Standardized result from a Bridge command to K0.

    Wraps success/failure with K0 health context.

    Attributes:
        success: Whether the command succeeded.
        data: Response payload from K0 (empty dict on failure).
        error_code: Machine-readable error code (empty on success).
        error_message: Human-readable error message (empty on success).
        k0_mode: K0 health mode at time of response.
        latency_ms: Round-trip latency for this command.
        trace_id: Trace ID echoed back for correlation.
    """

    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    k0_mode: str = "K0_FULL"
    latency_ms: int = 0
    trace_id: str = ""

    @staticmethod
    def ok(
        data: Optional[Dict[str, Any]] = None,
        *,
        latency_ms: int = 0,
        trace_id: str = "",
    ) -> BridgeCommandResult:
        """Create a successful result."""
        return BridgeCommandResult(
            success=True,
            data=data or {},
            latency_ms=latency_ms,
            trace_id=trace_id,
        )

    @staticmethod
    def fail(
        error_code: str,
        error_message: str,
        *,
        k0_mode: str = "K0_OFFLINE",
        trace_id: str = "",
    ) -> BridgeCommandResult:
        """Create a failure result."""
        return BridgeCommandResult(
            success=False,
            error_code=error_code,
            error_message=error_message,
            k0_mode=k0_mode,
            trace_id=trace_id,
        )


@dataclass(frozen=True)
class IFLRoute:
    """
    IFL (Inter-Function-Language) routing descriptor.

    Used for tool execution across K0/K1 address spaces.
    The Bridge routes IFL-addressed commands to the correct
    execution context (home.*, device.*).

    Attributes:
        address: IFL address string (e.g. ``"tool.execute.home.lights"``).
        namespace: Top-level namespace (``"home"``, ``"device"``).
        function_name: The function/tool name within the namespace.
        timeout_ms: Per-route timeout override (0 = use default).
    """

    address: str = ""
    namespace: str = ""
    function_name: str = ""
    timeout_ms: int = 0

    @staticmethod
    def parse(address: str, timeout_ms: int = 0) -> IFLRoute:
        """
        Parse an IFL address into a route descriptor.

        Address format: ``"tool.execute.<namespace>.<function>"``

        Args:
            address: Full IFL address string.
            timeout_ms: Optional timeout override.

        Returns:
            Parsed IFLRoute with namespace and function extracted.

        Raises:
            ValueError: If address does not match IFL format.
        """
        parts = address.split(".")
        if len(parts) < 4 or parts[0] != "tool" or parts[1] != "execute":
            raise ValueError(
                f"Invalid IFL address: {address!r}. "
                f"Expected format: tool.execute.<namespace>.<function>"
            )
        namespace = parts[2]
        function_name = ".".join(parts[3:])
        return IFLRoute(
            address=address,
            namespace=namespace,
            function_name=function_name,
            timeout_ms=timeout_ms,
        )


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IBridgePort(Protocol):
    """
    K0 access port via the Cross-Kernel Bridge.

    This is the canonical port interface (5.1.3).  Any object with
    matching method signatures satisfies this protocol (structural
    subtyping via ``typing.Protocol``).

    The Bridge provides:
      1. Memory operations (store, recall, delta)
      2. Lifecycle operations (checkpoint, feedback)
      3. IFL-routed tool execution (home.*, device.*)

    Offline handling:
      When K0 is unavailable, ``is_available()`` returns False.
      All command methods SHOULD return graceful fallback
      ``BridgeCommandResult.fail("k0_offline", ...)`` rather than
      raising exceptions.

    Thread safety:
      Implementations MUST support concurrent calls from multiple
      asyncio tasks.  Internal connection management handles
      serialization if needed.
    """

    async def send_command(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """
        Send a command through the Bridge to K0.

        Used for write operations: memory.store, memory.delta,
        checkpoint, feedback.signal.

        Args:
            operation: Operation type (e.g. ``"memory.store"``, ``"checkpoint"``).
            payload: Command payload data.
            trace_id: Trace ID for observability (FAB-09).
            timeout_ms: Per-command timeout (0 = use adapter default).

        Returns:
            BridgeCommandResult with data or error.
        """
        ...  # pragma: no cover

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """
        Query K0 for data via the Bridge.

        Used for read-only operations: memory.recall.

        Args:
            operation: Operation type (e.g. ``"memory.recall"``).
            selectors: Query selectors/filters.
            trace_id: Trace ID for observability.
            timeout_ms: Per-query timeout (0 = use adapter default).

        Returns:
            BridgeCommandResult with data or error.
        """
        ...  # pragma: no cover

    async def route_ifl(
        self,
        route: IFLRoute,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
    ) -> BridgeCommandResult:
        """
        Execute a tool via IFL (Inter-Function-Language) routing.

        Routes through the Bridge to the correct execution context
        based on the IFL address (home.*, device.*).

        Args:
            route: IFLRoute descriptor with parsed IFL address.
            payload: Tool execution payload.
            trace_id: Trace ID for observability.

        Returns:
            BridgeCommandResult with tool execution result or error.
        """
        ...  # pragma: no cover

    def is_available(self) -> bool:
        """
        Check if the Bridge connection to K0 is available.

        Returns:
            True if K0 is reachable through the Bridge,
            False if offline or disconnected.
        """
        ...  # pragma: no cover

    def get_health(self) -> BridgeHealth:
        """
        Return the current K0 health as observed through the Bridge.

        Used by BridgeProvider to decide execution strategy:
          - K0_FULL     -> normal bridge execution
          - K0_DEGRADED -> bridge execution with extended timeout
          - K0_OFFLINE  -> fallback to LOCAL COLD mode

        Returns:
            BridgeHealth snapshot with availability and mode.
        """
        ...  # pragma: no cover
