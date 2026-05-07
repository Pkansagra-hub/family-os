"""HealthReportAdapter -- Fabric health reporting [F36].

Reports hub health to Fabric/Observability.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.health_report_adapter
  -> k1.model_hub.ports      (Layer 1)
  -> k1.model_hub.types      (Layer 0)
  -> stdlib only
"""

from __future__ import annotations

import logging
from typing import Dict

from k1.model_hub.ports.health_port import HealthReport
from k1.model_hub.types import HealthStatus

logger = logging.getLogger(__name__)


class HealthReportAdapter:
    """IHealthPort adapter reporting hub health to Fabric.

    Production: publishes health to Fabric health-check endpoint.
    Current: in-memory status tracking for single-process operation.

    Error handling: never crash hub on health report failure.
    """

    def __init__(self, component: str = "model_hub") -> None:
        self._component = component
        self._statuses: Dict[str, HealthStatus] = {}

    def report_health(self, component: str, status: HealthStatus) -> None:
        """Report health status for a sub-component."""
        try:
            self._statuses[component] = status
        except Exception:
            logger.exception(
                "HealthReportAdapter.report_health failed component=%s",
                component,
            )

    def check_health(self) -> HealthReport:
        """Aggregate health from all sub-components.

        Returns HEALTHY if all sub-components healthy.
        Returns DEGRADED if any sub-component degraded.
        Returns UNHEALTHY if any sub-component unhealthy.
        """
        try:
            details: Dict[str, str] = {comp: st.value for comp, st in self._statuses.items()}
            if not self._statuses:
                overall = HealthStatus.HEALTHY
            elif any(s == HealthStatus.UNHEALTHY for s in self._statuses.values()):
                overall = HealthStatus.UNHEALTHY
            elif any(s == HealthStatus.DEGRADED for s in self._statuses.values()):
                overall = HealthStatus.DEGRADED
            else:
                overall = HealthStatus.HEALTHY
            return HealthReport(
                component=self._component,
                status=overall,
                details=details,
            )
        except Exception:
            logger.exception("HealthReportAdapter.check_health failed")
            return HealthReport(
                component=self._component,
                status=HealthStatus.UNHEALTHY,
            )


__all__ = ["HealthReportAdapter"]
