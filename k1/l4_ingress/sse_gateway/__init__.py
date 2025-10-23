"""
K1 L4 Ingress — SSE Gateway

**Purpose:** Server-Sent Events with 17 event types, topic filtering, FlatBuffers→JSON serialization

**Components:**
- event_taxonomy/ — 17 event types (agent lifecycle, turn, tool, session, system)
- serialization/ — FlatBuffers→JSON <2ms P95
- filtering/ — Topic-based filtering, 60-70% bandwidth savings
- browser/ — EventSource integration, React hooks
- bridge/ — SSE→WebSocket bridge <20ms

**Performance:**
- Serialization: <2ms P95
- Event delivery: <10ms
- Bandwidth savings: 60-70% (filtering)

**ADRs (9 total):** ADR-0016 to 0016d (SSE Event Schemas), ADR-0042a, 0042d (K0 SSE Streaming),
ADR-0043c (Topic Taxonomy), ADR-0046 (SSE-WebSocket Bridge)

**Last Updated:** October 2025
"""

__version__ = "0.1.0"

# TODO: Implement event_taxonomy/, serialization/, filtering/, browser/, bridge/
