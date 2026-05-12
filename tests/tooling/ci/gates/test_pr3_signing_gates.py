"""Tests for the three new MS-5 PR#3 CI gates.

* :mod:`tooling.ci.gates.ca_bundle_not_placeholder`
* :mod:`tooling.ci.gates.manifest_signatures_valid`
* :mod:`tooling.ci.gates.dev_trust_anchor_audit_present`

Each gate is run against a synthetic ``--repo-root`` fixture so we can
inject placeholder bundles, dev anchors with/without audit stubs, and
deliberately broken signatures without touching the real repo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[4]


def _make_fake_repo(
    tmp_path: Path,
    *,
    bundle: dict | None,
    audit: dict | None = None,
    manifests: list[tuple[str, dict]] | None = None,
) -> Path:
    """Build a minimal repo fixture rooted at tmp_path.

    The fake repo carries only the files the gate examines: a
    ``bridge/contracts/_meta/`` dir + a ``bridge/contracts/manifests/``
    dir.
    """
    meta_dir = tmp_path / "bridge" / "contracts" / "_meta"
    manifests_dir = tmp_path / "bridge" / "contracts" / "manifests"
    meta_dir.mkdir(parents=True)
    manifests_dir.mkdir(parents=True)
    if bundle is not None:
        (meta_dir / "ca_bundle.json").write_text(
            json.dumps(bundle),
            encoding="utf-8",
        )
    if audit is not None:
        (meta_dir / "ca_bundle.audit.json").write_text(
            json.dumps(audit),
            encoding="utf-8",
        )
    for name, manifest in manifests or []:
        (manifests_dir / name).write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )
    return tmp_path


def _run_gate(module: str, repo_root: Path, *, env: dict | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", module, "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


@pytest.fixture()
def env_no_dev_allow(monkeypatch: pytest.MonkeyPatch) -> dict:
    import os

    e = dict(os.environ)
    e.pop("CI_ALLOW_DEV_TRUST_ANCHOR", None)
    return e


@pytest.fixture()
def env_with_dev_allow() -> dict:
    import os

    e = dict(os.environ)
    e["CI_ALLOW_DEV_TRUST_ANCHOR"] = "1"
    return e


class TestCABundleNotPlaceholder:
    def test_placeholder_pubkey_is_rejected(self, tmp_path: Path, env_with_dev_allow: dict) -> None:
        bundle = {
            "ca_id": "familyos_root_v1",
            "ed25519_public_key": "PLACEHOLDER_REPLACE_BEFORE_MS5",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle)
        rc, out = _run_gate(
            "tooling.ci.gates.ca_bundle_not_placeholder",
            repo,
            env=env_with_dev_allow,
        )
        assert rc == 1
        assert "PLACEHOLDER" in out

    def test_dev_anchor_rejected_without_env_flag(
        self, tmp_path: Path, env_no_dev_allow: dict
    ) -> None:
        bundle = {
            "ca_id": "dev_familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        audit = {
            "ca_id": "dev_familyos_root_v1",
            "performed_at": "2026-05-17T00:00:00Z",
            "method": "test",
            "key_storage": "test",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=audit)
        rc, out = _run_gate(
            "tooling.ci.gates.ca_bundle_not_placeholder",
            repo,
            env=env_no_dev_allow,
        )
        assert rc == 1
        assert "DEV trust anchor" in out

    def test_dev_anchor_passes_with_env_flag_and_audit(
        self, tmp_path: Path, env_with_dev_allow: dict
    ) -> None:
        bundle = {
            "ca_id": "dev_familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        audit = {
            "ca_id": "dev_familyos_root_v1",
            "performed_at": "2026-05-17T00:00:00Z",
            "method": "test",
            "key_storage": "test",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=audit)
        rc, _ = _run_gate(
            "tooling.ci.gates.ca_bundle_not_placeholder",
            repo,
            env=env_with_dev_allow,
        )
        assert rc == 0

    def test_production_anchor_passes_without_audit(
        self, tmp_path: Path, env_no_dev_allow: dict
    ) -> None:
        bundle = {
            "ca_id": "familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle)
        rc, _ = _run_gate(
            "tooling.ci.gates.ca_bundle_not_placeholder",
            repo,
            env=env_no_dev_allow,
        )
        assert rc == 0

    def test_missing_bundle_fails(self, tmp_path: Path) -> None:
        repo = _make_fake_repo(tmp_path, bundle=None)
        rc, out = _run_gate("tooling.ci.gates.ca_bundle_not_placeholder", repo)
        assert rc == 1
        assert "missing" in out.lower()


class TestDevTrustAnchorAuditPresent:
    def test_dev_anchor_without_audit_fails(self, tmp_path: Path) -> None:
        bundle = {
            "ca_id": "dev_familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=None)
        rc, out = _run_gate(
            "tooling.ci.gates.dev_trust_anchor_audit_present",
            repo,
        )
        assert rc == 1
        assert "audit" in out.lower()

    def test_dev_anchor_with_audit_passes(self, tmp_path: Path) -> None:
        bundle = {
            "ca_id": "dev_familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        audit = {
            "ca_id": "dev_familyos_root_v1",
            "performed_at": "2026-05-17T00:00:00Z",
            "method": "test",
            "key_storage": "test",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=audit)
        rc, _ = _run_gate(
            "tooling.ci.gates.dev_trust_anchor_audit_present",
            repo,
        )
        assert rc == 0

    def test_audit_ca_id_mismatch_fails(self, tmp_path: Path) -> None:
        bundle = {
            "ca_id": "dev_familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        audit = {
            "ca_id": "dev_other_anchor",  # mismatch
            "performed_at": "2026-05-17",
            "method": "x",
            "key_storage": "x",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=audit)
        rc, out = _run_gate(
            "tooling.ci.gates.dev_trust_anchor_audit_present",
            repo,
        )
        assert rc == 1
        assert "mismatch" in out.lower()

    def test_audit_missing_required_field_fails(self, tmp_path: Path) -> None:
        bundle = {
            "ca_id": "dev_familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        audit = {
            "ca_id": "dev_familyos_root_v1",
            "performed_at": "",  # blank
            "method": "x",
            "key_storage": "x",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=audit)
        rc, _ = _run_gate(
            "tooling.ci.gates.dev_trust_anchor_audit_present",
            repo,
        )
        assert rc == 1

    def test_production_anchor_skips_audit_check(self, tmp_path: Path) -> None:
        bundle = {
            "ca_id": "familyos_root_v1",
            "ed25519_public_key": "abc",
            "status": "active",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        repo = _make_fake_repo(tmp_path, bundle=bundle, audit=None)
        rc, _ = _run_gate(
            "tooling.ci.gates.dev_trust_anchor_audit_present",
            repo,
        )
        assert rc == 0


class TestManifestSignaturesValid:
    def test_real_repo_passes(self) -> None:
        # The actual repo state must verify cleanly — this is the
        # backstop for the gate against bit rot.
        rc, _ = _run_gate(
            "tooling.ci.gates.manifest_signatures_valid",
            _REPO,
        )
        assert rc == 0

    def test_unsigned_ifl_manifest_fails(self, tmp_path: Path) -> None:
        # Copy the real bundle so verification can use the dev pubkey.
        repo = _make_fake_repo(
            tmp_path,
            bundle=json.loads(
                (_REPO / "bridge" / "contracts" / "_meta" / "ca_bundle.json").read_text(
                    encoding="utf-8"
                )
            ),
        )
        # Drop an IFL manifest with NO signing block.
        manifest = {
            "adapter_id": "broken",
            "delivery": {"transport": "mcp_stdio"},
            "mcp": {"server_command": ["python", "-m", "x"]},
        }
        (repo / "bridge" / "contracts" / "manifests" / "ifl.broken.v1.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )
        rc, out = _run_gate(
            "tooling.ci.gates.manifest_signatures_valid",
            repo,
        )
        assert rc == 1
        assert "INVALID" in out

    def test_bus_manifests_are_skipped(self, tmp_path: Path) -> None:
        # A bus contract manifest WITHOUT a signing block must not
        # cause the gate to fail (only IFL adapter manifests are
        # subject to signing checks).
        repo = _make_fake_repo(
            tmp_path,
            bundle=json.loads(
                (_REPO / "bridge" / "contracts" / "_meta" / "ca_bundle.json").read_text(
                    encoding="utf-8"
                )
            ),
        )
        bus_manifest = {
            "topic": "bus.example.v1",
            "delivery": {"transport": "http"},
        }
        (repo / "bridge" / "contracts" / "manifests" / "bus.example.v1.yaml").write_text(
            yaml.safe_dump(bus_manifest, sort_keys=False),
            encoding="utf-8",
        )
        rc, _ = _run_gate(
            "tooling.ci.gates.manifest_signatures_valid",
            repo,
        )
        assert rc == 0
