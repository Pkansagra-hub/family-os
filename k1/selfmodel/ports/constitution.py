"""``IConstitutionPort`` — read/diff/propose/sign constitution amendments.

Active constitution rows are immutable; the version chain is built by
``parent_version``. Implementation lands in M3
(``service/constitution.py`` + ``service/amendment.py``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConstitutionDiff,
    ConstitutionSnapshot,
    SigningProof,
)

__all__ = ["IConstitutionPort"]


@runtime_checkable
class IConstitutionPort(Protocol):
    """Constitution + amendment lifecycle surface."""

    def get_active(self) -> ConstitutionSnapshot:
        """The currently-active signed constitution."""
        ...

    def get_diff(self, constitution_id: str, version_a: str, version_b: str) -> ConstitutionDiff:
        """Diff between two versions of the same constitution."""
        ...

    def propose(
        self,
        proposed_by: str,
        parent_version: str,
        body: dict[str, object],
    ) -> AmendmentProposal:
        """Create a DRAFT amendment owned by ``proposed_by``."""
        ...

    def submit(self, amendment_id: str) -> AmendmentProposal:
        """Move DRAFT → PENDING and start the signing window."""
        ...

    def sign(self, amendment_id: str, proof: SigningProof) -> AmendmentProposal:
        """Append a signature; on quorum, transition to APPROVED → ACTIVE.

        Empty-Set Invariant E4: an amendment can only become ACTIVE with
        a valid signature chain back to the bootstrap signers.
        """
        ...

    def decline(self, amendment_id: str, reason: str = "") -> AmendmentProposal:
        """Mark a PENDING amendment as REJECTED."""
        ...

    def list_pending(self) -> tuple[AmendmentProposal, ...]:
        """Amendments currently in PENDING or CONFLICT_PENDING."""
        ...

    def list_history(self, status: AmendmentStatus | None = None) -> tuple[AmendmentProposal, ...]:
        """All amendments, optionally filtered by status."""
        ...
