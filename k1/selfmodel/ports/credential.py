"""``ICredentialPort`` — verify credentials presented to ``IIdentityPort``.

The verifier is the only place cryptographic checks live. Production
implementation in M3 (``adapters/credential_verifier.py`` —
``Ed25519CredentialVerifier``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    IdentityTier,
    VerificationResult,
)

__all__ = ["ICredentialPort"]


@runtime_checkable
class ICredentialPort(Protocol):
    """Verify a credential against a profile and return the tier it grants."""

    def verify(
        self,
        profile_id: str,
        credential: CredentialPresentation,
    ) -> VerificationResult:
        """Verify the credential. Constant-time comparison required.

        Returns a ``VerificationResult`` with ``accepted=False`` and a
        ``reason`` string for any failure (wrong PIN, replay, malformed,
        unknown profile).
        """
        ...

    def max_tier_for(self, kind: str) -> IdentityTier:
        """Static ceiling for a credential kind (independent of payload)."""
        ...
