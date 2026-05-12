"""Tests for bridge.connector.adapter_verifier.CABundleAdapterVerifier."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from bridge.connector.adapter_verifier import (
    CABundleAdapterVerifier,
    _canonical_signing_payload,
)
from bridge.connector.contracts import InvalidAdapterSignatureError


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _make_bundle(tmp_path: Path, *, public_key: bytes, status: str = "active") -> Path:
    bundle_path = tmp_path / "ca_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "ca_id": "test_ca_v1",
                "ed25519_public_key": _b64url(public_key),
                "status": status,
                "valid_until": "2099-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return bundle_path


def _signed_manifest(sk: SigningKey, *, ca_id: str = "test_ca_v1") -> dict:
    base = {
        "topic": "ifl.test.v1",
        "delivery": {"transport": "mcp_stdio"},
    }
    payload = _canonical_signing_payload(base)
    sig = sk.sign(payload).signature
    base["signing"] = {
        "algorithm": "ed25519",
        "key_source": "ca_bundle",
        "ca_id": ca_id,
        "signature": _b64url(sig),
    }
    return base


def test_verifier_accepts_valid_signature(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    bundle = _make_bundle(tmp_path, public_key=sk.verify_key.encode())
    verifier = CABundleAdapterVerifier(ca_bundle_path=bundle)

    manifest = _signed_manifest(sk)
    verifier.verify(manifest)  # no raise


def test_verifier_rejects_tampered_payload(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    bundle = _make_bundle(tmp_path, public_key=sk.verify_key.encode())
    verifier = CABundleAdapterVerifier(ca_bundle_path=bundle)

    manifest = _signed_manifest(sk)
    manifest["topic"] = "ifl.tampered.v1"  # change after signing
    with pytest.raises(InvalidAdapterSignatureError):
        verifier.verify(manifest)


def test_verifier_rejects_unknown_ca(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    bundle = _make_bundle(tmp_path, public_key=sk.verify_key.encode())
    verifier = CABundleAdapterVerifier(ca_bundle_path=bundle)

    manifest = _signed_manifest(sk, ca_id="other_ca_v1")
    with pytest.raises(InvalidAdapterSignatureError, match="unknown ca_id"):
        verifier.verify(manifest)


def test_verifier_rejects_inactive_ca(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    bundle = _make_bundle(tmp_path, public_key=sk.verify_key.encode(), status="revoked")
    verifier = CABundleAdapterVerifier(ca_bundle_path=bundle)

    manifest = _signed_manifest(sk)
    with pytest.raises(InvalidAdapterSignatureError, match="not active"):
        verifier.verify(manifest)


def test_verifier_rejects_missing_signing_block_in_strict_mode(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    bundle = _make_bundle(tmp_path, public_key=sk.verify_key.encode())
    verifier = CABundleAdapterVerifier(ca_bundle_path=bundle)

    with pytest.raises(InvalidAdapterSignatureError, match="missing 'signing'"):
        verifier.verify({"topic": "ifl.unsigned.v1"})


def test_verifier_trust_unsigned_skips_check() -> None:
    verifier = CABundleAdapterVerifier(trust_unsigned=True)
    verifier.verify({"topic": "ifl.unsigned.v1"})  # no raise


def test_verifier_rejects_placeholder_public_key_when_strict(
    tmp_path: Path,
) -> None:
    """Strict mode must refuse to validate signatures against
    placeholder keys, regardless of which bundle the verifier is
    pointed at. Historically ca_bundle.json shipped with
    ``PLACEHOLDER_REPLACE_BEFORE_MS5``; now the production bundle
    carries a real dev key, so we inject a placeholder bundle
    explicitly to exercise this guard."""
    bundle = tmp_path / "ca_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "ca_id": "familyos_root_v1",
                "ed25519_public_key": "PLACEHOLDER_REPLACE_BEFORE_MS5",
                "status": "active",
                "valid_until": "2099-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    verifier = CABundleAdapterVerifier(
        ca_bundle_path=bundle, trust_unsigned=False,
    )
    sk = SigningKey.generate()
    manifest = _signed_manifest(sk, ca_id="familyos_root_v1")
    with pytest.raises(InvalidAdapterSignatureError, match="placeholder"):
        verifier.verify(manifest)


def test_verifier_payload_sha256_mismatch_fails(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    bundle = _make_bundle(tmp_path, public_key=sk.verify_key.encode())
    verifier = CABundleAdapterVerifier(ca_bundle_path=bundle)

    manifest = _signed_manifest(sk)
    manifest["signing"]["payload_sha256"] = "0" * 64
    with pytest.raises(InvalidAdapterSignatureError, match="payload_sha256"):
        verifier.verify(manifest)
