"""Ward + Hypothesis coverage for canonical idempotency derivation."""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import raises, test  # type: ignore[attr-defined]

from k0.idem import canonical_idem_components, derive_idem_key

BASE_PAYLOAD_HASH = "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2"
BASE_ENVELOPE: dict[str, Any] = {
    "tenant_id": "tenant-123",
    "space_id": "space-alpha",
    "actor": "device-123",
    "topic": "memory.snapshot.commit",
    "schema_uri": "https://contracts.family-ai.dev/schemas/memory.snapshot.json",
    "schema_version": "1.0.0",
}
EXPECTED_BASE_IDEM_KEY = (
    "81336ba5cd6b4ec72fd42d12749dd25b06a9cdc3e2ab154f47bcae2e08e5a334"
)


@test("canonical derivation matches reference digest")
def _() -> None:
    envelope = dict(BASE_ENVELOPE)
    components = canonical_idem_components(envelope, payload_hash=BASE_PAYLOAD_HASH)
    assert components == [
        "tenant-123",
        "space-alpha",
        "device-123",
        "memory.snapshot.commit",
        "https://contracts.family-ai.dev/schemas/memory.snapshot.json",
        "1.0.0",
        BASE_PAYLOAD_HASH,
    ]
    digest = derive_idem_key(envelope, payload_hash=BASE_PAYLOAD_HASH)
    assert digest == EXPECTED_BASE_IDEM_KEY


@test("non-canonical fields do not influence idem key")
def _() -> None:
    envelope = dict(BASE_ENVELOPE)
    envelope["noise"] = "value-1"
    key_one = derive_idem_key(envelope, payload_hash=BASE_PAYLOAD_HASH)
    envelope["noise"] = "value-2"
    key_two = derive_idem_key(envelope, payload_hash=BASE_PAYLOAD_HASH)
    assert key_one == key_two


@test("missing canonical field raises a ValueError")
def _() -> None:
    envelope = dict(BASE_ENVELOPE)
    envelope.pop("actor")
    with raises(ValueError):
        derive_idem_key(envelope, payload_hash=BASE_PAYLOAD_HASH)


@test("changing canonical inputs changes the derived key")
def _() -> None:
    @settings(max_examples=50)
    @given(
        tenant=st.text(min_size=1),
        jitter=st.text(min_size=1),
    )
    def property(tenant: str, jitter: str) -> None:
        envelope = dict(BASE_ENVELOPE)
        envelope["tenant_id"] = tenant
        key_original = derive_idem_key(envelope, payload_hash=BASE_PAYLOAD_HASH)
        envelope["tenant_id"] = tenant + jitter
        key_mutated = derive_idem_key(envelope, payload_hash=BASE_PAYLOAD_HASH)
        assert key_original != key_mutated

    property()
