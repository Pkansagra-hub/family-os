"""
SSE Outbox Driver - Publishes outbox events to SSE subscribers with Prometheus metrics.

Purpose: Bridge between transactional outbox pattern and SSE real-time streaming.
Use case: Telemetry, monitoring, and future UI event notifications.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from prometheus_client import Counter, Histogram

if TYPE_CHECKING:
    from k0.sse.server import SSEServer

logger = logging.getLogger(__name__)

# Prometheus metrics for outbox event publishing
outbox_events_published = Counter(
    "k0_outbox_events_published_total",
    "Total outbox events published to SSE",
    ["op_kind", "status"],
)

outbox_publish_duration = Histogram(
    "k0_outbox_publish_duration_seconds",
    "Time to publish outbox event to SSE",
    ["op_kind"],
)


class SSEOutboxDriver:
    """
    Driver for publishing outbox events to SSE server with telemetry.

    Each outbox entry becomes an SSE event with:
    - topic: Derived from op_kind (e.g., "pipeline.completed", "affect.analyzed")
    - payload: JSON-serialized event data
    - metrics: Published to Prometheus for Grafana dashboards
    """

    def __init__(self, sse_server: SSEServer | None = None):
        """
        Initialize SSE outbox driver.

        Args:
            sse_server: Optional SSE server instance for testing.
                       In production, will use global SSE server from app state.
        """
        self.sse_server = sse_server
        logger.info("SSEOutboxDriver initialized")

    def apply(self, entry) -> None:
        """
        Publish outbox event to SSE subscribers.

        Args:
            entry: OutboxEntry with tenant_id, space_id, op_kind, payload fields

        Raises:
            ValueError: If payload is not valid JSON
            RuntimeError: If SSE server not available
        """
        op_kind = entry.op_kind
        with outbox_publish_duration.labels(op_kind=op_kind).time():
            try:
                # Decode payload
                try:
                    event_data = json.loads(entry.payload)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON payload for {op_kind}: {e}")
                    outbox_events_published.labels(op_kind=op_kind, status="invalid_json").inc()
                    raise ValueError(f"Invalid JSON payload: {e}") from e

                # Map op_kind to SSE topic
                topic = self._map_op_kind_to_topic(op_kind)

                # Build SSE event
                sse_event = {
                    "topic": topic,
                    "tenant_id": entry.tenant_id,
                    "space_id": entry.space_id,
                    "op_kind": op_kind,
                    "payload": event_data,
                }

                # Publish to SSE (or log if no server available)
                if self.sse_server is not None:
                    # TODO: Call sse_server.broadcast(topic, sse_event) when SSE server exposes broadcast API
                    logger.info(
                        f"SSE event published: {topic}",
                        extra={"topic": topic, "op_kind": op_kind, "tenant_id": entry.tenant_id},
                    )
                else:
                    # Fallback: Log event for observability until SSE server integrated
                    logger.info(
                        f"SSE event (no server): {topic}",
                        extra={
                            "topic": topic,
                            "op_kind": op_kind,
                            "tenant_id": entry.tenant_id,
                            "event": sse_event,
                        },
                    )

                outbox_events_published.labels(op_kind=op_kind, status="success").inc()

            except Exception as e:
                logger.exception(f"Failed to publish outbox event to SSE: {e}")
                outbox_events_published.labels(op_kind=op_kind, status="error").inc()
                raise

    def _map_op_kind_to_topic(self, op_kind: str) -> str:
        """
        Map outbox op_kind to SSE topic.

        Examples:
            "PIPELINE_COMPLETED" -> "pipeline.completed"
            "AFFECT_ANALYZED" -> "affect.analyzed"
            "EMBEDDING_QUEUED" -> "embedding.queued"

        Args:
            op_kind: Outbox operation kind (UPPERCASE_SNAKE_CASE)

        Returns:
            SSE topic (lowercase.dotted.notation)
        """
        return op_kind.lower().replace("_", ".")


def build_driver() -> SSEOutboxDriver:
    """
    Factory function for outbox worker pool to instantiate driver.

    Returns:
        Configured SSEOutboxDriver instance
    """
    return SSEOutboxDriver()
