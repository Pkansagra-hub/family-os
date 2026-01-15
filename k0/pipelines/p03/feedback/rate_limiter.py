"""Feedback rate limiter with sliding window (Issue 6.2.11).

Implements per-user/device rate limiting for feedback signals
using sliding window algorithm.

Dossier Reference: Section 6.21.4 Detection Algorithms
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    exceeded: bool
    current_count: int
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp when window resets
    window_size: int  # Window size in seconds


# Default configuration
DEFAULT_MAX_SIGNALS_PER_MINUTE: int = 100
DEFAULT_WINDOW_SIZE_SECONDS: int = 60


class FeedbackRateLimiter:
    """Rate limit feedback signals per user/device.

    Uses sliding window algorithm with configurable limits.

    Dossier Reference: Section 6.21.4
    """

    def __init__(
        self,
        *,
        max_signals_per_minute: int = DEFAULT_MAX_SIGNALS_PER_MINUTE,
        window_size_seconds: int = DEFAULT_WINDOW_SIZE_SECONDS,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_signals_per_minute: Maximum signals allowed in window.
            window_size_seconds: Sliding window size in seconds.
            metrics: Optional metrics exporter.
        """
        self._max_per_minute = max_signals_per_minute
        self._window_size = window_size_seconds
        self._metrics = metrics

    @property
    def max_signals(self) -> int:
        """Maximum signals allowed per window."""
        return self._max_per_minute

    @property
    def window_size(self) -> int:
        """Window size in seconds."""
        return self._window_size

    async def check_rate_limit(
        self,
        space_id: str,
        user_id: str,
        *,
        device_id: Optional[str] = None,
        connection: asyncpg.Connection,
    ) -> RateLimitResult:
        """Check if user/device has exceeded rate limit.

        Args:
            space_id: Space context.
            user_id: User to check.
            device_id: Optional device for device-specific limits.
            connection: Database connection.

        Returns:
            RateLimitResult with exceeded status and remaining quota.
        """
        now = int(time.time())
        window_start = now - self._window_size

        # Count signals in current window
        if device_id:
            row = await connection.fetchrow(
                """
                SELECT COUNT(*) as signal_count
                FROM st_feedback_signals
                WHERE space_id = $1
                  AND user_id = $2
                  AND device_id = $3
                  AND created_at > $4
                """,
                space_id,
                user_id,
                device_id,
                window_start,
            )
        else:
            row = await connection.fetchrow(
                """
                SELECT COUNT(*) as signal_count
                FROM st_feedback_signals
                WHERE space_id = $1
                  AND user_id = $2
                  AND created_at > $3
                """,
                space_id,
                user_id,
                window_start,
            )

        current_count = row["signal_count"] if row else 0
        exceeded = current_count >= self._max_per_minute
        remaining = max(0, self._max_per_minute - current_count)
        reset_at = now + self._window_size

        # Emit metrics
        self._emit_metric(
            "p03_rate_limit_checks_total",
            exceeded=str(exceeded).lower(),
        )

        if exceeded:
            self._emit_metric(
                "p03_rate_limit_exceeded_total",
                user_id=user_id[:8],  # Truncate for cardinality
            )

        return RateLimitResult(
            exceeded=exceeded,
            current_count=current_count,
            limit=self._max_per_minute,
            remaining=remaining,
            reset_at=reset_at,
            window_size=self._window_size,
        )

    async def get_remaining_quota(
        self,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> tuple[int, int]:
        """Get remaining quota for rate limit headers.

        Returns:
            Tuple of (remaining, reset_at) for X-RateLimit headers.
        """
        result = await self.check_rate_limit(
            space_id,
            user_id,
            connection=connection,
        )
        return result.remaining, result.reset_at

    async def get_usage_stats(
        self,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> dict[str, int]:
        """Get detailed usage statistics for user.

        Args:
            space_id: Space context.
            user_id: User to check.
            connection: Database connection.

        Returns:
            Dict with 'current', 'limit', 'remaining', 'reset_at' keys.
        """
        result = await self.check_rate_limit(
            space_id,
            user_id,
            connection=connection,
        )
        return {
            "current": result.current_count,
            "limit": result.limit,
            "remaining": result.remaining,
            "reset_at": result.reset_at,
            "window_size": result.window_size,
        }

    async def is_allowed(
        self,
        space_id: str,
        user_id: str,
        *,
        device_id: Optional[str] = None,
        connection: asyncpg.Connection,
    ) -> bool:
        """Simple check if next signal would be allowed.

        Args:
            space_id: Space context.
            user_id: User to check.
            device_id: Optional device ID.
            connection: Database connection.

        Returns:
            True if signal would be allowed.
        """
        result = await self.check_rate_limit(
            space_id,
            user_id,
            device_id=device_id,
            connection=connection,
        )
        return not result.exceeded

    def _emit_metric(self, name: str, **labels: str) -> None:
        """Emit metric with labels."""
        if self._metrics is not None:
            self._metrics.emit(name, 1.0, **labels)


def create_feedback_rate_limiter(
    *,
    max_signals_per_minute: int = DEFAULT_MAX_SIGNALS_PER_MINUTE,
    window_size_seconds: int = DEFAULT_WINDOW_SIZE_SECONDS,
    metrics: Optional[MetricsExporter] = None,
) -> FeedbackRateLimiter:
    """Factory function to create FeedbackRateLimiter.

    Args:
        max_signals_per_minute: Maximum signals allowed in window.
        window_size_seconds: Sliding window size in seconds.
        metrics: Optional metrics exporter.

    Returns:
        Configured FeedbackRateLimiter instance.
    """
    return FeedbackRateLimiter(
        max_signals_per_minute=max_signals_per_minute,
        window_size_seconds=window_size_seconds,
        metrics=metrics,
    )
