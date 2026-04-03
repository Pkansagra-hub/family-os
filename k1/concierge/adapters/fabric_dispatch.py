"""
k1.concierge.adapters.fabric_dispatch -- Production adapter for IDispatchPort.

Unifies IFabricPort (LOW tier) + OrchestratorStub (MED/HIGH tier)
behind the single IDispatchPort Protocol.
"""

from __future__ import annotations

from typing import Any

from k1.concierge.orchestrator.types import AggregatedResult, TaskEnvelope
from k1.fabric.types import CapabilityRequest, CapabilityResult


class FabricDispatchAdapter:
    """Production adapter for IDispatchPort — Fabric + Orchestrator.

    LOW tier: dispatch_direct → IFabricPort.execute(CapabilityRequest)
    MED/HIGH: dispatch_envelope → OrchestratorStub.handle_task(TaskEnvelope)
    """

    def __init__(self, fabric_port: Any, orchestrator: Any = None) -> None:
        self._fabric = fabric_port
        self._orchestrator = orchestrator

    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        return await self._fabric.execute(request)

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> AggregatedResult:
        if self._orchestrator is None:
            raise RuntimeError(
                "IDispatchPort.dispatch_envelope called but no orchestrator is wired. "
                "Enable orchestrator in KernelConfig."
            )
        return await self._orchestrator.handle_task(envelope)
