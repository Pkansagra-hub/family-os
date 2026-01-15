"""Tests for location masking for external APIs."""

from __future__ import annotations

from k0.pipelines.p03.security.location_masking import (
    MaskedLocation,
    get_safe_location_description,
    mask_for_external_api,
    should_include_location,
)


class TestMaskForExternalApi:
    """Tests for mask_for_external_api()."""

    def test_none_location_returns_none(self) -> None:
        """None location returns None."""
        result = mask_for_external_api(None, None, "GREEN")
        assert result is None

    def test_partial_none_returns_none(self) -> None:
        """Partial None location returns None."""
        result = mask_for_external_api(37.7749, None, "GREEN")
        assert result is None

    def test_green_full_precision(self) -> None:
        """GREEN band returns full precision location."""
        result = mask_for_external_api(37.7749, -122.4194, "GREEN")
        assert result is not None
        assert isinstance(result, MaskedLocation)
        assert result.band == "GREEN"
        assert len(result.geohash) == 12  # Full precision

    def test_amber_city_precision(self) -> None:
        """AMBER band returns city precision."""
        result = mask_for_external_api(37.7749, -122.4194, "AMBER")
        assert result is not None
        assert result.band == "AMBER"
        assert len(result.geohash) == 6  # City precision

    def test_red_country_precision(self) -> None:
        """RED band returns country precision."""
        result = mask_for_external_api(37.7749, -122.4194, "RED")
        assert result is not None
        assert result.band == "RED"
        assert len(result.geohash) == 4  # Country precision


class TestGetSafeLocationDescription:
    """Tests for get_safe_location_description()."""

    def test_none_location(self) -> None:
        """None location returns unknown."""
        desc = get_safe_location_description(None, None, "GREEN")
        assert desc == "unknown location"

    def test_green_specific(self) -> None:
        """GREEN band gives specific description."""
        desc = get_safe_location_description(37.7749, -122.4194, "GREEN")
        assert "coordinates" in desc or "at" in desc

    def test_amber_vague(self) -> None:
        """AMBER band gives vague description."""
        desc = get_safe_location_description(37.7749, -122.4194, "AMBER")
        assert "local area" in desc

    def test_red_very_vague(self) -> None:
        """RED band gives very vague description."""
        desc = get_safe_location_description(37.7749, -122.4194, "RED")
        assert "region" in desc


class TestShouldIncludeLocation:
    """Tests for should_include_location()."""

    def test_always_true(self) -> None:
        """Location always included (at appropriate precision)."""
        assert should_include_location("GREEN") is True
        assert should_include_location("AMBER") is True
        assert should_include_location("RED") is True
