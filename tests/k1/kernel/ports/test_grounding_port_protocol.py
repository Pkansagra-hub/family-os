"""Tests for the M0 IGroundingPort Protocol."""

from __future__ import annotations

import inspect

from k1.grounding.types import GroundingFreshness as GroundingFreshnessDirect
from k1.kernel.ports import GroundingFreshness, IGroundingPort
from k1.kernel.ports.grounding_port import IGroundingPort as IGroundingPortDirect

REQUIRED_METHODS = (
    "create_envelope",
    "build_projection",
    "build_agent_lease",
    "refresh_if_stale",
    "shutdown",
)


def test_igroundingport_is_reexported() -> None:
    assert IGroundingPort is IGroundingPortDirect
    assert GroundingFreshness is GroundingFreshnessDirect


def test_igroundingport_required_methods() -> None:
    for name in REQUIRED_METHODS:
        assert hasattr(IGroundingPort, name), f"IGroundingPort missing {name}"


def test_igroundingport_signatures() -> None:
    create_params = inspect.signature(IGroundingPort.create_envelope).parameters
    assert "session_id" in create_params
    assert "consumer" in create_params
    assert "turn_id" in create_params
    assert "trace_id" in create_params
    assert "envelope" in inspect.signature(IGroundingPort.build_projection).parameters
    lease_params = inspect.signature(IGroundingPort.build_agent_lease).parameters
    assert "task_scope" in lease_params
    assert "ttl_seconds" in lease_params


def test_igroundingport_runtime_checkable() -> None:
    class _Stub:
        async def create_envelope(self, session_id, consumer, *, turn_id=None, trace_id=None):  # type: ignore[no-untyped-def]
            ...

        async def build_projection(self, envelope, consumer):  # type: ignore[no-untyped-def]
            ...

        async def build_agent_lease(self, envelope, *, task_scope, ttl_seconds):  # type: ignore[no-untyped-def]
            ...

        async def refresh_if_stale(self, envelope):  # type: ignore[no-untyped-def]
            ...

        async def shutdown(self):  # type: ignore[no-untyped-def]
            ...

    assert isinstance(_Stub(), IGroundingPort)
