"""sign_manifest — CLI to attach an Ed25519 signature to an IFL manifest.

MS-5 PR#3: signs IFL adapter manifests (e.g. the Google Calendar
manifest) using a local private key, then writes the signature back
into the YAML's ``signing.signature`` field.

Canonical signing payload:
    json.dumps({k: v for k, v in manifest.items() if k != "signing"},
               sort_keys=True, separators=(",",":")).encode("utf-8")

…which matches :func:`bridge.connector.adapter_verifier._canonical_signing_payload`.
This guarantees that any signature the CLI produces verifies with the
exact same code path the gateway uses at registration time.

Usage:
    python -m tooling.contracts.sign_manifest \\
        --manifest bridge/contracts/manifests/ifl.google_calendar.events.list.v1.yaml \\
        --priv-key tests/fixtures/dev_trust_anchor.priv.json \\
        --ca-id dev_familyos_root_v1

The CLI mutates the YAML in place (preserving comment-free key order)
so the only delta is ``signing.signature`` and ``signing.payload_sha256``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from nacl.signing import SigningKey


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _canonical_signing_payload(manifest: dict[str, Any]) -> bytes:
    """Bytes that the signature is computed over.

    Mirrors :func:`bridge.connector.adapter_verifier._canonical_signing_payload`
    exactly so the CLI's output verifies via the gateway's verifier.
    """
    payload = {k: v for k, v in manifest.items() if k != "signing"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_private_key(priv_key_path: Path) -> SigningKey:
    raw = json.loads(priv_key_path.read_text(encoding="utf-8"))
    priv_b64 = raw["ed25519_private_key_b64url"]
    return SigningKey(_b64url_decode(priv_b64))


def sign_manifest(
    *,
    manifest_path: Path,
    priv_key_path: Path,
    ca_id: str,
    in_place: bool = True,
) -> dict[str, Any]:
    """Sign ``manifest_path`` and (optionally) write the result back.

    Returns the updated manifest dict so callers can inspect the
    signature without having to re-read the file.
    """
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest at {manifest_path} did not parse to a dict")

    signing_block = manifest.get("signing")
    if not isinstance(signing_block, dict):
        raise ValueError("manifest is missing a 'signing' block; cannot attach signature")

    # Update ca_id BEFORE building canonical payload so the bytes we
    # sign are identical to the bytes the verifier reconstructs from
    # the YAML's signing block (minus the signature itself).
    signing_block["ca_id"] = ca_id

    signing_key = _load_private_key(priv_key_path)
    payload = _canonical_signing_payload(manifest)
    signature_bytes = signing_key.sign(payload).signature
    signature_b64 = _b64url_encode(signature_bytes)
    payload_sha256 = hashlib.sha256(payload).hexdigest()

    signing_block["signature"] = signature_b64
    signing_block["payload_sha256"] = payload_sha256
    manifest["signing"] = signing_block

    if in_place:
        # Use sort_keys=False so the YAML key order is preserved as
        # it was written by hand. yaml.safe_dump's default is
        # sort_keys=True which would shuffle the manifest unhelpfully.
        manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sign_manifest",
        description="Attach an Ed25519 signature to an IFL adapter manifest.",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--priv-key", type=Path, required=True)
    parser.add_argument("--ca-id", type=str, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write; print the would-be signature.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = sign_manifest(
        manifest_path=args.manifest,
        priv_key_path=args.priv_key,
        ca_id=args.ca_id,
        in_place=not args.check,
    )
    sig = manifest["signing"]["signature"]
    print(
        f"signed manifest={args.manifest} ca_id={args.ca_id} " f"signature={sig[:24]}…",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
