"""
k1.kernel.ports.orchestrator_port -- IOrchestratorPort (2.0.8).

Kernel-level port for the shared Orchestrator lifecycle and access.

The Orchestrator is a shared Tier 1 component (S5) that handles MED/HIGH
tier task dispatch. It owns a 9-port hexagonal boundary internally
(see ``k1.orchestrator.ports``). This kernel port manages its lifecycle
and exposes it to per-session Concierge instances.

Design:
  - ``startup()`` / ``shutdown()`` are async (internal async init).
  - ``get_service()`` is sync (returns the Orchestrator reference).
  - ``wire_planner()`` is the S6b cross-wire step: replaces
    MockPlannerAdapter with real PlannerAdapter after Planner starts.

Production adapter: will wrap ``OrchestratorFactory.create_production()``
  (see ``k1.orchestrator.factory``).

References:
  - S5 (Orchestrator) and S6b (cross-wire) in
    08_end_to_end_wiring_requirements
  - O-1..O-9 (Orchestrator port inventory) in 05_port_adapter_mapping
  - B-OR-5 (AdminHttpAdapter isinstance bug) resolved by Issue 2.0.11

Exports:
  IOrchestratorPort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IOrchestratorPort(Protocol):
    """Kernel port for Orchestrator lifecycle and access.

    Manages the shared Orchestrator instance. Includes the cross-wire
    step (S6b) where MockPlannerAdapter is replaced with real Planner
    after Planner startup.
    """

    async def startup(
        self,
        bus: Any,
        router: Any,
        fabric: Any,
        model_hub: Any,
        bridge: Any,
    ) -> None:
        """Create and start the Orchestrator with its 9 ports.

        Args:
            bus: The shared ``IBus`` instance.
            router: The shared ``IMailboxRouter`` instance.
            fabric: The shared ``CapabilityFabric`` instance.
            model_hub: The shared ``ModelHub`` instance.
            bridge: The bridge client (or ``None``).
        """
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Shutdown the Orchestrator, cancel background tasks."""
        ...  # pragma: no cover

    def get_service(self) -> Any:
        """Return the ``OrchestratorService`` instance.

        Returns:
            The live Orchestrator service for task dispatch.
        """
        ...  # pragma: no cover

    async def wire_planner(self, planner: Any) -> None:
        """Cross-wire step S6b: replace MockPlannerAdapter with real Planner.

        Args:
            planner: The live ``Planner`` instance (started in S6).
        """
        ...  # pragma: no cover
