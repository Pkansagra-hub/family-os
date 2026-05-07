"""``ConstitutionService`` — read path (M1) for the active constitution.

Issue M1.E1.I3.

Responsibilities in M1:

- Load the active ``ConstitutionSnapshot`` from the projection store.
- Optionally validate the signature chain via an injected validator
  (the M1 stub is a no-op; the real Ed25519 validator lands in M3).
- If the chain validation fails, the service enters **safe-mode**:
  reads keep working but ``ensure_writable()`` raises
  ``ConstitutionSafeModeError``. M3's ``AmendmentService`` consults
  ``ensure_writable()`` before any state-mutating call.

The amendment lifecycle (DRAFT → PENDING → APPROVED → ACTIVE) is M3
work and is intentionally NOT implemented here.

Empty-Set Invariants this service is responsible for:

- **E4 (no unsigned amendment active):** when the validator returns
  False, the service does NOT return the unverified snapshot to
  callers; it raises ``ConstitutionUnavailableError``. (Reads of a
  *previously valid* snapshot still work — safe-mode is about refusing
  *future writes*, not about hiding the active row.)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from k1.selfmodel.contracts.constitution import (
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
)
from k1.selfmodel.service.errors import (
    ConstitutionSafeModeError,
    ConstitutionUnavailableError,
)

__all__ = [
    "ConstitutionService",
    "ConstitutionReadResult",
    "SignatureChainValidator",
    "stub_signature_validator",
]


logger = logging.getLogger(__name__)


#: Validator signature: takes the snapshot and returns ``True`` iff the
#: signature chain validates back to the bootstrap signers. The M1 stub
#: returns ``True`` for any non-empty signatures tuple; the real M3
#: implementation runs Ed25519 verification + chain replay.
SignatureChainValidator = Callable[[ConstitutionSnapshot], bool]


def stub_signature_validator(snapshot: ConstitutionSnapshot) -> bool:
    """Permissive M1 validator.

    Treats any snapshot with at least one signature as valid; treats a
    snapshot with no signatures as invalid (so the bootstrap path with
    a synthetic system signature still validates, but a tampered row
    with the signatures stripped does not).
    """
    return len(snapshot.signatures) > 0


class ConstitutionReadResult:
    """Composite result: snapshot + freshness + safe-mode flag."""

    __slots__ = ("snapshot", "freshness", "safe_mode")

    def __init__(
        self,
        snapshot: ConstitutionSnapshot,
        *,
        freshness: ProjectionFreshness,
        safe_mode: bool,
    ) -> None:
        self.snapshot = snapshot
        self.freshness = freshness
        self.safe_mode = safe_mode

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"ConstitutionReadResult(version={self.snapshot.version!r}, "
            f"freshness={self.freshness.value}, safe_mode={self.safe_mode})"
        )


class ConstitutionService:
    """Read-only service over the active constitution row."""

    def __init__(
        self,
        store: IProjectionStorePort,
        constitution_id: str,
        *,
        validator: SignatureChainValidator | None = None,
    ) -> None:
        if not constitution_id:
            raise ValueError("constitution_id must be non-empty")
        self._store = store
        self._constitution_id = constitution_id
        self._validator: SignatureChainValidator = validator or stub_signature_validator
        self._lock = threading.RLock()
        self._safe_mode = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def constitution_id(self) -> str:
        return self._constitution_id

    @property
    def is_safe_mode(self) -> bool:
        with self._lock:
            return self._safe_mode

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_active(self) -> ConstitutionReadResult:
        """Read + validate the active constitution row.

        Raises ``ConstitutionUnavailableError`` if the row does not
        exist OR the signature chain does not validate. Sets safe-mode
        in the latter case.
        """
        snapshot, result = self._store.read_constitution(self._constitution_id)
        if snapshot is None:
            raise ConstitutionUnavailableError(
                f"no constitution row in store for id={self._constitution_id!r}"
            )

        if not self._validator(snapshot):
            with self._lock:
                self._safe_mode = True
            logger.error(
                "constitution_service.get_active: signature validation FAILED "
                "for id=%s version=%s; entering safe-mode",
                self._constitution_id,
                snapshot.version,
            )
            raise ConstitutionUnavailableError(
                f"signature chain invalid for {self._constitution_id!r} "
                f"version={snapshot.version!r}"
            )

        with self._lock:
            # Successful validation clears any prior safe-mode latch.
            self._safe_mode = False
        return ConstitutionReadResult(snapshot, freshness=result.freshness, safe_mode=False)

    # ------------------------------------------------------------------
    # Write-side gate (used by M3 amendment service)
    # ------------------------------------------------------------------
    def ensure_writable(self) -> None:
        """Raise ``ConstitutionSafeModeError`` if amendments are blocked."""
        with self._lock:
            if self._safe_mode:
                raise ConstitutionSafeModeError(
                    f"constitution {self._constitution_id!r} is in safe-mode; "
                    "amendments rejected until signature chain is repaired"
                )

    def freshness(self) -> ProjectionFreshness:
        return self._store.freshness(f"constitution:{self._constitution_id}")


# ---------------------------------------------------------------------
# Re-exports for downstream test fixtures
# ---------------------------------------------------------------------
__all__ += ["SigningProof"]
