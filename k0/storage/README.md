# K0 Storage Module

**Purpose**: Persistence adapters for WAL, outbox, offsets, receipts, DLQ, provisioning, snapshots, FTS, obligations, replay, and shard promotion.

**Layer**: Storage & Persistence
**Category**: SQLite storage adapters, durability guarantees
**Related ADRs**: ADR-0140 (WAL V1 Envelope Integrity), ADR-0141 (Outbox Pattern), ADR-0142 (Snapshot Scheduler)

---

## Overview

The storage module provides **12 persistence adapters**:

1. **WAL** (`wal.py`): Write-Ahead Log with V1 envelope integrity (envelope_sha256)
2. **Outbox** (`outbox.py`): Async driver intents with exponential backoff (Migration 0004)
3. **DLQ** (`dlq.py`): Dead-letter queue for failed outbox entries
4. **Offsets** (`offsets.py`): Subscriber offset tracking for SSE acknowledgments
5. **Receipts** (`receipts.py`): Receipt persistence with WAL position linkage
6. **Provisioning** (`provisioning.py`): Device bindings and key rotation with LRU caching
7. **Obligations** (`obligations.py`): Policy obligation log (ADR-0089)
8. **FTS** (`fts.py`, `fts5_indexer.py`): Full-text search indexing (SQLite FTS5 + BM25)
9. **Replayer** (`replayer.py`): Cold replay coordinator for parity validation
10. **Snapshots** (`snapshots.py`): Point-in-time snapshots with WAL watermark markers
11. **Shard Promotion** (`shard_promotion.py`): Primary/standby synchronization for HA

**Storage Technology**: SQLite with connection pooling, row factory, and defensive transactions

---

## Repository Files Summary

### Core Storage Adapters

| File | Purpose | Key Tables | Key Features |
|------|---------|------------|--------------|
| `wal.py` | Write-Ahead Log | `st_wal` | V1 envelope integrity, async worker status, policy stamps |
| `outbox.py` | Async driver queue | `st_outbox` | Exponential backoff, status tracking, requeue_seq |
| `dlq.py` | Dead-letter queue | `st_dlq` | Retry tracking, quarantine state, Gap 23 collision prevention |
| `offsets.py` | Subscriber offsets | `st_offsets` | Per-subscriber/topic tracking, Gap 32 RLock concurrency |
| `receipts.py` | Receipt storage | `st_receipts` | WAL position linkage, manifest fingerprints |
| `provisioning.py` | Device provisioning | `st_devices`, `st_device_keys` | LRU caching, key rotation states |
| `obligations.py` | Obligation log | `st_obligation_log` | Policy enforcement tracking (ADR-0089) |
| `fts.py` | FTS operations | `st_fts` | Full-text search with BM25 scoring |
| `fts5_indexer.py` | Memory indexing | `st_epi_fts`, `st_hipp_fts` | Episodic/hippocampus keyword search |
| `replayer.py` | Replay coordinator | N/A | Parity validation (WAL→receipts→outbox), Gap 22/33 |
| `snapshots.py` | Snapshot scheduler | `st_wal` | Watermark markers, SQLite BACKUP API |
| `shard_promotion.py` | Shard sync | `st_wal`, `st_receipts` | Primary/standby reconciliation, lag metrics |

### WAL (V1 Envelope Integrity)

**Key V1 Changes**:
- `envelope_sha256`: Full canonical envelope hash (body + headers)
- `ingested_at`: Server-side timestamp for clock skew tracking
- `clock_skew_ms`: Difference between device `ts` and `ingested_at`
- `policy_stamp_json`: Policy evaluation result (band, obligations, redactions)
- `location_geohash`/`location_precision_m`: Privacy-preserving location tracking
- `embedding_status`/`fts_status`: Async worker progress (PENDING/IN_PROGRESS/COMPLETE/FAILED)

**Performance**: ~100µs append latency, supports fsync with chaos injection

### Outbox (Exponential Backoff - Migration 0004)

**Key Features**:
- `next_attempt_ts`: ISO8601 timestamp for retry scheduling
- `backoff_exp`: Exponent for 2^n exponential backoff
- `status`: PENDING/PROCESSING/FAILED/DEAD
- `dequeue_ready_batch()`: Respects backoff timing (WHERE next_attempt_ts <= NOW())
- **Fallback**: Legacy schema support (baseline without backoff columns)

**Backoff Algorithm**: `next_attempt_ts = now + (2^backoff_exp) seconds`

### DLQ (Dead-Letter Queue - Gap 44)

**Key Features**:
- Gap 23: `_get_next_requeue_seq()` prevents collision with outbox
- Gap 44: Metrics tracking (entries by state, retry attempts, requeue latency)
- State transitions: PENDING → REQUEUED → QUARANTINED
- `mark_requeued()`: Safely computes next requeue_seq from outbox MAX(requeue_seq)

### Offsets (Subscriber Tracking - Gap 32)

**Key Features**:
- Gap 32: `threading.RLock()` protects concurrent read/write operations
- Per-subscriber/topic/space/tenant tracking
- Upsert semantics (ON CONFLICT DO UPDATE)

### Provisioning (Device Keys - Key Rotation)

**Key Features**:
- **Device Bindings**: tenant_id, space_id, mls_group_id
- **Key Rotation**: key_state (PENDING/ACTIVE/ROTATING/REVOKED)
- **Grace Periods**: `grace_expires_ts` for overlapping key rotation
- **LRU Caching**: 512 entries for device records, 512 for key records
- **Defensive**: Normalized verify keys (stripped whitespace)

**Key States**:
- `PENDING`: Registered but not yet activated
- `ACTIVE`: Currently valid for signature verification
- `ROTATING`: In grace period during rotation
- `REVOKED`: No longer valid

### FTS (Full-Text Search)

**FTS5 Features**:
- BM25 relevance scoring (lower score = more relevant)
- Keyword search across episodic (`st_epi_fts`) and hippocampus (`st_hipp_fts`) memories
- Searchable fields: text, summary, tags, topics, location_names, participant_names
- `search_episodic()`/`search_hippocampus()`: Query with tenant/space filtering

### Replayer (Cold Replay - Gap 22/33)

**Key Features**:
- Gap 33: Explicit transactions for atomic parity checks (WAL → receipts → outbox → offsets)
- Gap 22: `_verify_outbox_parity()` checks WAL→outbox linkage
- Schema validation: Reject BLOCKED schemas
- Receipt parity: Verify every WAL entry has corresponding receipt
- Dry-run support: Detect parity violations without failing

### Snapshots (Watermark Markers - Issue #044)

**Key Features**:
- Point-in-time snapshots with SQLite BACKUP API
- WAL watermark markers (BEGIN/COMMIT) for replay resumption
- Manifest files (JSON) with snapshot metadata
- Issue #044: `snapshot_watermark` gauge metric

### Shard Promotion (HA Synchronization)

**Key Features**:
- Primary/standby WAL delta synchronization
- Receipt parity validation (all WAL entries must have receipts)
- Lag calculation: `(primary_latest_ts - standby_latest_ts).total_seconds()`
- Metrics: `wal_replica_lag_seconds`, `kernel_replay_watermark`

---

## Usage Examples

### WAL Append (V1 Envelope Integrity)

```python
from k0.storage import WriteAheadLog
from k0.security import compute_envelope_sha256

wal = WriteAheadLog(metrics=metrics_exporter)

# Compute envelope hash
envelope_sha256 = compute_envelope_sha256(envelope)

# Append to WAL
entry = WalEntry(
    tenant_id="tenant_001",
    space_id="space_001",
    topic="memory.store",
    envelope_json=canonical_json(envelope),
    body=body_bytes,
    payload_sha256=hash_payload(body_bytes),
    schema_uri="https://schema.dev/memory.store.json",
    schema_version="1.0.0",
    device_id="device_abc",
    commit_ts=now_iso8601,
    envelope_sha256=envelope_sha256,  # V1 NEW
    ingested_at=server_now_iso8601,  # V1 NEW
    clock_skew_ms=100,  # V1 NEW
    policy_stamp_json=policy_json,  # V1.3 NEW
    embedding_status="PENDING",  # V1.4 NEW
)

position = wal.append(entry)
print(f"WAL position: {position}")
```

### Outbox with Exponential Backoff

```python
from k0.storage import OutboxStore
from datetime import datetime, timezone, timedelta

outbox = OutboxStore(metrics=metrics_exporter)

# Enqueue outbox entry
entry = OutboxEntry(
    id=None,
    wal_pos=1500,
    tenant_id="tenant_001",
    space_id="space_001",
    driver="embedding_driver",
    op_kind="memory.embed",
    payload=payload_bytes,
    fingerprint="abc123",
    requeue_seq=0,
    retries=0,
    status="PENDING",
)

entry_id = outbox.enqueue(entry)

# Dequeue ready entries (respects backoff timing)
ready_entries = outbox.dequeue_ready_batch(driver="embedding_driver", limit=128)

# Record failure with exponential backoff
if processing_failed:
    backoff_exp = entry.backoff_exp + 1
    next_attempt = datetime.now(timezone.utc) + timedelta(seconds=2**backoff_exp)

    outbox.record_failure(
        entry,
        retries=entry.retries + 1,
        requeue_seq=entry.requeue_seq,
        last_error="Connection timeout",
        next_attempt_ts=next_attempt.isoformat(),
        backoff_exp=backoff_exp,
        status="PENDING",
    )
```

### DLQ with Safe Requeue

```python
from k0.storage import DeadLetterQueue

dlq = DeadLetterQueue(metrics=metrics_exporter)

# Record dead-letter
letter = DeadLetter(
    id=None,
    wal_pos=1500,
    tenant_id="tenant_001",
    space_id="space_001",
    driver="embedding_driver",
    op_kind="memory.embed",
    fingerprint="abc123",
    payload=payload_bytes,
    reason="Max retries exceeded (5 attempts)",
    retries=5,
    requeue_seq=0,
    first_failure_ts=first_fail_iso,
    last_failure_ts=now_iso,
    state="PENDING",
)

letter_id = dlq.record(letter)

# Mark as requeued (Gap 23: safe requeue_seq)
dlq.mark_requeued(letter_id)  # Computes next safe requeue_seq from outbox
```

### Provisioning with Key Rotation

```python
from k0.storage import ProvisioningLedger, DeviceKey

ledger = ProvisioningLedger(cache_size=512, key_cache_size=512)

# Register device
device = ProvisionedDevice(
    device_id="device_abc",
    tenant_id="tenant_001",
    space_id="space_001",
    mls_group_id="group_001",
    provisioned_ts=now_iso,
)
ledger.register(device)

# Add verification key
key = DeviceKey(
    device_id="device_abc",
    key_version="key_v1",
    verify_key="abc123def456...",
    key_state="ACTIVE",
    registered_ts=now_iso,
    activated_ts=now_iso,
)
ledger.add_key(key)

# Lookup device with key filtering
keys = ledger.get_keys("device_abc", states=["ACTIVE", "ROTATING"])
for key in keys:
    print(f"Key {key.key_version}: {key.key_state}")
```

### FTS Keyword Search

```python
from k0.storage.fts5_indexer import FTS5Indexer

indexer = FTS5Indexer(connection)

# Index episodic memory
indexer.index_episodic(
    event_id="evt_123",
    text="Had dinner with Mom at Olive Garden",
    summary="Family dinner",
    tags=["family", "dinner"],
    topics=["social", "food"],
    location_names=["Olive Garden"],
    participant_names=["Mom"],
    tenant_id="tenant_001",
    space_id="space_001",
    commit_ts=now_iso,
)

# Search memories
results = indexer.search_episodic(
    query="dinner Mom",
    limit=20,
    tenant_id="tenant_001",
    space_id="space_001",
)
print(f"Found {len(results)} matching memories")
```

### Snapshot with Watermark

```python
from k0.storage import SnapshotScheduler
from pathlib import Path

scheduler = SnapshotScheduler(
    database_path=Path("/data/k0_kernel.db"),
    metrics=metrics_exporter,
    observability=emitter,
    write_ahead_log=wal,
)

# Create snapshot
manifest = scheduler.create_snapshot(
    output_dir=Path("/backups"),
    snapshot_id="snap-20251112T100000-abc123",
    dry_run=False,
)

print(f"Snapshot created at watermark {manifest.watermark}")
print(f"Artifact: {manifest.artifact_path}")
print(f"Manifest: {manifest.manifest_path}")
```

### Shard Promotion

```python
from k0.storage import ShardPromotionCoordinator

coordinator = ShardPromotionCoordinator(
    shard_id="shard_001",
    primary_path=Path("/data/primary.db"),
    standby_path=Path("/data/standby.db"),
    metrics=metrics_exporter,
    observability=emitter,
)

# Compute replica lag
lag = coordinator.compute_replica_lag()
print(f"Replica lag: {lag:.2f}s")

# Promote standby (sync WAL delta)
result = coordinator.promote()
print(f"Applied {len(result.applied_positions)} WAL entries")
print(f"Lag before: {result.lag_before_seconds:.2f}s")
print(f"Lag after: {result.lag_after_seconds:.2f}s")
```

---

## Performance & Observability

### Metrics

- **WAL**: `wal_current_position` (gauge), `wal_append_latency_seconds` (histogram)
- **Outbox**: `outbox_pending_total` (gauge by driver), `outbox_dequeue_latency_seconds`
- **DLQ**: `dlq_entries_by_state` (gauge), `dlq_retry_attempts_total`, `dlq_requeue_latency_seconds`
- **Snapshots**: `snapshot_watermark` (gauge), `snapshot_create_total` (counter), `snapshot_open_transactions` (gauge)
- **Shard**: `wal_replica_lag_seconds` (gauge), `shard_promotion_total` (counter)

### Performance Targets (P95)

| Operation | Latency | Throughput |
|-----------|---------|------------|
| WAL append | <100µs | 10K ops/s |
| Outbox enqueue | <200µs | 5K ops/s |
| Offset upsert | <50µs | 20K ops/s |
| Provisioning lookup (cached) | <10µs | 100K ops/s |
| FTS search | <10ms | 100 queries/s |
| Snapshot creation | <5s | N/A |

---

## Integration Points

### Upstream Dependencies

- **`k0.uow.connection_pool`**: Connection pooling and scope management
- **`k0.obs`**: MetricsExporter, ObservabilityEmitter
- **`k0.security`**: Canonical JSON, envelope hashing
- **SQLite**: Row factory, transactions, FTS5

### Downstream Consumers

- **`k0.kernel`**: WAL append, outbox enqueue
- **`k0.workers`**: Outbox processing, DLQ retry
- **`k0.sse`**: Offset tracking, WAL streaming
- **`k0.gate`**: Provisioning lookup, receipt storage
- **`k0.query`**: FTS search, WAL read

---

## Related ADRs

- **ADR-0140**: WAL V1 Envelope Integrity with envelope_sha256
- **ADR-0141**: Outbox Pattern with Exponential Backoff (Migration 0004)
- **ADR-0142**: Snapshot Scheduler with Watermark Markers
- **ADR-0143**: FTS5 Indexing for Memory Search
- **ADR-0144**: Shard Promotion for High Availability
- **ADR-0145**: Provisioning Ledger with Key Rotation

---

## Key Design Decisions

1. **V1 Envelope Integrity**: Full envelope hash (envelope_sha256) prevents header tampering
2. **Exponential Backoff**: Outbox retry timing respects next_attempt_ts (Migration 0004)
3. **Gap 23 Collision Prevention**: DLQ computes safe requeue_seq from outbox MAX
4. **Gap 32 Concurrency**: Offsets use RLock for thread-safe read/write
5. **LRU Caching**: Provisioning uses 512-entry caches for hot path performance
6. **FTS5 BM25**: Relevance scoring with SQLite full-text search
7. **Atomic Parity Checks**: Replayer wraps checks in IMMEDIATE transactions (Gap 33)
8. **Watermark Markers**: Snapshots emit BEGIN/COMMIT markers to WAL for replay resumption
