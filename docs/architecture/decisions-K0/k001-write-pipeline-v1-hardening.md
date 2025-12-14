---
adr_number: 'K001'
affected_layers:
- layer5_infrastructure
- layer4_runtime
- layer2_orchestration
affected_modules:
- k0.ports.command
- k0.gate.minimal_gate
- k0.policy.decision
- k0.storage.connection
- k0.uow.unit_of_work
- k0.receipts.generator
- memory_steward
- hippocampus.api
- working_memory.manager
authors:
- K0 Architecture Team
- External Security Reviewer
concerns:
- security
- privacy
- performance
- data-integrity
date_created: '2025-11-10'
date_updated: '2025-11-10'
implementation_date: null
implementation_phase: 'V1 Launch'
implementation_status: ACCEPTED
propagation:
  affected_adrs: []
  affected_contracts:
  - k0/contracts/jsonschema/envelope.schema.json
  - k0/contracts/jsonschema/receipt.schema.json
  affected_tests:
  - tests/k0/ports/test_command_signature.py
  - tests/k0/gate/test_idempotency.py
  - tests/k0/policy/test_obligation_propagation.py
  - tests/k0/storage/test_durability.py
  triggers:
  - External security review identified critical gaps
  - V1 production launch requirements
  - Privacy compliance (AMBER/RED bands)
related_adrs: []
related_contracts:
- k0/contracts/jsonschema/envelope.schema.json
- k0/contracts/jsonschema/receipt.schema.json
related_diagrams:
- docs/envelope_movement/envelope_write_path.md
research_citations:
- 'HMAC-based idempotency keys (RFC 2104)'
- 'SQLite WAL mode durability guarantees (SQLite documentation)'
- 'Geohash privacy masking (Gustavo Niemeyer, 2008)'
status: ACCEPTED
superseded_by: []
supersedes: []
title: Write Pipeline V1 Security & Privacy Hardening
---

# ADR-K001: Write Pipeline V1 Security & Privacy Hardening

**Status**: Accepted

**Date**: 2025-11-10

**Authors**: @K0-Architecture-Team, @External-Security-Reviewer

## Context

The K0 write pipeline (Command Port → MinimalGate → PEP → Memory Steward → Hippocampus → st_hipp_store) was reviewed for production readiness. External security review identified **10 critical gaps** that must be addressed before V1 launch:

### Current Pain Points

1. **Signature tampering vulnerability**: Only `body` is signed; headers (actor, space_id, band, ts) can be tampered post-K1
2. **Replay attack exposure**: Human-readable `idem_key` allows cross-device collisions and replay attacks
3. **Privacy band leakage**: PEP creates separate PolicyDecision object; obligations can be dropped downstream
4. **Location privacy violation**: Raw lat/lon stored for ALL bands (AMBER/RED non-compliant)
5. **Data loss risk**: Default SQLite settings don't guarantee durability on crash
6. **Time confusion**: No clock skew validation; vulnerable to time-travel attacks
7. **Performance regression**: Embedding generation blocks commit (~50ms), exceeds P95 budget
8. **Working memory broken**: L1 cache TTL is 100ms (likely typo), causing thrashing
9. **Audit gap**: Receipts missing critical fields (envelope_sha256, obligations_applied)
10. **Documentation mismatch**: Doc claims only PII modifies body; obligations also modify location/time/mentions

### Business Drivers

- **V1 Production Launch**: Cannot ship with security/privacy violations
- **Privacy Compliance**: GDPR/CCPA require AMBER/RED location masking
- **Performance SLA**: User-facing latency must be <100ms P95
- **Data Safety**: Zero tolerance for data loss on device crash

### Constraints

- **Latency Budget**: 150ms P95 → 100ms P95 target
- **K1 Trust Boundary**: K1 is external orchestrator; K0 must verify all inputs
- **Single-Writer SQLite**: No distributed transactions; must use WAL mode
- **Device Constraints**: Mobile devices have limited CPU/memory

## Decision

Implement **10 mandatory changes** for V1 launch, organized into 5 categories:

### 1. Security Hardening (3 changes)

#### A. Full Envelope Signature

**Change**: Sign canonicalized envelope (headers + body), not just body.

**Implementation**:

```json
// ADD TO ENVELOPE HEADER
"sig_alg": "ECDSA_P256_SHA256",
"sig_kid": "did:device:dad-phone#2025-10-01",
"envelope_sha256": "sha256:c4a7...",  // Replaces payload_sha256
"sig": "MEUC..."                       // Signs envelope_sha256
```

**Validation** (MinimalGate):

```python
def verify_envelope_signature(envelope: Envelope) -> bool:
    # 1. Compute canonical envelope (exclude sig field)
    canonical = canonicalize(envelope, exclude=["sig"])
    computed_hash = sha256(canonical)

    # 2. Verify computed hash matches envelope_sha256
    if computed_hash != envelope.envelope_sha256:
        raise HashMismatchError()

    # 3. Verify signature covers envelope_sha256
    public_key = resolve_key(envelope.sig_kid)
    if not verify_ecdsa(public_key, envelope.envelope_sha256, envelope.sig):
        raise SignatureInvalidError()

    return True
```

**Files Modified**:
- `k0/contracts/jsonschema/envelope.schema.json` (add sig_alg, sig_kid, envelope_sha256)
- `k0/gate/minimal_gate.py` (implement full envelope verification)
- K1 orchestrator (sign canonicalized envelope)

#### B. HMAC-Based Idempotency Keys

**Change**: Derive `idem_key` from envelope hash using HMAC.

**Implementation**:

```python
def derive_idem_key(envelope: Envelope, device_secret: bytes) -> str:
    # Time bucket prevents cross-session replays
    time_bucket = int(envelope.ts.timestamp() / 60) * 60  # 60s buckets
    message = f"{envelope.envelope_sha256}||{time_bucket}"

    hmac_value = hmac.new(device_secret, message.encode(), hashlib.sha256).hexdigest()
    return f"idem:{hmac_value[:32]}"
```

**Replay Detection** (Command Port):

```python
async def check_idempotency(envelope: Envelope) -> bool:
    # 1. Check idem_key in ledger
    if await self.ledger.exists(envelope.idem_key):
        raise DuplicateRequestError(envelope.idem_key)

    # 2. Check envelope_sha256 in WAL (stronger duplicate check)
    if await self.wal.exists_by_hash(envelope.envelope_sha256):
        raise ReplayAttackError(envelope.envelope_sha256)

    return True
```

**Files Modified**:
- `k0/ports/command.py` (derive idem_key, check WAL)
- `k0/idem/ledger.py` (add envelope_sha256 lookup)
- `k0/storage/wal.py` (add hash index)

#### C. Time & Replay Protection

**Change**: Reject requests with excessive clock skew.

**Implementation**:

```python
MAX_CLOCK_SKEW_SECONDS = 600  # 10 minutes

def validate_timestamp(envelope: Envelope, now: datetime) -> None:
    client_ts = datetime.fromisoformat(envelope.ts)
    clock_skew_ms = abs((now - client_ts).total_seconds() * 1000)

    if clock_skew_ms > MAX_CLOCK_SKEW_SECONDS * 1000:
        raise ClockSkewError(f"Skew {clock_skew_ms}ms exceeds {MAX_CLOCK_SKEW_SECONDS}s")

    # Store both clocks for audit
    envelope.ingested_at = now.isoformat()
    envelope.clock_skew_ms = int(clock_skew_ms)
```

**Files Modified**:
- `k0/gate/minimal_gate.py` (add time validation)
- `k0/config/gate.yml` (add max_clock_skew_seconds)

### 2. Privacy Compliance (2 changes)

#### D. Policy Stamp Propagation

**Change**: Attach `policy_stamp` to envelope after PEP; all downstream consumers read obligations from stamp.

**Implementation**:

```python
@dataclass
class PolicyStamp:
    policy_version: str
    band: str
    obligations: List[str]
    visible_to: List[str]
    decision: str  # ALLOW/DENY

# After PEP evaluation
policy_stamp = PolicyStamp(
    policy_version=envelope.policy_version,
    band=envelope.band,
    obligations=pep_decision.obligations,
    visible_to=pep_decision.visible_to,
    decision=pep_decision.decision
)

# Attach to envelope
envelope.policy_stamp = policy_stamp

# Memory Steward reads obligations from stamp
for obligation in envelope.policy_stamp.obligations:
    apply_obligation(envelope, obligation)
```

**Obligations Applied by Memory Steward**:
- `mask.location.precision` → Geohash for AMBER/RED
- `redact.pii` → PII patterns replaced with placeholders
- `mask.time.precision` → Time bucketed to hour/day

**Files Modified**:
- `memory_steward/__init__.py` (attach stamp after PEP, read obligations)
- `k0/uow/unit_of_work.py` (persist stamp in WAL)
- `k0/outbox/publisher.py` (include stamp in payload)

#### E. Location Privacy Masking

**Change**: Store geohash (not raw lat/lon) for AMBER/RED bands.

**Implementation**:

```python
import geohash

def apply_location_masking(envelope: Envelope) -> None:
    band = envelope.policy_stamp.band

    if band in ["AMBER", "RED"]:
        # AMBER: 5km precision (geohash length 6)
        # RED: 25km precision (geohash length 4)
        precision = 6 if band == "AMBER" else 4

        lat = envelope.body.location_lat
        lon = envelope.body.location_lon

        # Compute geohash
        gh = geohash.encode(lat, lon, precision=precision)

        # Store masked version in primary columns
        envelope.body.location_geohash = gh
        envelope.body.location_precision_m = 5000 if band == "AMBER" else 25000

        # Clear exact coordinates (or move to encrypted side table)
        envelope.body.location_lat = None
        envelope.body.location_lon = None
```

**Database Schema**:

```sql
ALTER TABLE st_hipp_store ADD COLUMN location_geohash TEXT;
ALTER TABLE st_hipp_store ADD COLUMN location_precision_m INTEGER;
-- location_lat/lon become nullable or moved to encrypted table
```

**Files Modified**:
- `memory_steward/__init__.py` (RedactionCoordinator)
- `docs/whiteboard/whiteboard_schema.md` (st_hipp_store schema)
- `k0/storage/migrations/001_add_geohash.sql`

### 3. Performance Optimization (1 change)

#### F. Async Embeddings/FTS

**Change**: Move embedding generation and FTS indexing to async workers; don't block commit.

**Implementation**:

```python
# Memory Steward (BEFORE)
embedding_id = await self.embedding_service.generate(text)  # BLOCKS 50ms
envelope.body.embedding_id = embedding_id

# Memory Steward (AFTER)
envelope.body.embedding_status = "PENDING"
envelope.body.fts_status = "PENDING"

# Outbox payload includes async work items
outbox_payload = {
    "event_id": event_id,
    "next_actions": ["embedding.enqueue", "fts.enqueue"]
}
```

**Async Workers**:

```python
# k0/workers/embedding_worker.py
async def process_embedding(event_id: str):
    event = await db.get(event_id)
    embedding_id = await embedding_service.generate(event.text)

    await db.execute(
        "UPDATE st_hipp_store SET embedding_id = ?, embedding_status = 'DONE' WHERE event_id = ?",
        (embedding_id, event_id)
    )
```

**Database Schema**:

```sql
ALTER TABLE st_hipp_store ADD COLUMN embedding_status TEXT DEFAULT 'PENDING';
ALTER TABLE st_hipp_store ADD COLUMN fts_status TEXT DEFAULT 'PENDING';
-- embedding_id becomes nullable
```

**Performance Impact**: 150ms P95 → 80-100ms P95

**Files Modified**:
- `memory_steward/__init__.py` (don't wait for embeddings)
- `k0/workers/embedding_worker.py` (new)
- `k0/workers/fts_worker.py` (new)
- `k0/outbox/publisher.py` (add topics)

### 4. Data Safety (1 change)

#### G. SQLite Durability Settings

**Change**: Enable WAL mode and full synchronous mode at K0 init.

**Implementation**:

```python
# k0/storage/connection.py
def init_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)

    # Critical durability settings
    conn.execute("PRAGMA journal_mode=WAL")      # Write-Ahead Log
    conn.execute("PRAGMA synchronous=FULL")      # fsync on every commit
    conn.execute("PRAGMA foreign_keys=ON")       # Referential integrity
    conn.execute("PRAGMA temp_store=MEMORY")     # Temp tables in RAM
    conn.execute("PRAGMA busy_timeout=5000")     # 5s retry on lock

    return conn
```

**Crash Recovery Test**:

```python
# tests/k0/storage/test_durability.py
async def test_crash_recovery():
    # Write envelope
    envelope_id = await command_port.submit(envelope)

    # Simulate crash (kill process)
    await simulate_crash()

    # Restart K0
    await k0.restart()

    # Verify envelope persisted
    assert await wal.exists(envelope_id)
    assert await st_hipp_store.exists(envelope_id)
```

**Files Modified**:
- `k0/storage/connection.py` (set pragmas)
- `k0/config/storage.yml` (add durability_mode)
- `tests/k0/storage/test_durability.py` (crash recovery test)

### 5. Bug Fixes & Audit (3 changes)

#### H. Working Memory TTL Fix

**Change**: Fix L1 cache TTL from 100ms to 100 seconds.

**Implementation**:

```python
# working_memory/manager.py (BEFORE)
L1_TTL_SECONDS = 0.1  # 100ms - WRONG

# working_memory/manager.py (AFTER)
L1_TTL_SECONDS = 100   # 100 seconds
L2_TTL_SECONDS = 300   # 5 minutes
L3_TTL_SECONDS = 86400 # 24 hours
```

**Files Modified**:
- `working_memory/manager.py` (fix constant)
- `k0/config/working_memory.yml` (add TTL config)

#### I. Receipt Enhancement

**Change**: Add audit fields to receipt.

**Implementation**:

```json
// Receipt (BEFORE)
{
  "receipt_id": "rcpt-...",
  "envelope_id": "evt-...",
  "status": "ok"
}

// Receipt (AFTER)
{
  "receipt_id": "rcpt-...",
  "envelope_id": "evt-...",
  "envelope_sha256": "sha256:...",
  "status": "ok",
  "policy_band": "AMBER",
  "obligations_applied": ["mask.location.precision"]
}
```

**Files Modified**:
- `k0/receipts/generator.py` (add fields)
- `k0/contracts/jsonschema/receipt.schema.json` (update schema)

#### J. Documentation Corrections

**Change**: Clarify that policy obligations modify body (not just PII redaction).

**Documentation Updates**:
- Update `docs/envelope_movement/envelope_write_path.md`
- Add section on obligation transformations
- Document CA1 obligation filtering (KG triples respect masking)
- Add `k0/config/models.yml` for embedding_model_version

**Files Modified**:
- `docs/envelope_movement/envelope_write_path.md`
- `k0/config/models.yml` (new)

## Architecture Diagram References

**Updated Flow**:

```
K1 → [Full Envelope Signature] → Command Port
  ↓ [Verify envelope_sha256 + sig]
MinimalGate [Time skew check <10min]
  ↓
PEP [Attach Policy Stamp]
  ↓
Memory Steward [Apply Obligations]:
  - Location masking (geohash for AMBER/RED)
  - PII redaction
  - Time bucketing
  ↓
Hippocampus [Pattern Separation]
  ↓
UnitOfWork [ACID Transaction]:
  - WAL (with policy_stamp)
  - st_hipp_store (with geohash, status flags)
  - Outbox (with async topics)
  - Receipt (with envelope_sha256, obligations)
  ↓
Working Memory [L1: 100s, L2: 5min, L3: 24h]
  ↓
[Async Workers]:
  - Embedding Worker → embedding_status = DONE
  - FTS Worker → fts_status = DONE
```

**Diagrams**:
- `docs/envelope_movement/envelope_write_path.md` (updated with V1 requirements)

## Consequences

### Positive

1. **Security Hardened**: Full envelope signature prevents header tampering; HMAC idempotency prevents replay attacks
2. **Privacy Compliant**: AMBER/RED location masking meets GDPR/CCPA requirements
3. **Performance Improved**: 150ms → 80-100ms P95 (async embeddings)
4. **Data Safe**: WAL + FULL sync prevents data loss on crash
5. **Audit Complete**: Receipts include envelope_sha256 and obligations_applied
6. **Working Memory Fixed**: L1 cache functional with 100s TTL
7. **Trust Boundary Clear**: K0 verifies all K1 inputs; no blind trust

### Negative

1. **Complexity Increased**: Policy stamp adds boilerplate; 3 new config files
2. **Storage Overhead**: Geohash + precision_m + status flags add ~100 bytes per row
3. **Async Complexity**: Embedding/FTS workers add operational overhead (monitoring, retry logic)
4. **Migration Required**: Existing data needs backfill for new columns

### Risks

1. **K1 Integration**: K1 must implement full envelope signing (coordination required)
2. **Performance Regression**: Async workers could introduce latency spikes if queue backs up
3. **SQLite Lock Contention**: WAL mode + FULL sync may increase lock contention under high write load
4. **Geohash Precision**: 5km masking may be insufficient for RED band (consider 25km)

**Mitigation**:
- K1 coordination: Schedule joint testing sprint
- Queue backpressure: Monitor Outbox depth; alert if >1000 pending
- SQLite tuning: Increase `busy_timeout` to 10s; consider read replicas
- Geohash review: Add config for band-specific precision levels

## Alternatives Considered

### Alternative 1: Trust K1 Analysis (Skip Signature Verification)

**Description**: Assume K1 is trusted; skip full envelope signature verification.

**Why Rejected**:
- K1 is external orchestrator (trust boundary violation)
- Single compromised device could inject tampered envelopes
- No audit trail for envelope integrity
- **Security risk: CRITICAL**

### Alternative 2: Synchronous Embeddings (Skip Async Workers)

**Description**: Keep embedding generation in commit path; optimize with caching.

**Why Rejected**:
- Cannot hit <100ms P95 target with 50ms embedding overhead
- Caching doesn't help for novel events (novelty=0.8 means cache miss)
- Blocks UnitOfWork commit (increases transaction hold time)
- **Performance risk: HIGH**

### Alternative 3: Store Raw Lat/Lon with Encryption (Skip Geohash)

**Description**: Store encrypted exact coordinates; decrypt on query.

**Why Rejected**:
- Encryption key management complexity (where to store keys?)
- Decryption adds latency to every query
- Doesn't meet privacy requirement (GDPR: "data minimization" means don't store what you don't need)
- **Privacy risk: MEDIUM**

### Alternative 4: PostgreSQL Instead of SQLite

**Description**: Use PostgreSQL for durability and concurrency.

**Why Rejected**:
- K0 targets single-device deployment (mobile, desktop)
- PostgreSQL requires server setup (defeats single-binary goal)
- SQLite WAL mode sufficient for single-writer workload
- **Complexity cost: HIGH**

## Implementation Notes

### Phasing Strategy

**Phase 1 (Week 1): Security & Privacy** (30-40 hours)
1. Signature & hash scope
2. Idempotency key derivation
3. Policy stamp propagation
4. Location privacy masking
5. SQLite durability settings
6. Time & replay hygiene

**Phase 2 (Week 2): Performance & Operations** (15-25 hours)
7. Async embeddings/FTS workers
8. Working memory TTL fix
9. Receipt enhancement
10. Documentation corrections

### Migration Path

**Database Migration**:

```sql
-- Migration 001: Add V1 columns
ALTER TABLE st_hipp_store ADD COLUMN ingested_at TEXT;
ALTER TABLE st_hipp_store ADD COLUMN clock_skew_ms INTEGER;
ALTER TABLE st_hipp_store ADD COLUMN envelope_sha256 TEXT;
ALTER TABLE st_hipp_store ADD COLUMN location_geohash TEXT;
ALTER TABLE st_hipp_store ADD COLUMN location_precision_m INTEGER;
ALTER TABLE st_hipp_store ADD COLUMN embedding_status TEXT DEFAULT 'PENDING';
ALTER TABLE st_hipp_store ADD COLUMN fts_status TEXT DEFAULT 'PENDING';

-- Index for replay detection
CREATE UNIQUE INDEX idx_envelope_sha256 ON st_hipp_store(envelope_sha256);

-- Index for geohash queries
CREATE INDEX idx_location_geohash ON st_hipp_store(location_geohash);
```

**Backward Compatibility**:
- V0 envelopes without `envelope_sha256`: Compute on ingestion, reject if `sig` missing
- V0 rows without `geohash`: Backfill during P03 consolidation (async job)
- V0 embeddings: Mark as `embedding_status = 'DONE'` (already generated)

### Testing Requirements

**Security Tests**:
- [ ] Signature tampering rejected (modify header after sign)
- [ ] Replay attack blocked (same envelope_sha256 twice)
- [ ] Time skew >10min rejected
- [ ] Policy stamp persisted through pipeline

**Privacy Tests**:
- [ ] AMBER location masked to geohash-6
- [ ] RED location masked to geohash-4
- [ ] GREEN location raw (no masking)
- [ ] Obligations applied before storage

**Performance Tests**:
- [ ] P95 latency <100ms (with async embeddings)
- [ ] Embedding worker processes within 5s
- [ ] FTS worker processes within 10s
- [ ] Outbox depth <100 under load

**Durability Tests**:
- [ ] Crash recovery: envelope persists after kill -9
- [ ] WAL checkpoint: data moves to main DB
- [ ] Foreign key constraints enforced

### Rollback Plan

**If Critical Bug in Production**:

1. **Disable async workers**: Set `ASYNC_ENABLED=false` in config (reverts to synchronous embeddings)
2. **Relax time skew**: Increase `MAX_CLOCK_SKEW_SECONDS` from 600 to 3600 (1 hour)
3. **Skip geohash masking**: Set `PRIVACY_MASKING_ENABLED=false` (log violation, don't block)
4. **Full rollback**: Deploy V0 binary; run migration 001 rollback script

**Rollback Script**:

```sql
-- Rollback 001: Remove V1 columns (WARNING: data loss)
ALTER TABLE st_hipp_store DROP COLUMN ingested_at;
ALTER TABLE st_hipp_store DROP COLUMN clock_skew_ms;
ALTER TABLE st_hipp_store DROP COLUMN envelope_sha256;
ALTER TABLE st_hipp_store DROP COLUMN location_geohash;
ALTER TABLE st_hipp_store DROP COLUMN location_precision_m;
ALTER TABLE st_hipp_store DROP COLUMN embedding_status;
ALTER TABLE st_hipp_store DROP COLUMN fts_status;

DROP INDEX idx_envelope_sha256;
DROP INDEX idx_location_geohash;
```

## References

**Architecture Documents**:
- `docs/envelope_movement/envelope_write_path.md` (complete write path)
- `docs/envelope_movement/v1_requirements_analysis.md` (full analysis)
- `docs/whiteboard/whiteboard_schema.md` (st_hipp_store schema)

**External Review**:
- Security review findings (2025-11-10)
- Privacy compliance requirements (GDPR/CCPA)

**Research Citations**:
- **HMAC**: RFC 2104 (Krawczyk, Bellare, Canetti, 1997)
- **SQLite WAL**: SQLite Write-Ahead Logging documentation
- **Geohash**: Gustavo Niemeyer, 2008 (public domain algorithm)
- **Time-based Idempotency**: Stripe API design patterns

**Related ADRs**: None (this is first K0 ADR)

**Specifications**:
- Envelope Schema: `k0/contracts/jsonschema/envelope.schema.json`
- Receipt Schema: `k0/contracts/jsonschema/receipt.schema.json`
- Policy Schema: `k0/contracts/policy/pep.schema.json`

**Performance Budgets**:

| Stage | V0 P95 | V1 P95 Target |
|-------|--------|---------------|
| Command Port + MinimalGate | 10ms | 8ms |
| PEP | 5ms | 5ms |
| Memory Steward | 15ms | 12ms |
| Hippocampus DG | 20ms | 20ms |
| UnitOfWork Commit | 50ms | 15ms |
| Embedding (async) | 50ms (blocking) | 5s (background) |
| **Total** | **150ms** | **80-100ms** |

## Revision History

- 2025-11-10: Initial draft (K0 Architecture Team)
- 2025-11-10: Accepted for V1 implementation (K0 Architecture Team)
