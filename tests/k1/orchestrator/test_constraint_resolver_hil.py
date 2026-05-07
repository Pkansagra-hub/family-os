"""ConstraintResolver HIL fallback tests (E6 / M1.2).

Verifies trigger_hil_fallback path with an injected stub IHILPort:
  * choice='override' (approved) -> response surfaced with choice=='override'
  * choice='abort'    (rejected) -> response surfaced with choice=='abort'
  * timed_out=True              -> response surfaced with timed_out=True
  * no hil_port wired            -> defensive timed_out abort response
"""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from k1.hil.types import OverrideRequest, OverrideResponse
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.constraint_resolver import ConstraintResolver
from k1.orchestrator.types import CapabilityCheck, CommittedPlan, PlanStep


class _StubHILPort:
    __slots__ = ("calls", "_response")

    def __init__(self, response: OverrideResponse) -> None:
        self.calls: List[OverrideRequest] = []
        self._response = response

    async def ask_clarification(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_approval(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def needs_human(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_override(self, req: OverrideRequest) -> OverrideResponse:
        self.calls.append(req)
        return self._response

    async def gate_capability(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def reset_round_budget(self, caller_key: str) -> None:  # pragma: no cover
        return None

    async def shutdown(self) -> None:  # pragma: no cover
        return None


def _plan() -> CommittedPlan:
    return CommittedPlan(
        plan_id="plan-hil",
        request_id="req-hil",
        intent="test",
        steps=[PlanStep(id="s1", capability="tool.x")],
        trace_id="trace-hil",
    )


def _unresolved() -> List[CapabilityCheck]:
    return [CapabilityCheck(step_id="s1", capability="tool.x", available=False)]


async def _resolver_with(stub: Optional[_StubHILPort]) -> ConstraintResolver:
    if stub is None:
        service = await OrchestratorFactory.create_for_testing()
    else:
        service = await OrchestratorFactory.create_for_testing(hil_port=stub)
    return service._constraint_resolver  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_trigger_hil_fallback_approved_returns_override() -> None:
    stub = _StubHILPort(
        OverrideResponse(hil_request_id="r1", choice="override", timed_out=False)
    )
    resolver = await _resolver_with(stub)

    response = await resolver.trigger_hil_fallback(_unresolved(), _plan())

    assert response.choice == "override"
    assert response.timed_out is False
    assert len(stub.calls) == 1
    assert stub.calls[0].caller_key == "orchestrator:resolver:plan-hil"


@pytest.mark.asyncio
async def test_trigger_hil_fallback_rejected_returns_abort() -> None:
    stub = _StubHILPort(
        OverrideResponse(hil_request_id="r1", choice="abort", timed_out=False)
    )
    resolver = await _resolver_with(stub)

    response = await resolver.trigger_hil_fallback(_unresolved(), _plan())

    assert response.choice == "abort"
    assert response.timed_out is False


@pytest.mark.asyncio
async def test_trigger_hil_fallback_timeout_surfaces_timed_out() -> None:
    stub = _StubHILPort(
        OverrideResponse(hil_request_id="r1", choice="override", timed_out=True)
    )
    resolver = await _resolver_with(stub)

    response = await resolver.trigger_hil_fallback(_unresolved(), _plan())

    assert response.timed_out is True


@pytest.mark.asyncio
async def test_trigger_hil_fallback_without_hil_port_returns_timed_out_abort() -> None:
    """Resolver constructed without hil_port returns defensive timed-out abort."""
    # Bypass factory: instantiate resolver with hil_port=None directly.
    service = await OrchestratorFactory.create_for_testing()
    resolver = ConstraintResolver(
        fabric=service._fabric_port,
        hil_port=None,
    )

    response = await resolver.trigger_hil_fallback(_unresolved(), _plan())

    assert response.choice == "abort"
    assert response.timed_out is True
