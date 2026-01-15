"""P03 Error Handler — Issue 6.2.2.

Central error handler that routes errors to retry scheduler, DLQ, or circuit breaker
based on classification from ErrorClassifier.

References:
- Dossier Section 13.3: K0 DLQ Integration
- M6_EXECUTION.md Issue 6.2.2
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from k0.pipelines.p03.ops.error_classifier import ErrorClassifier, P03ErrorCategory
from k0.storage.dlq import DeadLetter, DeadLetterQueue

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter
    from k0.outbox.scheduler import RetryDecision


@dataclass
class P03ErrorContext:
    """Context for error handling decisions.

    Captures all metadata needed to record errors in DLQ
    and make retry decisions.
    """

    cycle_id: str
    phase: str
    event_id: Optional[str] = None
    entity_id: Optional[str] = None
    tenant_id: str = ""
    space_id: str = ""
    attempt_count: int = 1
    max_attempts: int = 3
    payload: dict = field(default_factory=dict)


class P03ErrorHandler:
    """Central error handler integrated with K0 DLQ and retry subsystems.

    Routes errors based on classification:
    - TRANSIENT: Schedule retry via RetryScheduler (up to max_attempts)
    - VALIDATION: Immediate DLQ (no retry)
    - LOGIC: DLQ + alert emission
    - FATAL: DLQ + circuit breaker trigger

    References:
    - k0/storage/dlq.py: DeadLetterQueue.record()
    - k0/outbox/scheduler.py: RetryScheduler.decide()
    - Dossier Section 13.3
    """

    DRIVER = "p03_consolidation"

    def __init__(
        self,
        dlq: DeadLetterQueue,
        metrics: Optional[MetricsExporter] = None,
        *,
        default_max_attempts: int = 3,
    ) -> None:
        """Initialize error handler.

        Args:
            dlq: K0 DeadLetterQueue for recording failed operations.
            metrics: Optional metrics exporter for observability.
            default_max_attempts: Default max retry attempts if not in context.
        """
        self._dlq = dlq
        self._metrics = metrics
        self._classifier = ErrorClassifier()
        self._default_max_attempts = default_max_attempts

    async def handle_error(
        self,
        error: BaseException,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Optional[RetryDecision]:
        """Route error to appropriate handler based on classification.

        Args:
            error: The exception that occurred.
            context: Error context with cycle/phase/event info.
            connection: Optional database connection for DLQ writes.

        Returns:
            RetryDecision if error should be retried, None if sent to DLQ.
        """
        category = self._classifier.classify(error)

        # Emit error metric
        self._emit_metric(
            "p03_errors_total",
            1.0,
            phase=context.phase,
            error_type=category.value,
            error_class=type(error).__name__,
        )

        if category == P03ErrorCategory.TRANSIENT:
            return await self._handle_transient(error, context, connection=connection)
        elif category == P03ErrorCategory.VALIDATION:
            await self._handle_validation(error, context, connection=connection)
            return None
        elif category == P03ErrorCategory.LOGIC:
            await self._handle_logic(error, context, connection=connection)
            return None
        else:  # FATAL
            await self._handle_fatal(error, context, connection=connection)
            return None

    async def _handle_transient(
        self,
        error: BaseException,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Optional[RetryDecision]:
        """Handle transient error with retry logic.

        Returns RetryDecision if retry should be attempted,
        None if max attempts exceeded (sent to DLQ).
        """
        from datetime import datetime, timedelta, timezone

        from k0.outbox.scheduler import RetryDecision

        max_attempts = context.max_attempts or self._default_max_attempts

        if context.attempt_count >= max_attempts:
            # Max retries exceeded, send to DLQ
            await self._send_to_dlq(
                error,
                context,
                category=P03ErrorCategory.TRANSIENT,
                status="ABANDONED",
                connection=connection,
            )
            self._emit_metric(
                "p03_retry_exhausted_total",
                1.0,
                phase=context.phase,
            )
            return None

        # Calculate exponential backoff with jitter
        backoff_exp = min(context.attempt_count, 6)
        backoff_seconds = 2**backoff_exp
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)

        self._emit_metric(
            "p03_retry_scheduled_total",
            1.0,
            phase=context.phase,
            attempt=str(context.attempt_count),
        )

        return RetryDecision(
            action="retry",
            retries=context.attempt_count,
            requeue_seq=0,
            next_attempt_ts=next_attempt,
            backoff_exp=backoff_exp,
            status="PENDING",
        )

    async def _handle_validation(
        self,
        error: BaseException,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Handle validation error - immediate DLQ, no retry."""
        await self._send_to_dlq(
            error,
            context,
            category=P03ErrorCategory.VALIDATION,
            status="PENDING",
            connection=connection,
        )

    async def _handle_logic(
        self,
        error: BaseException,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Handle logic error - DLQ + alert."""
        await self._send_to_dlq(
            error,
            context,
            category=P03ErrorCategory.LOGIC,
            status="MANUAL_REVIEW",
            connection=connection,
        )

        # Emit alert metric
        self._emit_metric(
            "p03_error_alert_total",
            1.0,
            phase=context.phase,
            severity="high",
        )

    async def _handle_fatal(
        self,
        error: BaseException,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Handle fatal error - DLQ + circuit breaker trigger."""
        await self._send_to_dlq(
            error,
            context,
            category=P03ErrorCategory.FATAL,
            status="ABANDONED",
            connection=connection,
        )

        # Emit fatal alert metric
        self._emit_metric(
            "p03_error_fatal_total",
            1.0,
            phase=context.phase,
            severity="critical",
        )

    async def _send_to_dlq(
        self,
        error: BaseException,
        context: P03ErrorContext,
        *,
        category: P03ErrorCategory,
        status: str = "PENDING",
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record error in K0 DLQ (st_dlq table).

        Args:
            error: The exception that occurred.
            context: Error context.
            category: Error category from classifier.
            status: DLQ entry status.
            connection: Optional database connection.

        Returns:
            The assigned dead letter ID.
        """
        import time

        now = str(int(time.time() * 1000))

        # Build payload with full error context
        payload_dict = {
            "cycle_id": context.cycle_id,
            "phase": context.phase,
            "event_id": context.event_id,
            "entity_id": context.entity_id,
            "error_type": category.value,
            "error_code": type(error).__name__,
            "error_message": str(error),
            "stack_trace": traceback.format_exc(),
            "attempt_count": context.attempt_count,
            "max_attempts": context.max_attempts,
            "payload": context.payload,
        }

        letter = DeadLetter(
            id=None,
            wal_pos=None,
            tenant_id=context.tenant_id,
            space_id=context.space_id,
            driver=self.DRIVER,
            op_kind=context.phase,
            fingerprint=f"{context.cycle_id}:{context.event_id or 'batch'}",
            payload=json.dumps(payload_dict).encode("utf-8"),
            reason=str(error),
            retries=context.attempt_count,
            requeue_seq=0,
            first_failure_ts=now,
            last_failure_ts=now,
            state=status,
        )

        dlq_id = await self._dlq.record(letter, connection=connection)

        self._emit_metric(
            "p03_dlq_records_total",
            1.0,
            phase=context.phase,
            error_type=category.value,
            status=status,
        )

        return dlq_id

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics is not None:
            self._metrics.emit(name, value, **labels)
