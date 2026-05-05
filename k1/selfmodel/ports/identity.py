"""``IIdentityPort`` — identity sessions on personal/shared devices.

See ``docs/whiteboard/SERVICE_DESIGN_SELF_MODEL.md`` §2.1 (port surface)
and the V0 Family Operating Design (whiteboard) for tier semantics.

Implementations land in M3 (``service/identity_session.py`` +
``adapters/credential_verifier.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "IdentityTier",
    "DeviceContext",
    "ProfileSummary",
    "CredentialPresentation",
    "IdentitySession",
    "VerificationResult",
    "IIdentityPort",
]


class IdentityTier(IntEnum):
    """Identity assurance tiers for a session.

    Higher tiers unlock higher-risk capabilities. See
    whiteboard §V0 Family Operating Design (Identity Tier Mechanism).
    """

    ANONYMOUS = 0
    SOFT_CLAIM = 1
    PIN_VERIFIED = 2
    STRONG_CRED = 3


@dataclass(frozen=True)
class DeviceContext:
    """Per-device runtime context the identity port needs."""

    device_id: str
    is_shared_hub: bool = False
    locale: str = ""
    last_seen_actors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProfileSummary:
    """Lightweight profile description shown in selection UIs."""

    profile_id: str
    display_name: str = ""
    role: str = ""
    age_band: str = ""
    last_seen_at_ms: int = 0


@dataclass(frozen=True)
class CredentialPresentation:
    """Caller-supplied credential to attempt a tier promotion."""

    kind: str  # "pin" | "passkey" | "webauthn" | "voice_advisory"
    payload: dict[str, object] = field(default_factory=dict)
    presented_at_ms: int = 0


@dataclass(frozen=True)
class IdentitySession:
    """Active identity session with hard TTL."""

    session_token: str
    profile_id: str
    tier: IdentityTier
    device_id: str
    issued_at_ms: int = 0
    hard_expires_at_ms: int = 0


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of presenting a credential."""

    accepted: bool
    promoted_to_tier: IdentityTier = IdentityTier.ANONYMOUS
    reason: str = ""


@runtime_checkable
class IIdentityPort(Protocol):
    """Identity session lifecycle + credential presentation."""

    def list_eligible_profiles(self, device: DeviceContext) -> tuple[ProfileSummary, ...]:
        """Profiles selectable on this device."""
        ...

    def start_session(
        self,
        profile_id: str,
        device: DeviceContext,
        proof: CredentialPresentation | None = None,
    ) -> IdentitySession:
        """Open a new identity session at the highest tier the proof permits."""
        ...

    def present_credential(
        self, session_token: str, credential: CredentialPresentation
    ) -> VerificationResult:
        """Attempt to promote an existing session to a higher tier."""
        ...

    def end_session(self, session_token: str) -> None:
        """Terminate the session and purge any per-session state."""
        ...

    def get_session_tier(self, session_token: str) -> IdentityTier:
        """Current tier; ``ANONYMOUS`` if unknown/expired."""
        ...
