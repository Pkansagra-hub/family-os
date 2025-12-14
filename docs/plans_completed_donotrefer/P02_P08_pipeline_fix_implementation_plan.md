# P02/P08 Pipeline Fix Implementation Plan

**Status**: Ready for Implementation
**Version**: 1.0.0
**Created**: 2025-12-13
**Owner**: K0 Architecture Team
**Related ADR**: ADR-K003 (Inline Embedding via UltraBERT)
**Supersedes**: Portions of `P02_P08_inline_embedding_implementation_plan.md`

---

## Executive Summary

### Problems Identified

The current P02/P08 inline embedding architecture has critical implementation issues:

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | **Ordering Violation** | 🔴 Critical | M23 writes `st_vec` before `st_hipp_events` exists - FK constraint will fail |
| 2 | **Missing Event Routing** | 🔴 Critical | `st_outbox` → `BusDispatcher` for internal events not implemented |
| 3 | **Inconsistent Abstractions** | 🟡 Medium | M24 uses raw SQLite, bypassing capability security model |
| 4 | **Incomplete Syscalls** | 🟡 Medium | M25 backfill calls non-existent syscalls |
| 5 | **Dual Status Tracking** | 🟢 Low | `embedding_status` tracked in two places |

### Proposed Solution

**Merge M23 into M16 + Convert P08 to Scheduled/Query-Based**

```
BEFORE (Current - Broken):
┌─────────────────────────────────────────────────────────────┐
│ P02: Stage 61 (M23) writes st_vec → Stage 70 (M16) writes   │
│      st_hipp_events → emits event → P08 triggers            │
│      ❌ FK fails because st_hipp_events doesn't exist yet   │
│      ❌ Event never reaches BusDispatcher                   │
└─────────────────────────────────────────────────────────────┘

AFTER (Fixed):
┌─────────────────────────────────────────────────────────────┐
│ P02: Stage 70 (M16) writes BOTH st_hipp_events + st_vec     │
│      atomically (same transaction, correct order)           │
│      ✅ No event emission needed                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ P08: Scheduled job queries st_vec WHERE status='READY'      │
│      Batch-processes into FAISS index                       │
│      ✅ Decoupled, efficient, no event routing needed       │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Decision

**Q: Do we need P08 after every P02?**

**A: NO.** P08's FAISS indexing is only needed when:

- P03 consolidation needs similarity search
- Users perform semantic memory recall

**Recommendation**: P08 should run as a **scheduled batch job**, not per-event trigger.

| Mode | Latency | Efficiency | Complexity |
|------|---------|------------|------------|
| Per-event (current) | Immediate | Low (overhead per event) | High (event routing) |
| **Scheduled batch** | 1-5 min delay | High (batch FAISS ops) | Low (simple query) |

---

## Implementation Phases

### Phase 0: Preparation (30 min)

#### Task 0.1: Backup Current Implementation

- [ ] Git commit current state
- [ ] Document current behavior for rollback

---

### Phase 1: Fix Transaction Atomicity (Critical - 2 hours)

**Goal**: Write both `st_hipp_events` and `st_vec` in a single atomic transaction.

#### Task 1.1: Update M16 (hipp_events_writer) to Include vec_write

**File**: `k0/modules/core/hipp_events_writer.py`

**Current M16 Responsibility**:

```python
# Writes st_hipp_events via syscalls.hipp_events_upsert()
# Writes st_pipeline_processed via syscalls.pipeline_processed_upsert()
```

**New M16 Responsibility**:

```python
# 1. Writes st_hipp_events via syscalls.hipp_events_upsert()
# 2. Writes st_vec via syscalls.vec_write() [NEW - from M23]
# 3. Writes st_pipeline_processed via syscalls.pipeline_processed_upsert()
```

**Changes Required**:

```python
async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    Atomic writer for episodic memory.

    Writes (in order, same transaction):
    1. st_hipp_events (episodic event record)
    2. st_vec (embedding vector) [NEW]
    3. st_pipeline_processed (idempotency record)
    """
    envelope = config.get("envelope", {})
    syscalls = context.syscalls

    # Get hipp_events_row from stage 60
    hipp_row = envelope.get("hipp_events_row", {})

    # Get embedding data from stage 22 (extract_from_cache)
    embedding_data = envelope.get("extract_from_cache", {})
    embedding = embedding_data.get("embedding")
    embedding_id = embedding_data.get("embedding_id")

    # 1. Write st_hipp_events FIRST (parent row for FK)
    await syscalls.hipp_events_upsert(**hipp_row)

    # 2. Write st_vec SECOND (child row, FK to st_hipp_events)
    if embedding and embedding_id:
        import struct
        vector_bytes = struct.pack('768f', *embedding)
        await syscalls.vec_write(
            embedding_id=embedding_id,
            event_id=hipp_row["event_id"],
            tenant_id=hipp_row["tenant_id"],
            space_id=hipp_row["space_id"],
            vector=vector_bytes,
            vector_dim=768,
            model_id=embedding_data.get("model_id", "ultrabert_v2.1.0"),
            status="READY",
        )

    # 3. Write st_pipeline_processed
    await syscalls.pipeline_processed_upsert(...)

    return {"written": True, "event_id": hipp_row["event_id"]}
```

**Acceptance Criteria**:

- [ ] M16 reads embedding from `envelope.extract_from_cache`
- [ ] M16 writes st_hipp_events BEFORE st_vec
- [ ] M16 handles missing embedding gracefully (sets embedding_status=PENDING)
- [ ] FK constraint satisfied (parent before child)
- [ ] Tests pass

#### Task 1.2: Remove Stage 61 (M23) from P02 DAG

**File**: `k0/contracts/pipelines/p02_write.v1.yaml`

**Current DAG (lines ~130-145)**:

```yaml
  # REPLACED: Stage 61 - Inline Embedding Write
  - id: stage_61_embedding_write
    module: builders.embedding_write:v1
    after:
      - stage_22_embedding_extract
```

**New DAG**:

```yaml
  # REMOVED: Stage 61 - Merged into Stage 70 (M16)
  # Embedding write is now handled atomically in stage_70_atomic_writer
```

**Update Stage 70 dependencies**:

```yaml
  - id: stage_70_atomic_writer
    module: core.hipp_events_writer:v1
    after:
      - stage_60_build_hipp_events_row
      - stage_22_embedding_extract    # NEW: Now depends on stage 22 directly
    description: Atomic writer - commits st_hipp_events + st_vec + st_pipeline_processed
    config:
      write_embedding: true           # NEW: Flag to include embedding write
```

**Acceptance Criteria**:

- [ ] Stage 61 removed from DAG
- [ ] Stage 70 depends on stage_22
- [ ] Pipeline YAML validates
- [ ] Integration tests pass

#### Task 1.3: Update M16 Contract

**File**: `k0/contracts/modules/core.hipp_events_writer.v1.yaml`

**Add**:

```yaml
required_capabilities:
  - st_hipp_events.write
  - st_vec.write              # NEW
  - st_pipeline_processed.write
  - st_outbox.write
```

**Acceptance Criteria**:

- [ ] Contract includes st_vec.write capability
- [ ] Contract validates

#### Task 1.4: Update P02 Pipeline Contract Capabilities

**File**: `k0/contracts/pipelines/p02_write.v1.yaml`

**Remove** (no longer needed at pipeline level, moved to M16):

```yaml
required_capabilities:
  # - st_vec.write  # Moved to M16 module
```

**Keep**:

```yaml
required_capabilities:
  - st_hipp_events.write
  - st_embedding_queue.write    # DEPRECATED - keep for backward compat
  - st_pipeline_processed.write
  - st_outbox.write
  - st_relationships.read
```

---

### Phase 2: Convert P08 to Scheduled/Query-Based (High - 1.5 hours)

**Goal**: P08 no longer depends on events, queries `st_vec` directly.

#### Task 2.1: Update P08 Contract to Remove Event Dependency

**File**: `k0/contracts/pipelines/p08_embedding_management.v2.yaml`

**Current**:

```yaml
entry_topic: cognitive.vector.stored.v1
```

**New**:

```yaml
# P08 is now trigger-based (scheduled or manual invocation)
# No entry_topic - does not subscribe to bus events
entry_topic: null  # Or remove entirely
trigger_mode: scheduled  # NEW field

# Trigger configuration
schedule:
  interval_seconds: 300  # Every 5 minutes
  batch_size: 100        # Process 100 vectors per batch
```

**Acceptance Criteria**:

- [ ] P08 contract updated
- [ ] No bus subscription required
- [ ] Scheduler config documented

#### Task 2.2: Implement vec_query Syscall

**File**: `k0/kernel/syscalls.py`

**Add new syscall** (after `vec_write`):

```python
async def vec_query(
    self,
    status: str | None = None,
    tenant_id: str | None = None,
    space_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Query st_vec table for embeddings by status (requires st_vec.read cap).

    Used by P08 M24 (faiss_indexer) to find READY embeddings for indexing.

    Capability Required: "st_vec.read"

    Args:
        status: Filter by status (READY, INDEXED, FAILED)
        tenant_id: Optional tenant filter
        space_id: Optional space filter
        limit: Max records to return (default: 100)
        offset: Pagination offset

    Returns:
        Dictionary with:
        - embeddings: list[dict] with embedding_id, event_id, vector, etc.
        - count: int (number of records returned)
        - total: int (total matching records)
    """
    self._require_cap("st_vec.read")

    # Build query with optional filters
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if tenant_id:
        conditions.append("tenant_id = ?")
        params.append(tenant_id)
    if space_id:
        conditions.append("space_id = ?")
        params.append(space_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with self._uow_factory() as uow:
        conn = uow._connection

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM st_vec WHERE {where_clause}"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Get paginated results
        query_sql = f"""
            SELECT embedding_id, event_id, tenant_id, space_id,
                   vector, vector_dim, model_id, status, created_at
            FROM st_vec
            WHERE {where_clause}
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
        """
        cursor = conn.execute(query_sql, params + [limit, offset])
        rows = cursor.fetchall()

        embeddings = [
            {
                "embedding_id": row[0],
                "event_id": row[1],
                "tenant_id": row[2],
                "space_id": row[3],
                "vector": row[4],  # bytes
                "vector_dim": row[5],
                "model_id": row[6],
                "status": row[7],
                "created_at": row[8],
            }
            for row in rows
        ]

        return {
            "embeddings": embeddings,
            "count": len(embeddings),
            "total": total,
        }
```

**Acceptance Criteria**:

- [ ] Syscall implemented
- [ ] Capability check enforced
- [ ] Pagination works
- [ ] Status filter works

#### Task 2.3: Implement vec_update_status Syscall

**File**: `k0/kernel/syscalls.py`

**Add new syscall**:

```python
async def vec_update_status(
    self,
    embedding_id: str,
    status: str,
    indexed_at: int | None = None,
) -> dict[str, Any]:
    """
    Update st_vec status (requires st_vec.write cap).

    Used by P08 M24 after adding to FAISS index.

    Capability Required: "st_vec.write"
    """
    self._require_cap("st_vec.write")

    if status not in ("READY", "INDEXED", "FAILED"):
        raise ValueError(f"Invalid status: {status}")

    async with self._uow_factory() as uow:
        conn = uow._connection

        if indexed_at:
            conn.execute(
                "UPDATE st_vec SET status = ?, indexed_at = ?, updated_at = ? WHERE embedding_id = ?",
                (status, indexed_at, int(time.time()), embedding_id)
            )
        else:
            conn.execute(
                "UPDATE st_vec SET status = ?, updated_at = ? WHERE embedding_id = ?",
                (status, int(time.time()), embedding_id)
            )

        return {"updated": True, "embedding_id": embedding_id, "status": status}
```

**Acceptance Criteria**:

- [ ] Syscall implemented
- [ ] Capability check enforced
- [ ] indexed_at optional

#### Task 2.4: Rewrite M24 (faiss_indexer) to Use Syscalls

**File**: `k0/modules/embedding/faiss_indexer.py`

**Current (problematic)**:

```python
# Uses raw sqlite3.connect() - bypasses capabilities
conn = sqlite3.connect("/data/k0_kernel.db")
cursor = conn.cursor()
cursor.execute("SELECT vector FROM st_vec WHERE embedding_id = ?", (embedding_id,))
```

**New (uses syscalls)**:

```python
async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    Index READY embeddings in FAISS.

    Trigger modes:
    1. Scheduled: Query st_vec WHERE status='READY', batch process
    2. Single: Process specific embedding_id from config
    """
    syscalls = context.syscalls

    # Get configuration
    batch_size = config.get("batch_size", 100)
    single_embedding_id = config.get("embedding_id")  # For single-mode

    if single_embedding_id:
        # Single embedding mode (for manual/event trigger)
        embeddings = [await _get_single_embedding(syscalls, single_embedding_id)]
    else:
        # Batch mode (for scheduled trigger)
        result = await syscalls.vec_query(status="READY", limit=batch_size)
        embeddings = result["embeddings"]

    if not embeddings:
        return {"indexed": 0, "message": "No READY embeddings found"}

    indexed_count = 0
    for emb in embeddings:
        embedding_id = emb["embedding_id"]
        vector_bytes = emb["vector"]

        # Unpack vector from bytes
        vector = list(struct.unpack("768f", vector_bytes))

        # Add to FAISS via syscall
        await syscalls.faiss_add(
            embedding_id=embedding_id,
            vector=vector,
        )

        # Update status to INDEXED
        await syscalls.vec_update_status(
            embedding_id=embedding_id,
            status="INDEXED",
            indexed_at=int(time.time()),
        )

        indexed_count += 1

    return {
        "indexed": indexed_count,
        "batch_size": len(embeddings),
    }
```

**Acceptance Criteria**:

- [ ] No raw SQLite connections
- [ ] Uses vec_query syscall
- [ ] Uses vec_update_status syscall
- [ ] Batch mode works
- [ ] Single mode works

#### Task 2.5: Create P08 Scheduler Entry Point

**File**: `k0/scripts/run_p08_indexer.py` (new)

```python
#!/usr/bin/env python3
"""
P08 FAISS Indexer - Scheduled Batch Runner

Usage:
    python k0/scripts/run_p08_indexer.py --batch-size 100
    python k0/scripts/run_p08_indexer.py --single emb_uuid_123

Cron example (every 5 minutes):
    */5 * * * * python k0/scripts/run_p08_indexer.py --batch-size 100
"""

import argparse
import asyncio
from k0.modules.embedding.faiss_indexer import run as faiss_indexer_run
from k0.kernel.syscalls import Syscalls

async def main(args):
    # Create syscalls with required capabilities
    syscalls = Syscalls(
        pipeline_id="P08_INDEXER",
        granted_caps={"st_vec.read", "st_vec.write", "faiss.write"},
        uow_factory=get_uow_factory(),
    )

    # Create mock context
    context = SimpleNamespace(syscalls=syscalls, logger=logger)

    # Run indexer
    config = {"batch_size": args.batch_size}
    if args.single:
        config["embedding_id"] = args.single

    result = await faiss_indexer_run(None, context, **config)
    print(f"Indexed {result['indexed']} embeddings")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--single", type=str, help="Single embedding_id to index")
    args = parser.parse_args()
    asyncio.run(main(args))
```

**Acceptance Criteria**:

- [ ] Script runs standalone
- [ ] Batch mode works
- [ ] Single mode works
- [ ] Can be scheduled via cron/scheduler

---

### Phase 3: Fix M25 Backfill Syscalls (Medium - 1 hour)

**Goal**: Implement missing syscalls used by M25 backfill.

#### Task 3.1: Implement hipp_events_query Syscall

**File**: `k0/kernel/syscalls.py`

```python
async def hipp_events_query(
    self,
    tenant_id: str | None = None,
    space_id: str | None = None,
    embedding_status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Query st_hipp_events by embedding_status (requires st_hipp_events.read cap).

    Used by M25 backfill to find PENDING embeddings.
    """
    self._require_cap("st_hipp_events.read")

    conditions = []
    params = []

    if tenant_id:
        conditions.append("tenant_id = ?")
        params.append(tenant_id)
    if space_id:
        conditions.append("space_id = ?")
        params.append(space_id)
    if embedding_status:
        conditions.append("embedding_status = ?")
        params.append(embedding_status)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with self._uow_factory() as uow:
        conn = uow._connection

        query = f"""
            SELECT event_id, tenant_id, space_id, text, embedding_status
            FROM st_hipp_events
            WHERE {where_clause}
            ORDER BY created_at ASC
            LIMIT ?
        """
        cursor = conn.execute(query, params + [limit])
        rows = cursor.fetchall()

        events = [
            {
                "event_id": row[0],
                "tenant_id": row[1],
                "space_id": row[2],
                "event_text": row[3],
                "embedding_status": row[4],
            }
            for row in rows
        ]

        return {"events": events, "count": len(events)}
```

#### Task 3.2: Implement ultrabert_embed Syscall

**File**: `k0/kernel/syscalls.py`

```python
async def ultrabert_embed(
    self,
    text: str,
    model_id: str = "ultrabert_v2.1.0",
) -> dict[str, Any]:
    """
    Generate embedding via UltraBERT (requires ultrabert.embed cap).

    Used by M25 backfill to compute embeddings for PENDING events.
    """
    self._require_cap("ultrabert.embed")

    import uuid
    from k0.runtime.ultrabert_adapter import get_embedding

    embedding = get_embedding(text)

    if not embedding:
        return {"embedding": None, "embedding_id": None, "error": "UltraBERT unavailable"}

    return {
        "embedding": embedding,
        "embedding_id": str(uuid.uuid4()),
        "vector_dim": len(embedding),
        "model_id": model_id,
    }
```

#### Task 3.3: Implement hipp_events_update_embedding_status Syscall

**File**: `k0/kernel/syscalls.py`

```python
async def hipp_events_update_embedding_status(
    self,
    event_id: str,
    embedding_status: str,
) -> dict[str, Any]:
    """
    Update st_hipp_events.embedding_status (requires st_hipp_events.write cap).
    """
    self._require_cap("st_hipp_events.write")

    if embedding_status not in ("PENDING", "READY", "INDEXED", "FAILED"):
        raise ValueError(f"Invalid embedding_status: {embedding_status}")

    async with self._uow_factory() as uow:
        conn = uow._connection
        conn.execute(
            "UPDATE st_hipp_events SET embedding_status = ?, updated_at = ? WHERE event_id = ?",
            (embedding_status, int(time.time()), event_id)
        )
        return {"updated": True, "event_id": event_id, "embedding_status": embedding_status}
```

**Acceptance Criteria**:

- [ ] All 3 syscalls implemented
- [ ] M25 backfill module works
- [ ] Tests pass

---

### Phase 4: Cleanup and Documentation (Low - 30 min)

#### Task 4.1: Deprecate M23 Module

**File**: `k0/modules/builders/embedding_write.py`

Add deprecation warning:

```python
"""
DEPRECATED: M23 embedding_write

This module is deprecated as of ADR-K003 v1.1.
Embedding writes are now handled atomically in M16 (hipp_events_writer).

Migration: Remove stage_61 from P02 DAG, M16 handles both tables.
"""

import warnings
warnings.warn(
    "M23 embedding_write is deprecated. Use M16 hipp_events_writer instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

#### Task 4.2: Update Architecture Documentation

**Files to Update**:

- `k0/pipelines/k0_architecture_master.md`: Update P02/P08 descriptions
- `docs/architecture/decisions-K0/pipelines/k003-inline-embedding-ultrabert.md`: Add revision note

---

## Implementation Checklist

### Phase 1: Transaction Atomicity ✅

- [ ] Task 1.1: Update M16 to include vec_write
- [ ] Task 1.2: Remove Stage 61 from P02 DAG
- [ ] Task 1.3: Update M16 contract capabilities
- [ ] Task 1.4: Update P02 pipeline contract

### Phase 2: P08 Scheduled Mode ✅

- [ ] Task 2.1: Update P08 contract (remove event dependency)
- [ ] Task 2.2: Implement vec_query syscall
- [ ] Task 2.3: Implement vec_update_status syscall
- [ ] Task 2.4: Rewrite M24 to use syscalls
- [ ] Task 2.5: Create P08 scheduler script

### Phase 3: Backfill Syscalls ✅

- [ ] Task 3.1: Implement hipp_events_query syscall
- [ ] Task 3.2: Implement ultrabert_embed syscall
- [ ] Task 3.3: Implement hipp_events_update_embedding_status syscall

### Phase 4: Cleanup ✅

- [ ] Task 4.1: Deprecate M23 module
- [ ] Task 4.2: Update architecture docs

---

## File Change Summary

| File | Action | Phase |
|------|--------|-------|
| `k0/modules/core/hipp_events_writer.py` | Modify - add vec_write | Phase 1 |
| `k0/contracts/pipelines/p02_write.v1.yaml` | Modify - remove stage 61 | Phase 1 |
| `k0/contracts/modules/core.hipp_events_writer.v1.yaml` | Modify - add capability | Phase 1 |
| `k0/contracts/pipelines/p08_embedding_management.v2.yaml` | Modify - remove event | Phase 2 |
| `k0/kernel/syscalls.py` | Modify - add 5 syscalls | Phase 2+3 |
| `k0/modules/embedding/faiss_indexer.py` | Rewrite - use syscalls | Phase 2 |
| `k0/scripts/run_p08_indexer.py` | Create - scheduler | Phase 2 |
| `k0/modules/builders/embedding_write.py` | Deprecate | Phase 4 |

---

## Testing Strategy

### Unit Tests

- [ ] M16 writes both tables in correct order
- [ ] vec_query returns correct results
- [ ] vec_update_status updates correctly
- [ ] M24 uses syscalls (no raw SQL)

### Integration Tests

- [ ] P02 end-to-end: envelope → st_hipp_events + st_vec (same txn)
- [ ] P08 batch: READY → FAISS → INDEXED
- [ ] Backfill: PENDING → compute → READY

### Manual Validation

- [ ] FK constraint passes (st_vec.event_id → st_hipp_events.event_id)
- [ ] Scheduler runs successfully
- [ ] FAISS search returns indexed vectors

---

## Risk Assessment

| Risk | Probability | Mitigation |
|------|-------------|------------|
| M16 transaction failure | Low | Rollback both writes |
| FAISS index rebuild needed | Medium | Keep dimension=768, no rebuild |
| Scheduler missed runs | Low | Catch-up batch in next run |
| Existing st_vec orphans | Medium | One-time cleanup script |

---

## Estimated Effort

| Phase | Duration | Complexity |
|-------|----------|------------|
| Phase 0: Preparation | 30 min | Low |
| Phase 1: Transaction Fix | 2 hours | High |
| Phase 2: P08 Scheduled | 1.5 hours | Medium |
| Phase 3: Backfill Syscalls | 1 hour | Medium |
| Phase 4: Cleanup | 30 min | Low |
| **Total** | **~5.5 hours** | |

---

## Approval

- [ ] Architecture team review
- [ ] ADR-K003 revision approved
- [ ] Implementation started

---

## References

- Original Plan: `docs/plans/P02_P08_inline_embedding_implementation_plan.md`
- ADR-K003: `docs/architecture/decisions-K0/pipelines/k003-inline-embedding-ultrabert.md`
- P02 Contract: `k0/contracts/pipelines/p02_write.v1.yaml`
- P08 Contract: `k0/contracts/pipelines/p08_embedding_management.v2.yaml`
