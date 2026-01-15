"""P03 Retry Configuration — Issue 6.2.4.

P03-specific retry configuration with phase overrides and exponential backoff.

References:
- Dossier Section 13.5: Retry Strategy (K0 RetryScheduler)
- M6_EXECUTION.md Issue 6.2.4
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from k0.outbox.scheduler import RetryDecision


# =============================================================================
# PHASE RETRY OVERRIDES (from Dossier Section 13.5)
# =============================================================================

# Phase-specific max_attempts overrides
PHASE_RETRY_OVERRIDES: Dict[str, Dict[str, int]] = {
    "R0": {"max_attempts": 5},  # Trigger detection - retry more (lock contention)
    "R7": {"max_attempts": 10},  # Truth writes - critical (version conflicts)
    "R8": {"max_attempts": 3},  # Bus emission - standard
    # Other phases use default_max_attempts
}


@dataclass
class P03RetryConfig:
    """P03-specific retry configuration with phase overrides.

    Implements exponential backoff with jitter for retry delays.

    References:
    - k0/outbox/scheduler.py: K0 RetryScheduler
    - Dossier Section 13.5

    Attributes:
        base_delay_ms: Initial retry delay in milliseconds.
        max_delay_ms: Maximum backoff cap in milliseconds.
        exponential_base: Backoff multiplier (default 2.0).
        jitter_factor: Random jitter factor (±10%).
        default_max_attempts: Default max retries if no phase override.
        phase_overrides: Phase-specific retry settings.
    """

    base_delay_ms: int = 1000
    max_delay_ms: int = 60000
    exponential_base: float = 2.0
    jitter_factor: float = 0.1
    default_max_attempts: int = 3
    phase_overrides: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: dict(PHASE_RETRY_OVERRIDES)
    )

    def get_max_attempts(self, phase: str) -> int:
        """Get max retry attempts for a phase.

        Args:
            phase: Phase identifier (R0-R8).

        Returns:
            Maximum retry attempts for the phase.
        """
        override = self.phase_overrides.get(phase, {})
        return override.get("max_attempts", self.default_max_attempts)

    def get_backoff_delay_ms(self, attempt: int) -> int:
        """Calculate exponential backoff delay for attempt number.

        Args:
            attempt: Current attempt number (1-based).

        Returns:
            Delay in milliseconds before next retry.

        Example:
            Attempt 1: 1000ms
            Attempt 2: 2000ms
            Attempt 3: 4000ms
            ...
            Attempt 6+: 60000ms (capped)
        """
        delay = self.base_delay_ms * (self.exponential_base ** (attempt - 1))
        return min(int(delay), self.max_delay_ms)

    def add_jitter(self, delay_ms: int) -> int:
        """Add random jitter to delay (±jitter_factor).

        Args:
            delay_ms: Base delay in milliseconds.

        Returns:
            Delay with random jitter applied.
        """
        jitter_range = int(delay_ms * self.jitter_factor)
        if jitter_range == 0:
            return delay_ms
        jitter = random.randint(-jitter_range, jitter_range)
        return max(0, delay_ms + jitter)

    def get_delay_with_jitter(self, attempt: int) -> int:
        """Get backoff delay with jitter for an attempt.

        Args:
            attempt: Current attempt number (1-based).

        Returns:
            Delay in milliseconds with jitter.
        """
        delay = self.get_backoff_delay_ms(attempt)
        return self.add_jitter(delay)


class P03RetryScheduler:
    """Phase-aware retry scheduler for P03 using K0 patterns.

    Integrates with k0/outbox/scheduler.py RetryDecision format.
    Provides phase-specific max_attempts and exponential backoff.

    References:
    - Dossier Section 13.5
    """

    def __init__(self, config: Optional[P03RetryConfig] = None) -> None:
        """Initialize retry scheduler.

        Args:
            config: Optional retry configuration.
                    Uses default P03RetryConfig if not provided.
        """
        self._config = config or P03RetryConfig()

    @property
    def config(self) -> P03RetryConfig:
        """Get retry configuration."""
        return self._config

    def decide(
        self,
        phase: str,
        attempt_count: int,
        error: Optional[BaseException] = None,
    ) -> RetryDecision:
        """Decide whether to retry based on phase and attempt count.

        Args:
            phase: Phase identifier (R0-R8).
            attempt_count: Current attempt number.
            error: Optional exception (for logging/classification).

        Returns:
            RetryDecision with action="retry" or action="quarantine".
        """
        from k0.outbox.scheduler import RetryDecision

        max_attempts = self._config.get_max_attempts(phase)

        if attempt_count >= max_attempts:
            # Max retries exceeded → quarantine
            return RetryDecision(
                action="quarantine",
                retries=attempt_count,
                requeue_seq=0,
                next_attempt_ts=None,
                backoff_exp=0,
                status="DEAD",
            )

        # Calculate backoff with jitter
        delay_ms = self._config.get_delay_with_jitter(attempt_count)
        next_attempt = datetime.now(timezone.utc) + timedelta(milliseconds=delay_ms)
        backoff_exp = min(attempt_count, 6)

        return RetryDecision(
            action="retry",
            retries=attempt_count,
            requeue_seq=0,
            next_attempt_ts=next_attempt,
            backoff_exp=backoff_exp,
            status="PENDING",
        )

    def should_retry(self, phase: str, attempt_count: int) -> bool:
        """Check if retry should be attempted.

        Args:
            phase: Phase identifier (R0-R8).
            attempt_count: Current attempt number.

        Returns:
            True if attempt_count < max_attempts for phase.
        """
        return attempt_count < self._config.get_max_attempts(phase)

    def get_delay_ms(self, attempt_count: int) -> int:
        """Get delay for next retry attempt (with jitter).

        Args:
            attempt_count: Current attempt number.

        Returns:
            Delay in milliseconds before next retry.
        """
        return self._config.get_delay_with_jitter(attempt_count)

    def get_remaining_attempts(self, phase: str, attempt_count: int) -> int:
        """Get remaining retry attempts for a phase.

        Args:
            phase: Phase identifier (R0-R8).
            attempt_count: Current attempt number.

        Returns:
            Number of remaining attempts (0 if exhausted).
        """
        max_attempts = self._config.get_max_attempts(phase)
        return max(0, max_attempts - attempt_count)


def create_p03_retry_scheduler(
    config: Optional[P03RetryConfig] = None,
) -> P03RetryScheduler:
    """Factory for P03's retry scheduler instance.

    Args:
        config: Optional custom retry configuration.

    Returns:
        Configured P03RetryScheduler instance.
    """
    return P03RetryScheduler(config=config)


# =============================================================================
# RETRY DELAY REFERENCE TABLE
# =============================================================================
#
# | Attempt | Base Delay | With Jitter (±10%) | Max Cap |
# |---------|------------|-------------------|---------|
# | 1       | 1000ms     | 900-1100ms        | —       |
# | 2       | 2000ms     | 1800-2200ms       | —       |
# | 3       | 4000ms     | 3600-4400ms       | —       |
# | 4       | 8000ms     | 7200-8800ms       | —       |
# | 5       | 16000ms    | 14400-17600ms     | —       |
# | 6       | 32000ms    | 28800-35200ms     | —       |
# | 7+      | 60000ms    | 54000-60000ms     | capped  |
#
# =============================================================================
