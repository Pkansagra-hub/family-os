"""``Ed25519SignatureChainValidator`` — production validator for k1.selfmodel.

Issue M3.E3.I2.

Replaces the M1 ``stub_signature_validator`` in
:mod:`k1.selfmodel.service.constitution`. Validates that:

1. Every signature on the active ``ConstitutionSnapshot`` was produced
   by a known signer (key registered with this validator), AND
2. The signature is a valid Ed25519 signature over the canonical-JSON
   serialisation of the snapshot body, AND
3. Quorum is met: at least ``min_signatures`` accepted signatures.

The optional ``parent_chain`` lookup lets the validator walk the
``parent_version`` chain back to the bootstrap row (whose
``parent_version`` is empty); each ancestor must validate too. The
walker is bounded by ``max_chain_depth`` to avoid runaway loops on
corrupt data.

Canonical JSON: stdlib ``json.dumps(body, sort_keys=True,
separators=(",", ":"), ensure_ascii=False).encode("utf-8")``. Matches
the convention used by the bridge sync adapter (M4) so signatures are
portable across the bridge.

This module does not store keys — the caller registers them at
construction time. Production wiring happens in the kernel bootstrap
(M5) via the same admin path used by the credential verifier.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections.abc import Callable

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from k1.selfmodel.contracts.constitution import (
    ConstitutionSnapshot,
    SigningProof,
)

__all__ = [
    "Ed25519SignatureChainValidator",
    "canonical_body_bytes",
]


logger = logging.getLogger(__name__)


def canonical_body_bytes(body: dict) -> bytes:
    """Return the canonical-JSON byte representation used for signing."""
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# Lookup signature: constitution_id, version -> ConstitutionSnapshot | None.
ParentLookup = Callable[[str, str], "ConstitutionSnapshot | None"]


class Ed25519SignatureChainValidator:
    """Validates a snapshot's signatures and (optionally) its ancestry."""

    def __init__(
        self,
        *,
        min_signatures: int = 1,
        parent_lookup: ParentLookup | None = None,
        max_chain_depth: int = 64,
    ) -> None:
        if min_signatures <= 0:
            raise ValueError("min_signatures must be positive")
        if max_chain_depth <= 0:
            raise ValueError("max_chain_depth must be positive")
        self._min = min_signatures
        self._parent_lookup = parent_lookup
        self._max_depth = max_chain_depth
        self._lock = threading.RLock()
        # signer_id -> 32-byte Ed25519 public key
        self._signers: dict[str, bytes] = {}

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------
    def register_signer(self, signer_id: str, public_key: bytes) -> None:
        if not signer_id:
            raise ValueError("signer_id required")
        if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != 32:
            raise ValueError("public_key must be 32 raw Ed25519 bytes")
        with self._lock:
            self._signers[signer_id] = bytes(public_key)

    def revoke_signer(self, signer_id: str) -> None:
        with self._lock:
            self._signers.pop(signer_id, None)

    @property
    def known_signers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._signers))

    # ------------------------------------------------------------------
    # Validator entry point (matches SignatureChainValidator type)
    # ------------------------------------------------------------------
    def __call__(self, snapshot: ConstitutionSnapshot) -> bool:
        return self.validate(snapshot)

    def validate(self, snapshot: ConstitutionSnapshot) -> bool:
        if not isinstance(snapshot, ConstitutionSnapshot):
            return False
        seen: set[str] = set()
        cursor = snapshot
        depth = 0
        while True:
            if depth >= self._max_depth:
                logger.warning(
                    "signature_chain: chain depth exceeded for %s",
                    snapshot.constitution_id,
                )
                return False
            if cursor.version in seen:
                logger.warning(
                    "signature_chain: cycle detected at version=%s",
                    cursor.version,
                )
                return False
            seen.add(cursor.version)
            if not self._validate_one(cursor):
                return False
            if not cursor.parent_version:
                return True  # reached the bootstrap row
            if self._parent_lookup is None:
                # Caller didn't supply ancestry; trust on parent_version
                # presence (no walk possible).
                return True
            parent = self._parent_lookup(cursor.constitution_id, cursor.parent_version)
            if parent is None:
                logger.warning(
                    "signature_chain: missing parent %s for %s",
                    cursor.parent_version,
                    cursor.version,
                )
                return False
            cursor = parent
            depth += 1

    # ------------------------------------------------------------------
    # Per-snapshot signature math
    # ------------------------------------------------------------------
    def _validate_one(self, snapshot: ConstitutionSnapshot) -> bool:
        if not snapshot.signatures:
            return False
        message = canonical_body_bytes(snapshot.body)
        accepted = 0
        seen_signers: set[str] = set()
        with self._lock:
            signers = dict(self._signers)
        for proof in snapshot.signatures:
            if not isinstance(proof, SigningProof):
                continue
            if proof.algorithm != "ed25519":
                continue
            if proof.signer_id in seen_signers:
                continue
            public_key = signers.get(proof.signer_id)
            if public_key is None:
                continue
            try:
                signature = base64.b64decode(proof.signature_b64, validate=True)
            except (ValueError, base64.binascii.Error):
                continue
            try:
                VerifyKey(public_key).verify(message, signature)
            except BadSignatureError:
                continue
            seen_signers.add(proof.signer_id)
            accepted += 1
        if accepted < self._min:
            logger.info(
                "signature_chain: %d/%d signatures accepted for %s",
                accepted,
                self._min,
                snapshot.version,
            )
            return False
        return True
