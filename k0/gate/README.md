# Gate Module

## Overview

The **gate** module is the central validation gateway for K0, enforcing envelope correctness contracts before WAL writes. It provides cryptographic verification, schema validation, device provisioning checks, replay detection, and idempotency enforcement for all incoming envelopes.

## Purpose

- **Envelope Validation**: Verify envelope structure, signatures, and payload hashes before commit
- **Schema Registry**: Manage schema lifecycle (REGISTERED → ACTIVE → DEPRECATED/BLOCKED) with audit trails
- **Device Provisioning**: Validate device bindings (tenant, space, device) and key rotation states
- **Replay Detection**: Prevent duplicate envelope processing via envelope_sha256 tracking
- **Idempotency Enforcement**: Derive and verify idempotency keys (V0: BLAKE3, V1: HMAC-SHA256)
- **Observability**: Emit metrics and events for gate rejections, signature failures, and schema issues

## Architecture

The gate acts as a **correctness firewall** before the WAL:

```text
Client → MinimalGate → SchemaRegistry + ProvisioningLedger → WAL
             ↓
   [Validation Steps]
   1. Canonicalization + size limits
   2. Device provisioning check
   3. Schema status validation
   4. Payload hash verification
   5. Signature verification (multi-key rotation support)
   6. Replay detection (envelope_sha256)
   7. Idempotency key derivation (BLAKE3 or HMAC)
   8. Clock skew validation
```

## Core Components

### 1. `minimal_gate.py` - Central Validation Gateway

**Class: `MinimalGate`**

The primary validation engine enforcing all envelope correctness contracts.

**Key Methods:**

- **`validate(envelope, body, connection)`** - Main validation pipeline
  - Returns `GateOutcome` with `accepted` boolean, `reason`, `idem_key`, `key_version`, `key_state`
  - Performs all validation steps in sequence
  - Emits metrics/events for rejections and successes

**Validation Steps:**

1. **Canonicalization & Size Limits**
   - Canonical JSON encoding (RFC 8785)
   - Max envelope bytes: 64KB (default, configurable)
   - Max body bytes: 4MB (default, configurable)
   - Rejection reason: `CANONICALIZATION_ERROR`, `LIMIT_EXCEEDED`

2. **Required Fields Check**
   - Validate presence: `tenant_id`, `space_id`, `device_id`, `schema_uri`, `schema_version`
   - Rejection reason: `MISSING_ACTOR_BINDINGS:<fields>`

3. **Clock Skew Validation** (Gap 7)
   - Parse `ts` field (ISO 8601 timestamp)
   - Validate within max_clock_skew_seconds (default: 300s = 5 minutes)
   - Rejection reason: `CLOCK_SKEW_EXCESSIVE:skew=<seconds>s`

4. **Device Provisioning Check**
   - Lookup device in `ProvisioningLedger` (tenant, space, device)
   - Verify bindings match envelope
   - Rejection reasons: `DEVICE_NOT_PROVISIONED`, `SPACE_MISMATCH`

5. **Schema Status Validation**
   - Query `SchemaRegistry` for schema_uri@version
   - Accept only `ACTIVE` status
   - Reject `REGISTERED`, `DEPRECATED`, `BLOCKED`
   - Rejection reasons: `SCHEMA_NOT_ACTIVE`, `SCHEMA_BLOCKED`, `SCHEMA_SUNSET`

6. **Payload Hash Verification**
   - Compute SHA-256 of body
   - Compare with `payload_sha256` in envelope
   - Rejection reasons: `PAYLOAD_HASH_MISSING`, `PAYLOAD_HASH_MISMATCH`

7. **Body Requirement** (Gap 34)
   - Bodies are mandatory for K0 (no null/empty bodies)
   - Rejection reason: `BODY_REQUIRED`

8. **Signature Verification** (Multi-Key Rotation)
   - Query device keys from `ProvisioningLedger` (states: ACTIVE, ROTATING)
   - Canonicalize envelope for signing
   - Try verification with each key (ACTIVE first, then ROTATING)
   - Support Ed25519 signatures (URL-safe base64 encoding)
   - Rejection reasons: `NO_VALID_KEYS`, `SIGNATURE_INVALID`, `SIGNATURE_MISSING`, `REVOKED_KEY`

9. **Envelope SHA-256 Validation** (Gap 4, V1)
   - Compute `envelope_sha256` = SHA-256(canonical_envelope)
   - Validate client-provided `envelope_sha256` matches computed value
   - Rejection reason: `ENVELOPE_SHA256_MISMATCH`

10. **Replay Detection** (V1)
    - Check if `envelope_sha256` exists in WAL (`st_wal.envelope_sha256` column)
    - If found → reject as duplicate/replay
    - Rejection reason: `ENVELOPE_REPLAY_DETECTED`

11. **Idempotency Key Derivation**
    - **V1 (HMAC-based)**: If device has `hmac_secret` in provisioning ledger
      - `derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)`
      - HMAC-SHA256 with 60-second time bucket
      - Format: `idem:<32-char hex>`
    - **V0 (BLAKE3-based)**: Fallback for legacy devices
      - `derive_idem_key(envelope, payload_hash)`
      - BLAKE3 hash of canonical components
    - Verify client-provided `idem_key` matches computed value
    - Rejection reasons: `IDEM_KEY_INVALID`, `IDEM_KEY_MISMATCH`

12. **Location Validation** (Gap 4)
    - For AMBER/RED bands, validate `location` field exists
    - Rejection reason: `LOCATION_MISSING:band=<band>`

13. **Policy Stamp Validation** (Gap 4)
    - If `policy_stamp` present, validate structure (band, obligations, decision)
    - Rejection reason: `POLICY_STAMP_INVALID`

**Observability:**

- **Metrics**:
  - `gate_rejections_total` - Rejections by reason and tenant
  - `gate_accepted_total` - Acceptances by tenant
  - `k0_signature_verified` - Signature success with key metadata
  - `k0_signature_verification_failed` - Signature failures by reason
  - `k0_provisioning_denial` - Provisioning check failures
  - `k0_schema_denial` - Schema validation failures
  - `k0_envelope_replay_detected` - Replay attempts detected
- **Events** (via `ObservabilityEmitter`):
  - `signature_verification` (success/failure)
  - `provisioning_check` (failure)
  - `schema_validation` (failure)
  - `envelope_replay_detected`

**Configuration:**

- `max_envelope_bytes` - Envelope size limit (default: 64KB)
- `max_body_bytes` - Body size limit (default: 4MB)
- `max_clock_skew_seconds` - Clock skew tolerance (default: 300s)
- `registry` - SchemaRegistry instance (optional)
- `provisioning` - ProvisioningLedger instance (optional)
- `metrics` - MetricsExporter instance (optional)
- `observability` - ObservabilityEmitter instance (optional)

**Example:**

```python
from k0.gate import MinimalGate, SchemaRegistry
from k0.storage.provisioning import ProvisioningLedger
from k0.obs import MetricsExporter, ObservabilityEmitter

# Initialize components
registry = SchemaRegistry()
registry.load()
provisioning = ProvisioningLedger()
metrics = MetricsExporter(namespace="k0")
observability = ObservabilityEmitter()

# Create gate
gate = MinimalGate(
    registry=registry,
    provisioning=provisioning,
    max_envelope_bytes=64_000,
    max_body_bytes=4_194_304,
    max_clock_skew_seconds=300,
    metrics=metrics,
    observability=observability,
)

# Validate envelope
envelope = {
    "tenant_id": "tenant_123",
    "space_id": "space_456",
    "device_id": "device_789",
    "schema_uri": "envelope.schema.json",
    "schema_version": "1.0.0",
    "payload_sha256": "abc123...",
    "sig": "signature_base64...",
    "ts": "2025-01-15T10:30:00Z",
}
body = b"envelope payload"

outcome = gate.validate(envelope, body, connection=conn)
if outcome.accepted:
    print(f"Accepted: idem_key={outcome.idem_key}")
else:
    print(f"Rejected: {outcome.reason}")
```

**Rejection Reason Constants:**

- `CANONICALIZATION_ERROR` - JSON canonicalization failed
- `LIMIT_EXCEEDED` - Envelope or body size exceeded
- `BODY_REQUIRED` - Body is null or empty (Gap 34)
- `MISSING_BINDINGS` - Required fields missing
- `CLOCK_SKEW_EXCESSIVE` - Timestamp outside tolerance (Gap 7)
- `DEVICE_NOT_PROVISIONED` - Device not found in ledger
- `SPACE_MISMATCH` - Tenant/space bindings don't match
- `SCHEMA_NOT_ACTIVE` - Schema version not ACTIVE
- `SCHEMA_BLOCKED` - Schema version emergency blocked
- `SCHEMA_SUNSET` - Schema version deprecated
- `PAYLOAD_HASH_MISSING` - payload_sha256 field missing
- `PAYLOAD_HASH_MISMATCH` - Payload hash doesn't match computed
- `SIGNATURE_MISSING` - sig field missing
- `NO_VALID_KEYS` - No verification keys available
- `REVOKED_KEY` - Key is revoked (Gap 35)
- `SIGNATURE_INVALID` - Signature verification failed
- `ENVELOPE_SHA256_MISMATCH` - Client-provided hash mismatch (Gap 4)
- `ENVELOPE_REPLAY_DETECTED` - Duplicate envelope detected (V1)
- `IDEM_KEY_INVALID` - Idempotency key format invalid
- `IDEM_KEY_MISMATCH` - Idempotency key doesn't match computed
- `LOCATION_MISSING` - Location required for AMBER/RED (Gap 4)
- `POLICY_STAMP_INVALID` - Policy stamp structure invalid (Gap 4)

### 2. `schema_registry.py` - Schema Lifecycle Management

**Class: `SchemaRegistry`**

Thread-safe, cached registry for schema metadata backed by `schema_registry` SQLite table.

**Schema Lifecycle:**

```text
REGISTERED → ACTIVE → DEPRECATED → BLOCKED
     ↑                      ↓
     └──────────────────────┘ (unblock via promote)
```

**Key Methods:**

- **`load(connection)`** - Load all schemas into process cache
  - Populates internal cache from `schema_registry` table
  - Thread-safe with RLock
  - Updates `schema_cache_entries_active` gauge (Gap 43)

- **`get(uri, version, connection)`** - Retrieve schema record
  - Cache hit: Return from memory
  - Cache miss: Query database, cache result
  - Raises `KeyError` if not found
  - Emits `schema_cache_hits_total` / `schema_cache_misses_total` metrics (Gap 43)

- **`register(record, connection)`** - Register new schema version
  - Insert into database with status (REGISTERED or ACTIVE)
  - Raises `ValueError` if already exists
  - Updates cache

- **`upsert(record, connection)`** - Insert or update schema
  - Uses `ON CONFLICT DO UPDATE` for idempotent registration
  - Updates cache

- **`promote(uri, version, connection)`** - Promote version to ACTIVE
  - Demote current ACTIVE → DEPRECATED
  - Block old DEPRECATED → BLOCKED (N/N+1 policy)
  - Set `unblocked_ts` if version was previously blocked
  - Updates entire URI cache

- **`block(uri, version, operator_id, reason, connection)`** - Emergency block schema
  - Set status to BLOCKED with audit metadata
  - Record `operator_id`, `blocked_ts`, `blocked_reason` (ADR-002 audit trail)
  - Raises `ValueError` if operator_id or reason empty
  - Updates cache

- **`get_audit_trail(uri, version, status, connection)`** - Query audit trail
  - Filter by URI, version, status (optional)
  - Returns all matching records with audit metadata

- **`active_versions(uri)`** - Get all ACTIVE versions for URI
- **`records_for_uri(uri)`** - Get all versions for URI
- **`clear_cache()`** - Clear process cache (testing/reload)

**Schema Record Fields:**

```python
@dataclass(slots=True)
class SchemaRecord:
    uri: str                      # Schema URI (e.g., "envelope.schema.json")
    version: str                  # Semantic version (e.g., "1.0.0")
    sha256: str                   # 64-char hex digest of schema payload
    status: str                   # REGISTERED, ACTIVE, DEPRECATED, BLOCKED
    operator_id: str | None       # Operator who blocked (audit trail)
    blocked_ts: str | None        # ISO 8601 timestamp of block
    blocked_reason: str | None    # Justification for block
    unblocked_ts: str | None      # ISO 8601 timestamp of unblock
```

**Example:**

```python
from k0.gate import SchemaRegistry, SchemaRecord

registry = SchemaRegistry()
registry.load()

# Register new version
record = SchemaRecord(
    uri="envelope.schema.json",
    version="1.1.0",
    sha256="abc123...",
    status="REGISTERED",
)
registry.register(record)

# Promote to ACTIVE (demotes old version)
registry.promote("envelope.schema.json", "1.1.0")

# Emergency block
registry.block(
    "envelope.schema.json",
    "1.0.0",
    operator_id="admin@example.com",
    reason="Security vulnerability CVE-2025-001",
)

# Query audit trail
audit_records = registry.get_audit_trail(uri="envelope.schema.json")
for record in audit_records:
    print(f"{record.uri}@{record.version} - {record.status}")
    if record.operator_id:
        print(f"  Blocked by {record.operator_id}: {record.blocked_reason}")
```

**Thread Safety:**

- Internal cache protected by `threading.RLock`
- Safe for multi-threaded access
- Connection management via context managers

**Performance:**

- Cache hits: O(1) dict lookup
- Cache misses: Single database query
- Full reload: O(n) for all schemas

**Metrics (Gap 43):**

- `schema_cache_entries_active` - Gauge of cached schema count
- `schema_cache_hits_total` - Cache hit counter
- `schema_cache_misses_total` - Cache miss counter

## Integration Points

### With WAL & Unit of Work

```python
from k0.gate import MinimalGate
from k0.uow import UnitOfWork

gate = MinimalGate()
uow = UnitOfWork()

with uow.begin() as conn:
    outcome = gate.validate(envelope, body, connection=conn)
    if outcome.accepted:
        # Proceed with WAL write
        uow.append_wal_entry(...)
        conn.commit()
    else:
        # Reject request
        return {"error": outcome.reason}, 400
```

### With Device Provisioning

```python
from k0.storage.provisioning import ProvisioningLedger, ProvisionedDevice, DeviceKey

ledger = ProvisioningLedger()

# Register device
ledger.register(ProvisionedDevice(
    device_id="device_123",
    tenant_id="tenant_abc",
    space_id="space_xyz",
    mls_group_id="mls_group_001",
    provisioned_ts="2025-01-15T10:00:00Z",
))

# Add initial key
ledger.add_key(DeviceKey(
    device_id="device_123",
    key_version="v1",
    verify_key="base64_ed25519_public_key",
    key_state="ACTIVE",
    registered_ts="2025-01-15T10:00:00Z",
))

# Gate validates against this data
outcome = gate.validate(envelope, body, connection=conn)
```

### With Idempotency Ledger

```python
from k0.idem import IdempotencyLedger, LedgerEntry

ledger = IdempotencyLedger()

# Check for duplicate before gate
existing = ledger.lookup(idem_key, connection=conn)
if existing is not None:
    # Return cached receipt
    return {"receipt_id": existing.receipt_id}, 200

# Validate with gate
outcome = gate.validate(envelope, body, connection=conn)
if outcome.accepted:
    # Record in ledger
    ledger.upsert(LedgerEntry(
        idem_key=outcome.idem_key,
        receipt_id=receipt_id,
        first_seen_ts=now_iso,
        state="COMMITTED",
    ), connection=conn)
```

### With CLI (k0ctl)

```bash
# Register schema
k0ctl schema register --uri envelope.schema.json --version 1.0.0 --sha256 abc123

# Promote to ACTIVE
k0ctl schema promote --uri envelope.schema.json --version 1.0.0

# Emergency block
k0ctl schema block --uri envelope.schema.json --version 1.0.0 \
  --operator admin@example.com --reason "Security vulnerability"

# View audit trail
k0ctl schema audit --uri envelope.schema.json
```

## Testing

**Unit Tests:**

- Validation logic for each rejection reason
- Schema lifecycle transitions
- Multi-key rotation verification
- Clock skew edge cases
- Cache hit/miss behavior

**Integration Tests:**

- End-to-end envelope validation flow
- Database interactions (schema_registry, st_devices, st_wal)
- Metrics emission verification
- Replay detection with real WAL table

**Example Test:**

```python
from k0.gate import MinimalGate, SchemaRegistry

def test_gate_rejects_expired_schema():
    registry = SchemaRegistry()
    registry.upsert(SchemaRecord(
        uri="test.schema.json",
        version="1.0.0",
        sha256="abc123",
        status="DEPRECATED",
    ))

    gate = MinimalGate(registry=registry)

    envelope = {
        "tenant_id": "tenant_123",
        "schema_uri": "test.schema.json",
        "schema_version": "1.0.0",
        # ... other fields
    }

    outcome = gate.validate(envelope, b"body")
    assert not outcome.accepted
    assert outcome.reason.startswith("SCHEMA_SUNSET")
```

## Related Modules

- **k0.security**: Signature verification, canonicalization, hash utilities
- **k0.storage.provisioning**: Device and key management
- **k0.idem**: Idempotency key derivation and ledger
- **k0.uow**: Connection pooling and transaction management
- **k0.obs**: Metrics and observability
- **k0.cli**: Schema registry CLI commands

## Related ADRs

- **K0 README §6.2**: Gate validation contract
- **ADR-002**: Schema registry audit trail and emergency blocking
- **ADR-001**: Key rotation with multi-key verification
- **Issue #009**: HMAC-based idempotency (V1)
- **Gap 7**: Clock skew validation
- **Gap 34**: Body requirement enforcement
- **Gap 35**: Revoked key rejection
- **Gap 43**: Schema cache metrics
- **Gap 47**: Gate rejection metrics by reason

## Security Properties

- **Signature Verification**: Ed25519 cryptographic verification with key rotation support
- **Replay Protection**: Envelope SHA-256 tracking in WAL prevents exact duplicates
- **Idempotency**: HMAC-based keys prevent cross-device collisions and replay attacks
- **Clock Skew**: Prevents timestamp manipulation attacks (5-minute tolerance)
- **Schema Blocking**: Emergency kill switch for vulnerable schemas with audit trail
- **Key Rotation**: Supports ACTIVE + ROTATING keys for zero-downtime rotation
- **PII Protection**: Location validation for AMBER/RED bands
