"""Canonical idempotency key derivation utilities."""

from __future__ import annotations

import hashlib
import hmac
import string
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from blake3 import blake3  # type: ignore[import]

from k0.security import canonical_json

_CANONICAL_FIELDS: Sequence[str] = (
    "tenant_id",
    "space_id",
    "actor",
    "topic",
    "schema_uri",
    "schema_version",
)


def canonical_idem_components(
    envelope: Mapping[str, Any],
    *,
    payload_hash: str | None = None,
) -> list[str | None]:
    """Return the canonical component array used for idempotency derivation.

    Parameters
    ----------
    envelope:
        Request envelope providing the canonical fields documented in the
        correctness contract. Each value is coerced to a trimmed UTF-8 string
        and must be non-empty.
    payload_hash:
        Optional payload digest to include as the final element. When omitted,
        ``envelope['payload_sha256']`` is used instead. ``None`` represents an
        absent payload and serialises to ``null`` within the canonical array.
    """

    components: list[str | None] = []
    for field in _CANONICAL_FIELDS:
        raw_value = envelope.get(field)
        if raw_value is None:
            msg = f"{field} is required for idempotency derivation"
            raise ValueError(msg)
        text = str(raw_value)
        if not text:
            msg = f"{field} must not be empty for idempotency derivation"
            raise ValueError(msg)
        components.append(text)

    hash_value = payload_hash
    if hash_value is None:
        raw_hash = envelope.get("payload_sha256")
        if raw_hash is not None:
            hash_value = str(raw_hash)

    if hash_value is None:
        components.append(None)
    else:
        components.append(_normalize_hash(hash_value))

    return components


def derive_idem_key(
    envelope: Mapping[str, Any],
    *,
    payload_hash: str | None = None,
) -> str:
    """Derive the canonical BLAKE3 idempotency key for *envelope*."""

    components = canonical_idem_components(envelope, payload_hash=payload_hash)
    canonical_bytes = canonical_json(components).encode("utf-8")
    digest = blake3(canonical_bytes)
    return digest.hexdigest()


def _normalize_hash(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(ch not in string.hexdigits for ch in normalized):
        msg = "payload hash must be a 64-character hexadecimal digest"
        raise ValueError(msg)
    return normalized


def derive_hmac_idem_key(
    envelope_sha256: str,
    device_id: str,
    device_secret: bytes,
    ts: str | None = None,
) -> str:
    """Derive HMAC-based idempotency key using device secret + time bucket (V1).

    This derives a cryptographically secure, device-specific, time-limited
    idempotency key that prevents replay attacks and cross-device collisions.

    Parameters
    ----------
    envelope_sha256 : str
        SHA-256 hash of full canonical envelope (from Issue 1.1)
    device_id : str
        Device identifier (from envelope)
    device_secret : bytes
        HMAC secret stored in provisioning ledger (32 bytes)
    ts : str, optional
        ISO8601 timestamp from envelope. If None, uses current time.

    Returns
    -------
    str
        HMAC-based idem_key in format: idem:<32-char hex>

    Algorithm
    ---------
    1. Parse ts to datetime, bucket to 60-second intervals
    2. Create message = envelope_sha256 || device_id || time_bucket
    3. Compute HMAC-SHA256(device_secret, message)
    4. Return f"idem:{digest[:32]}"

    Properties
    ----------
    - Cryptographically secure (HMAC-SHA256)
    - Device-specific (includes device_id + device_secret)
    - Time-limited (60-second bucket = replay window)
    - Non-predictable (requires device_secret)
    """
    # Determine timestamp to use
    if ts is None:
        now = datetime.now(timezone.utc)
    else:
        # Parse ISO8601 timestamp
        try:
            now = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            msg = f"Invalid timestamp format: {ts}"
            raise ValueError(msg) from exc

    # Bucket to 60-second intervals (ensures stability within window)
    time_bucket = int(now.timestamp()) // 60

    # Create message for HMAC
    message = f"{envelope_sha256}|{device_id}|{time_bucket}".encode("utf-8")

    # Compute HMAC-SHA256
    digest = hmac.new(device_secret, message, hashlib.sha256).hexdigest()

    # Return in format: idem:<32-char hex>
    return f"idem:{digest[:32]}"


__all__ = [
    "canonical_idem_components",
    "derive_hmac_idem_key",
    "derive_idem_key",
]
