"""Ward regression tests for the receipt issuance pipeline."""

from __future__ import annotations

import base64
from typing import Any, cast

from nacl.signing import SigningKey
from ward import fixture, test  # type: ignore[attr-defined]

from k0.policy.pep_syscall import Obligation
from k0.receipts import ReceiptIssuer, ReceiptSigner
from k0.security.crypto import canonical_json
from k0.storage.receipts import ReceiptStore
from k0.obs.events import ObservabilityEmitter
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


@fixture
def signing_key() -> SigningKey:
    return SigningKey.generate()


@test("receipt issuer signs, persists, and emits observability signals")
def _(
    sqlite_runtime: Any = sqlite_runtime,
    signing_key_obj: Any = signing_key,
) -> None:
    del sqlite_runtime

    key = cast(SigningKey, signing_key_obj)

    store = ReceiptStore()
    emitter = ObservabilityEmitter()
    metrics: list[tuple[str, float, dict[str, str]]] = []

    def _record_metric(metric_name: str, value: float, **labels: str) -> None:
        metrics.append((metric_name, value, dict(labels)))

    issuer = ReceiptIssuer(
        receipt_store=store,
    signer=ReceiptSigner(key),
        metrics_recorder=_record_metric,
        observability_emitter=emitter,
    )

    obligations: list[Obligation | str] = [
        Obligation(name="notify_observer", details={"channel": "email"}),
        "log_only",
    ]

    receipt_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    payload_hash = "f" * 64

    document = issuer.issue(
        receipt_id=receipt_id,
        idem_key="tenant:space:topic:1",
        wal_pos=42,
        commit_ts="2025-09-28T12:00:00Z",
        tenant_id="tenant-1",
        space_id="space-1",
        device_id="device-42",
        payload_sha256=payload_hash,
        mls_group_id="mls-group-1",
        key_version="v1",
        obligations=obligations,
    )

    stored = store.get(receipt_id)
    assert stored is not None
    assert stored.device_sig == document.device_sig
    assert document.obligations == ("notify_observer", "log_only")

    signature_payload: dict[str, object] = {
        "receipt_id": receipt_id,
        "idem_key": "tenant:space:topic:1",
        "wal_pos": 42,
        "commit_ts": "2025-09-28T12:00:00Z",
        "tenant_id": "tenant-1",
        "space_id": "space-1",
        "device_id": "device-42",
        "payload_sha256": payload_hash,
        "mls_group_id": "mls-group-1",
        "key_version": "v1",
        "obligations": ["notify_observer", "log_only"],
    }
    key.verify_key.verify(
        canonical_json(signature_payload).encode("utf-8"),
        _decode_base64url(document.device_sig),
    )

    assert metrics == [
        ("receipt_issue_total", 1.0, {"outcome": "success"}),
    ]

    events = emitter.snapshot()
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "receipt_issued"
    assert event["receipt_id"] == receipt_id
    assert event["obligations"] == ["notify_observer", "log_only"]
    assert event["obligation_details"] == [
        {"channel": "email"},
        {},
    ]
    assert event["payload_sha256"] == payload_hash
