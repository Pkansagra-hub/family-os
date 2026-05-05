"""M0.E1.I2 — privacy band re-export and bridge mapping."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.privacy import (
    BlackBandLeakError,
    PrivacyBand,
    privacy_band_to_bridge,
)
from k1.sessionstate.sections.meta import PrivacyBand as CanonicalPrivacyBand


def test_privacy_band_is_reexport_of_canonical_enum() -> None:
    # Re-export, NOT a new enum — same identity preserves isinstance checks.
    assert PrivacyBand is CanonicalPrivacyBand


@pytest.mark.parametrize(
    ("band", "wire"),
    [
        (PrivacyBand.GREEN, "GREEN"),
        (PrivacyBand.AMBER, "AMBER"),
        (PrivacyBand.RED, "RED"),
    ],
)
def test_privacy_band_maps_to_bridge_wire_string(band: PrivacyBand, wire: str) -> None:
    assert privacy_band_to_bridge(band) == wire


def test_black_band_raises_black_band_leak_error() -> None:
    with pytest.raises(BlackBandLeakError):
        privacy_band_to_bridge(PrivacyBand.BLACK)


def test_black_band_leak_error_is_runtime_error() -> None:
    # Defense-in-depth: callers may catch RuntimeError generically.
    assert issubclass(BlackBandLeakError, RuntimeError)
