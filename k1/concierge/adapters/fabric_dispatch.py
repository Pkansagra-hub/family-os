"""
k1.concierge.adapters.fabric_dispatch -- Production adapter for IDispatchPort.

Unifies IFabricPort (LOW tier) + OrchestratorStub (MED/HIGH tier)
behind the single IDispatchPort Protocol.
"""

from __future__ import annotations

from typing import Any

from k1.fabric.types import CapabilityRequest, CapabilityResult


class FabricDispatchAdapter:
    """Production adapter for IDispatchPort — Fabric + Orchestrator.

    LOW tier: dispatch_direct → IFabricPort.execute(CapabilityRequest)
    MED/HIGH: dispatch_envelope → orchestrator.handle_task(envelope)

    Also exposes ``execute()`` and ``discover_capabilities()`` as aliases so
    that legacy code can use this adapter as a drop-in until
    P4B.5 removes these bridge methods.
    """

    def __init__(self, fabric_port: Any, orchestrator: Any = None) -> None:
        self._fabric = fabric_port
        self._orchestrator = orchestrator

    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        return await self._fabric.execute(request)

    async def dispatch_envelope(self, envelope: Any) -> Any:
        if self._orchestrator is None:
            raise RuntimeError(
                "IDispatchPort.dispatch_envelope called but no orchestrator is wired. "
                "Enable orchestrator in KernelConfig."
            )
        return await self._orchestrator.handle_task(envelope)

    # -- IFabricPort compat (P4B.2 bridge, removed in P4B.5) --

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """IFabricPort.execute alias → dispatch_direct."""
        return await self.dispatch_direct(request)

    async def execute_batch(
        self, requests: list[CapabilityRequest], strategy: str = "PARALLEL"
    ) -> list[CapabilityResult]:
        """IFabricPort.execute_batch alias."""
        return [await self.dispatch_direct(r) for r in requests]

    async def discover_capabilities(
        self, intent: str = "", domain: str | None = None, **kwargs: Any
    ) -> Any:
        """IFabricPort.discover_capabilities passthrough."""
        if hasattr(self._fabric, "discover_capabilities"):
            return await self._fabric.discover_capabilities(intent, domain=domain, **kwargs)
        return {"capabilities": [], "count": 0}

    # -- IFabricPort compat (P4B.2 bridge, removed in P4B.3) --

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """IFabricPort.execute alias → dispatch_direct."""
        return await self.dispatch_direct(request)

    async def execute_batch(
        self, requests: list[CapabilityRequest], strategy: str = "PARALLEL"
    ) -> list[CapabilityResult]:
        """IFabricPort.execute_batch alias."""
        return [await self.dispatch_direct(r) for r in requests]

    async def discover_capabilities(
        self, intent: str = "", domain: str | None = None, **kwargs: Any
    ) -> Any:
        """IFabricPort.discover_capabilities passthrough."""
        if hasattr(self._fabric, "discover_capabilities"):
            return await self._fabric.discover_capabilities(intent, domain=domain, **kwargs)
        return {"capabilities": [], "count": 0}
