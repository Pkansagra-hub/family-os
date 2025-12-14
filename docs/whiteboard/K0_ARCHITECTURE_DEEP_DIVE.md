# 🏗️ K0 Kernel Architecture Deep Dive

**Purpose:** Understand K0's actual implementation patterns to design the 20 pipelines correctly
**Date:** November 2, 2025
**Audience:** Pipeline designers, ADR authors

---

## 📋 Executive Summary

K0 is a **production-ready microkernel** providing:

- **Single durable commit surface** for all writes
- **Policy enforcement** at syscall boundary (PEP)
- **QoS scheduling** with hard budgets
- **ACID + async cohorts** (SQLite WAL + outbox pattern)
- **Event bus** for post-commit dispatch
- **Driver SPI** for pluggable storage engines

**Key Insight:** Pipelines must integrate into this **existing flow**, not replace it.

---

## 🔍 Core Architecture Patterns

### 1. Request Flow (Command Port)

```
HTTP Request
  ↓
FastAPI Middleware (telemetry, CORS)
  ↓
Minimal Gate (schema/hash/device validation)
  ↓
Idempotency Check (return cached receipt if duplicate)
  ↓
Policy Enforcement Point (PEP) — Evaluate envelope
  ↓
QoS Scheduler (acquire token based on band/port/cost)
  ↓
Unit of Work (UoW)
    ├─ Write to WAL (st_wal table)
    ├─ Issue Receipt (st_receipts)
    ├─ Write to Outbox (st_outbox) — async intents
    ├─ Record Obligations (st_obligations)
    └─ Update Offsets (st_offsets)
  ↓
Commit Transaction (ACID cohort)
  ↓
Bus Dispatcher (post-commit fanout)
    ├─ SSE subscriptions
    ├─ Driver workers (outbox → async cohort)
    └─ Telemetry/metrics
  ↓
Return Receipt to Client
```

**Key Files:**

- `k0/ports/command.py` — HTTP handler, orchestrates flow
- `k0/gate/minimal_gate.py` — Preflight validation
- `k0/policy/pep.py` — Policy evaluation
- `k0/qos/scheduler.py` — Budget enforcement
- `k0/uow/unit_of_work.py` — Transaction coordinator
- `k0/bus/core.py` — Post-commit dispatch

---

### 2. Storage Architecture

#### **ACID Cohort (Synchronous)**

```sql
-- Single SQLite database (k0_runtime.sqlite3)
-- WAL mode enabled
-- Durable writes via fsync

Tables:
  ├─ st_wal              — Append-only event log (pos, tenant, space, topic, envelope, body)
  ├─ st_receipts         — Signed audit trail (receipt_id, wal_pos, sig)
  ├─ st_offsets          — Consumer position tracking (subscriber, topic, offset)
  ├─ st_outbox           — Async intents (wal_pos, driver, op_kind, payload)
  ├─ st_dlq              — Failed operations (reason, retries, state)
  ├─ idem_ledger         — Idempotency deduplication (idem_key → receipt_id)
  ├─ st_devices          — Provisioned device ledger
  ├─ st_device_keys      — Key rotation support
  └─ schema_registry     — Schema validation registry
```

**Key Files:**

- `k0/contracts/sql/storage.sql` — Canonical DDL
- `k0/storage/wal.py` — WAL operations
- `k0/storage/receipts.py` — Receipt management
- `k0/storage/outbox.py` — Outbox pattern implementation
- `k0/storage/replay.py` — Replayer for WAL reconstruction

#### **Async Cohort (Eventually Consistent)**

```
Drivers (via SPI):
  ├─ st_vector     — FAISS vector embeddings
  ├─ st_fts5       — Full-text search (FTS5)
  ├─ st_kg         — Knowledge Graph (SQLite with temporal edges) [PLANNED]
  ├─ st_blob       — Blob storage (local filesystem)
  ├─ st_epi        — Episodic memory [PLANNED]
  ├─ st_semantic   — Semantic knowledge [PLANNED]
  └─ st_affect     — Emotional grounding [PLANNED]
```

**Driver Pattern:**

1. Command writes to WAL + Outbox (ACID commit)
2. Bus dispatcher triggers driver workers
3. Workers read from Outbox, call driver-specific operations
4. On success: Remove from Outbox
5. On failure: Retry with exponential backoff, eventually move to DLQ

**Key Files:**

- `k0/drivers/alias_map.yaml` — Driver registration
- `k0/drivers/sqlite_kg.py` — KG driver (placeholder)
- `k0/drivers/faiss.py` — Vector driver (placeholder)
- `k0/outbox/worker_pool.py` — Outbox processing

---

### 3. Event Bus Pattern

```python
# Post-commit fanout to multiple consumers

class BusDispatcher:
    def __init__(
        self,
        scheduler: Scheduler,
        sinks: List[BusSink],  # List of async handlers
        middlewares: List[BusMiddleware],  # Timestamp, tracing, metrics
    ):
        ...

    async def dispatch(self, messages: List[BusMessage]):
        # Dispatch in WAL order
        # Acquire QoS tokens per message
        # Execute middleware chain
        # Fan out to all sinks
        ...

# Sinks can be:
#   - SSE subscribers (real-time push)
#   - Driver workers (async indexing)
#   - Telemetry emitters
#   - Pipeline handlers (THIS IS WHERE P03/P06/P09 HOOK IN)
```

**Key Insight:** **Pipelines = Bus Sinks**

When P02 (Write) commits to WAL:

1. Bus dispatcher receives `BusMessage`
2. Middleware adds timestamps, traces, metrics
3. Dispatcher fans out to registered sinks:
   - **P03 Consolidation Sink** (episodic → semantic transformation)
   - **P06 Learning Sink** (adaptive feedback processing)
   - **P08 Embedding Sink** (vector generation)
   - **P09 Connector Sink** (external data ingestion)
   - SSE subscribers
   - Telemetry

**Key Files:**

- `k0/bus/core.py` — Bus dispatcher
- `k0/bus/middleware.py` — Timestamp, tracing, latency middlewares

---

### 4. Query Pattern (P01 Recall)

```
HTTP Request (/k0/query.recall)
  ↓
QoS Scheduler (acquire query token)
  ↓
Query Service
    ├─ Parse recall request (space_id, topic filter, selector)
    ├─ Fanout to drivers (st_sqlite, st_fts5, st_vector, st_kg)
    ├─ Apply top-k aggregation
    ├─ Enforce budget limits (max_results, timeout)
    └─ Return aggregated results
  ↓
Response (with telemetry: latency, budgets consumed)
```

**Current State:**

- ✅ Query service exists (`k0/query/service.py`)
- ✅ Fanout to multiple drivers
- ❌ Memory type awareness (doesn't distinguish episodic vs semantic)
- ❌ Semantic enrichment (no context retrieval)
- ❌ Affect filtering (no emotional salience)

**For P01 (Recall):** Enhance query service with:

- Memory type routing (episodic → st_epi, semantic → st_semantic)
- KG traversal for relationship context
- Affect weighting for importance

**Key Files:**

- `k0/query/service.py` — Query orchestration
- `k0/query/router.py` — HTTP handler

---

### 5. Policy Enforcement (PEP)

```python
# Policy Enforcement Point (at syscall boundary)

def evaluate_envelope(envelope: dict, policy_ctx: dict) -> PolicyDecision:
    # 1. Load policy manifest (from k0/policy/manifest.yaml)
    # 2. Evaluate rules (band, topic, role, privacy)
    # 3. Return decision:
    #      - admit: bool
    #      - deny_reason: str | None
    #      - obligations: List[Obligation]  # Actions to enforce
    # 4. Obligations can be:
    #      - REDACT(fields=[...])
    #      - AUDIT_LOG(sensitivity="high")
    #      - QOS_ADJUST(multiplier=0.5)
    ...

class Obligation:
    name: str  # e.g., "REDACT", "AUDIT_LOG"
    details: dict  # {fields: ["email"], level: "PII"}
```

**Key Insight:** Policy obligations trigger pipeline behavior

Example obligations for pipelines:

- `CONSOLIDATE_PRIORITY` → P03 processes this envelope sooner
- `LEARNING_SIGNAL` → P06 receives feedback
- `AFFECT_TAG(emotion="important")` → Affects memory storage
- `PRIVACY_BAND(level="RED")` → Restricts recall

**Key Files:**

- `k0/policy/pep.py` — Policy evaluation
- `k0/policy/manifest.yaml` — Policy rules
- `contracts/policy/bridge_policy.yml` — Contract definition

---

### 6. QoS Scheduling

```python
# Budget-based scheduling with fairness

class Scheduler:
    def acquire(self, band: str, port: str, cost: int) -> SchedulerToken:
        # 1. Check budget for (band, port) pair
        # 2. If budget available:
        #      - Deduct cost
        #      - Return token
        # 3. If budget exceeded:
        #      - Raise QoSBudgetError
        # 4. Token release returns cost to budget
        ...

Budgets (from qos/defaults.yaml):
  GREEN:
    command: 1000 tokens/sec
    query: 500 tokens/sec
    bus: 2000 tokens/sec
  AMBER:
    command: 500 tokens/sec
    query: 250 tokens/sec
  RED:
    command: 100 tokens/sec
    query: 50 tokens/sec
```

**Key Insight:** Pipelines must respect QoS budgets

P03 Consolidation:

- Runs in background (band=GREEN, port=consolidation)
- Cost = number of episodic memories to process
- If budget exceeded, defer until next cycle

P09 Connectors:

- External API calls (band=AMBER, port=connector)
- Cost = API rate limit consumed
- Backpressure prevents overload

**Key Files:**

- `k0/qos/scheduler.py` — Budget enforcement
- `k0/qos/defaults.yaml` — Default profiles

---

### 7. Observability (Metrics, Traces, Logs)

```python
# Three-pillar observability

# 1. Metrics (Prometheus)
metrics_exporter.emit(
    "http_requests_total",
    1.0,
    route="/k0/command.submit",
    status="200",
    outcome="success"
)

# 2. Traces (OpenTelemetry)
with tracer.span("P03_Consolidation", attributes={...}):
    # Consolidation work
    ...

# 3. Logs (Structured)
logger.info(
    "Consolidation phase complete",
    extra={
        "cognitive_trace_id": trace_id,
        "phase": "episodic_to_semantic",
        "memories_processed": 47,
        "duration_ms": 230
    }
)
```

**Key Insight:** Pipelines must emit telemetry

Each pipeline needs:

- **Metrics:**
  - `pipeline_executions_total{pipeline, outcome}`
  - `pipeline_latency_seconds{pipeline, phase}`
  - `pipeline_backlog{pipeline}`
- **Traces:**
  - Span per pipeline execution
  - Attributes: memory types, counts, outcomes
- **Logs:**
  - Structured logs with `cognitive_trace_id`
  - Include: phase, duration, errors

**Key Files:**

- `k0/obs/metrics.py` — Metrics exporter
- `k0/obs/tracing.py` — Tracer factory
- `k0/telemetry/` — Telemetry configuration

---

## 🔌 Where Pipelines Hook In

### **Pattern 1: Bus Sink (Post-Commit Processing)**

```python
# Example: P03 Consolidation Sink

class ConsolidationSink:
    async def __call__(self, message: BusMessage) -> None:
        # 1. Check if topic is relevant (e.g., "mem.episodic.append")
        if not self._should_process(message):
            return

        # 2. Acquire QoS token
        token = scheduler.acquire(band="GREEN", port="consolidation", cost=1)

        try:
            # 3. Parse message payload (envelope + body)
            envelope = json.loads(message.payload)

            # 4. Process consolidation phases
            await self._hippocampal_replay(envelope)
            await self._episodic_to_semantic(envelope)
            await self._kg_evolution(envelope)

            # 5. Write consolidated results to async cohort
            #    (via outbox → st_semantic, st_kg drivers)

        finally:
            token.release()

# Register with bus dispatcher
bus_dispatcher.register_sink(ConsolidationSink())
```

**Applicable Pipelines:**

- ✅ P03 (Consolidation)
- ✅ P06 (Learning)
- ✅ P08 (Embedding Lifecycle)
- ✅ P13 (Index Rebuild)
- ✅ P14 (Deduplication)
- ✅ P15 (Rollups)
- ✅ P18 (Safety)

---

### **Pattern 2: Outbox Worker (Async Driver Operations)**

```python
# Example: P08 Embedding Worker

class EmbeddingWorker:
    def __init__(self, outbox_store: OutboxStore, vector_driver: FAISSDriver):
        self.outbox = outbox_store
        self.driver = vector_driver

    async def process_batch(self):
        # 1. Read pending entries from st_outbox (driver="st_vector")
        entries = self.outbox.fetch_pending(driver="st_vector", limit=100)

        for entry in entries:
            try:
                # 2. Generate embedding
                text = entry.payload["text"]
                vector = await self._generate_embedding(text)

                # 3. Write to FAISS index
                await self.driver.upsert(entry.payload["id"], vector)

                # 4. Remove from outbox
                self.outbox.delete(entry.id)

            except Exception as e:
                # 5. On failure: retry or move to DLQ
                self.outbox.increment_retry(entry.id)
                if entry.retries >= 3:
                    self.outbox.move_to_dlq(entry.id, reason=str(e))

# Start worker pool
worker_pool.register_worker("st_vector", EmbeddingWorker(...))
```

**Applicable Pipelines:**

- ✅ P08 (Embedding Lifecycle)
- ✅ P09 (Connector Ingestion) — External API calls
- ✅ P07 (Sync/CRDT) — Multi-device coordination
- ✅ P13 (Index Rebuild)
- ✅ P14 (Deduplication)

---

### **Pattern 3: Query Port Extension (Enriched Recall)**

```python
# Example: P01 Recall with Memory Type Awareness

class MemoryAwareQueryService:
    def recall(self, request: RecallRequest) -> RecallResponse:
        # 1. Determine memory types needed
        memory_types = self._infer_memory_types(request.selector)
        # e.g., {"episodic", "semantic", "affect", "kg"}

        # 2. Fanout to relevant drivers
        results = {}
        if "episodic" in memory_types:
            results["episodic"] = self.drivers["st_epi"].query(...)
        if "semantic" in memory_types:
            results["semantic"] = self.drivers["st_semantic"].query(...)
        if "kg" in memory_types:
            results["kg"] = self.drivers["st_kg"].traverse(...)

        # 3. Apply affect filtering (emotional salience)
        if "affect" in memory_types:
            affect_tags = self.drivers["st_affect"].query(...)
            results = self._filter_by_salience(results, affect_tags)

        # 4. Aggregate with top-k
        aggregated = self._aggregate_top_k(results, request.top_k)

        # 5. Return enriched response
        return RecallResponse(memories=aggregated, context=...)
```

**Applicable Pipelines:**

- ✅ P01 (Recall/Read) — Enhanced query
- ✅ P19 (Personalization) — User model retrieval

---

### **Pattern 4: Command Port Extension (Memory Formation)**

```python
# Example: P02 Write with Async Memory Formation

async def submit_command(envelope: Envelope, body: bytes):
    # 1. Existing flow: Gate → PEP → QoS → UoW → Commit

    # 2. **NEW:** After commit, trigger async memory formation
    async def _async_memory_formation():
        # Parse memory type from topic
        if envelope.topic.startswith("mem.episodic"):
            # Trigger P03 consolidation (via bus sink)
            # Trigger P06 learning (if feedback signal)
            # Trigger P08 embedding (vector generation)
            # Trigger P19 personalization (user model update)
            pass

    # 3. Fork async task (non-blocking)
    asyncio.create_task(_async_memory_formation())

    # 4. Return receipt immediately (<200ms target)
    return receipt
```

**Applicable Pipelines:**

- ✅ P02 (Write/Ingest) — Async triggering
- ✅ P05 (Prospective) — Trigger scheduling
- ✅ P19 (Personalization) — User model updates

---

### **Pattern 5: Scheduled Background Jobs**

```python
# Example: P03 Consolidation Scheduler

class ConsolidationScheduler:
    def __init__(self, interval_seconds: int = 3600):
        self.interval = interval_seconds

    async def run_forever(self):
        while True:
            await asyncio.sleep(self.interval)

            # 1. Trigger consolidation cycle
            await self._run_consolidation_cycle()

    async def _run_consolidation_cycle(self):
        # 1. Query for episodic memories since last consolidation
        last_run = self._get_last_consolidation_timestamp()
        episodic_memories = self._query_episodic_since(last_run)

        # 2. Run 5 consolidation phases
        await self._phase_1_hippocampal_replay(episodic_memories)
        await self._phase_2_episodic_to_semantic(episodic_memories)
        await self._phase_3_kg_evolution(episodic_memories)
        await self._phase_4_synaptic_pruning(episodic_memories)
        await self._phase_5_dream_exploration(episodic_memories)

        # 3. Record consolidation log
        self._log_consolidation_run(timestamp=now(), memories_processed=len(...))

# Start scheduler
asyncio.create_task(ConsolidationScheduler().run_forever())
```

**Applicable Pipelines:**

- ✅ P03 (Consolidation) — Sleep-like processing (hourly/daily)
- ✅ P05 (Prospective) — Trigger checking (minute/hourly)
- ✅ P07 (Sync/CRDT) — Multi-device sync (5min intervals)
- ✅ P13 (Index Rebuild) — Maintenance (daily)
- ✅ P14 (Deduplication) — Cleanup (daily)
- ✅ P15 (Rollups) — Aggregation (hourly)

---

## 📊 Memory Table Design Guidance

Based on K0's storage patterns, here's how to design memory tables:

### **Pattern: Episodic Memory (st_epi)**

```sql
-- Episodic memories (time-stamped experiences)
CREATE TABLE IF NOT EXISTS st_episodic (
  id TEXT PRIMARY KEY,                 -- UUID
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  commit_ts TEXT NOT NULL,             -- ISO8601 timestamp
  wal_pos INTEGER NOT NULL,            -- Reference to st_wal
  content_text TEXT NOT NULL,          -- Searchable text
  content_embedding BLOB,              -- Vector (768-dim, optional)
  entities_json TEXT,                  -- Extracted entities: ["Mom", "coffee"]
  affect_tags TEXT,                    -- Emotional tags: "important,supportive"
  affect_salience REAL DEFAULT 0.0,    -- Importance score (0.0-1.0)
  privacy_band TEXT NOT NULL,          -- GREEN/AMBER/RED
  schema_uri TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  consolidated_at TEXT,                -- Timestamp of last consolidation
  consolidated_to_semantic_id TEXT,    -- Link to st_semantic
  FOREIGN KEY(wal_pos) REFERENCES st_wal(pos)
);

CREATE INDEX idx_episodic_space_ts ON st_episodic(space_id, commit_ts);
CREATE INDEX idx_episodic_salience ON st_episodic(affect_salience DESC);
CREATE INDEX idx_episodic_consolidated ON st_episodic(consolidated_at);
```

**Key Design Choices:**

- ✅ References `st_wal(pos)` for provenance
- ✅ Includes `affect_salience` for emotional weighting
- ✅ Tracks `consolidated_at` to know what's been processed
- ✅ Links to semantic knowledge via `consolidated_to_semantic_id`

---

### **Pattern: Semantic Knowledge (st_semantic)**

```sql
-- Semantic knowledge (generalized facts, patterns)
CREATE TABLE IF NOT EXISTS st_semantic (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  knowledge_text TEXT NOT NULL,        -- e.g., "Mom values connection"
  knowledge_type TEXT NOT NULL,        -- "pattern", "rule", "preference"
  confidence REAL DEFAULT 1.0,         -- Confidence score (0.0-1.0)
  source_episodic_ids TEXT,            -- JSON array of episodic IDs that led to this
  source_count INTEGER DEFAULT 1,      -- Number of episodic memories supporting this
  created_at TEXT NOT NULL,            -- When this was first learned
  updated_at TEXT NOT NULL,            -- Last reinforcement
  privacy_band TEXT NOT NULL,
  schema_uri TEXT NOT NULL,
  schema_version TEXT NOT NULL
);

CREATE INDEX idx_semantic_space ON st_semantic(space_id, updated_at);
CREATE INDEX idx_semantic_confidence ON st_semantic(confidence DESC);
CREATE INDEX idx_semantic_type ON st_semantic(knowledge_type);
```

**Key Design Choices:**

- ✅ Stores generalized facts ("Mom values connection")
- ✅ Tracks `source_episodic_ids` for provenance
- ✅ Includes `confidence` score (can decay over time)
- ✅ Updates `source_count` as more episodes support it

---

### **Pattern: Knowledge Graph (st_kg)**

```sql
-- Knowledge Graph nodes (entities)
CREATE TABLE IF NOT EXISTS st_kg_nodes (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  node_type TEXT NOT NULL,             -- "person", "event", "location", "concept"
  label TEXT NOT NULL,                 -- Display name: "Mom", "Alice", "PT session"
  attributes_json TEXT,                -- {age: 65, role: "mother"}
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  privacy_band TEXT NOT NULL
);

-- Knowledge Graph edges (relationships)
CREATE TABLE IF NOT EXISTS st_kg_edges (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  source_id TEXT NOT NULL,             -- From node
  target_id TEXT NOT NULL,             -- To node
  edge_type TEXT NOT NULL,             -- "sister", "supports", "attends", "caused"
  confidence REAL DEFAULT 1.0,
  valid_from TEXT,                     -- Temporal validity start
  valid_to TEXT,                       -- Temporal validity end (NULL = ongoing)
  attributes_json TEXT,                -- {frequency: "2x/week"}
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES st_kg_nodes(id),
  FOREIGN KEY(target_id) REFERENCES st_kg_nodes(id)
);

CREATE INDEX idx_kg_edges_source ON st_kg_edges(source_id, edge_type);
CREATE INDEX idx_kg_edges_target ON st_kg_edges(target_id, edge_type);
CREATE INDEX idx_kg_edges_temporal ON st_kg_edges(valid_from, valid_to);
```

**Key Design Choices:**

- ✅ Separate nodes and edges (standard graph structure)
- ✅ Temporal validity (`valid_from`, `valid_to`) for time-aware relationships
- ✅ Confidence scores for uncertainty
- ✅ Attributes in JSON for flexibility

---

### **Pattern: Consolidation Log (P03 tracking)**

```sql
-- Consolidation pipeline execution log
CREATE TABLE IF NOT EXISTS st_consolidation_log (
  run_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  phase TEXT NOT NULL,                 -- "hippocampal", "semantic", "kg", "pruning", "dream"
  status TEXT NOT NULL,                -- "running", "completed", "failed"
  episodic_count INTEGER DEFAULT 0,    -- Memories processed
  semantic_created INTEGER DEFAULT 0,  -- New semantic facts
  kg_nodes_created INTEGER DEFAULT 0,
  kg_edges_created INTEGER DEFAULT 0,
  duration_ms INTEGER,
  error_reason TEXT
);

CREATE INDEX idx_consolidation_space_ts ON st_consolidation_log(space_id, started_at);
CREATE INDEX idx_consolidation_phase ON st_consolidation_log(phase, status);
```

---

### **Pattern: Learning Traces (P06 tracking)**

```sql
-- Learning loop feedback tracking
CREATE TABLE IF NOT EXISTS st_learning_traces (
  trace_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  feedback_signal TEXT NOT NULL,       -- "positive", "negative", "neutral"
  feedback_source TEXT NOT NULL,       -- "user_explicit", "implicit_behavior"
  learned_update_json TEXT NOT NULL,   -- {parameter: "social_proactivity", delta: +0.2}
  confidence REAL DEFAULT 1.0,
  created_at TEXT NOT NULL,
  applied_at TEXT,                     -- When parameter was updated
  reverted_at TEXT,                    -- If rolled back due to drift
  revert_reason TEXT
);

CREATE INDEX idx_learning_space_ts ON st_learning_traces(space_id, created_at);
CREATE INDEX idx_learning_signal ON st_learning_traces(feedback_signal);
```

---

## 🎯 Pipeline Design Checklist

When designing a pipeline ADR, include:

### **1. Integration Point**

- [ ] Bus sink (post-commit)?
- [ ] Outbox worker (async driver)?
- [ ] Query enhancement?
- [ ] Command extension?
- [ ] Scheduled background job?

### **2. Storage Schema**

- [ ] DDL for tables (if new memory type)
- [ ] Indexes for performance
- [ ] Foreign keys to `st_wal` for provenance
- [ ] Privacy band column
- [ ] Temporal validity (if relationships)

### **3. QoS Profile**

- [ ] Port name (e.g., "consolidation", "connector")
- [ ] Cost model (tokens per operation)
- [ ] Budget limits per band (GREEN/AMBER/RED)
- [ ] Backpressure handling

### **4. Policy Integration**

- [ ] Obligations that trigger pipeline (e.g., `CONSOLIDATE_PRIORITY`)
- [ ] Privacy enforcement (respect RED band)
- [ ] Audit logging

### **5. Observability**

- [ ] Metrics:
  - `pipeline_executions_total{pipeline, outcome}`
  - `pipeline_latency_seconds{pipeline, phase}`
  - `pipeline_backlog{pipeline}`
- [ ] Traces:
  - Span per execution
  - Attributes (memory count, phase, outcome)
- [ ] Logs:
  - Structured with `cognitive_trace_id`
  - Include: phase, duration, errors

### **6. Error Handling**

- [ ] Retry strategy (exponential backoff)
- [ ] DLQ for permanent failures
- [ ] Alerting thresholds

### **7. Testing**

- [ ] Integration tests (not mocks)
- [ ] Contract compliance tests
- [ ] Performance budget tests (latency, throughput)

---

## 🚀 Next Steps

1. ✅ **Understand K0 architecture** (this document)
2. ⏭️ **Write ADRs for P01-P20** using patterns above
3. ⏭️ **Define schemas** (episodic, semantic, affect, KG, etc.)
4. ⏭️ **Update storage.sql** with memory tables
5. ⏭️ **Implement pipelines** following established K0 conventions

---

## 📚 Key Files Reference

| Component | File | Purpose |
|-----------|------|---------|
| **App Factory** | `k0/kernel/app.py` | FastAPI setup, dependency wiring |
| **Config** | `k0/kernel/config.py` | Settings, env vars, YAML loading |
| **Command Port** | `k0/ports/command.py` | Write operations |
| **Query Port** | `k0/ports/query.py` | Read operations |
| **Event Bus** | `k0/bus/core.py` | Post-commit dispatch |
| **WAL** | `k0/storage/wal.py` | Append-only log |
| **Outbox** | `k0/storage/outbox.py` | Async intents |
| **Receipts** | `k0/receipts/issuer.py` | Signed audit trail |
| **Policy** | `k0/policy/pep.py` | PEP enforcement |
| **QoS** | `k0/qos/scheduler.py` | Budget enforcement |
| **Drivers** | `k0/drivers/` | Storage engine SPI |
| **Metrics** | `k0/obs/metrics.py` | Prometheus exporter |
| **Tracing** | `k0/obs/tracing.py` | OpenTelemetry spans |
| **Storage DDL** | `k0/contracts/sql/storage.sql` | Canonical schema |

---

## 🔑 Key Takeaways

1. **Pipelines = Bus Sinks + Outbox Workers + Query Extensions**
2. **Memory tables must link to `st_wal` for provenance**
3. **All pipelines respect QoS budgets and policy obligations**
4. **Observability is mandatory: metrics, traces, logs**
5. **Use existing K0 patterns, don't reinvent**
6. **ACID cohort (SQLite) for durability, async cohort (drivers) for convergence**
7. **Integration tests with real components, no mocks**

---
