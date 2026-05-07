"""Unit tests for ``bootstrap_constitution`` (M3.E5.I1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import ConstitutionSnapshot
from k1.selfmodel.service.bootstrap_constitution import (
    BOOTSTRAP_CONSTITUTION_ID,
    BOOTSTRAP_SIGNER_ID,
    BOOTSTRAP_VERSION,
    BOOTSTRAP_WRITER_ID,
    build_bootstrap_snapshot,
    ensure_bootstrap_constitution,
    load_bootstrap_yaml,
)
from k1.selfmodel.service.signature_chain import Ed25519SignatureChainValidator

T_MS = 1_700_000_000_000


# ---------------------------------------------------------------------
# load_bootstrap_yaml
# ---------------------------------------------------------------------
def test_load_bootstrap_yaml_from_package() -> None:
    body = load_bootstrap_yaml()
    assert body["constitution_id"] == BOOTSTRAP_CONSTITUTION_ID
    assert "governance" in body
    assert "visibility_rules" in body
    assert "autonomy_rules" in body
    assert "authority_rules" in body
    assert body["governance"]["signing_quorum"] == 1
    assert body["governance"]["bootstrap_immutable"] is True


def test_load_bootstrap_yaml_from_path(tmp_path: Path) -> None:
    p = tmp_path / "boot.yaml"
    p.write_text(
        f"""
constitution_id: {BOOTSTRAP_CONSTITUTION_ID}
governance:
  signing_quorum: 1
visibility_rules: {{}}
autonomy_rules: {{}}
authority_rules: {{}}
""",
        encoding="utf-8",
    )
    body = load_bootstrap_yaml(p)
    assert body["constitution_id"] == BOOTSTRAP_CONSTITUTION_ID


def test_load_bootstrap_yaml_rejects_non_dict(tmp_path: Path) -> None:
    p = tmp_path / "boot.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_bootstrap_yaml(p)


def test_load_bootstrap_yaml_rejects_wrong_id(tmp_path: Path) -> None:
    p = tmp_path / "boot.yaml"
    p.write_text(
        "constitution_id: wrong\ngovernance: {}\nvisibility_rules: {}\nautonomy_rules: {}\nauthority_rules: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_bootstrap_yaml(p)


def test_load_bootstrap_yaml_rejects_missing_required(tmp_path: Path) -> None:
    p = tmp_path / "boot.yaml"
    p.write_text(
        f"constitution_id: {BOOTSTRAP_CONSTITUTION_ID}\ngovernance: {{}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_bootstrap_yaml(p)


# ---------------------------------------------------------------------
# build_bootstrap_snapshot
# ---------------------------------------------------------------------
def test_build_bootstrap_snapshot_validates_signing_key() -> None:
    with pytest.raises(TypeError):
        build_bootstrap_snapshot({"a": 1}, signing_key="not a key", activated_at_ms=T_MS)  # type: ignore[arg-type]


def test_build_bootstrap_snapshot_signature_validates() -> None:
    from nacl.signing import SigningKey

    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    body = load_bootstrap_yaml()
    snap = build_bootstrap_snapshot(body, signing_key=sk, activated_at_ms=T_MS)
    assert snap.constitution_id == BOOTSTRAP_CONSTITUTION_ID
    assert snap.version == BOOTSTRAP_VERSION
    assert snap.parent_version == ""
    assert len(snap.signatures) == 1
    assert snap.signatures[0].signer_id == BOOTSTRAP_SIGNER_ID

    v = Ed25519SignatureChainValidator(min_signatures=1)
    v.register_signer(BOOTSTRAP_SIGNER_ID, pk)
    assert v.validate(snap) is True


def test_build_bootstrap_snapshot_custom_key_id() -> None:
    from nacl.signing import SigningKey

    sk = SigningKey.generate()
    snap = build_bootstrap_snapshot(
        {"a": 1}, signing_key=sk, activated_at_ms=T_MS, key_id="did:custom"
    )
    assert snap.signatures[0].key_id == "did:custom"


# ---------------------------------------------------------------------
# ensure_bootstrap_constitution
# ---------------------------------------------------------------------
def test_ensure_bootstrap_creates_row_first_time() -> None:
    store = InMemoryProjectionStore(allowed_writers=(BOOTSTRAP_WRITER_ID,))
    validator = Ed25519SignatureChainValidator(min_signatures=1)
    res = ensure_bootstrap_constitution(store, now_ms=T_MS, validator=validator, schema_version=0)
    assert res.created is True
    assert res.snapshot.constitution_id == BOOTSTRAP_CONSTITUTION_ID
    assert res.snapshot.parent_version == ""
    assert BOOTSTRAP_SIGNER_ID in validator.known_signers
    # Validator must accept the freshly written row.
    assert validator.validate(res.snapshot) is True


def test_ensure_bootstrap_is_idempotent() -> None:
    store = InMemoryProjectionStore(allowed_writers=(BOOTSTRAP_WRITER_ID,))
    res1 = ensure_bootstrap_constitution(store, now_ms=T_MS)
    assert res1.created is True
    res2 = ensure_bootstrap_constitution(store, now_ms=T_MS + 1000)
    assert res2.created is False
    assert res2.snapshot.version == res1.snapshot.version
    assert res2.snapshot.activated_at_ms == res1.snapshot.activated_at_ms


def test_ensure_bootstrap_rejects_when_writer_denied() -> None:
    # Writer-id allowlist excludes the bootstrap writer.
    store = InMemoryProjectionStore(allowed_writers=("only:me",))
    with pytest.raises(RuntimeError):
        ensure_bootstrap_constitution(store, now_ms=T_MS)


def test_ensure_bootstrap_with_existing_row_returns_unchanged() -> None:
    """Pre-existing row preserved; second call returns it as-is."""
    store = InMemoryProjectionStore(allowed_writers=(BOOTSTRAP_WRITER_ID, "test:fixture"))
    seed = ConstitutionSnapshot(
        constitution_id=BOOTSTRAP_CONSTITUTION_ID,
        version="vX",
        parent_version="",
        body={"x": 1},
        signatures=(),
        activated_at_ms=42,
    )
    store.write_constitution(seed, writer_id="test:fixture")
    res = ensure_bootstrap_constitution(store, now_ms=T_MS, schema_version=0)
    assert res.created is False
    assert res.snapshot.version == "vX"
