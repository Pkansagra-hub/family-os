"""IHealthPort -- health reporting [F16].

Reports hub health to Fabric/Observability.

Import graph (Layer 1)
----------------------
k1.model_hub.ports.health_port
  -> k1.model_hub.types (HealthStatus)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Protocol, runtime_checkable

from k1.model_hub.types import HealthStatus


@dataclass(frozen=True)
class HealthReport:
    """Component-level health report."""

    component: str
    status: HealthStatus
    details: Dict[str, str] = field(default_factory=dict)


@runtime_checkable
class IHealthPort(Protocol):
    """Health reporting port.

    Status: HEALTHY | DEGRADED | UNHEALTHY.
    """

    def report_health(self, component: str, status: HealthStatus) -> None:
        """Report health status for a component."""
        ...

    def check_health(self) -> HealthReport:
        """Check and return current health status."""
        ...


__all__ = ["IHealthPort", "HealthReport"]
