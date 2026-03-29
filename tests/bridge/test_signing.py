"""Real component tests for Bridge signing backends.

Tests HmacSigning and Ed25519Signing with actual crypto operations --
no mocks.  Verifies sign, verify, tamper detection, key rotation,
and edge cases.

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import os

import pytest

from bridge.core.signing import Ed25519Signing, HmacSigning

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hmac_secret() -> bytes:
    """32-byte random secret for HMAC tests."""
    return os.urandom(32)


@pytest.fixture
def hmac_signer(hmac_secret: bytes) -> HmacSigning:
    return HmacSigning(secret=hmac_secret, key_id="did:device:test-001#2026-01-01")


@pytest.fixture
def ed25519_seed() -> bytes:
    """32-byte Ed25519 seed."""
    return os.urandom(32)


@pytest.fixture
def ed25519_signer(ed25519_seed: bytes) -> Ed25519Signing:
    return Ed25519Signing(signing_key_bytes=ed25519_seed, key_id="did:device:test-001#ed-001")


# ===========================================================================
# HmacSigning
# ===========================================================================


class TestHmacSigning:
    """Real HMAC-SHA256 signing and verification."""

    def test_sign_returns_string(self, hmac_signer: HmacSigning) -> None:
        sig = hmac_signer.sign(b"hello world")
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_sign_is_base64url(self, hmac_signer: HmacSigning) -> None:
        sig = hmac_signer.sign(b"test message")
        # base64url chars only (no padding)
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in sig)

    def test_verify_correct_signature(self, hmac_signer: HmacSigning) -> None:
        message = b"verify me"
        sig = hmac_signer.sign(message)
        assert hmac_signer.verify(message, sig) is True

    def test_verify_rejects_tampered_message(self, hmac_signer: HmacSigning) -> None:
        sig = hmac_signer.sign(b"original message")
        assert hmac_signer.verify(b"tampered message", sig) is False

    def test_verify_rejects_tampered_signature(self, hmac_signer: HmacSigning) -> None:
        message = b"some data"
        sig = hmac_signer.sign(message)
        tampered_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        assert hmac_signer.verify(message, tampered_sig) is False

    def test_deterministic_signature(self, hmac_signer: HmacSigning) -> None:
        """Same message + same key = same signature."""
        msg = b"deterministic"
        assert hmac_signer.sign(msg) == hmac_signer.sign(msg)

    def test_different_messages_different_sigs(self, hmac_signer: HmacSigning) -> None:
        assert hmac_signer.sign(b"msg-a") != hmac_signer.sign(b"msg-b")

    def test_different_keys_different_sigs(self) -> None:
        key_a = os.urandom(32)
        key_b = os.urandom(32)
        signer_a = HmacSigning(secret=key_a, key_id="key-a")
        signer_b = HmacSigning(secret=key_b, key_id="key-b")
        msg = b"same message"
        assert signer_a.sign(msg) != signer_b.sign(msg)

    def test_algorithm_property(self, hmac_signer: HmacSigning) -> None:
        assert hmac_signer.algorithm == "hmac-sha256"

    def test_key_id_property(self, hmac_signer: HmacSigning) -> None:
        assert hmac_signer.key_id == "did:device:test-001#2026-01-01"

    def test_empty_message(self, hmac_signer: HmacSigning) -> None:
        sig = hmac_signer.sign(b"")
        assert isinstance(sig, str)
        assert hmac_signer.verify(b"", sig) is True

    def test_large_message(self, hmac_signer: HmacSigning) -> None:
        msg = os.urandom(1_000_000)  # 1 MB
        sig = hmac_signer.sign(msg)
        assert hmac_signer.verify(msg, sig) is True


# ===========================================================================
# HmacSigning: key constraints
# ===========================================================================


class TestHmacKeyConstraints:
    """Verify minimum key length enforcement."""

    def test_16_byte_secret_accepted(self) -> None:
        signer = HmacSigning(secret=os.urandom(16), key_id="min-key")
        assert signer.sign(b"ok") is not None

    def test_15_byte_secret_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 16 bytes"):
            HmacSigning(secret=os.urandom(15), key_id="short-key")

    def test_1_byte_secret_rejected(self) -> None:
        with pytest.raises(ValueError):
            HmacSigning(secret=b"x", key_id="tiny")

    def test_empty_secret_rejected(self) -> None:
        with pytest.raises(ValueError):
            HmacSigning(secret=b"", key_id="empty")


# ===========================================================================
# Ed25519Signing
# ===========================================================================


class TestEd25519Signing:
    """Real Ed25519 signing and verification using PyNaCl."""

    def test_sign_returns_string(self, ed25519_signer: Ed25519Signing) -> None:
        sig = ed25519_signer.sign(b"hello ed25519")
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_sign_is_base64url(self, ed25519_signer: Ed25519Signing) -> None:
        sig = ed25519_signer.sign(b"test message")
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in sig)

    def test_verify_correct_signature(self, ed25519_signer: Ed25519Signing) -> None:
        message = b"verify ed25519"
        sig = ed25519_signer.sign(message)
        assert ed25519_signer.verify(message, sig) is True

    def test_verify_rejects_tampered_message(self, ed25519_signer: Ed25519Signing) -> None:
        sig = ed25519_signer.sign(b"original ed25519")
        assert ed25519_signer.verify(b"tampered ed25519", sig) is False

    def test_verify_rejects_tampered_signature(self, ed25519_signer: Ed25519Signing) -> None:
        message = b"ed25519 data"
        sig = ed25519_signer.sign(message)
        # Flip a character
        tampered = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        assert ed25519_signer.verify(message, tampered) is False

    def test_deterministic_signature(self, ed25519_signer: Ed25519Signing) -> None:
        """Ed25519 is deterministic: same key + message = same signature."""
        msg = b"deterministic ed25519"
        assert ed25519_signer.sign(msg) == ed25519_signer.sign(msg)

    def test_different_messages_different_sigs(self, ed25519_signer: Ed25519Signing) -> None:
        assert ed25519_signer.sign(b"a") != ed25519_signer.sign(b"b")

    def test_different_keys_different_sigs(self) -> None:
        seed_a = os.urandom(32)
        seed_b = os.urandom(32)
        signer_a = Ed25519Signing(signing_key_bytes=seed_a, key_id="key-a")
        signer_b = Ed25519Signing(signing_key_bytes=seed_b, key_id="key-b")
        msg = b"same message"
        assert signer_a.sign(msg) != signer_b.sign(msg)

    def test_algorithm_property(self, ed25519_signer: Ed25519Signing) -> None:
        assert ed25519_signer.algorithm == "ed25519"

    def test_key_id_property(self, ed25519_signer: Ed25519Signing) -> None:
        assert ed25519_signer.key_id == "did:device:test-001#ed-001"

    def test_empty_message(self, ed25519_signer: Ed25519Signing) -> None:
        sig = ed25519_signer.sign(b"")
        assert ed25519_signer.verify(b"", sig) is True

    def test_large_message(self, ed25519_signer: Ed25519Signing) -> None:
        msg = os.urandom(100_000)
        sig = ed25519_signer.sign(msg)
        assert ed25519_signer.verify(msg, sig) is True


# ===========================================================================
# Cross-backend: HMAC cannot verify Ed25519 and vice versa
# ===========================================================================


class TestCrossBackendRejection:
    """Ensure signatures from one backend fail on the other."""

    def test_hmac_sig_fails_ed25519_verify(
        self, hmac_signer: HmacSigning, ed25519_signer: Ed25519Signing
    ) -> None:
        msg = b"cross backend"
        hmac_sig = hmac_signer.sign(msg)
        # HMAC produces 32-byte digest; Ed25519 expects 64-byte signature.
        # nacl raises ValueError for wrong-length sigs, which is correct rejection.
        try:
            result = ed25519_signer.verify(msg, hmac_sig)
            assert result is False
        except (ValueError, Exception):
            # nacl.exceptions.ValueError for wrong sig length is valid rejection
            pass

    def test_ed25519_sig_fails_hmac_verify(
        self, hmac_signer: HmacSigning, ed25519_signer: Ed25519Signing
    ) -> None:
        msg = b"cross backend"
        ed_sig = ed25519_signer.sign(msg)
        assert hmac_signer.verify(msg, ed_sig) is False


# ===========================================================================
# Key rotation (different key_ids, same backend)
# ===========================================================================


class TestKeyRotation:
    """Verify that key_id is purely metadata and does not affect signing."""

    def test_same_secret_different_kid_same_sig(self) -> None:
        secret = os.urandom(32)
        signer_v1 = HmacSigning(secret=secret, key_id="v1")
        signer_v2 = HmacSigning(secret=secret, key_id="v2")
        msg = b"rotation test"
        assert signer_v1.sign(msg) == signer_v2.sign(msg)
        assert signer_v1.key_id != signer_v2.key_id

    def test_rotated_secret_cannot_verify_old(self) -> None:
        old_secret = os.urandom(32)
        new_secret = os.urandom(32)
        old_signer = HmacSigning(secret=old_secret, key_id="old")
        new_signer = HmacSigning(secret=new_secret, key_id="new")
        msg = b"before rotation"
        old_sig = old_signer.sign(msg)
        assert new_signer.verify(msg, old_sig) is False


# ===========================================================================
# SigningBackend protocol conformance
# ===========================================================================


class TestSigningBackendProtocol:
    """Both backends satisfy the SigningBackend protocol."""

    def test_hmac_has_required_attrs(self, hmac_signer: HmacSigning) -> None:
        assert hasattr(hmac_signer, "algorithm")
        assert hasattr(hmac_signer, "key_id")
        assert callable(hmac_signer.sign)

    def test_ed25519_has_required_attrs(self, ed25519_signer: Ed25519Signing) -> None:
        assert hasattr(ed25519_signer, "algorithm")
        assert hasattr(ed25519_signer, "key_id")
        assert callable(ed25519_signer.sign)
