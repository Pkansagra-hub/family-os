"""
k1.kernel.ports.model_hub_port -- IModelHubPort (2.0.8).

Kernel-level port for LLM lifecycle management.

ModelHub is a shared stateless service created in Tier 1 (S2). It provides
LLM execution, streaming, budgeting, and model registry access. Four
consumers use it through different adapter surfaces:
  - Concierge: execute + stream_execute
  - Planner: execute only
  - Fabric: handle factory (IModelGatewayPort)
  - MemoryWriter: chat (anti-corruption via ModelHubAdapter)

Design:
  - ``startup()`` / ``shutdown()`` are async (plugin loading, connection
    pooling).
  - ``get_hub()`` is sync (returns the hub reference).
  - ``is_available()`` is sync (checks cached health state).

Production adapter: will wrap ``ModelHubFactory.create_standalone()``
  (see ``k1.model_hub.factory``).

References:
  - S2 (ModelHub Gateway) in 08_end_to_end_wiring_requirements
  - M-1..M-7 (ModelHub port inventory) in 05_port_adapter_mapping
  - B-MH-3 (IModelHubPort name collision with MemoryWriter)

Exports:
  IModelHubPort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IModelHubPort(Protocol):
    """Kernel port for LLM lifecycle and access.

    Manages the shared ModelHub instance that serves all components
    requiring LLM access. Created once during Tier 1 bootstrap (S2).
    """

    async def startup(self) -> None:
        """Initialize ModelHub: load plugins, connect providers."""
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Shutdown ModelHub: close connections, release resources."""
        ...  # pragma: no cover

    def get_hub(self) -> Any:
        """Return the ModelHub service instance.

        Returns:
            The ``ModelHub`` instance. Typed as ``Any`` until ModelHub
            ports are consolidated (see Issue 2.0.9 / B-MH-3).
        """
        ...  # pragma: no cover

    def is_available(self) -> bool:
        """Check whether at least one LLM provider is connected."""
        ...  # pragma: no cover
