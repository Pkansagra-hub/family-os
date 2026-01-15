"""
Internal Bus Driver - Publishes outbox events directly to the internal event bus.

Purpose: Bridge between transactional outbox pattern and internal pipeline triggering.
Use case: Trigger pipelines (like P08) from other pipeline outputs (like P02).
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# Global references (set during app startup)
_bus_dispatcher_ref = None
_bus_loop_ref: asyncio.AbstractEventLoop | None = None


def set_bus_dispatcher(dispatcher):
    """Set the global bus dispatcher reference (called during app startup)."""
    global _bus_dispatcher_ref, _bus_loop_ref
    _bus_dispatcher_ref = dispatcher
    try:
        _bus_loop_ref = asyncio.get_running_loop()
    except RuntimeError:
        _bus_loop_ref = None


class InternalBusDriver:
    """
    Driver for publishing outbox events to the internal event bus.

    Each outbox entry becomes an internal bus message that can trigger pipelines.
    Used for inter-pipeline communication (e.g., P02 → P08 via cognitive.vector.stored.v1).
    """

    def __init__(self):
        """Initialize internal bus driver."""
        logger.info("InternalBusDriver initialized")

    def apply(self, entry) -> None:
        """
        Publish outbox event to internal bus dispatcher.

        Args:
            entry: OutboxEntry with tenant_id, space_id, op_kind, payload fields

        Raises:
            ValueError: If payload is not valid JSON
            RuntimeError: If bus dispatcher not available
        """
        try:
            # Get bus dispatcher from global reference
            bus_dispatcher = _bus_dispatcher_ref
            if bus_dispatcher is None:
                logger.error(
                    "Bus dispatcher not available - cannot publish event",
                    extra={
                        "driver": entry.driver,
                        "op_kind": entry.op_kind,
                        "tenant_id": entry.tenant_id,
                    },
                )
                return

            # Decode payload
            try:
                payload_data = json.loads(entry.payload)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Invalid JSON payload for {entry.op_kind}: {e}",
                    extra={"driver": entry.driver, "op_kind": entry.op_kind},
                )
                raise ValueError(f"Invalid JSON payload: {e}") from e

            # Import BusMessage here to avoid circular imports
            from k0.bus.core import BusMessage

            # Map op_kind to bus topic
            topic = self._map_op_kind_to_topic(entry.op_kind)

            # Create bus message
            # Note: entry.payload is a string from SQL, BusMessage.payload expects bytes
            payload_bytes = (
                entry.payload if isinstance(entry.payload, bytes) else entry.payload.encode("utf-8")
            )
            bus_message = BusMessage(
                topic=topic,
                payload=payload_bytes,
                offset=0,  # Outbox entries don't have bus offsets
                trace_id=payload_data.get("event_id", "unknown"),
                space_id=entry.space_id,
            )

            # Publish to bus dispatcher (will trigger subscribed pipelines)
            # Note: dispatch() is async, so we need to run it in the event loop
            # Fire-and-forget to avoid blocking outbox worker (pipelines may take >30s)
            loop = _bus_loop_ref or asyncio.get_event_loop()
            if loop and bus_dispatcher:
                try:
                    # Schedule async dispatch but don't wait (fire-and-forget)
                    asyncio.run_coroutine_threadsafe(bus_dispatcher.dispatch([bus_message]), loop)
                    # Don't wait for result - let pipelines execute asynchronously
                    # Errors will be logged by pipeline runner
                    logger.info(
                        f"Published to internal bus: {topic}",
                        extra={
                            "topic": topic,
                            "op_kind": entry.op_kind,
                            "tenant_id": entry.tenant_id,
                            "trace_id": bus_message.trace_id,
                            "async_execution": True,
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to publish to internal bus: {e}",
                        extra={
                            "topic": topic,
                            "op_kind": entry.op_kind,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )
                    raise
            else:
                logger.error(
                    "Event loop not available - cannot publish to internal bus",
                    extra={"topic": topic, "op_kind": entry.op_kind},
                )
                raise RuntimeError("Event loop not available for internal bus")

        except Exception as e:
            logger.exception(f"Failed to publish outbox event to internal bus: {e}")
            raise

    def _map_op_kind_to_topic(self, op_kind: str) -> str:
        """
        Map outbox op_kind to internal bus topic.

        Examples:
            "VECTOR_STORED" -> "cognitive.vector.stored.v1"
            "EMBEDDING_QUEUED" -> "cognitive.embedding.queued.v1"
            "PATTERN_SEPARATED" -> "cognitive.pattern.separated.v1"

        Args:
            op_kind: Outbox operation kind (UPPERCASE_SNAKE_CASE)

        Returns:
            Internal bus topic (cognitive.*.v1 format)
        """
        # Convert VECTOR_STORED → vector.stored
        topic_suffix = op_kind.lower().replace("_", ".")

        # Add cognitive prefix and version
        return f"cognitive.{topic_suffix}.v1"


def build_driver() -> InternalBusDriver:
    """
    Factory function for outbox worker pool to instantiate driver.

    Returns:
        Configured InternalBusDriver instance
    """
    return InternalBusDriver()
