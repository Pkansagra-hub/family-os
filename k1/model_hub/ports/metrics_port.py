"""IMetricsPort -- metrics emission [F13].

Synchronous, fire-and-forget metrics port.

Import graph (Layer 1)
----------------------
k1.model_hub.ports.metrics_port
  -> stdlib only
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class IMetricsPort(Protocol):
    """Metrics emission port.

    Labels: provider, model, consumer, capability, priority.
    Synchronous, fire-and-forget (never blocks request pipeline).
    """

    def emit(
        self,
        metric_name: str,
        value: float,
        labels: Dict[str, Any] | None = None,
    ) -> None:
        """Emit a metric value with optional labels."""
        ...


__all__ = ["IMetricsPort"]
