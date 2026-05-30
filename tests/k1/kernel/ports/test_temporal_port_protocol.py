"""Tests for the M0 ITemporalPort Protocol."""

from __future__ import annotations

import inspect

from k1.kernel.ports import ITemporalPort, TemporalAnchor
from k1.kernel.ports.temporal_port import ITemporalPort as ITemporalPortDirect
from k1.temporal.types import TemporalAnchor as TemporalAnchorDirect

REQUIRED_METHODS = (
    "get_anchor",
    "get_windows",
    "resolve_expression",
    "build_projection",
    "refresh_turn",
    "shutdown",
)


def test_itemporalport_is_reexported() -> None:
    assert ITemporalPort is ITemporalPortDirect
    assert TemporalAnchor is TemporalAnchorDirect


def test_itemporalport_required_methods() -> None:
    for name in REQUIRED_METHODS:
        assert hasattr(ITemporalPort, name), f"ITemporalPort missing {name}"


def test_itemporalport_signatures() -> None:
    assert "session_id" in inspect.signature(ITemporalPort.get_anchor).parameters
    assert "session_id" in inspect.signature(ITemporalPort.get_windows).parameters
    resolve_params = inspect.signature(ITemporalPort.resolve_expression).parameters
    assert "session_id" in resolve_params
    assert "text" in resolve_params
    assert "subject_ref" in resolve_params
    assert "consumer" in inspect.signature(ITemporalPort.build_projection).parameters
    refresh_params = inspect.signature(ITemporalPort.refresh_turn).parameters
    assert "turn_id" in refresh_params
    assert "trace_id" in refresh_params


def test_itemporalport_runtime_checkable() -> None:
    class _Stub:
        async def get_anchor(self, session_id):  # type: ignore[no-untyped-def]
            ...

        async def get_windows(self, session_id):  # type: ignore[no-untyped-def]
            ...

        async def resolve_expression(self, session_id, text, *, intent=None, subject_ref=None):  # type: ignore[no-untyped-def]
            ...

        async def build_projection(self, session_id, consumer):  # type: ignore[no-untyped-def]
            ...

        async def refresh_turn(self, session_id, *, turn_id=None, trace_id=None, candidates=()):  # type: ignore[no-untyped-def]
            ...

        async def shutdown(self):  # type: ignore[no-untyped-def]
            ...

    assert isinstance(_Stub(), ITemporalPort)
