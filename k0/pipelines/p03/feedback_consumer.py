"""P03 Feedback Consumer — Processes feedback signals from P21.

Issue: M3 3.2.6 — P21 to P03 Feedback Consumer
Related ADR: K020
Dossier Reference: Section 9.8 (P21 Feedback Integration)

P03 is a CONSUMER of the P21 feedback system, not the owner.
Feedback ingestion, schema validation, and storage are handled by P21.

This module:
1. Subscribes to `feedback.signal.p03.v1` bus topic
2. Routes signals to appropriate learning handlers (stubs for M3, real in M4+)
3. Marks signals as consumed in st_feedback_signals
4. Emits metrics for observability

Signal-to-Handler Mapping (Dossier Section 9.8.4):
- SALIENCE_ADJUSTMENT → ImportanceLearner (M2)
- DECAY_REVERSAL → DecayLearner (M3)
- CLUSTER_CORRECTION → SimilarityLearner (M4)
- REINFORCEMENT_OUTCOME → HebbianLearner (M4)
- NOVELTY_SIGNAL → AuditLogger (M1)
- REGRET_SIGNAL → DecayLearner (M3)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

from k0.feedback.payloads import P03FeedbackPayload
from k0.feedback.topics import FEEDBACK_SIGNAL_P03_V1

if TYPE_CHECKING:
    from asyncpg import Pool
    from asyncpg.connection import Connection

    from k0.bus import BusDispatcher

logger = logging.getLogger(__name__)


class FeedbackType(str, Enum):
    """Feedback signal types consumed by P03 (from Dossier 9.8.3)."""

    SALIENCE_ADJUSTMENT = "SALIENCE_ADJUSTMENT"
    DECAY_REVERSAL = "DECAY_REVERSAL"
    CLUSTER_CORRECTION = "CLUSTER_CORRECTION"
    REINFORCEMENT_OUTCOME = "REINFORCEMENT_OUTCOME"
    NOVELTY_SIGNAL = "NOVELTY_SIGNAL"
    REGRET_SIGNAL = "REGRET_SIGNAL"


class FeedbackHandler(Protocol):
    """Protocol for feedback signal handlers."""

    async def __call__(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle a feedback signal."""
        ...


@dataclass
class P03FeedbackMetrics:
    """Metrics for P03 feedback processing."""

    received_total: dict[str, int] = field(default_factory=dict)
    processed_total: dict[str, int] = field(default_factory=dict)
    errors_total: dict[str, int] = field(default_factory=dict)

    def record_received(self, feedback_type: str) -> None:
        """Record a received signal."""
        self.received_total[feedback_type] = self.received_total.get(feedback_type, 0) + 1

    def record_processed(self, feedback_type: str) -> None:
        """Record a successfully processed signal."""
        self.processed_total[feedback_type] = self.processed_total.get(feedback_type, 0) + 1

    def record_error(self, feedback_type: str) -> None:
        """Record a processing error."""
        self.errors_total[feedback_type] = self.errors_total.get(feedback_type, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        """Return metrics as dictionary for export."""
        return {
            "p03_feedback_received_total": self.received_total,
            "p03_feedback_processed_total": self.processed_total,
            "p03_feedback_errors_total": self.errors_total,
        }


class P03FeedbackConsumer:
    """Consumes and routes P21 feedback signals for P03.

    Per dossier 9.8, routes by feedback_type to learning modules.
    For M3, handlers are stubs that log and mark consumed.
    Real learning implementations come in M4+.
    """

    TOPIC = FEEDBACK_SIGNAL_P03_V1

    def __init__(self, pool: Pool) -> None:
        """Initialize consumer with database pool.

        Args:
            pool: AsyncPG connection pool for marking signals consumed
        """
        self._pool = pool
        self._handlers: dict[
            FeedbackType, Callable[[P03FeedbackPayload, Connection], Awaitable[None]]
        ] = {}
        self._metrics = P03FeedbackMetrics()
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default stub handlers for all feedback types."""
        self._handlers = {
            FeedbackType.SALIENCE_ADJUSTMENT: self._handle_salience,
            FeedbackType.DECAY_REVERSAL: self._handle_decay,
            FeedbackType.CLUSTER_CORRECTION: self._handle_cluster,
            FeedbackType.REINFORCEMENT_OUTCOME: self._handle_reinforcement,
            FeedbackType.NOVELTY_SIGNAL: self._handle_novelty,
            FeedbackType.REGRET_SIGNAL: self._handle_regret,
        }

    def register_handler(
        self,
        feedback_type: FeedbackType,
        handler: Callable[[P03FeedbackPayload, Any], Awaitable[None]],
    ) -> None:
        """Register custom handler for a feedback type.

        Use this in M4+ to inject real learning modules.

        Args:
            feedback_type: The type of feedback to handle
            handler: Async callable that processes the payload
        """
        self._handlers[feedback_type] = handler

    async def process(self, message: dict[str, Any]) -> bool:
        """Process incoming feedback message from bus.

        Args:
            message: Raw message from bus containing FeedbackEnvelope

        Returns:
            True if processed successfully, False otherwise
        """
        signal_id: str | None = None
        feedback_type_str: str = "UNKNOWN"

        try:
            # Extract envelope fields
            signal_id = message.get("feedback_id") or message.get("envelope_id")
            payload_dict = message.get("payload", {})

            # Validate and parse payload
            payload = P03FeedbackPayload.model_validate(payload_dict)
            feedback_type_str = payload.feedback_type

            # Record received metric
            self._metrics.record_received(feedback_type_str)

            # Get handler for this type
            try:
                feedback_type = FeedbackType(payload.feedback_type)
            except ValueError:
                logger.warning(
                    "Unknown feedback_type %s, skipping",
                    payload.feedback_type,
                    extra={"signal_id": signal_id},
                )
                return False

            handler = self._handlers.get(feedback_type)
            if not handler:
                logger.warning(
                    "No handler registered for %s",
                    feedback_type.value,
                    extra={"signal_id": signal_id},
                )
                return False

            # Process with connection
            async with self._pool.acquire() as conn:
                await handler(payload, conn)

                # Mark as consumed in st_feedback_signals
                if signal_id:
                    await self._mark_consumed(signal_id, conn)

            # Record success
            self._metrics.record_processed(feedback_type_str)
            logger.debug(
                "Processed P03 feedback signal",
                extra={
                    "signal_id": signal_id,
                    "feedback_type": feedback_type_str,
                },
            )
            return True

        except Exception:
            self._metrics.record_error(feedback_type_str)
            logger.exception(
                "Error processing P03 feedback signal",
                extra={"signal_id": signal_id, "feedback_type": feedback_type_str},
            )
            return False

    async def _mark_consumed(self, signal_id: str, conn: Any) -> None:
        """Mark signal as consumed in st_feedback_signals.

        Per Dossier 9.8.2:
        UPDATE st_feedback_signals
        SET consumed_at = $1, consumed_by = 'P03'
        WHERE signal_id = $2
        """
        now_ms = int(time.time() * 1000)
        await conn.execute(
            """
            UPDATE st_feedback_signals
            SET consumed_at = $1, consumed_by = 'P03'
            WHERE signal_id = $2
            """,
            now_ms,
            signal_id,
        )

    @property
    def metrics(self) -> P03FeedbackMetrics:
        """Return current metrics."""
        return self._metrics

    # =========================================================================
    # Stub handlers (M3)
    # These will be replaced with real learning implementations in M4+
    # =========================================================================

    async def _handle_salience(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle SALIENCE_ADJUSTMENT feedback.

        Routes to ImportanceLearner to adjust salience weights.

        Target: entity, episode, or pattern
        Delta: positive increases salience, negative decreases

        M4+ Implementation:
            await self.importance_learner.adjust_weight(
                target_id=payload.entity_id,
                delta=payload.salience_delta,
                confidence=payload.confidence,
            )
        """
        logger.info(
            "SALIENCE_ADJUSTMENT received (M3 stub)",
            extra={
                "entity_id": payload.entity_id,
                "salience_delta": payload.salience_delta,
                "confidence": payload.confidence,
            },
        )

    async def _handle_decay(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle DECAY_REVERSAL feedback.

        Routes to DecayLearner to reverse/pause decay.
        Memory was needed but had decayed too much.

        M4+ Implementation:
            await self.decay_learner.reverse_decay(
                entity_id=payload.entity_id,
                lambda_delta=payload.decay_lambda_delta,
            )
        """
        logger.info(
            "DECAY_REVERSAL received (M3 stub)",
            extra={
                "entity_id": payload.entity_id,
                "decay_lambda_delta": payload.decay_lambda_delta,
            },
        )

    async def _handle_cluster(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle CLUSTER_CORRECTION feedback.

        Routes to SimilarityLearner to adjust clustering thresholds.
        User indicated memories should/shouldn't be grouped.

        M4+ Implementation:
            await self.similarity_learner.update_clustering(
                entity_id=payload.entity_id,
                correct_cluster=payload.correct_cluster_id,
                incorrect_cluster=payload.incorrect_cluster_id,
            )
        """
        logger.info(
            "CLUSTER_CORRECTION received (M3 stub)",
            extra={
                "entity_id": payload.entity_id,
                "correct_cluster_id": payload.correct_cluster_id,
                "incorrect_cluster_id": payload.incorrect_cluster_id,
            },
        )

    async def _handle_reinforcement(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle REINFORCEMENT_OUTCOME feedback.

        Routes to HebbianLearner for edge weight updates.
        Delta: reward (+) or penalty (-) for co-occurrence.

        M4+ Implementation:
            await self.hebbian_learner.apply_reward(
                edge_id=payload.edge_id,
                reward=payload.salience_delta,
                was_helpful=payload.was_helpful,
            )
        """
        logger.info(
            "REINFORCEMENT_OUTCOME received (M3 stub)",
            extra={
                "edge_id": payload.edge_id,
                "was_helpful": payload.was_helpful,
            },
        )

    async def _handle_novelty(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle NOVELTY_SIGNAL feedback.

        Routes to AuditLogger for tracking novel patterns.
        Used for system monitoring, not active learning.
        Triggered by K1 hedging detection (uncertainty in responses).

        M4+ Implementation:
            await self.audit_logger.log_novelty(
                session_context=payload.session_context,
                confidence=payload.confidence,
            )
        """
        logger.info(
            "NOVELTY_SIGNAL received (M3 stub)",
            extra={
                "confidence": payload.confidence,
                "session_context": payload.session_context,
            },
        )

    async def _handle_regret(self, payload: P03FeedbackPayload, conn: Any) -> None:
        """Handle REGRET_SIGNAL feedback.

        Routes to DecayLearner for decision correction.
        Triggered when a pruned entity was later queried.

        M4+ Implementation:
            await self.decay_learner.learn_from_regret(
                entity_id=payload.entity_id,
                was_retrieved=payload.was_retrieved,
            )
        """
        logger.info(
            "REGRET_SIGNAL received (M3 stub)",
            extra={
                "entity_id": payload.entity_id,
                "was_retrieved": payload.was_retrieved,
            },
        )


class P03FeedbackSubscriber:
    """Bus subscriber for P21 feedback signals.

    Wraps P03FeedbackConsumer with bus subscription lifecycle.
    """

    def __init__(
        self,
        consumer: P03FeedbackConsumer,
        bus: BusDispatcher,
    ) -> None:
        """Initialize subscriber.

        Args:
            consumer: The P03FeedbackConsumer instance
            bus: BusDispatcher for subscribing to topics
        """
        self._consumer = consumer
        self._bus = bus
        self._running = False

    @property
    def running(self) -> bool:
        """Return whether subscriber is running."""
        return self._running

    async def start(self) -> None:
        """Start consuming feedback signals."""
        if self._running:
            logger.warning("P03FeedbackSubscriber already running")
            return

        self._running = True
        self._bus.subscribe(
            topic=P03FeedbackConsumer.TOPIC,
            handler=self._handle_message,
        )
        logger.info("P03FeedbackSubscriber started on topic %s", P03FeedbackConsumer.TOPIC)

    async def stop(self) -> None:
        """Stop consuming."""
        if not self._running:
            return

        self._running = False
        # Note: BusDispatcher doesn't have unsubscribe yet, just mark as stopped
        # Messages received after stop will be ignored
        logger.info("P03FeedbackSubscriber stopped")

    async def _handle_message(self, message: Any) -> None:
        """Handle incoming bus message.

        Args:
            message: BusMessage from bus dispatcher
        """
        # Extract payload from BusMessage
        # BusMessage.payload is bytes, decode to dict
        import json

        payload_dict: dict[str, Any] = {}
        if hasattr(message, "payload") and message.payload:
            try:
                payload_dict = json.loads(message.payload)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to decode BusMessage payload")
                return
        elif isinstance(message, dict):
            # Already a dict (e.g., in tests)
            payload_dict = message

        success = await self._consumer.process(payload_dict)

        if not success:
            # TODO: Implement retry/DLQ logic in M4+
            # For now, just log
            logger.warning(
                "Failed to process feedback message, would DLQ in production",
                extra={"message_keys": list(payload_dict.keys())},
            )


__all__ = [
    "FeedbackType",
    "P03FeedbackConsumer",
    "P03FeedbackMetrics",
    "P03FeedbackSubscriber",
]
