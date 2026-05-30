"""
k1.memory_writer.pipeline.turn_dispatcher -- Routes turn.completed.v1 events to pipeline.

Glue between the K1 Bus and MemoryWriterPipeline.

1. Subscribes to turn.completed.v1 via IEventSubscriptionPort
2. Deserializes raw event payloads into TurnCompletePayload
3. Deduplicates by turn_id (at-most-once guarantee)
4. Routes to MemoryWriterPipeline.process()
5. Backpressure: max 1 concurrent process() + 1 queued (newest wins)
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Optional

from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.pipeline.pipeline import MemoryWriterPipeline
from k1.memory_writer.ports.event_subscription_port import IEventSubscriptionPort
from k1.memory_writer.types import Subscription

log = logging.getLogger(__name__)


class TurnDispatcher:
    """Routes turn.completed.v1 events to MemoryWriterPipeline.

    Guarantees at-most-once processing per turn_id within a session.
    In-memory dedup set cleared on session end (stop).

    Backpressure: max 1 concurrent process() call + 1 queued.
    If a third turn arrives while processing, the queued turn is
    replaced (newest wins — older context is stale anyway).
    """

    TOPIC = "k1.session.turn.completed.v1"  # fixed: was missing 'd' (MW-01-A)
    MAX_QUEUE_DEPTH = 2  # processing + 1 queued

    def __init__(
        self,
        pipeline: MemoryWriterPipeline,
        event_port: IEventSubscriptionPort,
    ) -> None:
        self._pipeline = pipeline
        self._event_port = event_port
        self._subscription: Optional[Subscription] = None
        self._processed_ids: deque[str] = deque(maxlen=200)  # bounded: MW-02-A
        self._processing: bool = False
        self._queued_payload: Optional[TurnCompletePayload] = None

    async def start(self) -> None:
        """Subscribe to turn.complete.v1 on the K1 Bus."""
        self._subscription = await self._event_port.subscribe(self.TOPIC, self._on_turn_complete)
        log.info("MW: TurnDispatcher started, topic=%s", self.TOPIC)

    async def stop(self) -> None:
        """Unsubscribe + flush pending + clear dedup set."""
        if self._subscription:
            await self._event_port.unsubscribe(self._subscription.subscription_id)
            self._subscription = None

        # Flush any pending pipeline work
        await self._pipeline.flush_pending()

        self._processed_ids.clear()
        self._queued_payload = None
        log.info("MW: TurnDispatcher stopped")

    async def _on_turn_complete(self, raw_payload: dict) -> None:
        """Event handler called by K1 Bus on turn.complete.v1.

        Deserializes, deduplicates, and routes to pipeline.
        """
        try:
            payload = self._deserialize(raw_payload)
        except Exception as exc:
            log.warning("MW: failed to deserialize turn event, error=%s", str(exc))
            return

        # At-most-once dedup
        if payload.turn_id in self._processed_ids:
            log.info("MW: duplicate turn_id, skipping, turn_id=%s", payload.turn_id)
            return

        # Backpressure: if already processing, queue (replace if full)
        if self._processing:
            # Do not overwrite a queued correction/contradiction with a routine turn (MW-06)
            existing = self._queued_payload
            if existing is not None and (
                getattr(existing, "correction_signal", False)
                or getattr(existing, "contradiction_signal", False)
            ):
                log.info(
                    "MW: skipping overwrite of queued correction/contradiction turn, "
                    "keeping turn_id=%s",
                    existing.turn_id,
                )
                return
            self._queued_payload = payload  # newest wins (non-correction)
            log.info(
                "MW: turn queued (processing in progress), turn_id=%s",
                payload.turn_id,
            )
            return

        await self._process_turn(payload)

        # Process queued turn if one arrived during processing
        if self._queued_payload:
            queued = self._queued_payload
            self._queued_payload = None
            if queued.turn_id not in self._processed_ids:
                await self._process_turn(queued)

    async def _process_turn(self, payload: TurnCompletePayload) -> None:
        """Process a turn through the pipeline with dedup tracking."""
        self._processing = True
        try:
            self._processed_ids.append(payload.turn_id)
            result = await self._pipeline.process(payload)
            log.info(
                "MW: turn processed, turn_id=%s, trace_id=%s, skipped=%s, atoms=%d, submitted=%d",
                payload.turn_id,
                result.trace_id,
                result.skipped,
                result.atoms_extracted,
                result.envelopes_submitted,
            )
        except Exception as exc:
            # Pipeline should never raise, but safety net
            log.error(
                "MW: pipeline process error, turn_id=%s, error=%s",
                payload.turn_id,
                str(exc),
            )
        finally:
            self._processing = False

    @staticmethod
    def _deserialize(raw: dict) -> TurnCompletePayload:
        """Convert raw K1 Bus event dict → TurnCompletePayload.

        Maps event fields to the typed dataclass.
        Missing optional fields get safe defaults.
        """
        return TurnCompletePayload(
            turn_id=str(raw.get("turn_id", "")),
            session_id=str(raw.get("session_id", "")),
            cognitive_trace_id=str(raw.get("cognitive_trace_id", "")),
            user_message=str(raw.get("user_message", "")),
            assistant_response=str(raw.get("assistant_response", "")),
            timestamp_ms=int(raw.get("timestamp_ms", 0)),
            turn_number=int(raw.get("turn_number", 0)),
            # GAP-002 temporal fields
            mentioned_time_raw=str(raw.get("mentioned_time_raw", "")),
            mentioned_time_resolved_ms=int(raw.get("mentioned_time_resolved_ms", 0)),
            mentioned_time_confidence=float(raw.get("mentioned_time_confidence", 0.0)),
            mentioned_time_is_relative=bool(raw.get("mentioned_time_is_relative", True)),
            # GAP-002 spatial fields
            mentioned_location_raw=str(raw.get("mentioned_location_raw", "")),
            mentioned_location_type=str(raw.get("mentioned_location_type", "")),
            mentioned_location_entity_id=str(raw.get("mentioned_location_entity_id", "")),
            mentioned_location_confidence=float(raw.get("mentioned_location_confidence", 0.0)),
            section_update=(
                dict(raw.get("section_update"))
                if isinstance(raw.get("section_update"), dict)
                else None
            ),
        )
