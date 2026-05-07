"""IConnectorGatewayPort — bidirectional external traffic via IFL.

Security gateway for ALL external traffic: devices, APIs, services,
sensors.  Routes through IFL Universal Connector Protocol.

This port is NOT on the critical path for MS-7 kernel bootstrap.
It raises ``NotImplementedError`` in the SinkBridgeClient until
MS-3 (IFL) is built.

MS-5 (this revision):
    Added ``invoke``/``list_tools``/``health`` methods per the IFL
    minimum plan. The legacy ``execute``/``list_adapters`` methods are
    kept for backward compatibility (they remain part of the Protocol)
    and the default ``ConnectorGateway`` impl provides
    ``execute()`` as a thin alias over ``invoke()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    # The MS-5 typed boundary objects live in bridge.connector.contracts
    # so the connector tier owns its surface. We import them only under
    # TYPE_CHECKING to avoid a circular import:
    # bridge.connector.__init__ imports the concrete ``ConnectorGateway``,
    # which in turn imports this module.
    from bridge.connector.contracts import (
        AdapterHealth,
        ConnectorCaller,
    )
    from bridge.connector.contracts import ConnectorResult as ConnectorInvokeResult
    from bridge.connector.contracts import (
        ToolDescriptor,
    )

# ---------------------------------------------------------------------------
# Supporting types (legacy — pre-MS-5)
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
    """Result from an IFL connector execution (legacy shape).

    MS-5 callers should use :class:`bridge.connector.contracts.ConnectorResult`
    instead — it is the canonical shape used by ``invoke()``. This shape
    is preserved for the deprecated ``execute()`` method.

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

    The MS-5 contract surface is ``invoke``/``list_tools``/``health``.
    The legacy ``execute``/``list_adapters`` methods are kept for
    backward compatibility with pre-MS-5 callers (they delegate to the
    new methods in the default impl).

    This Protocol's primary impl is :class:`bridge.connector.gateway.ConnectorGateway`.
    The :class:`bridge.client.SinkBridgeClient` raises
    ``NotImplementedError`` for all methods (offline mode).
    """

    # -- MS-5 canonical surface --------------------------------------------

    async def invoke(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
        caller: ConnectorCaller,
    ) -> ConnectorInvokeResult:
        """Invoke a tool on a registered IFL adapter.

        Routes through the 3-stage gateway pipeline:
        ``TokenVerifier`` → ``AdapterVerifier`` → ``RequestRouter``.

        Args:
            adapter_id: Target adapter (e.g. ``"google_calendar_father"``).
            tool: Tool name as advertised by the adapter manifest.
            args: JSON-serialisable arguments per the tool's input schema.
            caller: K1-side caller identity (carries trace_id, capability
                token, and band).

        Returns:
            :class:`bridge.connector.contracts.ConnectorResult`.

        Raises:
            UnknownAdapterError: ``adapter_id`` not registered.
            TokenDeniedError: token verification failed.
            InvalidAdapterSignatureError: adapter manifest signature
                invalid (raised at registration time but re-checked here
                if the gateway runs in defensive mode).
            AdapterQuarantinedError: adapter exceeded crash budget.
            OfflineAdapterError: adapter healthy registry-side but child
                process not currently reachable.
        """
        ...  # pragma: no cover

    async def list_tools(self, *, adapter_id: str) -> list[ToolDescriptor]:
        """List the tools an adapter exposes.

        Args:
            adapter_id: Adapter to query.

        Returns:
            List of :class:`ToolDescriptor`. Empty list if adapter is
            registered but currently offline; raises
            :class:`UnknownAdapterError` if adapter is unknown.
        """
        ...  # pragma: no cover

    async def health(self, *, adapter_id: str) -> AdapterHealth:
        """Return a health snapshot for one adapter.

        Args:
            adapter_id: Adapter to query.

        Returns:
            :class:`AdapterHealth` describing the adapter's current state.
        """
        ...  # pragma: no cover

    # -- Legacy surface (kept for pre-MS-5 callers; deprecated) ------------

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

        Deprecated since MS-5: prefer :meth:`invoke`. This method is kept
        for offline/sink-client compatibility and may be removed in a
        future version.

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

        Deprecated since MS-5 in favour of per-adapter
        :meth:`health` calls; preserved for pre-MS-5 dashboard callers.

        Returns:
            List of AdapterStatus for all known adapters.
        """
        ...  # pragma: no cover
