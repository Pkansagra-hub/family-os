"""SafetyBandPolicy (E1.M1.5).

Decides whether a capability invocation requires HIL based on the
contract's safety band, explicit `requires_human_confirmation`, and
declared side effects.

Decision matrix (Decision #6 of design):
    explicit requires_human_confirmation=True  -> ASK
    explicit requires_human_confirmation=False -> ALLOW (override)
        EXCEPT: RED / CRISIS bands always ASK (cannot override down)
    requires_human_confirmation=None (inferred):
        GREEN + no side_effects                -> ALLOW
        GREEN + side_effects                   -> ASK (escalate)
        AMBER                                  -> ASK
        RED                                    -> ASK (always ask, never auto-deny)
        CRISIS                                 -> ASK (always ask, audit_only=True)

DENY is reserved for future hard-blocks (capabilities permanently
disabled by org policy). Not produced today.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from k1.hil.types import CapabilityContractView


class SafetyDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"  # reserved; not used today


_RESTRICTED_BANDS = frozenset({"RED", "CRISIS"})


class SafetyBandPolicy:
    """Pure-function policy. Stateless; safe to share across requests."""

    __slots__ = ()

    def decide(
        self, contract: CapabilityContractView, params: dict[str, Any] | None = None
    ) -> SafetyDecision:
        band = (contract.safety_band_min or "GREEN").upper()
        rhc = contract.requires_human_confirmation
        has_side_effects = bool(contract.side_effects)

        # RED / CRISIS always ask -- explicit False cannot override down.
        if band in _RESTRICTED_BANDS:
            return SafetyDecision.ASK

        # Explicit override wins for non-restricted bands.
        if rhc is True:
            return SafetyDecision.ASK
        if rhc is False:
            return SafetyDecision.ALLOW

        # Inferred path (rhc is None).
        if band == "AMBER":
            return SafetyDecision.ASK
        # band == "GREEN"
        if has_side_effects:
            return SafetyDecision.ASK
        return SafetyDecision.ALLOW

    def is_audit_only(self, contract: CapabilityContractView) -> bool:
        """True for governance-flagged outcomes (RED/CRISIS user-approved)."""
        band = (contract.safety_band_min or "GREEN").upper()
        return band in _RESTRICTED_BANDS
