"""Test async FTS indexing worker (V1.4 Performance Optimization).

Tests verify:
1. FTS worker polls Outbox for fts entries
2. Extracts keywords and indexes text
3. Updates WAL with fts_entry_id and fts_status='DONE'
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
from k0.workers.fts_worker import (
    FtsIndexingWorker,
    extract_keywords,
    fts_payload_to_request,
)


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


class TestKeywordExtraction:
    """Test keyword extraction utility."""

    def test_extract_keywords_removes_stop_words(self):
        """Verify stop words removed from keywords."""
        text = "The quick brown fox jumps over the lazy dog"
        keywords = extract_keywords(text, max_keywords=10)

        # Stop words removed
        assert "the" not in keywords
        assert "over" not in keywords

        # Content words preserved (note: stemmed to base form)
        assert "quick" in keywords
        assert "brown" in keywords
        assert "fox" in keywords
        assert "jump" in keywords  # 'jumps' is stemmed to 'jump'
        assert "lazi" in keywords  # 'lazy' is stemmed to 'lazi'
        assert "dog" in keywords

    def test_extract_keywords_limits_count(self):
        """Verify max_keywords limit enforced."""
        text = "apple banana cherry date elderberry fig grape honeydew kiwi lemon mango"
        keywords = extract_keywords(text, max_keywords=5)

        assert len(keywords) == 5

    def test_fts_payload_conversion(self):
        """Verify payload → FtsIndexRequest conversion."""
        payload = {
            "event_id": "event-123",
            "space_id": "space-1",
            "document_id": "doc-456",
            "text": "Sample text for FTS indexing",
            "document_type": "memory_event",
            "keywords": ["sample", "text", "indexing"],
        }

        request = fts_payload_to_request(payload)

        assert request.event_id == "event-123"
        assert request.space_id == "space-1"
        assert request.document_id == "doc-456"
        assert request.text == "Sample text for FTS indexing"
        assert request.document_type == "memory_event"
        assert request.keywords == ["sample", "text", "indexing"]


class TestFtsWorkerIntegration:
    """Test FTS worker with Outbox and WAL integration."""

    def test_worker_processes_outbox_entry(self, temp_db: Path):
        """Verify worker dequeues Outbox, indexes text, updates WAL."""
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row

        # Insert WAL entry
        wal_pos = 1
        conn.execute(
            "INSERT INTO st_wal (wal_pos, tenant_id, space_id, envelope_json, redacted_body_json, "
            "fts_status, fts_entry_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING", None),
        )

        # Insert Outbox entry for FTS indexing
        payload = {
            "event_id": str(uuid.uuid4()),
            "space_id": "space-1",
            "document_id": "doc-123",
            "text": "This is test text for full-text search indexing",
        }
        outbox_store = OutboxStore()
        outbox_entry = OutboxEntry(
            id=None,
            wal_pos=wal_pos,
            tenant_id="tenant-1",
            space_id="space-1",
            driver="fts",
            op_kind="INDEX_FTS",
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint="test-fp",
            requeue_seq=0,
            retries=0,
        )
        outbox_store.enqueue(outbox_entry, connection=conn)
        conn.commit()

        # Run worker
        worker = FtsIndexingWorker(db_path=temp_db, batch_size=50)
        processed = worker.run_once()

        assert processed == 1

        # Verify WAL updated
        wal_row = conn.execute(
            "SELECT fts_status, fts_entry_id FROM st_wal WHERE wal_pos=?", (wal_pos,)
        ).fetchone()
        assert wal_row["fts_status"] == "DONE"
        assert wal_row["fts_entry_id"] is not None
        assert wal_row["fts_entry_id"].startswith("fts-")

        # Verify Outbox entry deleted
        outbox_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_outbox WHERE driver='fts'"
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
                "fts_status) VALUES (?, ?, ?, ?, ?, ?)",
                (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING"),
            )

            # Insert Outbox entry with malformed payload (will fail)
            outbox_store = OutboxStore()
            outbox_entry = OutboxEntry(
                id=None,
                wal_pos=wal_pos,
                tenant_id="tenant-1",
                space_id="space-1",
                driver="fts",
                op_kind="INDEX_FTS",
                payload=b"invalid-json",  # Malformed JSON
                fingerprint="test-fp-2",
                requeue_seq=0,
                retries=0,
            )
            outbox_store.enqueue(outbox_entry, connection=conn)
            conn.commit()

            # Run worker (should fail gracefully)
            worker = FtsIndexingWorker(db_path=temp_db, batch_size=50)
            processed = worker.run_once()

            assert processed == 0  # Failed to process

            # Verify Outbox entry still exists with retry info
            outbox_row = conn.execute(
                "SELECT retries, last_error, status FROM st_outbox WHERE driver='fts'"
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
        worker = FtsIndexingWorker(db_path=temp_db, batch_size=50)
        processed = worker.run_once()

        assert processed == 0


class TestFtsWorkerBatchProcessing:
    """Test batch processing capabilities."""

    def test_worker_processes_multiple_entries(self, temp_db: Path):
        """Verify worker processes multiple Outbox entries in batch."""
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        outbox_store = OutboxStore()

        # Insert 5 WAL + Outbox entries
        for wal_pos in [20, 21, 22, 23, 24]:
            conn.execute(
                "INSERT INTO st_wal (wal_pos, tenant_id, space_id, envelope_json, redacted_body_json, "
                "fts_status) VALUES (?, ?, ?, ?, ?, ?)",
                (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING"),
            )

            payload = {
                "event_id": f"event-{wal_pos}",
                "space_id": "space-1",
                "document_id": f"doc-{wal_pos}",
                "text": f"FTS test text entry number {wal_pos}",
            }
            outbox_entry = OutboxEntry(
                id=None,
                wal_pos=wal_pos,
                tenant_id="tenant-1",
                space_id="space-1",
                driver="fts",
                op_kind="INDEX_FTS",
                payload=json.dumps(payload).encode("utf-8"),
                fingerprint=f"fp-{wal_pos}",
                requeue_seq=0,
                retries=0,
            )
            outbox_store.enqueue(outbox_entry, connection=conn)

        conn.commit()

        # Run worker
        worker = FtsIndexingWorker(db_path=temp_db, batch_size=50)
        processed = worker.run_once()

        assert processed == 5

        # Verify all WAL entries updated
        done_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_wal WHERE fts_status='DONE'"
        ).fetchone()["count"]
        assert done_count == 5

        # Verify all Outbox entries deleted
        outbox_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_outbox WHERE driver='fts'"
        ).fetchone()["count"]
        assert outbox_count == 0

        conn.close()

    def test_worker_batch_size_limit_enforced(self, temp_db: Path):
        """Verify worker respects batch_size limit."""
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        outbox_store = OutboxStore()

        # Insert 10 entries
        for wal_pos in range(100, 110):
            conn.execute(
                "INSERT INTO st_wal (wal_pos, tenant_id, space_id, envelope_json, redacted_body_json, "
                "fts_status) VALUES (?, ?, ?, ?, ?, ?)",
                (wal_pos, "tenant-1", "space-1", "{}", "{}", "PENDING"),
            )

            payload = {
                "event_id": f"event-{wal_pos}",
                "space_id": "space-1",
                "document_id": f"doc-{wal_pos}",
                "text": f"Text {wal_pos}",
            }
            outbox_entry = OutboxEntry(
                id=None,
                wal_pos=wal_pos,
                tenant_id="tenant-1",
                space_id="space-1",
                driver="fts",
                op_kind="INDEX_FTS",
                payload=json.dumps(payload).encode("utf-8"),
                fingerprint=f"fp-{wal_pos}",
                requeue_seq=0,
                retries=0,
            )
            outbox_store.enqueue(outbox_entry, connection=conn)

        conn.commit()

        # Run worker with batch_size=5
        worker = FtsIndexingWorker(db_path=temp_db, batch_size=5)
        processed = worker.run_once()

        # Should only process 5 entries (batch limit)
        assert processed == 5

        # Verify 5 WAL entries updated
        done_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_wal WHERE fts_status='DONE'"
        ).fetchone()["count"]
        assert done_count == 5

        # Verify 5 Outbox entries remaining
        outbox_count = conn.execute(
            "SELECT COUNT(*) AS count FROM st_outbox WHERE driver='fts'"
        ).fetchone()["count"]
        assert outbox_count == 5

        conn.close()
