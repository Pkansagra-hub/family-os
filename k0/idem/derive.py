"""Canonical idempotency key derivation utilities."""

from __future__ import annotations

import string
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


__all__ = [
    "canonical_idem_components",
    "derive_idem_key",
]
