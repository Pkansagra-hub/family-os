"""Stage 2 of the IFL gateway pipeline: AdapterVerifier.

Validates that a registered adapter's manifest carries a valid Ed25519
signature whose ``ca_id`` matches an entry in
``bridge/contracts/_meta/ca_bundle.json``.

This is the trust boundary for the entire IFL: only manifests signed by
the FamilyOS root CA (or another bundle-listed CA) are allowed to
register adapters. The verification runs once at registration time; the
gateway caches the verdict and re-runs the check whenever the manifest
hash changes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .contracts import InvalidAdapterSignatureError


@runtime_checkable
class AdapterVerifier(Protocol):
    """Protocol for stage-2 manifest signature verification."""

    def verify(self, manifest: dict[str, Any]) -> None:
        """Raise :class:`InvalidAdapterSignatureError` if invalid."""
        ...  # pragma: no cover


def _b64url_decode(data: str) -> bytes:
    """Decode a base64url string with optional missing padding."""
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _canonical_signing_payload(manifest: dict[str, Any]) -> bytes:
    """Build the canonical bytes that the manifest's ``signing.signature``
    is computed over.

    The signing block itself is excluded (signatures cannot sign
    themselves). Everything else is serialised with sorted keys and no
    whitespace — matches :mod:`bridge.core.signing` conventions.
    """
    payload = {k: v for k, v in manifest.items() if k != "signing"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class CABundleAdapterVerifier:
    """Default verifier backed by ``ca_bundle.json``.

    The bundle is loaded eagerly at construction time. Pass
    ``trust_unsigned=True`` only in tests where a manifest deliberately
    omits the ``signing`` block — the gateway itself never sets that
    flag.
    """

    def __init__(
        self,
        *,
        ca_bundle_path: Path | str | None = None,
        trust_unsigned: bool = False,
    ) -> None:
        self._trust_unsigned = trust_unsigned
        if ca_bundle_path is None:
            ca_bundle_path = (
                Path(__file__).resolve().parent.parent / "contracts" / "_meta" / "ca_bundle.json"
            )
        self._ca_bundle_path = Path(ca_bundle_path)
        self._bundle = self._load_bundle(self._ca_bundle_path)

    @staticmethod
    def _load_bundle(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        # ca_bundle.json is a single-CA dict in MS-5; coerce to a
        # ca_id-indexed map so future bundles with multiple CAs Just Work.
        if isinstance(raw, dict) and "ca_id" in raw:
            return {raw["ca_id"]: raw}
        if isinstance(raw, list):
            return {entry["ca_id"]: entry for entry in raw if "ca_id" in entry}
        if isinstance(raw, dict):
            return raw
        return {}

    def verify(self, manifest: dict[str, Any]) -> None:
        signing = manifest.get("signing")
        if signing is None:
            if self._trust_unsigned:
                return
            raise InvalidAdapterSignatureError(
                "manifest missing 'signing' block; refusing to register"
            )

        ca_id = signing.get("ca_id")
        signature_b64 = signing.get("signature")
        if not ca_id or not signature_b64:
            raise InvalidAdapterSignatureError(
                "signing block missing required fields (ca_id, signature)"
            )

        ca_entry = self._bundle.get(ca_id)
        if ca_entry is None:
            raise InvalidAdapterSignatureError(f"unknown ca_id {ca_id!r}; not in ca_bundle.json")

        if ca_entry.get("status") != "active":
            raise InvalidAdapterSignatureError(
                f"ca {ca_id!r} not active (status={ca_entry.get('status')!r})"
            )

        public_key_b64 = ca_entry.get("ed25519_public_key", "")
        if not public_key_b64 or public_key_b64.startswith("PLACEHOLDER"):
            if self._trust_unsigned:
                return
            raise InvalidAdapterSignatureError(
                f"ca {ca_id!r} has placeholder public key; refusing to verify"
            )

        try:
            public_key_bytes = _b64url_decode(public_key_b64)
            signature_bytes = _b64url_decode(signature_b64)
        except (ValueError, TypeError) as exc:
            raise InvalidAdapterSignatureError(
                f"signature/public-key not valid base64url: {exc}"
            ) from exc

        payload = _canonical_signing_payload(manifest)

        # Optional integrity check: signing.payload_sha256 (if present)
        # must match the SHA-256 of the canonical payload — protects
        # against accidental mutation between sign and verify.
        expected_digest = signing.get("payload_sha256")
        if expected_digest:
            actual_digest = hashlib.sha256(payload).hexdigest()
            if actual_digest != expected_digest:
                raise InvalidAdapterSignatureError(
                    "signing.payload_sha256 does not match canonical payload"
                )

        try:
            from nacl.exceptions import BadSignatureError  # noqa: PLC0415
            from nacl.signing import VerifyKey  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover — pynacl is a dep
            raise InvalidAdapterSignatureError(
                f"PyNaCl not available for signature verification: {exc}"
            ) from exc

        verify_key = VerifyKey(public_key_bytes)
        try:
            verify_key.verify(payload, signature_bytes)
        except BadSignatureError as exc:
            raise InvalidAdapterSignatureError(
                f"manifest signature verification failed for ca_id={ca_id!r}"
            ) from exc


__all__ = ["AdapterVerifier", "CABundleAdapterVerifier"]
