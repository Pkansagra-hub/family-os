"""Tests for the manifest signing CLI (MS-5 PR#3)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from bridge.connector.adapter_verifier import CABundleAdapterVerifier
from tooling.contracts.sign_manifest import (
    _canonical_signing_payload,
    sign_manifest,
)

_REPO = Path(__file__).resolve().parents[3]
_GCAL_MANIFEST = (
    _REPO / "bridge" / "contracts" / "manifests" / "ifl.google_calendar.events.list.v1.yaml"
)
_DEV_PRIV = _REPO / "tests" / "fixtures" / "dev_trust_anchor.priv.json"
_BUNDLE = _REPO / "bridge" / "contracts" / "_meta" / "ca_bundle.json"


@pytest.fixture()
def manifest_copy(tmp_path: Path) -> Path:
    target = tmp_path / "manifest.yaml"
    shutil.copy(_GCAL_MANIFEST, target)
    return target


class TestSignManifest:
    def test_sign_attaches_signature_field(self, manifest_copy: Path) -> None:
        result = sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        assert result["signing"]["signature"]
        assert not result["signing"]["signature"].startswith("PLACEHOLDER")

    def test_sign_includes_payload_sha256(self, manifest_copy: Path) -> None:
        result = sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        digest = result["signing"]["payload_sha256"]
        assert isinstance(digest, str) and len(digest) == 64

    def test_signed_manifest_verifies_with_production_verifier(self, manifest_copy: Path) -> None:
        sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        manifest = yaml.safe_load(manifest_copy.read_text(encoding="utf-8"))
        verifier = CABundleAdapterVerifier(
            ca_bundle_path=_BUNDLE,
            trust_unsigned=False,
        )
        verifier.verify(manifest)  # must not raise

    def test_payload_excludes_signing_block(self, manifest_copy: Path) -> None:
        manifest = yaml.safe_load(manifest_copy.read_text(encoding="utf-8"))
        payload = _canonical_signing_payload(manifest)
        assert b'"signing"' not in payload
        # Other top-level keys MUST be present.
        assert b'"delivery"' in payload

    def test_sign_in_place_writes_yaml_back(self, manifest_copy: Path) -> None:
        sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        after = manifest_copy.read_text(encoding="utf-8")
        # Whatever the prior state was, after signing the placeholder
        # marker MUST be gone and the file MUST still parse as YAML.
        assert "PLACEHOLDER_SIGN_BEFORE_REGISTER" not in after
        parsed = yaml.safe_load(after)
        assert parsed["signing"]["signature"]
        assert not parsed["signing"]["signature"].startswith("PLACEHOLDER")

    def test_sign_check_mode_does_not_mutate_file(self, manifest_copy: Path) -> None:
        before = manifest_copy.read_text(encoding="utf-8")
        sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
            in_place=False,
        )
        assert manifest_copy.read_text(encoding="utf-8") == before

    def test_sign_overwrites_existing_signature(self, manifest_copy: Path) -> None:
        first = sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        # Mutate a non-signing field; second signing must produce a
        # different signature because canonical payload changed.
        m = yaml.safe_load(manifest_copy.read_text(encoding="utf-8"))
        m["semantics"] = m.get("semantics") or {}
        m["semantics"]["touched_at"] = "2026-05-17"
        manifest_copy.write_text(
            yaml.safe_dump(m, sort_keys=False),
            encoding="utf-8",
        )
        second = sign_manifest(
            manifest_path=manifest_copy,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        assert first["signing"]["signature"] != second["signing"]["signature"]

    def test_sign_rejects_manifest_without_signing_block(self, tmp_path: Path) -> None:
        target = tmp_path / "no_signing.yaml"
        target.write_text(
            yaml.safe_dump({"adapter_id": "x", "kind": "ifl"}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            sign_manifest(
                manifest_path=target,
                priv_key_path=_DEV_PRIV,
                ca_id="dev_familyos_root_v1",
            )

    def test_sign_rejects_non_dict_yaml(self, tmp_path: Path) -> None:
        target = tmp_path / "list.yaml"
        target.write_text(yaml.safe_dump([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError):
            sign_manifest(
                manifest_path=target,
                priv_key_path=_DEV_PRIV,
                ca_id="dev_familyos_root_v1",
            )


class TestDevTrustAnchorFiles:
    def test_priv_key_file_has_required_fields(self) -> None:
        priv = json.loads(_DEV_PRIV.read_text(encoding="utf-8"))
        for k in ("ca_id", "ed25519_public_key_b64url", "ed25519_private_key_b64url"):
            assert k in priv

    def test_pub_key_matches_priv_key_pubkey(self) -> None:
        priv = json.loads(_DEV_PRIV.read_text(encoding="utf-8"))
        pub_path = _REPO / "tests" / "fixtures" / "dev_trust_anchor.pub.json"
        pub = json.loads(pub_path.read_text(encoding="utf-8"))
        assert priv["ed25519_public_key_b64url"] == pub["ed25519_public_key_b64url"]

    def test_ca_bundle_uses_dev_anchor_pubkey(self) -> None:
        priv = json.loads(_DEV_PRIV.read_text(encoding="utf-8"))
        bundle = json.loads(_BUNDLE.read_text(encoding="utf-8"))
        assert bundle["ed25519_public_key"] == priv["ed25519_public_key_b64url"]
        assert bundle["ca_id"] == priv["ca_id"]
