"""
k1.kernel.ports.planner_port -- IPlannerPort (2.0.8).

Kernel-level port for the shared Planner lifecycle and access.

The Planner is a shared Tier 1 component (S6) that runs as a background
task. It owns a 7-port hexagonal boundary internally
(see ``k1.planner.ports``). After startup, it is cross-wired into the
Orchestrator via S6b.

Design:
  - ``startup()`` is async (creates Planner + starts background task).
  - ``shutdown()`` is async (stops Planner, cancels task).
  - ``get_agent()`` is sync (returns the Planner reference).
  - The Planner uses a ``SnapshotStateReadAdapter`` that is late-bound
    per request — no session binding at construction time.

Production adapter: will wrap ``PlannerFactory.create_production()``
  (see ``k1.planner.factory``).

References:
  - S6 (Planner) and S6b (cross-wire) in
    08_end_to_end_wiring_requirements
  - P-1..P-7 (Planner port inventory) in 05_port_adapter_mapping
  - PL-G3 (sync bus calls from async Planner) resolved by AsyncBusBridge

Exports:
  IPlannerPort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IPlannerPort(Protocol):
    """Kernel port for Planner lifecycle and access.

    Manages the shared Planner instance that runs as a background
    ``asyncio.Task``. Created in S6, cross-wired in S6b.
    """

    async def startup(
        self,
        bus: Any,
        router: Any,
        fabric: Any,
        model_hub: Any,
        bridge: Any,
    ) -> None:
        """Create and start the Planner as a background task.

        Args:
            bus: The shared ``IBus`` instance.
            router: The shared ``IMailboxRouter`` instance.
            fabric: The shared ``CapabilityFabric`` instance.
            model_hub: The shared ``ModelHub`` instance.
            bridge: The bridge client (or ``None``).
        """
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Stop the Planner and cancel its background task."""
        ...  # pragma: no cover

    def get_agent(self) -> Any:
        """Return the ``Planner`` agent instance.

        Returns:
            The live Planner agent. Used by S6b cross-wire to
            obtain the Planner's mailbox for OrchestratorAdapter.
        """
        ...  # pragma: no cover
