"""Typed boundary objects for the Connector Gateway / IFL surface (MS-5).

These dataclasses live at the gateway boundary so the gateway, MCP process
manager, credential vault, and adapter verifier all speak the same vocabulary.

Wire/serialisation:
    These objects are *internal* to the bridge runtime; they are never
    serialised onto the wire. The wire envelopes for IFL invocations are
    JSON dicts shaped per the per-topic JSON Schema (e.g.
    ``ifl.google_calendar.events.list.v1.request.json``).

Stability:
    Field additions are additive only; any rename is a breaking change
    that requires bumping the gateway port version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Caller / result / descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConnectorCaller:
    """Identity of the K1-side caller invoking an IFL adapter.

    Attributes:
        session_id: K1 conversation/session id (used for audit + dedupe).
        tenant_id: Tenant identifier for multi-tenant routing.
        space_id: Privacy-band space (e.g. ``personal``, ``family``).
        user_band: Caller's effective privacy band.
        capability_token: Opaque token issued by the K1 fabric; the
            ``TokenVerifier`` stage validates it. The token contract is
            deliberately opaque at this layer (any K1 fabric can issue
            its own; verifier looks it up via the manifest's
            ``capability_required`` hint when present).
        trace_id: Distributed trace correlation id.
    """

    session_id: str
    tenant_id: str
    space_id: str = "personal"
    user_band: str = "GREEN"
    capability_token: str = ""
    trace_id: str = ""


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    """Result of a single IFL adapter invocation.

    Attributes:
        success: True iff the call completed without error.
        data: JSON-serialisable response payload from the adapter.
        error_code: Machine-readable code (empty on success).
        error_message: Human-readable message (empty on success).
        adapter_id: Adapter that handled the call.
        tool: Tool/action invoked.
        latency_ms: Round-trip latency, including pipeline overhead.
        attempt_count: How many tries the router used (1 for v1; reserved
            for retry policy work in v1.1).
    """

    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    adapter_id: str = ""
    tool: str = ""
    latency_ms: int = 0
    attempt_count: int = 1


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """A single tool exposed by a registered adapter.

    Attributes:
        name: Tool name as the adapter reports it via MCP ``tools/list``.
        description: Free-form description from the adapter manifest.
        input_schema: JSON Schema dict describing accepted args.
        output_schema: JSON Schema dict describing the return shape;
            empty dict if the adapter does not advertise one.
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterHealth:
    """Snapshot of a registered adapter's health.

    Attributes:
        adapter_id: Adapter identifier.
        state: One of ``ready``, ``starting``, ``unhealthy``,
            ``quarantined``, ``stopped``, ``unknown``.
        last_ping_ms: Epoch-ms of the last successful MCP ping; 0 if
            never pinged.
        consecutive_failures: How many consecutive ping failures preceded
            this snapshot.
        crash_count_window: Crashes in the active crash-budget window
            (default 60s — managed by ``CrashBudget``).
        message: Human-readable detail (empty when state==ready).
    """

    adapter_id: str
    state: str = "unknown"
    last_ping_ms: int = 0
    consecutive_failures: int = 0
    crash_count_window: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConnectorGatewayError(Exception):
    """Base for all gateway-layer errors. Subclasses are catchable
    individually so K1 callers can react granularly."""


class OfflineAdapterError(ConnectorGatewayError):
    """Raised when an adapter is registered but not currently reachable
    (e.g. MCP child crashed and is restarting)."""


class AdapterQuarantinedError(ConnectorGatewayError):
    """Raised when an adapter has exceeded its crash budget. Cleared
    only by manual operator intervention via
    ``python -m bridge.connector.unquarantine <adapter_id>``."""


class InvalidAdapterSignatureError(ConnectorGatewayError):
    """Raised at boot/registration time when an adapter manifest fails
    Ed25519 signature verification against ``ca_bundle.json``. The
    gateway refuses to register such adapters."""


class TokenDeniedError(ConnectorGatewayError):
    """Raised by ``TokenVerifier`` when the caller's capability token is
    missing, malformed, or insufficient for the requested manifest."""


class UnknownAdapterError(ConnectorGatewayError):
    """Raised when ``invoke``/``list_tools``/``health`` is called for an
    adapter id the gateway does not know about."""


__all__ = [
    "AdapterHealth",
    "AdapterQuarantinedError",
    "ConnectorCaller",
    "ConnectorGatewayError",
    "ConnectorResult",
    "InvalidAdapterSignatureError",
    "OfflineAdapterError",
    "TokenDeniedError",
    "ToolDescriptor",
    "UnknownAdapterError",
]
