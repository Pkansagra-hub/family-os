"""dev_trust_anchor_audit_present — dev anchor must ship an audit stub.

If ``bridge/contracts/_meta/ca_bundle.json`` declares a ``dev_*``
``ca_id``, the matching ``ca_bundle.audit.json`` file MUST exist and
must record at minimum:

* ``ca_id`` (matches the bundle)
* ``performed_at``
* ``method``
* ``key_storage``

This is the cheap check that prevents an engineer from rotating the
dev anchor without leaving an audit trail. The production ceremony
audit lives outside the repo (operator-signed PDF) per D19; this gate
only enforces the dev-anchor contract.

For non-dev anchors the gate is a no-op — production audits are out
of scope.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._harness import run_gate

_GATE_NAME = "dev_trust_anchor_audit_present"
_BUNDLE_REL_PATH = Path("bridge/contracts/_meta/ca_bundle.json")
_AUDIT_REL_PATH = Path("bridge/contracts/_meta/ca_bundle.audit.json")
_DEV_PREFIX = "dev_"
_REQUIRED_FIELDS = ("ca_id", "performed_at", "method", "key_storage")


def _check(args: argparse.Namespace) -> list[str]:
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[3]
    )
    bundle_path = repo_root / _BUNDLE_REL_PATH
    if not bundle_path.exists():
        return [f"{_BUNDLE_REL_PATH}: missing"]
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{_BUNDLE_REL_PATH}: not valid JSON ({exc})"]

    bundle_ca_id = bundle.get("ca_id", "")
    if not bundle_ca_id.startswith(_DEV_PREFIX):
        return []  # production anchor; audit lives elsewhere

    audit_path = repo_root / _AUDIT_REL_PATH
    if not audit_path.exists():
        return [f"{_AUDIT_REL_PATH}: missing audit stub for DEV anchor " f"ca_id={bundle_ca_id!r}"]
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{_AUDIT_REL_PATH}: not valid JSON ({exc})"]

    violations: list[str] = []
    audit_ca_id = audit.get("ca_id", "")
    if audit_ca_id != bundle_ca_id:
        violations.append(
            f"{_AUDIT_REL_PATH}: ca_id mismatch — bundle says "
            f"{bundle_ca_id!r}, audit says {audit_ca_id!r}"
        )
    for field in _REQUIRED_FIELDS:
        if not audit.get(field):
            violations.append(f"{_AUDIT_REL_PATH}: required field {field!r} is missing or empty")
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(_GATE_NAME, _check, argv)


if __name__ == "__main__":
    raise SystemExit(main())
