"""Utilities for computing deterministic outbox fingerprints."""

from __future__ import annotations

from blake3 import blake3  # type: ignore[import]


def compute_fingerprint(driver: str, op_kind: str, payload: bytes) -> str:
    """Return a deterministic BLAKE3 fingerprint for an outbox entry.

    The fingerprint combines the driver alias, operation kind, and raw payload bytes to
    guarantee idempotent application semantics for downstream drivers. Inputs must be
    provided exactly as committed into the outbox to ensure replay parity.
    """

    if not driver:
        msg = "driver alias must be provided"
        raise ValueError(msg)
    if not op_kind:
        msg = "operation kind must be provided"
        raise ValueError(msg)

    digest = blake3()  # type: ignore[call-arg]
    digest.update(driver.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(op_kind.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(payload)
    return digest.hexdigest()
