"""
Integration tests for CRDT Merge Logger

Tests conflict resolution audit logging using st_crdt_merge_log from Migration 0004.

Run with: python -m pytest tests/k0/integration/test_crdt_merge_logging.py -v
"""

import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

from k0.sync.crdt_merge_logger import CRDTMergeLogger, resolve_conflict_with_logging


@pytest.fixture
def temp_db_with_crdt_log():
    """Create temporary database with Migration 0004 CRDT merge log schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_crdt.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create st_crdt_merge_log table (from Migration 0004)
        conn.execute(
            """
            CREATE TABLE st_crdt_merge_log (
              merge_id TEXT PRIMARY KEY,
              resource_type TEXT NOT NULL,
              resource_id TEXT NOT NULL,
              merge_strategy TEXT NOT NULL,
              winner_device_id TEXT NOT NULL,
              loser_device_id TEXT NOT NULL,
              winner_vector_clock TEXT,
              loser_vector_clock TEXT,
              conflict_reason TEXT,
              merged_at TEXT NOT NULL,
              tenant_id TEXT,
              CHECK(merge_strategy IN ('last-write-wins', 'vector-clock', 'manual', 'semantic-merge'))
            )
        """
        )

        conn.execute(
            "CREATE INDEX idx_crdt_resource ON st_crdt_merge_log(resource_type, resource_id)"
        )
        conn.execute(
            "CREATE INDEX idx_crdt_device ON st_crdt_merge_log(winner_device_id, loser_device_id)"
        )

        conn.commit()

        yield conn, str(db_path)
        conn.close()


def test_log_merge_basic(temp_db_with_crdt_log):
    """Test basic CRDT merge logging."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    merge_id = str(uuid.uuid4())
    logger.log_merge(
        merge_id=merge_id,
        resource_type="st_epi",
        resource_id="evt_123",
        merge_strategy="vector-clock",
        winner_device_id="device_001",
        loser_device_id="device_002",
        winner_vector_clock={"device_001": 5, "device_002": 3},
        loser_vector_clock={"device_001": 4, "device_002": 4},
        conflict_reason="Concurrent edits detected",
        tenant_id="tenant_001",
        connection=conn,
    )

    # Verify log entry created
    row = conn.execute("SELECT * FROM st_crdt_merge_log WHERE merge_id = ?", (merge_id,)).fetchone()

    assert row is not None
    assert row["resource_type"] == "st_epi"
    assert row["resource_id"] == "evt_123"
    assert row["merge_strategy"] == "vector-clock"
    assert row["winner_device_id"] == "device_001"
    assert row["loser_device_id"] == "device_002"
    assert row["conflict_reason"] == "Concurrent edits detected"


def test_log_merge_with_vector_clocks(temp_db_with_crdt_log):
    """Test merge logging with vector clock serialization."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    winner_vc = {"device_A": 10, "device_B": 5, "device_C": 7}
    loser_vc = {"device_A": 9, "device_B": 6, "device_C": 7}

    merge_id = str(uuid.uuid4())
    logger.log_merge(
        merge_id=merge_id,
        resource_type="st_sem",
        resource_id="fact_456",
        merge_strategy="vector-clock",
        winner_device_id="device_A",
        loser_device_id="device_B",
        winner_vector_clock=winner_vc,
        loser_vector_clock=loser_vc,
        connection=conn,
    )

    # Verify vector clocks stored as JSON
    row = conn.execute(
        "SELECT winner_vector_clock, loser_vector_clock FROM st_crdt_merge_log WHERE merge_id = ?",
        (merge_id,),
    ).fetchone()

    import json

    assert json.loads(row["winner_vector_clock"]) == winner_vc
    assert json.loads(row["loser_vector_clock"]) == loser_vc


def test_get_merge_history_by_resource(temp_db_with_crdt_log):
    """Test retrieving merge history for specific resource."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    # Log 3 merges for same resource
    resource_id = "evt_collab"
    for i in range(3):
        logger.log_merge(
            merge_id=str(uuid.uuid4()),
            resource_type="st_epi",
            resource_id=resource_id,
            merge_strategy="last-write-wins",
            winner_device_id=f"device_{i}",
            loser_device_id=f"device_{i+1}",
            connection=conn,
        )

    # Get merge history
    history = logger.get_merge_history(
        resource_type="st_epi", resource_id=resource_id, connection=conn
    )

    assert len(history) == 3
    assert all(log.resource_id == resource_id for log in history)


def test_get_merge_history_by_device(temp_db_with_crdt_log):
    """Test retrieving merge history involving specific device."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    device_id = "device_alice"

    # Log merges where device_alice is winner
    logger.log_merge(
        merge_id=str(uuid.uuid4()),
        resource_type="st_epi",
        resource_id="evt_001",
        merge_strategy="vector-clock",
        winner_device_id=device_id,
        loser_device_id="device_bob",
        connection=conn,
    )

    # Log merges where device_alice is loser
    logger.log_merge(
        merge_id=str(uuid.uuid4()),
        resource_type="st_epi",
        resource_id="evt_002",
        merge_strategy="vector-clock",
        winner_device_id="device_charlie",
        loser_device_id=device_id,
        connection=conn,
    )

    # Get merge history for device
    history = logger.get_merge_history(device_id=device_id, connection=conn)

    assert len(history) == 2
    assert any(log.winner_device_id == device_id for log in history)
    assert any(log.loser_device_id == device_id for log in history)


def test_resolve_conflict_with_logging_vector_clock(temp_db_with_crdt_log):
    """Test resolve_conflict_with_logging using vector clock strategy."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    local_memory = {
        "device_id": "device_001",
        "vector_clock": {"device_001": 5, "device_002": 3},
        "updated_at": "2025-11-10T19:00:00Z",
        "content": "Local version",
        "tenant_id": "tenant_001",
    }

    remote_memory = {
        "device_id": "device_002",
        "vector_clock": {"device_001": 4, "device_002": 4},
        "updated_at": "2025-11-10T18:55:00Z",
        "content": "Remote version",
        "tenant_id": "tenant_001",
    }

    # Resolve conflict (local should win: vc {5,3} > {4,4})
    winner = resolve_conflict_with_logging(
        local_memory,
        remote_memory,
        resource_type="st_epi",
        resource_id="evt_conflict",
        logger=logger,
        merge_strategy="vector-clock",
        connection=conn,
    )

    assert winner["content"] == "Local version"

    # Verify merge logged
    history = logger.get_merge_history(resource_id="evt_conflict", connection=conn)
    assert len(history) == 1
    assert history[0].winner_device_id == "device_001"
    assert history[0].loser_device_id == "device_002"


def test_resolve_conflict_with_logging_last_write_wins(temp_db_with_crdt_log):
    """Test resolve_conflict_with_logging using last-write-wins strategy."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    local_memory = {
        "device_id": "device_001",
        "updated_at": "2025-11-10T18:50:00Z",  # Older
        "content": "Local version",
    }

    remote_memory = {
        "device_id": "device_002",
        "updated_at": "2025-11-10T19:00:00Z",  # Newer
        "content": "Remote version",
    }

    # Resolve conflict (remote should win: newer timestamp)
    winner = resolve_conflict_with_logging(
        local_memory,
        remote_memory,
        resource_type="st_epi",
        resource_id="evt_lww",
        logger=logger,
        merge_strategy="last-write-wins",
        connection=conn,
    )

    assert winner["content"] == "Remote version"

    # Verify merge logged
    history = logger.get_merge_history(resource_id="evt_lww", connection=conn)
    assert len(history) == 1
    assert history[0].merge_strategy == "last-write-wins"
    assert history[0].winner_device_id == "device_002"


def test_log_merge_without_vector_clocks(temp_db_with_crdt_log):
    """Test merge logging without vector clocks (manual strategy)."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    merge_id = str(uuid.uuid4())
    logger.log_merge(
        merge_id=merge_id,
        resource_type="st_epi",
        resource_id="evt_manual",
        merge_strategy="manual",
        winner_device_id="device_admin",
        loser_device_id="device_user",
        conflict_reason="Admin override",
        connection=conn,
    )

    # Verify log entry without vector clocks
    row = conn.execute("SELECT * FROM st_crdt_merge_log WHERE merge_id = ?", (merge_id,)).fetchone()

    assert row["merge_strategy"] == "manual"
    assert row["winner_vector_clock"] is None
    assert row["loser_vector_clock"] is None


def test_get_merge_history_limit(temp_db_with_crdt_log):
    """Test merge history retrieval respects limit parameter."""
    conn, _ = temp_db_with_crdt_log
    logger = CRDTMergeLogger()

    # Log 20 merges
    for i in range(20):
        logger.log_merge(
            merge_id=str(uuid.uuid4()),
            resource_type="st_epi",
            resource_id=f"evt_{i}",
            merge_strategy="vector-clock",
            winner_device_id="device_001",
            loser_device_id="device_002",
            connection=conn,
        )

    # Get history with limit=5
    history = logger.get_merge_history(limit=5, connection=conn)

    assert len(history) == 5


def test_crdt_logger_backward_compatible():
    """Test logger gracefully handles missing st_crdt_merge_log table."""
    # Create database WITHOUT st_crdt_merge_log table
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_baseline.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        logger = CRDTMergeLogger()

        # Should not raise error (prints warning instead)
        logger.log_merge(
            merge_id="test_id",
            resource_type="st_epi",
            resource_id="evt_123",
            merge_strategy="vector-clock",
            winner_device_id="device_001",
            loser_device_id="device_002",
            connection=conn,
        )

        # get_merge_history should return empty list
        history = logger.get_merge_history(connection=conn)
        assert history == []

        conn.close()
