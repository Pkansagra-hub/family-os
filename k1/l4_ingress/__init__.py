"""
K1 L4 Ingress — API Gateway, WebSocket, SSE, Voice Pipeline

**Purpose:** External ingress layer for REST API, WebSocket, SSE, and Voice pipelines

**Components:**
- api_gateway/ — REST API (JSON/FlatBuffers dual format, JWT auth, pagination)
- websocket/ — WebSocket binary protocol (FlatBuffers, flow control, reconnection)
- sse_gateway/ — SSE event streaming (17 event types, topic filtering)
- voice_pipeline/ — Voice pipeline (ASR→Intent→Tools→TTS→Audio, backpressure, barge-in)

**Performance:**
- REST endpoint: <100ms P95
- WebSocket latency: <20ms P95
- SSE event delivery: <10ms
- Voice E2E turn: <500ms P95

**ADRs:** 80+ ADRs across API Gateway (13), WebSocket (11), SSE (9), Voice Pipeline (10), and cross-cutting concerns

**Integration:**
- L4 Runtime: SessionState, Actor Fabric, Protocol Monitor
- L3 Execution: Agent routing, tool execution
- K0 Memory: WAL integration, event streaming

**Last Updated:** October 2025
**Status:** Production-ready ingress infrastructure
"""

__version__ = "0.1.0"
