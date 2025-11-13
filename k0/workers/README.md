# K0 Workers Module

**Purpose:** Async background workers for embedding generation and FTS indexing (V1.4 Performance Optimization). Reduces commit latency from ~150ms to ~80-100ms by deferring heavy computation to background workers.

---

## Part 1: Repository Files & Functions

### Core Files

#### `__init__.py`
**Purpose:** Module package entry (no exports to avoid sys.modules pollution)

**Design Note:** Workers are designed to run as standalone scripts via `python -m k0.workers.embedding_worker`. Nothing is imported at package level to avoid `RuntimeWarning` when executing workers as modules.

**Import Pattern:**
```python
# Import directly where needed:
from k0.workers.coordinator import AsyncWorkerCoordinator
from k0.workers.embedding_worker import EmbeddingWorker
from k0.workers.fts_worker import FtsIndexingWorker
```

---

#### `coordinator.py`
**Purpose:** Coordinates embedding and FTS workers through outbox-based work queuing

**Key Classes:**

**`WorkerCoordinatorConfig`** (dataclass)
- `embedding_batch_size: int = 10` - Max embeddings per batch
- `fts_batch_size: int = 50` - Max FTS entries per batch (FTS can batch more aggressively)
- `max_retries: int = 3` - Retry attempts before marking FAILED
- `retry_backoff_ms: int = 100` - Exponential backoff delay

**`WorkerResult`** (dataclass)
- `operation_kind: str` - `COMPUTE_EMBEDDING` or `INDEX_FTS`
- `event_id: str` - Event identifier
- `status: str` - `COMPLETE` or `FAILED`
- `result: EmbeddingResult | FtsIndexResult | None` - Worker result
- `error: str | None` - Error message if failed

**`AsyncWorkerCoordinator`**
- **Purpose:** Dispatches work from outbox to workers, aggregates results, updates WAL

**Key Methods:**

**`__init__(config: WorkerCoordinatorConfig | None = None) -> None`**
- Initializes coordinator with embedding and FTS workers
- Lazy imports workers at runtime (avoids sys.modules conflicts)

**`process_outbox_batch(outbox_entries: list[dict[str, Any]]) -> list[WorkerResult]`**
- Processes batch of outbox entries
- Separates by operation kind (`COMPUTE_EMBEDDING` vs `INDEX_FTS`)
- Dispatches to appropriate worker
- Returns list of results (COMPLETE or FAILED)
- Logs processing and failure counts

**`get_status() -> dict[str, Any]`**
- Returns coordinator status:
  - `processed`: Total successful operations
  - `failed`: Total failed operations
  - `success_rate`: `processed / (processed + failed)`

**Architecture:**
1. **Commit phase:** Create outbox entries for embedding + FTS work
2. **Worker discovery:** Poll outbox for pending work
3. **Worker dispatch:** Send to embedding/FTS workers
4. **Worker completion:** Update WAL with results, mark outbox complete
5. **Status propagation:** Track embedding_status and fts_status in hippocampus store

**Performance Impact:**
- Commit latency: 150ms → 80-100ms (47-67% reduction)
- Embedding computation: 50-100ms (now async)
- FTS indexing: 10-30ms (now async)

---

#### `embedding_worker.py`
**Purpose:** Async embedding generation worker (V1.4 Performance Optimization)

**Key Classes:**

**`EmbeddingRequest`** (dataclass)
- `event_id: str` - Memory event identifier
- `space_id: str` - Memory space
- `text: str` - Text to embed
- `topics: list[str] | None` - Optional topics
- `embedding_model: str` - Model name (default: `all-mpnet-base-v2`)
- `backend: Literal["openai", "sentence-transformers", "ollama", "fake"]` - Backend

**`EmbeddingResult`** (dataclass)
- `event_id: str` - Event identifier
- `embedding_id: str` - Generated embedding ID
- `embedding_dimension: int` - Vector dimension (384-1536)
- `model_used: str` - Actual model used
- `computed_at: str` - ISO timestamp

**`EmbeddingWorker`**
- **Purpose:** Polls outbox, computes embeddings, updates WAL

**Configuration:**
- `db_path: str | Path` - SQLite database path
- `batch_size: int = 10` - Max embeddings per batch
- `model: str` - Embedding model name
- `backend: Literal[...]` - Embedding backend
- `poll_interval_sec: float = 1.0` - Polling interval

**Key Methods:**

**`process_embedding_request(request: EmbeddingRequest) -> EmbeddingResult`**
- Computes embedding for single request
- Delegates to backend (OpenAI, sentence-transformers, Ollama, fake)
- Returns result with embedding_id

**`process_batch(requests: list[EmbeddingRequest]) -> list[EmbeddingResult]`**
- Processes batch of embedding requests
- Continues on individual failures (fault isolation)

**`run_once() -> int`**
- Processes one batch of outbox entries
- Returns count of processed entries
- **Workflow:**
  1. Dequeue batch from outbox (driver="embedding")
  2. Parse payloads → EmbeddingRequest
  3. Compute embeddings
  4. Update WAL: `embedding_status=DONE`, `embedding_id=<id>`
  5. Mark outbox entries as applied (delete)
  6. Commit transaction

**`run_forever() -> None`**
- Runs worker continuously (production mode)
- Polls every `poll_interval_sec` seconds
- Handles KeyboardInterrupt gracefully
- Exponential backoff on errors

**Embedding Backends:**

**1. sentence-transformers (Local HuggingFace)**
- Models: `all-MiniLM-L6-v2` (384 dims), `all-mpnet-base-v2` (768 dims)
- Lazy loading: Model cached globally
- No API rate limits
- CPU/GPU support

**2. openai (OpenAI API)**
- Models: `text-embedding-3-small` (1536 dims), `text-embedding-3-large`
- Requires `OPENAI_API_KEY` environment variable
- Rate limits: 3000 RPM, 1M TPM (tier 1)
- Exponential backoff on 429 errors

**3. ollama (Local Ollama Deployment)**
- Models: `llama2`, `mistral` (varies by model)
- Requires Ollama server running (default: `http://localhost:11434`)
- Uses `OLLAMA_URL` environment variable
- No rate limits

**4. fake (Testing Only)**
- Deterministic hash-based embedding IDs
- No actual embeddings computed
- Used for testing and development

**Embedding ID Format:**
- sentence-transformers: `emb-st-<event_id[:8]>-<text_hash>`
- openai: `emb-openai-<event_id[:8]>-<index>`
- ollama: `emb-ollama-<event_id[:8]>-<text_hash>`
- fake: `emb-fake-<event_id[:8]>-<text_hash>`

**CLI Usage:**
```bash
# Run worker with environment config
export EMBEDDING_BACKEND=sentence-transformers
export EMBEDDING_MODEL=all-MiniLM-L6-v2
export K0_DB_PATH=k0_runtime.sqlite3
python -m k0.workers.embedding_worker

# Or with inline config
EMBEDDING_BACKEND=openai OPENAI_API_KEY=sk-... python -m k0.workers.embedding_worker
```

**Environment Variables:**
- `K0_DB_PATH` - Database path (default: `k0_runtime.sqlite3`)
- `EMBEDDING_BACKEND` - Backend: `sentence-transformers`, `openai`, `ollama`, `fake`
- `EMBEDDING_MODEL` - Model name (backend-specific)
- `EMBEDDING_BATCH_SIZE` - Batch size (default: 10)
- `EMBEDDING_POLL_INTERVAL_SEC` - Poll interval (default: 1.0)
- `OPENAI_API_KEY` - OpenAI API key (required for openai backend)
- `OLLAMA_URL` - Ollama server URL (default: `http://localhost:11434`)

---

**Helper Functions:**

**`compute_embedding(request: EmbeddingRequest) -> EmbeddingResult`**
- Computes embedding using specified backend
- Raises `RuntimeError` if backend unavailable or API error

**`embedding_payload_to_request(payload: dict[str, Any]) -> EmbeddingRequest`**
- Converts outbox payload to EmbeddingRequest

**Backend-Specific Functions:**
- `_compute_sentence_transformer(request) -> EmbeddingResult`
- `_compute_openai(request) -> EmbeddingResult`
- `_compute_ollama(request) -> EmbeddingResult`
- `_compute_fake(request) -> EmbeddingResult`

---

#### `fts_worker.py`
**Purpose:** Async FTS indexing worker (V1.4 Performance Optimization)

**Key Classes:**

**`FtsIndexRequest`** (dataclass)
- `event_id: str` - Event identifier
- `space_id: str` - Memory space
- `document_id: str` - Document identifier
- `text: str` - Text to index
- `document_type: str` - Document type (e.g., `memory_event`, `envelope_receipt`)
- `keywords: list[str] | None` - Optional pre-extracted keywords

**`FtsIndexResult`** (dataclass)
- `event_id: str` - Event identifier
- `fts_entry_id: str` - Generated FTS entry ID
- `indexed_at: str` - ISO timestamp
- `text_length: int` - Character count
- `keyword_count: int` - Extracted keyword count

**`FtsIndexingWorker`**
- **Purpose:** Polls outbox, builds FTS entries, updates WAL

**Configuration:**
- `db_path: str | Path` - SQLite database path
- `batch_size: int = 50` - Max FTS entries per batch (can batch more than embedding)
- `poll_interval_sec: float = 1.0` - Polling interval
- `index_name: str = "memory_events"` - FTS index name

**Key Methods:**

**`process_fts_request(request: FtsIndexRequest) -> FtsIndexResult`**
- Processes single FTS indexing request
- Extracts keywords if not provided
- Generates FTS entry ID

**`process_batch(requests: list[FtsIndexRequest]) -> list[FtsIndexResult]`**
- Processes batch of FTS requests
- Continues on individual failures

**`run_once() -> int`**
- Processes one batch of outbox entries
- Returns count of processed entries
- **Workflow:**
  1. Dequeue batch from outbox (driver="fts")
  2. Parse payloads → FtsIndexRequest
  3. Extract keywords and index text
  4. Update WAL: `fts_status=DONE`, `fts_entry_id=<id>`
  5. Mark outbox entries as applied (delete)
  6. Commit transaction

**`run_forever() -> None`**
- Runs worker continuously (production mode)
- Polls every `poll_interval_sec` seconds

**NLP Processing:**

**`extract_keywords(text: str, max_keywords: int = 10, language: str = "english", stem: bool = True) -> list[str]`**
- **Tokenization:** NLTK `word_tokenize()` (handles punctuation, contractions)
- **Stop Word Removal:** NLTK stopwords corpus (40+ languages)
- **Stemming:** Porter stemmer (reduces "running", "ran", "runs" → "run")
- **Deduplication:** Preserves order, removes duplicates
- **Filtering:** Removes punctuation, short tokens (<3 chars)

**Production NLP Libraries:**
- **NLTK:** Tokenization, stop words, stemming
- **spaCy (optional):** Named entity recognition, POS tagging
- **Porter Stemmer:** English stemming
- **Snowball Stemmer:** Multi-language stemming (future)

**FTS Entry ID Format:**
- `fts-<event_id[:8]>-<keyword_count:02d>`

**CLI Usage:**
```bash
# Run worker with environment config
export K0_DB_PATH=k0_runtime.sqlite3
export FTS_BATCH_SIZE=50
python -m k0.workers.fts_worker
```

**Environment Variables:**
- `K0_DB_PATH` - Database path (default: `k0_runtime.sqlite3`)
- `FTS_BATCH_SIZE` - Batch size (default: 50)
- `FTS_POLL_INTERVAL_SEC` - Poll interval (default: 1.0)

---

**Helper Functions:**

**`fts_payload_to_request(payload: dict[str, Any]) -> FtsIndexRequest`**
- Converts outbox payload to FtsIndexRequest

---

### Architecture Patterns

#### 1. Outbox-Based Work Queue
**Pattern:** Async work dispatched via transactional outbox

**Workflow:**
```
Commit Phase (Synchronous)
  ↓
Create outbox entries (driver="embedding"/"fts", op_kind="COMPUTE_EMBEDDING"/"INDEX_FTS")
  ↓
Commit transaction (embedding_status=PENDING, fts_status=PENDING)
  ↓
[Async Workers Poll]
  ↓
Worker Phase (Asynchronous)
  ↓
Dequeue outbox batch (driver filter)
  ↓
Process batch (compute embeddings / build FTS entries)
  ↓
Update WAL (embedding_id, fts_entry_id, status=DONE)
  ↓
Mark outbox applied (delete entries)
  ↓
Commit
```

**Benefits:**
- Decouples heavy computation from commit path
- Fault isolation (worker failures don't block commits)
- Retryable work (outbox retries on failure)
- Backpressure via outbox backlog

---

#### 2. Standalone Script Execution
**Pattern:** Workers run as `python -m k0.workers.<worker>`

**Design:**
- No package-level imports (avoids sys.modules pollution)
- `__main__` block for CLI entry
- Environment variable configuration
- Structured logging to stdout

**Benefits:**
- Clean process isolation
- Easy deployment (systemd, supervisord, Docker)
- Independent scaling (run multiple workers)

---

#### 3. Backend Abstraction
**Pattern:** Pluggable embedding backends

**Backends:**
- `sentence-transformers`: Local HuggingFace (no API costs)
- `openai`: OpenAI API (high quality, rate limited)
- `ollama`: Local Ollama (privacy-focused)
- `fake`: Testing (deterministic, no computation)

**Benefits:**
- Flexibility for different deployment scenarios
- Cost optimization (local vs cloud)
- Privacy control (local vs API)
- Testing without external dependencies

---

## Part 2: Cross-Module Connections & Integration Points

### Upstream Dependencies

#### 1. Outbox Store (`k0/storage/outbox.py`)
**Connection:** Workers poll outbox for pending work

**Integration:**
- Workers call `outbox_store.dequeue_ready_batch(driver="embedding"/"fts")`
- Mark entries applied: `outbox_store.mark_applied(entry.id)`
- Record failures: `outbox_store.record_failure(entry, retries, ...)`

**Outbox Entry Schema:**
```python
OutboxEntry(
    driver="embedding",  # or "fts"
    op_kind="COMPUTE_EMBEDDING",  # or "INDEX_FTS"
    payload=json.dumps({
        "event_id": "...",
        "space_id": "...",
        "text": "...",
        "embedding_model": "all-mpnet-base-v2"
    }),
    wal_pos=12345,
    status="PENDING"
)
```

---

#### 2. WAL (`k0/storage/wal.py`)
**Connection:** Workers update WAL with embedding_id and fts_entry_id

**Schema Updates:**
```sql
UPDATE st_wal
SET embedding_status='DONE', embedding_id='emb-st-...'
WHERE wal_pos=?

UPDATE st_wal
SET fts_status='DONE', fts_entry_id='fts-...-10'
WHERE wal_pos=?
```

**Status Tracking:**
- `embedding_status`: `PENDING` → `DONE` (or `FAILED` after retries)
- `fts_status`: `PENDING` → `DONE` (or `FAILED` after retries)

---

#### 3. Ports (`k0/ports/command_port.py`)
**Connection:** Command port creates outbox entries during commit

**Pattern:**
```python
with UnitOfWork(...) as uow:
    # Append WAL entry
    wal_pos = uow.append_wal(WalEntry(...))

    # Stage embedding work
    uow.stage_outbox(OutboxEntry(
        driver="embedding",
        op_kind="COMPUTE_EMBEDDING",
        payload=json.dumps({
            "event_id": event_id,
            "text": event.text,
            ...
        }),
        wal_pos=wal_pos
    ))

    # Stage FTS work
    uow.stage_outbox(OutboxEntry(
        driver="fts",
        op_kind="INDEX_FTS",
        payload=json.dumps({
            "event_id": event_id,
            "text": event.text,
            ...
        }),
        wal_pos=wal_pos
    ))

    # Commit (async work queued)
```

---

### Downstream Consumers

#### 1. Hippocampus Store
**Connection:** Embedding IDs used for semantic search

**Integration:**
- Workers generate `embedding_id` → stored in WAL
- Hippocampus queries embeddings for memory retrieval
- Vector similarity search uses embedding IDs

---

#### 2. FTS Query Port (`k0/ports/query_port.py`)
**Connection:** FTS entry IDs used for keyword search

**Integration:**
- Workers generate `fts_entry_id` → stored in WAL
- Query port searches FTS index by keywords
- Full-text search uses FTS entry IDs

---

### Testing Strategy

#### 1. Worker Unit Tests
**Coverage:**
- Embedding request/result serialization
- FTS request/result serialization
- Keyword extraction (NLTK)
- Backend switching (fake/sentence-transformers)
- Batch processing
- Error handling

---

#### 2. Coordinator Integration Tests
**Coverage:**
- Outbox batch processing
- Worker result aggregation
- Status tracking (processed/failed counts)
- Mixed workloads (embedding + FTS)

---

#### 3. End-to-End Tests
**Coverage:**
- Full workflow: commit → outbox → worker → WAL update
- Worker restart scenarios
- Failure and retry logic
- Backpressure (outbox backlog)

---

### Performance Characteristics

#### Commit Latency Reduction
**Before V1.4:**
- Command submit: ~150ms P95
- Breakdown: UoW commit (50ms) + embedding (50-100ms) + FTS (10-30ms)

**After V1.4:**
- Command submit: ~80-100ms P95
- Breakdown: UoW commit (50ms) + outbox staging (30-50ms)
- Embedding/FTS: Async (no blocking)

**Improvement:** 47-67% latency reduction

---

#### Worker Throughput
**Embedding Worker:**
- Batch size: 10 requests
- Processing time: 500-1000ms per batch (sentence-transformers)
- Throughput: 10-20 embeddings/sec

**FTS Worker:**
- Batch size: 50 requests
- Processing time: 500-1500ms per batch (NLTK)
- Throughput: 33-100 FTS entries/sec

---

#### Backpressure Handling
**Outbox Saturation:**
- Alert @ 50k pending entries (warning)
- Alert @ 100k pending entries (critical)

**Mitigation:**
- Scale worker instances horizontally
- Increase batch sizes
- Optimize NLP processing (caching, parallelization)

---

### Operational Notes

#### 1. Deployment
**Systemd Service (Linux):**
```ini
[Unit]
Description=K0 Embedding Worker
After=network.target

[Service]
Type=simple
User=k0
WorkingDirectory=/opt/k0
Environment="EMBEDDING_BACKEND=sentence-transformers"
Environment="EMBEDDING_MODEL=all-mpnet-base-v2"
ExecStart=/usr/bin/python -m k0.workers.embedding_worker
Restart=always

[Install]
WantedBy=multi-user.target
```

**Docker Compose:**
```yaml
services:
  embedding-worker:
    image: k0-kernel:latest
    command: python -m k0.workers.embedding_worker
    environment:
      - EMBEDDING_BACKEND=sentence-transformers
      - K0_DB_PATH=/data/k0_runtime.sqlite3
    volumes:
      - ./data:/data
    restart: unless-stopped
```

---

#### 2. Monitoring
**Metrics:**
- Outbox backlog: `k0_outbox_pending_total{driver="embedding"/"fts"}`
- Worker throughput: `rate(k0_outbox_apply_total{outcome="success"}[5m])`
- Failure rate: `rate(k0_outbox_apply_total{outcome="quarantine"}[5m])`

**Dashboards:**
- `replay_throughput.json`: Outbox backlog panel
- `kernel_overview.json`: Outbox apply rate

---

#### 3. Troubleshooting

**High Outbox Backlog:**
1. Check worker logs for errors
2. Increase worker instances
3. Increase batch sizes
4. Monitor CPU/memory usage

**Embedding Worker Failures:**
1. Verify backend availability (OpenAI API, Ollama server)
2. Check API rate limits (OpenAI)
3. Validate model availability (sentence-transformers)
4. Review outbox quarantine entries

**FTS Worker Failures:**
1. Verify NLTK data downloaded (`punkt`, `stopwords`)
2. Check text encoding issues
3. Review keyword extraction logic

---

#### 4. Scaling
**Horizontal Scaling:**
- Run multiple worker instances
- Each instance polls outbox independently
- SQLite busy timeout handles contention

**Vertical Scaling:**
- Increase batch sizes
- Use GPU for embedding (sentence-transformers)
- Optimize NLTK processing (caching, parallelization)

---

### References

- **Design:** V1.4 Performance Optimization (commit latency reduction)
- **Outbox Pattern:** Chris Richardson, *Microservices Patterns* (Transactional Outbox)
- **Architecture:** `.github/copilot-instructions.md` (Section 3: Development Standards)
- **Storage Integration:** `k0/storage/README.md` (Outbox, WAL)
- **NLP Libraries:** NLTK documentation, sentence-transformers documentation
- **Embedding Backends:** OpenAI API docs, HuggingFace documentation, Ollama docs
