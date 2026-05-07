"""``AmendmentService`` — DRAFT→ACTIVE FSM for k1.selfmodel constitutions.

Issue M3.E3.I1.

Implements ``IConstitutionPort`` mutation surface (``propose``, ``submit``,
``sign``, ``decline``, ``list_pending``, ``list_history``).

State machine (legal transitions only — anything else raises
``IllegalAmendmentTransition``):

::

    DRAFT  -- submit() ----------> PENDING
    DRAFT  -- decline() ---------> REJECTED
    PENDING -- sign() (n<q) -----> PENDING            (more signatures needed)
    PENDING -- sign() (n>=q) ----> APPROVED  -- _activate() --> ACTIVE
    PENDING -- decline() --------> REJECTED
    PENDING -- expiry tick ------> EXPIRED
    PENDING -- sibling parent ---> CONFLICT_PENDING   (set by store; opaque here)
    APPROVED -- _activate() -----> ACTIVE             (synchronous; no external wait)
    ACTIVE -- (terminal) --------> ACTIVE
    REJECTED / EXPIRED ----------> (terminal)

Quorum (``signing_quorum``): integer threshold injected at construction.
The bootstrap V0 default is 1 (single guardian) — production raises it
via the constitution body's ``governance.signing_quorum``. We do NOT
read the body here; that's the caller's job (kernel bootstrap). The
service treats quorum as a pure parameter.

Activation policy:

When the quorum is reached, the proposal transitions PENDING→APPROVED,
then the service immediately attempts to ``_activate`` it: this writes
a fresh ``ConstitutionSnapshot`` (parent_version = current active
version) via ``IProjectionStorePort.write_constitution`` and bumps the
proposal status to ACTIVE. If the write is rejected (e.g. writer-id
denied), the proposal stays APPROVED and the caller can retry.

E4 invariant (no unsigned amendment active): ``_activate`` refuses to
write a snapshot whose ``signatures`` tuple is empty. The signature
chain validator (M3.E3.I2) is the second line of defence at READ time.

Bus events emitted (best-effort):

* ``k1.selfmodel.constitution.amendment_proposed.v1``  (DRAFT→PENDING)
* ``k1.selfmodel.constitution.amendment_approved.v1``  (PENDING→APPROVED)
* ``k1.selfmodel.constitution.amendment_active.v1``    (APPROVED→ACTIVE)
* ``k1.selfmodel.constitution.amendment_rejected.v1``  (→REJECTED)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.events.topics import (
    TOPIC_CONSTITUTION_AMENDMENT_ACTIVE,
    TOPIC_CONSTITUTION_AMENDMENT_APPROVED,
    TOPIC_CONSTITUTION_AMENDMENT_PROPOSED,
    TOPIC_CONSTITUTION_AMENDMENT_REJECTED,
)
from k1.selfmodel.ports.projection_store import IProjectionStorePort
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.errors import (
    ConstitutionSafeModeError,
    ConstitutionUnavailableError,
)

__all__ = [
    "AmendmentService",
    "AmendmentNotFoundError",
    "IllegalAmendmentTransition",
    "QuorumNotMetError",
    "UnsignedAmendmentError",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------
class AmendmentNotFoundError(LookupError):
    """Raised when ``amendment_id`` is unknown."""


class IllegalAmendmentTransition(RuntimeError):
    """Raised when a transition violates the FSM."""

    def __init__(self, amendment_id: str, from_state: AmendmentStatus, action: str) -> None:
        super().__init__(
            f"amendment {amendment_id!r}: cannot {action} from {from_state.value}"
        )
        self.amendment_id = amendment_id
        self.from_state = from_state
        self.action = action


class QuorumNotMetError(RuntimeError):
    """Raised by ``_activate`` when called below quorum (defensive)."""


class UnsignedAmendmentError(RuntimeError):
    """E4 enforcement: refuse to activate a proposal with no signatures."""


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------
ClockFn = Callable[[], int]
IdFn = Callable[[], str]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_amendment_id() -> str:
    return f"amd:{uuid.uuid4().hex}"


def _new_version() -> str:
    return f"v:{uuid.uuid4().hex[:16]}"


class AmendmentService:
    """Mutation surface over ``IProjectionStorePort`` constitution rows."""

    def __init__(
        self,
        store: IProjectionStorePort,
        constitution: ConstitutionService,
        *,
        signing_quorum: int = 1,
        writer_id: str = "selfmodel:amendment",
        default_ttl_ms: int = 7 * 24 * 60 * 60 * 1000,  # 7 days
        clock: ClockFn | None = None,
        id_factory: IdFn | None = None,
        version_factory: IdFn | None = None,
        bus=None,
    ) -> None:
        if signing_quorum <= 0:
            raise ValueError("signing_quorum must be positive")
        if not writer_id:
            raise ValueError("writer_id required")
        if default_ttl_ms <= 0:
            raise ValueError("default_ttl_ms must be positive")
        self._store = store
        self._constitution = constitution
        self._quorum = signing_quorum
        self._writer = writer_id
        self._ttl_ms = default_ttl_ms
        self._clock: ClockFn = clock or _now_ms
        self._id: IdFn = id_factory or _new_amendment_id
        self._version: IdFn = version_factory or _new_version
        self._bus = bus
        self._lock = threading.RLock()
        # In-memory index: amendment_id -> AmendmentProposal mirror of
        # the latest store state (re-read on every mutation).
        self._index: dict[str, AmendmentProposal] = {}

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    @property
    def signing_quorum(self) -> int:
        return self._quorum

    def propose(
        self,
        proposed_by: str,
        parent_version: str,
        body: dict,
        *,
        ttl_ms: int | None = None,
    ) -> AmendmentProposal:
        if not proposed_by:
            raise ValueError("proposed_by required")
        if not isinstance(body, dict):
            raise TypeError("body must be dict")
        self._constitution.ensure_writable()
        now = self._clock()
        ttl = ttl_ms if ttl_ms is not None else self._ttl_ms
        if ttl <= 0:
            raise ValueError("ttl_ms must be positive")
        proposal = AmendmentProposal(
            amendment_id=self._id(),
            parent_version=parent_version,
            proposed_by=proposed_by,
            body=dict(body),
            status=AmendmentStatus.DRAFT,
            signatures=(),
            expires_at_ms=now + ttl,
            conflict=None,
        )
        self._persist(proposal)
        return proposal

    def submit(self, amendment_id: str) -> AmendmentProposal:
        self._constitution.ensure_writable()
        with self._lock:
            current = self._require(amendment_id)
            self._check_not_expired(current)
            if current.status != AmendmentStatus.DRAFT:
                raise IllegalAmendmentTransition(
                    amendment_id, current.status, "submit"
                )
            updated = replace(current, status=AmendmentStatus.PENDING)
            self._persist(updated)
            self._publish(
                TOPIC_CONSTITUTION_AMENDMENT_PROPOSED,
                {
                    "amendment_id": amendment_id,
                    "parent_version": current.parent_version,
                    "proposed_by": current.proposed_by,
                    "expires_at_ms": current.expires_at_ms,
                    "submitted_at_ms": self._clock(),
                },
            )
            return updated

    def sign(self, amendment_id: str, proof: SigningProof) -> AmendmentProposal:
        if not isinstance(proof, SigningProof):
            raise TypeError("proof must be SigningProof")
        if not proof.signer_id or not proof.signature_b64:
            raise ValueError("proof.signer_id and signature_b64 required")
        self._constitution.ensure_writable()
        with self._lock:
            current = self._require(amendment_id)
            self._check_not_expired(current)
            if current.status not in (AmendmentStatus.PENDING, AmendmentStatus.APPROVED):
                raise IllegalAmendmentTransition(
                    amendment_id, current.status, "sign"
                )
            # Reject duplicate signer.
            if any(s.signer_id == proof.signer_id for s in current.signatures):
                raise IllegalAmendmentTransition(
                    amendment_id, current.status, "sign(duplicate_signer)"
                )
            self._store.append_signature(
                amendment_id, proof, writer_id=self._writer
            )
            current = replace(
                current,
                signatures=current.signatures + (proof,),
            )
            self._index[amendment_id] = current

            if len(current.signatures) >= self._quorum:
                approved = replace(current, status=AmendmentStatus.APPROVED)
                self._persist(approved)
                self._publish(
                    TOPIC_CONSTITUTION_AMENDMENT_APPROVED,
                    {
                        "amendment_id": amendment_id,
                        "signatures": len(approved.signatures),
                        "approved_at_ms": self._clock(),
                    },
                )
                # Attempt activation immediately. If it fails (writer
                # rejected, store error), the proposal stays APPROVED
                # and the caller can retry via ``activate`` — but we
                # don't expose a public activate hook in V0; the only
                # path to ACTIVE is reaching quorum.
                try:
                    activated = self._activate(approved)
                except (UnsignedAmendmentError, RuntimeError):
                    raise
                except Exception:
                    logger.exception(
                        "amendment.sign: activation failed for %s; left APPROVED",
                        amendment_id,
                    )
                    return approved
                return activated
            return current

    def decline(
        self, amendment_id: str, reason: str = ""
    ) -> AmendmentProposal:
        self._constitution.ensure_writable()
        with self._lock:
            current = self._require(amendment_id)
            if current.status not in (
                AmendmentStatus.DRAFT,
                AmendmentStatus.PENDING,
            ):
                raise IllegalAmendmentTransition(
                    amendment_id, current.status, "decline"
                )
            updated = replace(current, status=AmendmentStatus.REJECTED)
            self._persist(updated)
            self._publish(
                TOPIC_CONSTITUTION_AMENDMENT_REJECTED,
                {
                    "amendment_id": amendment_id,
                    "reason": reason,
                    "rejected_at_ms": self._clock(),
                },
            )
            return updated

    def list_pending(self) -> tuple[AmendmentProposal, ...]:
        with self._lock:
            return tuple(
                a
                for a in self._index.values()
                if a.status
                in (AmendmentStatus.PENDING, AmendmentStatus.DRAFT, AmendmentStatus.APPROVED)
            )

    def list_history(
        self, status: AmendmentStatus | None = None
    ) -> tuple[AmendmentProposal, ...]:
        with self._lock:
            if status is None:
                return tuple(self._index.values())
            return tuple(a for a in self._index.values() if a.status == status)

    # ------------------------------------------------------------------
    # Maintenance: expire stale proposals
    # ------------------------------------------------------------------
    def expire_stale(self) -> int:
        """Mark expired DRAFT/PENDING proposals as EXPIRED. Returns count."""
        now = self._clock()
        expired: list[str] = []
        with self._lock:
            for amd_id, proposal in list(self._index.items()):
                if proposal.status not in (
                    AmendmentStatus.DRAFT,
                    AmendmentStatus.PENDING,
                ):
                    continue
                if proposal.expires_at_ms and proposal.expires_at_ms <= now:
                    self._persist(replace(proposal, status=AmendmentStatus.EXPIRED))
                    expired.append(amd_id)
        return len(expired)

    # ------------------------------------------------------------------
    # Activation (E4 enforcement)
    # ------------------------------------------------------------------
    def _activate(self, proposal: AmendmentProposal) -> AmendmentProposal:
        if len(proposal.signatures) < self._quorum:
            raise QuorumNotMetError(
                f"amendment {proposal.amendment_id!r} has "
                f"{len(proposal.signatures)} signatures; quorum is {self._quorum}"
            )
        if not proposal.signatures:
            # Defence in depth (also caught by quorum check when q>=1).
            raise UnsignedAmendmentError(
                f"refusing to activate unsigned amendment {proposal.amendment_id!r}"
            )

        try:
            current = self._constitution.get_active()
            current_version = current.snapshot.version
            current_id = current.snapshot.constitution_id
        except ConstitutionUnavailableError:
            # Bootstrap path: activating into a fresh constitution_id.
            # Caller is responsible for setting parent_version="" in the
            # proposal in that case; if they didn't, we error loudly.
            if proposal.parent_version:
                raise
            current_version = ""
            current_id = self._constitution.constitution_id
        except ConstitutionSafeModeError:
            raise

        if proposal.parent_version != current_version:
            raise IllegalAmendmentTransition(
                proposal.amendment_id,
                proposal.status,
                f"_activate(parent_version_mismatch:expected={current_version!r},got={proposal.parent_version!r})",
            )

        snapshot = ConstitutionSnapshot(
            constitution_id=current_id,
            version=self._version(),
            parent_version=current_version,
            body=dict(proposal.body),
            signatures=proposal.signatures,
            activated_at_ms=self._clock(),
        )
        write_result = self._store.write_constitution(snapshot, writer_id=self._writer)
        if not write_result.accepted:
            logger.error(
                "amendment._activate: store rejected write for %s: %s",
                proposal.amendment_id,
                write_result.reason,
            )
            return proposal  # left in APPROVED for the caller to retry
        active = replace(proposal, status=AmendmentStatus.ACTIVE)
        self._persist(active)
        self._publish(
            TOPIC_CONSTITUTION_AMENDMENT_ACTIVE,
            {
                "amendment_id": proposal.amendment_id,
                "constitution_id": snapshot.constitution_id,
                "version": snapshot.version,
                "parent_version": snapshot.parent_version,
                "activated_at_ms": snapshot.activated_at_ms,
            },
        )
        return active

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _require(self, amendment_id: str) -> AmendmentProposal:
        if not amendment_id:
            raise ValueError("amendment_id required")
        # Refresh from store to pick up conflict markers etc.
        record = self._index.get(amendment_id)
        if record is None:
            raise AmendmentNotFoundError(amendment_id)
        return record

    def _check_not_expired(self, proposal: AmendmentProposal) -> None:
        now = self._clock()
        if proposal.expires_at_ms and proposal.expires_at_ms <= now:
            self._persist(replace(proposal, status=AmendmentStatus.EXPIRED))
            raise IllegalAmendmentTransition(
                proposal.amendment_id, AmendmentStatus.EXPIRED, "transition"
            )

    def _persist(self, proposal: AmendmentProposal) -> None:
        self._store.upsert_amendment(proposal, writer_id=self._writer)
        self._index[proposal.amendment_id] = proposal

    def _publish(self, topic: str, body: dict) -> None:
        bus = self._bus
        if bus is None:
            return
        try:
            publish_simple = getattr(bus, "publish_simple", None)
            if callable(publish_simple):
                publish_simple(topic, body)
                return
            publish = getattr(bus, "publish", None)
            if callable(publish):
                publish(topic, body)
        except Exception:
            logger.debug("amendment: bus publish failed topic=%s", topic, exc_info=True)
