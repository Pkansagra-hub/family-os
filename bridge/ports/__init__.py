"""Bridge Port Protocol ABCs — formal interfaces for all 5 K1↔K0 ports.

E-2.1: Defines the canonical Protocol interfaces that K1 components depend on.
Each K1 component's local port (Fabric IBridgePort, Planner IBridgePort,
Orchestrator IBridgeWritePort, MW IBridgeCommandPort) is an adapter over
one or more of these central bridge ports.

Ports:
  IKernelCommandPort — K1→K0 fire-and-forget writes
  IKernelQueryPort   — K1→K0→K1 request/response recall
  IKernelSSEPort     — K0→K1 streaming events
  IKernelObsPort     — K1→K0 telemetry + feedback
  IConnectorGatewayPort — bidirectional external traffic via IFL
"""

from .command_port_protocol import IKernelCommandPort
from .connector_gateway_protocol import IConnectorGatewayPort
from .obs_port_protocol import IKernelObsPort
from .query_port_protocol import (
    IKernelQueryPort,
    QueryEnvelope,
    RecallBundle,
    RecallItem,
    RecallSelector,
)
from .sse_port_protocol import BackpressureLevel, IKernelSSEPort, SSEBackpressure, SSETraceEvent

__all__ = [
    # Command
    "IKernelCommandPort",
    # Query
    "IKernelQueryPort",
    "QueryEnvelope",
    "RecallBundle",
    "RecallItem",
    "RecallSelector",
    # SSE
    "IKernelSSEPort",
    "SSETraceEvent",
    "SSEBackpressure",
    "BackpressureLevel",
    # Observability
    "IKernelObsPort",
    # Connector Gateway
    "IConnectorGatewayPort",
]
