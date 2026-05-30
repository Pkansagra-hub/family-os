"""M3-E3 location normalization tests."""

from __future__ import annotations

import pytest

from k1.spatial.errors import InvalidLocationFixError
from k1.spatial.service import normalize_location_fix, normalize_permission_state


def test_location_normalizer_validates_coordinates_and_confidence() -> None:
    fix = normalize_location_fix(
        {"lat": 33.2, "lng": -97.1, "accuracy": 40},
        observed_at_utc="2026-05-23T01:00:00+00:00",
        permission_state="granted",
    )

    assert fix.latitude == 33.2
    assert fix.longitude == -97.1
    assert fix.confidence > 0.9
    assert fix.precision == "raw"


def test_location_normalizer_marks_unavailable_without_coordinates() -> None:
    fix = normalize_location_fix(
        None,
        observed_at_utc="2026-05-23T01:00:00+00:00",
        permission_state="unavailable",
    )

    assert fix.latitude is None
    assert fix.permission_state == "unavailable"
    assert "source_unavailable" in fix.redactions


def test_location_normalizer_rejects_invalid_latitude() -> None:
    with pytest.raises(InvalidLocationFixError):
        normalize_location_fix(
            {"latitude": 99, "longitude": -97.1},
            permission_state="granted",
        )


def test_permission_normalizer_preserves_hidden_and_denied_states() -> None:
    assert normalize_permission_state("private") == "hidden"
    assert normalize_permission_state("blocked") == "denied"
