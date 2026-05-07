"""Unit tests for ``Ed25519SignatureChainValidator`` (M3.E3.I2)."""

from __future__ import annotations

import base64

import pytest
from nacl.signing import SigningKey

from k1.selfmodel.contracts.constitution import (
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.service.signature_chain import (
    Ed25519SignatureChainValidator,
    canonical_body_bytes,
)


T_MS = 1_700_000_000_000


def _sign(body: dict, *, signer_id: str = "g1") -> tuple[SigningProof, bytes]:
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    sig = sk.sign(canonical_body_bytes(body)).signature
    proof = SigningProof(
        signer_id=signer_id,
        key_id=f"did:device:hub#{signer_id}",
        algorithm="ed25519",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T_MS,
    )
    return proof, pk


def _snapshot(body: dict, *, version: str = "v1", parent: str = "", signatures=()) -> ConstitutionSnapshot:
    return ConstitutionSnapshot(
        constitution_id="c:home",
        version=version,
        parent_version=parent,
        body=body,
        signatures=tuple(signatures),
        activated_at_ms=T_MS,
    )


# ---------------------------------------------------------------------
# canonical_body_bytes
# ---------------------------------------------------------------------
def test_canonical_body_is_sorted_and_compact() -> None:
    out = canonical_body_bytes({"b": 2, "a": 1})
    assert out == b'{"a":1,"b":2}'


def test_canonical_body_is_deterministic_across_calls() -> None:
    body = {"z": [3, 2, 1], "a": {"y": 1, "x": 2}}
    assert canonical_body_bytes(body) == canonical_body_bytes(body)


# ---------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------
def test_constructor_validates_min_signatures() -> None:
    with pytest.raises(ValueError):
        Ed25519SignatureChainValidator(min_signatures=0)


def test_constructor_validates_max_chain_depth() -> None:
    with pytest.raises(ValueError):
        Ed25519SignatureChainValidator(max_chain_depth=0)


def test_register_signer_validates() -> None:
    v = Ed25519SignatureChainValidator()
    with pytest.raises(ValueError):
        v.register_signer("", b"x" * 32)
    with pytest.raises(ValueError):
        v.register_signer("g1", b"too short")
    with pytest.raises(ValueError):
        v.register_signer("g1", "not bytes")  # type: ignore[arg-type]


def test_register_revoke_signer_round_trip() -> None:
    v = Ed25519SignatureChainValidator()
    pk = bytes(SigningKey.generate().verify_key)
    v.register_signer("g1", pk)
    assert "g1" in v.known_signers
    v.revoke_signer("g1")
    assert "g1" not in v.known_signers


# ---------------------------------------------------------------------
# Per-snapshot validation
# ---------------------------------------------------------------------
def test_valid_single_signature_passes() -> None:
    body = {"a": 1}
    proof, pk = _sign(body)
    v = Ed25519SignatureChainValidator()
    v.register_signer("g1", pk)
    snap = _snapshot(body, signatures=(proof,))
    assert v.validate(snap) is True
    assert v(snap) is True  # __call__ alias


def test_unknown_signer_rejected() -> None:
    body = {"a": 1}
    proof, _ = _sign(body)
    v = Ed25519SignatureChainValidator()
    snap = _snapshot(body, signatures=(proof,))
    assert v.validate(snap) is False


def test_bad_signature_rejected() -> None:
    body = {"a": 1}
    _, pk = _sign(body)
    bad_proof = SigningProof(
        signer_id="g1",
        key_id="x",
        signature_b64=base64.b64encode(b"\x00" * 64).decode("ascii"),
        signed_at_ms=T_MS,
    )
    v = Ed25519SignatureChainValidator()
    v.register_signer("g1", pk)
    snap = _snapshot(body, signatures=(bad_proof,))
    assert v.validate(snap) is False


def test_non_ed25519_algorithm_skipped() -> None:
    body = {"a": 1}
    proof, pk = _sign(body)
    skipped = SigningProof(
        signer_id="g1",
        key_id="x",
        algorithm="ecdsa",
        signature_b64=proof.signature_b64,
        signed_at_ms=T_MS,
    )
    v = Ed25519SignatureChainValidator()
    v.register_signer("g1", pk)
    assert v.validate(_snapshot(body, signatures=(skipped,))) is False


def test_duplicate_signer_counts_once() -> None:
    body = {"a": 1}
    proof, pk = _sign(body)
    v = Ed25519SignatureChainValidator(min_signatures=2)
    v.register_signer("g1", pk)
    snap = _snapshot(body, signatures=(proof, proof))
    assert v.validate(snap) is False  # only one unique signer


def test_quorum_enforced() -> None:
    body = {"a": 1}
    p1, pk1 = _sign(body, signer_id="g1")
    p2, pk2 = _sign(body, signer_id="g2")
    v = Ed25519SignatureChainValidator(min_signatures=2)
    v.register_signer("g1", pk1)
    v.register_signer("g2", pk2)
    assert v.validate(_snapshot(body, signatures=(p1, p2))) is True
    assert v.validate(_snapshot(body, signatures=(p1,))) is False


def test_empty_signatures_rejected() -> None:
    v = Ed25519SignatureChainValidator()
    assert v.validate(_snapshot({"a": 1}, signatures=())) is False


def test_validate_rejects_non_snapshot() -> None:
    v = Ed25519SignatureChainValidator()
    assert v.validate("not a snapshot") is False  # type: ignore[arg-type]


def test_malformed_signature_b64_skipped() -> None:
    body = {"a": 1}
    _, pk = _sign(body)
    bad = SigningProof(
        signer_id="g1",
        key_id="x",
        signature_b64="!!!not-b64!!!",
        signed_at_ms=T_MS,
    )
    v = Ed25519SignatureChainValidator()
    v.register_signer("g1", pk)
    assert v.validate(_snapshot(body, signatures=(bad,))) is False


def test_non_signingproof_in_signatures_skipped() -> None:
    body = {"a": 1}
    proof, pk = _sign(body)
    v = Ed25519SignatureChainValidator()
    v.register_signer("g1", pk)
    snap = _snapshot(body, signatures=("garbage", proof))  # type: ignore[arg-type]
    assert v.validate(snap) is True


# ---------------------------------------------------------------------
# Chain walking
# ---------------------------------------------------------------------
def test_chain_walk_validates_ancestor() -> None:
    body_root = {"x": 1}
    body_child = {"x": 2}
    proot, pk = _sign(body_root)
    pchild = SigningProof(
        signer_id="g1",
        key_id="x",
        signature_b64=base64.b64encode(
            SigningKey(bytes(SigningKey.generate()._signing_key[:32])).sign(
                canonical_body_bytes(body_child)
            ).signature
        ).decode("ascii"),
        signed_at_ms=T_MS,
    )
    # Easier: re-sign child with same key as root.
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    proot = SigningProof(
        signer_id="g1",
        key_id="x",
        signature_b64=base64.b64encode(sk.sign(canonical_body_bytes(body_root)).signature).decode("ascii"),
        signed_at_ms=T_MS,
    )
    pchild = SigningProof(
        signer_id="g1",
        key_id="x",
        signature_b64=base64.b64encode(sk.sign(canonical_body_bytes(body_child)).signature).decode("ascii"),
        signed_at_ms=T_MS,
    )
    root = _snapshot(body_root, version="v0", parent="", signatures=(proot,))
    child = _snapshot(body_child, version="v1", parent="v0", signatures=(pchild,))

    parents = {("c:home", "v0"): root}

    v = Ed25519SignatureChainValidator(parent_lookup=lambda cid, ver: parents.get((cid, ver)))
    v.register_signer("g1", pk)
    assert v.validate(child) is True


def test_chain_walk_missing_parent_rejects() -> None:
    body = {"a": 1}
    proof, pk = _sign(body)
    snap = _snapshot(body, version="v1", parent="v0", signatures=(proof,))
    v = Ed25519SignatureChainValidator(parent_lookup=lambda *_: None)
    v.register_signer("g1", pk)
    assert v.validate(snap) is False


def test_chain_walk_no_lookup_accepts_after_one_row() -> None:
    body = {"a": 1}
    proof, pk = _sign(body)
    snap = _snapshot(body, version="v1", parent="v0-some-old", signatures=(proof,))
    v = Ed25519SignatureChainValidator()  # no parent_lookup
    v.register_signer("g1", pk)
    assert v.validate(snap) is True


def test_chain_cycle_detected() -> None:
    body = {"a": 1}
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)

    def proof_for(b):
        return SigningProof(
            signer_id="g1",
            key_id="x",
            signature_b64=base64.b64encode(sk.sign(canonical_body_bytes(b)).signature).decode("ascii"),
            signed_at_ms=T_MS,
        )

    a = _snapshot(body, version="v1", parent="v2", signatures=(proof_for(body),))
    b_snap = _snapshot(body, version="v2", parent="v1", signatures=(proof_for(body),))
    parents = {("c:home", "v1"): a, ("c:home", "v2"): b_snap}
    v = Ed25519SignatureChainValidator(parent_lookup=lambda cid, ver: parents.get((cid, ver)))
    v.register_signer("g1", pk)
    assert v.validate(a) is False


def test_chain_max_depth_enforced() -> None:
    body = {"a": 1}
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)

    def proof_for(b):
        return SigningProof(
            signer_id="g1",
            key_id="x",
            signature_b64=base64.b64encode(sk.sign(canonical_body_bytes(b)).signature).decode("ascii"),
            signed_at_ms=T_MS,
        )

    # Build a long chain v0 <- v1 <- v2 ... v10, but max_chain_depth=3.
    snaps = {}
    last = ""
    for i in range(11):
        ver = f"v{i}"
        snaps[ver] = _snapshot(body, version=ver, parent=last, signatures=(proof_for(body),))
        last = ver
    parents = {("c:home", k): s for k, s in snaps.items()}
    v = Ed25519SignatureChainValidator(
        parent_lookup=lambda cid, ver: parents.get((cid, ver)),
        max_chain_depth=3,
    )
    v.register_signer("g1", pk)
    assert v.validate(snaps["v10"]) is False
