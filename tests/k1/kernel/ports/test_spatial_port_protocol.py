"""Tests for the M0 ISpatialPort Protocol."""

from __future__ import annotations

import inspect

from k1.kernel.ports import ISpatialPort, LocationFix
from k1.kernel.ports.spatial_port import ISpatialPort as ISpatialPortDirect
from k1.spatial.types import LocationFix as LocationFixDirect

REQUIRED_METHODS = (
    "get_context",
    "resolve_place",
    "build_projection",
    "refresh_turn",
    "shutdown",
)


def test_ispatialport_is_reexported() -> None:
    assert ISpatialPort is ISpatialPortDirect
    assert LocationFix is LocationFixDirect


def test_ispatialport_required_methods() -> None:
    for name in REQUIRED_METHODS:
        assert hasattr(ISpatialPort, name), f"ISpatialPort missing {name}"


def test_ispatialport_signatures() -> None:
    assert "session_id" in inspect.signature(ISpatialPort.get_context).parameters
    resolve_params = inspect.signature(ISpatialPort.resolve_place).parameters
    assert "session_id" in resolve_params
    assert "text" in resolve_params
    assert "subject_ref" in resolve_params
    assert "consumer" in inspect.signature(ISpatialPort.build_projection).parameters
    refresh_params = inspect.signature(ISpatialPort.refresh_turn).parameters
    assert "turn_id" in refresh_params
    assert "trace_id" in refresh_params


def test_ispatialport_runtime_checkable() -> None:
    class _Stub:
        async def get_context(self, session_id):  # type: ignore[no-untyped-def]
            ...

        async def resolve_place(self, session_id, text, *, subject_ref=None):  # type: ignore[no-untyped-def]
            ...

        async def build_projection(self, session_id, consumer):  # type: ignore[no-untyped-def]
            ...

        async def refresh_turn(self, session_id, *, turn_id=None, trace_id=None):  # type: ignore[no-untyped-def]
            ...

        async def shutdown(self):  # type: ignore[no-untyped-def]
            ...

    assert isinstance(_Stub(), ISpatialPort)
