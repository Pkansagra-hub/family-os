"""
K0 Bridge Module - K1→K0 Communication Layer

Purpose: Dual-protocol bridge for K1→K0 communication (Command, Query, SSE, Batch, Observability)
Performance: <50ms Command (GREEN), <200ms (AMBER/RED), <100ms Query, <5ms SSE delivery
Total Modules: 6 modules (command_client, query_client, sse_client, batch_client, observability_client, http2)

Primary ADRs:
- ADR-0001: K0 Integration (20 pipelines, 4 external ports)
- ADR-0001a: K0 Bridge Architecture (dual-protocol, lane processing, multi-store retrieval)
- ADR-0001f: SessionState Delta Batching (250ms batching, P02 MemoryWrite)
- ADR-0044: K0 Bridge HTTP/2 (transport layer, multiplexing, connection pooling)

Key Components:
1. command_client.py - K0 Command Port (write operations, idempotency, receipts)
2. query_client.py - K0 Query Port (multi-store retrieval, fusion, caching)
3. sse_client.py - K0 SSE Port (event streaming, reconnection, backpressure)
4. batch_client.py - SessionState Delta Batching (250ms interval, 3-trigger flush)
5. observability_client.py - K0 Observability Port (metrics/logs push)
6. http2/ - HTTP/2 transport layer (connection pooling, stream multiplexing)

K0 Ports:
- Command Port (:5200) - Write operations (MEMORY_WRITE, PLAN_COMMITTED, SAGA_LOG, STATE_DELTA)
- Query Port (:5201) - Read operations (RECALL, SEARCH, KG_NEIGHBORS, KG_PATHS)
- SSE Port (:5202) - Event streaming (MEMORY_WRITTEN, CONSOLIDATION_COMPLETE, SYNC_STATUS)
- Observability Port (:5203) - Metrics/logs push (Prometheus, structured logs)

Dual Protocol:
- JSON (PRIMARY): K0 native format, human-readable
- FlatBuffers (SECONDARY): K1 optimization, zero-copy, <1ms serialization

Lane Processing:
- Fast Lane (GREEN): <50ms P95, 70% of writes, no safety review
- Smart Lane (AMBER/RED): <200ms P95, 30% of writes, arbiter approval

Research Foundations:
- HTTP/2 (RFC 7540): Binary framing, stream multiplexing, header compression
- SSE (W3C): Server-Sent Events, cursor-based resume, at-least-once delivery
- FlatBuffers (Google): Zero-copy serialization, backward compatibility

Last Updated: January 2025
ADR References: docs/architecture/decisions/0001-*.md, 0001a-*.md, 0001f-*.md, 0044-*.md
"""

# __version__ = "0.1.0"
# __all__ = [
#     "CommandClient",
#     "QueryClient",
#     "SSEClient",
#     "BatchClient",
#     "ObservabilityClient",
# ]
