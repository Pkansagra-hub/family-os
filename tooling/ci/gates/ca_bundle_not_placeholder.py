"""ca_bundle_not_placeholder — refuse PLACEHOLDER trust anchors.

Failure modes detected:

1. ``ed25519_public_key`` starts with ``PLACEHOLDER`` (the pre-MS-5
   stub the bundle shipped with).
2. ``ca_id`` starts with ``dev_`` AND ``CI_ALLOW_DEV_TRUST_ANCHOR`` is
   not set in the environment. This is the merge-protection gate that
   prevents the dev anchor from being mistaken for a production root.

Setting ``CI_ALLOW_DEV_TRUST_ANCHOR=1`` in CI lets contributor PRs run
green while the dev anchor is in place; the production deployment
pipeline must never set this flag, so the gate fires the moment
someone tries to merge the dev bundle to ``main``.

Exit code 1 (default) on violation; ``--warn-only`` to downgrade.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ._harness import run_gate

_GATE_NAME = "ca_bundle_not_placeholder"
_BUNDLE_REL_PATH = Path("bridge/contracts/_meta/ca_bundle.json")
_AUDIT_REL_PATH = Path("bridge/contracts/_meta/ca_bundle.audit.json")
_DEV_PREFIX = "dev_"
_PLACEHOLDER_MARKER = "PLACEHOLDER"
_ENV_ALLOW_DEV = "CI_ALLOW_DEV_TRUST_ANCHOR"


def _check(args: argparse.Namespace) -> list[str]:
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[3]
    )
    bundle_path = repo_root / _BUNDLE_REL_PATH
    if not bundle_path.exists():
        return [f"{_BUNDLE_REL_PATH}: file missing"]
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{_BUNDLE_REL_PATH}: not valid JSON ({exc})"]

    violations: list[str] = []
    pubkey = bundle.get("ed25519_public_key", "")
    if pubkey.startswith(_PLACEHOLDER_MARKER):
        violations.append(
            f"{_BUNDLE_REL_PATH}: ed25519_public_key still starts with "
            f"{_PLACEHOLDER_MARKER!r}; run the trust-anchor ceremony or "
            f"sign with the dev anchor"
        )

    ca_id = bundle.get("ca_id", "")
    allow_dev = os.environ.get(_ENV_ALLOW_DEV, "").strip() in ("1", "true", "yes")
    if ca_id.startswith(_DEV_PREFIX) and not allow_dev:
        violations.append(
            f"{_BUNDLE_REL_PATH}: ca_id={ca_id!r} is a DEV trust anchor; "
            f"set {_ENV_ALLOW_DEV}=1 in CI to merge — production must "
            f"replace this with the air-gapped root before deploy"
        )

    # If ca_id is dev_*, require an audit stub so operators can trace
    # how the dev anchor came to exist. Production audits live outside
    # the repo so this check is dev-anchor-specific.
    if ca_id.startswith(_DEV_PREFIX):
        audit_path = repo_root / _AUDIT_REL_PATH
        if not audit_path.exists():
            violations.append(
                f"{_AUDIT_REL_PATH}: missing audit stub for DEV trust "
                f"anchor {ca_id!r}; create one matching ca_bundle.audit.json"
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(_GATE_NAME, _check, argv)


if __name__ == "__main__":
    raise SystemExit(main())
