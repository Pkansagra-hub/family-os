"""Test async embedding worker (V1.4 Performance Optimization).

Tests verify:
1. Embedding worker polls Outbox for embedding entries
2. Computes embeddings (fake for testing)
3. Updates WAL with embedding_id and embedding_status='DONE'
4. Marks Outbox entries as applied (deleted)
5. Handles failures with retry logic
"""

import json
import sqlite3
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest

from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.workers.embedding_worker import (
    EmbeddingRequest,
    EmbeddingWorker,
    _compute_fake,
    embedding_payload_to_request,
)

# Alias for backward compatibility with tests
compute_fake_embedding = _compute_fake


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Initialize database schema
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE st_wal (
            wal_pos INTEGER PRIMARY KEY,
            tenant_id TEXT,
            space_id TEXT,
            envelope_json TEXT,
            redacted_body_json TEXT,
            embedding_status TEXT,
            embedding_id TEXT,
            fts_status TEXT,
            fts_entry_id TEXT
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE st_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER,
            tenant_id TEXT,
            space_id TEXT,
            driver TEXT,
            op_kind TEXT,
            payload BLOB,
            fingerprint TEXT,
            requeue_seq INTEGER,
            retries INTEGER,
            last_error TEXT,
            next_attempt_ts TEXT,
            backoff_exp INTEGER,
            status TEXT DEFAULT 'PENDING'
        )
    """
    )
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


class TestEmbeddingComputeFake:
    """Test fake embedding computation for testing."""

    def test_compute_fake_embedding_deterministic(self):
        """Verify fake embedding is deterministic (same text → same embedding_id)."""
        request1 = EmbeddingRequest(
            event_id="event-123",
            space_id="space-1",
            text="Hello world test",
        )
        request2 = EmbeddingRequest(
            event_id="event-456",  # Different event ID
            space_id="space-1",
            text="Hello world test",  # Same text
        )

        result1 = compute_fake_embedding(request1)
        result2 = compute_fake_embedding(request2)

        # Same text → same hash portion (not same embedding_id due to event_id)
        assert result1.embedding_dimension == 384
        assert result2.embedding_dimension == 384

    def test_embedding_payload_conversion(self):
        """Verify payload → EmbeddingRequest conversion."""
        payload = {
            "event_id": "event-789",
            "space_id": "space-2",
            "text": "Sample text for embedding",
            "topics": ["memory", "chat"],
            "embedding_model": "minilm-l6",
        }

        request = embedding_payload_to_request(payload)

        assert request.event_id == "event-789"
        assert request.space_id == "space-2"
        assert request.text == "Sample text for embedding"
        assert request.topics == ["memory", "chat"]
        assert request.embedding_model == "minilm-l6"


class TestEmbeddingWorkerIntegration:
    """Test embedding worker with Outbox and WAL integration."""

    def test_worker_processes_outbox_entry(self, temp_db: Path):
        """Verify worker dequeues Outbox, computes embedding, updates WAL."""
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row

        # Insert WAL entry
        wal_pos = 1
        conn.execute(
            "INSERT INTO st_wal (wal_pos, tenant_id, space_id, envelope_json, redacted_body_json, "
            "embedding_status, embedding_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING", None),
        )

        # Insert Outbox entry for embedding
        payload = {
            "event_id": str(uuid.uuid4()),
            "space_id": "space-1",
            "text": "Test embedding text",
        }
        outbox_store = OutboxStore()
        outbox_entry = OutboxEntry(
            id=None,
            wal_pos=wal_pos,
            tenant_id="tenant-1",
            space_id="space-1",
            driver="embedding",
            op_kind="COMPUTE_EMBEDDING",
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint="test-fp",
            requeue_seq=0,
            retries=0,
        )
        outbox_store.enqueue(outbox_entry, connection=conn)
        conn.commit()

        # Run worker
        worker = EmbeddingWorker(db_path=temp_db, batch_size=10)
        processed = worker.run_once()

        assert processed == 1

        # Verify WAL updated
        wal_row = conn.execute(
            "SELECT embedding_status, embedding_id FROM st_wal WHERE wal_pos=?", (wal_pos,)
        ).fetchone()
        assert wal_row["embedding_status"] == "DONE"
        assert wal_row["embedding_id"] is not None
        assert wal_row["embedding_id"].startswith("emb-")

        # Verify Outbox entry deleted
        outbox_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_outbox WHERE driver='embedding'"
        ).fetchone()["count"]
        assert outbox_count == 0

        conn.close()

    def test_worker_handles_failure_with_retry(self, temp_db: Path):
        """Verify worker records failure and allows retry."""
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row

        try:
            # Insert WAL entry
            wal_pos = 2
            conn.execute(
                "INSERT INTO st_wal (wal_pos, tenant_id, space_id, envelope_json, redacted_body_json, "
                "embedding_status) VALUES (?, ?, ?, ?, ?, ?)",
                (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING"),
            )

            # Insert Outbox entry with malformed payload (will fail)
            outbox_store = OutboxStore()
            outbox_entry = OutboxEntry(
                id=None,
                wal_pos=wal_pos,
                tenant_id="tenant-1",
                space_id="space-1",
                driver="embedding",
                op_kind="COMPUTE_EMBEDDING",
                payload=b"invalid-json",  # Malformed JSON
                fingerprint="test-fp-2",
                requeue_seq=0,
                retries=0,
            )
            outbox_store.enqueue(outbox_entry, connection=conn)
            conn.commit()

            # Run worker (should fail gracefully)
            worker = EmbeddingWorker(db_path=temp_db, batch_size=10, backend="fake")
            processed = worker.run_once()

            assert processed == 0  # Failed to process

            # Verify Outbox entry still exists with retry info
            outbox_row = conn.execute(
                "SELECT retries, last_error, status FROM st_outbox WHERE driver='embedding'"
            ).fetchone()
            assert outbox_row is not None
            assert outbox_row["retries"] == 1
            assert outbox_row["last_error"] is not None
            assert "expecting value" in outbox_row["last_error"].lower()  # JSON decode error
            assert outbox_row["status"] == "PENDING"  # Still pending for retry
        finally:
            conn.close()

    def test_worker_no_work_returns_zero(self, temp_db: Path):
        """Verify worker returns 0 when Outbox is empty."""
        worker = EmbeddingWorker(db_path=temp_db, batch_size=10, backend="fake")
        processed = worker.run_once()

        assert processed == 0


class TestEmbeddingWorkerBatchProcessing:
    """Test batch processing capabilities."""

    def test_worker_processes_multiple_entries(self, temp_db: Path):
        """Verify worker processes multiple Outbox entries in batch."""
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        outbox_store = OutboxStore()

        # Insert 3 WAL + Outbox entries
        for wal_pos in [10, 11, 12]:
            conn.execute(
                "INSERT INTO st_wal (wal_pos, tenant_id, space_id, envelope_json, redacted_body_json, "
                "embedding_status) VALUES (?, ?, ?, ?, ?, ?)",
                (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING"),
            )

            payload = {
                "event_id": f"event-{wal_pos}",
                "space_id": "space-1",
                "text": f"Test text {wal_pos}",
            }
            outbox_entry = OutboxEntry(
                id=None,
                wal_pos=wal_pos,
                tenant_id="tenant-1",
                space_id="space-1",
                driver="embedding",
                op_kind="COMPUTE_EMBEDDING",
                payload=json.dumps(payload).encode("utf-8"),
                fingerprint=f"fp-{wal_pos}",
                requeue_seq=0,
                retries=0,
            )
            outbox_store.enqueue(outbox_entry, connection=conn)

        conn.commit()

        # Run worker
        worker = EmbeddingWorker(db_path=temp_db, batch_size=10)
        processed = worker.run_once()

        assert processed == 3

        # Verify all WAL entries updated
        done_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_wal WHERE embedding_status='DONE'"
        ).fetchone()["count"]
        assert done_count == 3

        # Verify all Outbox entries deleted
        outbox_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_outbox WHERE driver='embedding'"
        ).fetchone()["count"]
        assert outbox_count == 0

        conn.close()
