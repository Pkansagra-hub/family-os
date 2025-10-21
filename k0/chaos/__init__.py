"""
Chaos Engineering Module for K0 Kernel

Provides controlled fault injection capabilities for resilience testing:
- WAL fsync failures (OSError injection)
- Scheduler starvation (capacity reduction)
- Network latency (transport delay)
- Telemetry outage (metric drop)

CRITICAL: Zero simulation code - all faults are real errors/behaviors.
"""

from dataclasses import dataclass

__all__ = [
    "ChaosDecision",
    "should_fail_fsync",
    "apply_scheduler_starvation",
    "get_network_delay_ms",
    "should_drop_telemetry",
    "ChaosTransport",
]


@dataclass
class ChaosDecision:
    """Result of chaos toggle evaluation."""

    should_inject: bool
    reason: str | None = None
    metadata: dict | None = None


from k0.chaos.network import ChaosTransport

# Import after dataclass to avoid circular dependencies
from k0.chaos.toggles import (
    apply_scheduler_starvation,
    get_network_delay_ms,
    should_drop_telemetry,
    should_fail_fsync,
)
