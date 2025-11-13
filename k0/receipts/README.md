# K0 Receipt Issuance

**Purpose**: Signed receipt generation with V1 envelope integrity verification, obligation proof tracking, and observability integration for command submission acknowledgments.

**Layer**: Business Logic
**Category**: Receipt issuance and signing
**Related ADRs**: ADR-0105 (Receipt V1 Specification), ADR-0107 (Obligation Proof), ADR-0109 (Envelope Integrity)

---

## Overview

The receipts module provides **cryptographically signed receipts** issued after successful command submission with:

1. **V1 envelope integrity**: SHA-256 hash of full canonical envelope (not just body)
2. **Obligation proof**: List of specific actions taken (e.g., `kernel.mask.location.AMBER`)
3. **Ed25519 signatures**: Device-signed receipts with base64url encoding
4. **Persistence**: Storage in `st_receipts` table via `ReceiptStore`
5. **Observability**: Metrics and structured events for receipt issuance
6. **Idempotency**: Receipt ID linked to envelope's `event_id` for deduplication

**Architecture Pattern**: Builder + signer + persistence + observability

**Performance Targets**: Receipt issuance <5ms P95

---

## Repository Files & Functions

### 1. `__init__.py`

**Purpose**: Export receipt public API.

```python
__all__ = [
    "ReceiptDocument",
    "ReceiptIssuer",
    "ReceiptSigner",
]
```

---

### 2. `issuer.py`

**Purpose**: Receipt issuance pipeline integrating signing, persistence, and observability.

#### Classes

```python
@dataclass(slots=True)
class ReceiptDocument:
    # Core Receipt Fields
    receipt_id: str
    idem_key: str
    wal_pos: int
    commit_ts: str
    tenant_id: str
    space_id: str
    device_id: str

    # V1 NEW FIELD: Full envelope integrity hash
    envelope_sha256: str  # SHA-256 of canonical envelope (not just body)

    mls_group_id: str
    key_version: str
    device_sig: str
    obligations: tuple[str, ...]

    # V1 NEW FIELD: Proof of applied obligations (GDPR/CCPA compliance)
    obligations_applied: tuple[str, ...] = ()  # Specific actions (e.g., "kernel.mask.location.AMBER")

    manifest_fingerprint: str | None = None
    obligation_details: tuple[dict[str, str], ...] = ()

    # Legacy Field (DEPRECATED in V1)
    payload_sha256: str | None = None  # DEPRECATED: Use envelope_sha256 instead
```

- **V1 changes**:
  - `envelope_sha256` (REQUIRED): SHA-256 of full canonical envelope for integrity verification
  - `obligations_applied` (optional): List of specific obligation actions applied during processing
  - `payload_sha256` (optional): DEPRECATED - kept for backward compatibility

- **Signature scope**: `device_sig` signs all fields except `obligation_details` and `payload_sha256`

- **Usage**: Returned by `ReceiptIssuer.issue()`, serialized in command response

**Example**:

```python
receipt = ReceiptDocument(
    receipt_id="rcpt_01h2x...",
    idem_key="evt_01h2x...",
    wal_pos=12345,
    commit_ts="2025-11-12T10:30:00Z",
    tenant_id="tenant_001",
    space_id="space_001",
    device_id="device_abc",
    envelope_sha256="a7f3c2e8d9b4f1a6...",  # V1: Full envelope hash
    mls_group_id="mls_group_001",
    key_version="key_v1",
    device_sig="base64url_signature...",
    obligations=("kernel.redact.pii", "kernel.location.mask"),
    obligations_applied=("kernel.mask.location.AMBER", "kernel.redact.field.ssn"),  # V1: Specific actions
    manifest_fingerprint="policy_manifest_sha256...",
)
```

```python
class ReceiptSigner:
    def __init__(self, signing_key: SigningKey)
    def sign(self, payload: Mapping[str, object]) -> str
```

- **Purpose**: Wrapper around Ed25519 signing key producing base64url signatures
- **Algorithm**: Ed25519 (NaCl library)
- **Canonical JSON**: Payload serialized with deterministic key ordering
- **Output**: Base64url-encoded signature

**Usage**:

```python
from nacl.signing import SigningKey
from k0.receipts import ReceiptSigner

signing_key = SigningKey.generate()
signer = ReceiptSigner(signing_key)

signature = signer.sign({
    "receipt_id": "rcpt_001",
    "envelope_sha256": "a7f3c2e8...",
    "obligations": ["kernel.redact.pii"],
})
# Returns: "base64url_signature..."
```

```python
class MetricsRecorder(Protocol):
    def __call__(self, metric_name: str, value: float, **labels: str) -> None
```

- **Purpose**: Callable protocol for metrics emission
- **Usage**: Injected into `ReceiptIssuer` for Prometheus metrics

```python
class ReceiptIssuer:
    def __init__(
        self,
        *,
        receipt_store: ReceiptStore,
        signer: ReceiptSigner,
        metrics_recorder: MetricsRecorder | None = None,
        observability_emitter: ObservabilityEmitter | None = None,
    )
```

- **Purpose**: Issue signed receipts with persistence and observability
- **Dependencies**:
  - `receipt_store`: Persistence layer (`k0.storage.receipts.ReceiptStore`)
  - `signer`: Signature generation (`ReceiptSigner`)
  - `metrics_recorder`: Prometheus metrics (optional)
  - `observability_emitter`: Structured event logs (optional)

#### Methods

```python
def issue(
    self,
    *,
    receipt_id: str,
    idem_key: str,
    wal_pos: int,
    commit_ts: str,
    tenant_id: str,
    space_id: str,
    device_id: str,
    envelope_sha256: str,  # V1: REQUIRED - Full envelope hash
    mls_group_id: str,
    key_version: str,
    obligations: Sequence[Obligation | str] = (),
    obligations_applied: Sequence[str] = (),  # V1: Specific actions taken
    manifest_fingerprint: str | None = None,
    payload_sha256: str | None = None,  # V1: Optional (legacy, deprecated)
    connection: sqlite3.Connection | None = None,
) -> ReceiptDocument
```

- **Purpose**: Create, sign, persist, and emit observability for a receipt
- **V1 changes**:
  - `envelope_sha256` (REQUIRED): SHA-256 hash of full canonical envelope
  - `obligations_applied` (optional): List of specific obligation actions applied
  - `payload_sha256` (optional): DEPRECATED - Use `envelope_sha256` for integrity verification

**Algorithm**:

```python
def issue(...) -> ReceiptDocument:
    # 1. Normalize obligations
    names, detail_payloads = self._normalise_obligations(obligations)

    # 2. Build signature payload
    signature_payload = {
        "receipt_id": receipt_id,
        "idem_key": idem_key,
        "wal_pos": wal_pos,
        "commit_ts": commit_ts,
        "tenant_id": tenant_id,
        "space_id": space_id,
        "device_id": device_id,
        "envelope_sha256": envelope_sha256,  # V1: Full envelope hash
        "mls_group_id": mls_group_id,
        "key_version": key_version,
        "obligations": list(names),
    }

    # V1: Include specific obligation actions if provided
    if obligations_applied:
        signature_payload["obligations_applied"] = list(obligations_applied)

    if manifest_fingerprint:
        signature_payload["policy_manifest_fingerprint"] = manifest_fingerprint

    # 3. Sign payload
    device_sig = self._signer.sign(signature_payload)

    # 4. Create storage record
    stored_receipt = Receipt(
        receipt_id=receipt_id,
        idem_key=idem_key,
        wal_pos=wal_pos,
        commit_ts=commit_ts,
        tenant_id=tenant_id,
        space_id=space_id,
        device_id=device_id,
        mls_group_id=mls_group_id,
        key_version=key_version,
        device_sig=device_sig,
        manifest_fingerprint=manifest_fingerprint,
    )

    # 5. Persist receipt
    try:
        self._store.save(stored_receipt, connection=connection)
        self._emit_metric("receipt_issue_total", 1.0, outcome="success")
    except Exception as exc:
        self._emit_metric("receipt_issue_total", 1.0, outcome="failure", error=exc.__class__.__name__)
        raise

    # 6. Emit observability event
    self._emit_observability_event({
        "event": "receipt_issued",
        "receipt_id": receipt_id,
        "envelope_sha256": envelope_sha256,  # V1: Full envelope hash
        "obligations": list(names),
        "obligations_applied": list(obligations_applied),  # V1: Specific actions
        "obligation_details": detail_payloads,
        "policy_manifest_fingerprint": manifest_fingerprint,
    })

    # 7. Return receipt document
    return ReceiptDocument(
        receipt_id=receipt_id,
        idem_key=idem_key,
        wal_pos=wal_pos,
        commit_ts=commit_ts,
        tenant_id=tenant_id,
        space_id=space_id,
        device_id=device_id,
        envelope_sha256=envelope_sha256,  # V1: Full envelope hash
        mls_group_id=mls_group_id,
        key_version=key_version,
        device_sig=device_sig,
        obligations=names,
        obligations_applied=tuple(obligations_applied),  # V1: Specific actions
        manifest_fingerprint=manifest_fingerprint,
        obligation_details=tuple(detail_payloads),
        payload_sha256=payload_sha256,  # V1: Optional legacy field
    )
```

**Example**:

```python
from k0.policy.pep_syscall import Obligation

issuer = ReceiptIssuer(
    receipt_store=receipt_store,
    signer=signer,
    metrics_recorder=metrics_recorder,
    observability_emitter=observability_emitter,
)

receipt = issuer.issue(
    receipt_id="rcpt_01h2x...",
    idem_key="evt_01h2x...",
    wal_pos=12345,
    commit_ts="2025-11-12T10:30:00Z",
    tenant_id="tenant_001",
    space_id="space_001",
    device_id="device_abc",
    envelope_sha256="a7f3c2e8d9b4f1a6...",  # V1: SHA-256 of full canonical envelope
    mls_group_id="mls_group_001",
    key_version="key_v1",
    obligations=[
        Obligation(name="kernel.redact.pii", details={"fields": ["ssn"]}),
        Obligation(name="kernel.location.mask", details={"band": "AMBER"}),
    ],
    obligations_applied=[  # V1: Specific actions taken
        "kernel.mask.location.AMBER",
        "kernel.redact.field.ssn",
    ],
    manifest_fingerprint="policy_manifest_sha256...",
)

# receipt.device_sig contains base64url signature
# receipt.obligations_applied contains specific actions
# Metrics: receipt_issue_total{outcome="success"} = 1
```

**Helper Methods**:

```python
def _normalise_obligations(
    self, obligations: Sequence[Obligation | str]
) -> tuple[tuple[str, ...], list[dict[str, str]]]
```

- **Purpose**: Extract obligation names and details from mixed sequence
- **Supports**: `Obligation` objects and plain strings
- **Returns**: `(names_tuple, details_list)`

**Example**:

```python
obligations = [
    Obligation(name="kernel.redact.pii", details={"fields": ["ssn"]}),
    "kernel.log.detailed",
]

names, details = issuer._normalise_obligations(obligations)
# names: ("kernel.redact.pii", "kernel.log.detailed")
# details: [{"fields": "ssn"}, {}]
```

```python
def _emit_metric(self, metric_name: str, value: float, **labels: str) -> None
```

- **Purpose**: Emit Prometheus metric with defensive error handling
- **Labels**: Arbitrary key-value pairs (e.g., `outcome="success"`, `error="ValueError"`)

```python
def _emit_observability_event(self, payload: Mapping[str, object]) -> None
```

- **Purpose**: Emit structured observability event with defensive error handling
- **Payload**: Dict with event details (receipt_id, obligations, envelope_sha256, etc.)

---

## Connections & Integration Points

### Upstream Dependencies

1. **`k0.storage.receipts.ReceiptStore`**: Persistence layer for receipts
2. **`k0.security.crypto.canonical_json()`**: Deterministic JSON serialization for signatures
3. **`k0.security.crypto.encode_base64url()`**: Base64url encoding for signatures
4. **`nacl.signing.SigningKey`**: Ed25519 signing key
5. **`k0.obs.events.ObservabilityEmitter`**: Structured event logging
6. **`k0.policy.pep_syscall.Obligation`**: Policy obligation data structure

### Downstream Consumers

1. **`k0.ports.command.submit_command()`**: Issues receipts after successful WAL commit
2. **`k0.storage.receipts.ReceiptStore`**: Persists receipts to `st_receipts` table
3. **`k0.obs.events`**: Emits receipt issuance events for audit trail

### Data Flow

#### Receipt Issuance Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Command Submission                                            │
│    POST /k0/command.submit                                       │
│    envelope = {...}                                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Pipeline Processing                                           │
│    - Gate validation                                             │
│    - PEP evaluation (obligations emitted)                        │
│    - Apply obligations (redaction, location masking)             │
│    - Attach policy stamp                                         │
│    - Idempotency check                                           │
│    - QoS budget consumption                                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. UoW Transaction                                               │
│    with uow.transaction():                                       │
│      - WAL append → wal_pos = 12345                             │
│      - Outbox staging                                            │
│      - Idempotency mark complete                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Receipt Issuance                                              │
│    receipt = receipts.issue(                                     │
│      receipt_id="rcpt_01h2x...",                                │
│      idem_key="evt_01h2x...",                                   │
│      wal_pos=12345,                                             │
│      envelope_sha256="a7f3c2e8...",  # V1: Full envelope hash   │
│      obligations=[...],                                          │
│      obligations_applied=[...],      # V1: Specific actions     │
│    )                                                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Receipt Signing                                               │
│    signature_payload = {                                         │
│      "receipt_id": "rcpt_01h2x...",                             │
│      "envelope_sha256": "a7f3c2e8...",                          │
│      "obligations": ["kernel.redact.pii"],                      │
│      "obligations_applied": ["kernel.mask.location.AMBER"],     │
│      ...                                                         │
│    }                                                             │
│    canonical = canonical_json(signature_payload)                 │
│    device_sig = signing_key.sign(canonical.encode("utf-8"))     │
│    device_sig_b64 = encode_base64url(device_sig.signature)      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Persistence                                                   │
│    receipt_store.save(Receipt(...), connection=connection)       │
│    → INSERT INTO st_receipts (receipt_id, device_sig, ...)      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. Observability                                                 │
│    metrics_recorder("receipt_issue_total", 1.0, outcome="success")│
│    observability_emitter.emit({                                  │
│      "event": "receipt_issued",                                  │
│      "receipt_id": "rcpt_01h2x...",                             │
│      "envelope_sha256": "a7f3c2e8...",                          │
│      "obligations_applied": [...],                              │
│    })                                                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. Response                                                      │
│    CommandResponse{                                              │
│      status="ACCEPTED",                                          │
│      receipt_id="rcpt_01h2x...",                                │
│      obligations=["kernel.redact.pii"],                         │
│    }                                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Tests

```python
# tests/k0/receipts/test_issuer.py
def test_receipt_issuance(mock_store, mock_signer, mock_metrics):
    issuer = ReceiptIssuer(
        receipt_store=mock_store,
        signer=mock_signer,
        metrics_recorder=mock_metrics,
    )

    receipt = issuer.issue(
        receipt_id="rcpt_001",
        idem_key="evt_001",
        wal_pos=100,
        commit_ts="2025-11-12T10:30:00Z",
        tenant_id="tenant_001",
        space_id="space_001",
        device_id="device_abc",
        envelope_sha256="a7f3c2e8d9b4f1a6...",  # V1 field
        mls_group_id="mls_001",
        key_version="key_v1",
        obligations=[Obligation(name="kernel.redact.pii", details={"fields": ["ssn"]})],
        obligations_applied=["kernel.redact.field.ssn"],  # V1 field
    )

    assert receipt.receipt_id == "rcpt_001"
    assert receipt.envelope_sha256 == "a7f3c2e8d9b4f1a6..."
    assert receipt.obligations == ("kernel.redact.pii",)
    assert receipt.obligations_applied == ("kernel.redact.field.ssn",)
    mock_store.save.assert_called_once()
    mock_metrics.assert_called_with("receipt_issue_total", 1.0, outcome="success")

def test_receipt_signing(signing_key):
    signer = ReceiptSigner(signing_key)

    payload = {
        "receipt_id": "rcpt_001",
        "envelope_sha256": "a7f3c2e8...",
        "obligations": ["kernel.redact.pii"],
    }

    signature = signer.sign(payload)
    assert len(signature) > 0
    assert signature.endswith("=") is False  # base64url, not base64

def test_normalise_obligations():
    issuer = ReceiptIssuer(receipt_store=mock_store, signer=mock_signer)

    obligations = [
        Obligation(name="kernel.redact.pii", details={"fields": ["ssn"]}),
        "kernel.log.detailed",
    ]

    names, details = issuer._normalise_obligations(obligations)
    assert names == ("kernel.redact.pii", "kernel.log.detailed")
    assert details == [{"fields": "ssn"}, {}]
```

### Integration Tests

```python
# tests/integration/test_receipt_issuance.py
def test_command_issues_receipt(kernel_client):
    response = kernel_client.post("/k0/command.submit", json=envelope)
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "ACCEPTED"
    assert "receipt_id" in result

    # Verify receipt persisted
    receipt = db.query("SELECT * FROM st_receipts WHERE receipt_id = ?", result["receipt_id"])
    assert receipt is not None
    assert receipt["device_sig"] is not None
```

---

## Performance & Observability

### Metrics

- `receipt_issue_total{outcome, error}` (counter): Receipt issuances by outcome (success/failure)

### Traces

- Span: `receipt.issue` (receipt_id, wal_pos, obligations)
- Span: `receipt.sign` (receipt_id, signature_length)

### Logging

```json
{
  "event": "receipt_issued",
  "receipt_id": "rcpt_01h2x...",
  "idem_key": "evt_01h2x...",
  "wal_pos": 12345,
  "envelope_sha256": "a7f3c2e8d9b4f1a6...",
  "obligations": ["kernel.redact.pii", "kernel.location.mask"],
  "obligations_applied": ["kernel.mask.location.AMBER", "kernel.redact.field.ssn"],
  "policy_manifest_fingerprint": "policy_sha256..."
}
```

---

## Related Modules

- **`k0.ports.command`**: Issues receipts after successful command submission
- **`k0.storage.receipts`**: Persistence layer for receipts
- **`k0.security.crypto`**: Canonical JSON and base64url encoding
- **`k0.policy.pep_syscall`**: Policy obligations
- **`k0.obs.events`**: Observability event emission

---

## Related ADRs

- **ADR-0105**: Receipt V1 Specification
- **ADR-0107**: Obligation Proof Tracking
- **ADR-0109**: Envelope Integrity Verification

---

## Key Design Decisions

1. **V1 envelope integrity**: SHA-256 of full canonical envelope (not just body) for tamper detection
2. **Obligation proof**: Specific actions tracked for GDPR/CCPA compliance audits
3. **Ed25519 signatures**: Fast, secure, and compact (64-byte signatures)
4. **Base64url encoding**: URL-safe signature representation
5. **Defensive observability**: Metrics/events failures don't propagate to caller
6. **Idempotency linking**: Receipt ID tied to event ID for deduplication
7. **Canonical JSON**: Deterministic serialization ensures signature reproducibility
8. **Legacy compatibility**: `payload_sha256` deprecated but kept for backward compatibility
