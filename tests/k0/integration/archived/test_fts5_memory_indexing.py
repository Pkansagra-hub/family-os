"""Integration tests for FTS5 memory indexing (Migration 0004)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from k0.storage.fts5_indexer import FTS5Indexer


@pytest.fixture
def temp_db_with_fts5(tmp_path: Path) -> Path:
    """Create temporary database with FTS5 memory tables."""
    db_path = tmp_path / "test_fts5.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create FTS5 tables (from Migration 0004)
    conn.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS st_epi_fts USING fts5(
            event_id UNINDEXED,
            tenant_id UNINDEXED,
            space_id UNINDEXED,
            text,
            summary,
            tags,
            topics,
            location_names,
            participant_names,
            commit_ts UNINDEXED
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS st_hipp_fts USING fts5(
            event_id UNINDEXED,
            tenant_id UNINDEXED,
            space_id UNINDEXED,
            text,
            topics,
            categories,
            participant_names,
            location_name UNINDEXED,
            commit_ts UNINDEXED
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_index_episodic_memory(temp_db_with_fts5: Path) -> None:
    """Test: Write episodic memory → FTS5 indexed → Search returns results."""
    conn = sqlite3.connect(str(temp_db_with_fts5))
    conn.row_factory = sqlite3.Row
    indexer = FTS5Indexer(conn)

    # Index episodic memory
    indexer.index_episodic(
        event_id="evt_123",
        text="Had dinner with Mom at Olive Garden",
        summary="Family dinner",
        tags=["family", "dinner"],
        topics=["social", "food"],
        location_names=["Olive Garden"],
        participant_names=["Mom"],
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T19:00:00Z",
    )
    conn.commit()

    # Search for keyword
    results = indexer.search_episodic("dinner Mom")
    assert results == ["evt_123"]

    # Search for location
    results = indexer.search_episodic("Olive Garden")
    assert results == ["evt_123"]

    # Search with no results
    results = indexer.search_episodic("breakfast")
    assert results == []

    conn.close()


def test_index_hippocampus_memory(temp_db_with_fts5: Path) -> None:
    """Test: Write hippocampus memory → FTS5 indexed → Search returns results."""
    conn = sqlite3.connect(str(temp_db_with_fts5))
    conn.row_factory = sqlite3.Row
    indexer = FTS5Indexer(conn)

    # Index hippocampus memory
    indexer.index_hippocampus(
        event_id="evt_456",
        text="User mentioned upcoming doctor appointment next week",
        topics=["health", "appointment"],
        categories=["medical", "reminder"],
        participant_names=["User"],
        location_name="Medical Center",
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T14:00:00Z",
    )
    conn.commit()

    # Search for keyword
    results = indexer.search_hippocampus("doctor appointment")
    assert results == ["evt_456"]

    # Search for topic
    results = indexer.search_hippocampus("health")
    assert results == ["evt_456"]

    conn.close()


def test_remove_from_index(temp_db_with_fts5: Path) -> None:
    """Test: Delete memory → Verify removed from FTS5."""
    conn = sqlite3.connect(str(temp_db_with_fts5))
    conn.row_factory = sqlite3.Row
    indexer = FTS5Indexer(conn)

    # Index memory
    indexer.index_episodic(
        event_id="evt_789",
        text="Temporary memory to delete",
        summary="Test",
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T20:00:00Z",
    )
    conn.commit()

    # Verify indexed
    results = indexer.search_episodic("Temporary")
    assert results == ["evt_789"]

    # Remove from index
    indexer.remove_from_index("st_epi_fts", "evt_789")
    conn.commit()

    # Verify removed
    results = indexer.search_episodic("Temporary")
    assert results == []

    conn.close()


def test_fts5_phrase_search(temp_db_with_fts5: Path) -> None:
    """Test: FTS5 phrase search with quotes."""
    conn = sqlite3.connect(str(temp_db_with_fts5))
    conn.row_factory = sqlite3.Row
    indexer = FTS5Indexer(conn)

    indexer.index_episodic(
        event_id="evt_001",
        text="Olive Garden has great breadsticks",
        summary="Restaurant review",
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T18:00:00Z",
    )
    indexer.index_episodic(
        event_id="evt_002",
        text="Met Mom at Olive Street",
        summary="Meeting",
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T19:00:00Z",
    )
    conn.commit()

    # Phrase search (exact match)
    results = indexer.search_episodic('"Olive Garden"')
    assert results == ["evt_001"]

    # Word search (both match)
    results = indexer.search_episodic("Olive")
    assert set(results) == {"evt_001", "evt_002"}

    conn.close()


def test_fts5_indexer_error_handling(temp_db_with_fts5: Path) -> None:
    """Test: Invalid table name raises ValueError."""
    conn = sqlite3.connect(str(temp_db_with_fts5))
    conn.row_factory = sqlite3.Row
    indexer = FTS5Indexer(conn)

    with pytest.raises(ValueError, match="Invalid FTS5 table"):
        indexer.remove_from_index("invalid_table", "evt_999")

    conn.close()


def test_fts5_search_with_tenant_space_filter(temp_db_with_fts5: Path) -> None:
    """Test: FTS5 search filtered by tenant_id and space_id."""
    conn = sqlite3.connect(str(temp_db_with_fts5))
    conn.row_factory = sqlite3.Row
    indexer = FTS5Indexer(conn)

    # Index memories in different spaces
    indexer.index_episodic(
        event_id="evt_tenant1",
        text="Secret data for tenant 1",
        summary="Private",
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T10:00:00Z",
    )
    indexer.index_episodic(
        event_id="evt_tenant2",
        text="Secret data for tenant 2",
        summary="Private",
        tenant_id="tenant_002",
        space_id="space_002",
        commit_ts="2025-11-10T11:00:00Z",
    )
    conn.commit()

    # Search without filter (returns both)
    results = indexer.search_episodic("Secret data")
    assert set(results) == {"evt_tenant1", "evt_tenant2"}

    # Search with tenant filter (returns only tenant 1)
    results = indexer.search_episodic("Secret data", tenant_id="tenant_001")
    assert results == ["evt_tenant1"]

    # Search with space filter (returns only space 2)
    results = indexer.search_episodic("Secret data", space_id="space_002")
    assert results == ["evt_tenant2"]

    conn.close()


def test_fts5_performance_target() -> None:
    """Test: Verify <10ms P95 for keyword search across 100K+ memories.

    NOTE: This is a placeholder test. Actual performance testing requires:
    - Populating 100K+ memories
    - Running multiple search queries
    - Measuring P95 latency

    This will be implemented in performance test suite.
    """
    # Performance test placeholder
    # See: tests/k0/performance/test_fts5_search_latency.py
    pass
