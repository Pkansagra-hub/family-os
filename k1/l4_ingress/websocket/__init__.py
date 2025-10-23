"""
K1 L4 Ingress — WebSocket Server

**Purpose:** WebSocket binary protocol with FlatBuffers, flow control, reconnection, streaming

**Components:**
- protocol/ — Binary FlatBuffers protocol, 17 message types
- flow_control/ — ACK protocol, backpressure, batch 5 messages
- reconnection/ — Resume protocol, exponential backoff
- streaming/ — Model inference streaming, TTFT <150ms
- message_queue/ — FIFO queue, 2s coalesce window, 5 msg/sec rate limit
- turn_boundary/ — Dual-signal detection (2s pause OR explicit submit)

**Performance:**
- Message latency: <20ms P95
- Serialization: <5ms
- Reconnection: <500ms

**ADRs (15 total):** ADR-0015 to 0015e (WebSocket Binary), ADR-0040 to 0040d (Realtime Chat),
ADR-0053 to 0053c (Message Queue), ADR-0054 to 0054c (Turn Boundary)

**Last Updated:** October 2025
"""

__version__ = "0.1.0"

# TODO: Implement protocol/, flow_control/, reconnection/, streaming/, message_queue/, turn_boundary/
