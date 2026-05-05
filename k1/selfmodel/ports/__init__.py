"""Hexagonal port surface for k1.selfmodel.

7 ports: 6 ``Protocol`` (Concierge style) + 1 ``ABC`` (mutating store).
See ``docs/whiteboard/SERVICE_DESIGN_SELF_MODEL.md`` §2.
"""

from __future__ import annotations

from k1.selfmodel.ports.constitution import IConstitutionPort
from k1.selfmodel.ports.credential import ICredentialPort
from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    DeviceContext,
    IdentitySession,
    IdentityTier,
    IIdentityPort,
    ProfileSummary,
    VerificationResult,
)
from k1.selfmodel.ports.policy import IPolicyPort
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
    ProjectionRevision,
    StoreReadResult,
    StoreWriteResult,
)
from k1.selfmodel.ports.selffamily import ISelfFamilyPort
from k1.selfmodel.ports.situation import ISituationFramePort

__all__ = [
    "IIdentityPort",
    "ICredentialPort",
    "IConstitutionPort",
    "ISelfFamilyPort",
    "ISituationFramePort",
    "IPolicyPort",
    "IProjectionStorePort",
    "IdentityTier",
    "DeviceContext",
    "ProfileSummary",
    "CredentialPresentation",
    "IdentitySession",
    "VerificationResult",
    "ProjectionFreshness",
    "ProjectionRevision",
    "StoreReadResult",
    "StoreWriteResult",
]
