"""IConnectorGatewayPort — bidirectional external traffic via IFL.

Security gateway for ALL external traffic: devices, APIs, services,
sensors.  Routes through IFL Universal Connector Protocol.

This port is NOT on the critical path for MS-7 kernel bootstrap.
It raises ``NotImplementedError`` in the SinkBridgeClient until
MS-3 (IFL) is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdapterStatus:
    """Health and registration status of an IFL adapter.

    Attributes:
        adapter_id: Unique adapter identifier (e.g. ``"com.philips.hue"``).
        category: Adapter category (home, health, finance, etc.).
        connected: Whether the adapter is currently connected.
        healthy: Whether the adapter's last health check passed.
        last_heartbeat_ms: Epoch ms of last health check.
        capabilities: List of registered capability names.
    """

    adapter_id: str
    category: str = ""
    connected: bool = False
    healthy: bool = False
    last_heartbeat_ms: int = 0
    capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    """Result from an IFL connector execution.

    Attributes:
        success: Whether the execution succeeded.
        data: Response payload from the external service.
        error_code: Machine-readable error code (empty on success).
        error_message: Human-readable error message (empty on success).
        adapter_id: Which adapter handled this request.
        latency_ms: Round-trip latency in ms.
    """

    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    adapter_id: str = ""
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IConnectorGatewayPort(Protocol):
    """Security gateway for all external traffic via IFL.

    Routes capability invocations through the IFL adapter registry,
    enforcing authentication, rate limiting, and circuit breaking
    per adapter.

    This port is intentionally unimplemented until MS-3 (IFL).
    The SinkBridgeClient raises ``NotImplementedError`` for all methods.
    """

    async def execute(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> ConnectorResult:
        """Execute a capability action through an IFL adapter.

        Args:
            adapter_id: Target adapter (e.g. ``"com.philips.hue"``).
            action: Action name within the adapter.
            params: Action parameters.
            trace_id: Cognitive trace ID.
            timeout_ms: Per-request timeout (0 = adapter default).

        Returns:
            ConnectorResult with response data or error.
        """
        ...  # pragma: no cover

    async def list_adapters(self) -> list[AdapterStatus]:
        """List all registered IFL adapters and their status.

        Returns:
            List of AdapterStatus for all known adapters.
        """
        ...  # pragma: no cover
