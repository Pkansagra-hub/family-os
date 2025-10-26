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

# ==============================================================================
# Observability Instrumentation (ADR-0029, ADR-0029c)
# ==============================================================================

from k1.l5_infrastructure.observability.metrics import record_sse_event


def _record_sse_event_sent(event_type: str, session_id: str, size_bytes: int):
    """
    Record SSE event emission metrics.

    Args:
        event_type: Event type (17 types from ADR-0016d taxonomy)
            - agent.lifecycle.* (hired, warming, active, idle, draining, terminated, crashed)
            - turn.execution.* (started, input_received, thinking, completed)
            - tool.execution.* (started, completed, failed)
            - session.* (created, restored, checkpointed, evicted, terminated)
            - system.* (health_check, thermal_warning)
        session_id: Session UUID
        size_bytes: Serialized event size (FlatBuffers→JSON)

    Metrics:
        - sse_events_sent_total: Counter (event_type label)

    ADR References:
        - ADR-0029c: Component Metrics (sse_events_sent_total)
        - ADR-0016d: SSE Event Taxonomy (17 event types)
        - ADR-0042a: K0 SSE Streaming (FlatBuffers serialization)

    Usage:
        ```python
        event = serialize_agent_lifecycle_event(agent_id, "active")
        await send_sse_event(session_id, event)
        _record_sse_event_sent("agent.lifecycle.active", session_id, len(event))
        ```
    """
    # Topic is session-specific, derive from event_type
    topic = f"k1.sse.{event_type.replace('.', '_')}"
    record_sse_event(event_type=event_type, topic=topic)


def _record_sse_backpressure(queue_size: int, session_id: str):
    """
    Record SSE event queue backpressure (gauge metric).

    Args:
        queue_size: Current event queue size (number of pending events)
        session_id: Session UUID

    Metrics:
        - sse_event_queue_size: Gauge (tracks backpressure)

    ADR References:
        - ADR-0029c: Component Metrics
        - ADR-0024: Performance Budgets (queue size <100 events)

    Usage:
        ```python
        queue_size = len(event_queue)
        if queue_size > 50:
            _record_sse_backpressure(queue_size, session_id)
        ```

    Alert: sse_event_queue_size > 100 (backpressure, slow client)
    """
    # NOTE: sse_event_queue_size gauge not yet in K1MetricsCollector
    # TODO: Add to SSEMetrics dataclass when implementing event queue
    pass  # Placeholder for future gauge implementation


__all__ = ["_record_sse_event_sent", "_record_sse_backpressure"]
