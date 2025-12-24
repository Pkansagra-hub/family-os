# K0 PostgreSQL & Async Migration

**Generated:** 2025-12-22T18:44:13.894939

This document identifies all K0 production files requiring changes for:

1. **SQLite → PostgreSQL migration** (asyncpg, pgvector)
2. **Sync → Async conversion** (remove run_in_executor wrappers)

---

## Target Technology Stack

| Component | Current | Target |
|-----------|---------|--------|
| Database | SQLite | PostgreSQL 16+ |
| Driver | sqlite3 (sync) | asyncpg (native async) |
| Vector Store | FAISS + SQLite metadata | pgvector extension |
| Full-Text Search | FTS5 | PostgreSQL tsvector + GIN |
| Migrations | Raw SQL files | Alembic |
| Connection Pool | Custom SQLiteConnectionPool | pgbouncer + asyncpg.Pool |
| Sync Wrappers | run_in_executor | Native async/await |

---

## Summary

| Category | Files | Occurrences |
|----------|-------|-------------|
| SQLite imports/types | 45 | 297 |
| Sync wrappers (run_in_executor) | 12 | 53 |
| DB execute operations | 49 | 282 |
| **Total unique files** | **49** | **632** |

---

## Files By Module

### automation/ (1 files, 28 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `automation\migrate.py` | 13 | 0 | 15 | 28 |

### cli/ (1 files, 6 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `cli\k0ctl.py` | 4 | 0 | 2 | 6 |

### deploy/ (3 files, 19 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `deploy\provision_device.py` | 5 | 0 | 14 | 19 |
| `deploy\multi_envelope.py` | 0 | 0 | 0 | 0 |
| `deploy\provision_and_submit.py` | 0 | 0 | 0 | 0 |

### drivers/ (4 files, 55 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `drivers\sqlite.py` | 11 | 0 | 12 | 23 |
| `drivers\embedding_queue.py` | 2 | 0 | 13 | 15 |
| `drivers\faiss.py` | 3 | 0 | 8 | 11 |
| `drivers\fts5.py` | 1 | 0 | 5 | 6 |

### fabric/ (2 files, 7 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `fabric\fabric.py` | 0 | 5 | 0 | 5 |
| `fabric\registry.py` | 0 | 2 | 0 | 2 |

### gate/ (2 files, 51 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `gate\schema_registry.py` | 21 | 0 | 19 | 40 |
| `gate\minimal_gate.py` | 7 | 0 | 4 | 11 |

### idem/ (1 files, 8 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `idem\ledger.py` | 5 | 0 | 3 | 8 |

### kernel/ (3 files, 45 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `kernel\syscalls.py` | 0 | 15 | 20 | 35 |
| `kernel\dependencies.py` | 8 | 0 | 0 | 8 |
| `kernel\app.py` | 1 | 1 | 0 | 2 |

### policy/ (2 files, 34 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `policy\retention_enforcer.py` | 9 | 0 | 10 | 19 |
| `policy\acl_enforcer.py` | 9 | 0 | 6 | 15 |

### perf/ (1 files, 1 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `perf\runner.py` | 0 | 0 | 1 | 1 |

### ports/ (2 files, 17 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `ports\command.py` | 2 | 0 | 13 | 15 |
| `ports\query.py` | 0 | 1 | 1 | 2 |

### query/ (2 files, 12 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `query\drivers.py` | 7 | 0 | 4 | 11 |
| `query\service.py` | 0 | 0 | 1 | 1 |

### receipts/ (1 files, 2 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `receipts\issuer.py` | 2 | 0 | 0 | 2 |

### scripts/ (7 files, 81 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `scripts\sqlite_migration_audit.py` | 17 | 0 | 0 | 17 |
| `scripts\find_sync_wrappers.py` | 2 | 9 | 4 | 15 |
| `scripts\generate_migration_doc.py` | 6 | 9 | 0 | 15 |
| `scripts\traffic_generator.py` | 3 | 0 | 9 | 12 |
| `scripts\filter_production_files.py` | 5 | 3 | 0 | 8 |
| `scripts\rebuild_faiss_index.py` | 4 | 0 | 4 | 8 |
| `scripts\backfill_pending_embeddings.py` | 4 | 0 | 2 | 6 |

### sse/ (1 files, 2 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `sse\server.py` | 2 | 0 | 0 | 2 |

### storage/ (12 files, 200 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `storage\outbox.py` | 11 | 1 | 19 | 31 |
| `storage\shard_promotion.py` | 19 | 0 | 12 | 31 |
| `storage\wal.py` | 10 | 4 | 7 | 21 |
| `storage\dlq.py` | 9 | 0 | 9 | 18 |
| `storage\provisioning.py` | 9 | 0 | 6 | 15 |
| `storage\replayer.py` | 6 | 0 | 9 | 15 |
| `storage\obligations.py` | 7 | 0 | 6 | 13 |
| `storage\snapshots.py` | 8 | 0 | 5 | 13 |
| `storage\offsets.py` | 7 | 2 | 3 | 12 |
| `storage\fts.py` | 5 | 0 | 6 | 11 |
| `storage\fts5_indexer.py` | 3 | 0 | 7 | 10 |
| `storage\receipts.py` | 6 | 1 | 3 | 10 |

### sync/ (1 files, 10 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `sync\crdt_merge_logger.py` | 7 | 0 | 3 | 10 |

### uow/ (2 files, 42 changes)

| File | SQLite | Async | Exec | Total |
|------|--------|-------|------|-------|
| `uow\unit_of_work.py` | 17 | 0 | 14 | 31 |
| `uow\connection_pool.py` | 9 | 0 | 2 | 11 |

---

## Detailed File Analysis

### `k0/gate\schema_registry.py`

**SQLite:** 21 | **Async Wrappers:** 0 | **Execute Calls:** 19

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 5 | import sqlite3 | `import sqlite3` |
| 36 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 37 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 47 | sqlite3.Connection type | `def _ensure_row_factory(connection: sqlite3.Connection) -> None:` |
| 48 | row_factory | `if connection.row_factory is None:` |
| 49 | sqlite3.Row | `connection.row_factory = sqlite3.Row` |
| 81 | sqlite3.Connection type | `def load(self, *, connection: sqlite3.Connection \| None = None) -> Non` |
| 85 | row_factory | `_ensure_row_factory(conn)` |
| 116 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 132 | row_factory | `_ensure_row_factory(conn)` |
| 166 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 170 | row_factory | `_ensure_row_factory(conn)` |
| 193 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 197 | row_factory | `_ensure_row_factory(conn)` |
| 218 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 225 | row_factory | `_ensure_row_factory(conn)` |
| 277 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 307 | row_factory | `_ensure_row_factory(conn)` |
| 352 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 390 | row_factory | `_ensure_row_factory(conn)` |
| 428 | sqlite3.Row | `def _refresh_uri_cache(self, uri: str, rows: Sequence[sqlite3.Row]) ->` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 86 | execute() | `rows = conn.execute(` |
| 88 | fetchall() | `).fetchall()` |
| 133 | execute() | `row = conn.execute(` |
| 136 | fetchone() | `).fetchone()` |
| 172 | execute() | `conn.execute(` |
| 198 | execute() | `conn.execute(` |
| 226 | execute() | `row = conn.execute(` |
| 229 | fetchone() | `).fetchone()` |
| 236 | execute() | `conn.execute(` |
| 240 | execute() | `conn.execute(` |
| 245 | execute() | `conn.execute(` |
| 254 | execute() | `conn.execute(` |
| 262 | execute() | `rows = conn.execute(` |
| 265 | fetchall() | `).fetchall()` |
| 308 | execute() | `updated = conn.execute(` |
| 324 | execute() | `rows = conn.execute(` |
| 327 | fetchall() | `).fetchall()` |
| 391 | execute() | `rows = conn.execute(query, tuple(params)).fetchall()` |
| 391 | fetchall() | `rows = conn.execute(query, tuple(params)).fetchall()` |

---

### `k0/kernel\syscalls.py`

**SQLite:** 0 | **Async Wrappers:** 15 | **Execute Calls:** 20

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 281 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 410 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 705 | run_in_executor | `result = await asyncio.get_event_loop().run_in_executor(` |
| 845 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 1091 | run_in_executor | `await loop.run_in_executor(None, uow.connection.executemany, insert_sq` |
| 1263 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 1423 | run_in_executor | `total_result = await loop.run_in_executor(` |
| 1438 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 1572 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 1580 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 2157 | run_in_executor | `total_result = await loop.run_in_executor(` |
| 2172 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 2303 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 2311 | run_in_executor | `cursor = await loop.run_in_executor(` |
| 2425 | run_in_executor | `result = await loop.run_in_executor(` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 283 | execute() | `lambda: conn.execute(` |
| 412 | execute() | `lambda: conn.execute(` |
| 707 | execute() | `lambda: conn.execute(query, (actor_id,)).fetchall(),` |
| 707 | fetchall() | `lambda: conn.execute(query, (actor_id,)).fetchall(),` |
| 847 | execute() | `lambda: conn.execute(` |
| 1265 | execute() | `lambda: conn.execute(` |
| 1425 | execute() | `lambda: conn.execute(count_sql, params).fetchone(),` |
| 1425 | fetchone() | `lambda: conn.execute(count_sql, params).fetchone(),` |
| 1440 | execute() | `lambda: conn.execute(query_sql, params + [limit, offset]),` |
| 1442 | fetchall() | `rows = cursor.fetchall()` |
| 1574 | execute() | `lambda: conn.execute(` |
| 1582 | execute() | `lambda: conn.execute(` |
| 2159 | execute() | `lambda: conn.execute(count_sql, params).fetchone(),` |
| 2159 | fetchone() | `lambda: conn.execute(count_sql, params).fetchone(),` |
| 2174 | execute() | `lambda: conn.execute(query_sql, params + [limit, offset]),` |
| 2176 | fetchall() | `rows = cursor.fetchall()` |
| 2305 | execute() | `lambda: conn.execute(` |
| 2313 | execute() | `lambda: conn.execute(` |
| 2427 | execute() | `lambda: conn.execute(sql, params).fetchone(),` |
| 2427 | fetchone() | `lambda: conn.execute(sql, params).fetchone(),` |

---

### `k0/storage\outbox.py`

**SQLite:** 11 | **Async Wrappers:** 1 | **Execute Calls:** 19

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 35 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 36 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 61 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 71 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 138 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 195 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 210 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 277 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 302 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 349 | sqlite3.Connection type | `connection: sqlite3.Connection,` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 65 | run_in_executor | `return await loop.run_in_executor(None, lambda: self.enqueue(entry, co` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 77 | execute() | `cursor = conn.execute(` |
| 102 | execute() | `cursor = conn.execute(` |
| 147 | execute() | `rows = conn.execute(` |
| 154 | fetchall() | `).fetchall()` |
| 158 | execute() | `rows = conn.execute(` |
| 165 | fetchall() | `).fetchall()` |
| 225 | execute() | `rows = conn.execute(` |
| 237 | fetchall() | `).fetchall()` |
| 241 | execute() | `rows = conn.execute(` |
| 248 | fetchall() | `).fetchall()` |
| 282 | execute() | `row = conn.execute(` |
| 285 | fetchone() | `).fetchone()` |
| 289 | execute() | `conn.execute("DELETE FROM st_outbox WHERE id=?", (entry_id,))` |
| 311 | execute() | `conn.execute(` |
| 330 | execute() | `conn.execute(` |
| 356 | execute() | `total_row = connection.execute("SELECT COUNT(*) AS pending FROM st_out` |
| 356 | fetchone() | `total_row = connection.execute("SELECT COUNT(*) AS pending FROM st_out` |
| 371 | execute() | `driver_row = connection.execute(` |
| 374 | fetchone() | `).fetchone()` |

---

### `k0/storage\shard_promotion.py`

**SQLite:** 19 | **Async Wrappers:** 0 | **Execute Calls:** 12

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 5 | import sqlite3 | `import sqlite3` |
| 211 | sqlite3.Connection type | `def _connect_primary(self) -> ContextManager[sqlite3.Connection]:` |
| 214 | sqlite3.Connection type | `def _connect_standby(self) -> ContextManager[sqlite3.Connection]:` |
| 218 | sqlite3.Connection type | `def _connect_database(path: Path) -> ContextManager[sqlite3.Connection` |
| 220 | sqlite3.Connection type | `def _connector() -> Iterator[sqlite3.Connection]:` |
| 221 | sqlite3.connect() | `connection = sqlite3.connect(path.as_posix())` |
| 222 | sqlite3.Row | `connection.row_factory = sqlite3.Row` |
| 223 | PRAGMA command | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 233 | sqlite3.Connection type | `primary_conn: sqlite3.Connection, standby_conn: sqlite3.Connection` |
| 243 | sqlite3.Connection type | `def _latest_commit_ts(connection: sqlite3.Connection) -> datetime \| No` |
| 261 | sqlite3.Connection type | `def _resolve_watermark(connection: sqlite3.Connection) -> int:` |
| 271 | sqlite3.Connection type | `connection: sqlite3.Connection, after_position: int` |
| 272 | sqlite3.Row | `) -> Iterable[sqlite3.Row]:` |
| 284 | sqlite3.Connection type | `connection: sqlite3.Connection,` |
| 286 | sqlite3.Row | `) -> dict[int, sqlite3.Row]:` |
| 301 | sqlite3.Connection type | `connection: sqlite3.Connection, positions: Sequence[int]` |
| 315 | sqlite3.Connection type | `connection: sqlite3.Connection, entry: Mapping[str, object]` |
| 334 | sqlite3.Connection type | `connection: sqlite3.Connection, receipt: Mapping[str, object]` |
| 351 | sqlite3.Row | `def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 223 | execute() | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 244 | execute() | `row = connection.execute(` |
| 246 | fetchone() | `).fetchone()` |
| 262 | execute() | `row = connection.execute(` |
| 264 | fetchone() | `).fetchone()` |
| 273 | execute() | `return connection.execute(` |
| 296 | execute() | `rows = connection.execute(query, tuple(positions)).fetchall()` |
| 296 | fetchall() | `rows = connection.execute(query, tuple(positions)).fetchall()` |
| 309 | execute() | `rows = connection.execute(query, tuple(positions)).fetchall()` |
| 309 | fetchall() | `rows = connection.execute(query, tuple(positions)).fetchall()` |
| 317 | execute() | `connection.execute(` |
| 336 | execute() | `connection.execute(` |

---

### `k0/uow\unit_of_work.py`

**SQLite:** 17 | **Async Wrappers:** 0 | **Execute Calls:** 14

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 7 | import sqlite3 | `import sqlite3` |
| 76 | sqlite3.Connection type | `_scope: AbstractContextManager[sqlite3.Connection] \| None = field(init` |
| 77 | sqlite3.Connection type | `_connection: sqlite3.Connection \| None = field(init=False, default=Non` |
| 105 | sqlite3.Connection type | `assert isinstance(connection, sqlite3.Connection)  # runtime safety` |
| 109 | PRAGMA command | `self._connection.execute("PRAGMA journal_mode=WAL")` |
| 110 | PRAGMA command | `self._connection.execute("PRAGMA synchronous=NORMAL")` |
| 111 | PRAGMA command | `self._connection.execute("PRAGMA foreign_keys=ON")` |
| 112 | PRAGMA command | `self._connection.execute("PRAGMA temp_store=MEMORY")` |
| 113 | PRAGMA command | `self._connection.execute("PRAGMA busy_timeout=5000")  # 5s fallback` |
| 114 | PRAGMA command | `self._connection.execute("PRAGMA wal_autocheckpoint=1000")` |
| 157 | PRAGMA command | `self._connection.execute("PRAGMA journal_mode=WAL")` |
| 158 | PRAGMA command | `self._connection.execute("PRAGMA synchronous=NORMAL")` |
| 159 | PRAGMA command | `self._connection.execute("PRAGMA foreign_keys=ON")` |
| 160 | PRAGMA command | `self._connection.execute("PRAGMA temp_store=MEMORY")` |
| 161 | PRAGMA command | `self._connection.execute("PRAGMA busy_timeout=60000")` |
| 162 | PRAGMA command | `self._connection.execute("PRAGMA wal_autocheckpoint=1000")` |
| 185 | sqlite3.Connection type | `def connection(self) -> sqlite3.Connection:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 109 | execute() | `self._connection.execute("PRAGMA journal_mode=WAL")` |
| 110 | execute() | `self._connection.execute("PRAGMA synchronous=NORMAL")` |
| 111 | execute() | `self._connection.execute("PRAGMA foreign_keys=ON")` |
| 112 | execute() | `self._connection.execute("PRAGMA temp_store=MEMORY")` |
| 113 | execute() | `self._connection.execute("PRAGMA busy_timeout=5000")  # 5s fallback` |
| 114 | execute() | `self._connection.execute("PRAGMA wal_autocheckpoint=1000")` |
| 117 | execute() | `self._connection.execute("BEGIN IMMEDIATE")` |
| 157 | execute() | `self._connection.execute("PRAGMA journal_mode=WAL")` |
| 158 | execute() | `self._connection.execute("PRAGMA synchronous=NORMAL")` |
| 159 | execute() | `self._connection.execute("PRAGMA foreign_keys=ON")` |
| 160 | execute() | `self._connection.execute("PRAGMA temp_store=MEMORY")` |
| 161 | execute() | `self._connection.execute("PRAGMA busy_timeout=60000")` |
| 162 | execute() | `self._connection.execute("PRAGMA wal_autocheckpoint=1000")` |
| 163 | execute() | `self._connection.execute("BEGIN IMMEDIATE")` |

---

### `k0/automation\migrate.py`

**SQLite:** 13 | **Async Wrappers:** 0 | **Execute Calls:** 15

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 36 | import sqlite3 | `import sqlite3` |
| 155 | sqlite3.connect() | `connection = sqlite3.connect(str(db_path))` |
| 157 | PRAGMA command | `connection.execute("PRAGMA journal_mode=WAL;")` |
| 158 | PRAGMA command | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 233 | PRAGMA command | `connection.execute("PRAGMA wal_checkpoint(FULL);")` |
| 304 | sqlite3.connect() | `connection = sqlite3.connect(str(db_path))` |
| 307 | PRAGMA command | `connection.execute("PRAGMA journal_mode=WAL;")` |
| 308 | PRAGMA command | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 392 | PRAGMA command | `connection.execute("PRAGMA wal_checkpoint(FULL);")` |
| 493 | PRAGMA command | `"PRAGMA foreign_keys=OFF;",` |
| 502 | PRAGMA command | `"PRAGMA foreign_keys=ON;",` |
| 525 | sqlite3.Connection type | `def _ensure_catalog(connection: sqlite3.Connection) -> None:` |
| 538 | sqlite3.Connection type | `def _load_applied(connection: sqlite3.Connection) -> dict[str, str]:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 157 | execute() | `connection.execute("PRAGMA journal_mode=WAL;")` |
| 158 | execute() | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 201 | execute() | `connection.execute("BEGIN")` |
| 202 | executescript() | `connection.executescript(script)` |
| 203 | execute() | `connection.execute(` |
| 233 | execute() | `connection.execute("PRAGMA wal_checkpoint(FULL);")` |
| 307 | execute() | `connection.execute("PRAGMA journal_mode=WAL;")` |
| 308 | execute() | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 362 | execute() | `connection.execute("BEGIN")` |
| 363 | executescript() | `connection.executescript(down_script)` |
| 364 | execute() | `connection.execute(` |
| 392 | execute() | `connection.execute("PRAGMA wal_checkpoint(FULL);")` |
| 527 | execute() | `connection.execute(` |
| 540 | execute() | `cursor = connection.execute("SELECT version, checksum FROM schema_migr` |
| 541 | fetchall() | `return {row[0]: row[1] for row in cursor.fetchall()}` |

---

### `k0/drivers\sqlite.py`

**SQLite:** 11 | **Async Wrappers:** 0 | **Execute Calls:** 12

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 23 | import sqlite3 | `import sqlite3` |
| 79 | sqlite3.Connection type | `self.conn: sqlite3.Connection \| None = None` |
| 107 | sqlite3.connect() | `self.conn = sqlite3.connect(` |
| 113 | PRAGMA command | `self.conn.execute("PRAGMA journal_mode=WAL")` |
| 114 | PRAGMA command | `self.conn.execute("PRAGMA synchronous=NORMAL")` |
| 115 | PRAGMA command | `self.conn.execute("PRAGMA temp_store=MEMORY")` |
| 116 | PRAGMA command | `self.conn.execute("PRAGMA busy_timeout=5000")` |
| 117 | PRAGMA command | `self.conn.execute("PRAGMA foreign_keys=OFF")  # K0 invariants enforced` |
| 120 | sqlite3.Row | `self.conn.row_factory = sqlite3.Row` |
| 359 | sqlite3.Cursor type | `def execute(self, sql: str, params: tuple[Any, ...] \| None = None) -> |
| 367 | sqlite3.Cursor type | `sqlite3.Cursor: Query result cursor` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 113 | execute() | `self.conn.execute("PRAGMA journal_mode=WAL")` |
| 114 | execute() | `self.conn.execute("PRAGMA synchronous=NORMAL")` |
| 115 | execute() | `self.conn.execute("PRAGMA temp_store=MEMORY")` |
| 116 | execute() | `self.conn.execute("PRAGMA busy_timeout=5000")` |
| 117 | execute() | `self.conn.execute("PRAGMA foreign_keys=OFF")  # K0 invariants enforced` |
| 153 | execute() | `self.conn.execute("BEGIN")` |
| 240 | execute() | `cursor = self.conn.execute(` |
| 288 | execute() | `cursor = self.conn.execute(` |
| 292 | fetchall() | `rows = [dict(row) for row in cursor.fetchall()]` |
| 332 | execute() | `cursor = self.conn.execute(` |
| 336 | fetchall() | `rows = [dict(row) for row in cursor.fetchall()]` |
| 377 | execute() | `cursor = self.conn.execute(sql, params or ())` |

---

### `k0/storage\wal.py`

**SQLite:** 10 | **Async Wrappers:** 4 | **Execute Calls:** 7

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 8 | import sqlite3 | `import sqlite3` |
| 61 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 62 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 116 | sqlite3.Connection type | `async def append(self, entry: WalEntry, *, connection: sqlite3.Connect` |
| 179 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 188 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 232 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 258 | PRAGMA command | `database_list = conn.execute("PRAGMA database_list").fetchall()` |
| 293 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 307 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 162 | run_in_executor | `position = await loop.run_in_executor(None, _execute_append)` |
| 182 | run_in_executor | `return await loop.run_in_executor(None, self._read_from_sync, position` |
| 284 | run_in_executor | `await loop.run_in_executor(None, _execute_fsync)` |
| 297 | run_in_executor | `return await loop.run_in_executor(` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 122 | execute() | `cursor = conn.execute(` |
| 191 | execute() | `rows = conn.execute(` |
| 200 | fetchall() | `).fetchall()` |
| 258 | execute() | `database_list = conn.execute("PRAGMA database_list").fetchall()` |
| 258 | fetchall() | `database_list = conn.execute("PRAGMA database_list").fetchall()` |
| 310 | execute() | `row = conn.execute(` |
| 316 | fetchone() | `).fetchone()` |

---

### `k0/deploy\provision_device.py`

**SQLite:** 5 | **Async Wrappers:** 0 | **Execute Calls:** 14

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 25 | import sqlite3 | `import sqlite3` |
| 93 | sqlite3.connect() | `conn = sqlite3.connect(self.db_path)` |
| 166 | sqlite3.connect() | `conn = sqlite3.connect(self.db_path)` |
| 205 | sqlite3.connect() | `conn = sqlite3.connect(self.db_path)` |
| 235 | sqlite3.connect() | `conn = sqlite3.connect(self.db_path)` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 96 | execute() | `cursor.execute("SELECT device_id FROM devices WHERE device_id = ?", (d` |
| 97 | fetchone() | `existing = cursor.fetchone()` |
| 109 | execute() | `cursor.execute("DELETE FROM devices WHERE device_id = ?", (device_id,)` |
| 114 | execute() | `cursor.execute(` |
| 134 | execute() | `cursor.execute("SELECT * FROM devices WHERE device_id = ?", (device_id` |
| 135 | fetchone() | `device_record = cursor.fetchone()` |
| 170 | execute() | `cursor.execute(` |
| 178 | execute() | `cursor.execute(` |
| 185 | fetchall() | `devices = cursor.fetchall()` |
| 209 | execute() | `cursor.execute("SELECT device_id FROM devices WHERE device_id = ?", (d` |
| 210 | fetchone() | `if not cursor.fetchone():` |
| 215 | execute() | `cursor.execute("DELETE FROM devices WHERE device_id = ?", (device_id,)` |
| 238 | execute() | `cursor.execute(` |
| 245 | fetchone() | `device = cursor.fetchone()` |

---

### `k0/policy\retention_enforcer.py`

**SQLite:** 9 | **Async Wrappers:** 0 | **Execute Calls:** 10

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 13 | import sqlite3 | `import sqlite3` |
| 90 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 101 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 163 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 172 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 212 | sqlite3.Connection type | `self, conn: sqlite3.Connection, enabled_only: bool = False` |
| 236 | sqlite3.Connection type | `self, conn: sqlite3.Connection, policy: RetentionPolicy` |
| 284 | sqlite3.Connection type | `self, conn: sqlite3.Connection, policy: RetentionPolicy, resource: dic` |
| 320 | sqlite3.Connection type | `self, conn: sqlite3.Connection, resource_type: str, resource_id: str, |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 184 | execute() | `policy_row = conn.execute(` |
| 187 | fetchone() | `).fetchone()` |
| 219 | execute() | `rows = conn.execute(query).fetchall()` |
| 219 | fetchall() | `rows = conn.execute(query).fetchall()` |
| 257 | execute() | `rows = conn.execute(query, params).fetchall()` |
| 257 | fetchall() | `rows = conn.execute(query, params).fetchall()` |
| 294 | execute() | `row = conn.execute(` |
| 297 | fetchone() | `).fetchone()` |
| 306 | execute() | `conn.execute(` |
| 323 | execute() | `conn.execute(` |

---

### `k0/storage\dlq.py`

**SQLite:** 9 | **Async Wrappers:** 0 | **Execute Calls:** 9

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 5 | import sqlite3 | `import sqlite3` |
| 35 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 36 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 53 | sqlite3.Connection type | `def record(self, letter: DeadLetter, *, connection: sqlite3.Connection` |
| 126 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 176 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 210 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 230 | sqlite3.Connection type | `def _get_next_requeue_seq(self, connection: sqlite3.Connection) -> int` |
| 246 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 62 | execute() | `cursor = conn.execute(` |
| 151 | execute() | `rows = conn.execute(query, parameters).fetchall()` |
| 151 | fetchall() | `rows = conn.execute(query, parameters).fetchall()` |
| 179 | execute() | `row = conn.execute(` |
| 185 | fetchone() | `).fetchone()` |
| 222 | execute() | `cursor = conn.execute(` |
| 236 | execute() | `row = connection.execute(` |
| 238 | fetchone() | `).fetchone()` |
| 249 | execute() | `cursor = conn.execute(` |

---

### `k0/scripts\sqlite_migration_audit.py`

**SQLite:** 17 | **Async Wrappers:** 0 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 22 | sqlite3.connect() | `(r"sqlite3\.connect\s*\(", "sqlite3.connect()"),` |
| 32 | PRAGMA command | `(r"PRAGMA\s+journal_mode", "PRAGMA journal_mode"),` |
| 33 | PRAGMA command | `(r"PRAGMA\s+synchronous", "PRAGMA synchronous"),` |
| 34 | PRAGMA command | `(r"PRAGMA\s+foreign_keys", "PRAGMA foreign_keys"),` |
| 35 | PRAGMA command | `(r"PRAGMA\s+temp_store", "PRAGMA temp_store"),` |
| 36 | PRAGMA command | `(r"PRAGMA\s+busy_timeout", "PRAGMA busy_timeout"),` |
| 37 | PRAGMA command | `(r"PRAGMA\s+wal_checkpoint", "PRAGMA wal_checkpoint"),` |
| 38 | PRAGMA command | `(r"PRAGMA\s+wal_autocheckpoint", "PRAGMA wal_autocheckpoint"),` |
| 39 | PRAGMA command | `(r"PRAGMA\s+table_info", "PRAGMA table_info"),` |
| 40 | PRAGMA command | `(r"PRAGMA\s+database_list", "PRAGMA database_list"),` |
| 60 | sqlite3.Connection type | `(r"sqlite3\.Connection", "sqlite3.Connection type"),` |
| 61 | sqlite3.Cursor type | `(r"sqlite3\.Cursor", "sqlite3.Cursor type"),` |
| 62 | sqlite3.Row | `(r"sqlite3\.Row", "sqlite3.Row"),` |
| 63 | row_factory | `(r"row_factory", "row_factory"),` |
| 294 | PRAGMA command | `lines.append("\|PRAGMA journal_mode=WAL` \| N/A (native) \| PostgreSQL ` |
| 295 | PRAGMA command | `lines.append("\|PRAGMA busy_timeout`\ Connection pool timeout \| Pool` |
| 296 | PRAGMA command | `lines.append("\|PRAGMA foreign_keys=ON` \| Default ON in PostgreSQL \| ` |

---

### `k0/drivers\embedding_queue.py`

**SQLite:** 2 | **Async Wrappers:** 0 | **Execute Calls:** 13

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 40 | import sqlite3 | `import sqlite3` |
| 117 | sqlite3.Row | `conn.row_factory = sqlite3.Row` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 160 | execute() | `cursor = conn.execute(` |
| 177 | fetchone() | `row = cursor.fetchone()` |
| 186 | execute() | `event_cursor = conn.execute(` |
| 195 | fetchone() | `event_row = event_cursor.fetchone()` |
| 209 | execute() | `conn.execute(` |
| 238 | execute() | `cursor = conn.execute(` |
| 247 | fetchone() | `row = cursor.fetchone()` |
| 253 | execute() | `conn.execute(` |
| 276 | execute() | `conn.execute(` |
| 298 | execute() | `cursor = conn.execute(` |
| 307 | fetchone() | `row = cursor.fetchone()` |
| 315 | execute() | `conn.execute(` |
| 341 | execute() | `conn.execute(` |

---

### `k0/policy\acl_enforcer.py`

**SQLite:** 9 | **Async Wrappers:** 0 | **Execute Calls:** 6

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 12 | import sqlite3 | `import sqlite3` |
| 75 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 94 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 149 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 174 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 215 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 224 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 250 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 265 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 108 | execute() | `result = conn.execute(` |
| 128 | fetchone() | `).fetchone()` |
| 182 | execute() | `conn.execute(` |
| 232 | execute() | `conn.execute(` |
| 291 | execute() | `rows = conn.execute(query, params).fetchall()` |
| 291 | fetchall() | `rows = conn.execute(query, params).fetchall()` |

---

### `k0/scripts\find_sync_wrappers.py`

**SQLite:** 2 | **Async Wrappers:** 9 | **Execute Calls:** 4

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 25 | sqlite3.connect() | `(r"sqlite3\.connect\s*\(", "sqlite3.connect"),` |
| 213 | sqlite3.connect() | `lines.append("\|sqlite3.connect()` \| `aiosqlite.connect()` or `asyncp` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 3 | run_in_executor | `Identifies run_in_executor, asyncio.to_thread and similar patterns.` |
| 15 | run_in_executor | `(r"run_in_executor\s*\(", "run_in_executor"),` |
| 16 | asyncio.to_thread | `(r"asyncio\.to_thread\s*\(", "asyncio.to_thread"),` |
| 17 | run_in_executor | `(r"loop\.run_in_executor", "loop.run_in_executor"),` |
| 19 | ThreadPoolExecutor | `(r"ThreadPoolExecutor", "ThreadPoolExecutor"),` |
| 20 | ProcessPoolExecutor | `(r"ProcessPoolExecutor", "ProcessPoolExecutor"),` |
| 143 | run_in_executor | `f"\| Executor Wrappers (run_in_executor, etc.) \| {len(results['executor` |
| 212 | run_in_executor | `lines.append("\|loop.run_in_executor(None, func)`\ Native async func` |
| 215 | ThreadPoolExecutor | `lines.append("\|ThreadPoolExecutor` \| `asyncio.TaskGroup`o remove \|` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 26 | execute() | `(r"connection\.execute\s*\(", "connection.execute (sync)"),` |
| 27 | execute() | `(r"conn\.execute\s*\(", "conn.execute (sync)"),` |
| 28 | execute() | `(r"cursor\.execute\s*\(", "cursor.execute (sync)"),` |
| 214 | execute() | `lines.append("\|conn.execute()` \| `await conn.execute()`\")` |

---

### `k0/scripts\generate_migration_doc.py`

**SQLite:** 6 | **Async Wrappers:** 9 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 17 | sqlite3.connect() | `(r"sqlite3\.connect", "sqlite3.connect()"),` |
| 18 | sqlite3.Connection type | `(r"sqlite3\.Connection", "sqlite3.Connection type"),` |
| 19 | sqlite3.Cursor type | `(r"sqlite3\.Cursor", "sqlite3.Cursor type"),` |
| 20 | sqlite3.Row | `(r"sqlite3\.Row", "sqlite3.Row"),` |
| 21 | row_factory | `(r"row_factory", "row_factory"),` |
| 22 | PRAGMA command | `(r"PRAGMA\s+\w+", "PRAGMA command"),` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 27 | run_in_executor | `(r"run_in_executor", "run_in_executor"),` |
| 28 | ThreadPoolExecutor | `(r"ThreadPoolExecutor", "ThreadPoolExecutor"),` |
| 29 | ProcessPoolExecutor | `(r"ProcessPoolExecutor", "ProcessPoolExecutor"),` |
| 30 | asyncio.to_thread | `(r"asyncio\.to_thread", "asyncio.to_thread"),` |
| 55 | run_in_executor | `and "run_in_executor" not in content` |
| 56 | ThreadPoolExecutor | `and "ThreadPoolExecutor" not in content` |
| 102 | run_in_executor | `lines.append("2. **Sync → Async conversion** (remove run_in_executor w` |
| 118 | run_in_executor | `lines.append("\| Sync Wrappers \| run_in_executor \| Native async/await \|` |
| 136 | run_in_executor | `lines.append(f"\| Sync wrappers (run_in_executor) \| {async_files} \| {to` |

---

### `k0/storage\provisioning.py`

**SQLite:** 9 | **Async Wrappers:** 0 | **Execute Calls:** 6

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 5 | import sqlite3 | `import sqlite3` |
| 44 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 45 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 150 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 181 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 223 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 236 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 275 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 302 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 158 | execute() | `conn.execute(` |
| 190 | execute() | `conn.execute(` |
| 245 | execute() | `row = conn.execute(` |
| 251 | fetchone() | `).fetchone()` |
| 305 | execute() | `rows = conn.execute(` |
| 313 | fetchall() | `).fetchall()` |

---

### `k0/storage\replayer.py`

**SQLite:** 6 | **Async Wrappers:** 0 | **Execute Calls:** 9

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 72 | sqlite3.Row | `connection.row_factory = sqlite3.Row` |
| 300 | sqlite3.Connection type | `connection: sqlite3.Connection,` |
| 305 | sqlite3.Row | `) -> Iterable[sqlite3.Row]:` |
| 324 | sqlite3.Connection type | `connection: sqlite3.Connection,` |
| 354 | sqlite3.Connection type | `connection: sqlite3.Connection,` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 110 | execute() | `connection.execute("BEGIN IMMEDIATE")` |
| 320 | execute() | `return connection.execute(statement, params).fetchall()` |
| 320 | fetchall() | `return connection.execute(statement, params).fetchall()` |
| 333 | execute() | `row = connection.execute(` |
| 336 | fetchone() | `).fetchone()` |
| 349 | execute() | `row = connection.execute(query, params).fetchone()` |
| 349 | fetchone() | `row = connection.execute(query, params).fetchone()` |
| 366 | execute() | `_row = connection.execute(` |
| 369 | fetchone() | `).fetchone()` |

---

### `k0/storage\obligations.py`

**SQLite:** 7 | **Async Wrappers:** 0 | **Execute Calls:** 6

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 5 | import sqlite3 | `import sqlite3` |
| 28 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 29 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 46 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 70 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 97 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 124 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 49 | execute() | `cursor = conn.execute(` |
| 85 | executemany() | `conn.executemany(` |
| 100 | execute() | `rows = conn.execute(` |
| 106 | fetchall() | `).fetchall()` |
| 127 | execute() | `rows = conn.execute(` |
| 133 | fetchall() | `).fetchall()` |

---

### `k0/storage\snapshots.py`

**SQLite:** 8 | **Async Wrappers:** 0 | **Execute Calls:** 5

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 7 | import sqlite3 | `import sqlite3` |
| 88 | sqlite3.connect() | `connection = sqlite3.connect(str(self._database_path))` |
| 90 | sqlite3.Row | `connection.row_factory = sqlite3.Row` |
| 91 | PRAGMA command | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 190 | sqlite3.Connection type | `connection: sqlite3.Connection,` |
| 276 | sqlite3.Connection type | `def _write_backup(self, connection: sqlite3.Connection, artifact_path:` |
| 278 | sqlite3.connect() | `with sqlite3.connect(str(artifact_path)) as destination:` |
| 306 | sqlite3.Connection type | `def _resolve_watermark(self, connection: sqlite3.Connection) -> int:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 91 | execute() | `connection.execute("PRAGMA busy_timeout=5000;")` |
| 233 | execute() | `cursor = connection.execute(` |
| 280 | execute() | `destination.execute("VACUUM;")` |
| 307 | execute() | `cursor = connection.execute("SELECT COALESCE(MAX(pos), 0) AS watermark` |
| 308 | fetchone() | `row = cursor.fetchone()` |

---

### `k0/scripts\traffic_generator.py`

**SQLite:** 3 | **Async Wrappers:** 0 | **Execute Calls:** 9

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 34 | import sqlite3 | `import sqlite3` |
| 75 | sqlite3.connect() | `conn = sqlite3.connect(db_path)` |
| 76 | sqlite3.Row | `conn.row_factory = sqlite3.Row` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 80 | execute() | `cursor.execute("SELECT COUNT(*) as total FROM st_outbox")` |
| 81 | fetchone() | `outbox_before = cursor.fetchone()["total"]` |
| 83 | execute() | `cursor.execute(` |
| 86 | fetchone() | `outbox_pending = cursor.fetchone()["pending"]` |
| 88 | execute() | `cursor.execute("SELECT COUNT(*) as total FROM st_dlq")` |
| 89 | fetchone() | `dlq_before = cursor.fetchone()["total"]` |
| 97 | execute() | `cursor.execute("DELETE FROM st_outbox")` |
| 103 | execute() | `cursor.execute("DELETE FROM st_dlq")` |
| 110 | execute() | `conn.execute("VACUUM")` |

---

### `k0/storage\offsets.py`

**SQLite:** 7 | **Async Wrappers:** 2 | **Execute Calls:** 3

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 27 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 28 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 45 | sqlite3.Connection type | `async def upsert(self, record: Offset, *, connection: sqlite3.Connecti` |
| 50 | sqlite3.Connection type | `def _upsert_sync(self, record: Offset, connection: sqlite3.Connection |
| 78 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 92 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 48 | run_in_executor | `await loop.run_in_executor(None, self._upsert_sync, record, connection` |
| 82 | run_in_executor | `return await loop.run_in_executor(` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 54 | execute() | `conn.execute(` |
| 97 | execute() | `row = conn.execute(` |
| 103 | fetchone() | `).fetchone()` |

---

### `k0/drivers\faiss.py`

**SQLite:** 3 | **Async Wrappers:** 0 | **Execute Calls:** 8

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 40 | import sqlite3 | `import sqlite3` |
| 103 | sqlite3.Row | `conn.row_factory = sqlite3.Row` |
| 190 | sqlite3.Row | `conn.row_factory = sqlite3.Row` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 135 | execute() | `conn.execute(` |
| 151 | execute() | `conn.execute(` |
| 158 | execute() | `conn.execute(` |
| 230 | execute() | `cursor = conn.execute(` |
| 245 | fetchone() | `row = cursor.fetchone()` |
| 272 | execute() | `conn.execute(` |
| 300 | execute() | `conn.execute(` |
| 327 | execute() | `conn.execute(` |

---

### `k0/gate\minimal_gate.py`

**SQLite:** 7 | **Async Wrappers:** 0 | **Execute Calls:** 4

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 112 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 789 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 876 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 924 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 1026 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 1043 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 898 | execute() | `cursor = connection.execute(` |
| 902 | fetchone() | `row = cursor.fetchone()` |
| 947 | execute() | `cursor = connection.execute(` |
| 951 | fetchone() | `row = cursor.fetchone()` |

---

### `k0/query\drivers.py`

**SQLite:** 7 | **Async Wrappers:** 0 | **Execute Calls:** 4

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 7 | import sqlite3 | `import sqlite3` |
| 199 | sqlite3.Connection type | `connection: sqlite3.Connection,` |
| 207 | sqlite3.Row | `) -> list[sqlite3.Row]:` |
| 238 | sqlite3.Row | `def _row_to_item(self, row: sqlite3.Row) -> dict[str, Any]:` |
| 367 | sqlite3.Connection type | `connection: sqlite3.Connection,` |
| 374 | sqlite3.Row | `) -> list[sqlite3.Row]:` |
| 399 | sqlite3.Row | `def _row_to_item(self, row: sqlite3.Row) -> dict[str, Any]:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 236 | execute() | `return list(connection.execute(statement, params).fetchall())` |
| 236 | fetchall() | `return list(connection.execute(statement, params).fetchall())` |
| 397 | execute() | `return list(connection.execute(statement, params).fetchall())` |
| 397 | fetchall() | `return list(connection.execute(statement, params).fetchall())` |

---

### `k0/uow\connection_pool.py`

**SQLite:** 9 | **Async Wrappers:** 0 | **Execute Calls:** 2

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 77 | sqlite3.Connection type | `self._available: list[sqlite3.Connection] = []` |
| 82 | sqlite3.Connection type | `def acquire(self, *, timeout: float \| None = None) -> sqlite3.Connecti` |
| 135 | sqlite3.Connection type | `def release(self, connection: sqlite3.Connection) -> None:` |
| 176 | sqlite3.Connection type | `def _create_connection(self) -> sqlite3.Connection:` |
| 245 | sqlite3.connect() | `connection = sqlite3.connect(` |
| 254 | PRAGMA command | `cursor.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")` |
| 256 | sqlite3.Row | `connection.row_factory = sqlite3.Row` |
| 374 | sqlite3.Connection type | `def connection_scope(*, timeout: float \| None = None) -> Iterator[sqli` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 253 | execute() | `cursor.execute(f"PRAGMA {pragma}={value}")` |
| 254 | execute() | `cursor.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")` |

---

### `k0/storage\fts5_indexer.py`

**SQLite:** 3 | **Async Wrappers:** 0 | **Execute Calls:** 7

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 30 | import sqlite3 | `import sqlite3` |
| 48 | sqlite3.Connection type | `def __init__(self, connection: sqlite3.Connection) -> None:` |
| 53 | sqlite3.Connection type | `connection : sqlite3.Connection` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 109 | execute() | `self._connection.execute(` |
| 183 | execute() | `self._connection.execute(` |
| 231 | execute() | `self._connection.execute(` |
| 290 | execute() | `cursor = self._connection.execute(` |
| 294 | fetchall() | `return [row[0] for row in cursor.fetchall()]` |
| 341 | execute() | `cursor = self._connection.execute(` |
| 345 | fetchall() | `return [row[0] for row in cursor.fetchall()]` |

---

### `k0/storage\receipts.py`

**SQLite:** 6 | **Async Wrappers:** 1 | **Execute Calls:** 3

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 31 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 32 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 46 | sqlite3.Connection type | `self, receipt: Receipt, *, connection: sqlite3.Connection \| None = Non` |
| 52 | sqlite3.Connection type | `def save(self, receipt: Receipt, *, connection: sqlite3.Connection \| N` |
| 83 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 50 | run_in_executor | `await loop.run_in_executor(None, lambda: self.save(receipt, connection` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 54 | execute() | `conn.execute(` |
| 86 | execute() | `row = conn.execute(` |
| 92 | fetchone() | `).fetchone()` |

---

### `k0/sync\crdt_merge_logger.py`

**SQLite:** 7 | **Async Wrappers:** 0 | **Execute Calls:** 3

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 14 | import sqlite3 | `import sqlite3` |
| 77 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 104 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 159 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 174 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |
| 232 | sqlite3.Connection type | `connection: Optional[sqlite3.Connection] = None,` |
| 253 | sqlite3.Connection type | `connection : sqlite3.Connection, optional` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 116 | execute() | `conn.execute(` |
| 201 | execute() | `rows = conn.execute(query, params).fetchall()` |
| 201 | fetchall() | `rows = conn.execute(query, params).fetchall()` |

---

### `k0/idem\ledger.py`

**SQLite:** 5 | **Async Wrappers:** 0 | **Execute Calls:** 3

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 28 | sqlite3.Connection type | `connection: sqlite3.Connection \| None,` |
| 29 | sqlite3.Connection type | `) -> Iterator[sqlite3.Connection]:` |
| 67 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |
| 91 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 70 | execute() | `row = conn.execute(` |
| 73 | fetchone() | `).fetchone()` |
| 94 | execute() | `conn.execute(` |

---

### `k0/kernel\dependencies.py`

**SQLite:** 8 | **Async Wrappers:** 0 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 11 | import sqlite3 | `import sqlite3` |
| 27 | sqlite3.Connection type | `def database_session() -> Iterator[sqlite3.Connection]:` |
| 66 | sqlite3.Connection type | `ConnectionFactory = Callable[[], sqlite3.Connection]` |
| 70 | sqlite3.Connection type | `_recently_closed_connections: deque[sqlite3.Connection] = deque(maxlen` |
| 129 | sqlite3.Connection type | `def _default_connection_factory(self) -> sqlite3.Connection:` |
| 134 | sqlite3.connect() | `conn = sqlite3.connect(` |
| 139 | sqlite3.Row | `conn.row_factory = sqlite3.Row` |
| 142 | sqlite3.Connection type | `def _database_session(self) -> Iterator[sqlite3.Connection]:` |

---

### `k0/scripts\filter_production_files.py`

**SQLite:** 5 | **Async Wrappers:** 3 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 15 | sqlite3.connect() | `(r"sqlite3\.connect", "sqlite3.connect"),` |
| 16 | sqlite3.Connection type | `(r"sqlite3\.Connection", "sqlite3.Connection"),` |
| 17 | sqlite3.Cursor type | `(r"sqlite3\.Cursor", "sqlite3.Cursor"),` |
| 18 | sqlite3.Row | `(r"sqlite3\.Row", "sqlite3.Row"),` |
| 26 | row_factory | `(r"row_factory", "row_factory"),` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 24 | run_in_executor | `(r"run_in_executor", "run_in_executor"),` |
| 45 | run_in_executor | `# Quick check - skip if no sqlite3 or run_in_executor` |
| 46 | run_in_executor | `if "sqlite3" not in content and "run_in_executor" not in content:` |

---

### `k0/scripts\rebuild_faiss_index.py`

**SQLite:** 4 | **Async Wrappers:** 0 | **Execute Calls:** 4

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 26 | import sqlite3 | `import sqlite3` |
| 57 | sqlite3.Connection type | `self.conn: sqlite3.Connection \| None = None` |
| 61 | sqlite3.connect() | `self.conn = sqlite3.connect(self.db_path)` |
| 62 | sqlite3.Row | `self.conn.row_factory = sqlite3.Row` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 112 | execute() | `cursor = self.conn.execute(query)` |
| 113 | fetchone() | `row = cursor.fetchone()` |
| 134 | execute() | `cursor = self.conn.execute(query, (batch_size, offset))` |
| 135 | fetchall() | `rows = cursor.fetchall()` |

---

### `k0/drivers\fts5.py`

**SQLite:** 1 | **Async Wrappers:** 0 | **Execute Calls:** 5

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 118 | sqlite3.Row | `conn.row_factory = sqlite3.Row` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 80 | execute() | `conn.execute(` |
| 159 | execute() | `cursor = conn.execute(` |
| 176 | fetchone() | `row = cursor.fetchone()` |
| 191 | execute() | `conn.execute(` |
| 233 | execute() | `conn.execute(` |

---

### `k0/scripts\backfill_pending_embeddings.py`

**SQLite:** 4 | **Async Wrappers:** 0 | **Execute Calls:** 2

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 22 | import sqlite3 | `import sqlite3` |
| 48 | sqlite3.Connection type | `self.conn: sqlite3.Connection \| None = None` |
| 52 | sqlite3.connect() | `self.conn = sqlite3.connect(self.db_path)` |
| 53 | sqlite3.Row | `self.conn.row_factory = sqlite3.Row` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 86 | execute() | `cursor = self.conn.execute(query, params)` |
| 87 | fetchall() | `results = cursor.fetchall()` |

---

### `k0/fabric\fabric.py`

**SQLite:** 0 | **Async Wrappers:** 5 | **Execute Calls:** 0

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 12 | ThreadPoolExecutor | `- Real timeout enforcement via ThreadPoolExecutor (handlers can't bloc` |
| 28 | ThreadPoolExecutor | `from concurrent.futures import ThreadPoolExecutor` |
| 79 | ThreadPoolExecutor | `pending requests and statistics, and a ThreadPoolExecutor for` |
| 123 | ThreadPoolExecutor | `self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_na` |
| 245 | ThreadPoolExecutor | `Handler is executed via ThreadPoolExecutor with real timeout.` |

---

### `k0/fabric\registry.py`

**SQLite:** 0 | **Async Wrappers:** 2 | **Execute Calls:** 0

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 354 | run_in_executor | `await loop.run_in_executor(` |
| 416 | run_in_executor | `await loop.run_in_executor(` |

---

### `k0/kernel\app.py`

**SQLite:** 1 | **Async Wrappers:** 1 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 7 | import sqlite3 | `import sqlite3` |

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 464 | run_in_executor | `await loop.run_in_executor(None, worker_pool.process_driver, alias)` |

---

### `k0/ports\command.py`

**SQLite:** 2 | **Async Wrappers:** 0 | **Execute Calls:** 13

> **CRITICAL FILE**: HTTP command submission endpoint (`/k0/command.submit`). Uses sync `connection_scope()` context manager for MinimalGate validation and idempotency checks. All storage layer calls pass explicit `connection=` parameter within sync transaction block. Must be converted to async for PostgreSQL migration.

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 51 | connection_scope import | `from k0.uow.connection_pool import connection_scope` |
| 280 | connection_scope() | `with connection_scope() as gate_connection:` |

**Connection Usage (within sync block):**

| Line | Pattern | Code |
|------|---------|------|
| 284 | connection parameter | `connection=gate_connection,` |
| 322 | idem_ledger.lookup | `duplicate = idem_ledger.lookup(idem_key, connection=gate_connection)` |
| 341 | provisioning.lookup | `connection=gate_connection,` |
| 647 | uow.connection | `duplicate = idem_ledger.lookup(idem_key, connection=uow.connection)` |
| 709 | obligation_store.bulk_save | `obligation_store.bulk_save(obligation_records, connection=uow.connection)` |
| 784 | connection parameter | `connection=uow.connection,` |
| 802 | idem_ledger.upsert | `idem_ledger.upsert(ledger_entry, connection=uow.connection)` |

**Migration Notes:**


- Convert `connection_scope()` to async context manager `async with connection_scope() as gate_connection:`
- All storage layer calls (IdempotencyLedger, ProvisioningLedger, ObligationStore) must be updated to async
- UnitOfWork transaction must support async PostgreSQL connection

---

### `k0/ports\query.py`

**SQLite:** 0 | **Async Wrappers:** 1 | **Execute Calls:** 1

**Sync Wrappers to Remove:**

| Line | Pattern | Code |
|------|---------|------|
| 311 | run_in_executor | `execution_result = await loop.run_in_executor(` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 313 | execute() | `lambda: aggregator.execute(` |

---

### `k0/receipts\issuer.py`

**SQLite:** 2 | **Async Wrappers:** 0 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 6 | import sqlite3 | `import sqlite3` |
| 103 | sqlite3.Connection type | `connection: sqlite3.Connection \| None = None,` |

---

### `k0/sse\server.py`

**SQLite:** 2 | **Async Wrappers:** 0 | **Execute Calls:** 0

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 7 | import sqlite3 | `import sqlite3` |
| 61 | sqlite3.Connection type | `database_connection: sqlite3.Connection \| None = None` |

---

### `k0/storage\fts.py`

**SQLite:** 5 | **Async Wrappers:** 0 | **Execute Calls:** 6

> **CRITICAL FILE**: FTS (Full Text Search) storage using SQLite FTS5 virtual tables. Implements full-text search indexing. Must be converted to PostgreSQL tsvector + GIN indexes.

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 9 | connection_scope import | `from k0.uow.connection_pool import connection_scope` |
| 63 | connection_scope() | `with connection_scope() as connection:` |
| 90 | connection_scope() | `with connection_scope() as connection:` |
| 107 | connection_scope() | `with connection_scope() as connection:` |
| 162 | connection_scope() | `with connection_scope() as connection:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 64 | execute() | `connection.execute(INSERT OR REPLACE INTO st_fts ...)` |
| 91 | execute() | `connection.execute("DELETE FROM st_fts WHERE wal_pos = ?", ...)` |
| 129 | execute() | `rows = connection.execute(statement, params).fetchall()` |
| 129 | fetchall() | `rows = connection.execute(statement, params).fetchall()` |
| 163 | execute() | `cursor = connection.execute("SELECT count(*) as total_docs FROM st_fts")` |
| 164 | fetchone() | `total_docs = cursor.fetchone()[0]` |


**Migration Notes:**

- Replace FTS5 virtual table with PostgreSQL tsvector column + GIN index
- Convert `MATCH ?` FTS5 syntax to `@@ to_tsquery(?)` PostgreSQL syntax
- Replace `bm25(st_fts)` with `ts_rank_cd()` for relevance scoring

---

### `k0/cli\k0ctl.py`

**SQLite:** 4 | **Async Wrappers:** 0 | **Execute Calls:** 2

> CLI tool for K0 kernel administration. Uses connection_scope for database operations.

**SQLite Patterns:**

| Line | Pattern | Code |
|------|---------|------|
| 24 | connection_scope import | `from ..uow.connection_pool import configure_pool, connection_scope, shutdown_pool` |
| 921 | connection_scope() | `with connection_scope() as conn:` |
| 1015 | connection_scope() | `with connection_scope() as conn:` |
| 1380 | connection_scope() | `with connection_scope() as connection:` |

**Execute Calls:**

| Line | Pattern | Code |
|------|---------|------|
| 1016 | execute() | `rows = conn.execute(...)` |
| 1017 | fetchall() | `.fetchall()` |

---
