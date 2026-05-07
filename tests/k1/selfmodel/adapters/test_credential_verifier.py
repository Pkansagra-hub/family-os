"""Unit tests for ``Ed25519CredentialVerifier`` (M3.E1.I1)."""

from __future__ import annotations

import base64

import pytest
from nacl.signing import SigningKey

from k1.selfmodel.adapters.credential_verifier import (
    Ed25519CredentialVerifier,
    PasskeyCredential,
    PinCredential,
    _coerce_bytes,
    generate_challenge,
    hash_pin,
    verify_pin_hash,
)
from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    IdentityTier,
)


T_MS = 1_700_000_000_000


# ---------------------------------------------------------------------
# hash_pin / verify_pin_hash
# ---------------------------------------------------------------------
def test_hash_pin_round_trip() -> None:
    encoded = hash_pin("1234")
    assert encoded.startswith("scrypt$")
    assert verify_pin_hash("1234", encoded) is True
    assert verify_pin_hash("0000", encoded) is False


def test_hash_pin_uses_random_salt() -> None:
    a = hash_pin("1234")
    b = hash_pin("1234")
    assert a != b


def test_hash_pin_rejects_empty_pin() -> None:
    with pytest.raises(ValueError):
        hash_pin("")


def test_hash_pin_rejects_non_str() -> None:
    with pytest.raises(TypeError):
        hash_pin(1234)  # type: ignore[arg-type]


def test_verify_pin_hash_returns_false_on_malformed() -> None:
    assert verify_pin_hash("1234", "not-a-hash") is False
    assert verify_pin_hash("1234", "scrypt$bad") is False
    assert verify_pin_hash("1234", "argon2$1$2$3$x$y") is False
    # Non-int parameters
    assert verify_pin_hash("1234", "scrypt$x$8$1$AAAA$AAAA") is False
    # Bad base64
    assert verify_pin_hash("1234", "scrypt$16384$8$1$!!!$!!!") is False


def test_verify_pin_hash_rejects_non_str_inputs() -> None:
    assert verify_pin_hash(1234, "scrypt$1$1$1$AAAA$AAAA") is False  # type: ignore[arg-type]
    assert verify_pin_hash("1234", 0) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Verifier construction
# ---------------------------------------------------------------------
def test_constructor_validates_max_used_nonces() -> None:
    with pytest.raises(ValueError):
        Ed25519CredentialVerifier(max_used_nonces=0)
    with pytest.raises(ValueError):
        Ed25519CredentialVerifier(max_used_nonces=-1)


def test_max_tier_for_known_kinds() -> None:
    v = Ed25519CredentialVerifier()
    assert v.max_tier_for("pin") == IdentityTier.PIN_VERIFIED
    assert v.max_tier_for("passkey") == IdentityTier.STRONG_CRED
    assert v.max_tier_for("webauthn") == IdentityTier.STRONG_CRED
    assert v.max_tier_for("anything-else") == IdentityTier.ANONYMOUS


# ---------------------------------------------------------------------
# Registration validation
# ---------------------------------------------------------------------
def test_register_pin_requires_profile_id() -> None:
    v = Ed25519CredentialVerifier()
    with pytest.raises(ValueError):
        v.register_pin("", "1234")


def test_register_passkey_validates_inputs() -> None:
    v = Ed25519CredentialVerifier()
    pk = bytes(SigningKey.generate().verify_key)
    with pytest.raises(ValueError):
        v.register_passkey("", "cred1", pk)
    with pytest.raises(ValueError):
        v.register_passkey("p", "", pk)
    with pytest.raises(ValueError):
        v.register_passkey("p", "cred1", b"too short")
    with pytest.raises(ValueError):
        v.register_passkey("p", "cred1", "not bytes")  # type: ignore[arg-type]


def test_unregister_removes_pin_and_passkey() -> None:
    v = Ed25519CredentialVerifier()
    v.register_pin("p1", "1234")
    pk = bytes(SigningKey.generate().verify_key)
    v.register_passkey("p1", "c1", pk)
    v.unregister("p1")
    res = v.verify("p1", CredentialPresentation(kind="pin", payload={"pin": "1234"}, presented_at_ms=T_MS))
    assert res.accepted is False


# ---------------------------------------------------------------------
# verify() — kind dispatch + edge cases
# ---------------------------------------------------------------------
def test_verify_rejects_non_credentialpresentation() -> None:
    v = Ed25519CredentialVerifier()
    res = v.verify("p1", "nope")  # type: ignore[arg-type]
    assert res.accepted is False
    assert res.reason == "malformed_credential"


def test_verify_requires_profile_id() -> None:
    v = Ed25519CredentialVerifier()
    cred = CredentialPresentation(kind="pin", payload={"pin": "1234"}, presented_at_ms=T_MS)
    res = v.verify("", cred)
    assert res.accepted is False
    assert res.reason == "missing_profile_id"


def test_verify_unsupported_kind() -> None:
    v = Ed25519CredentialVerifier()
    cred = CredentialPresentation(kind="totp", payload={}, presented_at_ms=T_MS)
    res = v.verify("p1", cred)
    assert res.accepted is False
    assert res.reason.startswith("unsupported_kind:")


# ---------------------------------------------------------------------
# PIN path
# ---------------------------------------------------------------------
def test_pin_happy_path_promotes_to_pin_verified() -> None:
    v = Ed25519CredentialVerifier()
    v.register_pin("p1", "0420")
    res = v.verify(
        "p1",
        CredentialPresentation(kind="pin", payload={"pin": "0420"}, presented_at_ms=T_MS),
    )
    assert res.accepted is True
    assert res.promoted_to_tier == IdentityTier.PIN_VERIFIED


def test_pin_wrong_value_returns_pin_mismatch() -> None:
    v = Ed25519CredentialVerifier()
    v.register_pin("p1", "0420")
    res = v.verify(
        "p1",
        CredentialPresentation(kind="pin", payload={"pin": "0000"}, presented_at_ms=T_MS),
    )
    assert res.accepted is False
    assert res.reason == "pin_mismatch"


def test_pin_no_credential_for_profile() -> None:
    v = Ed25519CredentialVerifier()
    res = v.verify(
        "missing",
        CredentialPresentation(kind="pin", payload={"pin": "0000"}, presented_at_ms=T_MS),
    )
    assert res.accepted is False
    assert res.reason == "no_credential"


def test_pin_malformed_payload() -> None:
    v = Ed25519CredentialVerifier()
    v.register_pin("p1", "0420")
    res = v.verify(
        "p1",
        CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS),
    )
    assert res.accepted is False
    assert res.reason == "malformed_pin"
    res2 = v.verify(
        "p1",
        CredentialPresentation(kind="pin", payload={"pin": ""}, presented_at_ms=T_MS),
    )
    assert res2.accepted is False
    assert res2.reason == "malformed_pin"


# ---------------------------------------------------------------------
# Passkey path
# ---------------------------------------------------------------------
def _make_passkey(profile_id: str = "p1", credential_id: str = "c1"):
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    return sk, pk


def test_passkey_happy_path_promotes_to_strong_cred() -> None:
    v = Ed25519CredentialVerifier()
    sk, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    challenge = generate_challenge(32)
    signature = sk.sign(challenge).signature
    res = v.verify(
        "p1",
        CredentialPresentation(
            kind="passkey",
            payload={
                "credential_id": "c1",
                "challenge": challenge,
                "signature": signature,
            },
            presented_at_ms=T_MS,
        ),
    )
    assert res.accepted is True
    assert res.promoted_to_tier == IdentityTier.STRONG_CRED


def test_passkey_replay_rejected() -> None:
    v = Ed25519CredentialVerifier()
    sk, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    challenge = generate_challenge(32)
    signature = sk.sign(challenge).signature
    cred = CredentialPresentation(
        kind="passkey",
        payload={"credential_id": "c1", "challenge": challenge, "signature": signature},
        presented_at_ms=T_MS,
    )
    assert v.verify("p1", cred).accepted is True
    res2 = v.verify("p1", cred)
    assert res2.accepted is False
    assert res2.reason == "replay_detected"


def test_passkey_bad_signature_rejected() -> None:
    v = Ed25519CredentialVerifier()
    sk, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    challenge = generate_challenge(32)
    bad_sig = bytes(64)
    res = v.verify(
        "p1",
        CredentialPresentation(
            kind="passkey",
            payload={"credential_id": "c1", "challenge": challenge, "signature": bad_sig},
            presented_at_ms=T_MS,
        ),
    )
    assert res.accepted is False
    assert res.reason == "signature_invalid"


def test_passkey_unknown_credential_id() -> None:
    v = Ed25519CredentialVerifier()
    _, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    res = v.verify(
        "p1",
        CredentialPresentation(
            kind="passkey",
            payload={
                "credential_id": "missing",
                "challenge": b"x" * 16,
                "signature": b"y" * 64,
            },
            presented_at_ms=T_MS,
        ),
    )
    assert res.accepted is False
    assert res.reason == "no_credential"


def test_passkey_payload_field_validation() -> None:
    v = Ed25519CredentialVerifier()
    cases = [
        {"credential_id": "", "challenge": b"x", "signature": b"y"},
        {"credential_id": "c", "challenge": "", "signature": b"y"},
        {"credential_id": "c", "challenge": b"x", "signature": ""},
    ]
    expected = ["missing_credential_id", "missing_challenge", "missing_signature"]
    for payload, reason in zip(cases, expected):
        res = v.verify(
            "p1",
            CredentialPresentation(kind="passkey", payload=payload, presented_at_ms=T_MS),
        )
        assert res.accepted is False
        assert res.reason == reason


def test_passkey_accepts_base64_and_hex_inputs() -> None:
    v = Ed25519CredentialVerifier()
    sk, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    challenge = generate_challenge(32)
    signature = sk.sign(challenge).signature
    res = v.verify(
        "p1",
        CredentialPresentation(
            kind="passkey",
            payload={
                "credential_id": "c1",
                "challenge": base64.b64encode(challenge).decode("ascii"),
                "signature": base64.b64encode(signature).decode("ascii"),
            },
            presented_at_ms=T_MS,
        ),
    )
    assert res.accepted is True


def test_webauthn_kind_is_alias_for_passkey() -> None:
    v = Ed25519CredentialVerifier()
    sk, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    challenge = generate_challenge(32)
    signature = sk.sign(challenge).signature
    res = v.verify(
        "p1",
        CredentialPresentation(
            kind="webauthn",
            payload={"credential_id": "c1", "challenge": challenge, "signature": signature},
            presented_at_ms=T_MS,
        ),
    )
    assert res.accepted is True
    assert res.promoted_to_tier == IdentityTier.STRONG_CRED


# ---------------------------------------------------------------------
# Internal: nonce eviction + reset_nonces
# ---------------------------------------------------------------------
def test_nonce_ledger_bounded_and_resettable() -> None:
    v = Ed25519CredentialVerifier(max_used_nonces=3)
    sk, pk = _make_passkey()
    v.register_passkey("p1", "c1", pk)
    for _ in range(5):
        challenge = generate_challenge(8)
        signature = sk.sign(challenge).signature
        res = v.verify(
            "p1",
            CredentialPresentation(
                kind="passkey",
                payload={"credential_id": "c1", "challenge": challenge, "signature": signature},
                presented_at_ms=T_MS,
            ),
        )
        assert res.accepted is True
    # Ledger should not exceed 3.
    assert len(v._used_nonces) <= 3
    v.reset_nonces()
    assert v._used_nonces == set()


# ---------------------------------------------------------------------
# Internal exception path → verifier_error
# ---------------------------------------------------------------------
def test_verifier_error_on_internal_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    v = Ed25519CredentialVerifier()
    v.register_pin("p1", "1234")

    def boom(self, profile_id, credential):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(Ed25519CredentialVerifier, "_verify_pin", boom)
    res = v.verify(
        "p1",
        CredentialPresentation(kind="pin", payload={"pin": "1234"}, presented_at_ms=T_MS),
    )
    assert res.accepted is False
    assert res.reason == "verifier_error"


# ---------------------------------------------------------------------
# _coerce_bytes coverage
# ---------------------------------------------------------------------
def test_coerce_bytes_variants() -> None:
    assert _coerce_bytes(b"abc") == b"abc"
    assert _coerce_bytes(bytearray(b"abc")) == b"abc"
    assert _coerce_bytes(base64.b64encode(b"abc").decode("ascii")) == b"abc"
    assert _coerce_bytes("48656c6c6f") == b"Hello"
    # Falls back to UTF-8 (must not look like base64 or hex)
    assert _coerce_bytes("zzz") == b"zzz"
    assert _coerce_bytes(123) is None


# ---------------------------------------------------------------------
# Frozen-dataclass smoke
# ---------------------------------------------------------------------
def test_credential_records_are_frozen() -> None:
    c = PinCredential(profile_id="p", encoded="x", created_at_ms=1)
    with pytest.raises(Exception):
        c.encoded = "y"  # type: ignore[misc]
    p = PasskeyCredential(profile_id="p", credential_id="c", public_key=b"x" * 32)
    with pytest.raises(Exception):
        p.credential_id = "z"  # type: ignore[misc]
