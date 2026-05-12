"""Pluggable envelope signing backends for the Bridge.

Supports HMAC-SHA256 (development) and Ed25519 (production).
Key rotation is handled via ``sig_kid`` identifiers.

Per bridge/contracts/command_port.protocol.yaml envelope_building.bridge_computes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signing result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SigningResult:
    """Output of a signing operation."""

    sig: str  # base64url-encoded signature
    sig_alg: str  # algorithm identifier
    sig_kid: str  # key identifier


# ---------------------------------------------------------------------------
# Protocol (pluggable backend)
# ---------------------------------------------------------------------------


@runtime_checkable
class SigningBackend(Protocol):
    """Protocol for envelope signing backends."""

    @property
    def algorithm(self) -> str:
        """Return the algorithm identifier (e.g. ``hmac-sha256``, ``ed25519``)."""
        ...

    @property
    def key_id(self) -> str:
        """Return the current key identifier."""
        ...

    def sign(self, message: bytes) -> str:
        """Sign *message* and return base64url-encoded signature."""
        ...


# ---------------------------------------------------------------------------
# HMAC-SHA256 backend (development / testing)
# ---------------------------------------------------------------------------


class HmacSigning:
    """HMAC-SHA256 signing backend for development and testing.

    Parameters
    ----------
    secret : bytes
        Shared secret key (min 32 bytes recommended).
    key_id : str
        Key identifier for ``sig_kid`` field (e.g. ``did:device:dev-001#2026-01-01``).
    """

    def __init__(self, secret: bytes, key_id: str) -> None:
        if len(secret) < 16:
            msg = "HMAC secret must be at least 16 bytes"
            raise ValueError(msg)
        self._secret = secret
        self._key_id = key_id

    @property
    def algorithm(self) -> str:
        return "hmac-sha256"

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, message: bytes) -> str:
        """Produce HMAC-SHA256 signature of *message*, base64url-encoded."""
        raw = hmac.new(self._secret, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def verify(self, message: bytes, signature_b64: str) -> bool:
        """Verify an HMAC-SHA256 signature. Returns True on match."""
        expected = self.sign(message)
        return hmac.compare_digest(expected, signature_b64)


# ---------------------------------------------------------------------------
# Ed25519 backend (production)
# ---------------------------------------------------------------------------


class Ed25519Signing:
    """Ed25519 signing backend for production use.

    Uses ``nacl.signing`` for EdDSA signatures.

    Parameters
    ----------
    signing_key_bytes : bytes
        32-byte Ed25519 seed or 64-byte expanded key.
    key_id : str
        Key identifier for ``sig_kid`` field.
    """

    def __init__(self, signing_key_bytes: bytes, key_id: str) -> None:
        try:
            from nacl.signing import SigningKey  # noqa: PLC0415
        except ImportError as exc:
            msg = "PyNaCl is required for Ed25519 signing: pip install pynacl"
            raise ImportError(msg) from exc
        self._signing_key = SigningKey(signing_key_bytes[:32])
        self._key_id = key_id

    @property
    def algorithm(self) -> str:
        return "Ed25519SHA512"

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, message: bytes) -> str:
        """Produce Ed25519 signature of *message*, base64url-encoded."""
        signed = self._signing_key.sign(message)
        # signed.signature is the 64-byte raw signature
        return base64.urlsafe_b64encode(signed.signature).rstrip(b"=").decode("ascii")

    def verify(self, message: bytes, signature_b64: str) -> bool:
        """Verify an Ed25519 signature. Returns True on valid."""
        from nacl.exceptions import BadSignatureError  # noqa: PLC0415

        verify_key = self._signing_key.verify_key
        padding = "=" * (-len(signature_b64) % 4)
        sig_bytes = base64.urlsafe_b64decode(f"{signature_b64}{padding}".encode("ascii"))
        try:
            verify_key.verify(message, sig_bytes)
            return True
        except BadSignatureError:
            return False
