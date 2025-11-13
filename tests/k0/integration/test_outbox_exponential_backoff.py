"""Integration tests for outbox exponential backoff (Migration 0004)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from k0.outbox.scheduler import RetryScheduler
from k0.storage.outbox import OutboxEntry, OutboxStore


@pytest.fixture
def temp_db_with_outbox(tmp_path: Path) -> Path:
    """Create temporary database with outbox table (Migration 0004 schema)."""
    db_path = tmp_path / "test_outbox.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create outbox table with new columns
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS st_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            driver TEXT NOT NULL,
            op_kind TEXT NOT NULL,
            payload BLOB NOT NULL,
            fingerprint TEXT NOT NULL,
            requeue_seq INTEGER NOT NULL DEFAULT 0,
            retries INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_attempt_ts TEXT,
            backoff_exp INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'PROCESSING', 'FAILED', 'DEAD'))
        );

        CREATE INDEX IF NOT EXISTS idx_outbox_next_attempt ON st_outbox(next_attempt_ts, status);
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_retry_decision_exponential_backoff() -> None:
    """Test: RetryScheduler calculates exponential backoff correctly."""
    scheduler = RetryScheduler(max_attempts=5)

    entry = OutboxEntry(
        id=1,
        wal_pos=100,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"test",
        fingerprint="fp_001",
        requeue_seq=0,
        retries=0,
    )

    # First retry: 2^1 = 2 seconds
    decision = scheduler.decide(entry)
    assert decision.action == "retry"
    assert decision.status == "PENDING"
    assert decision.backoff_exp == 1
    assert decision.retries == 1
    assert decision.next_attempt_ts is not None

    # Parse timestamp and verify it's ~2 seconds in future
    assert decision.next_attempt_ts is not None
    next_attempt = datetime.fromisoformat(decision.next_attempt_ts)
    now = datetime.now(timezone.utc)
    delta = (next_attempt - now).total_seconds()
    assert 1.5 < delta < 2.5  # Allow 0.5s tolerance for test execution time

    # Second retry: 2^2 = 4 seconds
    entry.retries = 1
    decision = scheduler.decide(entry)
    assert decision.backoff_exp == 2
    assert decision.next_attempt_ts is not None
    next_attempt = datetime.fromisoformat(decision.next_attempt_ts)
    delta = (next_attempt - now).total_seconds()
    assert 3.5 < delta < 4.5

    # Max retries: quarantine
    entry.retries = 4
    decision = scheduler.decide(entry)
    assert decision.action == "quarantine"
    assert decision.status == "DEAD"
    assert decision.next_attempt_ts is None


def test_outbox_store_dequeue_ready_batch(temp_db_with_outbox: Path) -> None:
    """Test: dequeue_ready_batch only returns entries WHERE next_attempt_ts <= NOW()."""
    conn = sqlite3.connect(str(temp_db_with_outbox))
    conn.row_factory = sqlite3.Row
    store = OutboxStore()

    now = datetime.now(timezone.utc)
    past = (now - timedelta(seconds=10)).isoformat()
    future = (now + timedelta(seconds=10)).isoformat()

    # Entry 1: Ready (next_attempt_ts in past)
    entry1 = OutboxEntry(
        id=None,
        wal_pos=100,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"entry1",
        fingerprint="fp_001",
        requeue_seq=0,
        retries=0,
        next_attempt_ts=past,
        backoff_exp=1,
        status="PENDING",
    )
    store.enqueue(entry1, connection=conn)

    # Entry 2: Not ready (next_attempt_ts in future)
    entry2 = OutboxEntry(
        id=None,
        wal_pos=101,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"entry2",
        fingerprint="fp_002",
        requeue_seq=0,
        retries=0,
        next_attempt_ts=future,
        backoff_exp=2,
        status="PENDING",
    )
    store.enqueue(entry2, connection=conn)

    # Entry 3: Ready (next_attempt_ts is NULL - immediate)
    entry3 = OutboxEntry(
        id=None,
        wal_pos=102,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"entry3",
        fingerprint="fp_003",
        requeue_seq=0,
        retries=0,
        next_attempt_ts=None,
        status="PENDING",
    )
    store.enqueue(entry3, connection=conn)

    conn.commit()

    # Dequeue ready batch (should return entry1 and entry3, NOT entry2)
    ready = store.dequeue_ready_batch("sqlite", limit=10, connection=conn)
    assert len(ready) == 2
    assert ready[0].payload == b"entry1"
    assert ready[1].payload == b"entry3"

    # Entry 2 should still be in outbox
    all_entries = store.dequeue_batch("sqlite", limit=10, connection=conn)
    assert len(all_entries) == 3

    conn.close()


def test_outbox_record_failure_with_backoff(temp_db_with_outbox: Path) -> None:
    """Test: record_failure updates next_attempt_ts, backoff_exp, status."""
    conn = sqlite3.connect(str(temp_db_with_outbox))
    conn.row_factory = sqlite3.Row
    store = OutboxStore()

    entry = OutboxEntry(
        id=None,
        wal_pos=100,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"test",
        fingerprint="fp_001",
        requeue_seq=0,
        retries=0,
    )
    store.enqueue(entry, connection=conn)
    conn.commit()

    # Record failure with backoff
    next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat()
    store.record_failure(
        entry,
        retries=1,
        requeue_seq=1,
        last_error="Connection timeout",
        next_attempt_ts=next_attempt,
        backoff_exp=2,
        status="PENDING",
        connection=conn,
    )
    conn.commit()

    # Verify fields updated
    assert entry.retries == 1
    assert entry.next_attempt_ts == next_attempt
    assert entry.backoff_exp == 2
    assert entry.status == "PENDING"

    # Verify in database
    cursor = conn.execute(
        "SELECT next_attempt_ts, backoff_exp, status FROM st_outbox WHERE id=?",
        (entry.id,),
    )
    row = cursor.fetchone()
    assert row["next_attempt_ts"] == next_attempt
    assert row["backoff_exp"] == 2
    assert row["status"] == "PENDING"

    conn.close()


def test_outbox_status_filtering(temp_db_with_outbox: Path) -> None:
    """Test: dequeue_ready_batch filters by status = 'PENDING'."""
    conn = sqlite3.connect(str(temp_db_with_outbox))
    conn.row_factory = sqlite3.Row
    store = OutboxStore()

    # Entry 1: PENDING
    entry1 = OutboxEntry(
        id=None,
        wal_pos=100,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"entry1",
        fingerprint="fp_001",
        requeue_seq=0,
        retries=0,
        status="PENDING",
    )
    store.enqueue(entry1, connection=conn)

    # Entry 2: DEAD (should NOT be returned)
    entry2 = OutboxEntry(
        id=None,
        wal_pos=101,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"entry2",
        fingerprint="fp_002",
        requeue_seq=0,
        retries=5,
        status="DEAD",
    )
    store.enqueue(entry2, connection=conn)

    conn.commit()

    # Dequeue ready batch (should return only entry1)
    ready = store.dequeue_ready_batch("sqlite", limit=10, connection=conn)
    assert len(ready) == 1
    assert ready[0].payload == b"entry1"

    conn.close()


def test_outbox_backoff_cap(temp_db_with_outbox: Path) -> None:
    """Test: Exponential backoff capped at 2^6 = 64 seconds."""
    scheduler = RetryScheduler(max_attempts=10)

    entry = OutboxEntry(
        id=1,
        wal_pos=100,
        tenant_id="tenant_001",
        space_id="space_001",
        driver="sqlite",
        op_kind="write",
        payload=b"test",
        fingerprint="fp_001",
        requeue_seq=0,
        retries=7,  # 8th retry
    )

    decision = scheduler.decide(entry)

    # Should be capped at 2^6 = 64 seconds
    assert decision.backoff_exp == 6
    assert decision.next_attempt_ts is not None

    next_attempt = datetime.fromisoformat(decision.next_attempt_ts)
    now = datetime.now(timezone.utc)
    delta = (next_attempt - now).total_seconds()

    # Should be ~64 seconds
    assert 63 < delta < 65


def test_performance_target_placeholder() -> None:
    """Test: Verify <5ms P95 for retry eligibility query.

    NOTE: This is a placeholder test. Actual performance testing requires:
    - Populating large outbox table (10K+ entries)
    - Running multiple dequeue_ready_batch queries
    - Measuring P95 latency with indexed next_attempt_ts

    This will be implemented in performance test suite.
    """
    # Performance test placeholder
    # See: tests/k0/performance/test_outbox_retry_query_latency.py
    pass
