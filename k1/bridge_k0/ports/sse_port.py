"""
SSE Port Adapter - K0 SSE Port (Server-Sent Events)

Layer: L5 Infrastructure
Component: K0 Bridge → SSE Port
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Dual Protocol (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0004a: Event Bus Architecture (SSE events → K1 event bus)
    - ADR-0014: JSON REST API Dual Format (content negotiation)

Dependencies:
    Internal:
        - k1.l5_infrastructure.event_bus (EventBus for internal event routing)
        - k1.bridge_k0.http2_client.HTTP2Connection (transport)
    External:
        - asyncio (async stream handling for SSE)

Connects To:
    Upstream:
        - K0 SSE Port: GET /k0/sse/stream (Server-Sent Events)
    Downstream:
        - k1.l5_infrastructure.event_bus (publish K0 events to K1 components)
        - k1.l2_orchestration.orchestrator (consolidation_complete events)

Performance Budgets:
    - Connection: <100ms (K1 → K0 SSE stream)
    - Event delivery: <10ms P95 (K0 SSE → K1 event bus)
    - Reconnection: <5s after disconnect

Observability:
    Metrics:
        - k1_k0_sse_port_events_received_total{event_type} (counter)
        - k1_k0_sse_port_connection_status{status} (gauge: connected/disconnected)
        - k1_k0_sse_port_reconnect_attempts_total (counter)
    Traces:
        - Span: k0_bridge.sse_port_receive
        - Attributes: event_type, session_id, cognitive_trace_id
    Logs:
        - INFO: event received (event_type, session_id)
        - WARNING: connection lost (reconnecting)
        - ERROR: reconnection failed (attempt, reason)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 SSE Port)
    - Test: tests/k1/bridge_k0/ports/test_sse_port.py
"""

import logging
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Callable, Dict, Optional

# Third-party imports
# None

# Internal imports
# from k1.l5_infrastructure.event_bus import EventBus, Event, EventTopic
# from k1.bridge_k0.http2_client import HTTP2Connection

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.2.3
DEFAULT_CONFIG = {
    "k0_host": "localhost",
    "k0_sse_port": 8080,
    "endpoint": "/k0/sse/stream",  # K0 SSE Port endpoint
    "reconnect_interval_s": 5,  # 5s reconnection interval
    "max_reconnect_attempts": 10,  # Max reconnection attempts before giving up
    "heartbeat_interval_s": 30,  # 30s heartbeat (keepalive)
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class SSEEventType(Enum):
    """SSE event types from K0"""

    CONSOLIDATION_COMPLETE = "consolidation_complete"  # K0 memory consolidation done
    HEALTH_ALERT = "health_alert"  # K0 health issue
    QUOTA_EXCEEDED = "quota_exceeded"  # K0 quota limit reached


@dataclass
class SSEEvent:
    """
    Server-Sent Event from K0.

    Fields:
        event: Event type (consolidation_complete, health_alert, quota_exceeded)
        session_id: Session ID (if event is session-specific)
        timestamp: Unix timestamp (milliseconds)
        data: Event payload (dict, event-specific)
    """

    event: SSEEventType
    session_id: Optional[str]
    timestamp: float
    data: Dict[str, Any]


class ConnectionStatus(Enum):
    """SSE connection status"""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class SSEPort:
    """
    Adapter for K0 SSE Port (Server-Sent Events).

    Purpose:
        Connects to K0 SSE stream, receives events (consolidation_complete,
        health_alert, quota_exceeded), publishes events to K1 internal event bus,
        handles reconnection logic (exponential backoff).

    Responsibilities:
        1. Connect to K0 SSE stream (GET /k0/sse/stream)
        2. Receive SSE events from K0 (streaming)
        3. Parse SSE event format (data: {...})
        4. Publish events to K1 internal event bus (ADR-0004a)
        5. Handle reconnection (exponential backoff, max 10 attempts)
        6. Heartbeat monitoring (30s interval)

    Lifecycle:
        INIT → CONNECTING → CONNECTED → [RECONNECTING] → TERMINATED

    Thread Safety: Yes (async-safe)
    Async Safe: Yes (fully async/await compatible)

    Cognitive Trace:
        - SSE events include cognitive_trace_id (if applicable)
        - Required for: event routing to K1 components

    Performance Budget (P95):
        - Connection: <100ms (K1 → K0 SSE stream)
        - Event delivery: <10ms (K0 SSE → K1 event bus)
        - Reconnection: <5s after disconnect

    Examples:
        >>> config = {'k0_host': 'localhost', 'k0_sse_port': 8080}
        >>> sse_port = SSEPort(config)
        >>>
        >>> # Subscribe to consolidation_complete events
        >>> async def on_consolidation_complete(event: SSEEvent):
        ...     print(f'Consolidation complete for session {event.session_id}')
        >>>
        >>> sse_port.subscribe(SSEEventType.CONSOLIDATION_COMPLETE, on_consolidation_complete)
        >>> await sse_port.initialize()
        >>> # SSE stream runs in background, delivering events to subscribers
        >>> await sse_port.shutdown()

    References:
        - ADR-0004a: Event Bus Architecture (K1 internal event routing)
        - ADR-0001a: K0 Bridge Dual Protocol
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize SSEPort adapter.

        Args:
            config: Configuration dict with K0 host, port, endpoints

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (subscribers, connection status)
            - Does NOT connect to K0 (call initialize() to connect)

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.3
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Validate config (check k0_host, k0_sse_port, endpoint)
        # 2. Initialize state machine (INIT → CONNECTING → CONNECTED)
        # 3. Initialize subscriber registry (event_type → handlers)
        # 4. Initialize reconnection logic (backoff, max attempts)
        self.config = config
        self.state = (
            "INIT"  # State: INIT | CONNECTING | CONNECTED | RECONNECTING | TERMINATED
        )
        self._logger = logger
        self._subscribers: Dict[SSEEventType, list] = {}
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._reconnect_attempts = 0
        pass

    async def initialize(self) -> None:
        """
        Async initialization phase - connect to K0 SSE stream.

        This method performs async setup (SSE connection, start event loop).

        Raises:
            RuntimeError: If initialization fails
            ConnectionError: If cannot connect to K0 SSE Port

        Lifecycle:
            Transitions: INIT → CONNECTING → CONNECTED

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.3
        """
        # TODO(@infrastructure-team): Implement async initialization (ADR-0001a)
        # 1. Connect to K0 SSE stream (GET /k0/sse/stream)
        # 2. Start event loop task (read SSE events)
        # 3. Start heartbeat task (30s interval)
        # 4. Transition state: INIT → CONNECTING → CONNECTED
        self.state = "CONNECTED"
        self._connection_status = ConnectionStatus.CONNECTED
        self._logger.info(
            "sse_port_initialized",
            k0_host=self.config.get("k0_host"),
            k0_port=self.config.get("k0_sse_port"),
        )
        pass

    def subscribe(
        self, event_type: SSEEventType, handler: Callable[[SSEEvent], None]
    ) -> None:
        """
        Subscribe to SSE event type.

        Args:
            event_type: SSE event type (consolidation_complete, health_alert, etc.)
            handler: Event handler (async or sync function)

        Side Effects:
            - Registers handler for event type
            - Handler called when event received

        Usage:
            async def on_consolidation(event: SSEEvent):
                print(f'Consolidation done: {event.session_id}')

            sse_port.subscribe(SSEEventType.CONSOLIDATION_COMPLETE, on_consolidation)

        ADR: ADR-0004a (Event Bus Architecture)
        Assigned to: Issue #L5-1.2.3
        """
        # TODO(@infrastructure-team): Implement subscribe (ADR-0004a)
        # 1. Add handler to subscriber registry (event_type → handlers)
        # 2. Support multiple subscribers per event type
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        pass

    async def _event_loop(self) -> None:
        """
        Background task: Read SSE events from K0 stream.

        This method runs continuously, reading SSE events and delivering to subscribers.

        Raises:
            ConnectionError: If SSE stream disconnects (triggers reconnection)

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.3
        """
        # TODO(@infrastructure-team): Implement event loop (ADR-0001a)
        # 1. Read SSE stream (GET /k0/sse/stream)
        # 2. Parse SSE event format:
        #    data: {"event": "consolidation_complete", "session_id": "sess_123", ...}
        # 3. Create SSEEvent object
        # 4. Deliver event to subscribers (handlers)
        # 5. If connection lost, trigger reconnection
        # 6. Record metrics (events received, latency)
        pass

    async def _reconnect(self) -> None:
        """
        Reconnection logic with exponential backoff.

        This method attempts reconnection up to max_reconnect_attempts.

        Raises:
            RuntimeError: If max reconnection attempts exceeded

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.3
        """
        # TODO(@infrastructure-team): Implement reconnection logic (ADR-0001a)
        # 1. Set state to RECONNECTING
        # 2. Exponential backoff: 1s, 2s, 4s, 8s, ... up to 60s
        # 3. Attempt reconnection (connect to K0 SSE stream)
        # 4. If successful, restart event loop
        # 5. If failed, increment reconnect_attempts
        # 6. If max_reconnect_attempts exceeded, set state to DISCONNECTED
        pass

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Stop event loop task
            - Stop heartbeat task
            - Close SSE connection

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.3
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0001a)
        # 1. Set state to TERMINATED
        # 2. Cancel event loop task
        # 3. Cancel heartbeat task
        # 4. Close SSE connection
        # 5. Clear subscribers
        # 6. Flush metrics (Prometheus)
        self.state = "TERMINATED"
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._logger.info("sse_port_shutdown_complete")
        pass


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def create_sse_port(config: Optional[Dict[str, Any]] = None) -> SSEPort:
    """
    Create SSEPort with default or provided configuration.

    Args:
        config: Configuration dict (default: localhost:8080)

    Returns:
        SSEPort instance

    ADR: ADR-0001a (K0 Bridge Dual Protocol)
    Assigned to: Issue #L5-1.2.3
    """
    if config is None:
        config = DEFAULT_CONFIG

    return SSEPort(config)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "SSEPort",
    "SSEEvent",
    "SSEEventType",
    "ConnectionStatus",
    "create_sse_port",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_sse_port_events_received_total{event_type} (counter)
#   - k1_k0_sse_port_connection_status{status} (gauge: 1=connected, 0=disconnected)
#   - k1_k0_sse_port_reconnect_attempts_total (counter)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.sse_port_receive
#   - Attributes: event_type, session_id, cognitive_trace_id
#   - Links to: downstream event bus spans
#
# Logs to emit (structured logging):
#   - Level: INFO (event received), WARNING (connection lost), ERROR (reconnection failed)
#   - Fields: component='sse_port', event_type, session_id, reconnect_attempt
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# SSE events include cognitive_trace_id (if applicable):
#   data: {
#       "event": "consolidation_complete",
#       "session_id": "sess_123",
#       "cognitive_trace_id": "trace_abc123",
#       ...
#   }
#
# Event handlers must:
#   1. Extract cognitive_trace_id from SSEEvent.data
#   2. Propagate trace_id to downstream components
#   3. Include trace_id in all log statements
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/ports/test_sse_port.py
#   - Test SSE connection (GET /k0/sse/stream)
#   - Test event reception (consolidation_complete, health_alert, quota_exceeded)
#   - Test subscriber delivery (event → handlers)
#   - Test reconnection logic (exponential backoff, max attempts)
#   - Test heartbeat monitoring (30s interval)
#
# No simulation code allowed:
#   - Use real K0 mock server with SSE endpoint
#   - Test event streaming (continuous, not one-shot)
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert connection <100ms
#   - Assert event delivery <10ms P95
#   - Assert reconnection <5s after disconnect
#
# =============================================================================
