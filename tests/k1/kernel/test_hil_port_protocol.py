"""Tests for IHILPort Protocol (E1.M1.2)."""

from __future__ import annotations

import pytest

from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.kernel.ports import IHILPort
from k1.kernel.ports.hil_port import IHILPort as IHILPortDirect

REQUIRED_METHODS = (
    "ask_clarification",
    "request_approval",
    "needs_human",
    "request_override",
    "gate_capability",
    "reset_round_budget",
    "shutdown",
)


def test_ihilport_has_required_methods() -> None:
    for name in REQUIRED_METHODS:
        assert hasattr(IHILPort, name), f"IHILPort missing {name}"
    assert IHILPort is IHILPortDirect


def test_ihilport_runtime_checkable() -> None:
    class _Stub:
        async def ask_clarification(self, req):  # type: ignore[no-untyped-def]
            ...

        async def request_approval(self, req):  # type: ignore[no-untyped-def]
            ...

        async def needs_human(self, req):  # type: ignore[no-untyped-def]
            ...

        async def request_override(self, req):  # type: ignore[no-untyped-def]
            ...

        async def gate_capability(self, req):  # type: ignore[no-untyped-def]
            ...

        def reset_round_budget(self, caller_key):  # type: ignore[no-untyped-def]
            ...

        async def shutdown(self):  # type: ignore[no-untyped-def]
            ...

    assert isinstance(_Stub(), IHILPort)


def test_ihilport_rejects_incomplete() -> None:
    class _Incomplete:
        async def ask_clarification(self, req):  # type: ignore[no-untyped-def]
            ...

    assert not isinstance(_Incomplete(), IHILPort)


class _FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}

    async def publish(self, topic, payload):  # type: ignore[no-untyped-def]
        self.published.append((topic, payload))

    def subscribe(self, topic, handler):  # type: ignore[no-untyped-def]
        self.handlers.setdefault(topic, []).append(handler)
        return (topic, handler)

    def unsubscribe(self, handle):  # type: ignore[no-untyped-def]
        topic, handler = handle
        self.handlers.get(topic, []).remove(handler)


@pytest.mark.asyncio
async def test_humanintheloopservice_satisfies_ihilport() -> None:
    svc = HumanInTheLoopService(
        event_port=_FakeBus(),
        ledger=HILLedgerAdapter(None),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=HILConfig(),
    )
    assert isinstance(svc, IHILPort)
    await svc.shutdown()
