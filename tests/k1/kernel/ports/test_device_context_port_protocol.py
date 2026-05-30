"""Tests for the M0 IDeviceContextPort Protocol."""

from __future__ import annotations

import inspect

from k1.grounding.types import DeviceContextSnapshot
from k1.kernel.ports import IDeviceContextPort
from k1.kernel.ports.device_context_port import IDeviceContextPort as IDeviceContextPortDirect


def test_idevicecontextport_is_reexported() -> None:
    assert IDeviceContextPort is IDeviceContextPortDirect


def test_idevicecontextport_uses_grounding_snapshot_type() -> None:
    from k1.kernel.ports.device_context_port import DeviceContextSnapshot as ReExported

    assert ReExported is DeviceContextSnapshot


def test_idevicecontextport_signatures() -> None:
    get_params = inspect.signature(IDeviceContextPort.get_snapshot).parameters
    assert "session_id" in get_params
    assert "device_id" in get_params
    assert "installation_id" in get_params
    assert "request" in inspect.signature(IDeviceContextPort.update_snapshot).parameters


def test_idevicecontextport_runtime_checkable() -> None:
    class _Stub:
        async def get_snapshot(self, session_id, device_id, installation_id):  # type: ignore[no-untyped-def]
            ...

        async def update_snapshot(self, request):  # type: ignore[no-untyped-def]
            ...

    assert isinstance(_Stub(), IDeviceContextPort)
