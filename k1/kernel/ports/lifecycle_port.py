"""
k1.kernel.ports.lifecycle_port -- ILifecyclePort (2.0.8).

Kernel-level port for KernelService startup, shutdown, and health.

This is the top-level lifecycle port that orchestrates the 8-phase
Tier 1 bootstrap (S1-S7 + S6b cross-wire) and the reverse shutdown
sequence. It also provides health aggregation across all components.

Design:
  - ``startup()`` is async (8-phase bootstrap, all components created).
  - ``shutdown()`` is async (reverse teardown: destroy all sessions,
    then Planner → Orchestrator → Bridge → Fabric → ModelHub → Bus).
  - ``health_check()`` is async (aggregates health from all components).
  - ``is_running()`` is sync (boolean flag).

References:
  - S1..S7 (Tier 1 bootstrap) in 08_end_to_end_wiring_requirements
  - Section 7 (Shutdown Wiring) in 08_end_to_end_wiring_requirements
  - Issue 2.1.1 (KernelService class skeleton)

Exports:
  ILifecyclePort
  HealthStatus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class HealthStatus:
    """Aggregated health snapshot across all kernel components.

    Attributes:
        healthy: Overall health (True only if all required components OK).
        components: Per-component health: ``{"bus": True, "model_hub": False, ...}``.
        details: Optional diagnostic details for unhealthy components.
    """

    healthy: bool
    components: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class ILifecyclePort(Protocol):
    """Kernel port for top-level lifecycle management.

    Controls the full bootstrap (S1-S7) and shutdown sequence
    for the KernelService.
    """

    async def startup(self) -> None:
        """Execute the 8-phase Tier 1 bootstrap.

        Phases: S1 (Bus) → S2 (ModelHub) → S3 (Shared Fabric) →
        S4 (Bridge) → S5 (Orchestrator) → S6 (Planner) →
        S6b (Cross-wire) → S7 (Return runtime).

        Raises:
            RuntimeError: If a FATAL phase fails (S1, S5).
        """
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Reverse teardown: destroy sessions, then shared components.

        Order: all sessions → Planner → Orchestrator → Bridge →
        Shared Fabric → ModelHub → Bus.
        """
        ...  # pragma: no cover

    async def health_check(self) -> HealthStatus:
        """Aggregate health from all components.

        Returns:
            A ``HealthStatus`` snapshot with per-component details.
        """
        ...  # pragma: no cover

    @property
    def is_running(self) -> bool:
        """Check whether the kernel has completed startup.

        Exposed as a ``@property`` so callers can use plain attribute
        access (``svc.is_running``) without the parentheses footgun.
        ``KernelService`` matches this shape; alternative implementations
        SHOULD also expose ``is_running`` as a property to preserve a
        single calling convention.
        """
        ...  # pragma: no cover
