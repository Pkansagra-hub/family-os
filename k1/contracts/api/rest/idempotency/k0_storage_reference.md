# Contract: K0 Storage Reference for Idempotency

**Contract ID:** `REST-IDEM-004`
**Status:** DRAFT
**Layer:** K1 API Gateway (Documentation Reference)
**ADR:** ADR-0041b (Idempotency), K0 README Section 9

---

## Purpose

This contract documents the reference to K0 Memory Kernel's SQLite-based idempotency storage implementation. K1 REST API delegates all idempotency storage to K0.

**Architecture:** K1 (API layer, stateless) does NOT implement its own idempotency storage. K0 (Memory Kernel) is the "only durable commit surface" and handles ALL storage including idempotency ledger.

---

## K0 Idempotency Implementation

### Location

```
k0/
├── README.md                    # Section 9: Idempotency & Receipts
├── idem/
│   ├── ledger.py               # IdempotencyLedger class (SQLite implementation)
│   └── derive.py               # BLAKE3 hash derivation
├── contracts/
│   └── sql/
│       └── idem_ledger.sql     # SQLite table schema
└── storage/
    └── wal.py                  # Write-Ahead Log integration
```

---

## K0 README Section 9: Idempotency & Receipts

**Full Reference:** `k0/README.md` lines 1-500 (Section 9)

### Key Concepts

#### Canonical Idempotency Key Derivation

```
idem_key = BLAKE3(
    tenant_id |
    space_id |
    actor |
    topic |
    schema_uri |
    schema_version |
    payload_sha256
)
```

**Properties:**
- **Deterministic:** Same envelope → same idem_key
- **Content-aware:** payload_sha256 ensures same content
- **Space-isolated:** space_id prevents cross-space collisions
- **Fast:** BLAKE3 hashing <0.5ms

#### Duplicate Detection

```
1. Client submits command with idem_key (optional, from Idempotency-Key header)
2. K0 Minimal Gate checks SQLite idem_ledger table
3. If idem_key exists → return 409 IDEMPOTENT_DUPLICATE with cached response
4. If idem_key new → process command, insert to idem_ledger, return 200 OK
```

#### Storage Implementation

**SQLite Table:** `idem_ledger`

```sql
CREATE TABLE idem_ledger (
  idem_key TEXT PRIMARY KEY,
  receipt_id TEXT NOT NULL,
  first_seen_ts TEXT NOT NULL,
  state TEXT NOT NULL,
  expiry_ts TEXT NOT NULL,
  cached_response BLOB
);

CREATE INDEX idx_idem_expiry ON idem_ledger(expiry_ts);
```

**Performance:**
- **Lookup latency:** <25ms P50, <150ms P95 (SQLite indexed lookup)
- **Insert latency:** <10ms P50 (SQLite WAL mode, append-only)
- **Storage:** ~2KB per entry (FlatBuffers serialized response)
- **Throughput:** 5000+ writes/sec (SQLite WAL mode)

#### 24-Hour TTL Policy

```python
# k0/idem/ledger.py
def lookup(self, idem_key: str, connection: sqlite3.Connection):
    row = connection.execute(
        "SELECT idem_key, receipt_id, first_seen_ts, state, expiry_ts, cached_response "
        "FROM idem_ledger WHERE idem_key = ?",
        (idem_key,)
    ).fetchone()

    if row is None:
        return None  # New request

    # Check expiry (24-hour TTL)
    if datetime.fromisoformat(row["expiry_ts"]) < datetime.utcnow():
        return None  # Expired, treat as new

    return LedgerEntry(...)  # Duplicate detected
```

**Cleanup:** Background task prunes expired entries every hour (reduces storage by 80%)

---

## K0 Implementation Code Reference

### IdempotencyLedger Class

**File:** `k0/idem/ledger.py` (lines 1-200)

```python
class IdempotencyLedger:
    """
    SQLite-based idempotency ledger.

    Performance: <25ms P50 lookup, <10ms P50 insert
    Storage: ~2KB per entry, 24h TTL
    """

    def __init__(self, connection_pool: sqlite3.ConnectionPool):
        self.connection_pool = connection_pool

    def lookup(self, idem_key: str, connection: sqlite3.Connection) -> Optional[LedgerEntry]:
        """
        Lookup idempotency key in SQLite ledger.

        Returns:
            LedgerEntry if key exists (duplicate), None if new request
        """
        row = connection.execute(
            "SELECT idem_key, receipt_id, first_seen_ts, state, expiry_ts, cached_response "
            "FROM idem_ledger WHERE idem_key = ?",
            (idem_key,)
        ).fetchone()

        if row is None:
            self._emit_lookup_telemetry(idem_key, None, outcome="miss")
            return None

        # Check expiry
        if datetime.fromisoformat(row["expiry_ts"]) < datetime.utcnow():
            self._emit_lookup_telemetry(idem_key, None, outcome="expired")
            return None

        entry = LedgerEntry(
            idem_key=row["idem_key"],
            receipt_id=row["receipt_id"],
            first_seen_ts=row["first_seen_ts"],
            state=row["state"],
            cached_response=row["cached_response"]
        )
        self._emit_lookup_telemetry(idem_key, entry, outcome="hit")
        return entry

    def upsert(self, entry: LedgerEntry, connection: sqlite3.Connection):
        """
        Insert or update idempotency ledger entry.

        Performance: <10ms P50 (SQLite WAL mode)
        """
        connection.execute(
            "INSERT INTO idem_ledger (idem_key, receipt_id, first_seen_ts, state, expiry_ts, cached_response) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(idem_key) DO UPDATE SET "
            "state = excluded.state, cached_response = excluded.cached_response",
            (
                entry.idem_key,
                entry.receipt_id,
                entry.first_seen_ts,
                entry.state,
                entry.expiry_ts,
                entry.cached_response
            )
        )
        self._emit_upsert_telemetry(entry)
```

---

## K0 SQL Schema

**File:** `k0/contracts/sql/idem_ledger.sql`

```sql
-- Idempotency Ledger Table
-- Purpose: Store idempotency keys with 24-hour TTL
-- Performance: <25ms P50 lookup (indexed), <10ms P50 insert (WAL mode)

CREATE TABLE IF NOT EXISTS idem_ledger (
  -- Primary key: Idempotency key (BLAKE3 hash or client-provided UUID)
  idem_key TEXT PRIMARY KEY,

  -- Receipt ID from first successful submission
  receipt_id TEXT NOT NULL,

  -- Timestamp of first submission (ISO 8601)
  first_seen_ts TEXT NOT NULL,

  -- State: PENDING, COMMITTED, FAILED
  state TEXT NOT NULL,

  -- Expiry timestamp (24 hours after first_seen_ts)
  expiry_ts TEXT NOT NULL,

  -- Cached response (FlatBuffers serialized, ~2KB)
  cached_response BLOB
);

-- Index for pruning expired entries
CREATE INDEX IF NOT EXISTS idx_idem_expiry ON idem_ledger(expiry_ts);

-- Index for space isolation (if space_id added to schema)
CREATE INDEX IF NOT EXISTS idx_idem_space ON idem_ledger(space_id);
```

---

## K1 → K0 Integration Contract

**File:** `k1/contracts/api/rest/idempotency/k0_integration.md`

### K1 Responsibilities

1. **Accept `Idempotency-Key` header** from client (optional UUID)
2. **Include in K0 envelope** as `idem_key` field
3. **Call K0 Command Port** (`POST /k0/command.submit`)
4. **Handle K0 responses:**
   - 200 OK → Translate to 201 Created (new request)
   - 409 Conflict → Translate to 200 OK with `X-Idempotent-Replayed: true` (duplicate)

### K0 Responsibilities

1. **Receive command envelope** with optional `idem_key`
2. **Derive idem_key** if not provided (BLAKE3 hash from envelope fields)
3. **Check SQLite ledger** for existing idem_key
4. **Return 409** if duplicate (with cached_response)
5. **Process command** if new, insert to ledger, return 200 OK

---

## Performance Comparison

### K0 SQLite vs Redis

| Metric | K0 SQLite (Local) | Redis (Network) |
|--------|-------------------|-----------------|
| **Lookup Latency P50** | <25ms | 8-13ms |
| **Lookup Latency P95** | <150ms | 50-80ms |
| **Insert Latency P50** | <10ms | 3-5ms |
| **Throughput** | 5000+ writes/sec | 10,000+ writes/sec |
| **Offline Capability** | ✅ 100% | ❌ 0% (requires server) |
| **Dependencies** | 0 (SQLite bundled) | 1 (Redis server) |
| **Setup Complexity** | Zero (auto-provision) | High (install, configure, monitor) |
| **Operational Cost** | $0 | $50-500/month |
| **Storage Cost** | Local disk (1GB = 500K entries) | RAM (1GB = 500K entries) |

**Trade-off Analysis:**
- **SQLite:** 2-3× slower than Redis for lookups (25ms vs 8ms), but provides 100% offline capability and zero operational complexity
- **Redis:** Faster but requires external server, online-only, operational overhead
- **FamilyOS Choice:** Local-first SQLite (consistent with dual-kernel architecture, zero dependencies)

---

## Local-First Benefits

### Zero External Dependencies

```
K1 API Gateway
    ↓ (HTTP call, <2ms)
K0 Memory Kernel
    ↓ (SQLite query, <25ms P50)
SQLite database (local disk)
    ↓
No network call required (100% offline)
```

**Benefits:**
1. **100% Offline:** Works without internet connection
2. **Zero Setup:** No Redis installation, no cloud accounts
3. **Zero Cost:** No operational expenses
4. **Instant Startup:** No external service dependencies
5. **Privacy:** All data stays local (GDPR/HIPAA compliance)

---

## Observability

### K0 Prometheus Metrics

**File:** `k0/idem/ledger.py`

```python
# K0 Idempotency Ledger Metrics
k0_idem_lookup = Histogram(
    'k0_idem_lookup_latency_ms',
    'Idempotency ledger lookup latency',
    buckets=[1, 5, 10, 25, 50, 100, 150]
)

k0_idem_duplicate_detected = Counter(
    'k0_idem_duplicate_detected_total',
    'Total duplicate requests detected',
    ['topic']
)

k0_idem_commit_recorded = Counter(
    'k0_idem_commit_recorded_total',
    'Total idempotency keys stored',
    ['topic']
)
```

**Example Queries:**

```promql
# Duplicate detection rate
rate(k0_idem_duplicate_detected_total[5m]) / rate(k0_idem_lookup_latency_ms_count[5m])

# P95 lookup latency
histogram_quantile(0.95, rate(k0_idem_lookup_latency_ms_bucket[5m]))
```

---

## Security

### Space Isolation

```python
# K0 enforces space_id from JWT claims
if envelope["space_id"] != jwt_claims.space_id:
    raise ForbiddenError("Space mismatch")

# Include space_id in idem_key derivation
idem_key = BLAKE3(
    tenant_id | space_id | actor | topic | schema_uri | schema_version | payload_sha256
)
```

**Prevents:** Cross-space attacks (user A can't replay user B's idempotency keys)

---

### Audit Trail

```python
# K0 logs all idempotency operations
audit_logger.info(
    "idempotency_check",
    idem_key=idem_key,
    outcome="hit" | "miss" | "expired",
    receipt_id=receipt_id if hit else None,
    user_id=envelope["actor"],
    space_id=envelope["space_id"],
    trace_id=envelope.get("trace_id")
)
```

---

## Testing

### K0 Integration Tests

**File:** `k0/tests/test_idempotency_ledger.py`

```python
@test("idempotency ledger detects duplicates")
async def test_idempotency_duplicate_detection():
    ledger = IdempotencyLedger(connection_pool)
    idem_key = "req-test-123"

    # First lookup (miss)
    entry = ledger.lookup(idem_key, connection)
    assert entry is None

    # Insert entry
    ledger.upsert(
        LedgerEntry(
            idem_key=idem_key,
            receipt_id="rcpt-001",
            first_seen_ts=datetime.utcnow().isoformat(),
            state="COMMITTED",
            expiry_ts=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
            cached_response=b"..."
        ),
        connection
    )

    # Second lookup (hit)
    entry = ledger.lookup(idem_key, connection)
    assert entry is not None
    assert entry.receipt_id == "rcpt-001"

@test("expired keys return None")
async def test_idempotency_expiry():
    ledger = IdempotencyLedger(connection_pool)
    idem_key = "req-test-456"

    # Insert expired entry
    ledger.upsert(
        LedgerEntry(
            idem_key=idem_key,
            receipt_id="rcpt-002",
            first_seen_ts=(datetime.utcnow() - timedelta(hours=25)).isoformat(),
            state="COMMITTED",
            expiry_ts=(datetime.utcnow() - timedelta(hours=1)).isoformat(),  # Expired
            cached_response=b"..."
        ),
        connection
    )

    # Lookup expired key (returns None)
    entry = ledger.lookup(idem_key, connection)
    assert entry is None  # Expired, treat as new request
```

---

## References

- **K0 README Section 9:** Idempotency & Receipts (full specification)
- **k0/idem/ledger.py:** Actual SQLite implementation (lines 1-200)
- **k0/contracts/sql/idem_ledger.sql:** SQLite table schema
- **k1/contracts/api/rest/idempotency/k0_integration.md:** K1 → K0 integration contract

---

## Rationale

**Why K1 delegates to K0 instead of implementing its own storage?**

1. **Single Source of Truth:** K0 is "the only durable commit surface" (K0 README Section 0). All state changes must go through K0 WAL.
2. **Dual-Channel Consistency:** REST and WebSocket both use K0 for idempotency (prevents duplicate submissions across channels).
3. **Local-First Architecture:** K0 handles all storage (SQLite WAL), K1 is stateless (no local cache, no Redis dependency).
4. **Crash Recovery:** K0 WAL replay reconstructs idempotency ledger on restart (K1 crash = no data loss).
5. **Separation of Concerns:** K1 handles API semantics (REST, HTTP), K0 handles storage (SQLite, durability).

**Why SQLite instead of Redis?**

1. **Local-First:** SQLite is embedded (no external server), works 100% offline
2. **Zero Dependencies:** No Redis installation, no cloud accounts
3. **Zero Cost:** No operational expenses ($0 vs $50-500/month)
4. **Privacy:** All data stays local (GDPR/HIPAA compliance)
5. **Simplicity:** Auto-provision on startup, no configuration

**Performance trade-off accepted:** 2-3× slower than Redis (25ms vs 8ms) for 100% offline capability and zero operational complexity.
