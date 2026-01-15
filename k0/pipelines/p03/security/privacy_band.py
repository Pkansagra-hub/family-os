"""Privacy band enforcement for P03 consolidation.

Enforces K0 privacy bands (GREEN/AMBER/RED) during consolidation
to restrict cross-event linking, actor linking, and external sharing.

This is for DEVICE deployment - controls what gets shared externally,
not multi-tenant isolation (which is unnecessary on single-device).

Dossier Reference: Section 14.2 Privacy Band Enforcement
K0 References:
- k0/policy/policy_stamp.py: PolicyStamp.band
- k0/policy/location_privacy.py: mask_location_for_band()
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from k0.policy.location_privacy import get_geohash_precision_for_band

if TYPE_CHECKING:
    pass  # Future: PolicyStamp if needed


class PrivacyBand(str, Enum):
    """Privacy bands for data classification."""

    GREEN = "GREEN"  # Full access, shareable
    AMBER = "AMBER"  # Restricted, anonymize before sharing
    RED = "RED"  # Private, never share externally


@dataclass(frozen=True)
class BandConstraints:
    """Constraints for a privacy band."""

    can_share_externally: bool  # Can send to external APIs (LLM, etc.)
    can_link_events: bool  # Can link across events
    can_include_pii: bool  # Can include PII in external calls
    location_precision: Literal["full", "city", "country"]

    @property
    def geohash_precision(self) -> int:
        """Convert location_precision to geohash precision."""
        mapping = {
            "full": 12,  # ~0.6m
            "city": 6,  # ~5km
            "country": 4,  # ~39km
        }
        return mapping[self.location_precision]


# Band constraints for device deployment (focus on external sharing)
BAND_CONSTRAINTS: dict[str, BandConstraints] = {
    "GREEN": BandConstraints(
        can_share_externally=True,
        can_link_events=True,
        can_include_pii=True,
        location_precision="full",
    ),
    "AMBER": BandConstraints(
        can_share_externally=True,
        can_link_events=True,
        can_include_pii=False,  # Must anonymize
        location_precision="city",
    ),
    "RED": BandConstraints(
        can_share_externally=False,  # Never share externally
        can_link_events=True,  # Can still link on-device
        can_include_pii=False,
        location_precision="country",
    ),
}


class PrivacyBandEnforcer:
    """Enforce K0 privacy bands for external sharing decisions.

    On-device deployment focus:
    - GREEN: Can share with external LLMs, full context
    - AMBER: Can share but must anonymize PII first
    - RED: Never share externally, on-device only
    """

    @classmethod
    def get_constraints(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> BandConstraints:
        """Get constraints for a privacy band.

        Args:
            band: Privacy band

        Returns:
            BandConstraints for the band

        Raises:
            ValueError: If band is unknown
        """
        if band not in BAND_CONSTRAINTS:
            raise ValueError(f"Invalid privacy band: {band}")
        return BAND_CONSTRAINTS[band]

    @classmethod
    def can_share_externally(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> bool:
        """Check if data with this band can be sent to external APIs.

        Args:
            band: Privacy band of the data

        Returns:
            True if shareable (GREEN/AMBER), False if RED
        """
        return cls.get_constraints(band).can_share_externally

    @classmethod
    def prepare_for_external_api(
        cls,
        data: dict[str, Any],
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> dict[str, Any] | None:
        """Prepare data for external API call based on privacy band.

        Args:
            data: Data to prepare for external sharing
            band: Privacy band of the data

        Returns:
            Prepared data (possibly anonymized), or None if RED band
        """
        constraints = cls.get_constraints(band)

        if not constraints.can_share_externally:
            return None  # RED band: do not share

        if not constraints.can_include_pii:
            # AMBER band: anonymize PII
            return cls._anonymize_data(data)

        # GREEN band: return as-is
        return data

    @classmethod
    def _anonymize_data(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Remove PII fields from data for AMBER band sharing.

        Args:
            data: Original data

        Returns:
            Anonymized copy of data
        """
        pii_fields = {
            "email",
            "phone",
            "phone_number",
            "address",
            "full_name",
            "first_name",
            "last_name",
            "ssn",
            "social_security",
            "credit_card",
            "bank_account",
            "ip_address",
            "device_id",
        }

        result = {}
        for key, value in data.items():
            if key.lower() in pii_fields:
                continue  # Skip PII fields
            if isinstance(value, dict):
                result[key] = cls._anonymize_data(value)
            elif isinstance(value, list):
                result[key] = [
                    cls._anonymize_data(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                result[key] = value

        return result

    @classmethod
    def get_location_precision(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> int:
        """Get geohash precision for external location sharing.

        Args:
            band: Privacy band

        Returns:
            Geohash precision (4=country, 6=city, 12=full)
        """
        return get_geohash_precision_for_band(band)

    @classmethod
    def can_link_events(
        cls,
        event_a_band: Literal["GREEN", "AMBER", "RED"],
        event_b_band: Literal["GREEN", "AMBER", "RED"],
    ) -> bool:
        """Check if two events can be linked on-device.

        On single-device deployment, all local linking is allowed.
        This is only for external sharing decisions.

        Args:
            event_a_band: Band of first event
            event_b_band: Band of second event

        Returns:
            True (always allowed on-device)
        """
        # On device, we can always link - it's the SHARING that's restricted
        return True

    @classmethod
    def get_effective_band(
        cls,
        bands: list[Literal["GREEN", "AMBER", "RED"]],
    ) -> Literal["GREEN", "AMBER", "RED"]:
        """Get effective band when combining multiple items.

        Uses most restrictive band (RED > AMBER > GREEN).

        Args:
            bands: List of bands to combine

        Returns:
            Most restrictive band
        """
        if not bands:
            return "GREEN"

        if "RED" in bands:
            return "RED"
        if "AMBER" in bands:
            return "AMBER"
        return "GREEN"
