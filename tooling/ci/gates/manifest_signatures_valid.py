"""manifest_signatures_valid — every IFL adapter manifest verifies cleanly.

Walks ``bridge/contracts/manifests/*.yaml``, **selects the IFL adapter
manifests** (those with ``delivery.transport == "mcp_stdio"``), and runs
each through the production :class:`CABundleAdapterVerifier` (no
``trust_unsigned`` short-circuit).

Bus contract manifests (HTTP-transport, K0↔K1 routing) are intentionally
out of scope: their integrity is enforced by the contract checksum gate
plus the producer/consumer pipeline tests, not by Ed25519 signing.

Failure modes detected on IFL manifests:

* missing ``signing`` block
* placeholder signature
* unknown ca_id (not in current ca_bundle.json)
* signature does not verify against the bundled public key
* ``signing.payload_sha256`` mismatch (when present)

Manifests with ``status: deprecated`` are skipped — they may carry
historical signatures from rotated CAs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from bridge.connector.adapter_verifier import (
    CABundleAdapterVerifier,
)
from bridge.connector.contracts import InvalidAdapterSignatureError

from ._harness import run_gate

_GATE_NAME = "manifest_signatures_valid"
_MANIFEST_DIR = Path("bridge/contracts/manifests")
_BUNDLE_PATH = Path("bridge/contracts/_meta/ca_bundle.json")


def _check(args: argparse.Namespace) -> list[str]:
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[3]
    )
    manifest_dir = repo_root / _MANIFEST_DIR
    if not manifest_dir.exists():
        return []  # nothing to verify
    bundle_path = repo_root / _BUNDLE_PATH

    verifier = CABundleAdapterVerifier(
        ca_bundle_path=bundle_path,
        trust_unsigned=False,
    )

    violations: list[str] = []
    for path in sorted(manifest_dir.glob("*.yaml")):
        try:
            manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            violations.append(f"{path.relative_to(repo_root)}: invalid YAML ({exc})")
            continue
        if not isinstance(manifest, dict):
            violations.append(f"{path.relative_to(repo_root)}: not a YAML mapping")
            continue
        if manifest.get("status") == "deprecated":
            continue
        # Restrict to IFL adapter manifests. Bus contract manifests
        # (transport: http) are validated by the schema_checksum_stable
        # gate and the per-contract producer/consumer tests instead.
        delivery = manifest.get("delivery") or {}
        if delivery.get("transport") != "mcp_stdio":
            continue
        try:
            verifier.verify(manifest)
        except InvalidAdapterSignatureError as exc:
            violations.append(f"{path.relative_to(repo_root)}: signature INVALID — {exc}")

    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(_GATE_NAME, _check, argv)


if __name__ == "__main__":
    raise SystemExit(main())
