from __future__ import annotations

import hashlib

from nacl.encoding import URLSafeBase64Encoder  # type: ignore[import]
from nacl.signing import SigningKey  # type: ignore[import]
from ward import raises, test  # type: ignore[attr-defined]

from k0.security import (
    SignatureVerificationError,
    canonical_envelope,
    canonical_json,
    hash_payload,
    verify_signature,
)

SIGNING_KEY = SigningKey(bytes(range(32)))
VERIFY_KEY_B64 = SIGNING_KEY.verify_key.encode(URLSafeBase64Encoder).decode("ascii")


@test("canonical_json renders keys in sorted order with compact separators")
def _() -> None:
    payload = {"b": 2, "a": 1}
    assert canonical_json(payload) == '{"a":1,"b":2}'


@test("canonical_envelope excludes signature field before serialisation")
def _() -> None:
    envelope = {"device_id": "device", "sig": "ignored", "tenant_id": "tenant"}
    canonical = canonical_envelope(envelope).decode("utf-8")
    assert canonical == canonical_json({"device_id": "device", "tenant_id": "tenant"})


@test("hash_payload returns sha256 hex digest and handles empty bodies")
def _() -> None:
    assert hash_payload(None) is None
    body = b"payload"
    assert hash_payload(body) == hashlib.sha256(body).hexdigest()


@test("verify_signature validates ed25519 signatures and rejects tampering")
def _() -> None:
    envelope = {"tenant_id": "tenant", "device_id": "device"}
    message = canonical_envelope(envelope)
    signature = SIGNING_KEY.sign(message).signature
    signature_b64 = URLSafeBase64Encoder.encode(signature).decode("ascii")

    verify_signature(message, signature_b64, VERIFY_KEY_B64)

    with raises(SignatureVerificationError):
        verify_signature(message, signature_b64[::-1], VERIFY_KEY_B64)
