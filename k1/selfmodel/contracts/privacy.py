"""Privacy band re-export and bridge wire mapping.

The canonical ``PrivacyBand`` enum is defined by SessionState
(`k1.sessionstate.sections.meta`). This module re-exports it to keep
``k1.selfmodel`` consumers from reaching across components for a tiny
enum, and adds the helper that maps it to the bridge wire band string.

Empty-Set Invariant E3 says BLACK never leaves K1. The mapping helper
enforces that as defense-in-depth on top of the bridge adapter check.
"""

from __future__ import annotations

from k1.sessionstate.sections.meta import PrivacyBand

__all__ = [
    "PrivacyBand",
    "BlackBandLeakError",
    "privacy_band_to_bridge",
]


class BlackBandLeakError(RuntimeError):
    """Raised when BLACK-banded content is about to cross the K1/K0 line."""


_BAND_TO_WIRE: dict[PrivacyBand, str] = {
    PrivacyBand.GREEN: "GREEN",
    PrivacyBand.AMBER: "AMBER",
    PrivacyBand.RED: "RED",
}


def privacy_band_to_bridge(band: PrivacyBand) -> str:
    """Map a ``PrivacyBand`` to the bridge wire band literal.

    Raises ``BlackBandLeakError`` if ``band`` is ``BLACK``. BLACK content
    is K1-local only; reaching this function with BLACK is a programming
    error, not a runtime condition to recover from.
    """
    try:
        return _BAND_TO_WIRE[band]
    except KeyError as exc:
        if band is PrivacyBand.BLACK:
            raise BlackBandLeakError(
                "BLACK-banded content cannot be sent over the bridge wire"
            ) from exc
        raise
