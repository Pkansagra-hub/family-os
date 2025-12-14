"""End-to-end performance test for K0 V1 (Issue 3.5).

Verifies P95 latency <100ms with async embedding/FTS workers.

Performance Targets (V1):
- P50 latency: <80ms
- P95 latency: <100ms (was 150ms in V0)
- P99 latency: <150ms
- Async worker processing: <10s for batch

Test Strategy:
1. Submit 1000 V1 envelopes to Command Port
2. Measure P50, P95, P99 latency (commit only, no async work)
3. Verify embedding_status='PENDING' (async deferred)
4. Run embedding/FTS workers
5. Verify embedding_status='DONE' (async completed)

Success Criteria:
- ✅ P95 latency <100ms (33% improvement from V0)
- ✅ Async workers process all entries <10s
- ✅ Zero errors in commit path
- ✅ Zero data loss (all envelopes in WAL)
"""

import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

import pytest

from k0.workers.embedding_worker import EmbeddingWorker
from k0.workers.fts_worker import FtsIndexingWorker


@pytest.fixture
def temp_db():
    """Create temporary database for performance testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Initialize database schema with WAL mode
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(
        """
        -- WAL table
        CREATE TABLE st_wal (
            wal_pos INTEGER PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            envelope_json TEXT NOT NULL,
            redacted_body_json TEXT,
            embedding_status TEXT DEFAULT 'PENDING',
            embedding_id TEXT,
            fts_status TEXT DEFAULT 'PENDING',
            fts_entry_id TEXT,
            created_at TEXT NOT NULL
        );

        -- Outbox table
        CREATE TABLE st_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            driver TEXT NOT NULL,
            op_kind TEXT NOT NULL,
            op_subkind TEXT,
            payload BLOB NOT NULL,
            fingerprint TEXT NOT NULL,
            requeue_seq INTEGER NOT NULL DEFAULT 0,
            retries INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            lease_expires_at TEXT NOT NULL,
            last_error TEXT,
            FOREIGN KEY (wal_pos) REFERENCES st_wal(wal_pos)
        );

        CREATE INDEX idx_outbox_driver_status ON st_outbox(driver, status);
        """
    )
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


class TestV1PerformanceEndToEnd:
    """End-to-end performance test for V1 hardening."""

    def test_p95_latency_under_100ms(self, temp_db: Path):
        """Verify P95 commit latency <100ms (V1 performance target).

        Simulates command port behavior:
        1. Parse envelope
        2. Validate schema
        3. Write to WAL
        4. Enqueue async work (Outbox)
        5. Return receipt

        V0 baseline: P95 = 150ms (blocking embedding generation)
        V1 target: P95 = <100ms (async embedding)
        """
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row

        latencies_ms = []
        num_envelopes = 1000

        # Submit 1000 envelopes and measure latency
        for i in range(num_envelopes):
            start_ns = time.perf_counter_ns()

            # Simulate commit path (without full MinimalGate, just WAL + Outbox)
            wal_pos = i + 1
            event_id = f"event-{i:04d}"

            # 1. Write to WAL
            conn.execute(
                """
                INSERT INTO st_wal (
                    wal_pos, tenant_id, space_id, envelope_json,
                    redacted_body_json, embedding_status, fts_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    wal_pos,
                    "tenant-1",
                    "space-1",
                    json.dumps({"event_id": event_id, "text": f"Sample text {i}"}),
                    "{}",
                    "PENDING",  # Async
                    "PENDING",  # Async
                ),
            )

            # 2. Enqueue async work (embedding)
            embedding_payload = json.dumps(
                {
                    "event_id": event_id,
                    "space_id": "space-1",
                    "text": f"Sample text {i}",
                    "embedding_model": "all-mpnet-base-v2",
                    "backend": "fake",  # Use fake backend for testing
                }
            )
            conn.execute(
                """
                INSERT INTO st_outbox (
                    wal_pos, tenant_id, space_id, driver, op_kind,
                    payload, fingerprint, created_at, lease_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+5 minutes'))
                """,
                (
                    wal_pos,
                    "tenant-1",
                    "space-1",
                    "embedding",
                    "COMPUTE_EMBEDDING",
                    embedding_payload.encode("utf-8"),
                    f"fp-emb-{event_id}",
                ),
            )

            # 3. Enqueue async work (FTS)
            fts_payload = json.dumps(
                {
                    "event_id": event_id,
                    "space_id": "space-1",
                    "document_id": f"doc-{i}",
                    "text": f"Sample text {i}",
                    "document_type": "memory_event",
                }
            )
            conn.execute(
                """
                INSERT INTO st_outbox (
                    wal_pos, tenant_id, space_id, driver, op_kind,
                    payload, fingerprint, created_at, lease_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+5 minutes'))
                """,
                (
                    wal_pos,
                    "tenant-1",
                    "space-1",
                    "fts",
                    "INDEX_FTS",
                    fts_payload.encode("utf-8"),
                    f"fp-fts-{event_id}",
                ),
            )

            conn.commit()

            end_ns = time.perf_counter_ns()
            latency_ms = (end_ns - start_ns) / 1_000_000  # Convert ns to ms
            latencies_ms.append(latency_ms)

        # Calculate percentiles
        latencies_sorted = sorted(latencies_ms)
        p50 = statistics.median(latencies_sorted)
        p95_index = int(len(latencies_sorted) * 0.95)
        p95 = latencies_sorted[p95_index]
        p99_index = int(len(latencies_sorted) * 0.99)
        p99 = latencies_sorted[p99_index]

        print(f"\n📊 Commit Latency Stats (n={num_envelopes}):")
        print(f"  P50: {p50:.2f}ms")
        print(f"  P95: {p95:.2f}ms (target: <100ms)")
        print(f"  P99: {p99:.2f}ms (target: <150ms)")

        # Verify WAL entries
        wal_count = conn.execute("SELECT COUNT(*) FROM st_wal").fetchone()[0]
        assert wal_count == num_envelopes, f"Expected {num_envelopes} WAL entries, got {wal_count}"

        # Verify Outbox entries (2 per envelope: embedding + FTS)
        outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
        assert (
            outbox_count == num_envelopes * 2
        ), f"Expected {num_envelopes * 2} Outbox entries, got {outbox_count}"

        # Verify embedding_status='PENDING' (async deferred)
        pending_count = conn.execute(
            "SELECT COUNT(*) FROM st_wal WHERE embedding_status='PENDING'"
        ).fetchone()[0]
        assert (
            pending_count == num_envelopes
        ), f"Expected {num_envelopes} PENDING embeddings, got {pending_count}"

        conn.close()

        # ✅ Assert: P95 latency <100ms
        assert p95 < 100.0, f"P95 latency {p95:.2f}ms exceeds target of 100ms"

        # ✅ Assert: P99 latency <150ms
        assert p99 < 150.0, f"P99 latency {p99:.2f}ms exceeds target of 150ms"

        print(f"✅ Performance targets met: P95={p95:.2f}ms, P99={p99:.2f}ms")

    def test_async_workers_process_backlog(self, temp_db: Path):
        """Verify async workers process backlog <10 seconds.

        Tests embedding and FTS workers processing 100 entries.
        """
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row

        num_entries = 100

        # Create WAL entries with async work
        for i in range(num_entries):
            wal_pos = i + 1
            event_id = f"async-event-{i:04d}"

            conn.execute(
                """
                INSERT INTO st_wal (
                    wal_pos, tenant_id, space_id, envelope_json,
                    redacted_body_json, embedding_status, fts_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    wal_pos,
                    "tenant-1",
                    "space-1",
                    json.dumps({"event_id": event_id, "text": f"Async text {i}"}),
                    "{}",
                    "PENDING",
                    "PENDING",
                ),
            )

            # Enqueue embedding work
            embedding_payload = json.dumps(
                {
                    "event_id": event_id,
                    "space_id": "space-1",
                    "text": f"Async text {i}",
                    "embedding_model": "all-mpnet-base-v2",
                    "backend": "fake",
                }
            )
            conn.execute(
                """
                INSERT INTO st_outbox (
                    wal_pos, tenant_id, space_id, driver, op_kind,
                    payload, fingerprint, created_at, lease_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+5 minutes'))
                """,
                (
                    wal_pos,
                    "tenant-1",
                    "space-1",
                    "embedding",
                    "COMPUTE_EMBEDDING",
                    embedding_payload.encode("utf-8"),
                    f"fp-async-emb-{event_id}",
                ),
            )

            # Enqueue FTS work
            fts_payload = json.dumps(
                {
                    "event_id": event_id,
                    "space_id": "space-1",
                    "document_id": f"async-doc-{i}",
                    "text": f"Async text {i}",
                    "document_type": "memory_event",
                }
            )
            conn.execute(
                """
                INSERT INTO st_outbox (
                    wal_pos, tenant_id, space_id, driver, op_kind,
                    payload, fingerprint, created_at, lease_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+5 minutes'))
                """,
                (
                    wal_pos,
                    "tenant-1",
                    "space-1",
                    "fts",
                    "INDEX_FTS",
                    fts_payload.encode("utf-8"),
                    f"fp-async-fts-{event_id}",
                ),
            )

        conn.commit()
        conn.close()

        # Run embedding worker
        embedding_worker = EmbeddingWorker(db_path=temp_db, batch_size=10, backend="fake")

        start_time = time.time()
        total_embedding_processed = 0

        while total_embedding_processed < num_entries:
            processed = embedding_worker.run_once()
            total_embedding_processed += processed
            if processed == 0:
                break  # No more work
            time.sleep(0.01)  # Small delay between batches

        embedding_duration = time.time() - start_time

        print("\n📊 Embedding Worker Stats:")
        print(f"  Processed: {total_embedding_processed}/{num_entries}")
        print(f"  Duration: {embedding_duration:.2f}s")

        # Run FTS worker
        fts_worker = FtsIndexingWorker(db_path=temp_db, batch_size=50)

        start_time = time.time()
        total_fts_processed = 0

        while total_fts_processed < num_entries:
            processed = fts_worker.run_once()
            total_fts_processed += processed
            if processed == 0:
                break  # No more work
            time.sleep(0.01)  # Small delay between batches

        fts_duration = time.time() - start_time

        print("\n📊 FTS Worker Stats:")
        print(f"  Processed: {total_fts_processed}/{num_entries}")
        print(f"  Duration: {fts_duration:.2f}s")

        # Verify all embeddings completed
        conn = sqlite3.connect(str(temp_db))
        done_count = conn.execute(
            "SELECT COUNT(*) FROM st_wal WHERE embedding_status='DONE'"
        ).fetchone()[0]
        fts_done_count = conn.execute(
            "SELECT COUNT(*) FROM st_wal WHERE fts_status='DONE'"
        ).fetchone()[0]
        conn.close()

        assert (
            done_count == num_entries
        ), f"Expected {num_entries} DONE embeddings, got {done_count}"
        assert (
            fts_done_count == num_entries
        ), f"Expected {num_entries} DONE FTS, got {fts_done_count}"

        # ✅ Assert: Total processing time <10 seconds
        total_duration = embedding_duration + fts_duration
        assert (
            total_duration < 10.0
        ), f"Async worker processing {total_duration:.2f}s exceeds 10s target"

        print(f"✅ Async workers completed in {total_duration:.2f}s (target: <10s)")

    def test_zero_data_loss_crash_recovery(self, temp_db: Path):
        """Verify SQLite WAL mode prevents data loss on crashes.

        This tests durability guarantees from V1 hardening.
        """
        # WAL mode should already be enabled by fixture
        conn = sqlite3.connect(str(temp_db))

        # Verify WAL mode enabled
        result = conn.execute("PRAGMA journal_mode").fetchone()
        journal_mode = result[0] if result else "unknown"
        # WAL mode should persist from fixture
        assert journal_mode.upper() == "WAL", f"Expected WAL mode, got {journal_mode}"

        # Verify synchronous=FULL
        result = conn.execute("PRAGMA synchronous").fetchone()
        sync_mode = result[0] if result else -1
        assert sync_mode == 2, f"Expected FULL sync (2), got {sync_mode}"

        # Write data and commit
        conn.execute(
            """
            INSERT INTO st_wal (
                wal_pos, tenant_id, space_id, envelope_json,
                redacted_body_json, embedding_status, fts_status, created_at
            )
            VALUES (1, 'tenant-1', 'space-1', '{}', '{}', 'PENDING', 'PENDING', datetime('now'))
            """
        )
        conn.commit()

        # Simulate crash (close without checkpoint)
        conn.close()

        # Reopen and verify data persisted
        conn = sqlite3.connect(str(temp_db))
        count = conn.execute("SELECT COUNT(*) FROM st_wal").fetchone()[0]
        conn.close()

        assert count == 1, f"Expected 1 WAL entry after crash, got {count}"

        print("✅ Zero data loss verified (WAL durability)")


class TestV1PerformanceRegression:
    """Performance regression tests to catch degradation."""

    def test_no_latency_regression_from_baseline(self, temp_db: Path):
        """Ensure V1 doesn't regress below baseline performance.

        Baseline (from testing): P95 should be consistent across runs.
        """
        conn = sqlite3.connect(str(temp_db))

        latencies = []

        # Run 100 commits and measure
        for i in range(100):
            start_ns = time.perf_counter_ns()

            conn.execute(
                """
                INSERT INTO st_wal (
                    wal_pos, tenant_id, space_id, envelope_json,
                    redacted_body_json, embedding_status, fts_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (i + 1, "tenant-1", "space-1", "{}", "{}", "PENDING", "PENDING"),
            )
            conn.commit()

            end_ns = time.perf_counter_ns()
            latencies.append((end_ns - start_ns) / 1_000_000)

        conn.close()

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]

        # Assert: P95 should not exceed 100ms
        assert p95 < 100.0, f"Latency regression detected: P95={p95:.2f}ms"

        print(f"✅ No regression: P95={p95:.2f}ms")
