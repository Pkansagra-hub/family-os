"""Protocol shape tests for temporal internal ports."""

from __future__ import annotations

import inspect

from k1.temporal.ports import (
    IClockPort,
    IRoutinePort,
    ITemporalDeviceContextPort,
    ITemporalEventPort,
    ITemporalIdPort,
    ITemporalMetricsPort,
    ITemporalPolicyPort,
    ITemporalStatePort,
    ITimezonePort,
)


def test_protocol_methods_are_present() -> None:
    assert tuple(inspect.signature(IClockPort.now_utc).parameters) == ("self",)
    assert (
        "session_id" in inspect.signature(ITemporalDeviceContextPort.get_device_snapshot).parameters
    )
    assert "principal_id" in inspect.signature(ITimezonePort.candidate_for_principal).parameters
    assert "routine_id" in inspect.signature(IRoutinePort.get_window).parameters
    assert "payload" in inspect.signature(ITemporalStatePort.write_section).parameters
    assert "topic" in inspect.signature(ITemporalEventPort.publish).parameters
    assert hasattr(ITemporalIdPort, "new_anchor_id")
    assert "name" in inspect.signature(ITemporalMetricsPort.incr).parameters
    assert "consumer" in inspect.signature(ITemporalPolicyPort.allow_routine).parameters


def test_protocols_are_runtime_checkable() -> None:
    class Clock:
        def now_utc(self):  # type: ignore[no-untyped-def]
            return "2025-01-01T00:00:00+00:00"

        def monotonic_ms(self):  # type: ignore[no-untyped-def]
            return 1

    assert isinstance(Clock(), IClockPort)
