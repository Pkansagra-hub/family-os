"""Deterministic helpers for payload hashing, canonical JSON, and signature checks."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any, Mapping

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

_CANONICAL_SEPARATORS: tuple[str, str] = (",", ":")


class SignatureVerificationError(RuntimeError):
    """Raised when signature verification fails or inputs are invalid."""


def canonical_json(payload: Any) -> str:
    """Return the canonical JSON representation of *payload*.

    Canonical form uses sorted keys, UTF-8 encoding, disabled ASCII escapes, and
    minimal separators so signing and hashing remain deterministic across
    runtimes.
    """

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=_CANONICAL_SEPARATORS,
    )


def canonical_envelope(
    envelope: Mapping[str, Any],
    *,
    exclude_signature: bool = True,
) -> bytes:
    """Return canonical bytes of *envelope* suitable for signing.

    When *exclude_signature* is true, the ``sig`` field is removed prior to
    serialisation (V1: body is now INCLUDED in the signature to provide full
    envelope integrity). This ensures callers sign the entire envelope including
    headers, body, and all metadata, preventing header tampering attacks.
    """

    exclude_fields: set[str] = set()
    if exclude_signature:
        exclude_fields.add("sig")
        exclude_fields.add("envelope_sha256")  # V1: exclude hash field itself
        # V1 CHANGE: body is now INCLUDED in signature (not excluded)

    if exclude_fields:
        working = {key: value for key, value in envelope.items() if key not in exclude_fields}
    else:
        working = dict(envelope)
    return canonical_json(working).encode("utf-8")


def hash_payload(body: bytes | None) -> str | None:
    """Return the SHA-256 hash of *body* or ``None`` when no payload exists."""

    if body is None:
        return None
    digest = hashlib.sha256(body)
    return digest.hexdigest()


def compute_envelope_sha256(envelope: Mapping[str, Any]) -> str:
    """Compute SHA-256 hash of the full canonical envelope (V1).

    This hash covers the entire envelope (all fields except sig itself).
    Used for:
    - Exact duplicate detection (replay protection)
    - Receipt verification
    - WAL deduplication indexing

    Parameters
    ----------
    envelope : Mapping[str, Any]
        Envelope to hash (sig field will be excluded, body will be included)

    Returns
    -------
    str
        Hexadecimal SHA-256 digest (64 characters)
    """
    canonical = canonical_envelope(envelope, exclude_signature=True)
    digest = hashlib.sha256(canonical)
    return digest.hexdigest()


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except (binascii.Error, ValueError) as exc:  # pragma: no cover - defensive guard
        raise SignatureVerificationError("Invalid base64url data") from exc


def verify_signature(message: bytes, signature_b64: str, verify_key_b64: str) -> None:
    """Verify *signature_b64* over *message* using the provided verify key.

    The signature and key are expected to be URL-safe base64 strings without
    padding. On failure, :class:`SignatureVerificationError` is raised.
    """

    try:
        signature = _decode_base64url(signature_b64)
        key_bytes = _decode_base64url(verify_key_b64)
        verify_key = VerifyKey(key_bytes)
        verify_key.verify(message, signature)
    except (ValueError, BadSignatureError) as exc:
        raise SignatureVerificationError("Signature verification failed") from exc


def verify_full_envelope_signature(
    envelope: Mapping[str, Any],
    verify_key_b64: str,
) -> bool:
    """Verify V1 full envelope signature (includes body + all headers).

    V1 signature covers the entire canonical envelope (all fields except sig itself).
    This prevents header tampering attacks (actor, space_id, band, ts, etc.).

    Parameters
    ----------
    envelope : Mapping[str, Any]
        Envelope with sig field to verify
    verify_key_b64 : str
        URL-safe base64 verify key (Ed25519 public key)

    Returns
    -------
    bool
        True if signature valid, False otherwise

    Notes
    -----
    - Signature must be in envelope["sig"]
    - Canonical envelope computed with exclude_signature=True (body INCLUDED)
    - Uses Ed25519 signature verification
    """
    signature_b64 = envelope.get("sig")
    if signature_b64 is None:
        return False

    try:
        # Compute canonical envelope (body INCLUDED, sig EXCLUDED)
        canonical = canonical_envelope(envelope, exclude_signature=True)

        # Verify signature over canonical bytes
        verify_signature(canonical, signature_b64, verify_key_b64)
        return True
    except SignatureVerificationError:
        return False


def encode_base64url(data: bytes) -> str:
    """Return the URL-safe base64 (unpadded) representation of *data*."""

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


__all__ = [
    "SignatureVerificationError",
    "canonical_envelope",
    "canonical_json",
    "compute_envelope_sha256",
    "encode_base64url",
    "hash_payload",
    "verify_full_envelope_signature",
    "verify_signature",
]
