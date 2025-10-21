"""Retry scheduling primitives for outbox workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from k0.storage.outbox import OutboxEntry


@dataclass(frozen=True)
class RetryDecision:
    """Represents the outcome of a retry scheduling decision."""

    action: str  # "retry" or "quarantine"
    retries: int
    requeue_seq: int


class RetryScheduler:
    """Compute retry decisions with exponential backoff semantics."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        backoff_steps: Sequence[int] | None = None,
    ) -> None:
        if max_attempts <= 0:
            msg = "max_attempts must be greater than zero"
            raise ValueError(msg)
        if backoff_steps is not None and not backoff_steps:
            msg = "backoff_steps must be non-empty when provided"
            raise ValueError(msg)

        self._max_attempts = max_attempts
        self._backoff_steps: Sequence[int] = backoff_steps or (1, 2, 4, 8, 16)

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def decide(self, entry: OutboxEntry) -> RetryDecision:
        """Return the retry decision for the provided outbox *entry*."""

        if entry.id is None:
            msg = "outbox entry must be persisted before scheduling"
            raise ValueError(msg)

        next_retry = entry.retries + 1
        if next_retry >= self._max_attempts:
            return RetryDecision(
                action="quarantine",
                retries=next_retry,
                requeue_seq=entry.requeue_seq,
            )

        backoff_index = min(next_retry - 1, len(self._backoff_steps) - 1)
        increment = self._backoff_steps[backoff_index]
        return RetryDecision(
            action="retry",
            retries=next_retry,
            requeue_seq=entry.requeue_seq + increment,
        )
