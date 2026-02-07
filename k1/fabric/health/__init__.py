"""
k1.fabric.health -- Health Checker subsystem (Epic 3.6).

Provides periodic provider health monitoring, availability tracking
with state transition history, and bidirectional circuit breaker
integration.

Submodules:
  availability_tracker -- Per-provider ONLINE/DEGRADED/OFFLINE tracking (3.6.2)
  health_checker       -- Periodic health monitor + CB wiring (3.6.1 + 3.6.3)

Usage::

    from k1.fabric.health import (
        AvailabilityTracker,
        HealthChecker,
        HealthCheckerConfig,
    )

    tracker = AvailabilityTracker(event_port=bus)
    checker = HealthChecker(
        provider_registry=registry,
        availability_tracker=tracker,
        provider_instances=providers,
        circuit_breakers=breakers,
        event_port=bus,
    )
    await checker.start()
"""

from k1.fabric.health.availability_tracker import (
    DEFAULT_MAX_HISTORY,
    EVENT_AVAILABILITY_CHANGED,
    VALID_TRANSITIONS,
    AvailabilityTracker,
    AvailabilityTrackerError,
    InvalidTransitionError,
    ProviderNotTrackedError,
    StateTransition,
)
from k1.fabric.health.health_checker import (
    DEFAULT_CHECK_INTERVAL_S,
    DEFAULT_CHECK_TIMEOUT_S,
    DEFAULT_FAILURE_THRESHOLD,
    EVENT_HEALTH_CHANGED,
    EVENT_HEALTH_CHECK_CYCLE,
    HealthChecker,
    HealthCheckerConfig,
    HealthCheckResult,
)

__all__ = [
    # availability_tracker.py
    "AvailabilityTracker",
    "AvailabilityTrackerError",
    "DEFAULT_MAX_HISTORY",
    "EVENT_AVAILABILITY_CHANGED",
    "InvalidTransitionError",
    "ProviderNotTrackedError",
    "StateTransition",
    "VALID_TRANSITIONS",
    # health_checker.py
    "DEFAULT_CHECK_INTERVAL_S",
    "DEFAULT_CHECK_TIMEOUT_S",
    "DEFAULT_FAILURE_THRESHOLD",
    "EVENT_HEALTH_CHANGED",
    "EVENT_HEALTH_CHECK_CYCLE",
    "HealthCheckResult",
    "HealthChecker",
    "HealthCheckerConfig",
]
