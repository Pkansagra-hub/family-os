"""P03 Trace Context Propagation — Issue 6.1.11.

This module implements trace context propagation using OpenTelemetry baggage
for cross-service correlation in P03 consolidation pipeline.

Issue Reference: M6_EXECUTION.md Issue 6.1.11
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.3.2

Key Features:
    - Attach P03 baggage items (cycle_id, tenant_id, space_id) at cycle start
    - Inject trace context into outbound event payloads
    - Extract trace context from incoming events for downstream correlation
    - Integration with K0's TracerFactory for cognitive_trace_id

Usage:
    from k0.pipelines.p03.ops.context_propagation import P03TraceContextPropagator

    propagator = P03TraceContextPropagator()

    # At cycle start
    token = propagator.attach_p03_baggage(
        cycle_id="01HXYZ...",
        tenant_id="tenant_123",
        space_id="space_456",
        correlation_id="corr_789",
    )

    try:
        # ... run cycle ...
        # Inject into outbound events
        event_payload = propagator.inject_into_event(event_payload)
    finally:
        propagator.detach(token)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, MutableMapping

from opentelemetry import baggage, context, propagate, trace

if TYPE_CHECKING:
    from opentelemetry.context import Context

__all__ = [
    "P03TraceContextPropagator",
    "P03BaggageKeys",
    "P03ContextSnapshot",
]

LOGGER = logging.getLogger(__name__)


class P03BaggageKeys:
    """Baggage keys for P03 trace context propagation."""

    # Required baggage items (always propagated)
    CYCLE_ID = "p03_cycle_id"
    TENANT_ID = "p03_tenant_id"
    SPACE_ID = "p03_space_id"
    CORRELATION_ID = "correlation_id"

    # Optional baggage items
    SOURCE_EVENT_IDS = "p03_source_event_ids"
    TRIGGERED_BY = "p03_triggered_by"
    PARENT_CYCLE_ID = "p03_parent_cycle_id"

    @classmethod
    def required_keys(cls) -> tuple[str, ...]:
        """Return required baggage keys."""
        return (cls.CYCLE_ID, cls.TENANT_ID, cls.SPACE_ID, cls.CORRELATION_ID)

    @classmethod
    def all_keys(cls) -> tuple[str, ...]:
        """Return all P03 baggage keys."""
        return (
            cls.CYCLE_ID,
            cls.TENANT_ID,
            cls.SPACE_ID,
            cls.CORRELATION_ID,
            cls.SOURCE_EVENT_IDS,
            cls.TRIGGERED_BY,
            cls.PARENT_CYCLE_ID,
        )


@dataclass(frozen=True, slots=True)
class P03ContextSnapshot:
    """Snapshot of P03 trace context for serialization."""

    cycle_id: str
    tenant_id: str
    space_id: str
    correlation_id: str | None
    trace_id: str | None
    span_id: str | None
    source_event_ids: str | None = None
    triggered_by: str | None = None
    parent_cycle_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event payload injection."""
        result: dict[str, Any] = {
            "cycle_id": self.cycle_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
        }
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.span_id:
            result["span_id"] = self.span_id
        if self.source_event_ids:
            result["source_event_ids"] = self.source_event_ids
        if self.triggered_by:
            result["triggered_by"] = self.triggered_by
        if self.parent_cycle_id:
            result["parent_cycle_id"] = self.parent_cycle_id
        return result


class P03TraceContextPropagator:
    """Propagate P03 trace context across service boundaries.

    This class wraps OpenTelemetry baggage propagation with P03-specific
    context items. It ensures cycle_id, tenant_id, and space_id are
    consistently propagated in all traces and events.

    Thread Safety:
        Context operations are thread-local via OpenTelemetry's Context API.

    Integration Points:
        - P03SequentialRunner.run(): attach baggage at cycle start
        - P03OutboxPublisher.publish(): inject context into events
        - Event handlers: extract context from incoming events
    """

    def attach_p03_baggage(
        self,
        cycle_id: str,
        tenant_id: str,
        space_id: str,
        correlation_id: str | None = None,
        source_event_ids: list[str] | None = None,
        triggered_by: str | None = None,
        parent_cycle_id: str | None = None,
    ) -> object:
        """Attach all P03 baggage items to current context.

        Args:
            cycle_id: P03 cycle identifier (ULID).
            tenant_id: Tenant isolation key.
            space_id: Space isolation key.
            correlation_id: Cross-service correlation ID (optional).
            source_event_ids: Source event IDs (optional, comma-separated in baggage).
            triggered_by: What triggered this cycle (optional).
            parent_cycle_id: Parent cycle ID if retry/continuation (optional).

        Returns:
            Context token to pass to detach() when scope ends.
        """
        ctx = context.get_current()

        # Required baggage items
        ctx = baggage.set_baggage(P03BaggageKeys.CYCLE_ID, cycle_id, ctx)
        ctx = baggage.set_baggage(P03BaggageKeys.TENANT_ID, tenant_id, ctx)
        ctx = baggage.set_baggage(P03BaggageKeys.SPACE_ID, space_id, ctx)

        if correlation_id:
            ctx = baggage.set_baggage(P03BaggageKeys.CORRELATION_ID, correlation_id, ctx)

        # Optional baggage items
        if source_event_ids:
            ctx = baggage.set_baggage(
                P03BaggageKeys.SOURCE_EVENT_IDS,
                ",".join(source_event_ids),
                ctx,
            )
        if triggered_by:
            ctx = baggage.set_baggage(P03BaggageKeys.TRIGGERED_BY, triggered_by, ctx)
        if parent_cycle_id:
            ctx = baggage.set_baggage(P03BaggageKeys.PARENT_CYCLE_ID, parent_cycle_id, ctx)

        token = context.attach(ctx)

        LOGGER.debug(
            "P03 baggage attached: cycle_id=%s tenant_id=%s space_id=%s",
            cycle_id,
            tenant_id,
            space_id,
        )

        return token

    @staticmethod
    def detach(token: object) -> None:
        """Detach previously attached context.

        Args:
            token: Token returned from attach_p03_baggage().
        """
        context.detach(token)  # type: ignore[arg-type]

    @staticmethod
    def get_current_baggage() -> P03ContextSnapshot:
        """Get current P03 baggage as a snapshot.

        Returns:
            P03ContextSnapshot with all baggage values.
        """
        cycle_id = baggage.get_baggage(P03BaggageKeys.CYCLE_ID) or ""
        tenant_id = baggage.get_baggage(P03BaggageKeys.TENANT_ID) or ""
        space_id = baggage.get_baggage(P03BaggageKeys.SPACE_ID) or ""
        correlation_id = baggage.get_baggage(P03BaggageKeys.CORRELATION_ID)

        # Get trace/span IDs from current span
        current_span = trace.get_current_span()
        span_ctx = current_span.get_span_context()
        trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else None
        span_id = format(span_ctx.span_id, "016x") if span_ctx.is_valid else None

        return P03ContextSnapshot(
            cycle_id=str(cycle_id),
            tenant_id=str(tenant_id),
            space_id=str(space_id),
            correlation_id=str(correlation_id) if correlation_id else None,
            trace_id=trace_id,
            span_id=span_id,
            source_event_ids=baggage.get_baggage(P03BaggageKeys.SOURCE_EVENT_IDS),
            triggered_by=baggage.get_baggage(P03BaggageKeys.TRIGGERED_BY),
            parent_cycle_id=baggage.get_baggage(P03BaggageKeys.PARENT_CYCLE_ID),
        )

    def inject_into_event(
        self,
        event_payload: dict[str, Any],
        include_span_context: bool = True,
    ) -> dict[str, Any]:
        """Inject trace context into bus event payload.

        Args:
            event_payload: Event payload to inject context into.
            include_span_context: Whether to include trace_id/span_id (default True).

        Returns:
            Event payload with trace context fields added.
        """
        snapshot = self.get_current_baggage()
        context_data = snapshot.to_dict()

        if not include_span_context:
            context_data.pop("trace_id", None)
            context_data.pop("span_id", None)

        event_payload.update(context_data)
        return event_payload

    def inject_into_headers(self, headers: MutableMapping[str, str]) -> None:
        """Inject trace context into HTTP headers.

        Uses OpenTelemetry W3C Trace Context propagator.

        Args:
            headers: Mutable mapping to inject headers into.
        """
        propagate.inject(headers)

    def extract_from_headers(self, headers: Mapping[str, str]) -> Context:
        """Extract trace context from HTTP headers.

        Args:
            headers: Headers containing trace context.

        Returns:
            Extracted OpenTelemetry context.
        """
        return propagate.extract(headers)

    def extract_from_event(self, event_payload: dict[str, Any]) -> object | None:
        """Extract and attach trace context from incoming event.

        Restores P03 baggage from event payload for downstream correlation.

        Args:
            event_payload: Event payload containing trace context fields.

        Returns:
            Context token if context was attached, None otherwise.
        """
        cycle_id = event_payload.get("cycle_id")
        tenant_id = event_payload.get("tenant_id")
        space_id = event_payload.get("space_id")

        if not (cycle_id and tenant_id and space_id):
            LOGGER.debug("Event missing required P03 context fields, skipping extraction")
            return None

        return self.attach_p03_baggage(
            cycle_id=str(cycle_id),
            tenant_id=str(tenant_id),
            space_id=str(space_id),
            correlation_id=event_payload.get("correlation_id"),
            triggered_by=event_payload.get("triggered_by"),
            parent_cycle_id=event_payload.get("parent_cycle_id"),
        )


# Module-level singleton for convenience
_propagator: P03TraceContextPropagator | None = None


def get_propagator() -> P03TraceContextPropagator:
    """Get or create the module-level propagator singleton."""
    global _propagator
    if _propagator is None:
        _propagator = P03TraceContextPropagator()
    return _propagator
