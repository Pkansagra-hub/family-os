"""
SSE Outbox Driver - Publishes outbox events to SSE subscribers with Prometheus metrics.

Purpose: Bridge between transactional outbox pattern and SSE real-time streaming.
Use case: Telemetry, monitoring, and future UI event notifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

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

# Global SSE server reference (set by app state during lifespan)
_sse_server: SSEServer | None = None


def set_sse_server(server: SSEServer | None) -> None:
    """
    Set the global SSE server reference.

    Called by app lifespan to wire the SSE server into the driver.

    Args:
        server: SSEServer instance or None to clear
    """
    global _sse_server
    _sse_server = server
    logger.info(
        "SSE server reference updated",
        extra={"has_server": server is not None},
    )


def get_sse_server() -> SSEServer | None:
    """Get the current SSE server reference."""
    return _sse_server


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
                       In production, uses global SSE server from app state.
        """
        self._sse_server = sse_server
        logger.info("SSEOutboxDriver initialized")

    @property
    def sse_server(self) -> SSEServer | None:
        """Get SSE server - prefer instance, fallback to global."""
        return self._sse_server or _sse_server

    def apply(self, entry: Any) -> None:
        """
        Publish outbox event to SSE subscribers.

        Args:
            entry: OutboxEntry with tenant_id, space_id, op_kind, payload fields

        Raises:
            ValueError: If payload is not valid JSON
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

                # Publish to SSE if server available
                server = self.sse_server
                if server is not None:
                    # Import here to avoid circular import at module load
                    from k0.sse.server import BroadcastEvent

                    broadcast_event = BroadcastEvent(
                        topic=topic,
                        tenant_id=entry.tenant_id,
                        space_id=entry.space_id,
                        op_kind=op_kind,
                        payload=event_data,
                    )

                    # Run broadcast in event loop
                    try:
                        loop = asyncio.get_running_loop()
                        # Schedule broadcast as a task
                        loop.create_task(self._broadcast_async(server, broadcast_event))
                    except RuntimeError:
                        # No running loop - run synchronously (for tests)
                        asyncio.run(server.broadcast(broadcast_event))

                    logger.info(
                        f"SSE event published: {topic}",
                        extra={
                            "topic": topic,
                            "op_kind": op_kind,
                            "tenant_id": entry.tenant_id,
                        },
                    )
                else:
                    # No server available - log at DEBUG level
                    logger.debug(
                        f"SSE event (no server): {topic}",
                        extra={
                            "topic": topic,
                            "op_kind": op_kind,
                            "tenant_id": entry.tenant_id,
                        },
                    )

                outbox_events_published.labels(op_kind=op_kind, status="success").inc()

            except Exception as e:
                logger.exception(f"Failed to publish outbox event to SSE: {e}")
                outbox_events_published.labels(op_kind=op_kind, status="error").inc()
                raise

    async def _broadcast_async(
        self,
        server: SSEServer,
        event: Any,
    ) -> None:
        """Async wrapper for broadcast with error handling."""
        try:
            await server.broadcast(event)
        except Exception as e:
            logger.exception(
                f"Failed to broadcast SSE event: {e}",
                extra={
                    "topic": event.topic,
                    "op_kind": event.op_kind,
                },
            )

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
