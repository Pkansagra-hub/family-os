"""Constitution + amendment dataclasses (the ``C`` set).

Active constitution rows are immutable; the version chain is built by
``parent_version``. Amendments transition through the FSM defined in
``service/amendment.py`` (M3).

Empty-Set Invariant E4: an amendment can only become ACTIVE with a
valid signature chain back to the bootstrap signers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "AmendmentStatus",
    "SigningProof",
    "ConflictDescriptor",
    "AmendmentProposal",
    "ConstitutionDiff",
    "ConstitutionSnapshot",
]


class AmendmentStatus(str, Enum):
    """Lifecycle states for an amendment proposal."""

    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONFLICT_PENDING = "CONFLICT_PENDING"


@dataclass(frozen=True)
class SigningProof:
    """Detached signature over a canonical amendment body."""

    signer_id: str  # guardian profile id (NOT device id)
    key_id: str  # "did:device:<device_id>#<rotation>" form
    algorithm: str = "ed25519"
    signature_b64: str = ""
    signed_at_ms: int = 0


@dataclass(frozen=True)
class ConflictDescriptor:
    """Captures a sibling-version conflict awaiting reconciliation."""

    parent_version: str
    sibling_amendment_ids: tuple[str, ...] = field(default_factory=tuple)
    detected_at_ms: int = 0


@dataclass(frozen=True)
class AmendmentProposal:
    """A proposed change to the constitution."""

    amendment_id: str
    parent_version: str
    proposed_by: str
    body: dict[str, object] = field(default_factory=dict)
    status: AmendmentStatus = AmendmentStatus.DRAFT
    signatures: tuple[SigningProof, ...] = field(default_factory=tuple)
    expires_at_ms: int = 0
    conflict: ConflictDescriptor | None = None


@dataclass(frozen=True)
class ConstitutionDiff:
    """Structured diff between two constitution versions."""

    from_version: str
    to_version: str
    added: tuple[str, ...] = field(default_factory=tuple)
    removed: tuple[str, ...] = field(default_factory=tuple)
    changed: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConstitutionSnapshot:
    """A signed, active constitution at a specific version."""

    constitution_id: str
    version: str
    parent_version: str = ""
    body: dict[str, object] = field(default_factory=dict)
    signatures: tuple[SigningProof, ...] = field(default_factory=tuple)
    activated_at_ms: int = 0
