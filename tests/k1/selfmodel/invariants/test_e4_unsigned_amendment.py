"""Empty-Set Invariant E4: no unsigned amendment ever becomes ACTIVE.

This invariant has two layers of defence:

1. ``AmendmentService._activate`` refuses to write a snapshot whose
   ``signatures`` tuple is empty, AND refuses to write below quorum.
2. ``ConstitutionService.get_active`` (with the M3 production
   ``Ed25519SignatureChainValidator``) refuses to return a snapshot
   that fails signature validation, latching the service into safe-mode.

If either of these fails, a corrupt or coerced peer could install an
unsigned constitution and unlock arbitrary capabilities. So we keep
both fences green.
"""

from __future__ import annotations

import base64

import pytest
from nacl.signing import SigningKey

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.service.amendment import (
    AmendmentService,
    QuorumNotMetError,
    UnsignedAmendmentError,
)
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.errors import (
    ConstitutionSafeModeError,
    ConstitutionUnavailableError,
)
from k1.selfmodel.service.signature_chain import (
    Ed25519SignatureChainValidator,
    canonical_body_bytes,
)

pytestmark = pytest.mark.invariant


T_MS = 1_700_000_000_000
CID = "c:home"


def _make_signed(body: dict, *, version: str = "v0", parent: str = ""):
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    sig = sk.sign(canonical_body_bytes(body)).signature
    proof = SigningProof(
        signer_id="g1",
        key_id="x",
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


# ---------------------------------------------------------------------
# Layer 1: AmendmentService._activate refuses unsigned proposals
# ---------------------------------------------------------------------
def test_e4_amendment_service_refuses_unsigned_proposal() -> None:
    store = InMemoryProjectionStore(allowed_writers=("selfmodel:amendment", "test:fixture"))
    snap, _, pk = _make_signed({"x": 1})
    store.write_constitution(snap, writer_id="test:fixture")
    validator = Ed25519SignatureChainValidator()
    validator.register_signer("g1", pk)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    svc = AmendmentService(store, cs, signing_quorum=1, clock=lambda: T_MS)

    unsigned = AmendmentProposal(
        amendment_id="amd:evil",
        parent_version="v0",
        proposed_by="attacker",
        body={"hijack": True},
        status=AmendmentStatus.APPROVED,
        signatures=(),
        expires_at_ms=T_MS + 100000,
    )
    with pytest.raises((UnsignedAmendmentError, QuorumNotMetError)):
        svc._activate(unsigned)
    # Confirm the constitution row was NOT replaced.
    cur, _ = store.read_constitution(CID)
    assert cur.body == {"x": 1}


def test_e4_amendment_service_refuses_below_quorum() -> None:
    store = InMemoryProjectionStore(allowed_writers=("selfmodel:amendment", "test:fixture"))
    snap, _, pk = _make_signed({"x": 1})
    store.write_constitution(snap, writer_id="test:fixture")
    validator = Ed25519SignatureChainValidator()
    validator.register_signer("g1", pk)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    svc = AmendmentService(store, cs, signing_quorum=3, clock=lambda: T_MS)

    one_sig = AmendmentProposal(
        amendment_id="amd:half",
        parent_version="v0",
        proposed_by="g1",
        body={"x": 2},
        status=AmendmentStatus.APPROVED,
        signatures=(
            SigningProof(signer_id="g1", key_id="x", signature_b64="QUFB", signed_at_ms=T_MS),
        ),
        expires_at_ms=T_MS + 100000,
    )
    with pytest.raises(QuorumNotMetError):
        svc._activate(one_sig)


# ---------------------------------------------------------------------
# Layer 2: ConstitutionService rejects unsigned active row at READ time
# ---------------------------------------------------------------------
def test_e4_constitution_service_refuses_unsigned_active_row_with_real_validator() -> None:
    store = InMemoryProjectionStore(allowed_writers=("test:fixture",))
    bad = ConstitutionSnapshot(
        constitution_id=CID,
        version="v0",
        parent_version="",
        body={"hijack": True},
        signatures=(),
        activated_at_ms=T_MS,
    )
    store.write_constitution(bad, writer_id="test:fixture")
    validator = Ed25519SignatureChainValidator(min_signatures=1)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)

    with pytest.raises(ConstitutionUnavailableError):
        cs.get_active()
    assert cs.is_safe_mode is True
    # Subsequent ensure_writable() must raise ConstitutionSafeModeError
    # so amendment writes are blocked.
    with pytest.raises(ConstitutionSafeModeError):
        cs.ensure_writable()


def test_e4_constitution_service_refuses_when_signer_revoked() -> None:
    """Even a previously-valid row becomes unavailable if signer revoked."""
    store = InMemoryProjectionStore(allowed_writers=("test:fixture",))
    snap, _, pk = _make_signed({"x": 1})
    store.write_constitution(snap, writer_id="test:fixture")
    validator = Ed25519SignatureChainValidator(min_signatures=1)
    validator.register_signer("g1", pk)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    # Validator accepts initially.
    assert cs.get_active().snapshot.body == {"x": 1}
    # Revoke the signer; new ConstitutionService must trip safe-mode.
    validator.revoke_signer("g1")
    cs2 = ConstitutionService(store, constitution_id=CID, validator=validator)
    with pytest.raises(ConstitutionUnavailableError):
        cs2.get_active()


# ---------------------------------------------------------------------
# Combined: end-to-end happy path doesn't bypass the invariant
# ---------------------------------------------------------------------
def test_e4_signed_quorum_activation_succeeds() -> None:
    """Sanity check: a properly-signed amendment activates."""
    store = InMemoryProjectionStore(allowed_writers=("selfmodel:amendment", "test:fixture"))
    snap, sk, pk = _make_signed({"x": 1})
    store.write_constitution(snap, writer_id="test:fixture")
    validator = Ed25519SignatureChainValidator()
    validator.register_signer("g1", pk)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    svc = AmendmentService(store, cs, signing_quorum=1, clock=lambda: T_MS)

    p = svc.propose("g1", "v0", {"x": 2})
    svc.submit(p.amendment_id)
    sig = sk.sign(canonical_body_bytes({"x": 2})).signature
    proof = SigningProof(
        signer_id="g1",
        key_id="x",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T_MS,
    )
    out = svc.sign(p.amendment_id, proof)
    assert out.status == AmendmentStatus.ACTIVE
    new_active = cs.get_active().snapshot
    assert new_active.body == {"x": 2}
    assert new_active.signatures  # non-empty
