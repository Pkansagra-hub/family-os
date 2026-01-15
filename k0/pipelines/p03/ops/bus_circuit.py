"""Bus Dispatcher Circuit Breaker — Issue 6.2.7.

Specialized circuit breaker for internal event bus used in R8 event emission.

References:
- Dossier Section 13.6: Circuit Breaker (External Dependencies)
- M6_EXECUTION.md Issue 6.2.7
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, FrozenSet, Optional

from k0.pipelines.p03.ops.circuit_breaker import (
    BUS_DISPATCHER_CONFIG,
    P03CircuitBreaker,
    P03CircuitBreakerState,
)

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


class EventPriority(Enum):
    """Event priority for emission decisions."""

    CRITICAL = "CRITICAL"  # Must emit (consolidation complete, errors)
    NORMAL = "NORMAL"  # Should emit (standard events)
    LOW = "LOW"  # Can drop (health checks, diagnostics)


@dataclass
class EmissionResult:
    """Result of event emission attempt."""

    success: bool
    method: str  # "direct", "outbox", "dropped"
    event_id: str


class BusDispatcherCircuitBreaker:
    """Circuit breaker for internal event bus.

    Used by R8 phase for event emission.
    Provides fallback to outbox when bus unavailable.

    Fallback Strategy:
    - Bus Available: Immediate publish
    - Bus Unavailable + CRITICAL/NORMAL: Queue to outbox
    - Bus Unavailable + LOW: Drop (non-critical)

    Dossier Reference: Section 13.6
    """

    # Event types that can be dropped when bus unavailable
    DROPPABLE_EVENTS: FrozenSet[str] = frozenset(
        {
            "p03.health.idle.v1",
            "p03.health.heartbeat.v1",
            "p03.debug.trace.v1",
        }
    )

    # Event types that are critical (must not drop)
    CRITICAL_PREFIXES = ("p03.error.", "p03.cycle.complete.")
    CRITICAL_SUFFIXES = (".complete.v1", ".failed.v1")

    def __init__(
        self,
        bus_client,
        outbox_publisher,
        circuit: P03CircuitBreaker,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """Initialize bus dispatcher circuit breaker.

        Args:
            bus_client: Internal bus client for event publishing.
            outbox_publisher: Outbox publisher for fallback queuing.
            circuit: Underlying circuit breaker instance.
            metrics: Optional metrics exporter.
        """
        self._bus = bus_client
        self._outbox = outbox_publisher
        self._circuit = circuit
        self._metrics = metrics

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._circuit.state == P03CircuitBreakerState.OPEN

    @property
    def state(self) -> P03CircuitBreakerState:
        """Get current circuit state."""
        return self._circuit.state

    async def emit(
        self,
        event: dict,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> EmissionResult:
        """Emit event with circuit breaker protection.

        Args:
            event: Event dict to emit.
            connection: Optional database connection for outbox fallback.

        Returns:
            EmissionResult with success status and method used.
        """
        event_id = event.get("event_id", "unknown")
        event_type = event.get("event_type", "")
        priority = self._classify_event_priority(event_type)

        if not self._circuit.should_allow_request():
            return await self._handle_circuit_open(event, event_id, priority, connection=connection)

        try:
            await self._bus.publish(event)
            self._circuit.record_success()
            self._emit_metric("p03_bus_emit_success_total", 1.0)
            return EmissionResult(success=True, method="direct", event_id=event_id)

        except Exception as e:
            self._circuit.record_failure()
            self._emit_metric(
                "p03_bus_emit_failure_total",
                1.0,
                error_type=type(e).__name__,
            )
            return await self._handle_circuit_open(event, event_id, priority, connection=connection)

    async def _handle_circuit_open(
        self,
        event: dict,
        event_id: str,
        priority: EventPriority,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> EmissionResult:
        """Handle emission when circuit is open.

        Args:
            event: Event to handle.
            event_id: Event identifier.
            priority: Event priority classification.
            connection: Optional database connection.

        Returns:
            EmissionResult indicating outcome.
        """
        if priority == EventPriority.LOW:
            self._emit_metric("p03_bus_dropped_total", 1.0)
            return EmissionResult(success=False, method="dropped", event_id=event_id)

        await self._fallback_to_outbox(event, connection=connection)
        self._emit_metric("p03_bus_outbox_fallback_total", 1.0)
        return EmissionResult(success=True, method="outbox", event_id=event_id)

    async def _fallback_to_outbox(
        self,
        event: dict,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> None:
        """Queue event to outbox for later emission.

        Args:
            event: Event to queue.
            connection: Optional database connection.
        """
        await self._outbox.enqueue(
            event_type=event.get("event_type", "unknown"),
            payload=event,
            connection=connection,
        )

    def _classify_event_priority(self, event_type: str) -> EventPriority:
        """Classify event priority for drop decisions.

        Args:
            event_type: Event type string.

        Returns:
            EventPriority classification.
        """
        if event_type in self.DROPPABLE_EVENTS:
            return EventPriority.LOW

        if any(event_type.startswith(p) for p in self.CRITICAL_PREFIXES):
            return EventPriority.CRITICAL

        if any(event_type.endswith(s) for s in self.CRITICAL_SUFFIXES):
            return EventPriority.CRITICAL

        return EventPriority.NORMAL

    def reset(self) -> None:
        """Reset circuit breaker."""
        self._circuit.reset()

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics is not None:
            self._metrics.emit(name, value, **labels)


def create_bus_circuit_breaker(
    bus_client,
    outbox_publisher,
    metrics: Optional[MetricsExporter] = None,
) -> BusDispatcherCircuitBreaker:
    """Factory for bus dispatcher circuit breaker.

    Args:
        bus_client: Internal bus client.
        outbox_publisher: Outbox publisher for fallback.
        metrics: Optional metrics exporter.

    Returns:
        Configured BusDispatcherCircuitBreaker.
    """
    circuit = P03CircuitBreaker(
        name="bus_dispatcher",
        config=BUS_DISPATCHER_CONFIG,
        metrics=metrics,
    )
    return BusDispatcherCircuitBreaker(bus_client, outbox_publisher, circuit, metrics)
