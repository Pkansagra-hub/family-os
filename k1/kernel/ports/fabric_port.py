"""
k1.kernel.ports.fabric_port -- IFabricPort (2.0.8).

Kernel-level port for shared and per-session Fabric lifecycle.

Two Fabric instances exist at runtime:
  - **Shared Fabric** (Tier 1, S3): uses ``NullSessionStateReaderAdapter``,
    serves Orchestrator and Planner.
  - **Per-session Fabric** (Tier 2, P3): uses real
    ``SessionStateReaderAdapter(ssm, session_id)``, serves Concierge.

Design:
  - ``create_shared()`` is async (Fabric factory is async).
  - ``create_for_session()`` is async (binds to SSM + session_id).
  - ``shutdown()`` tears down a Fabric instance.

Production adapter: will wrap ``FabricFactory.create_with_ports()`` and
  ``FabricFactory.create_shared()`` (see Issue 2.0.13).

References:
  - S3 (Shared Fabric) and P3 (Per-Session Fabric) in
    08_end_to_end_wiring_requirements
  - F-1..F-6 (Fabric port inventory) in 05_port_adapter_mapping
  - B-FAB-2 (no create_shared() method) resolved by Issue 2.0.13
  - W-FAB-2 (shared vs per-session decision) resolved by Issue 2.0.10

Exports:
  IFabricPort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IFabricPort(Protocol):
    """Kernel port for Fabric lifecycle and creation.

    Manages creation of both shared (Tier 1) and per-session (Tier 2)
    Fabric instances with correct port wiring.
    """

    async def create_shared(self, bus: Any, model_hub: Any, bridge: Any) -> Any:
        """Create shared Fabric with ``NullSessionStateReaderAdapter``.

        Args:
            bus: The shared ``IBus`` instance (wrapped in FabricBusAdapter
                for both IEventPort and IDeltaBusPort).
            model_hub: The shared ``ModelHub`` instance (wrapped in
                ModelHubGatewayAdapter).
            bridge: The bridge client (or ``None`` for offline mode).

        Returns:
            A ``CapabilityFabric`` instance.
        """
        ...  # pragma: no cover

    async def create_for_session(
        self,
        session_id: str,
        session_state: Any,
        bus: Any,
        model_hub: Any,
        bridge: Any,
    ) -> Any:
        """Create per-session Fabric bound to a specific session.

        Args:
            session_id: The session identifier.
            session_state: The ``SessionStateManager`` for this session.
            bus: The per-session ``IBus`` instance.
            model_hub: The shared ``ModelHub`` instance.
            bridge: The bridge client (or ``None`` for offline mode).

        Returns:
            A ``CapabilityFabric`` instance bound to ``session_id``.
        """
        ...  # pragma: no cover

    async def shutdown(self, fabric: Any) -> None:
        """Shutdown a Fabric instance, release resources."""
        ...  # pragma: no cover
