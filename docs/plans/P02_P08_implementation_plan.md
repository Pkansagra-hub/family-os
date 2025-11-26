# P02 Enhancement + P08 Embedding Pipeline - Implementation Plan

**Status**: PLANNING
**Created**: 2025-11-25
**Updated**: 2025-11-25
**Owner**: Architecture Team
**Architecture**: YAML Pipeline (Kernel Boundary Compliant)
**Total Estimated Effort**: ~6 days

---

## Executive Summary

This plan covers two interconnected work streams:

1. **P02 Enhancement** (Priority 1): M14 must emit `p02.embedding.enqueued.v1` topic to trigger P08
2. **P08 Embedding Pipeline** (Priority 2): Implement as YAML pipeline with topic subscription

**Critical Architecture Decision**: P08 is a **YAML pipeline** (NOT outbox driver) to maintain kernel boundary integrity. This ensures:

- Clean separation via `PipelineProtocol.handle(msg)`
- Capability enforcement via syscalls
- Contract validation via YAML spec
- Scalable to 200+ pipelines

---

## Current State Analysis

### P02 Current State

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Pipeline YAML | Exists | `k0/contracts/pipelines/p02_write.v1.yaml` | 18 stages, 171ms P95 |
| M14 embedding_queue_write | Exists | `k0/modules/builders/embedding_queue_write.py` | Uses in-memory dict |
| st_hipp_events | Exists | Migration 0024 | Has embedding_id, embedding_status columns |
| st_embedding_queue | Exists | Migration 0024 | Job queue for P08 |
| syscalls.embedding_enqueue | Exists | `k0/kernel/syscalls.py` | Writes to st_embedding_queue |
| Topic emission | MISSING | P02 M14 | Does NOT emit `p02.embedding.enqueued.v1` |

### P08/Embedding Current State

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| P08 YAML contract | MISSING | - | Needs creation |
| Embedding modules | MISSING | - | Refactor from drivers |
| New syscalls | MISSING | - | 6 new syscalls needed |
| EmbeddingQueueDriver | Exists | `k0/drivers/embedding_queue.py` | Refactor to modules |
| FaissDriver | Exists | `k0/drivers/faiss.py` | Refactor to modules |
| Runtime infrastructure | Exists | `k0/runtime/` | PipelineRunner, ModuleRegistry |
| BusDispatcher | Exists | `k0/bus/` | Topic routing |

### Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-1 | P08 YAML contract missing | Pipeline cannot be registered |
| GAP-2 | Embedding modules missing | Pipeline has no stages to execute |
| GAP-3 | New syscalls missing | Modules cannot access storage |
| GAP-4 | M14 does not emit topic | P08 never triggered |
| GAP-5 | M14 uses in-memory dict | Not using syscalls |

---

## Milestones

| Milestone | Days | Goal |
|-----------|------|------|
| M1: ADRs & Contracts | 0.5 | Create ADRs, P08 YAML contract |
| M2: New Syscalls | 1 | Add 6 new syscalls to kernel |
| M3: Embedding Modules | 1.5 | Create 5 modules, refactor from drivers |
| M4: P02 Integration | 0.5 | M14 emits topic, uses syscalls |
| M5: Model Preloading | 0.5 | Preload sentence-transformers |
| M6: Testing & Docs | 2 | Integration tests, documentation |

**Total**: ~6 days

---

## Milestone 1: ADRs & Contracts (Day 1 - Morning)

### Issue 1.1: Create ADR for P08 Architecture

**Type**: ADR
**Priority**: P0 (Critical)
**Estimated**: 2 hours

**Location**: `docs/architecture/decisions-K0/pipelines/ADR-P08-001-yaml-pipeline-architecture.md`

**Content**:

```markdown
# ADR-P08-001: P08 Embedding Pipeline Architecture

## Status
ACCEPTED

## Context
P08 (Embedding Lifecycle) processes embedding jobs created by P02.
Two options were considered:
1. Outbox driver pattern (kernel invokes drivers directly)
2. YAML pipeline pattern (topic subscription via BusDispatcher)

## Decision
P08 will be implemented as a **YAML pipeline** with topic subscription.

## Rationale
The outbox driver pattern **breaches kernel boundary**:
- `_outbox_worker_loop` in kernel directly invokes drivers
- Bypasses capability enforcement
- No contract validation
- Kernel bloat at scale (200+ pipelines)

The YAML pipeline pattern **maintains kernel boundary**:
- Clean separation via PipelineProtocol.handle(msg)
- Capability enforcement via syscalls
- Contract validation via YAML spec
- Scalable architecture

## Consequences
- P08 needs YAML contract in `k0/contracts/pipelines/p08_embedding.v1.yaml`
- Drivers refactored to modules in `k0/modules/embedding/`
- 6 new syscalls for storage access
- M14 emits topic instead of outbox entry

## Related ADRs
- k009.2: Embedding Queue Writer (M14 contract)
```

**Checklist**:
- [ ] Create ADR file
- [ ] Update ADR index

---

### Issue 1.2: Create P08 YAML Contract

**Type**: Contract
**Priority**: P0 (Critical)
**Estimated**: 1 hour

**Location**: `k0/contracts/pipelines/p08_embedding.v1.yaml`

**Content**:

```yaml
pipeline_id: p08_embedding
version: "1"
description: Background embedding lifecycle - compute vectors and index in FAISS

entry_topic: p02.embedding.enqueued.v1
exit_topic: p08.embedding.complete.v1
fail_topic: p08.embedding.failed.v1

required_caps:
  - st_embedding_queue.read
  - st_embedding_queue.write
  - st_hipp_events.read
  - st_hipp_events.write
  - st_embeddings.write
  - faiss.write

dag:
  - stage: claim
    module: embedding.claim:v1
    inputs: [payload]
    outputs: [job]
    on_error: emit_failed
    description: Atomically claim job to prevent duplicates

  - stage: compute
    module: embedding.compute:v1
    inputs: [job]
    outputs: [vector]
    depends_on: [claim]
    on_error: retry_with_backoff
    description: Compute 384-dim vector via sentence-transformers

  - stage: store
    module: embedding.store:v1
    inputs: [job, vector]
    outputs: [stored]
    depends_on: [compute]
    on_error: retry_with_backoff
    description: Store vector to st_embedding_queue

  - stage: index_faiss
    module: embedding.index_faiss:v1
    inputs: [job, vector, stored]
    outputs: [indexed]
    depends_on: [store]
    on_error: retry_with_backoff
    description: Add vector to FAISS index

  - stage: update_status
    module: embedding.update_status:v1
    inputs: [job, indexed]
    outputs: [complete]
    depends_on: [index_faiss]
    on_error: emit_failed
    description: Final status update and hippo sync

retry_policy:
  max_attempts: 5
  backoff: exponential
  base_delay_ms: 60000
  max_delay_ms: 960000

performance_targets:
  p95_latency_ms: 500
  throughput_per_sec: 5
```

**Checklist**:
- [ ] Create YAML contract file
- [ ] Validate schema

---

### Issue 1.3: Create Module Contracts

**Type**: Contract
**Priority**: P0 (Critical)
**Estimated**: 2 hours

**Files**:
- `k0/contracts/modules/embedding.claim.v1.yaml`
- `k0/contracts/modules/embedding.compute.v1.yaml`
- `k0/contracts/modules/embedding.store.v1.yaml`
- `k0/contracts/modules/embedding.index_faiss.v1.yaml`
- `k0/contracts/modules/embedding.update_status.v1.yaml`

**Example Contract (embedding.claim.v1.yaml)**:

```yaml
module_id: embedding.claim
version: "1"
description: Atomically claim embedding job to prevent duplicate processing

input_schema:
  type: object
  properties:
    embedding_id:
      type: string
    tenant_id:
      type: string
    space_id:
      type: string
  required: [embedding_id, tenant_id, space_id]

output_schema:
  type: object
  properties:
    job_id:
      type: integer
    event_id:
      type: string
    embedding_id:
      type: string
    status:
      type: string
      enum: [IN_PROGRESS]
    vector_kind:
      type: string
    model_id:
      type: string

side_effects:
  - read:st_embedding_queue
  - write:st_embedding_queue

error_types:
  - ALREADY_CLAIMED
  - NOT_FOUND

idempotency: true
```

**Checklist**:
- [ ] Create all 5 module contracts
- [ ] Validate schemas

---

## Milestone 2: New Syscalls (Day 1 - Afternoon)

### Issue 2.1: Add embedding_queue_claim Syscall

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1.5 hours

**Location**: `k0/kernel/syscalls.py`

```python
async def embedding_queue_claim(
    self,
    embedding_id: str,
    expected_status: str = "PENDING",
) -> dict[str, Any]:
    """
    Atomically claim embedding job.

    Capability Required: st_embedding_queue.read, st_embedding_queue.write

    Returns:
        {"status": "CLAIMED", "job_id": int, "event_id": str, ...} on success
        {"status": "ALREADY_CLAIMED"} if already processing
        {"status": "NOT_FOUND"} if job doesn't exist
    """
    self._require_capability("st_embedding_queue.read")
    self._require_capability("st_embedding_queue.write")

    # Atomic UPDATE with WHERE status = expected_status
    result = await self._conn.execute(
        """
        UPDATE st_embedding_queue
        SET status = 'IN_PROGRESS', updated_at = ?
        WHERE embedding_id = ? AND status = ?
        RETURNING job_id, event_id, embedding_id, tenant_id, space_id,
                  vector_kind, model_id, priority
        """,
        (self._now(), embedding_id, expected_status)
    )

    row = result.fetchone()
    if row is None:
        # Check if exists but different status
        existing = await self._conn.execute(
            "SELECT status FROM st_embedding_queue WHERE embedding_id = ?",
            (embedding_id,)
        )
        if existing.fetchone():
            return {"status": "ALREADY_CLAIMED"}
        return {"status": "NOT_FOUND"}

    return {
        "status": "CLAIMED",
        "job_id": row[0],
        "event_id": row[1],
        "embedding_id": row[2],
        "tenant_id": row[3],
        "space_id": row[4],
        "vector_kind": row[5],
        "model_id": row[6],
        "priority": row[7]
    }
```

**Checklist**:
- [ ] Implement syscall
- [ ] Add capability check
- [ ] Add unit tests

---

### Issue 2.2: Add hipp_event_read Syscall

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1 hour

**Location**: `k0/kernel/syscalls.py`

```python
async def hipp_event_read(
    self,
    event_id: str,
) -> dict[str, Any]:
    """
    Read event from st_hipp_events.

    Capability Required: st_hipp_events.read

    Returns:
        Event dict with text, metadata, etc.
    """
    self._require_capability("st_hipp_events.read")

    result = await self._conn.execute(
        """
        SELECT event_id, tenant_id, space_id, text,
               embedding_id, embedding_status, entities_json, kg_triples_json,
               created_at, updated_at
        FROM st_hipp_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    row = result.fetchone()
    if row is None:
        return {"status": "NOT_FOUND"}

    return {
        "status": "FOUND",
        "event_id": row[0],
        "tenant_id": row[1],
        "space_id": row[2],
        "text": row[3],
        "embedding_id": row[4],
        "embedding_status": row[5],
        "entities_json": row[6],
        "kg_triples_json": row[7],
        "created_at": row[8],
        "updated_at": row[9]
    }
```

**Checklist**:
- [ ] Implement syscall
- [ ] Add capability check
- [ ] Add unit tests

---

### Issue 2.3: Add embedding_store Syscall

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1 hour

**Location**: `k0/kernel/syscalls.py`

```python
async def embedding_store(
    self,
    embedding_id: str,
    vector_json: str,
    status: str = "READY",
) -> dict[str, Any]:
    """
    Store computed vector to st_embedding_queue.

    Capability Required: st_embedding_queue.write
    """
    self._require_capability("st_embedding_queue.write")

    result = await self._conn.execute(
        """
        UPDATE st_embedding_queue
        SET vector_json = ?, status = ?, updated_at = ?
        WHERE embedding_id = ?
        """,
        (vector_json, status, self._now(), embedding_id)
    )

    return {
        "status": "STORED",
        "embedding_id": embedding_id,
        "rows_affected": result.rowcount
    }
```

**Checklist**:
- [ ] Implement syscall
- [ ] Add capability check
- [ ] Add unit tests

---

### Issue 2.4: Add faiss_add Syscall

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1.5 hours

**Location**: `k0/kernel/syscalls.py`

```python
async def faiss_add(
    self,
    embedding_id: str,
    event_id: str,
    tenant_id: str,
    space_id: str,
    vector: list[float],
) -> dict[str, Any]:
    """
    Add vector to FAISS index and create st_embeddings metadata.

    Capability Required: faiss.write, st_embeddings.write

    Returns:
        {"vector_id": int, "indexed": True}
    """
    self._require_capability("faiss.write")
    self._require_capability("st_embeddings.write")

    import numpy as np

    # Get FAISS index from app state
    faiss_index = self._app_state.faiss_index

    # Convert to numpy array
    vector_np = np.array(vector, dtype=np.float32).reshape(1, -1)

    # Validate dimension
    if vector_np.shape[1] != faiss_index.d:
        raise ValueError(f"Vector dimension {vector_np.shape[1]} != index dimension {faiss_index.d}")

    # Add to FAISS (vector_id is the index position)
    vector_id = faiss_index.ntotal
    faiss_index.add(vector_np)

    # Compute norm for quality checks
    vector_norm = float(np.linalg.norm(vector_np))

    # Insert metadata to st_embeddings
    await self._conn.execute(
        """
        INSERT INTO st_embeddings (vector_id, embedding_id, event_id, tenant_id, space_id, vector_norm, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(embedding_id) DO UPDATE SET
            vector_id = excluded.vector_id,
            indexed_at = excluded.indexed_at
        """,
        (vector_id, embedding_id, event_id, tenant_id, space_id, vector_norm, self._now())
    )

    return {
        "vector_id": vector_id,
        "indexed": True,
        "vector_norm": vector_norm
    }
```

**Checklist**:
- [ ] Implement syscall
- [ ] Add capability checks
- [ ] Handle FAISS index access
- [ ] Add unit tests

---

### Issue 2.5: Add embedding_queue_update_status Syscall

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 0.5 hours

**Location**: `k0/kernel/syscalls.py`

```python
async def embedding_queue_update_status(
    self,
    embedding_id: str,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Update st_embedding_queue status.

    Capability Required: st_embedding_queue.write
    """
    self._require_capability("st_embedding_queue.write")

    if error:
        await self._conn.execute(
            """
            UPDATE st_embedding_queue
            SET status = ?, last_error = ?, updated_at = ?
            WHERE embedding_id = ?
            """,
            (status, error[:500], self._now(), embedding_id)
        )
    else:
        await self._conn.execute(
            """
            UPDATE st_embedding_queue
            SET status = ?, updated_at = ?
            WHERE embedding_id = ?
            """,
            (status, self._now(), embedding_id)
        )

    return {"status": "UPDATED", "embedding_id": embedding_id}
```

**Checklist**:
- [ ] Implement syscall
- [ ] Add capability check
- [ ] Add unit tests

---

### Issue 2.6: Add hipp_event_update_embedding_status Syscall

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 0.5 hours

**Location**: `k0/kernel/syscalls.py`

```python
async def hipp_event_update_embedding_status(
    self,
    embedding_id: str,
    embedding_status: str,
) -> dict[str, Any]:
    """
    Update st_hipp_events.embedding_status.

    Capability Required: st_hipp_events.write
    """
    self._require_capability("st_hipp_events.write")

    await self._conn.execute(
        """
        UPDATE st_hipp_events
        SET embedding_status = ?, updated_at = ?
        WHERE embedding_id = ?
        """,
        (embedding_status, self._now(), embedding_id)
    )

    return {"status": "UPDATED", "embedding_id": embedding_id}
```

**Checklist**:
- [ ] Implement syscall
- [ ] Add capability check
- [ ] Add unit tests

---

## Milestone 3: Embedding Modules (Days 2-3)

### Issue 3.1: Create embedding.claim Module

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 2 hours

**Location**: `k0/modules/embedding/claim.py`

```python
"""
Module: embedding.claim:v1
Purpose: Atomically claim embedding job to prevent duplicate processing
"""
from dataclasses import dataclass
from typing import Any

from k0.runtime.module import ModuleContext, SkipEvent


@dataclass
class ClaimInput:
    embedding_id: str
    tenant_id: str
    space_id: str


@dataclass
class ClaimOutput:
    job_id: int
    event_id: str
    embedding_id: str
    tenant_id: str
    space_id: str
    status: str
    vector_kind: str
    model_id: str


async def run(ctx: ModuleContext, input_data: dict[str, Any]) -> dict[str, Any]:
    """Atomically claim embedding job."""
    embedding_id = input_data["embedding_id"]

    result = await ctx.syscalls.embedding_queue_claim(
        embedding_id=embedding_id,
        expected_status="PENDING"
    )

    if result["status"] == "ALREADY_CLAIMED":
        raise SkipEvent(f"Job {embedding_id} already claimed")

    if result["status"] == "NOT_FOUND":
        raise SkipEvent(f"Job {embedding_id} not found")

    return {
        "job_id": result["job_id"],
        "event_id": result["event_id"],
        "embedding_id": result["embedding_id"],
        "tenant_id": result["tenant_id"],
        "space_id": result["space_id"],
        "status": "IN_PROGRESS",
        "vector_kind": result["vector_kind"],
        "model_id": result["model_id"]
    }
```

**Checklist**:
- [ ] Create module file
- [ ] Implement run function
- [ ] Add unit tests

---

### Issue 3.2: Create embedding.compute Module

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 3 hours

**Location**: `k0/modules/embedding/compute.py`

```python
"""
Module: embedding.compute:v1
Purpose: Compute 384-dim embedding vector via sentence-transformers
"""
import json
import time
from typing import Any

from k0.runtime.module import ModuleContext, PermanentFailure


async def run(ctx: ModuleContext, input_data: dict[str, Any]) -> dict[str, Any]:
    """Compute embedding vector from event text."""
    job = input_data["job"]
    event_id = job["event_id"]

    # Read text from hippocampus via syscall
    event = await ctx.syscalls.hipp_event_read(event_id=event_id)

    if event["status"] == "NOT_FOUND":
        raise PermanentFailure(f"Event {event_id} not found")

    text = event.get("text")
    if not text:
        raise PermanentFailure(f"Event {event_id} has no text content")

    # Get preloaded model from context
    model = ctx.app_state.preloaded_models.get("sentence_transformer")
    if model is None:
        # Fallback: load model (cold start)
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")

    # Compute embedding
    start = time.monotonic()
    vector = model.encode(text)
    compute_time_ms = int((time.monotonic() - start) * 1000)

    return {
        "embedding_id": job["embedding_id"],
        "vector": vector.tolist(),
        "model_id": job["model_id"],
        "compute_time_ms": compute_time_ms,
        "text_length": len(text)
    }
```

**Checklist**:
- [ ] Create module file
- [ ] Implement run function
- [ ] Handle model loading
- [ ] Add unit tests

---

### Issue 3.3: Create embedding.store Module

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1 hour

**Location**: `k0/modules/embedding/store.py`

```python
"""
Module: embedding.store:v1
Purpose: Store computed vector to st_embedding_queue
"""
import json
from typing import Any

from k0.runtime.module import ModuleContext


async def run(ctx: ModuleContext, input_data: dict[str, Any]) -> dict[str, Any]:
    """Store computed vector to st_embedding_queue."""
    job = input_data["job"]
    vector_data = input_data["vector"]

    # Serialize vector to JSON
    vector_json = json.dumps(vector_data["vector"])

    # Store via syscall
    result = await ctx.syscalls.embedding_store(
        embedding_id=job["embedding_id"],
        vector_json=vector_json,
        status="READY"
    )

    return {
        "embedding_id": job["embedding_id"],
        "status": "READY",
        "vector_stored": True
    }
```

**Checklist**:
- [ ] Create module file
- [ ] Implement run function
- [ ] Add unit tests

---

### Issue 3.4: Create embedding.index_faiss Module

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 2 hours

**Location**: `k0/modules/embedding/index_faiss.py`

```python
"""
Module: embedding.index_faiss:v1
Purpose: Add vector to FAISS index and create st_embeddings metadata
"""
from typing import Any

from k0.runtime.module import ModuleContext


async def run(ctx: ModuleContext, input_data: dict[str, Any]) -> dict[str, Any]:
    """Add vector to FAISS index."""
    job = input_data["job"]
    vector_data = input_data["vector"]

    # Add to FAISS via syscall
    result = await ctx.syscalls.faiss_add(
        embedding_id=job["embedding_id"],
        event_id=job["event_id"],
        tenant_id=job["tenant_id"],
        space_id=job["space_id"],
        vector=vector_data["vector"]
    )

    return {
        "embedding_id": job["embedding_id"],
        "vector_id": result["vector_id"],
        "indexed": True,
        "vector_norm": result["vector_norm"]
    }
```

**Checklist**:
- [ ] Create module file
- [ ] Implement run function
- [ ] Add unit tests

---

### Issue 3.5: Create embedding.update_status Module

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1.5 hours

**Location**: `k0/modules/embedding/update_status.py`

```python
"""
Module: embedding.update_status:v1
Purpose: Final status update and hippo sync
"""
from typing import Any

from k0.runtime.module import ModuleContext


async def run(ctx: ModuleContext, input_data: dict[str, Any]) -> dict[str, Any]:
    """Final status update for embedding job."""
    job = input_data["job"]
    indexed = input_data["indexed"]

    # Update queue status to INDEXED
    await ctx.syscalls.embedding_queue_update_status(
        embedding_id=job["embedding_id"],
        status="INDEXED"
    )

    # Sync hippo status to READY
    await ctx.syscalls.hipp_event_update_embedding_status(
        embedding_id=job["embedding_id"],
        embedding_status="READY"
    )

    return {
        "embedding_id": job["embedding_id"],
        "final_status": "INDEXED",
        "hippo_synced": True,
        "vector_id": indexed["vector_id"]
    }
```

**Checklist**:
- [ ] Create module file
- [ ] Implement run function
- [ ] Add unit tests

---

### Issue 3.6: Create Module __init__.py

**Type**: Implementation
**Priority**: P1 (High)
**Estimated**: 0.5 hours

**Location**: `k0/modules/embedding/__init__.py`

```python
"""
Embedding modules for P08 pipeline.

Modules:
- claim: Atomic job claim
- compute: Vector computation via sentence-transformers
- store: Store vector to st_embedding_queue
- index_faiss: Add to FAISS index
- update_status: Final status update
"""
from k0.modules.embedding import claim, compute, store, index_faiss, update_status

__all__ = ["claim", "compute", "store", "index_faiss", "update_status"]
```

**Checklist**:
- [ ] Create __init__.py
- [ ] Register modules with ModuleRegistry

---

## Milestone 4: P02 Integration (Day 3 - Afternoon)

### Issue 4.1: Migrate M14 from In-Memory to Syscalls

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 2 hours

**Location**: `k0/modules/builders/embedding_queue_write.py`

**Problem**: M14 currently uses in-memory dict instead of syscalls.

**Required Changes**:

```python
# BEFORE (wrong - in-memory)
_embedding_queue_db: Dict[str, Dict[str, Any]] = {}

async def write_to_embedding_queue(record: Dict[str, Any]) -> Dict[str, Any]:
    if embedding_id in _embedding_queue_db:
        return {"inserted": False, ...}
    _embedding_queue_db[embedding_id] = record.copy()

# AFTER (correct - syscalls)
async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    # ... extract fields from envelope ...

    # 1. Write to st_embedding_queue via syscalls
    result = await context.syscalls.embedding_enqueue(
        embedding_id=embedding_id,
        event_id=event_id,
        wal_pos=wal_pos,
        tenant_id=tenant_id,
        space_id=space_id,
        vector_kind="memory.body.text",
        model_id=config.get("model_id", "all-MiniLM-L6-v2"),
        priority=config.get("priority", "NORMAL"),
    )

    # 2. NEW: Emit topic to trigger P08
    if result["inserted"]:
        await context.syscalls.bus_emit(
            topic="p02.embedding.enqueued.v1",
            payload={
                "embedding_id": embedding_id,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "vector_kind": "memory.body.text",
                "model_id": config.get("model_id", "all-MiniLM-L6-v2"),
                "priority": config.get("priority", "NORMAL")
            }
        )

    return {...}
```

**Checklist**:
- [ ] Remove `_embedding_queue_db` in-memory dict
- [ ] Use `context.syscalls.embedding_enqueue()`
- [ ] Add `context.syscalls.bus_emit()` call
- [ ] Update unit tests

---

### Issue 4.2: Add bus_emit Syscall (If Missing)

**Type**: Implementation
**Priority**: P0 (Critical)
**Estimated**: 1 hour

**Location**: `k0/kernel/syscalls.py`

```python
async def bus_emit(
    self,
    topic: str,
    payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Emit event to BusDispatcher.

    Capability Required: bus.emit
    """
    self._require_capability("bus.emit")

    event = {
        "topic": topic,
        "payload": payload,
        "metadata": metadata or {},
        "timestamp": self._now(),
        "trace_id": self._trace_id
    }

    # Route to BusDispatcher
    await self._app_state.bus_dispatcher.emit(event)

    return {"status": "EMITTED", "topic": topic}
```

**Checklist**:
- [ ] Check if bus_emit exists
- [ ] Implement if missing
- [ ] Add capability check

---

### Issue 4.3: Update M14 Contract

**Type**: Contract
**Priority**: P1 (High)
**Estimated**: 0.5 hours

**Location**: `k0/contracts/modules/builders.embedding_queue_write.v1.yaml`

**Changes**:

```yaml
side_effects:
  - write:st_embedding_queue
  - emit:p02.embedding.enqueued.v1  # ADD THIS

output_event_types:
  - p02.embedding.enqueued.v1
```

**Checklist**:
- [ ] Update contract with emit side effect
- [ ] Validate contract

---

## Milestone 5: Model Preloading (Day 4 - Morning)

### Issue 5.1: Add sentence-transformers to _preload_models()

**Type**: Implementation
**Priority**: P1 (High)
**Estimated**: 1.5 hours

**Location**: `k0/kernel/app.py`

```python
async def _preload_models() -> dict[str, Any]:
    models = {}

    # ... existing spaCy and VADER loading ...

    # Preload sentence-transformers for P08
    try:
        import os
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("K0_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        logger.info(f"Preloading sentence-transformers model ({model_name})...")
        models["sentence_transformer"] = SentenceTransformer(model_name)
        logger.info("sentence-transformers model preloaded successfully")
    except ImportError:
        logger.warning("sentence-transformers not installed")
        models["sentence_transformer"] = None
    except Exception as e:
        logger.warning(f"Failed to preload sentence-transformers: {e}")
        models["sentence_transformer"] = None

    return models
```

**Checklist**:
- [ ] Add sentence-transformers preloading
- [ ] Store in app.state.preloaded_models
- [ ] Measure startup time impact

---

### Issue 5.2: Initialize FAISS Index at Startup

**Type**: Implementation
**Priority**: P1 (High)
**Estimated**: 1 hour

**Location**: `k0/kernel/app.py`

```python
async def _init_faiss_index() -> Any:
    """Initialize FAISS index at startup."""
    import os
    import faiss

    index_path = os.getenv("K0_FAISS_INDEX_PATH", "./k0_faiss.index")
    dimension = int(os.getenv("K0_FAISS_DIMENSION", "384"))

    if os.path.exists(index_path):
        logger.info(f"Loading FAISS index from {index_path}...")
        index = faiss.read_index(index_path)
    else:
        logger.info(f"Creating new FAISS index (dim={dimension})...")
        index = faiss.IndexFlatL2(dimension)

    return index
```

**Checklist**:
- [ ] Initialize FAISS index at startup
- [ ] Store in app.state.faiss_index
- [ ] Add shutdown hook to persist index

---

## Milestone 6: Testing & Documentation (Days 4-5)

### Issue 6.1: Create P08 Contract Tests

**Type**: Test
**Priority**: P0 (Critical)
**Estimated**: 3 hours

**Location**: `tests/contracts/p08/test_p08_embedding_contract.py`

```python
"""Contract tests for P08 Embedding Pipeline."""
import pytest
from k0.contracts.validator import validate_pipeline_contract


def test_p08_contract_valid():
    """P08 YAML contract should be valid."""
    errors = validate_pipeline_contract("p08_embedding.v1.yaml")
    assert not errors


def test_p08_modules_exist():
    """All modules referenced in P08 should exist."""
    from k0.runtime.registry import ModuleRegistry

    registry = ModuleRegistry()
    modules = [
        "embedding.claim:v1",
        "embedding.compute:v1",
        "embedding.store:v1",
        "embedding.index_faiss:v1",
        "embedding.update_status:v1"
    ]

    for module_id in modules:
        assert registry.has(module_id), f"Module {module_id} not found"


def test_p08_required_caps():
    """P08 should declare all required capabilities."""
    from k0.contracts.loader import load_pipeline_contract

    contract = load_pipeline_contract("p08_embedding.v1.yaml")
    required = {
        "st_embedding_queue.read",
        "st_embedding_queue.write",
        "st_hipp_events.read",
        "st_hipp_events.write",
        "st_embeddings.write",
        "faiss.write"
    }

    assert set(contract["required_caps"]) == required
```

**Checklist**:
- [ ] Create contract test file
- [ ] Test YAML validity
- [ ] Test module existence
- [ ] Test capability declarations

---

### Issue 6.2: Create P08 Integration Tests

**Type**: Test
**Priority**: P0 (Critical)
**Estimated**: 4 hours

**Location**: `tests/integration/p08/test_p08_embedding_e2e.py`

```python
"""End-to-end integration tests for P08 pipeline."""
import pytest
from k0.kernel.test_helpers import TestKernel


@pytest.mark.integration
async def test_p02_triggers_p08():
    """P02 completion should trigger P08 via topic."""
    async with TestKernel() as kernel:
        # 1. Submit memory write
        result = await kernel.command_port.submit({
            "type": "memory.write",
            "tenant_id": "test-tenant",
            "space_id": "personal:user",
            "text": "Test memory for embedding"
        })

        # 2. Verify P02 completed
        assert result["pipeline"] == "p02_write"
        assert result["status"] == "complete"

        # 3. Wait for P08 to process (topic-triggered)
        await kernel.wait_for_topic("p08.embedding.complete.v1", timeout=5.0)

        # 4. Verify embedding created
        embedding = await kernel.query(
            "SELECT * FROM st_embedding_queue WHERE event_id = ?",
            (result["event_id"],)
        )
        assert embedding["status"] == "INDEXED"

        # 5. Verify hippo status synced
        event = await kernel.query(
            "SELECT embedding_status FROM st_hipp_events WHERE event_id = ?",
            (result["event_id"],)
        )
        assert event["embedding_status"] == "READY"

        # 6. Verify FAISS index has vector
        vector_count = kernel.app_state.faiss_index.ntotal
        assert vector_count >= 1


@pytest.mark.integration
async def test_p08_idempotent():
    """Duplicate topic emissions should be handled gracefully."""
    async with TestKernel() as kernel:
        # Emit same topic twice
        await kernel.bus_emit("p02.embedding.enqueued.v1", {
            "embedding_id": "test-emb-001",
            "event_id": "test-evt-001",
            "tenant_id": "test-tenant",
            "space_id": "personal:user"
        })

        await kernel.bus_emit("p02.embedding.enqueued.v1", {
            "embedding_id": "test-emb-001",
            "event_id": "test-evt-001",
            "tenant_id": "test-tenant",
            "space_id": "personal:user"
        })

        # Should only process once
        await asyncio.sleep(1.0)

        embeddings = await kernel.query(
            "SELECT COUNT(*) as cnt FROM st_embeddings WHERE embedding_id = ?",
            ("test-emb-001",)
        )
        assert embeddings["cnt"] == 1


@pytest.mark.integration
async def test_p08_failure_marks_failed():
    """Permanent failures should update status to FAILED."""
    async with TestKernel() as kernel:
        # Create job with no text (will fail)
        await kernel.execute(
            """
            INSERT INTO st_embedding_queue
            (embedding_id, event_id, tenant_id, space_id, status, ...)
            VALUES (?, ?, ?, ?, 'PENDING', ...)
            """,
            ("fail-emb", "fail-evt", "test", "personal:user")
        )

        # No text in st_hipp_events for this event

        # Emit topic
        await kernel.bus_emit("p02.embedding.enqueued.v1", {
            "embedding_id": "fail-emb",
            "event_id": "fail-evt",
            ...
        })

        # Wait for failure
        await kernel.wait_for_topic("p08.embedding.failed.v1", timeout=5.0)

        # Check status
        job = await kernel.query(
            "SELECT status FROM st_embedding_queue WHERE embedding_id = ?",
            ("fail-emb",)
        )
        assert job["status"] == "FAILED_PERMANENT"
```

**Checklist**:
- [ ] Create integration test file
- [ ] Test happy path
- [ ] Test idempotency
- [ ] Test failure handling

---

### Issue 6.3: Update P08 Dossier

**Type**: Documentation
**Priority**: P1 (High)
**Estimated**: 1 hour

**Location**: `docs/pipelines/P08_embedding_dossier.md`

**Updates**:
- [ ] Mark implementation status as complete
- [ ] Add actual file paths
- [ ] Document any deviations from plan
- [ ] Add performance measurements

---

### Issue 6.4: Create ADR for Module Refactoring

**Type**: ADR
**Priority**: P2 (Medium)
**Estimated**: 1 hour

**Location**: `docs/architecture/decisions-K0/modules/ADR-M-001-driver-to-module-refactoring.md`

**Content**: Document the refactoring from EmbeddingQueueDriver/FaissDriver to pure function modules.

**Checklist**:
- [ ] Create ADR
- [ ] Document refactoring approach
- [ ] Note backward compatibility

---

### Issue 6.5: Update K0 Master Architecture Document

**Type**: Documentation
**Priority**: P1 (High)
**Estimated**: 2 hours

**Location**: `k0/pipelines/k0_architecture_master.md`

**Updates Required**:

| Section | Update |
|---------|--------|
| Part 2.1: Pipeline Registry | Add P08 as YAML pipeline (entry_topic: p02.embedding.enqueued.v1) |
| Part 3.1: Module Registry | Add 5 embedding modules (claim, compute, store, index_faiss, update_status) |
| Part 4.1: Event Topics Registry | Add p02.embedding.enqueued.v1, p08.embedding.complete.v1, p08.embedding.failed.v1 |
| Part 5.2: Syscall Matrix | Add 6 new syscalls (embedding_queue_claim, hipp_event_read, embedding_store, faiss_add, embedding_queue_update_status, hipp_event_update_embedding_status) |
| Part 6.1: Capability Matrix | Add faiss.write, bus.emit capabilities |
| Part 7.1: ADR Index | Add ADR-P08-001 (YAML Pipeline Architecture), ADR-M-001 (Driver to Module Refactoring) |

**Checklist**:
- [ ] Update Pipeline Registry with P08
- [ ] Update Module Registry with 5 embedding modules
- [ ] Update Event Topics Registry with P08 topics
- [ ] Update Syscall Matrix with 6 new syscalls
- [ ] Update Capability Matrix with new capabilities
- [ ] Update ADR Index with new ADRs
- [ ] Update M14 entry to reflect topic emission

---

### Issue 6.6: Update P02 Dossier

**Type**: Documentation
**Priority**: P1 (High)
**Estimated**: 1 hour

**Location**: `docs/pipelines/P02_write_dossier.md`

**Updates**:
- [ ] Update M14 section to document topic emission (not outbox)
- [ ] Add cross-reference to P08 dossier
- [ ] Update status checklist
- [ ] Document P02 -> P08 integration contract

---

## Summary Timeline

| Day | Morning | Afternoon |
|-----|---------|-----------|
| 1 | M1: ADRs, P08 contract | M2: Syscalls (2.1-2.3) |
| 2 | M2: Syscalls (2.4-2.6) | M3: Modules (3.1-3.3) |
| 3 | M3: Modules (3.4-3.6) | M4: P02 Integration |
| 4 | M5: Model/FAISS preload | M6: Contract tests |
| 5 | M6: Integration tests | M6: Documentation (6.3, 6.4) |
| 6 | M6: K0 Master + P02 Dossier (6.5, 6.6) | Final review |

**Total**: ~6 days

---

## Dependency Graph

```text
Issue 1.1 (ADR P08 Architecture)
    |
    v
Issue 1.2 (P08 YAML Contract) -----> Issue 1.3 (Module Contracts)
    |
    v
Issues 2.1-2.6 (New Syscalls)
    |
    v
Issues 3.1-3.6 (Embedding Modules)
    |
    v
Issues 4.1-4.3 (P02 Integration)
    |
    v
Issues 5.1-5.2 (Model Preloading)
    |
    v
Issues 6.1-6.2 (Testing)
    |
    v
Issues 6.3-6.6 (Documentation)
    |
    +---> 6.3 P08 Dossier
    +---> 6.4 ADR Module Refactoring
    +---> 6.5 K0 Master Architecture  <-- NEW
    +---> 6.6 P02 Dossier             <-- NEW
```

---

## Success Criteria

1. **P08 Pipeline Running**: Topic subscription triggers P08 within 500ms
2. **Kernel Boundary Maintained**: All storage via syscalls, no direct driver calls
3. **Status Sync Working**: `st_hipp_events.embedding_status` reflects actual state
4. **Tests Passing**: Contract + integration tests pass
5. **Documentation Updated**: P08 dossier complete
6. **Performance Target Met**: <500ms P95 end-to-end

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| FAISS index thread safety | High | Use async executor for FAISS ops |
| Model memory footprint | Medium | Lazy load option, monitor memory |
| BusDispatcher routing | Medium | Test topic subscription thoroughly |
| Syscall overhead | Low | Batch updates where possible |

---

## References

- **P08 Dossier**: `docs/pipelines/P08_embedding_dossier.md`
- **P08 Exploration**: `docs/pipelines/P08_embedding_exploration.md`
- **Runtime README**: `k0/runtime/README.md`
- **P02 Contract**: `k0/contracts/pipelines/p02_write.v1.yaml`
- **Existing Drivers**: `k0/drivers/embedding_queue.py`, `k0/drivers/faiss.py`
- **M14 Contract**: `k0/contracts/modules/builders.embedding_queue_write.v1.yaml`
