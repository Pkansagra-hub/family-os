"""Tests for OrchestratorService.hil_port wiring (E6 / M1.1).

Verifies that:
  * OrchestratorService.hil_port property exposes the injected port.
  * OrchestratorFactory threads a custom hil_port through construction.
  * Factory falls back to _NullHILAdapter when hil_port is omitted.
"""

from __future__ import annotations

from typing import Any, List

import pytest

from k1.hil.types import OverrideRequest, OverrideResponse
from k1.orchestrator.factory import OrchestratorFactory, _NullHILAdapter


class _StubHILPort:
    """Minimal IHILPort stub recording request_override calls."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: List[OverrideRequest] = []

    async def ask_clarification(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_approval(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def needs_human(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_override(self, req: OverrideRequest) -> OverrideResponse:
        self.calls.append(req)
        return OverrideResponse(
            hil_request_id=req.request_id,
            choice="override",
            timed_out=False,
        )

    async def gate_capability(self, req: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def reset_round_budget(self, caller_key: str) -> None:  # pragma: no cover
        return None

    async def shutdown(self) -> None:  # pragma: no cover
        return None


@pytest.mark.asyncio
async def test_hil_port_property_exposes_injected_port() -> None:
    stub = _StubHILPort()
    service = await OrchestratorFactory.create_for_testing(hil_port=stub)
    assert service.hil_port is stub


@pytest.mark.asyncio
async def test_factory_threads_custom_hil_port_through_construction() -> None:
    stub = _StubHILPort()
    service = await OrchestratorFactory.create_for_testing(hil_port=stub)
    # Both the service AND its constraint resolver must see the same port.
    assert service.hil_port is stub
    assert service._constraint_resolver._hil_port is stub  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_factory_uses_null_hil_adapter_when_omitted() -> None:
    service = await OrchestratorFactory.create_for_testing()
    assert isinstance(service.hil_port, _NullHILAdapter)
