"""``Ed25519CredentialVerifier`` — production credential verifier for k1.selfmodel.

Issue M3.E1.I1.

Implements ``ICredentialPort.verify`` for two credential kinds:

* ``"pin"``    — memory-hard hash check (stdlib ``hashlib.scrypt``).
                 The whiteboard calls for Argon2id; we use scrypt to keep
                 the kernel dependency-free. Both KDFs are memory-hard and
                 produce ~equivalent resistance against brute force when
                 sized correctly. The hash format embeds parameters so a
                 future swap to Argon2id is a drop-in upgrade.
* ``"passkey"`` / ``"webauthn"`` — Ed25519 signature verification over a
                 ``challenge`` payload using a previously-registered public
                 key (PyNaCl ``VerifyKey``). The verifier owns a one-shot
                 nonce ledger; replayed challenges are rejected even if the
                 signature is valid.

The verifier is **stateful** (registered credentials + used nonces). It is
thread-safe via a single ``threading.RLock``. Persistence is the caller's
responsibility — production wires a ``CredentialStore`` callable at
construction time; tests use the in-memory default.

Security properties enforced here:

1. Constant-time hash compare (``hmac.compare_digest``).
2. One-shot challenge nonces (replay rejection).
3. No exception leaks (every error path returns
   ``VerificationResult(accepted=False, reason=...)`` with a short string;
   the actual exception is logged at WARNING but never returned).
4. Static credential ceiling (``max_tier_for``): pin → ``PIN_VERIFIED``,
   passkey/webauthn → ``STRONG_CRED``, anything else → ``ANONYMOUS``.

E4 (no unsigned amendment active) and E6 (no tool outside capabilities)
are NOT this verifier's concern; this is purely about credential math.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from k1.selfmodel.ports.credential import ICredentialPort
from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    IdentityTier,
    VerificationResult,
)

__all__ = [
    "Ed25519CredentialVerifier",
    "PinCredential",
    "PasskeyCredential",
    "hash_pin",
    "verify_pin_hash",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# PIN hashing (stdlib scrypt, parameter-tagged format)
# ---------------------------------------------------------------------
# Format: scrypt$<n>$<r>$<p>$<salt_b64>$<dk_b64>
# n=2**14, r=8, p=1 — OWASP-recommended interactive baseline.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16
_HASH_PREFIX = "scrypt"


def hash_pin(pin: str, *, salt: bytes | None = None) -> str:
    """Compute a parameter-tagged scrypt hash of ``pin``.

    The returned string can be passed verbatim to ``verify_pin_hash``.
    Caller is responsible for normalising the PIN (trimming whitespace,
    rejecting empty input). We DO encode in UTF-8 (BMP-safe).
    """
    if not isinstance(pin, str):
        raise TypeError("pin must be str")
    if not pin:
        raise ValueError("pin must be non-empty")
    salt = salt if salt is not None else os.urandom(_SCRYPT_SALT_BYTES)
    dk = hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "$".join(
        [
            _HASH_PREFIX,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(dk).decode("ascii"),
        ]
    )


def verify_pin_hash(pin: str, encoded: str) -> bool:
    """Constant-time verification of ``pin`` against ``encoded`` hash."""
    if not isinstance(pin, str) or not isinstance(encoded, str):
        return False
    parts = encoded.split("$")
    if len(parts) != 6 or parts[0] != _HASH_PREFIX:
        return False
    try:
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = base64.b64decode(parts[4])
        expected = base64.b64decode(parts[5])
    except (ValueError, base64.binascii.Error):
        return False
    try:
        dk = hashlib.scrypt(
            pin.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(dk, expected)


# ---------------------------------------------------------------------
# In-memory credential records
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class PinCredential:
    """Stored PIN entry: ``encoded`` is the output of :func:`hash_pin`."""

    profile_id: str
    encoded: str
    created_at_ms: int = 0


@dataclass(frozen=True)
class PasskeyCredential:
    """Stored passkey entry: Ed25519 public key bound to a profile."""

    profile_id: str
    credential_id: str
    public_key: bytes  # 32 raw bytes (Ed25519 verify key)
    created_at_ms: int = 0


CredentialLookup = Callable[[str], "tuple[list[PinCredential], list[PasskeyCredential]]"]


# ---------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------
class Ed25519CredentialVerifier(ICredentialPort):
    """In-memory Ed25519 + scrypt PIN credential verifier."""

    __slots__ = (
        "_lock",
        "_pins",
        "_passkeys",
        "_used_nonces",
        "_max_used_nonces",
    )

    def __init__(self, *, max_used_nonces: int = 4096) -> None:
        if max_used_nonces <= 0:
            raise ValueError("max_used_nonces must be positive")
        self._lock = threading.RLock()
        self._pins: dict[str, PinCredential] = {}
        # profile_id -> {credential_id: PasskeyCredential}
        self._passkeys: dict[str, dict[str, PasskeyCredential]] = {}
        self._used_nonces: set[str] = set()
        self._max_used_nonces = max_used_nonces

    # ------------------------------------------------------------------
    # Registration (admin path; not part of ICredentialPort)
    # ------------------------------------------------------------------
    def register_pin(self, profile_id: str, pin: str, *, now_ms: int = 0) -> None:
        if not profile_id:
            raise ValueError("profile_id must be non-empty")
        encoded = hash_pin(pin)
        with self._lock:
            self._pins[profile_id] = PinCredential(
                profile_id=profile_id,
                encoded=encoded,
                created_at_ms=now_ms,
            )

    def register_passkey(
        self,
        profile_id: str,
        credential_id: str,
        public_key: bytes,
        *,
        now_ms: int = 0,
    ) -> None:
        if not profile_id:
            raise ValueError("profile_id must be non-empty")
        if not credential_id:
            raise ValueError("credential_id must be non-empty")
        if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != 32:
            raise ValueError("public_key must be 32 raw Ed25519 bytes")
        with self._lock:
            self._passkeys.setdefault(profile_id, {})[credential_id] = PasskeyCredential(
                profile_id=profile_id,
                credential_id=credential_id,
                public_key=bytes(public_key),
                created_at_ms=now_ms,
            )

    def unregister(self, profile_id: str) -> None:
        with self._lock:
            self._pins.pop(profile_id, None)
            self._passkeys.pop(profile_id, None)

    def reset_nonces(self) -> None:
        """Test helper: clear the replay ledger."""
        with self._lock:
            self._used_nonces.clear()

    # ------------------------------------------------------------------
    # ICredentialPort
    # ------------------------------------------------------------------
    def max_tier_for(self, kind: str) -> IdentityTier:
        if kind == "pin":
            return IdentityTier.PIN_VERIFIED
        if kind in ("passkey", "webauthn"):
            return IdentityTier.STRONG_CRED
        return IdentityTier.ANONYMOUS

    def verify(
        self,
        profile_id: str,
        credential: CredentialPresentation,
    ) -> VerificationResult:
        if not isinstance(credential, CredentialPresentation):
            return VerificationResult(accepted=False, reason="malformed_credential")
        if not profile_id:
            return VerificationResult(accepted=False, reason="missing_profile_id")
        kind = credential.kind
        try:
            if kind == "pin":
                return self._verify_pin(profile_id, credential)
            if kind in ("passkey", "webauthn"):
                return self._verify_passkey(profile_id, credential)
            return VerificationResult(accepted=False, reason=f"unsupported_kind:{kind}")
        except Exception:
            logger.warning(
                "credential_verifier: unexpected error verifying profile=%s kind=%s",
                profile_id,
                kind,
                exc_info=True,
            )
            return VerificationResult(accepted=False, reason="verifier_error")

    # ------------------------------------------------------------------
    # PIN path
    # ------------------------------------------------------------------
    def _verify_pin(
        self, profile_id: str, credential: CredentialPresentation
    ) -> VerificationResult:
        pin = credential.payload.get("pin")
        if not isinstance(pin, str) or not pin:
            return VerificationResult(accepted=False, reason="malformed_pin")
        with self._lock:
            record = self._pins.get(profile_id)
        if record is None:
            # Constant-time-equivalent: still compute scrypt against a
            # dummy hash so timing doesn't reveal "no PIN registered".
            verify_pin_hash(pin, hash_pin("__decoy__"))
            return VerificationResult(accepted=False, reason="no_credential")
        if verify_pin_hash(pin, record.encoded):
            return VerificationResult(
                accepted=True,
                promoted_to_tier=IdentityTier.PIN_VERIFIED,
                reason="ok",
            )
        return VerificationResult(accepted=False, reason="pin_mismatch")

    # ------------------------------------------------------------------
    # Passkey / WebAuthn path
    # ------------------------------------------------------------------
    def _verify_passkey(
        self, profile_id: str, credential: CredentialPresentation
    ) -> VerificationResult:
        payload = credential.payload
        credential_id = payload.get("credential_id")
        challenge = payload.get("challenge")
        signature = payload.get("signature")
        if not isinstance(credential_id, str) or not credential_id:
            return VerificationResult(accepted=False, reason="missing_credential_id")
        if not isinstance(challenge, (bytes, str)) or not challenge:
            return VerificationResult(accepted=False, reason="missing_challenge")
        if not isinstance(signature, (bytes, str)) or not signature:
            return VerificationResult(accepted=False, reason="missing_signature")

        challenge_bytes = _coerce_bytes(challenge)
        signature_bytes = _coerce_bytes(signature)
        if challenge_bytes is None or signature_bytes is None:
            return VerificationResult(accepted=False, reason="malformed_payload")

        # Replay check: nonce = profile_id || credential_id || challenge.
        nonce_key = f"{profile_id}:{credential_id}:{challenge_bytes.hex()}"
        with self._lock:
            if nonce_key in self._used_nonces:
                return VerificationResult(accepted=False, reason="replay_detected")
            record = self._passkeys.get(profile_id, {}).get(credential_id)
        if record is None:
            return VerificationResult(accepted=False, reason="no_credential")

        try:
            VerifyKey(record.public_key).verify(challenge_bytes, signature_bytes)
        except BadSignatureError:
            return VerificationResult(accepted=False, reason="signature_invalid")

        with self._lock:
            self._record_nonce(nonce_key)
        return VerificationResult(
            accepted=True,
            promoted_to_tier=IdentityTier.STRONG_CRED,
            reason="ok",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _record_nonce(self, nonce_key: str) -> None:
        # Bound the ledger; evict oldest by random sampling when full.
        if len(self._used_nonces) >= self._max_used_nonces:
            # ``set.pop`` removes an arbitrary element — sufficient for
            # bounded growth; not relied on for ordering.
            self._used_nonces.pop()
        self._used_nonces.add(nonce_key)


def _coerce_bytes(value: object) -> bytes | None:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        # Accept either base64 or hex; otherwise UTF-8.
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, base64.binascii.Error):
            pass
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
        return value.encode("utf-8")
    return None


# Re-export ``secrets`` token helper for symmetry with identity_session.
generate_challenge = secrets.token_bytes
