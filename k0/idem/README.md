# Idem Module

## Overview

The **idem** module provides idempotency primitives for K0, ensuring duplicate envelope detection and at-most-once processing semantics. It implements both V0 (BLAKE3-based) and V1 (HMAC-SHA256-based) idempotency key derivation algorithms, along with a storage-backed ledger for tracking processed requests.

## Purpose

- **Duplicate Detection**: Prevent duplicate envelope processing via unique idempotency keys
- **Key Derivation**: Generate deterministic, collision-resistant idempotency keys from envelopes
- **Ledger Management**: Track idem_key → receipt_id mappings with expiry and state
- **Replay Protection**: Detect and reject duplicate requests within time windows
- **Device Isolation**: V1 HMAC keys prevent cross-device collisions via device secrets
- **Time-Limited Windows**: V1 60-second time buckets balance safety and usability

## Architecture

The idempotency system uses **dual-mode key derivation** with fallback support:

```text
Envelope → Derive Idem Key → Ledger Lookup → Gate Validation → WAL Write
              ↓                     ↓
         V1: HMAC-SHA256      Duplicate? → Return cached receipt
         V0: BLAKE3           New? → Process + record in ledger
```

**V1 Flow (HMAC-based, preferred):**

```text
1. Gate computes envelope_sha256 = SHA-256(canonical_envelope)
2. Gate retrieves device_secret from st_devices (provisioning ledger)
3. Gate calls derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)
4. HMAC-SHA256(device_secret, envelope_sha256|device_id|time_bucket_60s)
5. Returns: idem:<32-char hex>
```

**V0 Flow (BLAKE3-based, fallback):**

```text
1. Gate extracts canonical components (tenant_id, space_id, actor, topic, schema_uri, schema_version, payload_sha256)
2. Gate calls derive_idem_key(envelope, payload_hash)
3. BLAKE3(canonical_json([components]))
4. Returns: 64-char hex digest
```

## Core Components

### 1. `derive.py` - Idempotency Key Derivation

Implements canonical key derivation algorithms for both V0 and V1 protocols.

**Functions:**

#### `canonical_idem_components(envelope, payload_hash)`

Extract canonical components for idempotency derivation (V0).

**Parameters:**

- `envelope` - Request envelope dict
- `payload_hash` - Optional payload digest (defaults to `envelope['payload_sha256']`)

**Returns:**

- List of canonical components: `[tenant_id, space_id, actor, topic, schema_uri, schema_version, payload_sha256]`
- Each component is trimmed, non-empty string
- `None` represents absent payload (serializes to `null` in JSON)

**Raises:**

- `ValueError` - If required field missing or empty
- `ValueError` - If payload_sha256 invalid format (not 64-char hex)

**Example:**

```python
from k0.idem import canonical_idem_components

components = canonical_idem_components(envelope, payload_hash="abc123...")
# Returns: ["tenant_123", "space_456", "device_789", "envelopes",
#           "envelope.schema.json", "1.0.0", "abc123..."]
```

#### `derive_idem_key(envelope, payload_hash)`

Derive canonical BLAKE3 idempotency key (V0 algorithm).

**Parameters:**

- `envelope` - Request envelope dict
- `payload_hash` - Optional payload digest

**Returns:**

- 64-character hex digest (BLAKE3 hash)

**Algorithm:**

1. Extract canonical components
2. Serialize to canonical JSON (RFC 8785)
3. Encode UTF-8
4. Compute BLAKE3 hash
5. Return hex digest

**Example:**

```python
from k0.idem import derive_idem_key

idem_key = derive_idem_key(envelope, payload_hash="abc123...")
# Returns: "5f8d7c6b5a4e3d2c1b0a9f8e7d6c5b4a..."
```

#### `derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)`

Derive HMAC-based idempotency key with device secret + time bucket (V1 algorithm).

**Parameters:**

- `envelope_sha256` - SHA-256 hash of full canonical envelope (64-char hex)
- `device_id` - Device identifier (e.g., "dad-phone")
- `device_secret` - HMAC secret from provisioning ledger (32 bytes)
- `ts` - ISO 8601 timestamp from envelope (optional, defaults to current time)

**Returns:**

- String in format: `idem:<32-char hex>`

**Algorithm:**

1. Parse `ts` to datetime, bucket to 60-second intervals
   - `time_bucket = int(timestamp) // 60`
   - Ensures stability within 60-second window
2. Create message: `envelope_sha256|device_id|time_bucket`
3. Compute HMAC-SHA256(device_secret, message)
4. Return first 32 characters: `idem:<hex[:32]>`

**Properties:**

- **Cryptographically secure**: HMAC-SHA256 prevents forgery without device_secret
- **Device-specific**: Different devices with same envelope → different keys
- **Time-limited**: 60-second replay window (balance between safety and usability)
- **Non-predictable**: Requires knowledge of device_secret (32-byte random)

**Example:**

```python
from k0.idem import derive_hmac_idem_key

device_secret = b"\x01\x02..." # 32-byte secret from st_devices
idem_key = derive_hmac_idem_key(
    envelope_sha256="abc123...",
    device_id="device_789",
    device_secret=device_secret,
    ts="2025-01-15T10:30:00Z",
)
# Returns: "idem:5f8d7c6b5a4e3d2c1b0a9f8e7d6c5b4a"
```

**Time Bucketing:**

```text
Timestamp: 2025-01-15T10:30:42Z → Unix: 1736934642
Time bucket: 1736934642 // 60 = 28948910

Within 60-second window:
  10:30:00Z → bucket 28948910
  10:30:30Z → bucket 28948910
  10:30:59Z → bucket 28948910
  10:31:00Z → bucket 28948911 (new window)
```

**Raises:**

- `ValueError` - If `ts` invalid ISO 8601 format

### 2. `ledger.py` - Idempotency Ledger Storage

Thread-safe storage abstraction over the `idem_ledger` SQLite table.

**Class: `IdempotencyLedger`**

**Key Methods:**

#### `lookup(idem_key, connection)`

Query ledger for existing idem_key entry.

**Parameters:**

- `idem_key` - Idempotency key to lookup
- `connection` - Optional SQLite connection (uses pool if None)

**Returns:**

- `LedgerEntry` if found
- `None` if not found (cache miss)

**Emits Metrics:**

- `k0_idem_lookup` - Counter with outcome (hit/miss) and state labels
- `k0_idem_duplicate_detected` - Counter for cache hits (duplicate requests)

**Emits Events:**

- `idem_ledger_lookup` - Observability event with lookup details

**Example:**

```python
from k0.idem import IdempotencyLedger

ledger = IdempotencyLedger()

existing = ledger.lookup("idem:5f8d7c6b...", connection=conn)
if existing is not None:
    print(f"Duplicate detected: receipt_id={existing.receipt_id}")
    return cached_response(existing.receipt_id)
```

#### `upsert(entry, connection)`

Insert or update ledger entry.

**Parameters:**

- `entry` - `LedgerEntry` to store
- `connection` - Optional SQLite connection

**Behavior:**

- Uses `ON CONFLICT DO UPDATE` for idempotent upserts
- Updates `receipt_id`, `first_seen_ts`, `state`, `expiry_ts`

**Emits Metrics:**

- `k0_idem_commit_recorded` - Counter with state label

**Emits Events:**

- `idem_ledger_upsert` - Observability event with entry details

**Example:**

```python
from k0.idem import IdempotencyLedger, LedgerEntry
from datetime import datetime, timezone

ledger = IdempotencyLedger()

entry = LedgerEntry(
    idem_key="idem:5f8d7c6b...",
    receipt_id="rcpt_123",
    first_seen_ts=datetime.now(timezone.utc).isoformat(),
    state="COMMITTED",
    expiry_ts=None,
)

ledger.upsert(entry, connection=conn)
```

**Dataclass: `LedgerEntry`**

```python
@dataclass(slots=True)
class LedgerEntry:
    idem_key: str           # Idempotency key (V0: 64-char hex, V1: idem:<32-char hex>)
    receipt_id: str         # Receipt identifier returned to client
    first_seen_ts: str      # ISO 8601 timestamp of first request
    state: str              # Entry state (COMMITTED, PENDING, EXPIRED)
    expiry_ts: str | None   # Optional expiry timestamp for TTL
```

**Ledger States:**

- **`COMMITTED`** - Request fully processed, receipt issued
- **`PENDING`** - Request in-flight, not yet committed
- **`EXPIRED`** - Ledger entry expired (TTL-based cleanup)

**Connection Management:**

Ledger uses connection pool (`k0.uow.connection_pool`) if no connection provided:

```python
# With explicit connection
with connection_scope() as conn:
    entry = ledger.lookup(idem_key, connection=conn)

# Uses internal pool
entry = ledger.lookup(idem_key)  # Auto-manages connection
```

**Observability Integration:**

```python
from k0.idem import IdempotencyLedger
from k0.obs import MetricsExporter, ObservabilityEmitter

metrics = MetricsExporter(namespace="k0")
observability = ObservabilityEmitter()

ledger = IdempotencyLedger(metrics=metrics, observability=observability)

# Metrics and events emitted automatically
entry = ledger.lookup(idem_key)
```

## Integration Points

### With Minimal Gate

```python
from k0.gate import MinimalGate
from k0.idem import IdempotencyLedger, LedgerEntry

gate = MinimalGate()
ledger = IdempotencyLedger()

# 1. Check for duplicate before gate validation
existing = ledger.lookup(idem_key, connection=conn)
if existing is not None:
    return {"receipt_id": existing.receipt_id}, 200

# 2. Validate envelope (gate derives idem_key)
outcome = gate.validate(envelope, body, connection=conn)
if not outcome.accepted:
    return {"error": outcome.reason}, 400

# 3. Process request (append to WAL)
receipt_id = uow.append_wal_entry(...)

# 4. Record in ledger
ledger.upsert(LedgerEntry(
    idem_key=outcome.idem_key,
    receipt_id=receipt_id,
    first_seen_ts=now_iso,
    state="COMMITTED",
), connection=conn)

conn.commit()
return {"receipt_id": receipt_id}, 200
```

### With Device Provisioning

```python
from k0.storage.provisioning import ProvisioningLedger
from k0.idem import derive_hmac_idem_key
import secrets

# Provision device with HMAC secret
ledger = ProvisioningLedger()

device_secret = secrets.token_bytes(32)  # Generate 32-byte secret
ledger.register_device_with_secret(
    device_id="device_123",
    tenant_id="tenant_abc",
    space_id="space_xyz",
    hmac_secret=device_secret,
)

# Derive V1 idem key
idem_key = derive_hmac_idem_key(
    envelope_sha256="abc123...",
    device_id="device_123",
    device_secret=device_secret,
    ts="2025-01-15T10:30:00Z",
)
```

### With WAL & Receipts

```python
from k0.idem import IdempotencyLedger
from k0.storage.receipts import ReceiptsStore

ledger = IdempotencyLedger()
receipts = ReceiptsStore()

# Idempotent request handling
existing = ledger.lookup(idem_key, connection=conn)
if existing:
    # Return cached receipt
    receipt = receipts.get(existing.receipt_id, connection=conn)
    return receipt.to_json()

# Process new request
receipt_id = process_envelope_to_wal(...)
ledger.upsert(LedgerEntry(
    idem_key=idem_key,
    receipt_id=receipt_id,
    first_seen_ts=now_iso,
    state="COMMITTED",
), connection=conn)
```

## Idempotency Guarantees

**V0 (BLAKE3-based):**

- **Collision Resistance**: BLAKE3 has 2^256 security level
- **Deterministic**: Same envelope → same key
- **Cross-Device Collisions**: Possible if two devices send identical envelopes
- **Time Independence**: Keys don't expire (infinite replay window)

**V1 (HMAC-based):**

- **Device Isolation**: Different devices → different keys (even for identical envelopes)
- **Time-Limited**: 60-second replay window (old requests rejected)
- **Secret-Based**: Requires knowledge of device_secret (32-byte random)
- **Cryptographically Secure**: HMAC-SHA256 prevents forgery
- **Rotation Support**: Device re-provisioning → new device_secret → new key space

**Ledger Guarantees:**

- **At-Most-Once Processing**: Duplicate idem_key → return cached receipt
- **ACID Transactions**: Ledger upsert within WAL transaction
- **State Tracking**: COMMITTED vs PENDING states for in-flight requests
- **TTL Support**: Optional expiry_ts for ledger cleanup

## Testing

**Unit Tests:**

- Key derivation correctness (V0 and V1)
- Time bucketing edge cases (59s → 60s boundary)
- Canonical component extraction
- Ledger lookup/upsert logic
- Metrics emission validation

**Integration Tests:**

- End-to-end idempotency flow with gate + ledger
- Database interactions (idem_ledger table)
- Duplicate detection with real WAL writes
- Device secret retrieval from provisioning ledger

**Example Test:**

```python
from k0.idem import derive_hmac_idem_key, IdempotencyLedger, LedgerEntry

def test_hmac_idem_key_time_bucketing():
    device_secret = b"\x01\x02\x03..." # 32 bytes

    # Same time bucket (within 60 seconds)
    key1 = derive_hmac_idem_key("abc123", "device_1", device_secret, "2025-01-15T10:30:00Z")
    key2 = derive_hmac_idem_key("abc123", "device_1", device_secret, "2025-01-15T10:30:59Z")
    assert key1 == key2  # Same bucket

    # Different time bucket
    key3 = derive_hmac_idem_key("abc123", "device_1", device_secret, "2025-01-15T10:31:00Z")
    assert key1 != key3  # Next bucket

def test_ledger_duplicate_detection():
    ledger = IdempotencyLedger()

    entry = LedgerEntry(
        idem_key="idem:test123",
        receipt_id="rcpt_001",
        first_seen_ts="2025-01-15T10:30:00Z",
        state="COMMITTED",
    )

    ledger.upsert(entry, connection=conn)

    # Lookup should find duplicate
    duplicate = ledger.lookup("idem:test123", connection=conn)
    assert duplicate is not None
    assert duplicate.receipt_id == "rcpt_001"
```

## Performance Considerations

**Key Derivation:**

- **V0 (BLAKE3)**: ~1-2 µs per key (very fast)
- **V1 (HMAC-SHA256)**: ~3-5 µs per key (fast, includes time bucketing)
- **Canonical JSON**: ~10-50 µs depending on envelope size

**Ledger Lookups:**

- **Cache Hit**: Single indexed query on `idem_key` primary key (<1ms)
- **Cache Miss**: No database operation (NULL result)
- **Upsert**: Single `INSERT ... ON CONFLICT` (<1ms)

**Scalability:**

- Ledger grows with unique requests (TTL-based cleanup recommended)
- Index on `idem_key` ensures O(1) lookup performance
- V1 time bucketing limits ledger growth (old entries expire)

## Configuration

**Gate Configuration:**

- `MinimalGate` automatically selects V0 vs V1 based on device_secret availability
- No explicit configuration needed

**Time Window:**

- V1 bucket size: 60 seconds (hardcoded in `derive_hmac_idem_key`)
- Configurable via function parameter if needed

**Ledger TTL:**

- Optional `expiry_ts` in `LedgerEntry`
- Cleanup via background job (not implemented yet)

## Related Modules

- **k0.gate**: Uses idem derivation in `MinimalGate.validate()`
- **k0.security**: Canonicalization utilities (`canonical_json`, `canonical_envelope`)
- **k0.storage.provisioning**: Device secret storage (`st_devices.hmac_secret`)
- **k0.uow**: Connection pooling for ledger operations
- **k0.obs**: Metrics and observability integration

## Related ADRs

- **ADR-002**: HMAC-based idempotency with device secrets (Issue #009)
- **Issue #1.1**: Envelope SHA-256 derivation
- **K0 README §6.3**: Idempotency contract
- **Migration 0003**: `idem_ledger` table schema

## Security Properties

- **V0 Collision Resistance**: BLAKE3 provides 256-bit security
- **V1 Secret Protection**: Device secrets never transmitted, stored encrypted
- **V1 Time Limitation**: 60-second replay window prevents infinite replay attacks
- **V1 Device Isolation**: Cross-device forgery requires compromising device_secret
- **Ledger ACID**: Idempotency checks within transaction boundary

## Future Enhancements

- **Ledger TTL Cleanup**: Background job to remove expired entries
- **Distributed Ledger**: Redis/Memcached for multi-instance deployments
- **Configurable Time Buckets**: Make 60-second window configurable
- **V2 Idempotency**: Support for server-generated idempotency keys
- **Metrics Dashboard**: Grafana panels for idem hit/miss rates
