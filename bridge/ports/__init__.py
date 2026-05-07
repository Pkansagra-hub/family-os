"""Bridge Port Protocol ABCs — formal interfaces for the K1↔K0 ports.

E-2.1: Defines the canonical Protocol interfaces that K1 components depend on.
Each K1 component's local port (Fabric IFabricK0Port, Planner IPlannerWritePort,
Orchestrator IBridgeWritePort, MW IBridgeCommandPort) is an adapter over
one or more of these central bridge ports.

MS-3c: ``IKernelQueryPort`` and its hand-written ``QueryEnvelope`` /
``RecallBundle`` types were removed; recall is now reachable only
through the typed paired contract ``recall.request.v1`` /
``recall.response.v1`` exposed by
``BridgeRuntime.query.recall_request_v1.request(...)``.

MS-3d: ``IKernelSSEPort`` and its hand-written ``SSETraceEvent`` /
``SSEBackpressure`` / ``BackpressureLevel`` types were removed; SSE
subscription is now codegen-driven (one generated subscriber port per
K0→K1 SSE manifest under ``bridge/_generated/k1/ports/``), wired to
the real chunked SSE transport at
``bridge/core/transport/sse_client.py``.

Ports:
  IKernelCommandPort    — K1→K0 fire-and-forget writes
  IKernelObsPort        — K1→K0 telemetry + feedback
  IConnectorGatewayPort — bidirectional external traffic via IFL
"""

from .command_port_protocol import IKernelCommandPort
from .connector_gateway_protocol import IConnectorGatewayPort
from .obs_port_protocol import IKernelObsPort

__all__ = [
    # Command
    "IKernelCommandPort",
    # Observability
    "IKernelObsPort",
    # Connector Gateway
    "IConnectorGatewayPort",
]
