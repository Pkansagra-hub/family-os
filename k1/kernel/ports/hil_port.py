"""k1.kernel.ports.hil_port -- IHILPort (E1.M1.2).

Kernel-level port for the unified Human-in-the-Loop service.

After E1, there is ONE HIL implementation: `k1.hil.service.HumanInTheLoopService`.
The previous two coordinators (`k1.concierge.protocols.hitl_coordinator.HILCoordinator`
and `k1.planner.services.hil_coordinator.HILCoordinator`) are replaced in
E4 / E5 respectively.

This Protocol declares the seven async / sync methods every HIL caller
in the kernel boundary uses. Only `k1.hil.types` is imported (types are
pure dataclasses with no service deps), so importing this module never
pulls in `k1.hil.service` -- prevents `kernel.ports -> hil.service ->
kernel.ports` cycles.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.hil.types import (
    ApprovalRequest,
    ApprovalResponse,
    CapabilityGateRequest,
    ClarificationRequest,
    ClarificationResponse,
    GateDecision,
    NeedsHumanRequest,
    NeedsHumanResponse,
    OverrideRequest,
    OverrideResponse,
)


@runtime_checkable
class IHILPort(Protocol):
    """Kernel-visible Human-in-the-Loop coordinator port."""

    async def ask_clarification(self, req: ClarificationRequest) -> ClarificationResponse: ...

    async def request_approval(self, req: ApprovalRequest) -> ApprovalResponse: ...

    async def needs_human(self, req: NeedsHumanRequest) -> NeedsHumanResponse: ...

    async def request_override(self, req: OverrideRequest) -> OverrideResponse: ...

    async def gate_capability(self, req: CapabilityGateRequest) -> GateDecision: ...

    def reset_round_budget(self, caller_key: str) -> None: ...

    async def shutdown(self) -> None: ...
