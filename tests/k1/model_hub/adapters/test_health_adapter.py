"""TestHealthAdapter -- test adapter for IHealthPort [6.1.7].

Deterministic health reporting for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from k1.model_hub.ports.health_port import HealthReport
from k1.model_hub.types import HealthStatus


@dataclass(frozen=True)
class CapturedHealthReport:
    """Recorded report_health() call."""

    component: str
    status: HealthStatus


class TestHealthAdapter:
    """Deterministic IHealthPort for testing.

    Configurable:
      - default_status: HealthStatus returned by check_health() (default HEALTHY).
      - default_component: component name for check_health() (default "model_hub").

    Capture:
      - reports: All report_health() calls.

    isinstance(adapter, IHealthPort) == True.
    """

    def __init__(
        self,
        default_status: HealthStatus = HealthStatus.HEALTHY,
        default_component: str = "model_hub",
    ) -> None:
        self._default_status = default_status
        self._default_component = default_component
        self._reports: List[CapturedHealthReport] = []
        self._component_statuses: Dict[str, HealthStatus] = {}

    def report_health(self, component: str, status: HealthStatus) -> None:
        """Record health report and update component status."""
        self._reports.append(CapturedHealthReport(component=component, status=status))
        self._component_statuses[component] = status

    def check_health(self) -> HealthReport:
        """Return HealthReport based on current state."""
        details: Dict[str, str] = {comp: st.value for comp, st in self._component_statuses.items()}
        return HealthReport(
            component=self._default_component,
            status=self._default_status,
            details=details,
        )

    # -- Test helpers ----------------------------------------------------------

    def set_default_status(self, status: HealthStatus) -> None:
        """Override the default status returned by check_health()."""
        self._default_status = status

    # -- Test inspection -------------------------------------------------------

    @property
    def reports(self) -> List[CapturedHealthReport]:
        return list(self._reports)

    @property
    def count(self) -> int:
        return len(self._reports)

    def reports_for(self, component: str) -> List[CapturedHealthReport]:
        return [r for r in self._reports if r.component == component]

    def reset(self) -> None:
        self._reports.clear()
        self._component_statuses.clear()


__all__ = ["TestHealthAdapter", "CapturedHealthReport"]
