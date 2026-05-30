"""Tests for TemporalFactory wiring."""

from __future__ import annotations

import pytest

from k1.temporal.factory import DuplicateTemporalPortError, TemporalFactory
from k1.temporal.kernel import TemporalServiceBundle


def test_create_standalone_returns_bundle() -> None:
    bundle = TemporalFactory.create_standalone()
    assert isinstance(bundle, TemporalServiceBundle)
    assert bundle.health().ready is True


def test_create_for_testing_returns_adapters() -> None:
    bundle, adapters = TemporalFactory.create_for_testing()
    assert isinstance(bundle, TemporalServiceBundle)
    assert "clock_port" in adapters
    assert "state_port" in adapters


def test_duplicate_port_identity_rejected() -> None:
    _bundle, adapters = TemporalFactory.create_for_testing()

    class ClockAndIdPort:
        def now_utc(self) -> str:
            return "2025-01-01T00:00:00+00:00"

        def monotonic_ms(self) -> int:
            return 0

        def new_anchor_id(self) -> str:
            return "anchor-1"

        def new_window_id(self) -> str:
            return "window-1"

        def new_resolution_id(self) -> str:
            return "resolution-1"

    duplicate = ClockAndIdPort()
    adapters["clock_port"] = duplicate
    adapters["id_port"] = duplicate
    with pytest.raises(DuplicateTemporalPortError):
        TemporalFactory.create_with_ports(**adapters)
