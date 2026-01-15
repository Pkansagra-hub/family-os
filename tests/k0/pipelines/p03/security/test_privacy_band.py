"""Tests for PrivacyBandEnforcer.

Verifies privacy band enforcement for external sharing.
"""

from __future__ import annotations

import pytest

from k0.pipelines.p03.security.privacy_band import PrivacyBand, PrivacyBandEnforcer


class TestBandConstraints:
    """Tests for BAND_CONSTRAINTS configuration."""

    def test_green_allows_external_sharing(self) -> None:
        """GREEN band allows external sharing with PII."""
        constraints = PrivacyBandEnforcer.get_constraints("GREEN")
        assert constraints.can_share_externally is True
        assert constraints.can_include_pii is True
        assert constraints.can_link_events is True
        assert constraints.location_precision == "full"

    def test_amber_allows_sharing_no_pii(self) -> None:
        """AMBER band allows sharing but must anonymize."""
        constraints = PrivacyBandEnforcer.get_constraints("AMBER")
        assert constraints.can_share_externally is True
        assert constraints.can_include_pii is False
        assert constraints.location_precision == "city"

    def test_red_blocks_external_sharing(self) -> None:
        """RED band blocks all external sharing."""
        constraints = PrivacyBandEnforcer.get_constraints("RED")
        assert constraints.can_share_externally is False
        assert constraints.can_include_pii is False
        assert constraints.location_precision == "country"

    def test_invalid_band_raises(self) -> None:
        """Invalid band raises ValueError."""
        with pytest.raises(ValueError, match="Invalid privacy band"):
            PrivacyBandEnforcer.get_constraints("INVALID")  # type: ignore

    def test_geohash_precision_mapping(self) -> None:
        """Verify geohash precision for each band."""
        assert PrivacyBandEnforcer.get_constraints("GREEN").geohash_precision == 12
        assert PrivacyBandEnforcer.get_constraints("AMBER").geohash_precision == 6
        assert PrivacyBandEnforcer.get_constraints("RED").geohash_precision == 4


class TestCanShareExternally:
    """Tests for can_share_externally()."""

    def test_green_can_share(self) -> None:
        """GREEN allows external sharing."""
        assert PrivacyBandEnforcer.can_share_externally("GREEN") is True

    def test_amber_can_share(self) -> None:
        """AMBER allows external sharing (anonymized)."""
        assert PrivacyBandEnforcer.can_share_externally("AMBER") is True

    def test_red_cannot_share(self) -> None:
        """RED blocks external sharing."""
        assert PrivacyBandEnforcer.can_share_externally("RED") is False


class TestPrepareForExternalApi:
    """Tests for prepare_for_external_api()."""

    def test_green_returns_full_data(self) -> None:
        """GREEN returns data unchanged."""
        data = {"name": "John", "email": "john@example.com", "content": "Hello"}
        result = PrivacyBandEnforcer.prepare_for_external_api(data, "GREEN")
        assert result == data

    def test_amber_anonymizes_pii(self) -> None:
        """AMBER removes PII fields."""
        data = {"name": "John", "email": "john@example.com", "content": "Hello"}
        result = PrivacyBandEnforcer.prepare_for_external_api(data, "AMBER")
        assert result is not None
        assert "email" not in result
        assert result["name"] == "John"  # name is kept, it's not in PII list
        assert result["content"] == "Hello"

    def test_red_returns_none(self) -> None:
        """RED returns None (do not share)."""
        data = {"name": "John", "content": "Hello"}
        result = PrivacyBandEnforcer.prepare_for_external_api(data, "RED")
        assert result is None

    def test_amber_anonymizes_nested(self) -> None:
        """AMBER handles nested structures."""
        data = {
            "user": {"email": "test@example.com", "role": "admin"},
            "items": [{"phone": "123", "value": 100}],
        }
        result = PrivacyBandEnforcer.prepare_for_external_api(data, "AMBER")
        assert result is not None
        assert "email" not in result["user"]
        assert result["user"]["role"] == "admin"
        assert "phone" not in result["items"][0]
        assert result["items"][0]["value"] == 100


class TestCanLinkEvents:
    """Tests for can_link_events()."""

    def test_on_device_always_allows_linking(self) -> None:
        """On-device linking is always allowed (any band)."""
        # This is intentional - on device we can link anything
        # The restriction is on SHARING, not linking
        assert PrivacyBandEnforcer.can_link_events("GREEN", "GREEN") is True
        assert PrivacyBandEnforcer.can_link_events("AMBER", "AMBER") is True
        assert PrivacyBandEnforcer.can_link_events("RED", "RED") is True
        assert PrivacyBandEnforcer.can_link_events("GREEN", "RED") is True


class TestGetEffectiveBand:
    """Tests for get_effective_band()."""

    def test_empty_returns_green(self) -> None:
        """Empty list returns GREEN (most permissive)."""
        assert PrivacyBandEnforcer.get_effective_band([]) == "GREEN"

    def test_all_green_returns_green(self) -> None:
        """All GREEN returns GREEN."""
        assert PrivacyBandEnforcer.get_effective_band(["GREEN", "GREEN"]) == "GREEN"

    def test_any_red_returns_red(self) -> None:
        """Any RED returns RED (most restrictive)."""
        assert PrivacyBandEnforcer.get_effective_band(["GREEN", "RED"]) == "RED"
        assert PrivacyBandEnforcer.get_effective_band(["AMBER", "RED"]) == "RED"

    def test_amber_without_red_returns_amber(self) -> None:
        """AMBER without RED returns AMBER."""
        assert PrivacyBandEnforcer.get_effective_band(["GREEN", "AMBER"]) == "AMBER"


class TestPrivacyBandEnum:
    """Tests for PrivacyBand enum."""

    def test_enum_values(self) -> None:
        """Verify enum values."""
        assert PrivacyBand.GREEN.value == "GREEN"
        assert PrivacyBand.AMBER.value == "AMBER"
        assert PrivacyBand.RED.value == "RED"
