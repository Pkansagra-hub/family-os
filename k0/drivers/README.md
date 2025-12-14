# Drivers Module

## Overview

The **drivers** module implements the K0 Driver SPI (Service Provider Interface) for integrating external storage systems and indexing services. It provides pluggable adapters for SQLite, Neo4j, FAISS, FTS5, and local filesystem blob storage, enabling the outbox worker to fan out operations to specialized backends.

## Purpose

- **Storage Abstraction**: Unified interface for heterogeneous storage backends (relational, graph, vector, blob)
- **Outbox Integration**: Process async operations from K0 outbox to external systems
- **Alias Resolution**: Map logical storage aliases (st_epi, st_kg_dom, st_vector) to concrete driver implementations
- **Driver SPI Contract**: Standardized `apply(entry)` method for outbox workers
- **Factory Pattern**: `build_driver()` functions for dependency injection

## Architecture

The driver layer follows a **factory + adapter pattern**:

```text
Outbox Worker → AliasMap → Driver Factory → Concrete Driver → External System
                    ↓                              ↓
          (st_epi → sqlite)           (sqlite.py → SQLite DB)
          (st_kg_dom → neo4j_driver)  (neo4j_driver.py → Neo4j Graph)
          (st_vector → faiss)         (faiss.py → FAISS Index)
```

## Core Components

### 1. `alias_map.yaml` - Driver Alias Bindings

Maps logical storage aliases to concrete driver modules.

**Format:**

```yaml
aliases:
  st_epi: sqlite           # Episodic memory → SQLite
  st_sem: sqlite           # Semantic memory → SQLite
  st_ws: sqlite            # Working memory → SQLite
  st_fts: fts5             # Full-text search → FTS5
  st_vector: faiss         # Vector embeddings → FAISS
  st_emb: faiss            # Embedding index → FAISS
  st_kg_dom: neo4j_driver  # Knowledge graph → Neo4j
  st_blob: blob_localfs    # Blob storage → Local filesystem
  traffic-gen: sqlite      # Load testing driver
```

**Usage:**

- Outbox worker resolves `driver` alias to module name
- Dynamically imports driver module and calls `build_driver()`
- ADR reference: K0 README §7 (Driver SPI)

### 2. `alias_map.py` - Alias Resolution Utility

Loads and resolves driver aliases from `alias_map.yaml`.

**Class: `AliasMap`**

```python
@dataclass(slots=True)
class AliasMap:
    bindings: dict[str, str]

    @classmethod
    def from_file(cls, path: Path | str | None = None) -> "AliasMap":
        # Load alias_map.yaml and return AliasMap instance
        ...

    def resolve(self, alias: str) -> str:
        # Return driver module name for alias (e.g., "sqlite" for "st_epi")
        return self.bindings[alias]
```

**Example:**

```python
from k0.drivers import AliasMap

alias_map = AliasMap.from_file()
driver_module = alias_map.resolve("st_epi")  # Returns "sqlite"
```

### 3. `sqlite.py` - SQLite Driver (ACID Cohort)

Implements K0 Driver SPI for SQLite backend, handling ACID operations for WAL, receipts, outbox, and memory tables.

**Class: `SQLiteDriver`**

**Key Methods:**

- `connect()` - Establish connection with WAL mode and performance tuning
- `begin()` / `commit()` / `rollback()` - ACID transaction control
- `append(table, data)` - Insert row (returns lastrowid)
- `read(table, query)` - Query rows with WHERE filters
- `scan(table, limit, offset)` - Paginated table scan
- `execute(sql, params)` - Execute arbitrary SQL
- `close()` - Close connection
- `apply(entry: OutboxEntry)` - Driver SPI method (placeholder)

**Storage Responsibilities:**

- **K0 Infrastructure**: `st_wal`, `st_receipts`, `st_outbox`, `st_dlq`, `idem_ledger`, `st_devices`, `schema_registry`
- **Memory Tables**: `st_hipp_store`, `st_epi`, `st_sem`, `st_ws`, `st_proc`, `st_social`
- **Self-Model**: `self_traits`, `self_preferences`, `self_health`, `self_roles`
- **Directory**: `people`, `households`

**Configuration:**

- WAL mode: `PRAGMA journal_mode=WAL`
- Synchronous: `PRAGMA synchronous=NORMAL` (balance durability/performance)
- Busy timeout: `PRAGMA busy_timeout=5000` (retry on lock contention)
- Row factory: Dict-like row access

**Example:**

```python
from k0.drivers.sqlite import SQLiteDriver
from pathlib import Path

driver = SQLiteDriver(database_path=Path("k0_runtime.sqlite3"))
with driver:
    driver.append("st_epi", {"event_id": "evt_123", "payload": b"..."})
    rows = driver.read("st_epi", {"event_id": "evt_123"})
```

**Factory Function:**

```python
def build_driver() -> SQLiteDriver:
    import os
    db_path = Path(os.getenv("K0_DB_PATH", "/data/k0_kernel.db"))
    return SQLiteDriver(database_path=db_path)
```

### 4. `neo4j_driver.py` - Neo4j Knowledge Graph Driver

Implements K0 Driver SPI for Neo4j temporal graph storage (ADR-0081).

**Class: `Neo4jKGDriver`**

**Key Methods:**

- `connect()` - Establish Bolt protocol connection with connection pooling
- `close()` - Close connection and cleanup
- `apply(entry: OutboxEntry)` - Parse JSON payload and route to graph operations
- `query_relationships(node_id)` - Query relationships for P01 recall
- `find_path(source_id, target_id, max_depth)` - Shortest path BFS traversal

**Graph Operations (via `apply`):**

- **Node Creation**: `create_person`, `create_location`, `create_event`, `create_organization`, `create_thing`
- **Relationship Creation**: `create_relationship` with temporal properties (valid_from, valid_to, confidence)
- **Updates**: `update_node`, `update_relationship`
- **Deletions**: `delete_node` (cascade), `delete_relationship`

**Temporal Schema (ADR-0081a):**

- **Node Labels**: Person, Location, Event, Organization, Thing
- **Relationship Types**: 50+ types (PARENT_OF, FRIEND_OF, EMPLOYED_BY, LIVES_IN, etc.)
- **Temporal Properties**: `valid_from`, `valid_to`, `confidence`, `created_at`, `updated_at`

**Privacy Integration:**

- Privacy bands: GREEN (shareable), AMBER (personal), RED (sensitive)
- PII redaction for RED band entities
- Audit logging for sensitive operations

**Configuration:** See `k0/config/neo4j.yaml`

**Example:**

```python
from k0.drivers.neo4j_driver import Neo4jKGDriver

driver = Neo4jKGDriver(
    uri="neo4j://localhost:7687",
    username="neo4j",
    password="test-password",
)
with driver:
    # Create person node
    payload = {
        "operation": "create_person",
        "params": {
            "node_id": "person_123",
            "name": "Alice",
            "privacy_band": "AMBER",
        }
    }
    driver.apply(entry)  # Processes OutboxEntry with JSON payload

    # Query relationships
    relationships = driver.query_relationships("person_123")
```

**Factory Function:**

```python
def build_driver() -> Neo4jKGDriver:
    import os
    return Neo4jKGDriver(
        uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        username=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "test-password"),
    )
```

### 5. `faiss.py` - FAISS Vector Index Driver (Placeholder)

Placeholder for FAISS vector similarity search integration.

**Class: `FaissDriver`**

**Methods:**

- `apply(entry: OutboxEntry)` - Currently no-op (TODO: vector index updates)

**Future Implementation:**

- Insert/update embeddings in FAISS index
- Perform k-NN similarity search
- Integrate with embedding workers (async flow: text → embedding → FAISS)

**Factory Function:**

```python
def build_driver() -> FaissDriver:
    return FaissDriver()
```

### 6. `fts5.py` - FTS5 Full-Text Search Driver (Placeholder)

Placeholder for SQLite FTS5 full-text search index integration.

**Class: `FTS5Driver`**

**Methods:**

- `configure()` - Not implemented
- `apply(entry: OutboxEntry)` - Currently no-op (TODO: FTS5 index updates)

**Future Implementation:**

- Shadow indexing for full-text search
- Synchronize with memory tables (st_epi, st_sem)
- Query interface for text search

**Factory Function:**

```python
def build_driver() -> FTS5Driver:
    return FTS5Driver()
```

### 7. `blob_localfs.py` - Local Filesystem Blob Driver (Placeholder)

Placeholder for local filesystem blob storage.

**Class: `LocalBlobDriver`**

**Methods:**

- `store(payload, fingerprint)` - Not implemented
- `apply(entry: OutboxEntry)` - Currently no-op (TODO: blob storage operations)

**Future Implementation:**

- Store binary blobs (images, documents, audio) on local filesystem
- Deduplication via fingerprint (SHA-256)
- Integration with envelope attachments

**Factory Function:**

```python
def build_driver() -> LocalBlobDriver:
    return LocalBlobDriver(base_path=Path("/data/blobs"))
```

### 8. `sqlite_kg.py` - SQLite KG Driver (Empty Placeholder)

Empty file placeholder for potential SQLite-based knowledge graph implementation (alternative to Neo4j).

## Driver SPI Contract

All drivers must implement:

1. **`apply(entry: OutboxEntry) -> None`**
   - Process outbox entry (wal_pos, tenant_id, space_id, driver, op_kind, payload, fingerprint)
   - Parse payload and execute operation
   - Raise exceptions on failure (outbox worker handles retries/DLQ)

2. **Factory Function: `build_driver() -> DriverType`**
   - Return configured driver instance
   - Use environment variables for configuration
   - Enable dependency injection for outbox worker

3. **Optional Context Manager Support**
   - `__enter__` / `__exit__` for connection lifecycle
   - Example: `with driver: driver.apply(entry)`

## Integration with Outbox Worker

**Outbox → Driver Flow:**

1. Outbox worker polls `st_outbox` table for pending entries
2. Resolves `driver` alias via `AliasMap.resolve("st_epi")` → `"sqlite"`
3. Dynamically imports `k0.drivers.sqlite` and calls `build_driver()`
4. Invokes `driver.apply(entry)` with `OutboxEntry` payload
5. Marks entry as processed or retries on failure

**Example:**

```python
from k0.drivers import AliasMap
from k0.storage.outbox import OutboxStore
import importlib

alias_map = AliasMap.from_file()
outbox = OutboxStore()

entries = outbox.poll_pending(limit=10)
for entry in entries:
    # Resolve driver module
    driver_module_name = alias_map.resolve(entry.driver)  # "sqlite"
    driver_module = importlib.import_module(f"k0.drivers.{driver_module_name}")

    # Build driver instance
    driver = driver_module.build_driver()

    # Apply operation
    driver.apply(entry)
```

## Configuration

**Driver-Specific Config Files:**

- **Neo4j**: `k0/config/neo4j.yaml` (connection, schema, performance, privacy)
- **Embeddings**: `k0/config/embeddings.yml` (backends, worker settings)
- **SQLite**: Configured via `database.path` in `k0/config/kernel.yaml`

**Environment Variables:**

- `K0_DB_PATH` - SQLite database path (default: `/data/k0_kernel.db`)
- `NEO4J_URI` - Neo4j Bolt URI (default: `neo4j://localhost:7687`)
- `NEO4J_USER` / `NEO4J_PASSWORD` - Neo4j credentials
- `NEO4J_DATABASE` - Neo4j database name (default: `neo4j`)

## Error Handling

**Driver Exceptions:**

- Drivers raise standard exceptions (`sqlite3.Error`, `Neo4jError`, `ValueError`, `RuntimeError`)
- Outbox worker catches exceptions and:
  - Retries up to `max_retries` (default: 3)
  - Moves to DLQ after retry exhaustion
  - Logs errors with `cognitive_trace_id` for traceability

**Best Practices:**

- Log errors with context (operation, payload preview, trace_id)
- Use structured logging for observability
- Validate payload format before processing
- Fail fast on invalid operations

## Testing

**Unit Tests:**

```python
from k0.drivers.sqlite import SQLiteDriver

def test_sqlite_driver_append():
    driver = SQLiteDriver(database_path=Path(":memory:"))
    with driver:
        row_id = driver.append("test_table", {"col1": "val1"})
        assert row_id > 0
```

**Integration Tests:**

```python
from k0.drivers.neo4j_driver import Neo4jKGDriver
from k0.storage.outbox import OutboxEntry
import json

def test_neo4j_driver_create_person():
    driver = Neo4jKGDriver(uri="neo4j://localhost:7687", ...)
    entry = OutboxEntry(
        wal_pos=1,
        tenant_id="tenant_123",
        space_id="space_456",
        driver="neo4j_driver",
        op_kind="graph.create_person",
        payload=json.dumps({
            "operation": "create_person",
            "params": {"node_id": "person_123", "name": "Alice"}
        }).encode()
    )
    with driver:
        driver.apply(entry)
```

## Related Modules

- **k0.storage.outbox**: Outbox store and worker (consumers of driver SPI)
- **k0.config**: Driver configuration files (neo4j.yaml, embeddings.yml)
- **k0.uow**: Connection pooling for SQLite transactions
- **k0.obs**: Observability integration (cognitive_trace_id, metrics, logging)
- **k0.qos**: Scheduler for rate limiting outbox processing

## Related ADRs

- **K0 README §7**: Driver SPI & Alias Map architecture
- **ADR-0081**: K0 Knowledge Graph Architecture (Neo4j integration)
- **ADR-0081a**: Temporal Graph Schema Design (relationship types, temporal properties)
- **Migration 0006**: Memory tables (st_epi, st_sem, st_proc, st_social, st_hipp_store)
- **Migration 0007**: Core directory tables (people, households)

## Future Enhancements

**Planned Drivers:**

- **Redis Driver**: Caching layer for hot data
- **S3 Driver**: Cloud blob storage alternative to local filesystem
- **Elasticsearch Driver**: Advanced full-text search and analytics
- **PostgreSQL Driver**: Alternative to SQLite for multi-tenant deployments
- **Pinecone/Weaviate Driver**: Managed vector database alternatives to FAISS

**Enhanced Features:**

- **Connection Pooling**: Shared driver pools across workers
- **Circuit Breaker**: Fail fast on repeated driver failures
- **Batch Operations**: Apply multiple entries in single transaction
- **Metrics**: Driver-specific latency, throughput, error rate metrics
- **Health Checks**: Periodic driver connectivity validation
