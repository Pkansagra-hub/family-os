"""
K0 Bridge Port Adapters

Layer: L5 Infrastructure
Component: K0 Bridge (K1 ↔ K0 Communication)
Priority: P0 (Critical Path)

This package contains adapters for K0's 4 external ports:
    - command_port: K0 Command Port (P02 MemoryWrite) - SessionState delta writes
    - query_port: K0 Query Port (P01 RecallQuery) - Multi-store retrieval
    - sse_port: K0 SSE Port - Server-Sent Events for K0 → K1 notifications
    - observability_port: K0 Observability Port - Prometheus metrics export

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Dual Protocol (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0001f: K0-K1 Pipeline Boundary (K1 NEVER implements pipelines)
    - ADR-0014: JSON REST API Dual Format (content negotiation)
    - ADR-0004a: Event Bus Architecture (SSE events)
    - ADR-0002d: Observability Schema (metrics)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Bridge 4 Ports)
"""

__all__ = [
    "CommandPort",
    "QueryPort",
    "SSEPort",
    "ObservabilityPort",
]
