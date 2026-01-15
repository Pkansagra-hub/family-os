# K0 PostgreSQL Migration Plan

**Status:** DRAFT
**Created:** 2025-12-22
**Target:** PostgreSQL 16+ / asyncpg / pgvector / Alembic / pgbouncer

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Files to Modify | 41 |
| Total Code Changes | 586 |
| New Files to Create | ~25-30 |
| Estimated Duration | 6-8 weeks |
| Phases | 5 |

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Database | PostgreSQL 16+ | Primary data store |
| Driver | asyncpg | Native async PostgreSQL driver |
| Vector | pgvector | Vector similarity search |
| Full-Text | tsvector + GIN | Full-text search |
| Migrations | Alembic | Schema versioning |
| Connection Pool | pgbouncer + asyncpg.Pool | Connection management |

---

# Current SQLite Wiring (To Be Replaced)

## How K0 Currently Uses SQLite

### Entry Points (Top-Level Wiring)

| Component | File | SQLite Integration |
|-----------|------|-------------------|
| **Global Connection Pool** | `k0/uow/connection_pool.py` | `SQLiteConnectionPool` class, `configure_pool()`, `get_pool()`, `connection_scope()` |
| **Dependency Injection** | `k0/kernel/dependencies.py` | `database_session()` → yields `sqlite3.Connection`, `ConnectionFactory` type alias |
| **App Bootstrap** | `k0/kernel/app.py` | Calls `configure_pool()` at startup, `shutdown_pool()` at shutdown |
| **Configuration** | `k0/kernel/config.py` | `DatabaseSettings.path` → `Path("k0_runtime.sqlite3")`, `fsync_mode` for WAL |
| **CLI** | `k0/cli/k0ctl.py` | Uses `configure_pool()`, `connection_scope()` |

### Connection Flow (Current)

```
App Startup (app.py)
    │
    ├── configure_pool(database_path) ─────────────────────┐
    │                                                      │
    │   SQLiteConnectionPool (connection_pool.py)          │
    │   ├── _path = Path to SQLite file                    │
    │   ├── _pragmas = {journal_mode: WAL, ...}            │
    │   ├── _available = list[sqlite3.Connection]          │
    │   └── acquire()/release() thread-safe pool           │
    │                                                      │
    ├── build_request_dependencies(settings)               │
    │   └── RequestDependencyProvider                      │
    │       ├── connection_factory = _default_connection_factory
    │       │   └── sqlite3.connect(db_path, ...)          │
    │       └── _database_session() → Iterator[Connection] │
    │                                                      │
    └── FastAPI dependency_overrides                       │
        └── database_session → _database_session           │
                                                           │
Routes/Syscalls                                            │
    │                                                      │
    ├── Depends(database_session) ─────────────────────────┘
    │   └── sqlite3.Connection
    │
    └── loop.run_in_executor(None, conn.execute, ...)
        └── Sync wrapper around blocking sqlite3 calls
```

### SQLite Configuration (kernel/config.py)

```python
class DatabaseSettings(BaseModel):
    path: Path = Field(default=Path("k0_runtime.sqlite3"))
    fsync_mode: Literal["strict", "wal_only", "disabled"] = "wal_only"
```

### PRAGMAs Applied (connection_pool.py, unit_of_work.py)

| PRAGMA | Value | PostgreSQL Equivalent |
|--------|-------|----------------------|
| `journal_mode` | WAL | N/A (native) |
| `synchronous` | NORMAL | `synchronous_commit = off` |
| `temp_store` | MEMORY | N/A |
| `foreign_keys` | ON | Default ON |
| `busy_timeout` | 5000-60000ms | Connection pool timeout |
| `wal_autocheckpoint` | 1000 | N/A |

---

# PostgreSQL Replacement Strategy

## New Connection Flow (Target)

```
App Startup (app.py)
    │
    ├── configure_pool(database_url) ─────────────────────┐
    │                                                      │
    │   asyncpg.Pool (db/pool.py) - NEW                    │
    │   ├── _dsn = PostgreSQL connection string            │
    │   ├── min_size / max_size                            │
    │   └── acquire()/release() native async              │
    │                                                      │
    ├── build_request_dependencies(settings)               │
    │   └── RequestDependencyProvider (MODIFIED)           │
    │       ├── pool: asyncpg.Pool                         │
    │       └── _database_session() → AsyncIterator[Conn]  │
    │                                                      │
    └── FastAPI dependency_overrides                       │
        └── database_session → _database_session           │
                                                           │
Routes/Syscalls                                            │
    │                                                      │
    ├── Depends(database_session) ─────────────────────────┘
    │   └── asyncpg.Connection (native async)
    │
    └── await conn.fetch(...) / await conn.execute(...)
        └── NO run_in_executor - direct async
```

## Configuration Changes

### Current (SQLite)

```python
# k0/kernel/config.py
class DatabaseSettings(BaseModel):
    path: Path = Field(default=Path("k0_runtime.sqlite3"))
    fsync_mode: Literal["strict", "wal_only", "disabled"]
```

### Target (PostgreSQL)

```python
# k0/config/postgres.py (NEW)
class PostgresSettings(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    database: str = Field(default="k0")
    user: str = Field(default="k0")
    password: str = Field(default="")  # From env/secrets
    min_pool_size: int = Field(default=2)
    max_pool_size: int = Field(default=10)
    ssl_mode: Literal["disable", "require", "verify-ca", "verify-full"] = "require"

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
```

---

# Files Cross-Reference (All 41 Files)

## Production Files to Modify

| # | Module | File | SQLite | Async | Exec | Total | In Plan? |
|---|--------|------|--------|-------|------|-------|----------|
| 1 | automation | `migrate.py` | 13 | 0 | 15 | 28 | ✅ Epic 5.2.1 |
| 2 | cli | `k0ctl.py` | 4 | 0 | 2 | 6 | ✅ Epic 5.2.5 |
| 3 | deploy | `provision_device.py` | 5 | 0 | 14 | 19 | ✅ Epic 5.2.1 |
| 4 | drivers | `sqlite.py` | 11 | 0 | 12 | 23 | ✅ Epic 4.1.1 |
| 5 | drivers | `embedding_queue.py` | 2 | 0 | 13 | 15 | ✅ Epic 4.1.3 |
| 6 | drivers | `faiss.py` | 3 | 0 | 8 | 11 | ✅ Epic 4.1.2 |
| 7 | drivers | `fts5.py` | 1 | 0 | 5 | 6 | ✅ Epic 4.1.2 |
| 8 | fabric | `fabric.py` | 0 | 5 | 0 | 5 | ✅ Epic 5.1.1 |
| 9 | fabric | `registry.py` | 0 | 2 | 0 | 2 | ✅ Epic 5.1.1 |
| 10 | gate | `schema_registry.py` | 21 | 0 | 19 | 40 | ✅ Epic 3.2.2 |
| 11 | gate | `minimal_gate.py` | 7 | 0 | 4 | 11 | ✅ Epic 3.2.2 |
| 12 | idem | `ledger.py` | 5 | 0 | 3 | 8 | ✅ Epic 5.2.3 |
| 13 | kernel | `syscalls.py` | 0 | 15 | 20 | 35 | ✅ Epic 4.2.1 |
| 14 | kernel | `dependencies.py` | 8 | 0 | 0 | 8 | ✅ Epic 4.2.2 |
| 15 | kernel | `app.py` | 1 | 1 | 0 | 2 | ✅ Epic 4.2.2 |
| 16 | policy | `retention_enforcer.py` | 9 | 0 | 10 | 19 | ✅ Epic 4.3.1 |
| 17 | policy | `acl_enforcer.py` | 9 | 0 | 6 | 15 | ✅ Epic 4.3.1 |
| 18 | ports | `command.py` | 2 | 0 | 13 | 15 | ✅ Epic 5.1.2 |
| 19 | ports | `query.py` | 0 | 1 | 1 | 2 | ✅ Epic 5.1.1 |
| 20 | query | `drivers.py` | 7 | 0 | 4 | 11 | ✅ Epic 4.3.2 |
| 21 | query | `service.py` | 0 | 0 | 1 | 1 | ✅ Epic 4.3.2 |
| 22 | receipts | `issuer.py` | 2 | 0 | 0 | 2 | ✅ Epic 5.2.3 |
| 23 | scripts | `sqlite_migration_audit.py` | 17 | 0 | 0 | 17 | ✅ Epic 5.3.2 (Archive) |
| 24 | scripts | `find_sync_wrappers.py` | 2 | 9 | 4 | 15 | ✅ Epic 5.3.2 (Archive) |
| 25 | scripts | `generate_migration_doc.py` | 6 | 9 | 0 | 15 | ✅ Epic 5.3.2 (Archive) |
| 26 | scripts | `traffic_generator.py` | 3 | 0 | 9 | 12 | ✅ Epic 5.3.1 |
| 27 | scripts | `filter_production_files.py` | 5 | 3 | 0 | 8 | ✅ Epic 5.3.2 (Archive) |
| 28 | scripts | `rebuild_faiss_index.py` | 4 | 0 | 4 | 8 | ✅ Epic 5.3.1 |
| 29 | scripts | `backfill_pending_embeddings.py` | 4 | 0 | 2 | 6 | ✅ Epic 5.3.1 |
| 30 | sse | `server.py` | 2 | 0 | 0 | 2 | ✅ Epic 5.2.4 |
| 31 | storage | `outbox.py` | 11 | 1 | 19 | 31 | ✅ Epic 3.1.1 |
| 32 | storage | `shard_promotion.py` | 19 | 0 | 12 | 31 | ✅ Epic 3.1.5 |
| 33 | storage | `wal.py` | 10 | 4 | 7 | 21 | ✅ Epic 3.1.1 |
| 34 | storage | `dlq.py` | 9 | 0 | 9 | 18 | ✅ Epic 3.1.2 |
| 35 | storage | `provisioning.py` | 9 | 0 | 6 | 15 | ✅ Epic 3.1.3 |
| 36 | storage | `replayer.py` | 6 | 0 | 9 | 15 | ✅ Epic 3.1.5 |
| 37 | storage | `obligations.py` | 7 | 0 | 6 | 13 | ✅ Epic 3.1.4 |
| 38 | storage | `snapshots.py` | 8 | 0 | 5 | 13 | ✅ Epic 3.1.3 |
| 39 | storage | `offsets.py` | 7 | 2 | 3 | 12 | ✅ Epic 3.1.4 |
| 40 | storage | `fts.py` | 5 | 0 | 6 | 11 | ✅ Epic 3.1.6 |
| 41 | storage | `fts5_indexer.py` | 3 | 0 | 7 | 10 | ✅ Epic 3.1.6 |
| 42 | storage | `receipts.py` | 6 | 1 | 3 | 10 | ✅ Epic 3.1.2 |
| 43 | sync | `crdt_merge_logger.py` | 7 | 0 | 3 | 10 | ✅ Epic 5.2.2 |
| 44 | uow | `unit_of_work.py` | 17 | 0 | 14 | 31 | ✅ Epic 3.2.1 |
| 45 | uow | `connection_pool.py` | 9 | 0 | 2 | 11 | ✅ Epic 3.2.1 |

**Total: 45/45 files covered (was 41, added cli/k0ctl.py, ports/command.py, query/service.py, storage/fts.py)**

## Additional Files Discovered (Now Included Above)

| File | Status | Epic |
|------|--------|------|
| `k0/kernel/config.py` | No SQLite patterns, but replace `DatabaseSettings` with `PostgresSettings` | Epic 1.1.1 |
| `k0/perf/runner.py` | 1 execute call, minimal changes | Epic 5.2.5 |

---

# Actual Database Schema (25 Tables)

> **Source:** `D:\familyos\k0_kernel_export.db` - Extracted from production database

## Database Statistics

| Category | Count |
|----------|-------|
| Total Tables | 25 (24 user + 1 internal) |
| Total Columns | ~400+ |
| Largest Table | st_hipp_events (91 columns) |
| FTS5 Virtual Tables | To be replaced with tsvector |
| Foreign Key Relationships | 15+ |

## Table Summary by Category

### Core Event Store (4 tables)

| Table | Columns | Indexes | Description |
|-------|---------|---------|-------------|
| st_wal | 22 | 9 | Write-Ahead Log (CDC events) |
| st_outbox | 14 | 3 | Transactional outbox pattern |
| st_dlq | 18 | 5 | Dead Letter Queue |
| st_receipts | 11 | 3 | Processing receipts |

### Domain Entities (3 tables)

| Table | Columns | Indexes | FKs | Description |
|-------|---------|---------|-----|-------------|
| households | 35 | 8 | 2 | Household records |
| people | 33 | 7 | 2 | Person records |
| st_relationships | 10 | 4 | 3 | Relationship graph |

### Device & Provisioning (2 tables)

| Table | Columns | Indexes | Description |
|-------|---------|---------|-------------|
| st_devices | 6 | 2 | Device provisioning |
| st_device_keys | 10 | 2 | Device key management (FK to st_devices) |

### Policy & Security (4 tables)

| Table | Columns | Description |
|-------|---------|-------------|
| st_acl | 11 | Access Control List |
| st_retention_policy | 11 | Data retention policies |
| st_archive_manifest | 9 | Archive tracking (FK to st_retention_policy) |
| idem_ledger | 5 | Idempotency key ledger |

### Pipeline Infrastructure (5 tables)

| Table | Columns | Description |
|-------|---------|-------------|
| st_offsets | 6 | Consumer group offsets (4-col PK) |
| st_obligation_log | 6 | Obligation tracking |
| st_pipeline_processed | 4 | Pipeline processing records |
| st_pipeline_status | 7 | Pipeline status tracking |
| st_pipeline_watermarks | 4 | Event watermarks |

### Hippocampus & AI/ML (4 tables)

| Table | Columns | Description |
|-------|---------|-------------|
| st_hipp_events | 91 | **MASSIVE** - Main hippocampus events table |
| st_embedding_queue | 17 | Embedding job queue (3 FKs) |
| st_vec | 13 | Vector embeddings (migrate to pgvector) |
| st_crdt_merge_log | 10 | CRDT conflict resolution log |

### Schema Management (2 tables)

| Table | Columns | Description |
|-------|---------|-------------|
| schema_registry | 8 | Schema versioning |
| schema_migrations | 3 | Alembic-like migration tracking |

### Internal (1 table - DROP)

| Table | Description |
|-------|-------------|
| sqlite_sequence | SQLite autoincrement tracking (not needed in PostgreSQL) |

## Migration Complexity by Table

| Complexity | Tables | Notes |
|------------|--------|-------|
| **HIGH** | st_hipp_events (91 cols), households (35 cols), people (33 cols) | Large tables, many indexes |
| **MEDIUM** | st_wal (22), st_dlq (18), st_embedding_queue (17) | Complex with FKs |
| **LOW** | Others (4-14 cols) | Standard migrations |

---

# Phase 1: Foundation & Infrastructure

## Milestone 1.1: PostgreSQL Infrastructure

### Epic 1.1.1: Database Setup & Configuration

#### Current State Analysis

| Aspect | Current Implementation | Location |
|--------|----------------------|----------|
| Docker Config | `Dockerfile` uses `python:3.11-slim`, installs `sqlite3` | [k0/deploy/Dockerfile](k0/deploy/Dockerfile) |
| Compose | `docker-compose.yml` has k0-kernel + neo4j services | [k0/deploy/docker-compose.yml](k0/deploy/docker-compose.yml) |
| Volume | `k0-data:/data` Docker volume for SQLite | docker-compose.yml L14 |
| DB Config | `DatabaseSettings` with `path`, `fsync_mode` | [k0/kernel/config.py](k0/kernel/config.py#L160-L185) |
| Env Vars | `K0_DB_PATH`, `K0_DB_WAL_MODE` | Dockerfile L52-53 |

#### Issue Details

---

**Issue 1.1.1.1: Create PostgreSQL Docker Configuration**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 2 hours |
| **Dependencies** | None |
| **Assignee** | TBD |

**Current State:**

- [k0/deploy/Dockerfile](k0/deploy/Dockerfile) installs `sqlite3` package (line 17)
- No PostgreSQL container exists

**Files to Create:**

| File | Purpose |
|------|---------|
| `k0/deploy/postgres/Dockerfile` | PostgreSQL 16 + pgvector image |
| `k0/deploy/postgres/init.sql` | Database/user creation, schema setup |

**Implementation:**

```dockerfile
# k0/deploy/postgres/Dockerfile
FROM postgres:16-alpine
RUN apk add --no-cache postgresql16-contrib
# pgvector installed via extensions.sql
COPY init.sql /docker-entrypoint-initdb.d/01-init.sql
COPY extensions.sql /docker-entrypoint-initdb.d/02-extensions.sql
```

```sql
-- k0/deploy/postgres/init.sql
CREATE DATABASE k0_kernel;
CREATE USER k0user WITH ENCRYPTED PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE k0_kernel TO k0user;
\c k0_kernel
GRANT ALL ON SCHEMA public TO k0user;
```

**Acceptance Criteria:**

- [ ] PostgreSQL 16 container builds successfully
- [ ] init.sql creates database and user
- [ ] Container health check passes
- [ ] Can connect with `psql` from host

---

**Issue 1.1.1.2: Create pgbouncer Configuration**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 1.5 hours |
| **Dependencies** | 1.1.1.1 |
| **Assignee** | TBD |

**Current State:**

- No connection pooler exists
- SQLite uses custom `SQLiteConnectionPool` in [k0/uow/connection_pool.py](k0/uow/connection_pool.py)

**Files to Create:**

| File | Purpose |
|------|---------|
| `k0/deploy/pgbouncer/pgbouncer.ini` | Connection pooler config |
| `k0/deploy/pgbouncer/userlist.txt` | Authentication credentials |

**Implementation:**

```ini
# k0/deploy/pgbouncer/pgbouncer.ini
[databases]
k0_kernel = host=postgres port=5432 dbname=k0_kernel

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 200
default_pool_size = 25
min_pool_size = 5
reserve_pool_size = 5
server_idle_timeout = 600
```

```txt
# k0/deploy/pgbouncer/userlist.txt
"k0user" "md5<hash>"
```

**Acceptance Criteria:**

- [ ] pgbouncer container starts successfully
- [ ] Connection pooling works (pool_mode=transaction)
- [ ] Can connect through pgbouncer:6432

---

**Issue 1.1.1.3: Extend docker-compose.yml for PostgreSQL**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 2 hours |
| **Dependencies** | 1.1.1.1, 1.1.1.2 |
| **Assignee** | TBD |

**Current State:**

- [k0/deploy/docker-compose.yml](k0/deploy/docker-compose.yml) has:
  - `k0-kernel` service (lines 5-42)
  - `neo4j` service (lines 44-78)
  - Volumes: `k0-data`, `neo4j-data`, `neo4j-logs`
  - Network: `k0-local` bridge

**File to Modify:** `k0/deploy/docker-compose.yml`

**Changes Required:**

1. Add `postgres` service:

```yaml
  postgres:
    build: ./postgres
    container_name: k0-postgres
    environment:
      POSTGRES_DB: k0_kernel
      POSTGRES_USER: k0user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U k0user -d k0_kernel"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - k0-local
```

1. Add `pgbouncer` service:

```yaml
  pgbouncer:
    image: edoburu/pgbouncer:1.21.0
    container_name: k0-pgbouncer
    volumes:
      - ./pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro
      - ./pgbouncer/userlist.txt:/etc/pgbouncer/userlist.txt:ro
    ports:
      - "6432:6432"
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - k0-local
```

1. Update `k0-kernel` service:
   - Remove `k0-data` volume mount
   - Add `depends_on: postgres`
   - Update env vars: `K0_DB_DSN=postgresql://k0user:changeme@pgbouncer:6432/k0_kernel`

2. Add volume: `postgres-data:`

**Acceptance Criteria:**

- [ ] `docker-compose up` starts all services
- [ ] k0-kernel connects to PostgreSQL via pgbouncer
- [ ] Health checks pass for all services
- [ ] Data persists in `postgres-data` volume

---

**Issue 1.1.1.4: Configure pgvector Extension**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 1 hour |
| **Dependencies** | 1.1.1.1 |
| **Assignee** | TBD |

**Current State:**

- Vector storage uses FAISS via [k0/drivers/faiss.py](k0/drivers/faiss.py)
- Embeddings stored in `st_vec` table (13 columns)
- Need to migrate to pgvector for native PostgreSQL vector ops

**File to Create:** `k0/deploy/postgres/extensions.sql`

**Implementation:**

```sql
-- k0/deploy/postgres/extensions.sql
-- Extensions for K0 kernel

-- Vector similarity search (embeddings)
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram similarity (fuzzy text search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Crypto functions (for hashing)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Verify extensions
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    RAISE EXCEPTION 'pgvector extension not installed';
  END IF;
END $$;
```

**Acceptance Criteria:**

- [ ] pgvector extension loads on container startup
- [ ] Can create `vector(768)` columns
- [ ] HNSW index creation works
- [ ] Cosine similarity queries execute

---

**Issue 1.1.1.5: Create PostgreSQL Environment Configuration**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 3 hours |
| **Dependencies** | None |
| **Assignee** | TBD |

**Current State:**

- [k0/kernel/config.py](k0/kernel/config.py#L160-L185) defines `DatabaseSettings`:

  ```python
  class DatabaseSettings(BaseModel):
      path: Path = Field(default=Path("k0_runtime.sqlite3"))
      fsync_mode: Literal["strict", "wal_only", "disabled"] = "wal_only"
  ```

- Used by `KernelSettings.database` (line ~350)
- No async connection string support

**File to Create:** `k0/config/postgres.py`

**Implementation:**

```python
# k0/config/postgres.py
"""PostgreSQL configuration for K0 kernel."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, field_validator


class PostgresSettings(BaseModel):
    """PostgreSQL connection settings with pgbouncer support."""

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="k0_kernel", min_length=1)
    user: str = Field(default="k0user", min_length=1)
    password: SecretStr = Field(default=SecretStr("changeme"))

    # Connection pool settings
    min_pool_size: int = Field(default=5, ge=1, le=100)
    max_pool_size: int = Field(default=25, ge=1, le=200)

    # SSL settings
    ssl_mode: str = Field(default="prefer")
    ssl_root_cert: str | None = Field(default=None)

    # pgvector settings
    vector_dimensions: int = Field(default=768)

    @property
    def dsn(self) -> str:
        """Build asyncpg-compatible DSN."""
        pwd = self.password.get_secret_value()
        return f"postgresql://{self.user}:{pwd}@{self.host}:{self.port}/{self.database}"

    @property
    def dsn_masked(self) -> str:
        """DSN with password masked for logging."""
        return f"postgresql://{self.user}:***@{self.host}:{self.port}/{self.database}"
```

**Files to Modify:**

| File | Change |
|------|--------|
| `k0/config/__init__.py` | Export `PostgresSettings` |
| `k0/kernel/config.py` | Replace `DatabaseSettings` with `PostgresSettings` import |

**Acceptance Criteria:**

- [ ] `PostgresSettings` validates all connection params
- [ ] DSN property generates valid asyncpg connection string
- [ ] Password is properly masked in logs
- [ ] SSL configuration works for production
- [ ] Environment variable override works (`K0_POSTGRES_*`)

---

### Epic 1.1.2: Alembic Migration Framework

#### Current State Analysis

| Aspect | Current Implementation | Location |
|--------|----------------------|----------|
| Migration Runner | Custom `apply_migrations()` in Python | [k0/automation/migrate.py](k0/automation/migrate.py) |
| Migration Format | Raw `.sql` files with `BEGIN`/`COMMIT` | [k0/contracts/sql/migrations/](k0/contracts/sql/migrations/) |
| Migration Count | 27 existing SQLite migrations (0001-0027) | migrations/ directory |
| Version Tracking | `schema_migrations` table | storage.sql |
| CLI | `k0ctl migrate` subcommand | [k0/cli/k0ctl.py](k0/cli/k0ctl.py#L78-L94) |

**Key Discovery:** Existing migration system is SQLite-specific with PRAGMA statements, CREATE TABLE IF NOT EXISTS patterns. Alembic will provide PostgreSQL-native migrations with proper upgrade/downgrade support.

#### Issue Details

---

**Issue 1.1.2.1: Initialize Alembic Structure**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 2 hours |
| **Dependencies** | 1.1.1.5 |
| **Assignee** | TBD |

**Current State:**

- `k0/db/` directory exists with `migrations/versions/` (empty `__pycache__/` only)
- No Alembic configuration present
- Migration tracking in `schema_migrations` table (3 columns: version, checksum, applied_ts)

**Files to Create:**

| File | Purpose |
|------|---------|
| `k0/db/alembic.ini` | Alembic configuration file |
| `k0/db/alembic/env.py` | Migration environment setup |
| `k0/db/alembic/versions/` | Migration scripts directory |

**Implementation:**

```ini
# k0/db/alembic.ini
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = .
version_path_separator = os

[alembic:exclude]
tables = spatial_ref_sys

[post_write_hooks]
hooks = ruff
ruff.type = exec
ruff.executable = ruff
ruff.options = format REVISION_SCRIPT_FILENAME

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

```python
# k0/db/alembic/env.py
"""Alembic migration environment for K0 kernel."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from k0.config.postgres import PostgresSettings
from k0.db.models import Base  # SQLAlchemy declarative base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from settings."""
    settings = PostgresSettings()
    return settings.dsn


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Acceptance Criteria:**

- [ ] `alembic --version` works in k0/db directory
- [ ] `alembic current` shows no revisions
- [ ] `alembic history` works (empty)
- [ ] env.py connects to PostgreSQL using `PostgresSettings`

---

**Issue 1.1.2.2: Create Migration Script Template**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 1 hour |
| **Dependencies** | 1.1.2.1 |
| **Assignee** | TBD |

**Current State:**

- No Alembic template exists
- Existing migrations use raw SQL in `.sql` files

**File to Create:** `k0/db/alembic/script.py.mako`

**Implementation:**

```mako
# k0/db/alembic/script.py.mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: Sequence[str] | None = ${repr(branch_labels)}
depends_on: Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply migration."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert migration."""
    ${downgrades if downgrades else "pass"}
```

**Acceptance Criteria:**

- [ ] `alembic revision -m "test"` generates valid Python file
- [ ] Generated file passes ruff formatting
- [ ] Type hints included in template
- [ ] Both upgrade() and downgrade() stubs present

---

**Issue 1.1.2.3: Create Base Revision (Empty)**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 1 hour |
| **Dependencies** | 1.1.2.2 |
| **Assignee** | TBD |

**Current State:**

- 27 SQLite migrations exist in `k0/contracts/sql/migrations/`
- Need fresh PostgreSQL baseline

**File to Create:** `k0/db/alembic/versions/0001_initial.py`

**Implementation:**

```python
# k0/db/alembic/versions/0001_initial.py
"""Initial baseline revision.

Revision ID: 0001
Revises: None
Create Date: 2024-XX-XX
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create alembic_version table (automatic).

    This is a placeholder revision to establish the migration baseline.
    Actual table creation begins with 0002_st_wal.py.
    """
    pass


def downgrade() -> None:
    """Drop all K0 tables.

    WARNING: This is destructive and removes all data.
    """
    # Intentionally empty - dropping baseline is not supported
    pass
```

**Acceptance Criteria:**

- [ ] `alembic upgrade head` applies revision 0001
- [ ] `alembic current` shows "0001 (head)"
- [ ] `alembic_version` table created in database

---

**Issue 1.1.2.4: Create Alembic CLI Wrapper**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 1.1.2.1 |
| **Assignee** | TBD |

**Current State:**

- [k0/cli/k0ctl.py](k0/cli/k0ctl.py#L78-L94) has `migrate` subcommand:

  ```python
  migrate_parser = subparsers.add_parser(
      "migrate", help="Apply storage schema migrations to the database"
  )
  migrate_parser.add_argument("--database", ...)
  migrate_parser.add_argument("--migrations-dir", ...)
  migrate_parser.add_argument("--dry-run", ...)
  ```

- Uses `apply_migrations()` from [k0/automation/migrate.py](k0/automation/migrate.py)

**File to Create:** `k0/cli/db_migrate.py`

**Implementation:**

```python
# k0/cli/db_migrate.py
"""Alembic CLI wrapper for K0 kernel migrations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def get_alembic_config() -> Config:
    """Get Alembic config pointing to k0/db/alembic.ini."""
    config_path = Path(__file__).parent.parent / "db" / "alembic.ini"
    if not config_path.exists():
        raise FileNotFoundError(f"Alembic config not found: {config_path}")
    return Config(str(config_path))


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Apply pending migrations."""
    cfg = get_alembic_config()
    revision = args.revision or "head"
    if args.dry_run:
        command.upgrade(cfg, revision, sql=True)
    else:
        command.upgrade(cfg, revision)
    return 0


def cmd_downgrade(args: argparse.Namespace) -> int:
    """Revert migrations."""
    cfg = get_alembic_config()
    command.downgrade(cfg, args.revision)
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    """Show current revision."""
    cfg = get_alembic_config()
    command.current(cfg, verbose=args.verbose)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Show migration history."""
    cfg = get_alembic_config()
    command.history(cfg, verbose=args.verbose)
    return 0


def cmd_revision(args: argparse.Namespace) -> int:
    """Create new migration."""
    cfg = get_alembic_config()
    command.revision(cfg, message=args.message, autogenerate=args.autogenerate)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for db-migrate CLI."""
    parser = argparse.ArgumentParser(
        prog="k0ctl db",
        description="K0 database migration commands (Alembic wrapper)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # upgrade
    up = subparsers.add_parser("upgrade", help="Apply migrations")
    up.add_argument("revision", nargs="?", default="head")
    up.add_argument("--dry-run", action="store_true")
    up.set_defaults(func=cmd_upgrade)

    # downgrade
    down = subparsers.add_parser("downgrade", help="Revert migrations")
    down.add_argument("revision", default="-1")
    down.set_defaults(func=cmd_downgrade)

    # current
    cur = subparsers.add_parser("current", help="Show current revision")
    cur.add_argument("-v", "--verbose", action="store_true")
    cur.set_defaults(func=cmd_current)

    # history
    hist = subparsers.add_parser("history", help="Show migration history")
    hist.add_argument("-v", "--verbose", action="store_true")
    hist.set_defaults(func=cmd_history)

    # revision
    rev = subparsers.add_parser("revision", help="Create new migration")
    rev.add_argument("-m", "--message", required=True)
    rev.add_argument("--autogenerate", action="store_true")
    rev.set_defaults(func=cmd_revision)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for db-migrate CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

**Files to Modify:**

| File | Change |
|------|--------|
| `k0/cli/k0ctl.py` | Add `db` subcommand that delegates to `db_migrate.py` |

**Acceptance Criteria:**

- [ ] `python -m k0.cli.db_migrate upgrade` works
- [ ] `python -m k0.cli.db_migrate current` shows revision
- [ ] `python -m k0.cli.db_migrate history` shows all migrations
- [ ] `k0ctl db upgrade` works (integrated with main CLI)
- [ ] Dry-run outputs SQL without executing

---

## Milestone 1.2: Core Database Layer

### Epic 1.2.1: Connection Pool Implementation

#### Current State Analysis

| Aspect | Current Implementation | Location |
|--------|----------------------|----------|
| Pool Class | `SQLiteConnectionPool` - thread-safe with metrics | [k0/uow/connection_pool.py](k0/uow/connection_pool.py#L42-L175) |
| Global Pool | `_pool` singleton with `configure_pool()` | [k0/uow/connection_pool.py](k0/uow/connection_pool.py#L320-L355) |
| Context Manager | `connection_scope()` yields `sqlite3.Connection` | [k0/uow/connection_pool.py](k0/uow/connection_pool.py#L358-L368) |
| Write Lock | `_WRITE_LOCK` asyncio.Lock for SQLite single-writer | [k0/uow/connection_pool.py](k0/uow/connection_pool.py#L20-L30) |
| DI Factory | `ConnectionFactory = Callable[[], sqlite3.Connection]` | [k0/kernel/dependencies.py](k0/kernel/dependencies.py#L68) |
| UoW Integration | Uses `connection_scope()` in `__aenter__` | [k0/uow/unit_of_work.py](k0/uow/unit_of_work.py#L106) |

**Key Discovery - Executor Wrappers:**
Storage layer uses `loop.run_in_executor()` to wrap sync SQLite calls:

- `k0/storage/offsets.py` - 2 calls (lines 48, 82)
- `k0/storage/wal.py` - 4 calls (lines 162, 182, 284, 297)
- `k0/storage/receipts.py` - 1 call (line 50)
- `k0/storage/outbox.py` - 1 call (line 65)

#### Issue Details

---

**Issue 1.2.1.1: Create asyncpg Connection Pool**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 4 hours |
| **Dependencies** | 1.1.1.5 (PostgresSettings) |
| **Assignee** | TBD |

**Current State:**

- `SQLiteConnectionPool` in [k0/uow/connection_pool.py](k0/uow/connection_pool.py#L42-L175):
  - Thread-safe with `threading.Condition`
  - `max_size=8` default
  - `acquire()` / `release()` / `close()`
  - Metrics: `sqlite_pool_connections_active`, `sqlite_pool_saturation_ratio`
  - PRAGMAs: journal_mode=WAL, synchronous=NORMAL, foreign_keys=1

**File to Create:** `k0/db/pool.py`

**Implementation:**

```python
# k0/db/pool.py
"""asyncpg connection pool for K0 kernel."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator

import asyncpg

if TYPE_CHECKING:
    from k0.config.postgres import PostgresSettings
    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoolStats:
    """Introspection data describing the current pool state."""

    size: int
    free_size: int
    used_size: int
    min_size: int
    max_size: int


class AsyncPgPool:
    """Managed asyncpg connection pool with metrics and health checks."""

    def __init__(
        self,
        settings: "PostgresSettings",
        *,
        metrics_exporter: "MetricsExporter | None" = None,
    ) -> None:
        self._settings = settings
        self._metrics = metrics_exporter
        self._pool: asyncpg.Pool | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Create the connection pool."""
        if self._initialized:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._settings.dsn,
            min_size=self._settings.min_pool_size,
            max_size=self._settings.max_pool_size,
            command_timeout=60.0,
            server_settings={
                "application_name": "k0_kernel",
                "timezone": "UTC",
            },
        )
        self._initialized = True
        logger.info(
            "PostgreSQL pool initialized",
            extra={"dsn": self._settings.dsn_masked},
        )

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a connection from the pool."""
        if self._pool is None:
            raise RuntimeError("Pool not initialized")

        async with self._pool.acquire() as conn:
            self._emit_metrics()
            yield conn

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results."""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute a query and return all results."""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Execute a query and return first row."""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> any:
        """Execute a query and return first column of first row."""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    def stats(self) -> PoolStats:
        """Get current pool statistics."""
        if self._pool is None:
            return PoolStats(0, 0, 0, 0, 0)
        return PoolStats(
            size=self._pool.get_size(),
            free_size=self._pool.get_idle_size(),
            used_size=self._pool.get_size() - self._pool.get_idle_size(),
            min_size=self._pool.get_min_size(),
            max_size=self._pool.get_max_size(),
        )

    def _emit_metrics(self) -> None:
        """Emit pool metrics."""
        if self._metrics is None or self._pool is None:
            return
        stats = self.stats()
        self._metrics.set_gauge("pg_pool_connections_active", float(stats.used_size))
        self._metrics.set_gauge(
            "pg_pool_saturation_ratio",
            stats.used_size / stats.max_size if stats.max_size > 0 else 0.0,
        )


# Global pool singleton
_pool: AsyncPgPool | None = None
_pool_lock = asyncio.Lock()


async def configure_pool(
    settings: "PostgresSettings",
    *,
    metrics_exporter: "MetricsExporter | None" = None,
) -> None:
    """Initialize the global asyncpg connection pool."""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
        _pool = AsyncPgPool(settings, metrics_exporter=metrics_exporter)
        await _pool.initialize()


async def shutdown_pool() -> None:
    """Close and discard the global pool."""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
        _pool = None


def get_pool() -> AsyncPgPool:
    """Return the configured pool or raise if missing."""
    if _pool is None:
        raise RuntimeError("Connection pool has not been configured")
    return _pool


__all__ = [
    "AsyncPgPool",
    "PoolStats",
    "configure_pool",
    "get_pool",
    "shutdown_pool",
]
```

**Acceptance Criteria:**

- [ ] `AsyncPgPool` creates connections with asyncpg
- [ ] Pool metrics emit to Prometheus (pg_pool_*)
- [ ] `configure_pool()` initializes global singleton
- [ ] `shutdown_pool()` cleanly closes connections
- [ ] Connection timeout works (60s default)

---

**Issue 1.2.1.2: Create Connection Context Manager**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical Path |
| **Estimate** | 2 hours |
| **Dependencies** | 1.2.1.1 |
| **Assignee** | TBD |

**Current State:**

- `connection_scope()` in [k0/uow/connection_pool.py](k0/uow/connection_pool.py#L358-L368):

  ```python
  @contextmanager
  def connection_scope(*, timeout: float | None = None) -> Iterator[sqlite3.Connection]:
      pool = get_pool()
      connection = pool.acquire(timeout=timeout)
      try:
          yield connection
      finally:
          pool.release(connection)
  ```

- Sync context manager yields `sqlite3.Connection`

**File to Create:** `k0/db/connection.py`

**Implementation:**

```python
# k0/db/connection.py
"""Async connection context managers for K0 kernel."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

import asyncpg

from .pool import get_pool

if TYPE_CHECKING:
    from asyncpg import Connection
    from asyncpg.transaction import Transaction


@asynccontextmanager
async def connection_scope() -> AsyncIterator[Connection]:
    """Yield a pooled PostgreSQL connection.

    Replaces the sync SQLite connection_scope() for async operations.
    Connection is automatically returned to pool on exit.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction_scope() -> AsyncIterator[tuple[Connection, Transaction]]:
    """Yield a connection with an active transaction.

    Automatically commits on success, rolls back on exception.
    Replaces the UoW pattern for simple transactional operations.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction() as tx:
            yield conn, tx


@asynccontextmanager
async def read_only_scope() -> AsyncIterator[Connection]:
    """Yield a read-only connection for queries.

    Sets transaction mode to READ ONLY for safety.
    Ideal for query operations that should never modify data.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("SET TRANSACTION READ ONLY")
        try:
            yield conn
        finally:
            # Connection returns to pool, transaction auto-rolls back
            pass


__all__ = [
    "connection_scope",
    "read_only_scope",
    "transaction_scope",
]
```

**Acceptance Criteria:**

- [ ] `connection_scope()` is async context manager
- [ ] `transaction_scope()` provides transaction + connection
- [ ] `read_only_scope()` sets READ ONLY mode
- [ ] All scopes properly return connections to pool

---

**Issue 1.2.1.3: Create PostgreSQL Type Converters**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 3 hours |
| **Dependencies** | 1.2.1.1 |
| **Assignee** | TBD |

**Current State:**

- SQLite uses `sqlite3.PARSE_DECLTYPES` for type detection
- JSON stored as TEXT columns
- UUIDs stored as TEXT
- Timestamps stored as ISO8601 TEXT strings
- Blobs stored as BLOB type

**File to Create:** `k0/db/types.py`

**Implementation:**

```python
# k0/db/types.py
"""PostgreSQL type converters for K0 kernel."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg


async def setup_type_codecs(conn: asyncpg.Connection) -> None:
    """Register custom type codecs on a connection.

    Called automatically when connections are created.
    Handles JSON, UUID, and timestamp conversions.
    """
    # JSON/JSONB codec - use built-in Python json
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


def text_to_uuid(value: str | None) -> uuid.UUID | None:
    """Convert SQLite TEXT UUID to Python UUID."""
    if value is None:
        return None
    return uuid.UUID(value)


def uuid_to_text(value: uuid.UUID | None) -> str | None:
    """Convert Python UUID to PostgreSQL-compatible format."""
    if value is None:
        return None
    return str(value)


def text_to_timestamp(value: str | None) -> datetime | None:
    """Convert SQLite ISO8601 TEXT to Python datetime.

    SQLite stores timestamps as: "2024-01-15T10:30:00.000000Z"
    PostgreSQL returns native datetime objects.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # Parse ISO8601 format
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def timestamp_to_text(value: datetime | None) -> str | None:
    """Convert Python datetime to ISO8601 TEXT for compatibility."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def bytes_to_bytea(value: bytes | None) -> bytes | None:
    """Convert Python bytes to PostgreSQL BYTEA (passthrough)."""
    return value


def record_to_dict(record: asyncpg.Record) -> dict[str, Any]:
    """Convert asyncpg Record to dictionary."""
    return dict(record)


def records_to_dicts(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
    """Convert list of asyncpg Records to list of dictionaries."""
    return [dict(r) for r in records]


__all__ = [
    "bytes_to_bytea",
    "record_to_dict",
    "records_to_dicts",
    "setup_type_codecs",
    "text_to_timestamp",
    "text_to_uuid",
    "timestamp_to_text",
    "uuid_to_text",
]
```

**Acceptance Criteria:**

- [ ] JSON/JSONB auto-encodes/decodes
- [ ] UUID TEXT ↔ native UUID conversion works
- [ ] Timestamp TEXT ↔ datetime conversion works
- [ ] Record → dict helper works for all tables
- [ ] Type codecs registered on pool init

---

**Issue 1.2.1.4: Deprecate SQLite Connection Pool**

| Field | Value |
|-------|-------|
| **Priority** | P2 - Medium |
| **Estimate** | 2 hours |
| **Dependencies** | 1.2.1.1, 1.2.1.2 |
| **Assignee** | TBD |

**Current State:**

- `SQLiteConnectionPool` class (125 lines)
- Global pool functions: `configure_pool()`, `shutdown_pool()`, `get_pool()`, `connection_scope()`
- Write lock: `get_write_lock()`
- Used by 41 files across k0/

**File to Modify:** `k0/uow/connection_pool.py`

**Changes Required:**

1. Add deprecation warnings:

```python
import warnings

def configure_pool(...) -> None:
    """Initialise the global SQLite connection pool.

    .. deprecated:: 2.0.0
        Use `k0.db.pool.configure_pool()` for PostgreSQL instead.
    """
    warnings.warn(
        "SQLite connection pool is deprecated. Use k0.db.pool for PostgreSQL.",
        DeprecationWarning,
        stacklevel=2,
    )
    # existing implementation...
```

1. Add shim functions for migration period:

```python
# Migration shim - redirects to new PostgreSQL pool
async def get_async_pool():
    """Get asyncpg pool (migration shim)."""
    from k0.db.pool import get_pool
    return get_pool()
```

1. Update `__all__` to export deprecation notice

**Acceptance Criteria:**

- [ ] Deprecation warnings emit when using SQLite pool
- [ ] Shim functions redirect to new pool
- [ ] Existing tests still pass (with warnings)
- [ ] No runtime breaks during migration

---

**Issue 1.2.1.5: Configure Pool for pgbouncer Compatibility (RISK MITIGATION)**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical |
| **Estimate** | 2 hours |
| **Dependencies** | 1.2.1.1 |
| **Risk** | HIGH - Prepared statements + pgbouncer conflict |
| **Assignee** | TBD |

**Problem Statement:**

`asyncpg` uses prepared statements by default for performance. When using `pgbouncer` in `pool_mode = transaction`, connections are reused aggressively across sessions. Prepared statements are **connection-local** in PostgreSQL, so when pgbouncer reassigns a connection, prepared statements from previous sessions don't exist, causing:

```
asyncpg.exceptions.InvalidSQLStatementNameError: prepared statement "..." does not exist
```

**Decision:** Disable prepared statement caching in asyncpg.

**Trade-off:** ~10-15% performance overhead vs prepared statements, but zero pgbouncer conflicts.

**File to Modify:** `k0/db/pool.py`

**Implementation:**

```python
# k0/db/pool.py - In AsyncPgPool.initialize()
async def initialize(self) -> None:
    """Create the connection pool with pgbouncer-compatible settings."""
    if self._initialized:
        return

    self._pool = await asyncpg.create_pool(
        dsn=self._settings.dsn,
        min_size=self._settings.min_pool_size,
        max_size=self._settings.max_pool_size,
        command_timeout=60.0,
        # CRITICAL: Disable prepared statement caching for pgbouncer compatibility
        statement_cache_size=0,
        max_cached_statement_lifetime=0,
        server_settings={
            "application_name": "k0_kernel",
            "timezone": "UTC",
        },
    )
    self._initialized = True
```

**Validation Test:**

```python
# tests/k0/db/test_pgbouncer_compat.py
import asyncio
import pytest
from k0.db.pool import create_pool, get_pool

@pytest.mark.asyncio
async def test_prepared_statement_disabled():
    """Verify no prepared statement errors under pgbouncer.

    Simulates aggressive connection reuse by running 100 concurrent queries.
    If statement_cache_size is not 0, this will fail with
    InvalidSQLStatementNameError under pgbouncer transaction mode.
    """
    pool = get_pool()

    async def query():
        async with pool.acquire() as conn:
            # Same query executed many times should not use prepared statements
            await conn.fetch("SELECT 1 AS test_value")

    # Run 100 concurrent queries to trigger connection reuse
    await asyncio.gather(*[query() for _ in range(100)])
    # Should complete without InvalidSQLStatementNameError


@pytest.mark.asyncio
async def test_pool_stats_show_cache_disabled():
    """Verify statement cache is disabled in pool config."""
    pool = get_pool()
    # asyncpg.Pool doesn't expose cache size directly, but we can verify
    # by checking that repeated queries don't create prepared statements
    async with pool.acquire() as conn:
        # This should not create a prepared statement
        await conn.fetch("SELECT 1")
        await conn.fetch("SELECT 1")
        # No assertion needed - if cache were enabled and pgbouncer
        # reassigned the connection, subsequent tests would fail
```

**Acceptance Criteria:**

- [ ] `statement_cache_size=0` in pool configuration
- [ ] `max_cached_statement_lifetime=0` in pool configuration
- [ ] Concurrent query test passes (100+ queries)
- [ ] No `InvalidSQLStatementNameError` in CI with pgbouncer
- [ ] Performance benchmark shows acceptable overhead (<15%)

---

### Epic 1.2.2: Query Builder Abstraction

#### Current State Analysis

| Aspect | Current Implementation | Location |
|--------|----------------------|----------|
| Query Style | Raw SQL with `?` placeholders | Throughout k0/storage/ |
| Cursor Pattern | `cursor.execute(sql, params)` | All storage modules |
| Parameter Style | Tuple positional `(value1, value2)` | SQLite standard |
| Prepared Statements | None (SQLite doesn't cache) | N/A |

**Key Differences SQLite → PostgreSQL:**

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Placeholders | `?` positional | `$1, $2` numbered |
| Returning | Not supported | `RETURNING *` clause |
| Upsert | `INSERT OR REPLACE` | `INSERT ... ON CONFLICT` |
| JSON Access | `json_extract()` | `->`, `->>` operators |

#### Issue Details

---

**Issue 1.2.2.1: Create Base Query Builder**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 4 hours |
| **Dependencies** | 1.2.1.1 |
| **Assignee** | TBD |

**Current State:**

- Raw SQL queries throughout storage layer
- Example from [k0/storage/wal.py](k0/storage/wal.py):

  ```python
  cursor.execute(
      "INSERT INTO st_wal (...) VALUES (?, ?, ?, ...)",
      (entry.tenant_id, entry.space_id, ...)
  )
  ```

**File to Create:** `k0/db/query.py`

**Implementation:**

```python
# k0/db/query.py
"""Query builder utilities for PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryBuilder:
    """Fluent query builder with PostgreSQL $N parameter style."""

    _parts: list[str] = field(default_factory=list)
    _params: list[Any] = field(default_factory=list)
    _param_index: int = field(default=0)

    def select(self, *columns: str) -> "QueryBuilder":
        """Add SELECT clause."""
        cols = ", ".join(columns) if columns else "*"
        self._parts.append(f"SELECT {cols}")
        return self

    def from_table(self, table: str) -> "QueryBuilder":
        """Add FROM clause."""
        self._parts.append(f"FROM {table}")
        return self

    def where(self, condition: str, *values: Any) -> "QueryBuilder":
        """Add WHERE clause with parameters."""
        # Replace ? with $N style
        formatted = self._format_params(condition, values)
        if any(p.startswith("WHERE") for p in self._parts):
            self._parts.append(f"AND {formatted}")
        else:
            self._parts.append(f"WHERE {formatted}")
        return self

    def insert(self, table: str, **columns: Any) -> "QueryBuilder":
        """Build INSERT statement."""
        cols = ", ".join(columns.keys())
        placeholders = ", ".join(
            f"${self._next_param(v)}" for v in columns.values()
        )
        self._parts.append(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})")
        return self

    def returning(self, *columns: str) -> "QueryBuilder":
        """Add RETURNING clause."""
        cols = ", ".join(columns) if columns else "*"
        self._parts.append(f"RETURNING {cols}")
        return self

    def on_conflict(self, columns: str, action: str = "DO NOTHING") -> "QueryBuilder":
        """Add ON CONFLICT clause for upsert."""
        self._parts.append(f"ON CONFLICT ({columns}) {action}")
        return self

    def order_by(self, *columns: str, desc: bool = False) -> "QueryBuilder":
        """Add ORDER BY clause."""
        direction = "DESC" if desc else "ASC"
        cols = ", ".join(f"{c} {direction}" for c in columns)
        self._parts.append(f"ORDER BY {cols}")
        return self

    def limit(self, n: int) -> "QueryBuilder":
        """Add LIMIT clause."""
        self._parts.append(f"LIMIT {n}")
        return self

    def offset(self, n: int) -> "QueryBuilder":
        """Add OFFSET clause."""
        self._parts.append(f"OFFSET {n}")
        return self

    def _next_param(self, value: Any) -> int:
        """Add parameter and return its index."""
        self._param_index += 1
        self._params.append(value)
        return self._param_index

    def _format_params(self, template: str, values: tuple[Any, ...]) -> str:
        """Replace ? placeholders with $N style."""
        result = template
        for value in values:
            idx = self._next_param(value)
            result = result.replace("?", f"${idx}", 1)
        return result

    def build(self) -> tuple[str, list[Any]]:
        """Return the query string and parameters."""
        return " ".join(self._parts), self._params

    def __str__(self) -> str:
        """Return query string for debugging."""
        return " ".join(self._parts)


def convert_sqlite_query(sql: str, params: tuple) -> tuple[str, list]:
    """Convert SQLite ? params to PostgreSQL $N style.

    Args:
        sql: SQL with ? placeholders
        params: Tuple of parameter values

    Returns:
        Tuple of (converted_sql, params_list)

    Example:
        >>> convert_sqlite_query("SELECT * FROM t WHERE a=? AND b=?", (1, 2))
        ("SELECT * FROM t WHERE a=$1 AND b=$2", [1, 2])
    """
    result = sql
    for i, _ in enumerate(params, start=1):
        result = result.replace("?", f"${i}", 1)
    return result, list(params)


__all__ = [
    "QueryBuilder",
    "convert_sqlite_query",
]
```

**Acceptance Criteria:**

- [ ] `QueryBuilder` generates valid PostgreSQL SQL
- [ ] `$1, $2` parameter style used correctly
- [ ] `convert_sqlite_query()` converts existing queries
- [ ] RETURNING clause supported
- [ ] ON CONFLICT upsert supported

---

**Issue 1.2.2.2: Create Prepared Statement Cache**

| Field | Value |
|-------|-------|
| **Priority** | P2 - Medium |
| **Estimate** | 3 hours |
| **Dependencies** | 1.2.1.1, 1.2.2.1 |
| **Assignee** | TBD |

**Current State:**

- SQLite doesn't support server-side prepared statements
- Each query is parsed fresh
- No query plan caching

**File to Create:** `k0/db/statements.py`

**Implementation:**

```python
# k0/db/statements.py
"""Prepared statement cache for PostgreSQL."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class PreparedStatement:
    """Cached prepared statement reference."""

    name: str
    sql: str
    prepared: bool = False


class StatementCache:
    """LRU cache for prepared statements.

    PostgreSQL prepared statements are connection-scoped.
    This cache tracks which statements are prepared on each connection.
    """

    def __init__(self, max_size: int = 100) -> None:
        self._max_size = max_size
        self._statements: dict[str, PreparedStatement] = {}
        self._access_order: list[str] = []

    def get_name(self, sql: str) -> str:
        """Get or create a statement name for the SQL."""
        # Hash the SQL to create a stable name
        sql_hash = hashlib.sha256(sql.encode()).hexdigest()[:16]
        name = f"k0_stmt_{sql_hash}"

        if name not in self._statements:
            self._statements[name] = PreparedStatement(name=name, sql=sql)
            self._access_order.append(name)
            self._evict_if_needed()
        else:
            # Move to end (most recently used)
            self._access_order.remove(name)
            self._access_order.append(name)

        return name

    async def prepare(
        self,
        conn: "asyncpg.Connection",
        sql: str,
    ) -> "asyncpg.PreparedStatement":
        """Get or prepare a statement on the connection."""
        name = self.get_name(sql)
        stmt = self._statements[name]

        # Note: asyncpg handles prepared statement caching internally
        # This is mainly for tracking and metrics
        return await conn.prepare(sql)

    def _evict_if_needed(self) -> None:
        """Evict oldest statements if cache is full."""
        while len(self._statements) > self._max_size:
            oldest = self._access_order.pop(0)
            del self._statements[oldest]
            logger.debug(f"Evicted prepared statement: {oldest}")

    def clear(self) -> None:
        """Clear all cached statements."""
        self._statements.clear()
        self._access_order.clear()

    @property
    def size(self) -> int:
        """Current cache size."""
        return len(self._statements)


# Global statement cache
_cache = StatementCache()


def get_statement_cache() -> StatementCache:
    """Get the global statement cache."""
    return _cache


__all__ = [
    "PreparedStatement",
    "StatementCache",
    "get_statement_cache",
]
```

**Acceptance Criteria:**

- [ ] Statement names generated from SQL hash
- [ ] LRU eviction when cache full
- [ ] Prepared statements reused across queries
- [ ] Cache clearable for testing

---

**Issue 1.2.2.3: Create Parameter Binding Utilities**

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 1.2.2.1 |
| **Assignee** | TBD |

**Current State:**

- SQLite uses tuple positional params: `(val1, val2)`
- Some places use dict params with `:name` style
- No type coercion for PostgreSQL-specific types

**File to Create:** `k0/db/params.py`

**Implementation:**

```python
# k0/db/params.py
"""Parameter binding utilities for PostgreSQL."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


def bind_params(*args: Any) -> list[Any]:
    """Convert parameters to PostgreSQL-compatible types.

    Handles:
    - UUID objects → str (PostgreSQL handles conversion)
    - datetime → ensures timezone aware
    - dict/list → JSON string for JSONB columns
    - None → NULL
    - bytes → passthrough for BYTEA
    """
    result = []
    for arg in args:
        result.append(_convert_param(arg))
    return result


def _convert_param(value: Any) -> Any:
    """Convert a single parameter value."""
    if value is None:
        return None

    if isinstance(value, uuid.UUID):
        # asyncpg handles UUID natively
        return value

    if isinstance(value, datetime):
        # Ensure timezone-aware
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, (dict, list)):
        # For JSONB columns - asyncpg handles this natively
        # but explicit conversion ensures consistency
        return value

    if isinstance(value, bytes):
        # BYTEA - passthrough
        return value

    if isinstance(value, bool):
        # PostgreSQL BOOLEAN
        return value

    # Default: return as-is
    return value


def named_to_positional(
    sql: str,
    params: Mapping[str, Any],
) -> tuple[str, list[Any]]:
    """Convert :name style params to $N positional.

    Args:
        sql: SQL with :name placeholders
        params: Dict of name → value

    Returns:
        Tuple of (converted_sql, ordered_params)

    Example:
        >>> named_to_positional(
        ...     "SELECT * FROM t WHERE a=:foo AND b=:bar",
        ...     {"foo": 1, "bar": 2}
        ... )
        ("SELECT * FROM t WHERE a=$1 AND b=$2", [1, 2])
    """
    result_sql = sql
    result_params = []
    param_index = 0

    # Find all :name patterns
    import re
    pattern = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")

    def replace_param(match: re.Match) -> str:
        nonlocal param_index
        name = match.group(1)
        if name not in params:
            raise KeyError(f"Missing parameter: {name}")
        param_index += 1
        result_params.append(_convert_param(params[name]))
        return f"${param_index}"

    result_sql = pattern.sub(replace_param, sql)
    return result_sql, result_params


def bulk_params(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> list[tuple]:
    """Prepare parameters for bulk insert.

    Args:
        rows: Sequence of row dicts
        columns: Column names in order

    Returns:
        List of tuples for executemany

    Example:
        >>> bulk_params(
        ...     [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        ...     ["a", "b"]
        ... )
        [(1, 2), (3, 4)]
    """
    result = []
    for row in rows:
        values = tuple(_convert_param(row.get(col)) for col in columns)
        result.append(values)
    return result


__all__ = [
    "bind_params",
    "bulk_params",
    "named_to_positional",
]
```

**Acceptance Criteria:**

- [ ] `bind_params()` handles all K0 data types
- [ ] `named_to_positional()` converts :name → $N
- [ ] `bulk_params()` prepares batch inserts
- [ ] UUID/datetime/JSON properly converted
- [ ] None → NULL handling correct

---

# Phase 2: Schema Migration

## Milestone 2.1: Core Table Migrations

### Epic 2.1.1: Event Store Schema (Core WAL/Outbox)

---

**Issue 2.1.1.1: Migrate st_wal Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0002_st_wal.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 4 hours |
| **Dependencies** | 0001_initial.py |

**Columns (22 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `pos` | INTEGER | BIGSERIAL | PRIMARY KEY |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `topic` | TEXT | VARCHAR(128) | NOT NULL |
| `envelope_json` | TEXT | JSONB | NOT NULL |
| `body` | BLOB | BYTEA | |
| `payload_sha256` | TEXT | CHAR(64) | |
| `schema_uri` | TEXT | VARCHAR(512) | |
| `schema_version` | TEXT | VARCHAR(32) | |
| `idem_key` | TEXT | VARCHAR(128) | |
| `device_id` | TEXT | VARCHAR(64) | |
| `commit_ts` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `redacted_body_json` | TEXT | JSONB | |
| `envelope_id` | TEXT | UUID | |
| `content_type` | TEXT | VARCHAR(64) | |
| `encryption_scheme` | TEXT | VARCHAR(32) | |
| `envelope_sha256` | TEXT | CHAR(64) | |
| `ingested_at` | TEXT | TIMESTAMPTZ | DEFAULT NOW() |
| `clock_skew_ms` | INTEGER | INTEGER | |
| `policy_stamp_json` | TEXT | JSONB | |
| `location_geohash` | TEXT | VARCHAR(12) | |
| `location_precision_m` | REAL | REAL | |

**Indexes (9 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_wal_tenant_space` | (tenant_id, space_id) | BTREE |
| `ix_st_wal_topic` | (topic) | BTREE |
| `ix_st_wal_idem_key` | (idem_key) | BTREE UNIQUE WHERE idem_key IS NOT NULL |
| `ix_st_wal_device_id` | (device_id) | BTREE |
| `ix_st_wal_commit_ts` | (commit_ts) | BTREE |
| `ix_st_wal_envelope_id` | (envelope_id) | BTREE |
| `ix_st_wal_schema_uri` | (schema_uri) | BTREE |
| `ix_st_wal_payload_sha256` | (payload_sha256) | BTREE |
| `ix_st_wal_geohash` | (location_geohash) | BTREE |

---

**Issue 2.1.1.2: Migrate st_outbox Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0003_st_outbox.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 3 hours |
| **Dependencies** | 0002_st_wal.py |

**Columns (14 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `id` | INTEGER | BIGSERIAL | PRIMARY KEY |
| `wal_pos` | INTEGER | BIGINT | NOT NULL |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `driver` | TEXT | VARCHAR(64) | NOT NULL |
| `op_kind` | TEXT | VARCHAR(32) | NOT NULL |
| `payload` | BLOB | BYTEA | NOT NULL |
| `fingerprint` | TEXT | CHAR(64) | |
| `requeue_seq` | INTEGER | INTEGER | DEFAULT 0 |
| `retries` | INTEGER | SMALLINT | DEFAULT 0 |
| `last_error` | TEXT | TEXT | |
| `next_attempt_ts` | TEXT | TIMESTAMPTZ | |
| `backoff_exp` | INTEGER | SMALLINT | DEFAULT 0 |
| `status` | TEXT | VARCHAR(16) | DEFAULT 'pending' |

**Indexes (3 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_outbox_status_next` | (status, next_attempt_ts) | BTREE |
| `ix_st_outbox_driver` | (driver) | BTREE |
| `ix_st_outbox_wal_pos` | (wal_pos) | BTREE |

---

**Issue 2.1.1.3: Migrate st_dlq Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0004_st_dlq.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 3 hours |
| **Dependencies** | 0002_st_wal.py |

**Columns (18 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `id` | INTEGER | BIGSERIAL | PRIMARY KEY |
| `wal_pos` | INTEGER | BIGINT | NOT NULL |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `driver` | TEXT | VARCHAR(64) | NOT NULL |
| `op_kind` | TEXT | VARCHAR(32) | NOT NULL |
| `fingerprint` | TEXT | CHAR(64) | |
| `payload` | BLOB | BYTEA | NOT NULL |
| `reason` | TEXT | TEXT | |
| `retries` | INTEGER | SMALLINT | DEFAULT 0 |
| `requeue_seq` | INTEGER | INTEGER | DEFAULT 0 |
| `first_failure_ts` | TEXT | TIMESTAMPTZ | NOT NULL |
| `last_failure_ts` | TEXT | TIMESTAMPTZ | NOT NULL |
| `state` | TEXT | VARCHAR(16) | DEFAULT 'dead' |
| `next_attempt_ts` | TEXT | TIMESTAMPTZ | |
| `backoff_exp` | INTEGER | SMALLINT | DEFAULT 0 |
| `error_kind` | TEXT | VARCHAR(64) | |
| `error_fingerprint` | TEXT | CHAR(64) | |

**Indexes (4 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_dlq_state` | (state) | BTREE |
| `ix_st_dlq_driver` | (driver) | BTREE |
| `ix_st_dlq_error_kind` | (error_kind) | BTREE |
| `ix_st_dlq_wal_pos` | (wal_pos) | BTREE |

---

**Issue 2.1.1.4: Migrate st_receipts Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0005_st_receipts.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 2 hours |
| **Dependencies** | 0002_st_wal.py |

**Columns (11 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `receipt_id` | TEXT | UUID | PRIMARY KEY |
| `idem_key` | TEXT | VARCHAR(128) | NOT NULL |
| `wal_pos` | INTEGER | BIGINT | NOT NULL |
| `commit_ts` | TEXT | TIMESTAMPTZ | NOT NULL |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `device_id` | TEXT | VARCHAR(64) | |
| `mls_group_id` | TEXT | VARCHAR(64) | |
| `key_version` | INTEGER | INTEGER | |
| `device_sig` | TEXT | TEXT | |
| `manifest_fingerprint` | TEXT | CHAR(64) | |

**Indexes (3 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_receipts_idem_key` | (idem_key) | BTREE |
| `ix_st_receipts_wal_pos` | (wal_pos) | BTREE |
| `ix_st_receipts_tenant_space` | (tenant_id, space_id) | BTREE |

---

### Epic 2.1.2: Metadata Schema (Registry/Offsets)

---

**Issue 2.1.2.1: Migrate schema_registry Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0006_schema_registry.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (8 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `schema_uri` | TEXT | VARCHAR(512) | PRIMARY KEY (composite) |
| `version` | TEXT | VARCHAR(32) | PRIMARY KEY (composite) |
| `sha256` | TEXT | CHAR(64) | NOT NULL |
| `status` | TEXT | VARCHAR(16) | DEFAULT 'active' |
| `operator_id` | TEXT | VARCHAR(64) | |
| `blocked_ts` | TEXT | TIMESTAMPTZ | |
| `blocked_reason` | TEXT | TEXT | |
| `unblocked_ts` | TEXT | TIMESTAMPTZ | |

**Indexes (1 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_schema_registry_sha256` | (sha256) | BTREE |

---

**Issue 2.1.2.2: Migrate schema_migrations Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0007_schema_migrations.py` |
| **Priority** | P1 - High |
| **Estimate** | 1 hour |
| **Dependencies** | 0001_initial.py |

**Note:** This table tracks SQLite migrations. For PostgreSQL, Alembic's `alembic_version` table replaces this. Create for backward compatibility only.

**Columns (3 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `version` | TEXT | VARCHAR(32) | PRIMARY KEY |
| `checksum` | TEXT | CHAR(64) | NOT NULL |
| `applied_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

---

**Issue 2.1.2.3: Migrate st_offsets Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0008_st_offsets.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (6 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `subscriber_id` | TEXT | VARCHAR(128) | PRIMARY KEY (composite) |
| `topic` | TEXT | VARCHAR(128) | PRIMARY KEY (composite) |
| `space_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `tenant_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `offset` | INTEGER | BIGINT | NOT NULL DEFAULT 0 |
| `updated_ts` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Indexes (1 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_offsets_updated` | (updated_ts) | BTREE |

---

**Issue 2.1.2.4: Migrate st_obligation_log Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0009_st_obligation_log.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0002_st_wal.py |

**Columns (7 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `id` | INTEGER | BIGSERIAL | PRIMARY KEY |
| `wal_pos` | INTEGER | BIGINT | NOT NULL, FK → st_wal.pos |
| `obligation` | TEXT | VARCHAR(64) | NOT NULL |
| `details_json` | TEXT | JSONB | |
| `commit_ts` | TEXT | TIMESTAMPTZ | NOT NULL |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_obligation_wal` | wal_pos | st_wal(pos) |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_obligation_wal_pos` | (wal_pos) | BTREE |
| `ix_st_obligation_tenant` | (tenant_id, space_id) | BTREE |

---

### Epic 2.1.3: Policy & Security Schema

---

**Issue 2.1.3.1: Migrate st_retention_policy Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0010_st_retention_policy.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (11 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `policy_id` | TEXT | UUID | PRIMARY KEY |
| `policy_name` | TEXT | VARCHAR(128) | NOT NULL UNIQUE |
| `resource_type` | TEXT | VARCHAR(64) | NOT NULL |
| `privacy_band` | TEXT | VARCHAR(16) | NOT NULL |
| `retention_days` | INTEGER | INTEGER | NOT NULL |
| `archive_enabled` | INTEGER | BOOLEAN | DEFAULT FALSE |
| `archive_after_days` | INTEGER | INTEGER | |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `created_by` | TEXT | VARCHAR(64) | |
| `updated_at` | TEXT | TIMESTAMPTZ | |
| `enabled` | INTEGER | BOOLEAN | DEFAULT TRUE |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_retention_resource` | (resource_type) | BTREE |
| `ix_st_retention_band` | (privacy_band) | BTREE |

---

**Issue 2.1.3.2: Migrate st_acl Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0011_st_acl.py` |
| **Priority** | P1 - High |
| **Estimate** | 3 hours |
| **Dependencies** | 0001_initial.py |

**Columns (11 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `acl_id` | TEXT | UUID | PRIMARY KEY |
| `resource_type` | TEXT | VARCHAR(64) | NOT NULL |
| `resource_id` | TEXT | VARCHAR(128) | NOT NULL |
| `principal_type` | TEXT | VARCHAR(32) | NOT NULL |
| `principal_id` | TEXT | VARCHAR(128) | NOT NULL |
| `permission` | TEXT | VARCHAR(32) | NOT NULL |
| `privacy_band` | TEXT | VARCHAR(16) | |
| `granted_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `granted_by` | TEXT | VARCHAR(64) | |
| `expires_at` | TEXT | TIMESTAMPTZ | |
| `revoked_at` | TEXT | TIMESTAMPTZ | |

**Indexes (4 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_acl_resource` | (resource_type, resource_id) | BTREE |
| `ix_st_acl_principal` | (principal_type, principal_id) | BTREE |
| `ix_st_acl_permission` | (permission) | BTREE |
| `ix_st_acl_expires` | (expires_at) | BTREE WHERE expires_at IS NOT NULL |

---

**Issue 2.1.3.3: Migrate st_archive_manifest Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0012_st_archive_manifest.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0010_st_retention_policy.py |

**Columns (9 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `archive_id` | TEXT | UUID | PRIMARY KEY |
| `resource_type` | TEXT | VARCHAR(64) | NOT NULL |
| `resource_id` | TEXT | VARCHAR(128) | NOT NULL |
| `archived_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `archive_location` | TEXT | VARCHAR(512) | NOT NULL |
| `archive_size_bytes` | INTEGER | BIGINT | |
| `archive_checksum` | TEXT | CHAR(64) | |
| `retention_policy_id` | TEXT | UUID | FK → st_retention_policy.policy_id |
| `delete_after` | TEXT | TIMESTAMPTZ | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_archive_policy` | retention_policy_id | st_retention_policy(policy_id) |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_archive_resource` | (resource_type, resource_id) | BTREE |
| `ix_st_archive_delete` | (delete_after) | BTREE WHERE delete_after IS NOT NULL |

---

**Issue 2.1.3.4: Migrate idem_ledger Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0013_idem_ledger.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (5 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `idem_key` | TEXT | VARCHAR(128) | PRIMARY KEY |
| `receipt_id` | TEXT | UUID | |
| `first_seen_ts` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `state` | TEXT | VARCHAR(16) | DEFAULT 'active' |
| `expiry_ts` | TEXT | TIMESTAMPTZ | |

**Indexes (1 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_idem_ledger_expiry` | (expiry_ts) | BTREE WHERE expiry_ts IS NOT NULL |

---

### Epic 2.1.4: Device & Provisioning Schema

---

**Issue 2.1.4.1: Migrate st_devices Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0014_st_devices.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (6 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `device_id` | TEXT | VARCHAR(64) | PRIMARY KEY |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `mls_group_id` | TEXT | VARCHAR(64) | |
| `provisioned_ts` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `hmac_secret` | BLOB | BYTEA | NOT NULL |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_devices_tenant` | (tenant_id) | BTREE |
| `ix_st_devices_tenant_space` | (tenant_id, space_id) | BTREE |

---

**Issue 2.1.4.2: Migrate st_device_keys Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0015_st_device_keys.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0014_st_devices.py |

**Columns (10 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `device_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite), FK → st_devices.device_id |
| `key_version` | INTEGER | INTEGER | PRIMARY KEY (composite) |
| `verify_key` | TEXT | TEXT | NOT NULL |
| `key_state` | TEXT | VARCHAR(16) | DEFAULT 'active' |
| `registered_ts` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `activated_ts` | TEXT | TIMESTAMPTZ | |
| `rotated_ts` | TEXT | TIMESTAMPTZ | |
| `revoked_ts` | TEXT | TIMESTAMPTZ | |
| `grace_expires_ts` | TEXT | TIMESTAMPTZ | |
| `revocation_reason` | TEXT | TEXT | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_device_keys_device` | device_id | st_devices(device_id) ON DELETE CASCADE |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_device_keys_state` | (key_state) | BTREE |
| `ix_st_device_keys_revoked` | (revoked_ts) | BTREE WHERE revoked_ts IS NOT NULL |

---

### Epic 2.1.5: Domain Entities Schema

---

**Issue 2.1.5.1: Migrate households Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0016_households.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 5 hours |
| **Dependencies** | 0014_st_devices.py |

**Columns (35 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `household_id` | TEXT | UUID | PRIMARY KEY |
| `cognitive_trace_id` | TEXT | VARCHAR(128) | |
| `label` | TEXT | VARCHAR(256) | |
| `household_type` | TEXT | VARCHAR(32) | |
| `address` | TEXT | TEXT | |
| `timezone` | TEXT | VARCHAR(64) | |
| `member_count` | INTEGER | INTEGER | DEFAULT 0 |
| `adult_count` | INTEGER | INTEGER | DEFAULT 0 |
| `child_count` | INTEGER | INTEGER | DEFAULT 0 |
| `primary_contact_person_id` | TEXT | UUID | FK → people.person_id (DEFERRED) |
| `policy_profile` | TEXT | JSONB | |
| `retention_defaults` | TEXT | JSONB | |
| `privacy_defaults` | TEXT | JSONB | |
| `rate_limits` | TEXT | JSONB | |
| `storage_quota_gb` | REAL | REAL | |
| `storage_used_gb` | REAL | REAL | DEFAULT 0 |
| `subscription_tier` | TEXT | VARCHAR(32) | |
| `subscription_status` | TEXT | VARCHAR(16) | |
| `subscription_expires_at` | TEXT | TIMESTAMPTZ | |
| `billing_email` | TEXT | VARCHAR(256) | |
| `features_enabled` | TEXT | JSONB | |
| `experimental_features` | TEXT | JSONB | |
| `connected_services` | TEXT | JSONB | |
| `connector_count` | INTEGER | INTEGER | DEFAULT 0 |
| `tenant_id` | TEXT | VARCHAR(64) | UNIQUE, FK → st_devices.tenant_id |
| `privacy_band` | TEXT | VARCHAR(16) | |
| `visible_to` | TEXT | JSONB | |
| `crdt_vector_clock` | TEXT | JSONB | |
| `crdt_tombstone` | INTEGER | BOOLEAN | DEFAULT FALSE |
| `crdt_lamport` | INTEGER | BIGINT | DEFAULT 0 |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TEXT | TIMESTAMPTZ | |
| `onboarded_at` | TEXT | TIMESTAMPTZ | |
| `last_active_at` | TEXT | TIMESTAMPTZ | |
| `deactivated_at` | TEXT | TIMESTAMPTZ | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_hh_primary_contact` | primary_contact_person_id | people(person_id) DEFERRABLE INITIALLY DEFERRED |
| `fk_hh_tenant` | tenant_id | st_devices(tenant_id) |

**Indexes (8 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_households_tenant_id` | (tenant_id) | BTREE UNIQUE |
| `ix_households_label` | (label) | BTREE |
| `ix_households_type` | (household_type) | BTREE |
| `ix_households_subscription` | (subscription_status) | BTREE |
| `ix_households_created` | (created_at) | BTREE |
| `ix_households_updated` | (updated_at) | BTREE |
| `ix_households_active` | (last_active_at) | BTREE |
| `ix_households_tombstone` | (crdt_tombstone) | BTREE WHERE crdt_tombstone = TRUE |

---

**Issue 2.1.5.2: Migrate people Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0017_people.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 5 hours |
| **Dependencies** | 0016_households.py |

**Columns (33 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `person_id` | TEXT | UUID | PRIMARY KEY |
| `cognitive_trace_id` | TEXT | VARCHAR(128) | |
| `label` | TEXT | VARCHAR(256) | |
| `full_name` | TEXT | VARCHAR(256) | |
| `nicknames` | TEXT | JSONB | |
| `birth_date` | TEXT | DATE | |
| `relationships` | TEXT | JSONB | |
| `household_id` | TEXT | UUID | FK → households.household_id |
| `household_role` | TEXT | VARCHAR(32) | |
| `visibility_default` | TEXT | VARCHAR(16) | |
| `band_default` | TEXT | VARCHAR(16) | |
| `consent_status` | TEXT | VARCHAR(16) | |
| `merge_keys` | TEXT | JSONB | |
| `canonical_person_id` | TEXT | UUID | |
| `merged_from` | TEXT | JSONB | |
| `primary_device_id` | TEXT | VARCHAR(64) | |
| `registered_devices` | TEXT | JSONB | |
| `timezone` | TEXT | VARCHAR(64) | |
| `language` | TEXT | VARCHAR(16) | |
| `contact_preferences` | TEXT | JSONB | |
| `tenant_id` | TEXT | VARCHAR(64) | FK → st_devices.tenant_id |
| `space_id` | TEXT | VARCHAR(64) | |
| `privacy_band` | TEXT | VARCHAR(16) | |
| `owner_id` | TEXT | UUID | |
| `visible_to` | TEXT | JSONB | |
| `crdt_vector_clock` | TEXT | JSONB | |
| `crdt_tombstone` | INTEGER | BOOLEAN | DEFAULT FALSE |
| `crdt_lamport` | INTEGER | BIGINT | DEFAULT 0 |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TEXT | TIMESTAMPTZ | |
| `onboarded_at` | TEXT | TIMESTAMPTZ | |
| `last_active_at` | TEXT | TIMESTAMPTZ | |
| `deactivated_at` | TEXT | TIMESTAMPTZ | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_people_household` | household_id | households(household_id) ON DELETE SET NULL |
| `fk_people_tenant` | tenant_id | st_devices(tenant_id) |

**Indexes (7 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_people_household` | (household_id) | BTREE |
| `ix_people_tenant` | (tenant_id) | BTREE |
| `ix_people_label` | (label) | BTREE |
| `ix_people_full_name` | (full_name) | BTREE |
| `ix_people_created` | (created_at) | BTREE |
| `ix_people_updated` | (updated_at) | BTREE |
| `ix_people_tombstone` | (crdt_tombstone) | BTREE WHERE crdt_tombstone = TRUE |

---

**Issue 2.1.5.3: Migrate st_relationships Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0018_st_relationships.py` |
| **Priority** | P1 - High |
| **Estimate** | 3 hours |
| **Dependencies** | 0016_households.py, 0017_people.py |

**Columns (9 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `id` | INTEGER | BIGSERIAL | PRIMARY KEY |
| `household_id` | TEXT | UUID | FK → households.household_id |
| `person_id` | TEXT | UUID | FK → people.person_id |
| `related_person_id` | TEXT | UUID | FK → people.person_id |
| `relationship_type` | TEXT | VARCHAR(32) | NOT NULL |
| `properties_json` | TEXT | JSONB | |
| `source_version` | TEXT | VARCHAR(64) | |
| `hydrated_at` | TEXT | TIMESTAMPTZ | DEFAULT NOW() |
| `ttl_seconds` | INTEGER | INTEGER | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_rel_household` | household_id | households(household_id) ON DELETE CASCADE |
| `fk_rel_person` | person_id | people(person_id) ON DELETE CASCADE |
| `fk_rel_related` | related_person_id | people(person_id) ON DELETE CASCADE |

**Indexes (4 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_rel_household` | (household_id) | BTREE |
| `ix_st_rel_person` | (person_id) | BTREE |
| `ix_st_rel_related` | (related_person_id) | BTREE |
| `ix_st_rel_type` | (relationship_type) | BTREE |

---

### Epic 2.1.6: Pipeline Schema

---

**Issue 2.1.6.1: Migrate st_pipeline_processed Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0019_st_pipeline_processed.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (4 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `pipeline_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `space_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `wal_pos` | INTEGER | BIGINT | PRIMARY KEY (composite) |
| `processed_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_pp_wal_pos` | (wal_pos) | BTREE |
| `ix_st_pp_processed` | (processed_at) | BTREE |

---

**Issue 2.1.6.2: Migrate st_pipeline_status Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0020_st_pipeline_status.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (7 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `pipeline_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `wal_pos` | INTEGER | BIGINT | PRIMARY KEY (composite) |
| `status` | TEXT | VARCHAR(16) | NOT NULL |
| `duration_ms` | INTEGER | INTEGER | |
| `error_kind` | TEXT | VARCHAR(64) | |
| `error_msg` | TEXT | TEXT | |
| `updated_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Indexes (3 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_ps_status` | (status) | BTREE |
| `ix_st_ps_wal_pos` | (wal_pos) | BTREE |
| `ix_st_ps_error` | (error_kind) | BTREE WHERE error_kind IS NOT NULL |

---

**Issue 2.1.6.3: Migrate st_pipeline_watermarks Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0021_st_pipeline_watermarks.py` |
| **Priority** | P1 - High |
| **Estimate** | 1 hour |
| **Dependencies** | 0001_initial.py |

**Columns (4 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `pipeline_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `space_id` | TEXT | VARCHAR(64) | PRIMARY KEY (composite) |
| `watermark` | INTEGER | BIGINT | NOT NULL DEFAULT 0 |
| `updated_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Indexes (2 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_pw_watermark` | (watermark) | BTREE |
| `ix_st_pw_updated` | (updated_at) | BTREE |

---

## Milestone 2.2: Event & Vector Schema

### Epic 2.2.1: Hippocampus Events

---

**Issue 2.2.1.1: Migrate st_hipp_events Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0022_st_hipp_events.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 8 hours |
| **Dependencies** | 0002_st_wal.py |

**Note:** This is the largest table (90 columns). Consider partitioning by `tenant_id` or `created_at` for performance.

**Columns (90 total) - Group 1: Core Identity (15 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `event_id` | TEXT | UUID | PRIMARY KEY |
| `wal_pos` | INTEGER | BIGINT | UNIQUE, FK → st_wal.pos |
| `cognitive_trace_id` | TEXT | VARCHAR(128) | |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `effective_space_id` | TEXT | VARCHAR(64) | |
| `topic` | TEXT | VARCHAR(128) | NOT NULL |
| `uow_id` | TEXT | VARCHAR(64) | |
| `schema_version` | TEXT | VARCHAR(32) | |
| `envelope_sha256` | TEXT | CHAR(64) | |
| `sig_alg` | TEXT | VARCHAR(16) | |
| `sig_kid` | TEXT | VARCHAR(128) | |
| `idem_key` | TEXT | VARCHAR(128) | |
| `ingested_at` | TEXT | TIMESTAMPTZ | DEFAULT NOW() |
| `clock_skew_ms` | INTEGER | INTEGER | |

**Columns - Group 2: Policy & Privacy (11 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `policy_decision` | TEXT | VARCHAR(16) | |
| `policy_band` | TEXT | VARCHAR(16) | |
| `policy_version` | TEXT | VARCHAR(32) | |
| `obligations_json` | TEXT | JSONB | |
| `visible_to_json` | TEXT | JSONB | |
| `visibility_scope` | TEXT | VARCHAR(16) | |
| `owner_id` | TEXT | UUID | |
| `co_owners_json` | TEXT | JSONB | |
| `retention_policy_id` | TEXT | UUID | |
| `retention_bucket` | TEXT | VARCHAR(32) | |
| `actor_id` | TEXT | UUID | |

**Columns - Group 3: Device & Ingress (5 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `actor_role` | TEXT | VARCHAR(32) | |
| `device_id` | TEXT | VARCHAR(64) | |
| `device_kind` | TEXT | VARCHAR(32) | |
| `device_os` | TEXT | VARCHAR(32) | |
| `ingress_channel` | TEXT | VARCHAR(32) | |

**Columns - Group 4: Temporal (12 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `event_time_utc` | TEXT | TIMESTAMPTZ | |
| `write_time_utc` | TEXT | TIMESTAMPTZ | |
| `write_lag_ms` | INTEGER | INTEGER | |
| `local_date` | TEXT | DATE | |
| `local_time` | TEXT | TIME | |
| `day_of_week` | INTEGER | SMALLINT | |
| `is_weekend` | INTEGER | BOOLEAN | |
| `time_of_day_bucket` | TEXT | VARCHAR(16) | |
| `circadian_slot` | TEXT | VARCHAR(16) | |
| `is_backdated` | INTEGER | BOOLEAN | |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TEXT | TIMESTAMPTZ | |

**Columns - Group 5: Location (4 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `location_name` | TEXT | VARCHAR(256) | |
| `location_type` | TEXT | VARCHAR(32) | |
| `geohash_6` | TEXT | VARCHAR(12) | |
| `geo_precision_external` | TEXT | VARCHAR(16) | |
| `geo_masking_reason` | TEXT | VARCHAR(32) | |

**Columns - Group 6: Social Context (10 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `participants_json` | TEXT | JSONB | |
| `num_participants` | INTEGER | INTEGER | |
| `has_partner_present` | INTEGER | BOOLEAN | |
| `has_parent_present` | INTEGER | BOOLEAN | |
| `is_solo_event` | INTEGER | BOOLEAN | |
| `participant_roles_json` | TEXT | JSONB | |
| `social_context` | TEXT | VARCHAR(32) | |
| `social_intimacy` | TEXT | VARCHAR(16) | |

**Columns - Group 7: Text Content (6 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `text` | TEXT | TEXT | |
| `text_normalized` | TEXT | TEXT | |
| `char_count` | INTEGER | INTEGER | |
| `token_count` | INTEGER | INTEGER | |
| `language` | TEXT | VARCHAR(16) | |

**Columns - Group 8: Activity (5 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `activity_type` | TEXT | VARCHAR(64) | |
| `activity_category` | TEXT | VARCHAR(32) | |
| `is_meal` | INTEGER | BOOLEAN | |
| `is_outing` | INTEGER | BOOLEAN | |
| `ingress_source` | TEXT | VARCHAR(32) | |

**Columns - Group 9: Deduplication & Clustering (10 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `simhash_hex` | TEXT | CHAR(16) | |
| `minhash32` | TEXT | INTEGER[] | |
| `novelty_score` | REAL | REAL | |
| `near_duplicates_json` | TEXT | JSONB | |
| `is_near_duplicate` | INTEGER | BOOLEAN | |
| `episode_cluster_id` | TEXT | UUID | |
| `cluster_confidence` | REAL | REAL | |
| `clustering_version` | TEXT | VARCHAR(32) | |
| `embedding_id` | TEXT | UUID | UNIQUE |
| `embedding_status` | TEXT | VARCHAR(16) | |

**Columns - Group 10: NLP & Affect (12 cols):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `entities_json` | TEXT | JSONB | |
| `kg_triples_json` | TEXT | JSONB | |
| `sentiment_score` | REAL | REAL | |
| `sentiment_label` | TEXT | VARCHAR(16) | |
| `dominant_emotions_json` | TEXT | JSONB | |
| `affect_valence` | REAL | REAL | |
| `affect_arousal` | REAL | REAL | |
| `affect_band` | TEXT | VARCHAR(16) | |
| `salience_score` | REAL | REAL | |
| `salience_reasons_json` | TEXT | JSONB | |
| `salience_band` | TEXT | VARCHAR(16) | |
| `hippocampus_api_version` | TEXT | VARCHAR(16) | |
| `space_resolver_version` | TEXT | VARCHAR(16) | |
| `schema_uri` | TEXT | VARCHAR(512) | |

**Indexes (9 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_hipp_wal_pos` | (wal_pos) | BTREE UNIQUE |
| `ix_st_hipp_tenant_space` | (tenant_id, space_id) | BTREE |
| `ix_st_hipp_topic` | (topic) | BTREE |
| `ix_st_hipp_created` | (created_at) | BTREE |
| `ix_st_hipp_event_time` | (event_time_utc) | BTREE |
| `ix_st_hipp_embedding_id` | (embedding_id) | BTREE UNIQUE |
| `ix_st_hipp_cluster` | (episode_cluster_id) | BTREE |
| `ix_st_hipp_geohash` | (geohash_6) | BTREE |
| `ix_st_hipp_activity` | (activity_type) | BTREE |

---

**Issue 2.2.1.1b: st_hipp_events Staged Data Migration (RISK MITIGATION)**

| Field | Value |
|-------|-------|
| **Priority** | P0 - Critical |
| **Estimate** | 16 hours |
| **Dependencies** | 2.2.1.1 (schema), PostgreSQL infrastructure |
| **Risk** | HIGH - 91 columns, heavy write volume, blast radius |
| **Assignee** | TBD |

**Problem Statement:**

`st_hipp_events` is the largest table (91 columns) with continuous write traffic from P02/P03 pipelines. Naive migration will cause:

- Long table locks
- Disk bloat during COPY
- Index creation blocking writes
- Potential multi-hour downtime

**Mitigation Strategy:** 5-phase staged migration with batched inserts and CONCURRENTLY index creation.

**Phase 1: Pre-Migration Preparation**

```sql
-- k0/db/alembic/versions/0022a_st_hipp_events_staging.py

-- 1. Create target table WITHOUT indexes (faster initial load)
CREATE TABLE st_hipp_events_new (
    -- ... all 91 columns from Issue 2.2.1.1 ...
) WITH (autovacuum_enabled = false);  -- Disable during bulk load

-- 2. Estimate row count for batch planning
-- SELECT reltuples::bigint FROM pg_class WHERE relname = 'st_hipp_events';
```

**Phase 2: Batched Data Migration**

```python
# k0/automation/migrate_hipp_events.py
"""Staged migration for st_hipp_events - RISK MITIGATION."""

import asyncio
import logging
from datetime import datetime

import asyncpg

logger = logging.getLogger(__name__)

BATCH_SIZE = 10_000  # Tuned for memory/lock duration balance
YIELD_DELAY = 0.1    # Seconds between batches to allow other transactions


async def migrate_hipp_events_staged(source_dsn: str, target_dsn: str) -> dict:
    """Migrate st_hipp_events in batches to avoid long locks.

    Returns:
        Migration statistics dict
    """
    source = await asyncpg.connect(source_dsn)
    target = await asyncpg.connect(target_dsn)

    stats = {
        "start_time": datetime.utcnow().isoformat(),
        "batches_completed": 0,
        "rows_migrated": 0,
        "errors": [],
    }

    try:
        # Get total row count for progress tracking
        total_rows = await source.fetchval(
            "SELECT COUNT(*) FROM st_hipp_events"
        )
        logger.info(f"Starting migration of {total_rows:,} rows")

        # Get max event_id for batching (assumes UUID ordering)
        # Alternative: use created_at for time-based batching
        offset = 0

        while True:
            # Fetch batch from source
            rows = await source.fetch(
                """
                SELECT * FROM st_hipp_events
                ORDER BY created_at
                LIMIT $1 OFFSET $2
                """,
                BATCH_SIZE,
                offset,
            )

            if not rows:
                break

            # Insert batch into target (within transaction)
            async with target.transaction():
                # Use COPY for bulk insert (faster than INSERT)
                await target.copy_records_to_table(
                    "st_hipp_events_new",
                    records=[tuple(r.values()) for r in rows],
                    columns=[k for k in rows[0].keys()],
                )

            stats["batches_completed"] += 1
            stats["rows_migrated"] += len(rows)
            offset += BATCH_SIZE

            # Progress logging
            progress = (stats["rows_migrated"] / total_rows) * 100
            logger.info(
                f"Migrated batch {stats['batches_completed']}: "
                f"{stats['rows_migrated']:,}/{total_rows:,} rows ({progress:.1f}%)"
            )

            # Yield to allow other transactions
            await asyncio.sleep(YIELD_DELAY)

        stats["end_time"] = datetime.utcnow().isoformat()
        stats["success"] = True

    except Exception as e:
        stats["errors"].append(str(e))
        stats["success"] = False
        raise

    finally:
        await source.close()
        await target.close()

    return stats
```

**Phase 3: Index Creation (CONCURRENTLY)**

```sql
-- Run these ONE AT A TIME, not in parallel
-- Each CREATE INDEX CONCURRENTLY does not block writes

-- Primary key (required, fast)
ALTER TABLE st_hipp_events_new ADD PRIMARY KEY (event_id);

-- Tenant/space lookup (most critical for queries)
CREATE INDEX CONCURRENTLY idx_hipp_tenant_space_new
ON st_hipp_events_new (tenant_id, space_id, created_at DESC);

-- Topic index
CREATE INDEX CONCURRENTLY idx_hipp_topic_new
ON st_hipp_events_new (topic);

-- Created timestamp index
CREATE INDEX CONCURRENTLY idx_hipp_created_new
ON st_hipp_events_new (created_at);

-- Full-text search (slowest, run during maintenance window)
CREATE INDEX CONCURRENTLY idx_hipp_fts_new
ON st_hipp_events_new USING GIN (tsv);

-- Vector similarity (run LAST, HNSW is most expensive)
-- Estimated time: 2-4 hours for 10M rows
CREATE INDEX CONCURRENTLY idx_hipp_vector_new
ON st_hipp_events_new USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Phase 4: Atomic Cutover**

```sql
-- MAINTENANCE WINDOW REQUIRED for this step (brief lock)
-- Estimated lock duration: < 1 second

BEGIN;
  -- Lock both tables briefly for atomic rename
  LOCK TABLE st_hipp_events IN ACCESS EXCLUSIVE MODE;
  LOCK TABLE st_hipp_events_new IN ACCESS EXCLUSIVE MODE;

  -- Atomic rename swap
  ALTER TABLE st_hipp_events RENAME TO st_hipp_events_old;
  ALTER TABLE st_hipp_events_new RENAME TO st_hipp_events;

  -- Rename indexes to match table
  ALTER INDEX idx_hipp_tenant_space_new RENAME TO idx_hipp_tenant_space;
  ALTER INDEX idx_hipp_topic_new RENAME TO idx_hipp_topic;
  ALTER INDEX idx_hipp_created_new RENAME TO idx_hipp_created;
  ALTER INDEX idx_hipp_fts_new RENAME TO idx_hipp_fts;
  ALTER INDEX idx_hipp_vector_new RENAME TO idx_hipp_vector;
COMMIT;

-- Re-enable autovacuum
ALTER TABLE st_hipp_events SET (autovacuum_enabled = true);
```

**Phase 5: Post-Migration Cleanup**

```sql
-- Run VACUUM ANALYZE after migration (background, non-blocking)
VACUUM ANALYZE st_hipp_events;

-- Monitor bloat for 24-48 hours
SELECT
    schemaname, tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) as table_size,
    pg_size_pretty(pg_indexes_size(schemaname || '.' || tablename::regclass)) as index_size
FROM pg_tables
WHERE tablename = 'st_hipp_events';

-- Drop old table after validation period (7 days recommended)
-- DROP TABLE st_hipp_events_old;
```

**Estimated Migration Time** (for 10M rows):

| Phase | Duration | Notes |
|-------|----------|-------|
| Data COPY (batched) | 30-60 minutes | BATCH_SIZE=10,000 |
| Primary key | ~5 minutes | Fast, required |
| B-tree indexes (4x) | ~10 minutes each | Run in sequence |
| GIN (FTS) index | ~30 minutes | Slowest B-tree variant |
| HNSW (vector) index | 2-4 hours | **Most expensive** |
| Atomic cutover | < 1 second | Brief lock |
| VACUUM ANALYZE | ~15 minutes | Background |

**Disk Space Required:** 2x current table size (old + new during migration)

**Acceptance Criteria:**

- [ ] Batched migration script tested on staging
- [ ] All indexes created with CONCURRENTLY
- [ ] Atomic cutover tested with < 1s lock
- [ ] Rollback procedure documented (rename tables back)
- [ ] Monitoring queries ready for post-migration
- [ ] 7-day old table retention before DROP

---

**Issue 2.2.1.2: Migrate st_embedding_queue Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0023_st_embedding_queue.py` |
| **Priority** | P1 - High |
| **Estimate** | 3 hours |
| **Dependencies** | 0022_st_hipp_events.py |

**Columns (17 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `job_id` | TEXT | UUID | PRIMARY KEY |
| `wal_pos` | INTEGER | BIGINT | FK → st_wal.pos |
| `event_id` | TEXT | UUID | FK → st_hipp_events.event_id |
| `embedding_id` | TEXT | UUID | UNIQUE, FK → st_hipp_events.embedding_id |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `vector_kind` | TEXT | VARCHAR(32) | NOT NULL |
| `model_id` | TEXT | VARCHAR(64) | NOT NULL |
| `priority` | INTEGER | SMALLINT | DEFAULT 0 |
| `status` | TEXT | VARCHAR(16) | DEFAULT 'pending' |
| `attempt_count` | INTEGER | SMALLINT | DEFAULT 0 |
| `max_attempts` | INTEGER | SMALLINT | DEFAULT 3 |
| `next_attempt_ts` | TEXT | TIMESTAMPTZ | |
| `last_error` | TEXT | TEXT | |
| `vector_json` | TEXT | JSONB | |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TEXT | TIMESTAMPTZ | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_eq_wal` | wal_pos | st_wal(pos) |
| `fk_eq_event` | event_id | st_hipp_events(event_id) ON DELETE CASCADE |
| `fk_eq_embedding` | embedding_id | st_hipp_events(embedding_id) |

**Indexes (5 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_eq_status` | (status, next_attempt_ts) | BTREE |
| `ix_st_eq_embedding` | (embedding_id) | BTREE UNIQUE |
| `ix_st_eq_event` | (event_id) | BTREE |
| `ix_st_eq_tenant` | (tenant_id, space_id) | BTREE |
| `ix_st_eq_priority` | (priority DESC, created_at) | BTREE |

---

**Issue 2.2.1.3: Migrate st_crdt_merge_log Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0024_st_crdt_merge_log.py` |
| **Priority** | P2 - Medium |
| **Estimate** | 2 hours |
| **Dependencies** | 0001_initial.py |

**Columns (10 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `merge_id` | TEXT | UUID | PRIMARY KEY |
| `resource_type` | TEXT | VARCHAR(64) | NOT NULL |
| `resource_id` | TEXT | VARCHAR(128) | NOT NULL |
| `merge_strategy` | TEXT | VARCHAR(32) | NOT NULL |
| `winner_device_id` | TEXT | VARCHAR(64) | |
| `loser_device_id` | TEXT | VARCHAR(64) | |
| `winner_vector_clock` | TEXT | JSONB | |
| `loser_vector_clock` | TEXT | JSONB | |
| `merged_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `conflict_reason` | TEXT | VARCHAR(64) | |

**Indexes (3 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_crdt_resource` | (resource_type, resource_id) | BTREE |
| `ix_st_crdt_merged` | (merged_at) | BTREE |
| `ix_st_crdt_reason` | (conflict_reason) | BTREE |

---

### Epic 2.2.2: Vector Store & Full-Text Search

---

**Issue 2.2.2.1: Create pgvector Extension**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0025_pgvector_extension.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 1 hour |
| **Dependencies** | 0001_initial.py |

**SQL:**

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Notes:**

- Requires PostgreSQL 15+ or 14 with pgvector extension installed
- Extension must be created by superuser or user with CREATE privilege
- Enables `vector` type for embedding storage

---

**Issue 2.2.2.2: Migrate st_vec Table**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0026_st_vec.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 4 hours |
| **Dependencies** | 0025_pgvector_extension.py, 0022_st_hipp_events.py |

**Columns (13 total):**

| Column | SQLite Type | PostgreSQL Type | Constraints |
|--------|-------------|-----------------|-------------|
| `embedding_id` | TEXT | UUID | PRIMARY KEY |
| `event_id` | TEXT | UUID | FK → st_hipp_events.event_id |
| `tenant_id` | TEXT | VARCHAR(64) | NOT NULL |
| `space_id` | TEXT | VARCHAR(64) | NOT NULL |
| `vector` | BLOB | VECTOR(768) | NOT NULL |
| `vector_dim` | INTEGER | INTEGER | DEFAULT 768 |
| `model_id` | TEXT | VARCHAR(64) | NOT NULL |
| `status` | TEXT | VARCHAR(16) | DEFAULT 'active' |
| `cognitive_trace_id` | TEXT | VARCHAR(128) | |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TEXT | TIMESTAMPTZ | |
| `faiss_id` | INTEGER | INTEGER | |
| `indexed_at` | TEXT | TIMESTAMPTZ | |

**Foreign Keys:**

| Constraint | Column | References |
|------------|--------|------------|
| `fk_vec_event` | event_id | st_hipp_events(event_id) ON DELETE CASCADE |

**Indexes (6 total):**

| Index Name | Columns | Type |
|------------|---------|------|
| `ix_st_vec_event` | (event_id) | BTREE |
| `ix_st_vec_tenant` | (tenant_id, space_id) | BTREE |
| `ix_st_vec_model` | (model_id) | BTREE |
| `ix_st_vec_status` | (status) | BTREE |
| `ix_st_vec_created` | (created_at) | BTREE |
| `ix_st_vec_faiss` | (faiss_id) | BTREE WHERE faiss_id IS NOT NULL |

**Data Migration Notes:**

- SQLite stores vectors as BLOB (numpy bytes)
- Convert to pgvector format: `array_to_vector(numpy_bytes)`
- Batch convert in chunks of 1000 to avoid memory issues

---

**Issue 2.2.2.3: Create HNSW Index on st_vec**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0027_vector_indexes.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 2 hours |
| **Dependencies** | 0026_st_vec.py |

**SQL:**

```sql
-- HNSW index for fast approximate nearest neighbor search
-- m = 16: connections per layer (memory vs speed tradeoff)
-- ef_construction = 64: build-time accuracy (higher = more accurate, slower build)
CREATE INDEX CONCURRENTLY ix_st_vec_hnsw
ON st_vec
USING hnsw (vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Alternative: IVFFlat for very large datasets (>1M rows)
-- CREATE INDEX CONCURRENTLY ix_st_vec_ivfflat
-- ON st_vec
-- USING ivfflat (vector vector_cosine_ops)
-- WITH (lists = 100);
```

**Performance Tuning:**

| Parameter | Description | Recommended |
|-----------|-------------|-------------|
| `m` | Max connections per layer | 16-64 |
| `ef_construction` | Build-time search width | 64-128 |
| `ef_search` | Query-time search width | 40-100 |

**Query Example:**

```sql
-- Find 10 nearest neighbors
SELECT embedding_id, event_id,
       vector <=> $1 AS distance
FROM st_vec
WHERE tenant_id = $2
ORDER BY vector <=> $1
LIMIT 10;
```

---

**Issue 2.2.2.4: Create tsvector Columns**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0028_fts_columns.py` |
| **Priority** | P1 - High |
| **Estimate** | 3 hours |
| **Dependencies** | 0022_st_hipp_events.py |

**Columns to Add to st_hipp_events:**

| Column | PostgreSQL Type | Purpose |
|--------|-----------------|---------|
| `text_search_vector` | TSVECTOR | Full-text search on text + text_normalized |
| `entities_search_vector` | TSVECTOR | Full-text search on extracted entities |

**SQL:**

```sql
-- Add tsvector columns
ALTER TABLE st_hipp_events
ADD COLUMN text_search_vector TSVECTOR
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', COALESCE(text, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(text_normalized, '')), 'B')
) STORED;

ALTER TABLE st_hipp_events
ADD COLUMN entities_search_vector TSVECTOR;

-- Trigger to update entities_search_vector from JSONB
CREATE OR REPLACE FUNCTION update_entities_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.entities_search_vector := to_tsvector('english',
        COALESCE(NEW.entities_json::text, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_entities_search
BEFORE INSERT OR UPDATE OF entities_json ON st_hipp_events
FOR EACH ROW EXECUTE FUNCTION update_entities_search_vector();
```

---

**Issue 2.2.2.5: Create GIN Indexes for Full-Text Search**

| Field | Value |
|-------|-------|
| **Alembic Revision** | `0029_fts_indexes.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 0028_fts_columns.py |

**SQL:**

```sql
-- GIN index for text search
CREATE INDEX CONCURRENTLY ix_st_hipp_text_search
ON st_hipp_events
USING gin (text_search_vector);

-- GIN index for entity search
CREATE INDEX CONCURRENTLY ix_st_hipp_entities_search
ON st_hipp_events
USING gin (entities_search_vector);

-- GIN index for JSONB fields (optional, for direct JSON queries)
CREATE INDEX CONCURRENTLY ix_st_hipp_entities_json
ON st_hipp_events
USING gin (entities_json jsonb_path_ops);

CREATE INDEX CONCURRENTLY ix_st_hipp_obligations
ON st_hipp_events
USING gin (obligations_json jsonb_path_ops);
```

**Query Examples:**

```sql
-- Full-text search
SELECT event_id, text,
       ts_rank(text_search_vector, query) AS rank
FROM st_hipp_events,
     plainto_tsquery('english', 'family dinner') AS query
WHERE text_search_vector @@ query
  AND tenant_id = $1
ORDER BY rank DESC
LIMIT 20;

-- Phrase search
SELECT event_id, text
FROM st_hipp_events
WHERE text_search_vector @@ phraseto_tsquery('english', 'went to park');

-- JSONB containment query
SELECT event_id
FROM st_hipp_events
WHERE entities_json @> '{"person": "John"}';
```

---

# Phase 3: Storage Layer Conversion

## Milestone 3.1: Core Storage Modules

### Epic 3.1.1: WAL & Outbox Conversion

---

**Issue 3.1.1.1: Convert WriteAheadLog to Native Async**

| Field | Value |
|-------|-------|
| **File** | `k0/storage/wal.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 6 hours |
| **Lines of Code** | 327 lines |
| **Dependencies** | Phase 1 (asyncpg pool), Phase 2 (st_wal schema) |

**Current SQLite Patterns Found:**

| Pattern | Lines | Description |
|---------|-------|-------------|
| `import sqlite3` | 8 | Direct SQLite import |
| `connection_scope()` | 15, 57-62 | Sync pool context manager |
| `run_in_executor` | 114, 163, 183, 260, 293 | Blocking-to-async wrapper |
| `cursor.execute()` | 118-142 | Direct cursor execution |
| `cursor.lastrowid` | 155 | SQLite-specific row ID |
| `conn.execute().fetchall()` | 195-210 | Sync batch fetch |
| `PRAGMA database_list` | 251 | SQLite-specific |

**Conversion Requirements:**

1. **Remove `run_in_executor` wrappers** (5 locations):

   ```python
   # BEFORE
   async def append(...) -> int:
       loop = asyncio.get_running_loop()
       def _execute_append() -> int:
           with _resolve_connection(connection) as conn:
               cursor = conn.execute(...)
           ...
       position = await loop.run_in_executor(None, _execute_append)

   # AFTER
   async def append(...) -> int:
       async with connection_scope() as conn:
           result = await conn.fetchval(
               """INSERT INTO st_wal (...) VALUES ($1, $2, ...) RETURNING pos""",
               entry.tenant_id, entry.space_id, ...
           )
       return result
   ```

2. **Convert `?` placeholders to `$N`**:
   - 18 parameters in `append()` INSERT
   - 2 parameters in `read_from()` SELECT
   - 4 parameters in `backlog_stats()` SELECT

3. **Use `RETURNING pos`** instead of `cursor.lastrowid`:

   ```python
   # PostgreSQL supports RETURNING
   result = await conn.fetchval(
       "INSERT INTO st_wal (...) VALUES (...) RETURNING pos",
       ...
   )
   ```

4. **Replace PRAGMA with PostgreSQL**:
   - `PRAGMA database_list` → Not needed (single database)
   - `fsync()` method → Use PostgreSQL WAL flush: `SELECT pg_current_wal_lsn()`

5. **Convert `fetchall()` to async**:

   ```python
   # BEFORE
   rows = conn.execute(...).fetchall()

   # AFTER
   rows = await conn.fetch(...)
   ```

6. **Update `_resolve_connection` context manager**:

   ```python
   # BEFORE (sync)
   @contextmanager
   def _resolve_connection(connection: sqlite3.Connection | None):
       ...

   # AFTER (async)
   @asynccontextmanager
   async def _resolve_connection(connection: asyncpg.Connection | None):
       if connection is not None:
           yield connection
           return
       async with connection_scope() as conn:
           yield conn
   ```

**Methods to Convert:**

| Method | Type | Changes |
|--------|------|---------|
| `append()` | async | Remove executor, use RETURNING |
| `read_from()` | async | Remove executor, async fetch |
| `_read_from_sync()` | delete | Merge into `read_from()` |
| `fsync()` | async | Replace with PostgreSQL sync |
| `_execute_fsync()` | delete | Not needed for PostgreSQL |
| `backlog_stats()` | async | Remove executor |
| `_backlog_stats_sync()` | delete | Merge into `backlog_stats()` |

---

**Issue 3.1.1.2: Convert OutboxStore to Native Async**

| Field | Value |
|-------|-------|
| **File** | `k0/storage/outbox.py` |
| **Priority** | P0 - Critical |
| **Estimate** | 6 hours |
| **Lines of Code** | 385 lines |
| **Dependencies** | Phase 1 (asyncpg pool), Phase 2 (st_outbox schema) |

**Current SQLite Patterns Found:**

| Pattern | Lines | Description |
|---------|-------|-------------|
| `import sqlite3` | 6 | Direct SQLite import |
| `connection_scope()` | 13, 35-42 | Sync pool context manager |
| `run_in_executor` | 57 | Blocking-to-async wrapper |
| `sqlite3.OperationalError` | 100, 161, 233, 311 | SQLite-specific exception |
| `cursor.lastrowid` | 106 | SQLite-specific row ID |
| `ON CONFLICT(...) DO UPDATE` | ✓ | Compatible with PostgreSQL |

**Conversion Requirements:**

1. **Remove SQLite schema fallback logic** (4 locations):
   - Lines 100-116: Try/except for missing columns
   - Lines 161-168: Legacy schema fallback
   - Lines 233-244: Legacy schema fallback
   - Lines 311-318: Legacy schema fallback

   PostgreSQL migration ensures all columns exist - remove try/except blocks.

2. **Convert exception handling**:

   ```python
   # BEFORE
   except sqlite3.OperationalError as e:
       if "no column named" in str(e):
           ...

   # AFTER
   # No fallback needed - PostgreSQL schema is complete
   ```

3. **Convert all methods to native async**:

   ```python
   # BEFORE
   async def enqueue_async(...) -> int:
       loop = asyncio.get_running_loop()
       return await loop.run_in_executor(None, lambda: self.enqueue(...))

   def enqueue(...) -> int:
       with _resolve_connection(connection) as conn:
           cursor = conn.execute(...)

   # AFTER
   async def enqueue(...) -> int:
       async with connection_scope() as conn:
           return await conn.fetchval(
               """INSERT INTO st_outbox (...) VALUES ($1, ...) RETURNING id""",
               ...
           )
   ```

4. **Use PostgreSQL datetime**:

   ```python
   # BEFORE
   from datetime import datetime, timezone
   now = datetime.now(timezone.utc).isoformat()

   # AFTER
   # Use PostgreSQL NOW() in query or pass datetime directly
   await conn.execute(
       "... WHERE next_attempt_ts <= NOW() ..."
   )
   ```

**Methods to Convert:**

| Method | Type | Changes |
|--------|------|---------|
| `enqueue_async()` | delete | Merge into `enqueue()` |
| `enqueue()` | async | Native async, remove fallback |
| `dequeue_batch()` | async | Native async, remove fallback |
| `dequeue_ready_batch()` | async | Native async, use NOW() |
| `mark_applied()` | async | Native async |
| `record_failure()` | async | Native async, remove fallback |
| `_update_pending_metrics()` | async | Native async |

---

### Epic 3.1.2: DLQ & Receipts Conversion

---

**Issue 3.1.2.1: Convert DeadLetterQueue to Native Async**

| Field | Value |
|-------|-------|
| **File** | `k0/storage/dlq.py` |
| **Priority** | P1 - High |
| **Estimate** | 4 hours |
| **Lines of Code** | 254 lines |
| **Dependencies** | Phase 1 (asyncpg pool), Phase 2 (st_dlq schema) |

**Current SQLite Patterns Found:**

| Pattern | Lines | Description |
|---------|-------|-------------|
| `import sqlite3` | 4 | Direct SQLite import |
| `connection_scope()` | 13, 33-40 | Sync pool context manager |
| `cursor.lastrowid` | 82 | SQLite-specific row ID |
| `conn.execute()` | 60-79, 127-139, etc. | Sync cursor execution |

**Conversion Requirements:**

1. **Convert all methods to native async**:
   - `record()` → Use RETURNING id
   - `list_pending()` → async fetch with dynamic filters
   - `update_state()` → async execute
   - `purge_resolved()` → async execute

2. **Dynamic query building** (preserved but parameterized):

   ```python
   # BEFORE
   filters.append("state = ?")
   parameters.append(state.upper())
   query += " WHERE " + " AND ".join(filters)

   # AFTER
   filters.append(f"state = ${len(params)+1}")
   params.append(state.upper())
   query += " WHERE " + " AND ".join(filters)
   ```

**Methods to Convert:**

| Method | Current | After |
|--------|---------|-------|
| `record()` | sync | async + RETURNING |
| `list_pending()` | sync | async fetch |
| `update_state()` | sync | async execute |
| `purge_resolved()` | sync | async execute |
| `count_by_state()` | sync | async fetchval |

---

**Issue 3.1.2.2: Convert ReceiptStore to Native Async**

| Field | Value |
|-------|-------|
| **File** | `k0/storage/receipts.py` |
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Lines of Code** | 108 lines |
| **Dependencies** | Phase 1 (asyncpg pool), Phase 2 (st_receipts schema) |

**Current SQLite Patterns Found:**

| Pattern | Lines | Description |
|---------|-------|-------------|
| `import sqlite3` | 6 | Direct SQLite import |
| `run_in_executor` | 47 | Blocking-to-async wrapper |
| `ON CONFLICT(...) DO UPDATE` | 53-61 | Compatible with PostgreSQL |

**Conversion Requirements:**

1. **Convert to native async**:

   ```python
   # BEFORE
   async def save_async(...):
       loop = asyncio.get_running_loop()
       await loop.run_in_executor(None, lambda: self.save(...))

   def save(...):
       with _resolve_connection(connection) as conn:
           conn.execute(...)

   # AFTER
   async def save(...):
       async with connection_scope() as conn:
           await conn.execute(
               """INSERT INTO st_receipts (...) VALUES ($1, ...)
                  ON CONFLICT(receipt_id) DO UPDATE SET ...""",
               ...
           )
   ```

2. **PostgreSQL ON CONFLICT syntax** (already compatible):

   ```sql
   INSERT INTO st_receipts (...)
   VALUES ($1, $2, ...)
   ON CONFLICT(receipt_id) DO UPDATE SET
       idem_key = EXCLUDED.idem_key,
       ...
   ```

**Methods to Convert:**

| Method | Current | After |
|--------|---------|-------|
| `save_async()` | async wrapper | delete (merge into save) |
| `save()` | sync | async |
| `get()` | sync | async |

---

### Epic 3.1.3: Provisioning & Snapshots (28 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 3.1.3.1 | Convert Provisioning to asyncpg | `k0/storage/provisioning.py` | 15 |
| 3.1.3.2 | Convert Snapshots to asyncpg | `k0/storage/snapshots.py` | 13 |

---

#### Issue 3.1.3.1: Convert Provisioning Ledger to asyncpg

**File:** `k0/storage/provisioning.py` (343 lines)

**Purpose:** Provisioning ledger adapter for Minimal Gate device validation. Manages device bindings (tenant/space/mls_group) and verification keys with LRU caching.

**Architecture:**

- `ProvisionedDevice` / `DeviceKey` — frozen dataclasses for device data
- `_LRUCache` / `_DeviceKeyCache` — thread-safe LRU cache with `threading.RLock`
- `ProvisioningLedger` — main adapter with cache invalidation on writes

**SQLite Patterns to Convert:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 5 | `import sqlite3` | `import asyncpg` | Replace driver |
| 43-52 | `@contextmanager def _resolve_connection(...)` | `@asynccontextmanager async def _resolve_connection(...)` | Convert context manager |
| 44 | `sqlite3.Connection \| None` | `asyncpg.Connection \| None` | Type hint |
| 45 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` | Async context |
| 46 | `conn.row_factory = sqlite3.Row` | (built-in asyncpg) | Remove row_factory |
| 48 | `yield conn` | `yield conn` | No change |

**Method Conversions:**

| Method | Lines | Current Pattern | Target Pattern |
|--------|-------|-----------------|----------------|
| `register()` | 151-176 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |
| `add_key()` | 178-216 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |
| `seed()` | 218-225 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |
| `lookup()` | 227-260 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |
| `get_keys()` | 262-285 | uses `_load_keys()` internally | same, but `_load_keys()` is async |
| `_load_keys()` | 287-311 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |

**SQL Syntax Changes:**

| Line | Current | Target | Notes |
|------|---------|--------|-------|
| 158-166 | `ON CONFLICT(device_id) DO UPDATE SET` | Same (PostgreSQL-compatible) | No change |
| 193-199 | `ON CONFLICT(device_id, key_version) DO UPDATE SET` | Same (PostgreSQL-compatible) | No change |
| 245-248 | `conn.execute(...).fetchone()` | `await conn.fetchrow(...)` | asyncpg pattern |
| 299-305 | `conn.execute(...).fetchall()` | `await conn.fetch(...)` | asyncpg pattern |

**Thread Safety Considerations:**

- `_LRUCache` uses `threading.RLock` — Keep for cache thread safety OR convert to `asyncio.Lock`
- Caches can remain synchronous (they don't touch DB)
- Cache invalidation calls remain synchronous

**Signature Changes:**

```python
# BEFORE
def register(self, device: ProvisionedDevice, *, connection: sqlite3.Connection | None = None) -> ProvisionedDevice:

# AFTER
async def register(self, device: ProvisionedDevice, *, connection: asyncpg.Connection | None = None) -> ProvisionedDevice:
```

---

#### Issue 3.1.3.2: Convert Snapshot Scheduler to asyncpg

**File:** `k0/storage/snapshots.py` (357 lines)

**Purpose:** Snapshot scheduler for capturing durable WAL checkpoints. Creates SQLite database backups with manifest files.

**Architecture:**

- `SnapshotManifest` — frozen dataclass for snapshot metadata
- `SnapshotError` — custom exception
- `SnapshotScheduler` — orchestrates backup creation with WAL markers

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 6 | `import sqlite3` | `import asyncpg` | Replace driver |
| 85 | `connection = sqlite3.connect(str(self._database_path))` | `connection = await asyncpg.connect(...)` | Direct connect |
| 86 | `connection.row_factory = sqlite3.Row` | (built-in asyncpg) | Remove |
| 87 | `connection.execute("PRAGMA busy_timeout=30000;")` | Remove | PostgreSQL uses connection timeout |
| 188 | `connection.close()` | `await connection.close()` | Async close |

**WAL Marker Methods:**

| Method | Lines | Current Pattern | Target Pattern |
|--------|-------|-----------------|----------------|
| `create()` | 64-188 | sync `sqlite3.connect()` | `async def create()` with `await asyncpg.connect()` |
| `_append_marker()` | 190-259 | `cursor.lastrowid` for position | `RETURNING pos` clause |
| `_write_backup()` | 261-265 | `connection.backup(destination)` | PostgreSQL `pg_dump` or logical backup |
| `_resolve_watermark()` | 284-287 | `connection.execute(...).fetchone()` | `await connection.fetchrow(...)` |

**SQLite-Specific Backup Logic (MAJOR REWRITE):**

```python
# BEFORE (line 261-265)
def _write_backup(self, connection: sqlite3.Connection, artifact_path: Path) -> None:
    with sqlite3.connect(str(artifact_path)) as destination:
        connection.backup(destination)
        destination.execute("VACUUM;")

# AFTER — PostgreSQL pg_dump or pg_basebackup
async def _write_backup(self, connection_string: str, artifact_path: Path) -> None:
    # Option A: pg_dump for logical backup
    await asyncio.create_subprocess_exec(
        "pg_dump", "-Fc", "-f", str(artifact_path), connection_string
    )
    # Option B: Copy specific tables using COPY TO
```

**cursor.lastrowid Replacement:**

```python
# BEFORE (line 245-250)
cursor = connection.execute("INSERT INTO st_wal (...) VALUES (...)")
position = cursor.lastrowid

# AFTER
position = await connection.fetchval(
    "INSERT INTO st_wal (...) VALUES (...) RETURNING pos"
)
```

**PRAGMA Removal:**

| Line | Current | Action |
|------|---------|--------|
| 87 | `PRAGMA busy_timeout=30000` | Remove (PostgreSQL uses pool timeout) |
| 265 | `VACUUM;` | Convert to `VACUUM ANALYZE st_wal` via separate command |

---

### Epic 3.1.4: Offsets & Obligations (25 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 3.1.4.1 | Convert Offsets to asyncpg | `k0/storage/offsets.py` | 12 |
| 3.1.4.2 | Convert Obligations to asyncpg | `k0/storage/obligations.py` | 13 |

---

#### Issue 3.1.4.1: Convert Offset Store to asyncpg

**File:** `k0/storage/offsets.py` (~110 lines)

**Purpose:** Subscriber offset storage for tracking consumer positions in event streams.

**Architecture:**

- `OffsetStore` — async wrapper class with sync internal methods
- Uses `run_in_executor` pattern for async-over-sync

**Critical run_in_executor Removal:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 6 | `import sqlite3` | `import asyncpg` | Replace driver |
| 47 | `await asyncio.get_event_loop().run_in_executor(None, self._upsert_sync, ...)` | `await self._upsert(...)` | Remove executor |
| 80 | `await asyncio.get_event_loop().run_in_executor(None, self._fetch_sync, ...)` | `await self._fetch(...)` | Remove executor |

**Method Consolidation:**

```python
# BEFORE — async wrapper + sync implementation
async def upsert(self, subscriber_id: str, topic: str, offset: int) -> None:
    await asyncio.get_event_loop().run_in_executor(
        None, self._upsert_sync, subscriber_id, topic, offset
    )

def _upsert_sync(self, subscriber_id: str, topic: str, offset: int) -> None:
    with self._lock:
        with connection_scope() as conn:
            conn.execute(...)

# AFTER — single async method
async def upsert(self, subscriber_id: str, topic: str, offset: int) -> None:
    async with async_connection_scope() as conn:
        await conn.execute(
            "INSERT INTO st_offsets (subscriber_id, topic, offset_val, updated_at) "
            "VALUES ($1, $2, $3, NOW()) "
            "ON CONFLICT (subscriber_id, topic) DO UPDATE SET offset_val = $3, updated_at = NOW()",
            subscriber_id, topic, offset
        )
```

**RLock Removal:**

| Line | Current | Action |
|------|---------|--------|
| 18 | `self._lock = threading.RLock()` | Remove (asyncpg handles concurrency) |
| 36 | `with self._lock:` | Remove lock block |
| 68 | `with self._lock:` | Remove lock block |

**SQL Parameter Style:**

| Current | Target |
|---------|--------|
| `?` placeholders | `$1, $2, $3` numbered placeholders |
| `ON CONFLICT(...) DO UPDATE SET` | Same (PostgreSQL native) |

---

#### Issue 3.1.4.2: Convert Obligation Store to asyncpg

**File:** `k0/storage/obligations.py` (~150 lines)

**Purpose:** Policy obligation log persistence (ADR-0089). Stores PDP evaluation results for audit.

**Architecture:**

- `ObligationStore` — sync-only class (no async wrappers currently)
- Uses `connection_scope()` for all DB access

**All Methods to Async:**

| Method | Lines | Current | Target |
|--------|-------|---------|--------|
| `save()` | ~30-55 | `def save(...)` | `async def save(...)` |
| `bulk_save()` | ~57-85 | `def bulk_save(...)` | `async def bulk_save(...)` |
| `fetch_by_wal_pos()` | ~87-105 | `def fetch_by_wal_pos(...)` | `async def fetch_by_wal_pos(...)` |
| `fetch_recent()` | ~107-130 | `def fetch_recent(...)` | `async def fetch_recent(...)` |

**cursor.lastrowid Replacement:**

```python
# BEFORE
cursor = conn.execute("INSERT INTO st_obligations (...) VALUES (...)")
return cursor.lastrowid

# AFTER
return await conn.fetchval(
    "INSERT INTO st_obligations (...) VALUES (...) RETURNING id"
)
```

**executemany() Replacement:**

```python
# BEFORE
cursor.executemany("INSERT INTO st_obligations (...) VALUES (?,...)", records)

# AFTER
await conn.executemany(
    "INSERT INTO st_obligations (...) VALUES ($1,...)",
    [(r.field1, r.field2, ...) for r in records]
)
```

**Detailed Line Changes:**

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 5 | `import sqlite3` | `import asyncpg` |
| 15 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| 30 | `def save(self, obligation: Obligation, *, connection: sqlite3.Connection \| None = None)` | `async def save(..., connection: asyncpg.Connection \| None = None)` |
| 35 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` |
| 42 | `cursor = conn.execute(...)` | `result = await conn.fetchval(... RETURNING id)` |
| 45 | `return cursor.lastrowid` | `return result` |
| 60 | `conn.executemany(...)` | `await conn.executemany(...)` |
| 90 | `rows = conn.execute(...).fetchall()` | `rows = await conn.fetch(...)` |
| 115 | `rows = conn.execute(...).fetchall()` | `rows = await conn.fetch(...)` |

---

### Epic 3.1.5: Shard Promotion & Replayer (46 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 3.1.5.1 | Convert Shard Promotion to asyncpg | `k0/storage/shard_promotion.py` | 31 |
| 3.1.5.2 | Convert Replayer to asyncpg | `k0/storage/replayer.py` | 15 |

---

#### Issue 3.1.5.1: Convert Shard Promotion Coordinator to asyncpg

**File:** `k0/storage/shard_promotion.py` (360 lines)

**Purpose:** Shard promotion and WAL synchronization between primary/standby database pairs.

**Architecture:**

- `ShardPromotionCoordinator` — manages WAL delta reconciliation
- `ShardPromotionResult` — frozen dataclass for promotion outcome
- `ShardPromotionError` — custom exception

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 5 | `import sqlite3` | `import asyncpg` | Replace driver |
| 213-227 | `@staticmethod def _connect_database(path: Path)` | `async def _connect_database(...)` | Async connect |
| 222 | `sqlite3.connect(path.as_posix())` | `await asyncpg.connect(connection_string)` | Connection string |
| 223 | `connection.row_factory = sqlite3.Row` | (built-in asyncpg) | Remove |
| 224 | `PRAGMA busy_timeout=5000` | Remove | PostgreSQL pool timeout |

**Connection Management Rewrite:**

```python
# BEFORE (lines 213-227)
@staticmethod
def _connect_database(path: Path) -> ContextManager[sqlite3.Connection]:
    @contextmanager
    def _connector() -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(path.as_posix())
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000;")
        try:
            yield connection
        finally:
            connection.close()
    return _connector()

# AFTER
async def _connect_database(self, connection_string: str) -> AsyncContextManager[asyncpg.Connection]:
    @asynccontextmanager
    async def _connector() -> AsyncIterator[asyncpg.Connection]:
        connection = await asyncpg.connect(connection_string)
        try:
            yield connection
        finally:
            await connection.close()
    return _connector()
```

**Primary/Standby Connection Paths:**

| Line | Current | Target |
|------|---------|--------|
| 41-42 | `self._primary_path = Path(primary_path)` | `self._primary_dsn = primary_dsn` |
| 43-44 | `self._standby_path = Path(standby_path)` | `self._standby_dsn = standby_dsn` |
| 211 | `_connect_primary()` returns file path | Returns DSN string |
| 214 | `_connect_standby()` returns file path | Returns DSN string |

**All @staticmethod Methods to Async:**

| Method | Lines | Notes |
|--------|-------|-------|
| `_compute_lag_seconds()` | 229-240 | Convert to async, uses `_latest_commit_ts()` |
| `_latest_commit_ts()` | 242-258 | Convert to async, `await conn.fetchrow(...)` |
| `_resolve_watermark()` | 260-265 | Convert to async, `await conn.fetchrow(...)` |
| `_fetch_wal_entries()` | 267-278 | Convert to async, `await conn.fetch(...)` |
| `_fetch_receipts()` | 280-294 | Convert to async, `await conn.fetch(...)` |
| `_find_missing_receipts()` | 296-308 | Convert to async, `await conn.fetch(...)` |
| `_upsert_wal_entry()` | 310-323 | Convert to async, `await conn.execute(...)` |
| `_upsert_receipt()` | 325-338 | Convert to async, `await conn.execute(...)` |
| `_row_to_dict()` | 340-341 | Keep sync (dict conversion only) |

**Main Methods to Async:**

| Method | Lines | Notes |
|--------|-------|-------|
| `compute_replica_lag()` | 50-55 | `async def`, context managers async |
| `promote()` | 57-146 | `async def`, all internal calls await |

**SQL Parameter Conversion:**

| Current | Target |
|---------|--------|
| `WHERE pos > ?` | `WHERE pos > $1` |
| `WHERE wal_pos IN (?,?,?)` | `WHERE wal_pos = ANY($1::int[])` |
| Named placeholders `:pos, :tenant_id` | `$1, $2` positional |

---

#### Issue 3.1.5.2: Convert Replayer to asyncpg

**File:** `k0/storage/replayer.py` (391 lines)

**Purpose:** Cold replay coordinator for WAL parity validation and readiness indicators.

**Architecture:**

- `Replayer` — validates WAL→receipts→outbox parity
- `ReplayResult` — frozen dataclass for replay outcome
- `ReplayError` — custom exception

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 6 | `import sqlite3` | `import asyncpg` | Replace driver |
| 14 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Async pool |
| 68 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` | Async context |
| 69 | `connection.row_factory = sqlite3.Row` | Remove (asyncpg built-in) | Remove |

**Main run() Method Conversion:**

```python
# BEFORE (line 49-68)
def run(self, *, from_position: int, ...) -> ReplayResult:
    with connection_scope() as connection:
        connection.row_factory = sqlite3.Row
        ...

# AFTER
async def run(self, *, from_position: int, ...) -> ReplayResult:
    async with async_connection_scope() as connection:
        await self._schema_registry.load(connection=connection)
        ...
```

**Transaction Handling:**

| Line | Current | Target |
|------|---------|--------|
| 102 | `connection.execute("BEGIN IMMEDIATE")` | `await connection.execute("BEGIN")` |
| 130 | `connection.rollback()` | `await connection.execute("ROLLBACK")` |
| 159 | `connection.commit()` | `await connection.execute("COMMIT")` |

**Method Conversions:**

| Method | Lines | Notes |
|--------|-------|-------|
| `run()` | 49-295 | Main orchestrator, fully async |
| `_fetch_batch()` | 297-318 | `await conn.fetch(...)` |
| `_receipt_exists()` | 320-346 | `await conn.fetchrow(...)` |
| `_verify_outbox_parity()` | 348-372 | `await conn.fetchrow(...)` |

**SQL Parameter Conversion:**

| Line | Current | Target |
|------|---------|--------|
| 316 | `LIMIT ?` | `LIMIT $4` |
| 330 | `WHERE wal_pos = ? LIMIT 1` | `WHERE wal_pos = $1 LIMIT 1` |
| 366 | `WHERE wal_pos = ? LIMIT 1` | `WHERE wal_pos = $1 LIMIT 1` |

---

### Epic 3.1.6: FTS Indexer & FTS Store (21 changes)

> **Note:** `k0/storage/fts.py` was missing from original audit. It uses SQLite FTS5 virtual tables with `connection_scope()` context manager. Must be converted to PostgreSQL tsvector + GIN.

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 3.1.6.1 | Convert FTS Store to tsvector | `k0/storage/fts.py` | 11 |
| 3.1.6.2 | Convert FTS5 Indexer to tsvector | `k0/storage/fts5_indexer.py` | 10 |

---

#### Issue 3.1.6.1: Convert FTS Store to tsvector

**File:** `k0/storage/fts.py` (11 changes)

**k0/storage/fts.py Detailed Changes:**

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 9 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| 63 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` |
| 64 | `connection.execute(INSERT OR REPLACE INTO st_fts ...)` | `await connection.execute(INSERT ON CONFLICT DO UPDATE ...)` |
| 90 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` |
| 91 | `connection.execute("DELETE FROM st_fts ...")` | `await connection.execute("DELETE FROM st_fts ...")` |
| 107 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` |
| 129 | FTS5 `MATCH ?` syntax | PostgreSQL `@@ to_tsquery(?)` |
| 129 | `bm25(st_fts)` | `ts_rank_cd(content_tsvector, ...)` |
| 162 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` |

---

#### Issue 3.1.6.2: Convert FTS5 Indexer to tsvector

**File:** `k0/storage/fts5_indexer.py` (352 lines)

**Purpose:** FTS5 full-text search indexer for episodic and hippocampus memory tables (`st_epi_fts`, `st_hipp_fts`).

**Architecture:**

- `FTS5Indexer` — manages FTS5 virtual table indexing
- `FTS5IndexerError` — custom exception
- Supports episodic and hippocampus memory indexing with keyword search

**Critical SQLite FTS5 Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 6 | `import sqlite3` | `import asyncpg` | Replace driver |
| 52 | `def __init__(self, connection: sqlite3.Connection)` | `def __init__(self, connection: asyncpg.Connection)` | Type hint |
| 52 | `self._connection = connection` | `self._connection = connection` | Keep reference |

**FTS5 Virtual Table → PostgreSQL tsvector:**

The `st_epi_fts` and `st_hipp_fts` FTS5 virtual tables must be converted to regular PostgreSQL tables with `tsvector` columns and GIN indexes:

```sql
-- BEFORE (SQLite FTS5)
CREATE VIRTUAL TABLE st_epi_fts USING fts5(
    event_id, tenant_id, space_id,
    text, summary, tags, topics,
    location_names, participant_names,
    commit_ts
);

-- AFTER (PostgreSQL tsvector + GIN)
CREATE TABLE st_epi_fts (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    text TEXT,
    summary TEXT,
    tags TEXT,
    topics TEXT,
    location_names TEXT,
    participant_names TEXT,
    commit_ts TIMESTAMPTZ,
    content_tsvector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(text, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(tags, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(topics, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(location_names, '')), 'D') ||
        setweight(to_tsvector('english', COALESCE(participant_names, '')), 'D')
    ) STORED
);
CREATE INDEX idx_st_epi_fts_tsvector ON st_epi_fts USING GIN(content_tsvector);
```

**Method Conversions:**

| Method | Lines | Current | Target |
|--------|-------|---------|--------|
| `index_episodic()` | 55-125 | `self._connection.execute(INSERT INTO st_epi_fts ...)` | `await self._connection.execute(INSERT ... ON CONFLICT DO UPDATE ...)` |
| `index_hippocampus()` | 127-200 | `self._connection.execute(INSERT INTO st_hipp_fts ...)` | `await self._connection.execute(INSERT ... ON CONFLICT DO UPDATE ...)` |
| `remove_from_index()` | 210-236 | `self._connection.execute(DELETE FROM ...)` | `await self._connection.execute(DELETE FROM ...)` |
| `search_episodic()` | 238-290 | FTS5 `MATCH ?` syntax | `@@ plainto_tsquery($1)` |
| `search_hippocampus()` | 292-340 | FTS5 `MATCH ?` syntax | `@@ plainto_tsquery($1)` |

**FTS5 MATCH → PostgreSQL tsquery:**

```python
# BEFORE (lines 285-288)
cursor = self._connection.execute(
    f"SELECT event_id FROM st_epi_fts WHERE {where_clause} LIMIT ?",
    params,
)

# AFTER
rows = await self._connection.fetch(
    """
    SELECT event_id FROM st_epi_fts
    WHERE content_tsvector @@ plainto_tsquery('english', $1)
    AND ($2::text IS NULL OR tenant_id = $2)
    AND ($3::text IS NULL OR space_id = $3)
    ORDER BY ts_rank_cd(content_tsvector, plainto_tsquery('english', $1)) DESC
    LIMIT $4
    """,
    query, tenant_id, space_id, limit
)
```

**Exception Handling:**

| Line | Current | Target |
|------|---------|--------|
| 123 | `except sqlite3.Error as exc:` | `except asyncpg.PostgresError as exc:` |
| 205 | `except sqlite3.Error as exc:` | `except asyncpg.PostgresError as exc:` |
| 234 | `except sqlite3.Error as exc:` | `except asyncpg.PostgresError as exc:` |
| 287 | `except sqlite3.Error as exc:` | `except asyncpg.PostgresError as exc:` |
| 337 | `except sqlite3.Error as exc:` | `except asyncpg.PostgresError as exc:` |

**Async Signature Changes:**

```python
# BEFORE
def index_episodic(self, *, event_id: str, text: str, ...) -> None:

# AFTER
async def index_episodic(self, *, event_id: str, text: str, ...) -> None:
```

All 5 public methods become async:

- `async def index_episodic(...)`
- `async def index_hippocampus(...)`
- `async def remove_from_index(...)`
- `async def search_episodic(...)`
- `async def search_hippocampus(...)`

---

## Milestone 3.2: UoW & Gate Modules (93 changes)

### Epic 3.2.1: Unit of Work (42 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 3.2.1.1 | Convert UoW to asyncpg | `k0/uow/unit_of_work.py` | 31 |
| 3.2.1.2 | Replace connection pool | `k0/uow/connection_pool.py` | 11 |

---

#### Issue 3.2.1.1: Convert Unit of Work to asyncpg

**File:** `k0/uow/unit_of_work.py` (388 lines)

**Purpose:** ACID transaction coordinator for WAL, receipts, offsets, and outbox operations. Central to all write operations in K0.

**Architecture:**

- `UnitOfWork` — dataclass implementing async context manager
- Coordinates `WriteAheadLog`, `ReceiptStore`, `OffsetStore`, `OutboxStore`
- Uses global write semaphore for SQLite single-writer constraint
- Context variable `_ACTIVE_UOW` for current transaction tracking

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 7 | `import sqlite3` | `import asyncpg` | Replace driver |
| 19 | `from .connection_pool import connection_scope` | `from .postgres_pool import async_connection_scope` | Async pool |
| 26-30 | `_WRITE_SEMAPHORE: asyncio.Semaphore` | Remove entirely | PostgreSQL handles concurrency |
| 75 | `_scope: AbstractContextManager[sqlite3.Connection]` | `_scope: AsyncContextManager[asyncpg.Connection]` | Type hint |
| 76 | `_connection: sqlite3.Connection \| None` | `_connection: asyncpg.Connection \| None` | Type hint |

**Write Semaphore Removal:**

The SQLite write semaphore pattern (lines 26-38) exists because SQLite allows only one writer at a time. PostgreSQL supports multiple concurrent writers with row-level locking, so this entire mechanism can be removed:

```python
# REMOVE (lines 26-38)
_WRITE_SEMAPHORE: asyncio.Semaphore | None = None
_WRITE_SEMAPHORE_TIMEOUT = 30.0

def _get_write_semaphore() -> asyncio.Semaphore:
    global _WRITE_SEMAPHORE
    if _WRITE_SEMAPHORE is None:
        _WRITE_SEMAPHORE = asyncio.Semaphore(1)
    return _WRITE_SEMAPHORE
```

**Async Context Manager Conversion:**

| Method | Lines | Current | Target |
|--------|-------|---------|--------|
| `__aenter__()` | 83-115 | Acquires semaphore, uses `connection_scope()` | Uses `async_connection_scope()`, no semaphore |
| `__aexit__()` | 117-134 | Releases semaphore, calls `_commit()` | No semaphore release needed |
| `__enter__()` | 136-159 | Deprecated sync enter | Remove or raise `NotImplementedError` |
| `__exit__()` | 161-175 | Broken sync exit | Remove entirely |

****aenter**() Rewrite:**

```python
# BEFORE (lines 83-115)
async def __aenter__(self) -> "UnitOfWork":
    semaphore = _get_write_semaphore()
    await asyncio.wait_for(semaphore.acquire(), timeout=_WRITE_SEMAPHORE_TIMEOUT)
    self._holds_semaphore = True

    self._scope = connection_scope()
    connection = self._scope.__enter__()
    assert isinstance(connection, sqlite3.Connection)
    self._connection = connection

    # SQLite WAL mode configuration
    self._connection.execute("PRAGMA journal_mode=WAL")
    self._connection.execute("PRAGMA synchronous=NORMAL")
    ...

# AFTER
async def __aenter__(self) -> "UnitOfWork":
    self._scope = async_connection_scope()
    self._connection = await self._scope.__aenter__()

    # PostgreSQL transaction isolation
    await self._connection.execute("BEGIN")
    self._start_time = time.perf_counter()
    self._token = _ACTIVE_UOW.set(self)
    return self
```

**PRAGMA Removal:**

| Line | Current | Action |
|------|---------|--------|
| 105 | `PRAGMA journal_mode=WAL` | Remove (PostgreSQL uses WAL by default) |
| 106 | `PRAGMA synchronous=NORMAL` | Remove |
| 107 | `PRAGMA foreign_keys=ON` | Remove (default in PostgreSQL) |
| 108 | `PRAGMA temp_store=MEMORY` | Remove |
| 109 | `PRAGMA busy_timeout=5000` | Remove (connection pool timeout) |
| 110 | `PRAGMA wal_autocheckpoint=1000` | Remove |
| 113 | `BEGIN IMMEDIATE` | `BEGIN` (PostgreSQL default isolation) |

**Commit/Rollback Methods:**

| Method | Lines | Current | Target |
|--------|-------|---------|--------|
| `_commit()` | 234-295 | `self._connection.commit()` | `await self._connection.execute("COMMIT")` |
| `_rollback()` | 297-312 | `self._connection.rollback()` | `await self._connection.execute("ROLLBACK")` |
| `_fsync_wal()` | 339-350 | WAL fsync via `write_ahead_log.fsync()` | PostgreSQL WAL is always fsync'd |

**Exception Handling:**

| Line | Current | Target |
|------|---------|--------|
| 99 | `raise sqlite3.OperationalError(...)` | `raise asyncpg.InterfaceError(...)` |
| 306 | `except sqlite3.Error:` | `except asyncpg.PostgresError:` |

---

#### Issue 3.2.1.2: Replace Connection Pool with asyncpg Pool

**File:** `k0/uow/connection_pool.py` (393 lines)

**Purpose:** Thread-safe SQLite connection pool with PRAGMA configuration.

**Migration Strategy:** This entire file will be **deprecated and replaced** with a new `k0/uow/postgres_pool.py` that uses asyncpg's built-in connection pooling.

**Current Architecture:**

- `SQLiteConnectionPool` — custom thread-safe pool with `threading.Condition`
- `connection_scope()` — context manager for acquiring pooled connections
- `configure_pool()` / `shutdown_pool()` / `get_pool()` — global pool management
- Extensive PRAGMA configuration and retry logic

**New Architecture (postgres_pool.py):**

```python
"""PostgreSQL connection pooling primitives using asyncpg."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from k0.obs.metrics import MetricsExporter

_pool: asyncpg.Pool | None = None


async def configure_pool(
    dsn: str,
    *,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 60.0,
    metrics_exporter: "MetricsExporter | None" = None,
) -> None:
    """Initialize the global asyncpg connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )


async def shutdown_pool() -> None:
    """Close and discard the global pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the configured pool or raise if missing."""
    if _pool is None:
        raise RuntimeError("Connection pool has not been configured")
    return _pool


@asynccontextmanager
async def async_connection_scope() -> AsyncIterator[asyncpg.Connection]:
    """Yield a pooled asyncpg connection."""
    pool = get_pool()
    async with pool.acquire() as connection:
        yield connection
```

**Files to Update (imports):**

All files that import from `connection_pool.py` must be updated:

| File | Current Import | Target Import |
|------|----------------|---------------|
| `k0/uow/unit_of_work.py` | `from .connection_pool import connection_scope` | `from .postgres_pool import async_connection_scope` |
| `k0/gate/schema_registry.py` | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| `k0/storage/*.py` | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| `k0/drivers/fts5.py` | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| `k0/drivers/faiss.py` | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |

---

### Epic 3.2.2: Gate Layer (51 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 3.2.2.1 | Convert Schema Registry to asyncpg | `k0/gate/schema_registry.py` | 40 |
| 3.2.2.2 | Convert Minimal Gate to asyncpg | `k0/gate/minimal_gate.py` | 11 |

---

#### Issue 3.2.2.1: Convert Schema Registry to asyncpg

**File:** `k0/gate/schema_registry.py` (448 lines)

**Purpose:** Cached facade for schema_registry SQLite table. Provides schema validation, registration, promotion, and blocking.

**Architecture:**

- `SchemaRecord` — dataclass for schema metadata
- `SchemaRegistry` — cached facade with thread-safe `threading.RLock`
- `_resolve_connection()` — context manager for optional connection parameter

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 5 | `import sqlite3` | `import asyncpg` | Replace driver |
| 11 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Async pool |
| 33-41 | `@contextmanager def _resolve_connection(...)` | `@asynccontextmanager async def _resolve_connection(...)` | Async context |
| 44-46 | `def _ensure_row_factory(connection)` | Remove | asyncpg has built-in dict rows |

**_resolve_connection() Rewrite:**

```python
# BEFORE (lines 33-41)
@contextmanager
def _resolve_connection(
    connection: sqlite3.Connection | None,
) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
        return
    with connection_scope() as pooled_connection:
        yield pooled_connection
        pooled_connection.commit()

# AFTER
@asynccontextmanager
async def _resolve_connection(
    connection: asyncpg.Connection | None,
) -> AsyncIterator[asyncpg.Connection]:
    if connection is not None:
        yield connection
        return
    async with async_connection_scope() as pooled_connection:
        yield pooled_connection
```

**Method Conversions (All to Async):**

| Method | Lines | Current | Target |
|--------|-------|---------|--------|
| `load()` | 73-99 | `def load(...)` | `async def load(...)` |
| `get()` | 101-144 | `def get(...)` | `async def get(...)` |
| `register()` | 146-173 | `def register(...)` | `async def register(...)` |
| `upsert()` | 175-212 | `def upsert(...)` | `async def upsert(...)` |
| `promote()` | 214-279 | `def promote(...)` | `async def promote(...)` |
| `block()` | 281-336 | `def block(...)` | `async def block(...)` |
| `get_audit_trail()` | 360-400 | `def get_audit_trail(...)` | `async def get_audit_trail(...)` |

**SQL Pattern Conversions:**

| Line | Current | Target |
|------|---------|--------|
| 81-83 | `conn.execute(...).fetchall()` | `await conn.fetch(...)` |
| 125-129 | `conn.execute(...).fetchone()` | `await conn.fetchrow(...)` |
| 163-169 | `conn.execute(INSERT ...)` | `await conn.execute(INSERT ...)` |
| 201-204 | `ON CONFLICT(...) DO UPDATE SET` | Same (PostgreSQL native) |

**Exception Handling:**

| Line | Current | Target |
|------|---------|--------|
| 170 | `except sqlite3.IntegrityError as exc:` | `except asyncpg.UniqueViolationError as exc:` |

**Thread Safety Considerations:**

The `threading.RLock` at line 66 is used for cache thread safety. Since we're moving to async:

- Keep `threading.RLock` for cache access (cache operations are CPU-bound, not I/O)
- OR convert to `asyncio.Lock` if all callers are async

---

#### Issue 3.2.2.2: Convert Minimal Gate to asyncpg

**File:** `k0/gate/minimal_gate.py` (1082 lines)

**Purpose:** Central gate enforcing envelope correctness contracts. Validates signatures, payload hashes, size limits, schema status, and provisioning.

**Architecture:**

- `GateOutcome` — dataclass for validation result
- `MinimalGate` — main validation class with provisioning and schema caches
- Uses `SchemaRegistry` and `ProvisioningLedger` for lookups

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 6 | `import sqlite3` | `import asyncpg` | Replace driver |
| 112 | `connection: sqlite3.Connection \| None = None` | `connection: asyncpg.Connection \| None = None` | Type hint |
| 789 | `connection: sqlite3.Connection \| None = None` | `connection: asyncpg.Connection \| None = None` | Type hint |
| 876 | `connection: sqlite3.Connection \| None = None` | `connection: asyncpg.Connection \| None = None` | Type hint |
| 924 | `connection: sqlite3.Connection \| None = None` | `connection: asyncpg.Connection \| None = None` | Type hint |
| 1026 | `connection: sqlite3.Connection \| None` | `connection: asyncpg.Connection \| None` | Type hint |
| 1043 | `connection: sqlite3.Connection \| None` | `connection: asyncpg.Connection \| None` | Type hint |

**Method Signature Changes:**

| Method | Lines | Current | Target |
|--------|-------|---------|--------|
| `validate()` | 109-200 | `def validate(...)` | `async def validate(...)` |
| `_detect_envelope_replay()` | 876-920 | Uses sync lookup | `async def _detect_envelope_replay(...)` |
| `_lookup_previous_sha256()` | 924-970 | Uses sync lookup | `async def _lookup_previous_sha256(...)` |
| `_lookup_provisioning()` | 1026-1040 | Sync provisioning lookup | `async def _lookup_provisioning(...)` |
| `_check_schema()` | 1043-1060 | Sync schema check | `async def _check_schema(...)` |

**Exception Handling:**

| Line | Current | Target |
|------|---------|--------|
| 904 | `except sqlite3.OperationalError as exc:` | `except asyncpg.PostgresError as exc:` |
| 964 | `except sqlite3.OperationalError as exc:` | `except asyncpg.PostgresError as exc:` |

**Internal Call Changes:**

All internal calls to `SchemaRegistry` and `ProvisioningLedger` must use `await`:

```python
# BEFORE
record = self._registry.get(schema_uri, schema_version, connection=connection)
device = self._provisioning.lookup(tenant, space, device, connection=connection)

# AFTER
record = await self._registry.get(schema_uri, schema_version, connection=connection)
device = await self._provisioning.lookup(tenant, space, device, connection=connection)
```

---

# Phase 4: Driver & Kernel Conversion

## Milestone 4.1: Driver Layer (55 changes)

### Epic 4.1.1: SQLite Driver Replacement

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.1.1.1 | Create PostgreSQL driver | - | New: `k0/drivers/postgres.py` |
| 4.1.1.2 | Deprecate SQLite driver | `k0/drivers/sqlite.py` | 23 |

---

#### Issue 4.1.1.1: Create PostgreSQL Driver

**File:** New `k0/drivers/postgres.py`

**Purpose:** PostgreSQL driver implementing the K0 Driver SPI for ACID operations.

**Template (based on SQLite driver patterns):**

```python
"""PostgreSQL driver for ACID operations (K0 infrastructure + memory tables).

This driver implements the K0 Driver SPI (see K0 README §7) for PostgreSQL backend.
It handles all ACID cohort operations: WAL, receipts, outbox, memory tables.

Architecture:
- ACID transactions via begin/commit/rollback
- Uses asyncpg for native async PostgreSQL access
- Connection pooling via asyncpg.Pool
- Observability: cognitive_trace_id in all operations
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)


class PostgresDriver:
    """PostgreSQL driver for ACID operations."""

    def __init__(self, dsn: str, cognitive_trace_id: str | None = None) -> None:
        self.dsn = dsn
        self.cognitive_trace_id = cognitive_trace_id
        self.conn: asyncpg.Connection | None = None
        self._in_transaction = False

    async def connect(self) -> None:
        if self.conn is not None:
            raise RuntimeError("Connection already established")
        self.conn = await asyncpg.connect(self.dsn)

    async def begin(self) -> None:
        if not self.conn:
            raise RuntimeError("Connection not established")
        if self._in_transaction:
            raise RuntimeError("Transaction already active")
        await self.conn.execute("BEGIN")
        self._in_transaction = True

    async def commit(self) -> None:
        if not self.conn:
            raise RuntimeError("Connection not established")
        if not self._in_transaction:
            raise RuntimeError("No transaction active")
        await self.conn.execute("COMMIT")
        self._in_transaction = False

    async def rollback(self) -> None:
        if not self.conn:
            raise RuntimeError("Connection not established")
        if not self._in_transaction:
            raise RuntimeError("No transaction active")
        await self.conn.execute("ROLLBACK")
        self._in_transaction = False

    async def append(self, table: str, data: dict[str, Any]) -> int:
        if not self.conn:
            raise RuntimeError("Connection not established")
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data))])
        values = list(data.values())
        row_id = await self.conn.fetchval(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id",
            *values,
        )
        return row_id

    async def read(self, table: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.conn:
            raise RuntimeError("Connection not established")
        where_parts = [f"{k} = ${i+1}" for i, k in enumerate(query.keys())]
        where_clause = " AND ".join(where_parts)
        values = list(query.values())
        rows = await self.conn.fetch(
            f"SELECT * FROM {table} WHERE {where_clause}",
            *values,
        )
        return [dict(row) for row in rows]

    async def scan(self, table: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if not self.conn:
            raise RuntimeError("Connection not established")
        rows = await self.conn.fetch(
            f"SELECT * FROM {table} LIMIT $1 OFFSET $2",
            limit, offset,
        )
        return [dict(row) for row in rows]

    async def execute(self, sql: str, *params: Any) -> str:
        if not self.conn:
            raise RuntimeError("Connection not established")
        return await self.conn.execute(sql, *params)

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None
```

---

#### Issue 4.1.1.2: Deprecate SQLite Driver

**File:** `k0/drivers/sqlite.py` (573 lines)

**Strategy:** Archive or delete after PostgreSQL driver is verified. Keep for backward compatibility during migration.

**Files Referencing SQLite Driver:**

| File | Reference | Action |
|------|-----------|--------|
| `k0/drivers/__init__.py` | May export `SQLiteDriver` | Update exports |
| `k0/kernel/dependencies.py` | Driver injection | Point to `PostgresDriver` |
| `k0/outbox/worker.py` | Uses driver for outbox processing | Update to async driver |

---

### Epic 4.1.2: Search Drivers (17 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.1.2.1 | Convert FTS5 to tsvector driver | `k0/drivers/fts5.py` | 6 |
| 4.1.2.2 | Convert FAISS to pgvector driver | `k0/drivers/faiss.py` | 11 |
| 4.1.2.3 | Create pgvector driver | - | New: `k0/drivers/pgvector.py` |

---

#### Issue 4.1.2.1: Convert FTS5 to tsvector Driver

**File:** `k0/drivers/fts5.py` (255 lines)

**Purpose:** FTS5 full-text search indexer for episodic memory events.

**Architecture:**

- `FTS5Driver` — processes outbox entries with `alias='st_fts'`
- Creates FTS5 virtual tables with Porter stemming
- Indexes `st_hipp_events` into `st_hipp_fts`

**Critical SQLite Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 44 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Async pool |
| 109 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` | Async context |
| 110 | `conn.row_factory = sqlite3.Row` | Remove (asyncpg built-in) | Remove |

**FTS5 Virtual Table → tsvector:**

```sql
-- BEFORE (FTS5 virtual table, lines 73-86)
CREATE VIRTUAL TABLE IF NOT EXISTS st_hipp_fts USING fts5(
    event_id UNINDEXED,
    tenant_id UNINDEXED,
    space_id UNINDEXED,
    text,
    text_normalized,
    entities,
    activity_type UNINDEXED,
    event_time_utc UNINDEXED,
    tokenize='porter unicode61'
)

-- AFTER (PostgreSQL regular table with tsvector)
CREATE TABLE IF NOT EXISTS st_hipp_fts (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    text TEXT,
    text_normalized TEXT,
    entities TEXT,
    activity_type TEXT,
    event_time_utc BIGINT,
    content_tsvector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(text, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(entities, '')), 'B')
    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_hipp_fts_tsvector ON st_hipp_fts USING GIN(content_tsvector);
```

**Method Conversions:**

| Method | Current | Target |
|--------|---------|--------|
| `apply()` | `def apply(...)` | `async def apply(...)` |
| `_ensure_fts_table()` | `def _ensure_fts_table(conn)` | `async def _ensure_fts_table(conn)` |
| `_index_event()` | `def _index_event(conn, event_id)` | `async def _index_event(conn, event_id)` |
| `_delete_event()` | `def _delete_event(conn, event_id)` | `async def _delete_event(conn, event_id)` |

---

#### Issue 4.1.2.2: Convert FAISS to pgvector Driver

**File:** `k0/drivers/faiss.py` (366 lines)

**Purpose:** FAISS vector index driver for semantic similarity search.

**Architecture:**

- `FaissDriver` — processes outbox entries with `alias='st_vector'`
- Stores embedding vectors in binary FAISS index file
- Maintains `st_embeddings` metadata table for mapping

**Migration Strategy:** Replace FAISS file-based index with pgvector extension in PostgreSQL.

**Critical Dependencies:**

| Line | Current Code | Target Code | Notes |
|------|--------------|-------------|-------|
| 41 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Async pool |
| 81 | `import faiss` | Remove (use pgvector) | Replace library |
| 90 | `faiss.read_index(...)` | PostgreSQL table query | Data in DB |
| 110 | `faiss.write_index(...)` | Not needed (DB persistence) | Remove |
| 118 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` | Async context |

**st_embeddings Table → pgvector:**

```sql
-- BEFORE (metadata table + FAISS file)
CREATE TABLE IF NOT EXISTS st_embeddings (
    vector_id INTEGER PRIMARY KEY,
    embedding_id TEXT NOT NULL UNIQUE,
    event_id TEXT NOT NULL,
    ...
);
-- Vectors stored in separate FAISS .index file

-- AFTER (single pgvector table)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS st_embeddings (
    id SERIAL PRIMARY KEY,
    embedding_id TEXT NOT NULL UNIQUE,
    event_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    embedding vector(384) NOT NULL,  -- all-MiniLM-L6-v2 dimension
    vector_norm REAL NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_embeddings_ivfflat ON st_embeddings USING ivfflat (embedding vector_cosine_ops);
```

---

#### Issue 4.1.2.3: Create pgvector Driver

**File:** New `k0/drivers/pgvector.py`

**Purpose:** pgvector driver for semantic similarity search replacing FAISS.

**Template:**

```python
"""pgvector driver for semantic similarity search.

Purpose:
    Processes outbox entries with alias='st_vector' to store embedding vectors
    in PostgreSQL with pgvector extension for fast approximate nearest neighbor search.

Architecture:
    - Native PostgreSQL storage (no separate index file)
    - Uses IVFFlat or HNSW indexes for ANN search
    - Supports incremental updates
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import asyncpg
import numpy as np

from k0.uow.postgres_pool import async_connection_scope

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)


class PgvectorDriver:
    """pgvector driver for semantic similarity search."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    async def apply(self, entry: "OutboxEntry") -> None:
        """Process outbox entry - store vector in pgvector table."""
        async with async_connection_scope() as conn:
            payload = json.loads(entry.payload)
            embedding_id = payload.get("embedding_id")
            action = payload.get("action", "add")

            if action == "add":
                await self._add_vector(conn, embedding_id)
            elif action == "delete":
                await self._delete_vector(conn, embedding_id)

    async def _add_vector(self, conn: asyncpg.Connection, embedding_id: str) -> None:
        """Add vector from embedding queue to pgvector table."""
        row = await conn.fetchrow(
            "SELECT embedding_id, event_id, tenant_id, space_id, vector_blob "
            "FROM st_embedding_queue WHERE embedding_id = $1 AND status = 'READY'",
            embedding_id,
        )
        if not row:
            logger.warning(f"Embedding {embedding_id} not found or not ready")
            return

        vector = np.frombuffer(row["vector_blob"], dtype=np.float32)
        vector_norm = float(np.linalg.norm(vector))

        await conn.execute(
            """
            INSERT INTO st_embeddings (embedding_id, event_id, tenant_id, space_id, embedding, vector_norm)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (embedding_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                vector_norm = EXCLUDED.vector_norm,
                indexed_at = NOW()
            """,
            row["embedding_id"],
            row["event_id"],
            row["tenant_id"],
            row["space_id"],
            vector.tolist(),
            vector_norm,
        )

    async def _delete_vector(self, conn: asyncpg.Connection, embedding_id: str) -> None:
        """Delete vector from pgvector table."""
        await conn.execute(
            "DELETE FROM st_embeddings WHERE embedding_id = $1",
            embedding_id,
        )

    async def search(
        self,
        query_vector: list[float],
        *,
        tenant_id: str,
        space_id: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search for similar vectors using pgvector."""
        async with async_connection_scope() as conn:
            if space_id:
                rows = await conn.fetch(
                    """
                    SELECT embedding_id, event_id, 1 - (embedding <=> $1::vector) as similarity
                    FROM st_embeddings
                    WHERE tenant_id = $2 AND space_id = $3
                    ORDER BY embedding <=> $1::vector
                    LIMIT $4
                    """,
                    query_vector, tenant_id, space_id, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT embedding_id, event_id, 1 - (embedding <=> $1::vector) as similarity
                    FROM st_embeddings
                    WHERE tenant_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    query_vector, tenant_id, limit,
                )
            return [dict(row) for row in rows]
```

---

### Epic 4.1.3: Embedding Queue (15 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.1.3.1 | Convert Embedding Queue to asyncpg | `k0/drivers/embedding_queue.py` | 15 |

---

#### Issue 4.1.3.1: Convert Embedding Queue to asyncpg

**File**: `k0/drivers/embedding_queue.py` (376 lines)

**Purpose**: Background embedding queue worker that computes vector embeddings using sentence-transformers model. Processes jobs from `st_embedding_queue` table with status lifecycle (PENDING → IN_PROGRESS → READY/FAILED).

**Key Classes/Functions**:

- `EmbeddingQueueDriver` - Main driver class with sync methods
- `apply()` - Main entry point, claims and processes pending jobs
- `_compute_embedding()` - Generates vectors using sentence-transformers
- `_retry_embedding()` - Handles retries with exponential backoff
- `_cancel_embedding()` - Marks jobs as FAILED_PERMANENT
- `_mark_failed()` - Sets FAILED_RETRYABLE with backoff timestamp
- `_enqueue_vector_indexing()` - Writes to st_outbox for FAISS indexing
- `build_driver()` - Factory function

**Current State (SQLite)**:

```python
# Line 41
from k0.uow.connection_pool import connection_scope

# Line 109-110
with connection_scope() as conn:
    conn.row_factory = sqlite3.Row

# Lines 116-122
cursor = conn.execute(
    """
    SELECT job_id, embedding_id, event_id, text
    FROM st_embedding_queue
    WHERE status = 'PENDING'
    ORDER BY priority DESC, created_at ASC
    LIMIT ?
    """,
    (batch_size,),
)

# Lines 136-145
conn.execute(
    """
    UPDATE st_embedding_queue
    SET status = 'IN_PROGRESS', updated_at = ?
    WHERE job_id = ?
    """,
    (self._current_timestamp(), job_id),
)
conn.commit()

# Lines 210-219
conn.execute(
    """
    UPDATE st_embedding_queue
    SET
        status = 'READY',
        vector_json = ?,
        attempt_count = attempt_count + 1,
        updated_at = ?
    WHERE job_id = ?
""",
    (vector_json, self._current_timestamp(), job_id),
)

# Lines 327-334
conn.execute(
    """
    INSERT INTO st_outbox (topic, alias, payload, status, created_at, updated_at)
    VALUES ('p02.vector.ready.v1', 'st_vector', ?, 'PENDING', ?, ?)
""",
    (json.dumps(payload), self._current_timestamp(), self._current_timestamp()),
)
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 41
from k0.uow.postgres_pool import async_connection_scope

# Line 109-110
async with async_connection_scope() as conn:
    # No row_factory needed - asyncpg returns Record objects

# Lines 116-122
rows = await conn.fetch(
    """
    SELECT job_id, embedding_id, event_id, text
    FROM st_embedding_queue
    WHERE status = 'PENDING'
    ORDER BY priority DESC, created_at ASC
    LIMIT $1
    """,
    batch_size,
)

# Lines 136-145
await conn.execute(
    """
    UPDATE st_embedding_queue
    SET status = 'IN_PROGRESS', updated_at = $1
    WHERE job_id = $2
    """,
    self._current_timestamp(), job_id,
)
# No explicit commit - handled by async context manager

# Lines 210-219
await conn.execute(
    """
    UPDATE st_embedding_queue
    SET
        status = 'READY',
        vector_json = $1,
        attempt_count = attempt_count + 1,
        updated_at = $2
    WHERE job_id = $3
    """,
    vector_json, self._current_timestamp(), job_id,
)

# Lines 327-334
await conn.execute(
    """
    INSERT INTO st_outbox (topic, alias, payload, status, created_at, updated_at)
    VALUES ('p02.vector.ready.v1', 'st_vector', $1, 'PENDING', $2, $3)
    """,
    json.dumps(payload), self._current_timestamp(), self._current_timestamp(),
)
```

**Detailed Line-by-Line Changes**:

| Line | Current Code | Target Code | Change Type |
|------|--------------|-------------|-------------|
| 3 | `import sqlite3` | *Remove* | Import removal |
| 41 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Import change |
| 75 | `def apply(self, batch_size: int = 10) -> int:` | `async def apply(self, batch_size: int = 10) -> int:` | Async conversion |
| 109 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` | Async context |
| 110 | `conn.row_factory = sqlite3.Row` | *Remove line* | Row factory removal |
| 116-122 | `cursor = conn.execute(...)` | `rows = await conn.fetch(...)` | Async query |
| 119 | `LIMIT ?` | `LIMIT $1` | Param style |
| 122 | `(batch_size,)` | `batch_size` | Tuple to positional |
| 124 | `jobs = cursor.fetchall()` | *Remove* (use rows directly) | Fetch pattern |
| 136-145 | `conn.execute(UPDATE...)` | `await conn.execute(UPDATE...)` | Async execute |
| 139 | `updated_at = ?` | `updated_at = $1` | Param style |
| 140 | `WHERE job_id = ?` | `WHERE job_id = $2` | Param style |
| 145 | `conn.commit()` | *Remove* | Commit removal |
| 163 | `def _compute_embedding(self, conn, job_id: int, embedding_id: str):` | `async def _compute_embedding(self, conn, job_id: int, embedding_id: str):` | Async method |
| 183-186 | `cursor = conn.execute(SELECT text...)` | `row = await conn.fetchrow(SELECT text...)` | Async query |
| 185 | `WHERE embedding_id = ?` | `WHERE embedding_id = $1` | Param style |
| 189 | `row = cursor.fetchone()` | *Remove* (use row directly) | Fetch pattern |
| 210-221 | `conn.execute(UPDATE st_embedding_queue...)` | `await conn.execute(...)` | Async execute |
| 216-218 | `?, ?, ?` placeholders | `$1, $2, $3` | Param style |
| 226 | `self._enqueue_vector_indexing(conn, embedding_id)` | `await self._enqueue_vector_indexing(conn, embedding_id)` | Async call |
| 228 | `conn.commit()` | *Remove* | Commit removal |
| 231 | `def _retry_embedding(self, conn, job_id: int, embedding_id: str):` | `async def _retry_embedding(self, conn, job_id: int, embedding_id: str):` | Async method |
| 240-246 | `cursor = conn.execute(SELECT attempt_count...)` | `row = await conn.fetchrow(...)` | Async query |
| 244 | `WHERE job_id = ?` | `WHERE job_id = $1` | Param style |
| 249 | `row = cursor.fetchone()` | *Remove* (use row directly) | Fetch pattern |
| 255-262 | `conn.execute(UPDATE...FAILED_PERMANENT...)` | `await conn.execute(...)` | Async execute |
| 260 | `?, ?` placeholders | `$1, $2` | Param style |
| 263 | `conn.commit()` | *Remove* | Commit removal |
| 268 | `self._compute_embedding(conn, job_id, embedding_id)` | `await self._compute_embedding(conn, job_id, embedding_id)` | Async call |
| 270 | `def _cancel_embedding(self, conn, job_id: int):` | `async def _cancel_embedding(self, conn, job_id: int):` | Async method |
| 278-284 | `conn.execute(UPDATE...FAILED_PERMANENT...)` | `await conn.execute(...)` | Async execute |
| 282 | `?, ?` placeholders | `$1, $2` | Param style |
| 286 | `conn.commit()` | *Remove* | Commit removal |
| 289 | `def _mark_failed(self, conn, job_id: int, error_msg: str):` | `async def _mark_failed(self, conn, job_id: int, error_msg: str):` | Async method |
| 298-303 | `cursor = conn.execute(SELECT attempt_count...)` | `row = await conn.fetchrow(...)` | Async query |
| 301 | `WHERE job_id = ?` | `WHERE job_id = $1` | Param style |
| 306 | `row = cursor.fetchone()` | *Remove* (use row directly) | Fetch pattern |
| 315-325 | `conn.execute(UPDATE...FAILED_RETRYABLE...)` | `await conn.execute(...)` | Async execute |
| 322-323 | `?, ?, ?, ?` placeholders | `$1, $2, $3, $4` | Param style |
| 326 | `conn.commit()` | *Remove* | Commit removal |
| 329 | `def _enqueue_vector_indexing(self, conn, embedding_id: str):` | `async def _enqueue_vector_indexing(self, conn, embedding_id: str):` | Async method |
| 339-345 | `conn.execute(INSERT INTO st_outbox...)` | `await conn.execute(...)` | Async execute |
| 342 | `?, ?, ?` placeholders | `$1, $2, $3` | Param style |

**Row Access Pattern Changes**:

| SQLite Pattern | asyncpg Pattern |
|----------------|-----------------|
| `row["job_id"]` | `row["job_id"]` (same - Record supports dict access) |
| `cursor.fetchone()` | `await conn.fetchrow()` |
| `cursor.fetchall()` | `await conn.fetch()` |
| `cursor.rowcount` | Check return value or use `RETURNING` |

**Test File Updates Required**:

- `tests/k0/drivers/test_embedding_queue.py` - All tests must use async/await

---

## Milestone 4.2: Kernel Layer (45 changes)

### Epic 4.2.1: Syscalls Async Conversion (35 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.2.1.1 | Remove run_in_executor (lines 281-410) | `k0/kernel/syscalls.py` | 5 |
| 4.2.1.2 | Remove run_in_executor (lines 705-1091) | `k0/kernel/syscalls.py` | 5 |
| 4.2.1.3 | Remove run_in_executor (lines 1263-1580) | `k0/kernel/syscalls.py` | 5 |
| 4.2.1.4 | Remove run_in_executor (lines 2157-2425) | `k0/kernel/syscalls.py` | 5 |
| 4.2.1.5 | Convert all execute() to asyncpg | `k0/kernel/syscalls.py` | 15 |

---

#### Issue 4.2.1.1: Remove run_in_executor (lines 281-410)

**File**: `k0/kernel/syscalls.py` (2667 lines)

**Purpose**: Syscalls class provides capability-gated storage access for pipelines with audit trail. All methods use `run_in_executor` pattern to wrap sync SQLite operations.

**Methods in Scope (lines 281-410)**:

- `hipp_events_upsert()` - Write to st_hipp_events table
- `pipeline_processed_upsert()` - Write to st_pipeline_processed table

**Current Pattern (SQLite + run_in_executor)**:

```python
# Lines 281-294 (hipp_events_upsert)
async with self._uow_factory() as uow:
    conn = uow._connection
    if conn is None:
        raise RuntimeError("UnitOfWork connection not initialized")

    try:
        loop = asyncio.get_running_loop()
        cursor = await loop.run_in_executor(
            None,
            lambda: conn.execute(
                """
                INSERT OR IGNORE INTO st_hipp_events (
                    event_id, tenant_id, space_id, text, ...
                ) VALUES (?, ?, ?, ?, ...)
                """,
                (event_id, tenant_id, space_id, text, ...),
            ),
        )

# Lines 398-410 (pipeline_processed_upsert)
loop = asyncio.get_running_loop()
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(
        """
        INSERT OR REPLACE INTO st_pipeline_processed (
            pipeline_id, space_id, wal_pos, processed_at
        ) VALUES (?, ?, ?, ?)
        """,
        (pipeline_id, space_id, wal_pos, processed_at),
    ),
)
```

**Target Pattern (Native asyncpg)**:

```python
# Lines 281-294 (hipp_events_upsert)
async with self._uow_factory() as uow:
    conn = uow._connection
    if conn is None:
        raise RuntimeError("UnitOfWork connection not initialized")

    try:
        result = await conn.execute(
            """
            INSERT INTO st_hipp_events (
                event_id, tenant_id, space_id, text, ...
            ) VALUES ($1, $2, $3, $4, ...)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event_id, tenant_id, space_id, text, ...,
        )

# Lines 398-410 (pipeline_processed_upsert)
result = await conn.execute(
    """
    INSERT INTO st_pipeline_processed (
        pipeline_id, space_id, wal_pos, processed_at
    ) VALUES ($1, $2, $3, $4)
    ON CONFLICT (pipeline_id, space_id, wal_pos) DO UPDATE SET
        processed_at = EXCLUDED.processed_at
    """,
    pipeline_id, space_id, wal_pos, processed_at,
)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 4 | `import asyncio` | Keep (for other async operations) |
| 281 | `loop = asyncio.get_running_loop()` | *Remove* |
| 282-294 | `cursor = await loop.run_in_executor(None, lambda: conn.execute(...))` | `result = await conn.execute(...)` |
| 285 | `INSERT OR IGNORE INTO` | `INSERT INTO ... ON CONFLICT DO NOTHING` |
| 289 | `VALUES (?, ?, ?, ?, ...)` | `VALUES ($1, $2, $3, $4, ...)` |
| 293 | `(event_id, tenant_id, ...),` | `event_id, tenant_id, ...` (no tuple) |
| 296 | `inserted = cursor.rowcount > 0` | `inserted = result != 'INSERT 0'` (asyncpg returns status string) |
| 398 | `loop = asyncio.get_running_loop()` | *Remove* |
| 399-410 | `cursor = await loop.run_in_executor(...)` | `result = await conn.execute(...)` |
| 401 | `INSERT OR REPLACE INTO` | `INSERT INTO ... ON CONFLICT DO UPDATE` |
| 405 | `VALUES (?, ?, ?, ?)` | `VALUES ($1, $2, $3, $4)` |
| 409 | `(pipeline_id, space_id, wal_pos, processed_at),` | `pipeline_id, space_id, wal_pos, processed_at` |

---

#### Issue 4.2.1.2: Remove run_in_executor (lines 705-1091)

**Methods in Scope**:

- `relationships_query()` (lines 700-730) - Query st_relationships
- `embedding_enqueue()` (lines 733-900) - Write to st_embedding_queue
- `outbox_emit_batch()` (lines 902-1091) - Batch write to st_outbox

**Current Pattern**:

```python
# Lines 705-710 (relationships_query)
result = await asyncio.get_event_loop().run_in_executor(
    None,
    lambda: conn.execute(query, (actor_id,)).fetchall(),
)

# Lines 845-867 (embedding_enqueue)
loop = asyncio.get_running_loop()
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(
        """
        INSERT OR IGNORE INTO st_embedding_queue (
            embedding_id, event_id, wal_pos,
            tenant_id, space_id, vector_kind, ...
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (embedding_id, event_id, wal_pos, ...),
    ),
)

# Lines 1030-1032 (outbox_emit_batch)
loop = asyncio.get_running_loop()
await loop.run_in_executor(None, uow.connection.executemany, insert_sql, records)
```

**Target Pattern**:

```python
# Lines 705-710 (relationships_query)
rows = await conn.fetch(query, actor_id)

# Lines 845-867 (embedding_enqueue)
result = await conn.execute(
    """
    INSERT INTO st_embedding_queue (
        embedding_id, event_id, wal_pos,
        tenant_id, space_id, vector_kind, ...
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    ON CONFLICT (embedding_id) DO NOTHING
    """,
    embedding_id, event_id, wal_pos, ...,
)

# Lines 1030-1032 (outbox_emit_batch)
await conn.executemany(insert_sql, records)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 705 | `result = await asyncio.get_event_loop().run_in_executor(...)` | `rows = await conn.fetch(query, actor_id)` |
| 707 | `conn.execute(query, (actor_id,)).fetchall()` | *Merged into fetch()* |
| 713 | `relationships = [(row[0], row[1]) for row in result]` | Keep (asyncpg Record supports indexing) |
| 845 | `loop = asyncio.get_running_loop()` | *Remove* |
| 846-867 | `cursor = await loop.run_in_executor(None, lambda: conn.execute(...))` | `result = await conn.execute(...)` |
| 850 | `INSERT OR IGNORE INTO` | `INSERT INTO ... ON CONFLICT DO NOTHING` |
| 858 | `VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` | `VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)` |
| 869 | `inserted = cursor.rowcount > 0` | `inserted = result != 'INSERT 0'` |
| 1030 | `loop = asyncio.get_running_loop()` | *Remove* |
| 1031-1032 | `await loop.run_in_executor(None, uow.connection.executemany, ...)` | `await conn.executemany(insert_sql, records)` |

---

#### Issue 4.2.1.3: Remove run_in_executor (lines 1263-1580)

**Methods in Scope**:

- `vec_write()` (lines 1175-1260) - Write to st_vec
- `vec_query()` (lines 1325-1460) - Query st_vec with pagination
- `vec_update_status()` (lines 1475-1580) - Update st_vec status

**Current Pattern**:

```python
# Lines 1263-1290 (vec_write)
loop = asyncio.get_running_loop()
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(
        """
        INSERT OR IGNORE INTO st_vec (
            embedding_id, event_id, tenant_id, space_id,
            vector, vector_dim, model_id, status, ...
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (embedding_id, event_id, tenant_id, ...),
    ),
)

# Lines 1420-1425 (vec_query - count)
count_sql = f"SELECT COUNT(*) FROM st_vec WHERE {where_clause}"
total_result = await loop.run_in_executor(
    None,
    lambda: conn.execute(count_sql, params).fetchone(),
)

# Lines 1440-1445 (vec_query - paginated)
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(query_sql, params + [limit, offset]),
)
rows = cursor.fetchall()

# Lines 1540-1560 (vec_update_status)
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(
        "UPDATE st_vec SET status = ?, indexed_at = ?, updated_at = ? WHERE embedding_id = ?",
        (status, indexed_at, updated_at, embedding_id),
    ),
)
```

**Target Pattern**:

```python
# Lines 1263-1290 (vec_write)
result = await conn.execute(
    """
    INSERT INTO st_vec (
        embedding_id, event_id, tenant_id, space_id,
        vector, vector_dim, model_id, status, ...
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    ON CONFLICT (embedding_id) DO NOTHING
    """,
    embedding_id, event_id, tenant_id, ...,
)

# Lines 1420-1425 (vec_query - count)
count_sql = f"SELECT COUNT(*) FROM st_vec WHERE {where_clause}"
total_result = await conn.fetchval(count_sql, *params)
total = total_result if total_result else 0

# Lines 1440-1445 (vec_query - paginated)
rows = await conn.fetch(query_sql, *params, limit, offset)

# Lines 1540-1560 (vec_update_status)
result = await conn.execute(
    "UPDATE st_vec SET status = $1, indexed_at = $2, updated_at = $3 WHERE embedding_id = $4",
    status, indexed_at, updated_at, embedding_id,
)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 1263 | `loop = asyncio.get_running_loop()` | *Remove* |
| 1264-1290 | `cursor = await loop.run_in_executor(...)` | `result = await conn.execute(...)` |
| 1268 | `INSERT OR IGNORE INTO` | `INSERT INTO ... ON CONFLICT DO NOTHING` |
| 1275 | `VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` | `VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)` |
| 1420 | `await loop.run_in_executor(None, lambda: conn.execute(count_sql, params).fetchone())` | `await conn.fetchval(count_sql, *params)` |
| 1422 | `total = total_result[0] if total_result else 0` | `total = total_result if total_result else 0` |
| 1440 | `cursor = await loop.run_in_executor(...)` | `rows = await conn.fetch(...)` |
| 1442 | `params + [limit, offset]` | `*params, limit, offset` |
| 1445 | `rows = cursor.fetchall()` | *Remove* (already have rows) |
| 1540 | `loop = asyncio.get_running_loop()` | *Remove* |
| 1541-1560 | `cursor = await loop.run_in_executor(...)` | `result = await conn.execute(...)` |
| 1545 | `?, ?, ?, ?` placeholders | `$1, $2, $3, $4` |

---

#### Issue 4.2.1.4: Remove run_in_executor (lines 2157-2425)

**Methods in Scope**:

- `hipp_events_query()` (lines 2050-2220) - Query st_hipp_events with pagination
- `hipp_events_update_embedding_status()` (lines 2230-2350) - Update embedding status
- `query_count()` (lines 2360-2425) - Generic count query for scheduler

**Current Pattern**:

```python
# Lines 2157-2165 (hipp_events_query - count)
count_sql = f"SELECT COUNT(*) FROM st_hipp_events WHERE {where_clause}"
total_result = await loop.run_in_executor(
    None,
    lambda: conn.execute(count_sql, params).fetchone(),
)

# Lines 2170-2180 (hipp_events_query - paginated)
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(query_sql, params + [limit, offset]),
)
rows = cursor.fetchall()

# Lines 2310-2330 (hipp_events_update_embedding_status)
cursor = await loop.run_in_executor(
    None,
    lambda: conn.execute(
        "UPDATE st_hipp_events SET embedding_status = ?, embedding_id = ?, updated_at = ? WHERE event_id = ?",
        (embedding_status, embedding_id, updated_at, event_id),
    ),
)

# Lines 2400-2415 (query_count)
loop = asyncio.get_running_loop()
sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
result = await loop.run_in_executor(
    None,
    lambda: conn.execute(sql, params).fetchone(),
)
```

**Target Pattern**:

```python
# Lines 2157-2165 (hipp_events_query - count)
count_sql = f"SELECT COUNT(*) FROM st_hipp_events WHERE {where_clause}"
total = await conn.fetchval(count_sql, *params)

# Lines 2170-2180 (hipp_events_query - paginated)
rows = await conn.fetch(query_sql, *params, limit, offset)

# Lines 2310-2330 (hipp_events_update_embedding_status)
result = await conn.execute(
    "UPDATE st_hipp_events SET embedding_status = $1, embedding_id = $2, updated_at = $3 WHERE event_id = $4",
    embedding_status, embedding_id, updated_at, event_id,
)

# Lines 2400-2415 (query_count)
sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
count = await conn.fetchval(sql, *params)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 2157 | `await loop.run_in_executor(None, lambda: conn.execute(count_sql, params).fetchone())` | `total = await conn.fetchval(count_sql, *params)` |
| 2160 | `total = total_result[0] if total_result else 0` | `total = total if total else 0` |
| 2170 | `cursor = await loop.run_in_executor(...)` | `rows = await conn.fetch(...)` |
| 2172 | `params + [limit, offset]` | `*params, limit, offset` |
| 2175 | `rows = cursor.fetchall()` | *Remove* |
| 2310 | `loop = asyncio.get_running_loop()` | *Remove* |
| 2311-2330 | `cursor = await loop.run_in_executor(...)` | `result = await conn.execute(...)` |
| 2318 | `?, ?, ?, ?` placeholders | `$1, $2, $3, $4` |
| 2320 | `(embedding_status, embedding_id, updated_at, event_id),` | `embedding_status, embedding_id, updated_at, event_id` |
| 2323 | `updated = cursor.rowcount > 0` | `updated = result == 'UPDATE 1'` |
| 2400 | `loop = asyncio.get_running_loop()` | *Remove* |
| 2402 | `await loop.run_in_executor(None, lambda: conn.execute(sql, params).fetchone())` | `count = await conn.fetchval(sql, *params)` |
| 2405 | `count = result[0] if result else 0` | `count = count if count else 0` |

---

#### Issue 4.2.1.5: Convert all execute() to asyncpg

**Scope**: Global search and replace for remaining SQL patterns across all Syscalls methods.

**SQL Syntax Conversions Required**:

| SQLite Syntax | PostgreSQL Syntax |
|---------------|-------------------|
| `INSERT OR IGNORE INTO` | `INSERT INTO ... ON CONFLICT DO NOTHING` |
| `INSERT OR REPLACE INTO` | `INSERT INTO ... ON CONFLICT DO UPDATE SET ...` |
| `?` placeholder | `$1, $2, $3...` positional params |
| `LIMIT ?` | `LIMIT $N` |
| `datetime('now')` | `NOW()` or `CURRENT_TIMESTAMP` |
| `strftime('%s', 'now')` | `EXTRACT(EPOCH FROM NOW())::int` |
| `json_extract(col, '$.key')` | `col->>'key'` or `col->'key'` |
| `LIKE '%' || ? || '%'` | `ILIKE '%' || $1 || '%'` |

**Connection Method Conversions**:

| SQLite Method | asyncpg Method |
|---------------|----------------|
| `conn.execute(sql, params)` | `await conn.execute(sql, *params)` |
| `conn.executemany(sql, records)` | `await conn.executemany(sql, records)` |
| `cursor.fetchone()` | `await conn.fetchrow(sql, *params)` |
| `cursor.fetchall()` | `await conn.fetch(sql, *params)` |
| `cursor.rowcount` | Parse result string or use `RETURNING` |
| `conn.commit()` | *Handled by async context manager* |

**Files Affected by Syscalls Changes**:

- `k0/kernel/syscalls.py` - Primary changes
- `tests/k0/kernel/test_syscalls.py` - All tests need async/await updates

---

### Epic 4.2.2: Kernel Dependencies (10 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.2.2.1 | Update dependencies imports | `k0/kernel/dependencies.py` | 8 |
| 4.2.2.2 | Update app initialization | `k0/kernel/app.py` | 2 |

---

#### Issue 4.2.2.1: Update dependencies imports

**File**: `k0/kernel/dependencies.py` (248 lines)

**Purpose**: Dependency wiring for FastAPI routes. Provides `ConnectionFactory`, `database_session()`, and `RequestDependencyProvider`.

**Current State (SQLite)**:

```python
# Line 11
import sqlite3

# Line 25
def database_session() -> Iterator[sqlite3.Connection]:

# Line 69
ConnectionFactory = Callable[[], sqlite3.Connection]

# Lines 195-197
def _default_connection_factory(self) -> sqlite3.Connection:
    """Create a new SQLite connection using the configured pool."""
    from ..uow.connection_pool import connection_scope
    # ... returns sync connection
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 11
import asyncpg

# Line 25
async def database_session() -> AsyncIterator[asyncpg.Connection]:

# Line 69
ConnectionFactory = Callable[[], Coroutine[Any, Any, asyncpg.Connection]]

# Lines 195-197
async def _default_connection_factory(self) -> asyncpg.Connection:
    """Create a new asyncpg connection using the configured pool."""
    from ..uow.postgres_pool import get_pool
    pool = await get_pool()
    return await pool.acquire()
```

**Detailed Line-by-Line Changes**:

| Line | Current Code | Target Code | Change Type |
|------|--------------|-------------|-------------|
| 11 | `import sqlite3` | `import asyncpg` | Import change |
| 13 | (add) | `from typing import AsyncIterator, Coroutine` | Import addition |
| 25 | `def database_session() -> Iterator[sqlite3.Connection]:` | `async def database_session() -> AsyncIterator[asyncpg.Connection]:` | Async generator |
| 27 | `from ..uow.connection_pool import connection_scope` | `from ..uow.postgres_pool import async_connection_scope` | Import change |
| 29-32 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` | Async context |
| 33 | `yield conn` | `yield conn` (keep) | Same |
| 69 | `ConnectionFactory = Callable[[], sqlite3.Connection]` | `ConnectionFactory = Callable[[], Coroutine[Any, Any, asyncpg.Connection]]` | Type change |
| 195 | `def _default_connection_factory(self) -> sqlite3.Connection:` | `async def _default_connection_factory(self) -> asyncpg.Connection:` | Async method |
| 197 | `from ..uow.connection_pool import connection_scope` | `from ..uow.postgres_pool import get_pool` | Import change |
| 198-200 | `with connection_scope() as conn: return conn` | `pool = await get_pool(); return await pool.acquire()` | Async pool |

**Type Annotation Updates Required**:

| Current Type | Target Type |
|--------------|-------------|
| `sqlite3.Connection` | `asyncpg.Connection` |
| `Iterator[sqlite3.Connection]` | `AsyncIterator[asyncpg.Connection]` |
| `Callable[[], sqlite3.Connection]` | `Callable[[], Coroutine[Any, Any, asyncpg.Connection]]` |

**FastAPI Dependency Updates**:

- `Depends(database_session)` calls must be in async route handlers
- Connection objects are now async and require `await` for operations

---

#### Issue 4.2.2.2: Update app initialization

**File**: `k0/kernel/app.py` (1526 lines)

**Purpose**: FastAPI application factory for K0 kernel. Initializes connection pool, storage components, and routes.

**Current State (SQLite)**:

```python
# Line 7
import sqlite3

# Line 54
from ..uow.connection_pool import configure_pool, shutdown_pool

# Line 365
database_path = Path(getattr(settings.database, "path")).resolve()
configure_pool(database_path)
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 7
# import sqlite3  <- REMOVE

# Line 54
from ..uow.postgres_pool import init_pool, close_pool

# Line 365 (inside async lifespan)
database_url = settings.database.url  # PostgreSQL connection string
await init_pool(database_url)
```

**Detailed Changes**:

| Line | Current Code | Target Code | Change Type |
|------|--------------|-------------|-------------|
| 7 | `import sqlite3` | *Remove* | Import removal |
| 54 | `from ..uow.connection_pool import configure_pool, shutdown_pool` | `from ..uow.postgres_pool import init_pool, close_pool` | Import change |
| 365 | `database_path = Path(getattr(settings.database, "path")).resolve()` | `database_url = settings.database.url` | Config change |
| 366 | `configure_pool(database_path)` | *Move to lifespan async context* | Async init |

**Lifespan Context Manager Updates**:

Current (sync pool init outside lifespan):

```python
database_path = Path(getattr(settings.database, "path")).resolve()
configure_pool(database_path)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ... startup logic
    yield
    # ... shutdown logic
    shutdown_pool()
```

Target (async pool init inside lifespan):

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize async pool
    database_url = settings.database.url
    await init_pool(database_url)

    # ... startup logic
    yield
    # ... shutdown logic
    await close_pool()
```

**Configuration Schema Changes** (in `k0/kernel/config.py`):

| Current Field | Target Field |
|---------------|--------------|
| `database.path: str` | `database.url: str` (PostgreSQL DSN) |
| `database.fsync_mode: str` | `database.pool_min_size: int` |
| | `database.pool_max_size: int` |
| | `database.ssl_mode: str` |

**Storage Component Initialization Updates**:
All storage components that receive `connection_factory` must be updated:

- `SchemaRegistry` - async connection factory
- `ProvisioningLedger` - async connection factory
- `WriteAheadLog` - async connection factory
- `OutboxStore` - async connection factory
- `OffsetStore` - async connection factory
- `ReceiptStore` - async connection factory
- `DeadLetterQueue` - async connection factory
- `ObligationStore` - async connection factory

**Test File Updates Required**:

- `tests/k0/kernel/test_app.py` - Mock async pool
- `tests/k0/kernel/test_dependencies.py` - All tests need async/await

---

## Milestone 4.3: Policy & Query Layers (45 changes)

### Epic 4.3.1: Policy Enforcers (34 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.3.1.1 | Convert Retention Enforcer | `k0/policy/retention_enforcer.py` | 19 |
| 4.3.1.2 | Convert ACL Enforcer | `k0/policy/acl_enforcer.py` | 15 |

---

#### Issue 4.3.1.1: Convert Retention Enforcer

**File**: `k0/policy/retention_enforcer.py` (327 lines)

**Purpose**: Applies retention policies from `st_retention_policy` table. Archives expired data to blob storage or performs hard deletes. Runs as nightly background job.

**Key Classes/Functions**:

- `RetentionPolicy` - Dataclass for retention policy
- `ArchiveManifest` - Dataclass for archived data entry
- `RetentionEnforcer` - Main enforcer class
- `apply_policies()` - Apply all enabled policies (nightly job)
- `get_expired_resources()` - Query expired resources for a policy

**Current State (SQLite)**:

```python
# Line 12
import sqlite3

# Line 18
from k0.uow.connection_pool import connection_scope

# Lines 82-83
def apply_policies(
    self,
    *,
    dry_run: bool = False,
    connection: Optional[sqlite3.Connection] = None,
) -> dict:

# Lines 96-97
resolve = connection if connection else connection_scope()
with resolve as conn:

# Lines 166-171
policy_row = conn.execute(
    "SELECT * FROM st_retention_policy WHERE policy_id = ?",
    (policy_id,),
).fetchone()
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 12
import asyncpg

# Line 18
from k0.uow.postgres_pool import async_connection_scope

# Lines 82-83
async def apply_policies(
    self,
    *,
    dry_run: bool = False,
    connection: Optional[asyncpg.Connection] = None,
) -> dict:

# Lines 96-97
resolve = connection if connection else async_connection_scope()
async with resolve as conn:

# Lines 166-171
policy_row = await conn.fetchrow(
    "SELECT * FROM st_retention_policy WHERE policy_id = $1",
    policy_id,
)
```

**Detailed Line-by-Line Changes**:

| Line | Current Code | Target Code | Change Type |
|------|--------------|-------------|-------------|
| 12 | `import sqlite3` | `import asyncpg` | Import change |
| 18 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Import change |
| 29 | `Optional[sqlite3.Connection]` | `Optional[asyncpg.Connection]` | Type annotation |
| 82 | `def apply_policies(...)` | `async def apply_policies(...)` | Async method |
| 87 | `connection: Optional[sqlite3.Connection]` | `connection: Optional[asyncpg.Connection]` | Type annotation |
| 96 | `resolve = connection if connection else connection_scope()` | `resolve = connection if connection else async_connection_scope()` | Context manager |
| 97 | `with resolve as conn:` | `async with resolve as conn:` | Async context |
| 99 | `policies = self._load_policies(conn, enabled_only=True)` | `policies = await self._load_policies(conn, enabled_only=True)` | Async call |
| 103 | `expired = self._get_expired_resources_for_policy(conn, policy)` | `expired = await self._get_expired_resources_for_policy(conn, policy)` | Async call |
| 109 | `self._archive_resource(conn, policy, resource)` | `await self._archive_resource(conn, policy, resource)` | Async call |
| 117 | `self._delete_resource(...)` | `await self._delete_resource(...)` | Async call |
| 123 | `conn.commit()` | *Remove* | Commit removal |
| 147 | `def get_expired_resources(...)` | `async def get_expired_resources(...)` | Async method |
| 152 | `connection: Optional[sqlite3.Connection]` | `connection: Optional[asyncpg.Connection]` | Type annotation |
| 163 | `with resolve as conn:` | `async with resolve as conn:` | Async context |
| 166-169 | `policy_row = conn.execute(...).fetchone()` | `policy_row = await conn.fetchrow(...)` | Async query |
| 168 | `WHERE policy_id = ?` | `WHERE policy_id = $1` | Param style |
| Various | `sqlite3.OperationalError` | `asyncpg.PostgresError` | Exception type |

---

#### Issue 4.3.1.2: Convert ACL Enforcer

**File**: `k0/policy/acl_enforcer.py` (312 lines)

**Purpose**: Row-level permission checks using `st_acl` table. Performance target: <2ms P95.

**Key Classes/Functions**:

- `ACLEntry` - Dataclass for ACL entry
- `ACLEnforcer` - Main enforcer class
- `check_permission()` - Check if principal has permission
- `grant_permission()` - Insert into st_acl
- `revoke_permission()` - Set revoked_at timestamp

**Current State (SQLite)**:

```python
# Line 11
import sqlite3

# Line 17
from k0.uow.connection_pool import connection_scope

# Lines 66-74
def check_permission(
    self,
    resource_type: str,
    resource_id: str,
    principal_id: str,
    permission: str,
    *,
    principal_type: str = "user",
    connection: Optional[sqlite3.Connection] = None,
) -> bool:

# Lines 100-117
result = conn.execute(
    """
    SELECT 1 FROM st_acl
    WHERE resource_type = ?
      AND resource_id = ?
      AND principal_type = ?
      AND principal_id = ?
      AND permission = ?
      AND revoked_at IS NULL
      AND (expires_at IS NULL OR expires_at > ?)
    LIMIT 1
    """,
    (resource_type, resource_id, principal_type, principal_id, permission, now),
).fetchone()
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 11
import asyncpg

# Line 17
from k0.uow.postgres_pool import async_connection_scope

# Lines 66-74
async def check_permission(
    self,
    resource_type: str,
    resource_id: str,
    principal_id: str,
    permission: str,
    *,
    principal_type: str = "user",
    connection: Optional[asyncpg.Connection] = None,
) -> bool:

# Lines 100-117
result = await conn.fetchrow(
    """
    SELECT 1 FROM st_acl
    WHERE resource_type = $1
      AND resource_id = $2
      AND principal_type = $3
      AND principal_id = $4
      AND permission = $5
      AND revoked_at IS NULL
      AND (expires_at IS NULL OR expires_at > $6)
    LIMIT 1
    """,
    resource_type, resource_id, principal_type, principal_id, permission, now,
)
```

**Detailed Line-by-Line Changes**:

| Line | Current Code | Target Code | Change Type |
|------|--------------|-------------|-------------|
| 11 | `import sqlite3` | `import asyncpg` | Import change |
| 17 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Import change |
| 66 | `def check_permission(...)` | `async def check_permission(...)` | Async method |
| 73 | `connection: Optional[sqlite3.Connection]` | `connection: Optional[asyncpg.Connection]` | Type annotation |
| 97 | `with resolve as conn:` | `async with resolve as conn:` | Async context |
| 100-117 | `result = conn.execute(...).fetchone()` | `result = await conn.fetchrow(...)` | Async query |
| 103-109 | `?, ?, ?, ?, ?, ?` placeholders | `$1, $2, $3, $4, $5, $6` | Param style |
| 115 | `(resource_type, resource_id, ...),` | `resource_type, resource_id, ...` | Tuple to positional |
| 117 | `return result is not None` | `return result is not None` | Keep |
| 120 | `sqlite3.OperationalError` | `asyncpg.PostgresError` | Exception type |
| 131 | `def grant_permission(...)` | `async def grant_permission(...)` | Async method |
| 145 | `connection: Optional[sqlite3.Connection]` | `connection: Optional[asyncpg.Connection]` | Type annotation |
| 166 | `with resolve as conn:` | `async with resolve as conn:` | Async context |
| 168-182 | `conn.execute(INSERT INTO st_acl...)` | `await conn.execute(...)` | Async execute |
| 171-181 | `?, ?, ?, ?, ...` placeholders | `$1, $2, $3, $4, ...` | Param style |
| 200 | `def revoke_permission(...)` | `async def revoke_permission(...)` | Async method |
| 210 | `conn.execute(UPDATE st_acl SET revoked_at = ?)` | `await conn.execute(... SET revoked_at = $1 ...)` | Async execute |

---

### Epic 4.3.2: Query Drivers (11 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 4.3.2.1 | Convert Query Drivers to asyncpg | `k0/query/drivers.py` | 11 |

---

#### Issue 4.3.2.1: Convert Query Drivers to asyncpg

**File**: `k0/query/drivers.py` (415 lines)

**Purpose**: Driver registry and implementations for query recall. Contains `WalDriver` and `FtsDriver` for database queries.

**Key Classes/Functions**:

- `DriverRegistry` - Registry that resolves selectors to drivers
- `WalDriver` - Primary driver for WAL slice queries
- `FtsDriver` - Full-text search driver using FTS5
- `AliasDriver` - Placeholder for unsupported types
- `build_default_registry()` - Factory function

**Current State (SQLite)**:

```python
# Line 7
import sqlite3

# Line 14
from k0.uow.connection_pool import connection_scope

# Lines 151-155
with connection_scope() as connection:
    rows = self._fetch_rows(
        connection,
        space_id=context.space_id,
        ...
    )

# Lines 200-207
def _fetch_rows(
    self,
    connection: sqlite3.Connection,
    *,
    space_id: str,
    ...
) -> list[sqlite3.Row]:

# Lines 235-236
return list(connection.execute(statement, params).fetchall())
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 7
import asyncpg

# Line 14
from k0.uow.postgres_pool import async_connection_scope

# Lines 151-155
async with async_connection_scope() as connection:
    rows = await self._fetch_rows(
        connection,
        space_id=context.space_id,
        ...
    )

# Lines 200-207
async def _fetch_rows(
    self,
    connection: asyncpg.Connection,
    *,
    space_id: str,
    ...
) -> list[asyncpg.Record]:

# Lines 235-236
return await connection.fetch(statement, *params)
```

**Detailed Line-by-Line Changes**:

| Line | Current Code | Target Code | Change Type |
|------|--------------|-------------|-------------|
| 7 | `import sqlite3` | `import asyncpg` | Import change |
| 14 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` | Import change |
| 140 | `def execute(...)` | `async def execute(...)` | Async method |
| 151 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` | Async context |
| 152-155 | `rows = self._fetch_rows(...)` | `rows = await self._fetch_rows(...)` | Async call |
| 200 | `def _fetch_rows(...)` | `async def _fetch_rows(...)` | Async method |
| 203 | `connection: sqlite3.Connection,` | `connection: asyncpg.Connection,` | Type annotation |
| 210 | `) -> list[sqlite3.Row]:` | `) -> list[asyncpg.Record]:` | Return type |
| 220 | `"WHERE space_id = ?"` | `"WHERE space_id = $1"` | Param style |
| 225 | `"AND tenant_id = ?"` | `"AND tenant_id = $2"` (etc.) | Param style |
| 235-236 | `connection.execute(statement, params).fetchall()` | `await connection.fetch(statement, *params)` | Async fetch |
| 239-242 | `row["body"]` access | `row["body"]` (asyncpg Record same) | Keep |
| 295 | `def execute(...)` (FtsDriver) | `async def execute(...)` | Async method |
| 308 | `with connection_scope() as connection:` | `async with async_connection_scope() as connection:` | Async context |
| 309-312 | `rows = self._search_fts(...)` | `rows = await self._search_fts(...)` | Async call |
| 334 | `def _search_fts(...)` | `async def _search_fts(...)` | Async method |
| 337 | `connection: sqlite3.Connection,` | `connection: asyncpg.Connection,` | Type annotation |
| 344 | `) -> list[sqlite3.Row]:` | `) -> list[asyncpg.Record]:` | Return type |
| 346-350 | FTS5 MATCH query | PostgreSQL ts_vector/ts_query | **Major rewrite** |
| 367-368 | `connection.execute(statement, params).fetchall()` | `await connection.fetch(statement, *params)` | Async fetch |

**FTS5 → PostgreSQL Full-Text Search Conversion**:

| SQLite FTS5 | PostgreSQL tsvector/tsquery |
|-------------|----------------------------|
| `st_fts MATCH '{query}'` | `tsv @@ plainto_tsquery('english', $1)` |
| `bm25(st_fts)` | `ts_rank(tsv, plainto_tsquery('english', $1))` |
| FTS5 virtual table | tsvector column with GIN index |
| `ORDER BY bm25(st_fts)` | `ORDER BY ts_rank(...) DESC` |

---

# Phase 5: Auxiliary & Cleanup

## Milestone 5.1: Fabric & Ports (24 changes)

### Epic 5.1.1: Remove Sync Wrappers

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.1.1.1 | Remove executor from Fabric | `k0/fabric/fabric.py` | 5 |
| 5.1.1.2 | Remove executor from Registry | `k0/fabric/registry.py` | 2 |
| 5.1.1.3 | Remove executor from Query Port | `k0/ports/query.py` | 2 |

---

#### Issue 5.1.1.1: Remove executor from Fabric

**File**: `k0/fabric/fabric.py` (435 lines)

**Purpose**: Capability Fabric provides request/reply by capability name. Uses ThreadPoolExecutor for timeout enforcement.

**Current State**: Uses `ThreadPoolExecutor` for handler execution with timeout. This is a threading pattern, not database-related.

**Migration Impact**: Low - ThreadPoolExecutor is for capability handlers, not database. Only database-related executor uses need removal.

**Changes Required**:

- No database connection changes (Fabric uses capability registry, not direct DB access)
- Keep ThreadPoolExecutor for handler timeout enforcement
- If any internal methods use `connection_scope()`, convert to async

---

#### Issue 5.1.1.2: Remove executor from Registry

**File**: `k0/fabric/registry.py` (459 lines)

**Purpose**: Maps capability names to providers. Thread-safe registry with RLock.

**Migration Impact**: Low - Registry is in-memory, no database calls.

**Changes Required**:

- No database connection changes
- Keep threading primitives for thread-safety

---

#### Issue 5.1.1.3: Remove executor from Query Port

**File**: `k0/ports/query.py` (841 lines)

**Purpose**: HTTP handlers for `/k0/query.recall` endpoint.

**Current State**: Calls sync `QueryAggregator` which uses `connection_scope()`.

**Changes Required**:

- Update driver calls to async
- `QueryAggregator.aggregate()` → `await QueryAggregator.aggregate()`

---

### Epic 5.1.2: Convert Command Port to Async (**CRITICAL**)

> **This is the main HTTP command submission endpoint (`/k0/command.submit`)**. Uses sync `connection_scope()` context manager for MinimalGate validation and idempotency checks. All storage layer calls pass explicit `connection=` parameter within sync transaction block.

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.1.2.1 | Convert connection_scope to async | `k0/ports/command.py` | 2 |
| 5.1.2.2 | Convert gate_connection usage to async | `k0/ports/command.py` | 4 |
| 5.1.2.3 | Convert UoW connection calls to async | `k0/ports/command.py` | 7 |

---

#### Issue 5.1.2.1: Convert connection_scope to async

**File**: `k0/ports/command.py` (1164 lines)

**Current State (SQLite)**:

```python
# Line 46
from k0.uow.connection_pool import connection_scope

# Line 281
with connection_scope() as gate_connection:
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 46
from k0.uow.postgres_pool import async_connection_scope

# Line 281
async with async_connection_scope() as gate_connection:
```

---

#### Issue 5.1.2.2: Convert gate_connection usage to async

**Current State**:

```python
# Line 284
outcome = minimal_gate.validate(
    dict(envelope_dict),
    body=body_bytes,
    connection=gate_connection,
)

# Line 322
duplicate = idem_ledger.lookup(idem_key, connection=gate_connection)

# Line 341
device_record = provisioning.lookup(
    envelope_dict["tenant_id"],
    envelope_dict["space_id"],
    envelope_dict["device_id"],
    connection=gate_connection,
)
```

**Target State**:

```python
# Line 284
outcome = await minimal_gate.validate(
    dict(envelope_dict),
    body=body_bytes,
    connection=gate_connection,
)

# Line 322
duplicate = await idem_ledger.lookup(idem_key, connection=gate_connection)

# Line 341
device_record = await provisioning.lookup(
    envelope_dict["tenant_id"],
    envelope_dict["space_id"],
    envelope_dict["device_id"],
    connection=gate_connection,
)
```

---

#### Issue 5.1.2.3: Convert UoW connection calls to async

**Current State**:

```python
# Line 647
duplicate = idem_ledger.lookup(idem_key, connection=uow.connection)

# Line 709
obligation_store.bulk_save(obligation_records, connection=uow.connection)

# Line 764
receipt_doc = receipt_issuer.issue(..., connection=uow.connection)

# Line 802
idem_ledger.upsert(ledger_entry, connection=uow.connection)
```

**Target State**:

```python
# Line 647
duplicate = await idem_ledger.lookup(idem_key, connection=uow.connection)

# Line 709
await obligation_store.bulk_save(obligation_records, connection=uow.connection)

# Line 764
receipt_doc = await receipt_issuer.issue(..., connection=uow.connection)

# Line 802
await idem_ledger.upsert(ledger_entry, connection=uow.connection)
```

**Complete Line-by-Line Changes for command.py**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 46 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| 281 | `with connection_scope() as gate_connection:` | `async with async_connection_scope() as gate_connection:` |
| 282-287 | `outcome = minimal_gate.validate(...)` | `outcome = await minimal_gate.validate(...)` |
| 322 | `duplicate = idem_ledger.lookup(...)` | `duplicate = await idem_ledger.lookup(...)` |
| 337-341 | `device_record = provisioning.lookup(...)` | `device_record = await provisioning.lookup(...)` |
| 647 | `duplicate = idem_ledger.lookup(...)` | `duplicate = await idem_ledger.lookup(...)` |
| 709 | `obligation_store.bulk_save(...)` | `await obligation_store.bulk_save(...)` |
| 764 | `receipt_doc = receipt_issuer.issue(...)` | `receipt_doc = await receipt_issuer.issue(...)` |
| 802 | `idem_ledger.upsert(...)` | `await idem_ledger.upsert(...)` |

---

## Milestone 5.2: Auxiliary Modules (57 changes)

### Epic 5.2.1: Automation & Deploy (47 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.2.1.1 | Rewrite migrate.py for Alembic | `k0/automation/migrate.py` | 28 |
| 5.2.1.2 | Convert provision_device.py | `k0/deploy/provision_device.py` | 19 |

---

#### Issue 5.2.1.1: Rewrite migrate.py for Alembic

**File**: `k0/automation/migrate.py` (556 lines)

**Purpose**: SQLite migration runner. Applies forward/rollback migrations, tracks in `schema_migrations` catalog.

**Current State (SQLite)**:

```python
# Line 35
import sqlite3

# Lines 89-95
def apply_migrations(
    database_path: Path | str,
    *,
    migrations_path: Path | str | None = None,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> list[MigrationResult]:

# Line 133
connection = sqlite3.connect(str(db_path))

# Lines 135-137
connection.execute("PRAGMA journal_mode=WAL;")
connection.execute("PRAGMA busy_timeout=5000;")
_ensure_catalog(connection)
```

**Target State (PostgreSQL/Alembic)**:

```python
# Imports
from alembic.config import Config
from alembic import command
import asyncpg

# Completely rewritten for Alembic
async def apply_migrations(
    database_url: str,
    *,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> list[MigrationResult]:
    """Apply Alembic migrations to PostgreSQL database."""
    alembic_cfg = Config("k0/db/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    if dry_run:
        # Use Alembic --sql mode for dry run
        command.upgrade(alembic_cfg, "head", sql=True)
    else:
        command.upgrade(alembic_cfg, "head")
```

**Migration Strategy**: Complete rewrite to use Alembic instead of custom migration runner.

**Key Changes**:

1. Remove `sqlite3.connect()` - use Alembic config
2. Remove PRAGMA statements - not applicable to PostgreSQL
3. Remove custom `_ensure_catalog()` - Alembic manages `alembic_version` table
4. Remove custom `_load_applied()` - Alembic tracks this
5. Remove checksum verification - Alembic handles this
6. Use `alembic.command.upgrade()` for forward migrations
7. Use `alembic.command.downgrade()` for rollbacks

---

#### Issue 5.2.1.2: Convert provision_device.py

**File**: `k0/deploy/provision_device.py` (402 lines)

**Purpose**: Device provisioning script. Registers devices in SQLite database.

**Current State (SQLite)**:

```python
# Line 23
import sqlite3

# Line 82-83
conn = sqlite3.connect(self.db_path)
cursor = conn.cursor()

# Lines 86-87
cursor.execute("SELECT device_id FROM devices WHERE device_id = ?", (device_id,))
existing = cursor.fetchone()

# Lines 105-119
cursor.execute(
    """
    INSERT INTO devices (
        tenant_id, space_id, device_id, public_key, roles, band, status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (tenant_id, space_id, device_id, public_key, roles, band, "ACTIVE", ...),
)
conn.commit()
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 23
import asyncpg
import asyncio

# Line 82-83
conn = await asyncpg.connect(self.db_url)

# Lines 86-87
existing = await conn.fetchrow(
    "SELECT device_id FROM devices WHERE device_id = $1", device_id
)

# Lines 105-119
await conn.execute(
    """
    INSERT INTO devices (
        tenant_id, space_id, device_id, public_key, roles, band, status, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """,
    tenant_id, space_id, device_id, public_key, roles, band, "ACTIVE", ...,
)
# No explicit commit - asyncpg auto-commits outside transactions
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 23 | `import sqlite3` | `import asyncpg; import asyncio` |
| 39 | `self.db_path = Path(db_path)` | `self.db_url = db_url` (PostgreSQL DSN) |
| 82 | `conn = sqlite3.connect(self.db_path)` | `conn = await asyncpg.connect(self.db_url)` |
| 83 | `cursor = conn.cursor()` | *Remove* (asyncpg doesn't use cursors) |
| 86-87 | `cursor.execute(...).fetchone()` | `await conn.fetchrow(...)` |
| 86 | `WHERE device_id = ?` | `WHERE device_id = $1` |
| 96 | `cursor.execute("DELETE FROM devices WHERE device_id = ?")` | `await conn.execute(...$1...)` |
| 97 | `conn.commit()` | *Remove* |
| 105-119 | `cursor.execute(INSERT... VALUES (?, ?, ...))` | `await conn.execute(... $1, $2, ...)` |
| 120 | `conn.commit()` | *Remove* |
| 124-125 | `cursor.execute(...).fetchone()` | `await conn.fetchrow(...)` |
| 126 | `conn.close()` | `await conn.close()` |
| 136 | `sqlite3.Error` | `asyncpg.PostgresError` |
| 155-175 | `list_devices()` - all sync calls | `async def list_devices()` with await |
| 190-210 | `delete_device()` - all sync calls | `async def delete_device()` with await |

**CLI Wrapper Changes**:
Since the script uses `argparse` and runs synchronously, wrap async functions:

```python
def main():
    # ... argparse setup ...
    asyncio.run(provisioner.provision_device(...))
```

---

### Epic 5.2.2: Sync & Misc (10 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.2.2.1 | Convert CRDT Merge Logger | `k0/sync/crdt_merge_logger.py` | 10 |

---

#### Issue 5.2.2.1: Convert CRDT Merge Logger

**File**: `k0/sync/crdt_merge_logger.py` (346 lines)

**Purpose**: Logs CRDT conflict resolution events to `st_crdt_merge_log` for debugging and compliance.

**Current State (SQLite)**:

```python
# Line 13
import sqlite3

# Line 19
from k0.uow.connection_pool import connection_scope

# Lines 64-78
def log_merge(
    self,
    merge_id: str,
    ...
    connection: Optional[sqlite3.Connection] = None,
) -> None:

# Lines 100-101
resolve = connection if connection else connection_scope()
with resolve as conn:

# Lines 103-119
conn.execute(
    """
    INSERT INTO st_crdt_merge_log (...)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (merge_id, resource_type, ...),
)
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 13
import asyncpg

# Line 19
from k0.uow.postgres_pool import async_connection_scope

# Lines 64-78
async def log_merge(
    self,
    merge_id: str,
    ...
    connection: Optional[asyncpg.Connection] = None,
) -> None:

# Lines 100-101
resolve = connection if connection else async_connection_scope()
async with resolve as conn:

# Lines 103-119
await conn.execute(
    """
    INSERT INTO st_crdt_merge_log (...)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    """,
    merge_id, resource_type, ...,
)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 13 | `import sqlite3` | `import asyncpg` |
| 19 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| 64 | `def log_merge(...)` | `async def log_merge(...)` |
| 78 | `connection: Optional[sqlite3.Connection]` | `connection: Optional[asyncpg.Connection]` |
| 100 | `resolve = connection if connection else connection_scope()` | `... async_connection_scope()` |
| 101 | `with resolve as conn:` | `async with resolve as conn:` |
| 103-119 | `conn.execute(INSERT... VALUES (?, ?, ...))` | `await conn.execute(... $1, $2, ...)` |
| 121 | `conn.commit()` | *Remove* |
| 122 | `sqlite3.OperationalError` | `asyncpg.PostgresError` |
| 142 | `def get_merge_history(...)` | `async def get_merge_history(...)` |
| 155 | `connection: Optional[sqlite3.Connection]` | `connection: Optional[asyncpg.Connection]` |
| 175-180 | `conn.execute(...).fetchall()` | `await conn.fetch(...)` |

---

### Epic 5.2.3: Idem & Receipts (10 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.2.3.1 | Convert Idempotency Ledger | `k0/idem/ledger.py` | 8 |
| 5.2.3.2 | Convert Receipt Issuer | `k0/receipts/issuer.py` | 2 |

---

#### Issue 5.2.3.1: Convert Idempotency Ledger

**File**: `k0/idem/ledger.py` (200 lines)

**Purpose**: Thin abstraction over storage-backed idempotency ledger. Provides `lookup()` and `upsert()` for command deduplication.

**Current State (SQLite)**:

```python
# Line 5
import sqlite3

# Line 11
from k0.uow.connection_pool import connection_scope

# Lines 26-31
@contextmanager
def _resolve_connection(
    connection: sqlite3.Connection | None,
) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
        return
    with connection_scope() as pooled_connection:
        yield pooled_connection
        pooled_connection.commit()

# Lines 58-68
def lookup(
    self,
    idem_key: str,
    *,
    connection: sqlite3.Connection | None = None,
) -> LedgerEntry | None:
    with _resolve_connection(connection) as conn:
        row = conn.execute(
            "SELECT ... FROM idem_ledger WHERE idem_key = ?",
            (idem_key,),
        ).fetchone()

# Lines 80-94
def upsert(
    self,
    entry: LedgerEntry,
    *,
    connection: sqlite3.Connection | None = None,
) -> None:
    with _resolve_connection(connection) as conn:
        conn.execute(
            "INSERT INTO idem_ledger ... ON CONFLICT(idem_key) DO UPDATE SET ...",
            (entry.idem_key, ...),
        )
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 5
import asyncpg

# Line 11
from k0.uow.postgres_pool import async_connection_scope

# Lines 26-31
@asynccontextmanager
async def _resolve_connection(
    connection: asyncpg.Connection | None,
) -> AsyncIterator[asyncpg.Connection]:
    if connection is not None:
        yield connection
        return
    async with async_connection_scope() as pooled_connection:
        yield pooled_connection

# Lines 58-68
async def lookup(
    self,
    idem_key: str,
    *,
    connection: asyncpg.Connection | None = None,
) -> LedgerEntry | None:
    async with _resolve_connection(connection) as conn:
        row = await conn.fetchrow(
            "SELECT ... FROM idem_ledger WHERE idem_key = $1",
            idem_key,
        )

# Lines 80-94
async def upsert(
    self,
    entry: LedgerEntry,
    *,
    connection: asyncpg.Connection | None = None,
) -> None:
    async with _resolve_connection(connection) as conn:
        await conn.execute(
            "INSERT INTO idem_ledger ... ON CONFLICT(idem_key) DO UPDATE SET ...",
            entry.idem_key, ...,
        )
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 5 | `import sqlite3` | `import asyncpg` |
| 8 | `from contextlib import contextmanager` | `from contextlib import asynccontextmanager` |
| 9 | `from typing import Iterator` | `from typing import AsyncIterator` |
| 11 | `from k0.uow.connection_pool import connection_scope` | `from k0.uow.postgres_pool import async_connection_scope` |
| 26 | `@contextmanager` | `@asynccontextmanager` |
| 27 | `def _resolve_connection(...)` | `async def _resolve_connection(...)` |
| 28 | `connection: sqlite3.Connection \| None` | `connection: asyncpg.Connection \| None` |
| 29 | `) -> Iterator[sqlite3.Connection]:` | `) -> AsyncIterator[asyncpg.Connection]:` |
| 33 | `with connection_scope() as pooled_connection:` | `async with async_connection_scope() as pooled_connection:` |
| 35 | `pooled_connection.commit()` | *Remove* |
| 58 | `def lookup(...)` | `async def lookup(...)` |
| 62 | `connection: sqlite3.Connection \| None` | `connection: asyncpg.Connection \| None` |
| 64 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |
| 65-68 | `row = conn.execute(...).fetchone()` | `row = await conn.fetchrow(...)` |
| 66 | `WHERE idem_key = ?` | `WHERE idem_key = $1` |
| 67 | `(idem_key,),` | `idem_key,` |
| 80 | `def upsert(...)` | `async def upsert(...)` |
| 84 | `connection: sqlite3.Connection \| None` | `connection: asyncpg.Connection \| None` |
| 86 | `with _resolve_connection(connection) as conn:` | `async with _resolve_connection(connection) as conn:` |
| 87-93 | `conn.execute(INSERT... ON CONFLICT...)` | `await conn.execute(...)` |
| 89-91 | `VALUES (?, ?, ?, ?, ?)` | `VALUES ($1, $2, $3, $4, $5)` |

---

#### Issue 5.2.3.2: Convert Receipt Issuer

**File**: `k0/receipts/issuer.py` (244 lines)

**Purpose**: Issue signed receipts, persist them, and fan-out observability signals.

**Current State (SQLite)**:

```python
# Line 7
import sqlite3

# Line 98
connection: sqlite3.Connection | None = None,

# Line 145
self._store.save(stored_receipt, connection=connection)
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 7
import asyncpg

# Line 98
connection: asyncpg.Connection | None = None,

# Line 145
await self._store.save(stored_receipt, connection=connection)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 7 | `import sqlite3` | `import asyncpg` |
| 79 | `def issue(...)` | `async def issue(...)` |
| 98 | `connection: sqlite3.Connection \| None = None,` | `connection: asyncpg.Connection \| None = None,` |
| 145 | `self._store.save(stored_receipt, connection=connection)` | `await self._store.save(stored_receipt, connection=connection)` |

### Epic 5.2.4: SSE (2 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.2.4.1 | Update SSE Server imports | `k0/sse/server.py` | 2 |

---

#### Issue 5.2.4.1: Update SSE Server imports

**File**: `k0/sse/server.py` (342 lines)

**Purpose**: SSE mux implementation for the kernel. Manages SSE subscriptions, acknowledgements, and backpressure evaluation.

**Current State (SQLite)**:

```python
# Line 7
import sqlite3

# Line 56
database_connection: sqlite3.Connection | None = None
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 7
import asyncpg

# Line 56
database_connection: asyncpg.Connection | None = None
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 7 | `import sqlite3` | `import asyncpg` |
| 56 | `database_connection: sqlite3.Connection \| None = None` | `database_connection: asyncpg.Connection \| None = None` |

**Note**: The SSEServer already uses async methods (`async def subscribe`, `async def evaluate_backpressure`). The WAL and OffsetStore calls within already expect async, so only the type annotations need updating.

---

### Epic 5.2.5: CLI & Perf (7 changes)

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.2.5.1 | Convert k0ctl.py connection_scope to async | `k0/cli/k0ctl.py` | 6 |
| 5.2.5.2 | Update perf runner | `k0/perf/runner.py` | 1 |

---

#### Issue 5.2.5.1: Convert k0ctl.py connection_scope to async

**File**: `k0/cli/k0ctl.py` (1469 lines)

**Purpose**: Administrative CLI for orchestrating the K0 kernel runtime. Provides `serve`, `migrate`, `provision`, `schema`, `key` subcommands.

**Current State (SQLite)**:

```python
# Line 23
from ..uow.connection_pool import configure_pool, connection_scope, shutdown_pool

# Various subcommand handlers use:
with connection_scope() as conn:
    # sync database operations
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 23
from ..uow.postgres_pool import configure_pool, async_connection_scope, shutdown_pool

# Various subcommand handlers use:
async with async_connection_scope() as conn:
    # async database operations
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 23 | `from ..uow.connection_pool import configure_pool, connection_scope, shutdown_pool` | `from ..uow.postgres_pool import configure_pool, async_connection_scope, shutdown_pool` |
| ~450 | `with connection_scope() as conn:` | `async with async_connection_scope() as conn:` |
| ~520 | `registry.register(...)` | `await registry.register(...)` |
| ~590 | `registry.promote(...)` | `await registry.promote(...)` |
| ~650 | `provisioning.upsert(...)` | `await provisioning.upsert(...)` |
| ~720 | `key_store.add_key(...)` | `await key_store.add_key(...)` |

**CLI Wrapper Pattern**: Since CLI commands run synchronously via argparse, wrap async handlers:

```python
def cmd_provision(args: argparse.Namespace, settings: KernelSettings) -> int:
    async def _async_provision():
        async with async_connection_scope() as conn:
            await provisioning.upsert(..., connection=conn)
    asyncio.run(_async_provision())
    return 0
```

**Note**: The `serve` subcommand already runs uvicorn (async-native), so it doesn't need changes. Only the sync CLI subcommands (`migrate`, `provision`, `schema`, `key`) need `asyncio.run()` wrappers.

---

#### Issue 5.2.5.2: Update perf runner

**File**: `k0/perf/runner.py` (410 lines)

**Purpose**: Performance scenario runner for k0 kernel load testing. Orchestrates YAML-based performance test scenarios.

**Current State**: The runner uses `httpx` for HTTP requests and does not directly access SQLite. No `sqlite3` imports.

**Migration Impact**: Low - No direct database changes required.

**Changes Required**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| N/A | No sqlite3 imports | No changes needed |

**Note**: This file is pure HTTP client code for load testing. It doesn't import `sqlite3` or use `connection_scope()`. The "1 change" in the epic may refer to updating any test scenario configuration files that reference SQLite paths, or updating metrics labels. Verify at implementation time.

---

## Milestone 5.3: Scripts Cleanup (81 changes)

### Epic 5.3.1: Update Utility Scripts

| Issue | Description | File | Changes |
|-------|-------------|------|---------|
| 5.3.1.1 | Update traffic generator | `k0/scripts/traffic_generator.py` | 12 |
| 5.3.1.2 | Update rebuild_faiss_index | `k0/scripts/rebuild_faiss_index.py` | 8 |
| 5.3.1.3 | Update backfill_pending | `k0/scripts/backfill_pending_embeddings.py` | 6 |

---

#### Issue 5.3.1.1: Update traffic generator

**File**: `k0/scripts/traffic_generator.py` (790 lines)

**Purpose**: Traffic generator for staging burn-in testing. Generates command, query, and SSE traffic patterns.

**Current State (SQLite)**:

```python
# Line 33
import sqlite3

# Lines 60-63 (clear_outbox_backlog function)
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Lines 70-73
cursor.execute("SELECT COUNT(*) as total FROM st_outbox")
outbox_before = cursor.fetchone()["total"]

# Lines 82-85
cursor.execute("DELETE FROM st_outbox")
outbox_cleared = cursor.rowcount
conn.commit()

# Line 93
conn.execute("VACUUM")
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 33
import asyncpg
import asyncio

# Lines 60-63 (clear_outbox_backlog function)
async def clear_outbox_backlog(db_url: str = "postgresql://...") -> dict:
    conn = await asyncpg.connect(db_url)

# Lines 70-73
row = await conn.fetchrow("SELECT COUNT(*) as total FROM st_outbox")
outbox_before = row["total"]

# Lines 82-85
result = await conn.execute("DELETE FROM st_outbox")
outbox_cleared = int(result.split()[-1])  # Parse "DELETE N"

# Line 93 - VACUUM in PostgreSQL
await conn.execute("VACUUM st_outbox")
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 33 | `import sqlite3` | `import asyncpg; import asyncio` |
| 56 | `def clear_outbox_backlog(db_path: str = ...)` | `async def clear_outbox_backlog(db_url: str = ...)` |
| 60 | `conn = sqlite3.connect(db_path)` | `conn = await asyncpg.connect(db_url)` |
| 61 | `conn.row_factory = sqlite3.Row` | *Remove* (asyncpg returns Record objects) |
| 62 | `cursor = conn.cursor()` | *Remove* (asyncpg doesn't use cursors) |
| 70 | `cursor.execute(...).fetchone()` | `await conn.fetchrow(...)` |
| 73 | `cursor.execute(...).fetchone()` | `await conn.fetchrow(...)` |
| 76 | `cursor.execute(...).fetchone()` | `await conn.fetchrow(...)` |
| 82 | `cursor.execute("DELETE FROM st_outbox")` | `await conn.execute("DELETE FROM st_outbox")` |
| 83 | `outbox_cleared = cursor.rowcount` | Parse result string or use RETURNING |
| 84 | `conn.commit()` | *Remove* (asyncpg auto-commits) |
| 88 | `cursor.execute("DELETE FROM st_dlq")` | `await conn.execute("DELETE FROM st_dlq")` |
| 90 | `conn.commit()` | *Remove* |
| 93 | `conn.execute("VACUUM")` | `await conn.execute("VACUUM")` |
| 96 | `conn.close()` | `await conn.close()` |

**CLI Wrapper Update**:

```python
# Main entry point
if __name__ == "__main__":
    # Wrap async clear_outbox_backlog
    result = asyncio.run(clear_outbox_backlog(args.db_url))
```

---

#### Issue 5.3.1.2: Update rebuild_faiss_index

**File**: `k0/scripts/rebuild_faiss_index.py` (511 lines)

**Purpose**: Rebuild FAISS index from st_vec embeddings. Backup, train, and build FAISS IVF256,PQ64 index.

**Current State (SQLite)**:

```python
# Line 28
import sqlite3

# Line 56
self.conn: sqlite3.Connection | None = None

# Line 61
self.conn = sqlite3.connect(self.db_path)
self.conn.row_factory = sqlite3.Row

# Line 107
cursor = self.conn.execute(query)
row = cursor.fetchone()

# Line 124
cursor = self.conn.execute(query, (batch_size, offset))
rows = cursor.fetchall()
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 28
import asyncpg
import asyncio

# Line 56
self.conn: asyncpg.Connection | None = None

# Line 61
async def connect(self) -> None:
    self.conn = await asyncpg.connect(self.db_url)

# Line 107
row = await self.conn.fetchrow(query)

# Line 124
rows = await self.conn.fetch(query, batch_size, offset)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 28 | `import sqlite3` | `import asyncpg; import asyncio` |
| 46 | `db_path: str` | `db_url: str` (PostgreSQL DSN) |
| 56 | `self.conn: sqlite3.Connection \| None = None` | `self.conn: asyncpg.Connection \| None = None` |
| 59 | `def connect(self) -> None:` | `async def connect(self) -> None:` |
| 61 | `self.conn = sqlite3.connect(self.db_path)` | `self.conn = await asyncpg.connect(self.db_url)` |
| 62 | `self.conn.row_factory = sqlite3.Row` | *Remove* |
| 65 | `def close(self) -> None:` | `async def close(self) -> None:` |
| 67-68 | `self.conn.close()` | `await self.conn.close()` |
| 107 | `cursor = self.conn.execute(query); row = cursor.fetchone()` | `row = await self.conn.fetchrow(query)` |
| 124-125 | `cursor = self.conn.execute(query, ...); rows = cursor.fetchall()` | `rows = await self.conn.fetch(query, ...)` |
| 124 | `LIMIT ? OFFSET ?` | `LIMIT $1 OFFSET $2` |

**pgvector Migration Note**: This script should ultimately be replaced by pgvector functionality. The FAISS index rebuild becomes unnecessary once pgvector HNSW indexes are in place.

---

#### Issue 5.3.1.3: Update backfill_pending

**File**: `k0/scripts/backfill_pending_embeddings.py` (316 lines)

**Purpose**: Backfill PENDING embedding records by triggering P08 pipeline events.

**Current State (SQLite)**:

```python
# Line 24
import sqlite3

# Line 46
self.conn: sqlite3.Connection | None = None

# Line 50
self.conn = sqlite3.connect(self.db_path)
self.conn.row_factory = sqlite3.Row

# Line 71
cursor = self.conn.execute(query, params)
results = cursor.fetchall()
```

**Target State (PostgreSQL/asyncpg)**:

```python
# Line 24
import asyncpg
import asyncio

# Line 46
self.conn: asyncpg.Connection | None = None

# Line 50
async def connect(self) -> None:
    self.conn = await asyncpg.connect(self.db_url)

# Line 71
results = await self.conn.fetch(query, *params)
```

**Detailed Changes**:

| Line | Current Code | Target Code |
|------|--------------|-------------|
| 24 | `import sqlite3` | `import asyncpg; import asyncio` |
| 39 | `db_path: str` | `db_url: str` |
| 46 | `self.conn: sqlite3.Connection \| None = None` | `self.conn: asyncpg.Connection \| None = None` |
| 49 | `def connect(self) -> None:` | `async def connect(self) -> None:` |
| 50 | `self.conn = sqlite3.connect(self.db_path)` | `self.conn = await asyncpg.connect(self.db_url)` |
| 51 | `self.conn.row_factory = sqlite3.Row` | *Remove* |
| 54 | `def close(self) -> None:` | `async def close(self) -> None:` |
| 56 | `self.conn.close()` | `await self.conn.close()` |
| 68-70 | `WHERE embedding_status = 'PENDING'` + `?` params | `WHERE embedding_status = 'PENDING'` + `$1, $2` params |
| 81 | `cursor = self.conn.execute(query, params)` | `results = await self.conn.fetch(query, *params)` |
| 82 | `results = cursor.fetchall()` | *Merged into above* |

---

### Epic 5.3.2: Archive Migration Scripts

| Issue | Description | File | Action |
|-------|-------------|------|--------|
| 5.3.2.1 | Archive SQLite audit scripts | `k0/scripts/sqlite_migration_audit.py` | Archive |
| 5.3.2.2 | Archive filter scripts | `k0/scripts/filter_production_files.py` | Archive |
| 5.3.2.3 | Archive find_sync_wrappers | `k0/scripts/find_sync_wrappers.py` | Archive |
| 5.3.2.4 | Archive generate_migration_doc | `k0/scripts/generate_migration_doc.py` | Archive |

---

#### Issue 5.3.2.1-5.3.2.4: Archive Migration Scripts

**Action**: Move SQLite-specific migration/analysis scripts to archive directory.

**Rationale**: These scripts were created to support the SQLite → PostgreSQL migration process itself. After migration is complete, they are no longer needed in the main codebase but should be preserved for reference.

**Archive Process**:

```bash
# Create archive directory
mkdir -p k0/scripts/_archived_sqlite_migration/

# Move scripts with timestamp prefix
mv k0/scripts/sqlite_migration_audit.py k0/scripts/_archived_sqlite_migration/
mv k0/scripts/filter_production_files.py k0/scripts/_archived_sqlite_migration/
mv k0/scripts/find_sync_wrappers.py k0/scripts/_archived_sqlite_migration/
mv k0/scripts/generate_migration_doc.py k0/scripts/_archived_sqlite_migration/

# Add README to archive
cat > k0/scripts/_archived_sqlite_migration/README.md << 'EOF'
# Archived SQLite Migration Scripts

These scripts were used during the SQLite → PostgreSQL migration (2025).
They are preserved for reference but are not part of the active codebase.

## Scripts

- `sqlite_migration_audit.py` - Audit SQLite usage in codebase
- `filter_production_files.py` - Filter files for migration analysis
- `find_sync_wrappers.py` - Find sync wrapper patterns
- `generate_migration_doc.py` - Generate migration documentation

## Archive Date
$(date -I)
EOF
```

**Files to Archive**:

| File | Purpose | Lines |
|------|---------|-------|
| `sqlite_migration_audit.py` | Audits codebase for SQLite patterns | ~200 |
| `filter_production_files.py` | Filters production files for analysis | ~150 |
| `find_sync_wrappers.py` | Finds `run_in_executor` patterns | ~100 |
| `generate_migration_doc.py` | Generates this migration documentation | ~300 |

---

## Milestone 5.4: Cleanup & Deprecation

### Epic 5.4.1: Remove SQLite Dependencies

| Issue | Description | Action |
|-------|-------------|--------|
| 5.4.1.1 | Remove sqlite3 from requirements | Update `pyproject.toml` |
| 5.4.1.2 | Remove SQLite driver | Delete `k0/drivers/sqlite.py` |
| 5.4.1.3 | Remove SQLite connection pool | Delete `k0/uow/connection_pool.py` |
| 5.4.1.4 | Remove FTS5 indexer | Delete `k0/storage/fts5_indexer.py` |

---

#### Issue 5.4.1.1: Remove sqlite3 from requirements

**File**: `pyproject.toml`

**Action**: No explicit removal needed - `sqlite3` is a Python stdlib module, not a pip dependency.

**Verification**: Ensure no `sqlite3` or SQLite-related packages remain in `pyproject.toml`:

- No `aiosqlite` in dependencies
- No `sqlite-utils` in dependencies

---

#### Issue 5.4.1.2: Remove SQLite driver

**File to Delete**: `k0/drivers/sqlite.py` (573 lines)

**Purpose**: SQLite driver implementing K0 Driver SPI for ACID operations.

**Pre-Deletion Checklist**:

- [ ] All imports of `SQLiteDriver` removed from codebase
- [ ] All references in `k0/drivers/__init__.py` removed
- [ ] New `PostgresDriver` in `k0/drivers/postgres.py` is functional
- [ ] All tests updated to use `PostgresDriver`

**Classes/Functions to Remove**:

- `SQLiteDriver` class
- `set_bus_dispatcher()` function
- All PRAGMA-based configuration

**Replacement**: `k0/drivers/postgres.py` (new file)

---

#### Issue 5.4.1.3: Remove SQLite connection pool

**File to Delete**: `k0/uow/connection_pool.py` (393 lines)

**Purpose**: Thread-safe SQLite connection pool with WAL mode, busy timeout, and metrics.

**Pre-Deletion Checklist**:

- [ ] All imports of `connection_scope`, `configure_pool`, `shutdown_pool` removed
- [ ] All references in `k0/uow/__init__.py` removed
- [ ] New `k0/db/pool.py` (asyncpg pool) is functional
- [ ] New `async_connection_scope` context manager is available

**Classes/Functions to Remove**:

- `SQLiteConnectionPool` class
- `PoolStats` dataclass
- `configure_pool()` function
- `connection_scope()` context manager
- `shutdown_pool()` function
- `get_write_lock()` function

**Replacement**: `k0/db/pool.py` with asyncpg.Pool wrapper

---

#### Issue 5.4.1.4: Remove FTS5 indexer

**File to Delete**: `k0/storage/fts5_indexer.py` (352 lines)

**Purpose**: FTS5 full-text search indexer for memory tables (st_epi_fts, st_hipp_fts).

**Pre-Deletion Checklist**:

- [ ] All imports of `FTS5Indexer` removed from codebase
- [ ] PostgreSQL tsvector columns and GIN indexes created via Alembic
- [ ] Full-text search queries converted to `ts_vector @@ ts_query` syntax
- [ ] All tests updated for PostgreSQL full-text search

**Classes/Functions to Remove**:

- `FTS5Indexer` class
- `FTS5IndexerError` exception
- `index_episodic()` method
- `search_episodic()` method
- `index_hippocampus()` method
- `search_hippocampus()` method

**Replacement**: PostgreSQL tsvector columns with GIN indexes (handled by Alembic migrations 0013-0015)

---

### Epic 5.4.2: Update Dependencies

| Issue | Description | Action |
|-------|-------------|--------|
| 5.4.2.1 | Add asyncpg to requirements | `pyproject.toml` |
| 5.4.2.2 | Add pgvector to requirements | `pyproject.toml` |
| 5.4.2.3 | Add alembic to requirements | `pyproject.toml` |
| 5.4.2.4 | Add psycopg2 for Alembic | `pyproject.toml` |

---

#### Issue 5.4.2.1-5.4.2.4: Update pyproject.toml

**File**: `pyproject.toml`

**Current State**:

```toml
[project]
name = "familyos-k1-bridge"
version = "0.1.0"
# ... no database dependencies listed
```

**Target State**:

```toml
[project]
name = "familyos-k1-bridge"
version = "0.1.0"
dependencies = [
    # PostgreSQL
    "asyncpg>=0.29.0",
    "pgvector>=0.2.5",
    # Migrations
    "alembic>=1.13.0",
    "psycopg2-binary>=2.9.9",  # Required by Alembic for sync operations
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    # ... existing dev deps ...
    "pytest-postgresql>=5.0.0",  # PostgreSQL test fixtures
]
```

**Detailed Changes**:

| Package | Version | Purpose |
|---------|---------|---------|
| `asyncpg` | `>=0.29.0` | Native async PostgreSQL driver |
| `pgvector` | `>=0.2.5` | Vector similarity search extension |
| `alembic` | `>=1.13.0` | Database migration framework |
| `psycopg2-binary` | `>=2.9.9` | Sync driver for Alembic migrations |
| `pytest-postgresql` | `>=5.0.0` | PostgreSQL fixtures for testing |

**Version Rationale**:

- `asyncpg>=0.29.0`: Latest stable with Python 3.10+ support
- `pgvector>=0.2.5`: Supports HNSW indexes, vector operations
- `alembic>=1.13.0`: Async migration support, latest features
- `psycopg2-binary>=2.9.9`: Binary wheel for easy installation

---

### Epic 5.4.3: Dual-Stack Deprecation & Feature Flags (RISK MITIGATION)

| Issue | Description | File | Changes |
|-------|-------------|------|--------|
| 5.4.3.1 | Add database backend feature flag | `k0/config/settings.py` | 3 |
| 5.4.3.2 | Create backend router shim | `k0/uow/__init__.py` | 2 |
| 5.4.3.3 | Add SQLite deprecation markers | Multiple files | 5 |
| 5.4.3.4 | Configure CI for phased testing | `.github/workflows/test.yml` | 1 |

**Problem Statement:**

During migration, the codebase temporarily supports both SQLite and PostgreSQL paths. This creates:

- Doubled test matrix
- Confusion about "source of truth"
- Risk of regressions in either path
- Maintenance burden

**Mitigation Strategy:** Aggressive 7-week deprecation timeline with feature flags.

---

#### Issue 5.4.3.1: Add Database Backend Feature Flag

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 1.2.1.1 (asyncpg pool) |
| **Risk** | MEDIUM - Dual-stack complexity |
| **Assignee** | TBD |

**File to Create/Modify:** `k0/config/settings.py`

**Implementation:**

```python
# k0/config/settings.py
from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database configuration with backend selection."""

    # Feature flag for gradual PostgreSQL rollout
    use_postgresql: bool = Field(
        default=True,
        env="K0_USE_POSTGRESQL",
        description="Use PostgreSQL instead of SQLite. Set to False for rollback."
    )

    # PostgreSQL settings (used when use_postgresql=True)
    postgres_host: str = Field(default="localhost", env="K0_POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="K0_POSTGRES_PORT")
    postgres_database: str = Field(default="k0_kernel", env="K0_POSTGRES_DB")
    postgres_user: str = Field(default="k0user", env="K0_POSTGRES_USER")
    postgres_password: str = Field(default="changeme", env="K0_POSTGRES_PASSWORD")

    # SQLite settings (used when use_postgresql=False, deprecated)
    sqlite_path: str = Field(
        default="/data/k0_runtime.sqlite3",
        env="K0_DB_PATH",
        deprecated="Use PostgreSQL settings instead"
    )

    @property
    def backend(self) -> str:
        """Return current database backend identifier."""
        return "postgresql" if self.use_postgresql else "sqlite"
```

**Environment Variable:**

```bash
# Enable PostgreSQL (default after Phase 3)
export K0_USE_POSTGRESQL=true

# Emergency rollback to SQLite
export K0_USE_POSTGRESQL=false
```

---

#### Issue 5.4.3.2: Create Backend Router Shim

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 2 hours |
| **Dependencies** | 5.4.3.1 |
| **Assignee** | TBD |

**File to Modify:** `k0/uow/__init__.py`

**Implementation:**

```python
# k0/uow/__init__.py
"""Unit of Work module with backend routing."""

from k0.config import get_settings

settings = get_settings()

if settings.database.use_postgresql:
    # PostgreSQL path (primary after Phase 3)
    from k0.db.pool import (
        configure_pool,
        get_pool,
        shutdown_pool,
    )
    from k0.db.connection import (
        connection_scope as async_connection_scope,
        transaction_scope,
        read_only_scope,
    )

    # Re-export with consistent names
    __all__ = [
        "async_connection_scope",
        "configure_pool",
        "get_pool",
        "read_only_scope",
        "shutdown_pool",
        "transaction_scope",
    ]
else:
    # SQLite path (deprecated, fallback only)
    import warnings
    warnings.warn(
        "SQLite backend is deprecated. Set K0_USE_POSTGRESQL=true",
        DeprecationWarning,
        stacklevel=2
    )

    from k0.uow.connection_pool import (
        configure_pool,
        connection_scope,
        get_pool,
        shutdown_pool,
    )

    # Alias for compatibility
    async_connection_scope = connection_scope

    __all__ = [
        "async_connection_scope",
        "configure_pool",
        "connection_scope",
        "get_pool",
        "shutdown_pool",
    ]
```

---

#### Issue 5.4.3.3: Add SQLite Deprecation Markers

| Field | Value |
|-------|-------|
| **Priority** | P2 - Medium |
| **Estimate** | 2 hours |
| **Dependencies** | Phase 3 complete |
| **Assignee** | TBD |

**Files to Modify:**

| File | Change |
|------|--------|
| `k0/uow/connection_pool.py` | Add `DeprecationWarning` to all public functions |
| `k0/drivers/sqlite.py` | Add `DeprecationWarning` to class |
| `k0/storage/fts5_indexer.py` | Add `DeprecationWarning` to class |

**Implementation Example:**

```python
# k0/uow/connection_pool.py
import warnings


def configure_pool(
    database_path: Path,
    *,
    max_size: int = 8,
    pragmas: Mapping[str, str | int] | None = None,
) -> None:
    """Configure the global SQLite connection pool.

    .. deprecated:: 2.0.0
        SQLite backend is deprecated. Use `k0.db.pool.configure_pool()`
        for PostgreSQL. Set K0_USE_POSTGRESQL=true in environment.
    """
    warnings.warn(
        "SQLite connection pool is deprecated. "
        "Use k0.db.pool.configure_pool() for PostgreSQL. "
        "Set K0_USE_POSTGRESQL=true to switch.",
        DeprecationWarning,
        stacklevel=2,
    )
    # ... existing implementation ...
```

---

#### Issue 5.4.3.4: Configure CI for Phased Testing

| Field | Value |
|-------|-------|
| **Priority** | P1 - High |
| **Estimate** | 3 hours |
| **Dependencies** | 5.4.3.1, 5.4.3.2 |
| **Assignee** | TBD |

**File to Modify:** `.github/workflows/test.yml`

**Implementation:**

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, postgre-sql-migration]
  pull_request:
  workflow_dispatch:
    inputs:
      include_sqlite_tests:
        description: 'Include deprecated SQLite tests'
        required: false
        default: 'false'
        type: boolean

jobs:
  test-postgresql:
    name: PostgreSQL Tests (Primary)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: k0user
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: k0_kernel_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      pgbouncer:
        image: edoburu/pgbouncer:1.21.0
        ports:
          - 6432:6432
    env:
      K0_USE_POSTGRESQL: "true"
      K0_POSTGRES_HOST: localhost
      K0_POSTGRES_PORT: 5432
      K0_POSTGRES_DB: k0_kernel_test
      K0_POSTGRES_USER: k0user
      K0_POSTGRES_PASSWORD: testpass
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -m "not sqlite_only" --tb=short

  test-sqlite-legacy:
    name: SQLite Tests (Deprecated)
    if: ${{ github.event.inputs.include_sqlite_tests == 'true' }}
    runs-on: ubuntu-latest
    env:
      K0_USE_POSTGRESQL: "false"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -m "sqlite_only" --tb=short -W ignore::DeprecationWarning
```

**Test Markers:**

```python
# conftest.py
import pytest
from k0.config import get_settings

settings = get_settings()

# Marker for SQLite-only tests (deprecated)
sqlite_only = pytest.mark.sqlite_only

# Skip SQLite tests when PostgreSQL is primary
skip_sqlite = pytest.mark.skipif(
    settings.database.use_postgresql,
    reason="SQLite path deprecated, K0_USE_POSTGRESQL=true"
)

# Marker for PostgreSQL-only tests
postgresql_only = pytest.mark.postgresql_only
```

---

**Week-by-Week Deprecation Schedule:**

| Week | Action | SQLite Code Status | CI Behavior |
|------|--------|-------------------|-------------|
| 1-2 | Phase 1-2 complete | Active (primary) | Both backends tested |
| 3-4 | Phase 3 complete | Deprecated (fallback) | PostgreSQL primary, SQLite optional |
| 5 | Phase 4 complete | Dead code (tests only) | PostgreSQL only, SQLite on-demand |
| 6 | Phase 5.1-5.2 complete | Archived | PostgreSQL only |
| 7 | Phase 5.3-5.4 complete | **Deleted** | PostgreSQL only |

**Acceptance Criteria:**

- [ ] Feature flag `K0_USE_POSTGRESQL` working
- [ ] Backend router imports correct module
- [ ] Deprecation warnings emit for SQLite usage
- [ ] CI runs PostgreSQL tests by default
- [ ] SQLite tests only run on-demand after Phase 4
- [ ] All SQLite code deleted by Week 7

---

# New Files Summary (Complete List)

## Infrastructure (6 files)

> **NOTE:** k0/deploy/ already contains Docker infrastructure (Dockerfile, docker-compose.yml, docker-compose.gpu.yml).
> Extend existing files rather than creating new ones at repository root.

| # | Path | Purpose |
|---|------|---------|------|
| 1 | `k0/deploy/postgres/Dockerfile` | PostgreSQL 16 + pgvector container |
| 2 | `k0/deploy/postgres/init.sql` | Initial schema creation |
| 3 | `k0/deploy/postgres/extensions.sql` | CREATE EXTENSION pgvector, pg_trgm |
| 4 | `k0/deploy/pgbouncer/pgbouncer.ini` | Connection pooler config |
| 5 | `k0/deploy/pgbouncer/userlist.txt` | pgbouncer auth credentials |
| 6 | `k0/deploy/docker-compose.yml` | Modify existing - add postgres + pgbouncer services |

## Configuration (2 files)

| # | Path | Purpose |
|---|------|---------|
| 7 | `k0/config/postgres.py` | PostgresSettings pydantic model |
| 8 | `k0/config/__init__.py` | Export postgres config (modify existing) |

## Database Layer (7 files)

| # | Path | Purpose |
|---|------|---------|
| 9 | `k0/db/__init__.py` | DB module exports |
| 10 | `k0/db/pool.py` | asyncpg.Pool wrapper, configure_pool(), get_pool() |
| 11 | `k0/db/connection.py` | Async connection context manager |
| 12 | `k0/db/types.py` | PostgreSQL ↔ Python type converters (UUID, JSONB, etc.) |
| 13 | `k0/db/query.py` | Query builder with $1, $2 param style |
| 14 | `k0/db/statements.py` | Prepared statement cache |
| 15 | `k0/db/params.py` | Parameter binding utilities |

## Alembic Migrations (22 files)

| # | Path | Purpose |
|---|------|---------|
| 16 | `k0/db/alembic.ini` | Alembic configuration |
| 17 | `k0/db/alembic/env.py` | Migration environment (async) |
| 18 | `k0/db/alembic/script.py.mako` | Migration template |
| 19 | `k0/db/alembic/versions/0001_initial.py` | Base revision (empty) |
| 20 | `k0/db/alembic/versions/0002_wal_table.py` | st_wal table |
| 21 | `k0/db/alembic/versions/0003_outbox_table.py` | st_outbox table |
| 22 | `k0/db/alembic/versions/0004_dlq_table.py` | st_dlq table |
| 23 | `k0/db/alembic/versions/0005_receipts_table.py` | st_receipts table |
| 24 | `k0/db/alembic/versions/0006_schema_registry.py` | schema_registry table |
| 25 | `k0/db/alembic/versions/0007_offsets.py` | offsets table |
| 26 | `k0/db/alembic/versions/0008_obligations.py` | obligations table |
| 27 | `k0/db/alembic/versions/0009_retention_policies.py` | retention_policies table |
| 28 | `k0/db/alembic/versions/0010_acl.py` | ACL tables |
| 29 | `k0/db/alembic/versions/0011_devices.py` | devices table |
| 30 | `k0/db/alembic/versions/0012_provisioning.py` | provisioning tables |
| 31 | `k0/db/alembic/versions/0013_fts_columns.py` | tsvector columns |
| 32 | `k0/db/alembic/versions/0014_fts_indexes.py` | GIN indexes |
| 33 | `k0/db/alembic/versions/0015_fts_triggers.py` | tsvector update triggers |
| 34 | `k0/db/alembic/versions/0016_pgvector_extension.py` | CREATE EXTENSION vector |
| 35 | `k0/db/alembic/versions/0017_embeddings_table.py` | embeddings table with vector column |
| 36 | `k0/db/alembic/versions/0018_vector_indexes.py` | HNSW/IVFFlat indexes |

## New Drivers (2 files)

| # | Path | Purpose |
|---|------|---------|
| 37 | `k0/drivers/postgres.py` | PostgreSQL driver (replaces sqlite.py) |
| 38 | `k0/drivers/pgvector.py` | pgvector driver (replaces faiss.py) |

## CLI (1 file)

| # | Path | Purpose |
|---|------|---------|
| 39 | `k0/cli/db_migrate.py` | Alembic CLI wrapper (upgrade, downgrade, status) |

## Tests (8+ files)

| # | Path | Purpose |
|---|------|---------|
| 40 | `tests/k0/db/test_pool.py` | Connection pool tests |
| 41 | `tests/k0/db/test_connection.py` | Connection context tests |
| 42 | `tests/k0/drivers/test_postgres.py` | PostgreSQL driver tests |
| 43 | `tests/k0/drivers/test_pgvector.py` | pgvector driver tests |
| 44 | `tests/fixtures/postgres.py` | PostgreSQL test fixtures |
| 45 | `tests/conftest.py` | Update with PostgreSQL fixtures |
| 46+ | Various test updates | Update existing tests for asyncpg |

**Total New Files: ~46**
| `k0/drivers/pgvector.py` | Vector search driver |

## CLI

| Path | Purpose |
|------|---------|
| `k0/cli/db_migrate.py` | Alembic CLI wrapper |

---

# Test Files to Update

| Module | Test File | Priority |
|--------|-----------|----------|
| storage | `tests/k0/storage/test_wal.py` | HIGH |
| storage | `tests/k0/storage/test_outbox.py` | HIGH |
| uow | `tests/k0/uow/test_unit_of_work.py` | HIGH |
| gate | `tests/k0/gate/test_schema_registry.py` | HIGH |
| kernel | `tests/k0/kernel/test_syscalls.py` | HIGH |
| drivers | `tests/k0/drivers/test_sqlite.py` → `test_postgres.py` | MEDIUM |
| policy | `tests/k0/policy/test_retention.py` | MEDIUM |
| query | `tests/k0/query/test_drivers.py` | MEDIUM |

---

# Migration Sequence (Critical Path)

```
Phase 1 (Week 1-2)
├── 1.1 Infrastructure Setup (k0/deploy/)
│   ├── PostgreSQL/pgbouncer in k0/deploy/
│   └── Alembic initialization
└── 1.2 Core DB Layer
    ├── Connection pool
    └── Query builder

Phase 2 (Week 2-3)
├── 2.1 Core Schema Migrations
│   ├── WAL, Outbox, DLQ, Receipts
│   └── Schema Registry, Offsets
└── 2.2 Search/Vector Schema
    ├── tsvector + GIN
    └── pgvector extension

Phase 3 (Week 3-5)
├── 3.1 Storage Layer (11 files, 189 changes)
│   └── Highest complexity
└── 3.2 UoW & Gate (4 files, 93 changes)
    └── Critical dependencies

Phase 4 (Week 5-6)
├── 4.1 Driver Layer (4 files, 55 changes)
├── 4.2 Kernel Layer (3 files, 45 changes)
│   └── Remove all run_in_executor
└── 4.3 Policy & Query (3 files, 45 changes)

Phase 5 (Week 6-8)
├── 5.1 Fabric & Ports (3 files, 9 changes)
├── 5.2 Auxiliary Modules (6 files, 57 changes)
├── 5.3 Scripts Cleanup (7 files)
└── 5.4 Final Cleanup
    └── Remove SQLite dependencies
```

---

# Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data migration failures | HIGH | Create rollback scripts, test on staging |
| Performance regression | MEDIUM | Benchmark before/after each phase |
| Connection pool exhaustion | MEDIUM | Configure pgbouncer limits, monitor |
| FTS5 → tsvector parity | LOW | Document search behavior differences |
| pgvector index build time | LOW | Build indexes during maintenance window |

---

# Critical Execution Risks & Mitigations

## Risk 1: Prepared Statements + pgbouncer (Transaction Mode)

**Severity**: HIGH - This is the biggest technical risk in the migration.

**The Conflict**:

- `asyncpg` uses prepared statements by default for performance
- `pgbouncer` in `pool_mode = transaction` reuses connections aggressively
- Prepared statements are **connection-local** in PostgreSQL
- When pgbouncer reassigns a connection, prepared statements from previous sessions don't exist

**Symptoms if Unmitigated**:

```
asyncpg.exceptions.InvalidSQLStatementNameError: prepared statement "..." does not exist
```

**Decision Required**: Choose ONE of these approaches:

### Option A: Disable Prepared Statements (RECOMMENDED)

Configure asyncpg to disable statement caching when using pgbouncer:

```python
# k0/db/pool.py
async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=5,
        max_size=20,
        # CRITICAL: Disable prepared statement caching for pgbouncer compatibility
        statement_cache_size=0,
        # Also disable the prepared statement threshold
        max_cached_statement_lifetime=0,
    )
```

**Trade-off**: ~10-15% performance overhead vs prepared statements, but zero pgbouncer conflicts.

### Option B: Use pgbouncer Session Mode

```ini
# pgbouncer.ini
[pgbouncer]
pool_mode = session  ; Changed from 'transaction'
```

**Trade-off**: Higher connection count to PostgreSQL, less efficient pooling, but prepared statements work.

### Option C: Server-Side Prepared Statements (PostgreSQL 14+)

Use `PREPARE` statements stored in PostgreSQL itself:

```python
# Not recommended - adds complexity without clear benefit
```

**Our Decision**: **Option A - Disable Prepared Statements**

Rationale:

- pgbouncer transaction mode is essential for connection efficiency at scale
- 10-15% overhead is acceptable vs connection exhaustion risk
- Simpler operational model

**Implementation**:

```python
# k0/db/pool.py - Line ~45
POOL_CONFIG = {
    "min_size": 5,
    "max_size": 20,
    "statement_cache_size": 0,           # Disable for pgbouncer
    "max_cached_statement_lifetime": 0,  # Disable lifetime caching
    "command_timeout": 60.0,
    "max_inactive_connection_lifetime": 300.0,
}
```

**Validation Test**:

```python
# tests/k0/db/test_pgbouncer_compat.py
async def test_prepared_statement_disabled():
    """Verify no prepared statement errors under pgbouncer."""
    pool = await create_pool()

    # Run 100 concurrent queries to trigger connection reuse
    async def query():
        async with pool.acquire() as conn:
            await conn.fetch("SELECT 1")

    await asyncio.gather(*[query() for _ in range(100)])
    # Should complete without InvalidSQLStatementNameError
```

---

## Risk 2: st_hipp_events Migration Blast Radius

**Severity**: HIGH - 91 columns, heavy write volume, largest table in the system.

**The Problem**:

- `st_hipp_events` is the primary episodic event store
- 91 columns including JSONB, vectors, timestamps
- Continuous write traffic from P02/P03 pipelines
- Naive migration will cause:
  - Long table locks
  - Disk bloat during COPY
  - Index creation blocking writes

**Migration Choreography**:

### Phase 1: Pre-Migration Preparation

```sql
-- 1. Create target table without indexes (faster initial load)
CREATE TABLE st_hipp_events_new (
    -- ... all 91 columns ...
) WITH (autovacuum_enabled = false);  -- Disable during bulk load

-- 2. Estimate row count and plan batching
SELECT reltuples::bigint FROM pg_class WHERE relname = 'st_hipp_events';
```

### Phase 2: Data Migration (Staged)

```python
# k0/automation/migrate_hipp_events.py
BATCH_SIZE = 10_000  # Tuned for memory/lock duration

async def migrate_hipp_events_staged():
    """Migrate st_hipp_events in batches to avoid long locks."""

    # 1. Get max event_id for batching
    max_id = await conn.fetchval("SELECT MAX(event_id) FROM st_hipp_events_old")

    # 2. Migrate in batches
    for offset in range(0, max_id, BATCH_SIZE):
        async with conn.transaction():
            await conn.execute("""
                INSERT INTO st_hipp_events_new
                SELECT * FROM st_hipp_events_old
                WHERE event_id > $1 AND event_id <= $2
            """, offset, offset + BATCH_SIZE)

        # 3. Yield to allow other transactions
        await asyncio.sleep(0.1)

        # 4. Log progress
        logger.info(f"Migrated batch {offset}-{offset + BATCH_SIZE}")
```

### Phase 3: Index Creation (Staged, CONCURRENTLY)

```sql
-- Create indexes CONCURRENTLY to avoid blocking writes
-- Run these one at a time, not in parallel

-- Primary key (required, but fast)
ALTER TABLE st_hipp_events_new ADD PRIMARY KEY (event_id);

-- Tenant/space lookup (most critical)
CREATE INDEX CONCURRENTLY idx_hipp_tenant_space
ON st_hipp_events_new (tenant_id, space_id, commit_ts DESC);

-- Full-text search (slowest, run during maintenance window)
CREATE INDEX CONCURRENTLY idx_hipp_fts
ON st_hipp_events_new USING GIN (tsv);

-- Vector similarity (run last, HNSW is expensive)
CREATE INDEX CONCURRENTLY idx_hipp_vector
ON st_hipp_events_new USING hnsw (embedding vector_cosine_ops);
```

### Phase 4: Cutover (Atomic Rename)

```sql
-- Maintenance window required for this step
BEGIN;
  -- Lock both tables briefly
  LOCK TABLE st_hipp_events IN ACCESS EXCLUSIVE MODE;
  LOCK TABLE st_hipp_events_new IN ACCESS EXCLUSIVE MODE;

  -- Atomic rename swap
  ALTER TABLE st_hipp_events RENAME TO st_hipp_events_old;
  ALTER TABLE st_hipp_events_new RENAME TO st_hipp_events;
COMMIT;

-- Re-enable autovacuum
ALTER TABLE st_hipp_events SET (autovacuum_enabled = true);
```

### Phase 5: Post-Migration Cleanup

```sql
-- Run VACUUM ANALYZE after migration
VACUUM ANALYZE st_hipp_events;

-- Monitor bloat for 24-48 hours
SELECT
    schemaname, tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size
FROM pg_tables
WHERE tablename = 'st_hipp_events';

-- Drop old table after validation period (7 days recommended)
-- DROP TABLE st_hipp_events_old;
```

**Estimated Migration Time** (for 10M rows):

- Data COPY: ~30-60 minutes (batched)
- Primary key: ~5 minutes
- B-tree indexes: ~10 minutes each
- GIN (FTS) index: ~30 minutes
- HNSW (vector) index: ~2-4 hours

**Disk Space Required**: 2x current table size (old + new during migration)

---

## Risk 3: Dual-Stack Period Complexity

**Severity**: MEDIUM - Test scope bloat, maintenance burden.

**The Problem**:
During migration, the codebase will temporarily support:

- SQLite shims (legacy paths)
- async PostgreSQL (new paths)
- Migration wrapper scripts
- Both test fixture sets

This creates:

- Doubled test matrix
- Confusion about "source of truth"
- Risk of regressions in either path

**Mitigation Strategy: Aggressive Deprecation Timeline**

### Week-by-Week Deprecation Schedule

| Week | Action | SQLite Code Status |
|------|--------|-------------------|
| 1-2 | Phase 1-2 complete, PostgreSQL infra up | Active (primary) |
| 3-4 | Phase 3 complete, storage layer migrated | Deprecated (fallback only) |
| 5 | Phase 4 complete, kernel migrated | Dead code (tests only) |
| 6 | Phase 5.1-5.2 complete | Archived |
| 7 | Phase 5.3-5.4 complete | **Deleted** |

### Feature Flag for Cutover

```python
# k0/config/settings.py
class DatabaseSettings(BaseSettings):
    # Feature flag for gradual rollout
    use_postgresql: bool = Field(
        default=True,
        env="K0_USE_POSTGRESQL",
        description="Use PostgreSQL instead of SQLite"
    )
```

```python
# k0/uow/__init__.py
from k0.config import settings

if settings.database.use_postgresql:
    from k0.db.pool import async_connection_scope
else:
    from k0.uow.connection_pool import connection_scope as async_connection_scope
```

### Test Matrix Reduction

```python
# conftest.py - Deprecate SQLite tests after Phase 4
import pytest
from k0.config import settings

# Skip SQLite tests once PostgreSQL is primary
skip_sqlite = pytest.mark.skipif(
    settings.database.use_postgresql,
    reason="SQLite path deprecated"
)

# tests/k0/storage/test_wal_sqlite.py
@skip_sqlite
class TestWalSQLite:
    """Legacy SQLite tests - deprecated after Phase 4."""
    pass
```

### CI Pipeline Phasing

```yaml
# .github/workflows/test.yml
jobs:
  test-postgresql:
    # Always run - primary path
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
    steps:
      - run: pytest tests/ -m "not sqlite_only"

  test-sqlite-legacy:
    # Run only until Phase 5 complete
    if: ${{ github.event.inputs.include_sqlite_tests == 'true' }}
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/ -m "sqlite_only"
```

### Deprecation Markers in Code

```python
# k0/uow/connection_pool.py (SQLite pool)
import warnings

def connection_scope():
    """DEPRECATED: Use async_connection_scope from k0.db.pool instead."""
    warnings.warn(
        "connection_scope() is deprecated. Use async_connection_scope() from k0.db.pool",
        DeprecationWarning,
        stacklevel=2
    )
    # ... existing implementation ...
```

---

## Risk Summary Matrix

| Risk | Severity | Mitigation | Owner | Status |
|------|----------|------------|-------|--------|
| Prepared statements + pgbouncer | HIGH | Disable statement_cache_size | DB Team | Planned |
| st_hipp_events blast radius | HIGH | Staged migration with CONCURRENTLY | DB Team | Planned |
| Dual-stack complexity | MEDIUM | Aggressive 7-week deprecation | Dev Team | Planned |
| Connection pool exhaustion | MEDIUM | pgbouncer limits + monitoring | Ops Team | Planned |
| FTS5 → tsvector parity | LOW | Document differences, test coverage | Dev Team | Planned |

---

# Definition of Done

- [ ] All 41 files converted
- [ ] All 586 code changes applied
- [ ] All Alembic migrations created and tested
- [ ] All tests passing with PostgreSQL
- [ ] No remaining `sqlite3` imports in production code
- [ ] No remaining `run_in_executor` patterns
- [ ] pgbouncer configured for production
- [ ] Performance benchmarks acceptable
- [ ] Rollback procedure documented
