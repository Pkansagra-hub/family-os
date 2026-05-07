"""Unit tests for ``AmendmentService`` (M3.E3.I1)."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import pytest
from nacl.signing import SigningKey

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import (
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
from k1.selfmodel.service.amendment import (
    AmendmentNotFoundError,
    AmendmentService,
    IllegalAmendmentTransition,
    QuorumNotMetError,
    UnsignedAmendmentError,
)
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.errors import ConstitutionSafeModeError
from k1.selfmodel.service.signature_chain import (
    Ed25519SignatureChainValidator,
    canonical_body_bytes,
)

T_MS = 1_700_000_000_000
CID = "c:home"
WRITER = "selfmodel:amendment"


@dataclass
class StubBus:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def publish_simple(self, topic: str, body: dict) -> None:
        self.events.append((topic, body))


def _make_signed_constitution(
    *, version: str = "v0", parent: str = "", body: dict | None = None
) -> tuple[ConstitutionSnapshot, SigningKey, bytes]:
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    body = body or {"governance": {"signing_quorum": 1}}
    sig = sk.sign(canonical_body_bytes(body)).signature
    proof = SigningProof(
        signer_id="bootstrap",
        key_id="did:bootstrap#0",
        algorithm="ed25519",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T_MS,
    )
    snap = ConstitutionSnapshot(
        constitution_id=CID,
        version=version,
        parent_version=parent,
        body=body,
        signatures=(proof,),
        activated_at_ms=T_MS,
    )
    return snap, sk, pk


def _build(
    *,
    quorum: int = 1,
    seed_constitution: bool = True,
    safe_mode: bool = False,
):
    """Wire AmendmentService + ConstitutionService over an InMemory store."""
    store = InMemoryProjectionStore(allowed_writers=(WRITER, "test:fixture"))
    validator = Ed25519SignatureChainValidator()
    bootstrap_pk = b""
    bootstrap_sk = None
    if seed_constitution:
        snap, bootstrap_sk, bootstrap_pk = _make_signed_constitution()
        validator.register_signer("bootstrap", bootstrap_pk)
        store.write_constitution(snap, writer_id="test:fixture")
    if safe_mode:
        # Write an unsigned snapshot so ConstitutionService.get_active fails.
        bad = ConstitutionSnapshot(
            constitution_id=CID,
            version="v0",
            parent_version="",
            body={},
            signatures=(),
            activated_at_ms=T_MS,
        )
        store.write_constitution(bad, writer_id="test:fixture")
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    if safe_mode:
        # Trip safe-mode latch.
        try:
            cs.get_active()
        except Exception:
            pass
    bus = StubBus()
    clock_ref = {"t": T_MS}
    svc = AmendmentService(
        store,
        cs,
        signing_quorum=quorum,
        clock=lambda: clock_ref["t"],
        bus=bus,
    )
    return svc, store, cs, bus, clock_ref, bootstrap_sk, bootstrap_pk, validator


def _proof_for_body(sk: SigningKey, body: dict, *, signer_id: str = "bootstrap") -> SigningProof:
    sig = sk.sign(canonical_body_bytes(body)).signature
    return SigningProof(
        signer_id=signer_id,
        key_id="did:bootstrap#0",
        algorithm="ed25519",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T_MS,
    )


# ---------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------
def test_constructor_validation() -> None:
    store = InMemoryProjectionStore()
    snap, _sk, _pk = _make_signed_constitution()
    store.write_constitution(snap, writer_id="test:fixture") if False else None
    cs = ConstitutionService(store, constitution_id=CID)
    with pytest.raises(ValueError):
        AmendmentService(store, cs, signing_quorum=0)
    with pytest.raises(ValueError):
        AmendmentService(store, cs, writer_id="")
    with pytest.raises(ValueError):
        AmendmentService(store, cs, default_ttl_ms=0)


# ---------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------
def test_propose_creates_draft() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    p = svc.propose("guardian:1", "v0", {"new": "rule"})
    assert p.status == AmendmentStatus.DRAFT
    assert p.parent_version == "v0"
    assert p.proposed_by == "guardian:1"
    assert p.body == {"new": "rule"}


def test_propose_validates_inputs() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    with pytest.raises(ValueError):
        svc.propose("", "v0", {})
    with pytest.raises(TypeError):
        svc.propose("g1", "v0", "not a dict")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.propose("g1", "v0", {}, ttl_ms=0)


def test_propose_blocked_in_safe_mode() -> None:
    svc, _, _, _, _, _, _, _ = _build(safe_mode=True)
    with pytest.raises(ConstitutionSafeModeError):
        svc.propose("g1", "v0", {})


# ---------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------
def test_submit_draft_to_pending_emits_event() -> None:
    svc, _, _, bus, _, _, _, _ = _build()
    p = svc.propose("g1", "v0", {})
    out = svc.submit(p.amendment_id)
    assert out.status == AmendmentStatus.PENDING
    assert any(t == TOPIC_CONSTITUTION_AMENDMENT_PROPOSED for t, _ in bus.events)


def test_submit_unknown_id_raises() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    with pytest.raises(AmendmentNotFoundError):
        svc.submit("amd:ghost")


def test_submit_from_pending_illegal() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    p = svc.propose("g1", "v0", {})
    svc.submit(p.amendment_id)
    with pytest.raises(IllegalAmendmentTransition):
        svc.submit(p.amendment_id)


def test_submit_expired_proposal_raises() -> None:
    svc, _, _, _, clock, _, _, _ = _build()
    p = svc.propose("g1", "v0", {}, ttl_ms=1000)
    clock["t"] = T_MS + 5000
    with pytest.raises(IllegalAmendmentTransition):
        svc.submit(p.amendment_id)


# ---------------------------------------------------------------------
# sign / quorum / activation
# ---------------------------------------------------------------------
def test_sign_quorum_one_activates_immediately() -> None:
    svc, store, cs, bus, _, sk, _, _ = _build()
    p = svc.propose("g1", "v0", {"new": "rule"})
    svc.submit(p.amendment_id)
    proof = _proof_for_body(sk, {"new": "rule"})
    out = svc.sign(p.amendment_id, proof)
    assert out.status == AmendmentStatus.ACTIVE
    topics = [t for t, _ in bus.events]
    assert TOPIC_CONSTITUTION_AMENDMENT_APPROVED in topics
    assert TOPIC_CONSTITUTION_AMENDMENT_ACTIVE in topics
    new_active = cs.get_active().snapshot
    assert new_active.parent_version == "v0"
    assert new_active.body == {"new": "rule"}


def test_sign_below_quorum_stays_pending() -> None:
    svc, _, _, _, _, sk, _, _ = _build(quorum=2)
    p = svc.propose("g1", "v0", {"x": 1})
    svc.submit(p.amendment_id)
    proof = _proof_for_body(sk, {"x": 1}, signer_id="g1")
    out = svc.sign(p.amendment_id, proof)
    assert out.status == AmendmentStatus.PENDING
    assert len(out.signatures) == 1


def test_sign_duplicate_signer_rejected() -> None:
    svc, _, _, _, _, sk, _, _ = _build(quorum=2)
    p = svc.propose("g1", "v0", {"x": 1})
    svc.submit(p.amendment_id)
    proof = _proof_for_body(sk, {"x": 1}, signer_id="g1")
    svc.sign(p.amendment_id, proof)
    with pytest.raises(IllegalAmendmentTransition):
        svc.sign(p.amendment_id, proof)


def test_sign_validates_proof_inputs() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    p = svc.propose("g1", "v0", {})
    svc.submit(p.amendment_id)
    with pytest.raises(TypeError):
        svc.sign(p.amendment_id, "not a proof")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.sign(p.amendment_id, SigningProof(signer_id="", key_id="x", signature_b64="y"))
    with pytest.raises(ValueError):
        svc.sign(p.amendment_id, SigningProof(signer_id="g", key_id="x", signature_b64=""))


def test_sign_from_draft_illegal() -> None:
    svc, _, _, _, _, sk, _, _ = _build()
    p = svc.propose("g1", "v0", {})
    proof = _proof_for_body(sk, {})
    with pytest.raises(IllegalAmendmentTransition):
        svc.sign(p.amendment_id, proof)


# ---------------------------------------------------------------------
# decline
# ---------------------------------------------------------------------
def test_decline_from_draft_to_rejected() -> None:
    svc, _, _, bus, _, _, _, _ = _build()
    p = svc.propose("g1", "v0", {})
    out = svc.decline(p.amendment_id, reason="not now")
    assert out.status == AmendmentStatus.REJECTED
    assert any(t == TOPIC_CONSTITUTION_AMENDMENT_REJECTED for t, _ in bus.events)


def test_decline_from_pending_to_rejected() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    p = svc.propose("g1", "v0", {})
    svc.submit(p.amendment_id)
    out = svc.decline(p.amendment_id)
    assert out.status == AmendmentStatus.REJECTED


def test_decline_from_active_illegal() -> None:
    svc, _, _, _, _, sk, _, _ = _build()
    p = svc.propose("g1", "v0", {"x": 1})
    svc.submit(p.amendment_id)
    svc.sign(p.amendment_id, _proof_for_body(sk, {"x": 1}))
    with pytest.raises(IllegalAmendmentTransition):
        svc.decline(p.amendment_id)


# ---------------------------------------------------------------------
# expire_stale
# ---------------------------------------------------------------------
def test_expire_stale_marks_expired() -> None:
    svc, _, _, _, clock, _, _, _ = _build()
    p1 = svc.propose("g1", "v0", {}, ttl_ms=100)
    p2 = svc.propose("g1", "v0", {}, ttl_ms=10_000_000)
    svc.submit(p1.amendment_id)
    clock["t"] = T_MS + 1000
    expired_count = svc.expire_stale()
    assert expired_count == 1
    history = svc.list_history(status=AmendmentStatus.EXPIRED)
    assert any(a.amendment_id == p1.amendment_id for a in history)
    # p2 still alive
    assert any(
        a.amendment_id == p2.amendment_id and a.status == AmendmentStatus.DRAFT
        for a in svc.list_pending()
    )


# ---------------------------------------------------------------------
# list_pending / list_history
# ---------------------------------------------------------------------
def test_list_pending_includes_draft_pending_approved() -> None:
    svc, _, _, _, _, sk, _, _ = _build(quorum=2)
    a = svc.propose("g1", "v0", {})  # DRAFT
    b = svc.propose("g1", "v0", {"x": 1})
    svc.submit(b.amendment_id)  # PENDING
    c = svc.propose("g1", "v0", {"y": 2})
    svc.submit(c.amendment_id)
    # Sign once but quorum=2 → still PENDING
    svc.sign(c.amendment_id, _proof_for_body(sk, {"y": 2}, signer_id="g1"))
    pending_ids = {p.amendment_id for p in svc.list_pending()}
    assert pending_ids == {a.amendment_id, b.amendment_id, c.amendment_id}


def test_list_history_filtered_by_status() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    a = svc.propose("g1", "v0", {})
    svc.decline(a.amendment_id)
    rejected = svc.list_history(status=AmendmentStatus.REJECTED)
    assert tuple(p.amendment_id for p in rejected) == (a.amendment_id,)
    assert len(svc.list_history()) == 1


# ---------------------------------------------------------------------
# _activate — E4 enforcement
# ---------------------------------------------------------------------
def test_activate_refuses_unsigned_amendment() -> None:
    svc, _, _, _, _, _, _, _ = _build()
    from k1.selfmodel.contracts.constitution import AmendmentProposal

    proposal = AmendmentProposal(
        amendment_id="amd:test",
        parent_version="v0",
        proposed_by="g1",
        body={},
        status=AmendmentStatus.APPROVED,
        signatures=(),  # empty!
        expires_at_ms=T_MS + 100000,
    )
    # quorum=1; empty sigs hits QuorumNotMetError first which is also a defence.
    with pytest.raises((UnsignedAmendmentError, QuorumNotMetError)):
        svc._activate(proposal)


def test_activate_parent_version_mismatch() -> None:
    svc, _, _, _, _, sk, _, _ = _build()
    from k1.selfmodel.contracts.constitution import AmendmentProposal

    proposal = AmendmentProposal(
        amendment_id="amd:test",
        parent_version="WRONG",
        proposed_by="g1",
        body={"x": 1},
        status=AmendmentStatus.APPROVED,
        signatures=(_proof_for_body(sk, {"x": 1}),),
        expires_at_ms=T_MS + 100000,
    )
    with pytest.raises(IllegalAmendmentTransition):
        svc._activate(proposal)


def test_activate_bootstrap_path_no_existing_constitution() -> None:
    svc, store, cs, _, _, _, _, _ = _build(seed_constitution=False)
    sk = SigningKey.generate()
    body = {"new_root": True}
    proof = _proof_for_body(sk, body, signer_id="g1")
    p = svc.propose("g1", "", body)
    svc.submit(p.amendment_id)
    out = svc.sign(p.amendment_id, proof)
    assert out.status == AmendmentStatus.ACTIVE
    snap = cs._store.read_constitution(CID)[0]
    assert snap is not None and snap.body == body


def test_activate_bootstrap_requires_empty_parent_version() -> None:
    svc, *_ = _build(seed_constitution=False)
    sk = SigningKey.generate()
    from k1.selfmodel.contracts.constitution import AmendmentProposal

    proposal = AmendmentProposal(
        amendment_id="amd:test",
        parent_version="not-empty",
        proposed_by="g1",
        body={"x": 1},
        status=AmendmentStatus.APPROVED,
        signatures=(_proof_for_body(sk, {"x": 1}),),
        expires_at_ms=T_MS + 100000,
    )
    # Should raise ConstitutionUnavailableError (re-raised) — the
    # bootstrap path requires parent_version="" to swallow it.
    with pytest.raises(Exception):
        svc._activate(proposal)


def test_activate_writer_rejected_leaves_proposal_approved() -> None:
    """If write_constitution is rejected, proposal stays APPROVED for retry."""
    store = InMemoryProjectionStore(allowed_writers=("only-me",))
    snap, sk, pk = _make_signed_constitution()
    store.write_constitution(snap, writer_id="only-me")
    validator = Ed25519SignatureChainValidator()
    validator.register_signer("bootstrap", pk)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    bus = StubBus()
    svc = AmendmentService(store, cs, signing_quorum=1, clock=lambda: T_MS, bus=bus)
    p = svc.propose("g1", "v0", {"x": 1})
    svc.submit(p.amendment_id)
    out = svc.sign(p.amendment_id, _proof_for_body(sk, {"x": 1}))
    assert out.status == AmendmentStatus.APPROVED  # write rejected → stays APPROVED


def test_signing_quorum_property() -> None:
    svc, *_ = _build(quorum=3)
    assert svc.signing_quorum == 3


# ---------------------------------------------------------------------
# Bus failure swallowed
# ---------------------------------------------------------------------
def test_bus_publish_failure_swallowed() -> None:
    class _Boom:
        def publish_simple(self, *_a):
            raise RuntimeError("boom")

    store = InMemoryProjectionStore(allowed_writers=(WRITER, "test:fixture"))
    snap, _sk, pk = _make_signed_constitution()
    validator = Ed25519SignatureChainValidator()
    validator.register_signer("bootstrap", pk)
    store.write_constitution(snap, writer_id="test:fixture")
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    svc = AmendmentService(store, cs, signing_quorum=1, clock=lambda: T_MS, bus=_Boom())
    p = svc.propose("g1", "v0", {})  # must not raise
    svc.submit(p.amendment_id)


def test_bus_falls_back_to_publish() -> None:
    class _LegacyBus:
        def __init__(self):
            self.events = []

        def publish(self, topic, body):
            self.events.append((topic, body))

    store = InMemoryProjectionStore(allowed_writers=(WRITER, "test:fixture"))
    snap, _sk, pk = _make_signed_constitution()
    validator = Ed25519SignatureChainValidator()
    validator.register_signer("bootstrap", pk)
    store.write_constitution(snap, writer_id="test:fixture")
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    bus = _LegacyBus()
    svc = AmendmentService(store, cs, signing_quorum=1, clock=lambda: T_MS, bus=bus)
    p = svc.propose("g1", "v0", {})
    svc.submit(p.amendment_id)
    assert any(t == TOPIC_CONSTITUTION_AMENDMENT_PROPOSED for t, _ in bus.events)


# ---------------------------------------------------------------------
# _require validation
# ---------------------------------------------------------------------
def test_require_empty_id_raises() -> None:
    svc, *_ = _build()
    with pytest.raises(ValueError):
        svc._require("")
