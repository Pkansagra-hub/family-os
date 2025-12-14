"""
Integration tests for Retention Policy Enforcer

Tests data retention policies, archival, and hard deletes using Migration 0004 tables.

Run with: python -m pytest tests/k0/integration/test_retention_policies.py -v
"""

import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from k0.policy.retention_enforcer import RetentionEnforcer


@pytest.fixture
def temp_db_with_retention():
    """Create temporary database with Migration 0004 retention schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_retention.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create st_retention_policy table (from Migration 0004)
        conn.execute(
            """
            CREATE TABLE st_retention_policy (
              policy_id TEXT PRIMARY KEY,
              resource_type TEXT NOT NULL,
              retention_days INTEGER NOT NULL,
              archive_enabled BOOLEAN NOT NULL,
              privacy_band_filter TEXT,
              tenant_id_filter TEXT,
              enabled BOOLEAN DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT
            )
        """
        )

        # Create st_archive_manifest table
        conn.execute(
            """
            CREATE TABLE st_archive_manifest (
              manifest_id TEXT PRIMARY KEY,
              resource_type TEXT NOT NULL,
              resource_id TEXT NOT NULL,
              archive_location TEXT NOT NULL,
              checksum TEXT,
              compressed_size_bytes INTEGER,
              archived_at TEXT NOT NULL,
              delete_after TEXT,
              tenant_id TEXT
            )
        """
        )

        # Create sample st_epi table (memory table)
        conn.execute(
            """
            CREATE TABLE st_epi (
              event_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              tenant_id TEXT,
              privacy_band TEXT,
              content TEXT
            )
        """
        )

        conn.commit()

        yield conn, str(db_path)
        conn.close()


def test_apply_policies_delete(temp_db_with_retention):
    """Test hard delete policy (archive_enabled=false)."""
    conn, _ = temp_db_with_retention
    enforcer = RetentionEnforcer()

    # Create retention policy: delete after 7 days
    policy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO st_retention_policy (
            policy_id, resource_type, retention_days,
            archive_enabled, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (policy_id, "st_epi", 7, False, True, datetime.now(timezone.utc).isoformat()),
    )

    # Create old memory (10 days ago)
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, content)
        VALUES (?, ?, ?, ?)
        """,
        ("evt_old", old_date, "tenant_001", "Old event"),
    )

    # Create recent memory (2 days ago)
    recent_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, content)
        VALUES (?, ?, ?, ?)
        """,
        ("evt_recent", recent_date, "tenant_001", "Recent event"),
    )

    conn.commit()

    # Apply policies
    stats = enforcer.apply_policies(connection=conn)

    # Verify old memory deleted
    result = conn.execute("SELECT COUNT(*) FROM st_epi WHERE event_id = ?", ("evt_old",)).fetchone()
    assert result[0] == 0, "Old memory should be deleted"

    # Verify recent memory kept
    result = conn.execute(
        "SELECT COUNT(*) FROM st_epi WHERE event_id = ?", ("evt_recent",)
    ).fetchone()
    assert result[0] == 1, "Recent memory should be kept"

    assert stats["deleted"] > 0


def test_apply_policies_archive(temp_db_with_retention):
    """Test archive policy (archive_enabled=true)."""
    conn, _ = temp_db_with_retention

    # Mock archive callback
    archived_items = []

    def mock_archive(resource_type, resource_id, data):
        location = f"s3://archives/{resource_type}/{resource_id}.zst"
        archived_items.append((resource_type, resource_id, location))
        return location

    enforcer = RetentionEnforcer(archive_callback=mock_archive)

    # Create retention policy: archive after 30 days
    policy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO st_retention_policy (
            policy_id, resource_type, retention_days,
            archive_enabled, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (policy_id, "st_epi", 30, True, True, datetime.now(timezone.utc).isoformat()),
    )

    # Create old memory (45 days ago)
    old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, content)
        VALUES (?, ?, ?, ?)
        """,
        ("evt_archive", old_date, "tenant_001", "Archived event"),
    )

    conn.commit()

    # Apply policies
    stats = enforcer.apply_policies(connection=conn)

    # Verify memory archived
    assert len(archived_items) > 0
    assert archived_items[0][0] == "st_epi"
    assert archived_items[0][1] == "evt_archive"

    # Verify archive manifest created
    manifest_count = conn.execute(
        "SELECT COUNT(*) FROM st_archive_manifest WHERE resource_id = ?",
        ("evt_archive",),
    ).fetchone()[0]
    assert manifest_count > 0

    assert stats["archived"] > 0


def test_get_expired_resources(temp_db_with_retention):
    """Test retrieval of expired resources for a policy."""
    conn, _ = temp_db_with_retention
    enforcer = RetentionEnforcer()

    # Create retention policy
    policy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO st_retention_policy (
            policy_id, resource_type, retention_days,
            archive_enabled, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (policy_id, "st_epi", 14, False, True, datetime.now(timezone.utc).isoformat()),
    )

    # Create 3 expired memories and 2 recent ones
    for i in range(5):
        days_ago = 20 if i < 3 else 5  # First 3 are expired (>14 days)
        created_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        conn.execute(
            """
            INSERT INTO st_epi (event_id, created_at, tenant_id, content)
            VALUES (?, ?, ?, ?)
            """,
            (f"evt_{i}", created_at, "tenant_001", f"Event {i}"),
        )

    conn.commit()

    # Get expired resources
    expired = enforcer.get_expired_resources(policy_id, connection=conn)

    # Should find 3 expired resources
    assert len(expired) == 3
    assert all(res["age_days"] > 14 for res in expired)


def test_privacy_band_filter(temp_db_with_retention):
    """Test retention policy with privacy_band filter."""
    conn, _ = temp_db_with_retention
    enforcer = RetentionEnforcer()

    # Create policy: delete GREEN privacy band after 30 days
    policy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO st_retention_policy (
            policy_id, resource_type, retention_days,
            archive_enabled, privacy_band_filter, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            "st_epi",
            30,
            False,
            "GREEN",
            True,
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    # Create old GREEN memory (should be deleted)
    old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, privacy_band, content)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("evt_green_old", old_date, "tenant_001", "GREEN", "Green event"),
    )

    # Create old RED memory (should be kept - not GREEN)
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, privacy_band, content)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("evt_red_old", old_date, "tenant_001", "RED", "Red event"),
    )

    conn.commit()

    # Apply policies
    enforcer.apply_policies(connection=conn)

    # Verify GREEN deleted, RED kept
    green_count = conn.execute(
        "SELECT COUNT(*) FROM st_epi WHERE event_id = ?", ("evt_green_old",)
    ).fetchone()[0]
    red_count = conn.execute(
        "SELECT COUNT(*) FROM st_epi WHERE event_id = ?", ("evt_red_old",)
    ).fetchone()[0]

    assert green_count == 0, "GREEN memory should be deleted"
    assert red_count == 1, "RED memory should be kept"


def test_dry_run_mode(temp_db_with_retention):
    """Test dry run mode (stats only, no changes)."""
    conn, _ = temp_db_with_retention
    enforcer = RetentionEnforcer()

    # Create policy
    policy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO st_retention_policy (
            policy_id, resource_type, retention_days,
            archive_enabled, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (policy_id, "st_epi", 7, False, True, datetime.now(timezone.utc).isoformat()),
    )

    # Create old memory
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, content)
        VALUES (?, ?, ?, ?)
        """,
        ("evt_test", old_date, "tenant_001", "Test event"),
    )

    conn.commit()

    # Apply policies in dry run mode
    stats = enforcer.apply_policies(dry_run=True, connection=conn)

    # Verify memory NOT deleted (dry run)
    result = conn.execute(
        "SELECT COUNT(*) FROM st_epi WHERE event_id = ?", ("evt_test",)
    ).fetchone()
    assert result[0] == 1, "Memory should NOT be deleted in dry run"

    # Stats should still be 0 in dry run
    assert stats["deleted"] == 0


def test_disabled_policy_ignored(temp_db_with_retention):
    """Test disabled policies are not applied."""
    conn, _ = temp_db_with_retention
    enforcer = RetentionEnforcer()

    # Create DISABLED policy
    policy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO st_retention_policy (
            policy_id, resource_type, retention_days,
            archive_enabled, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (policy_id, "st_epi", 1, False, False, datetime.now(timezone.utc).isoformat()),
    )

    # Create old memory
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn.execute(
        """
        INSERT INTO st_epi (event_id, created_at, tenant_id, content)
        VALUES (?, ?, ?, ?)
        """,
        ("evt_test", old_date, "tenant_001", "Test event"),
    )

    conn.commit()

    # Apply policies
    enforcer.apply_policies(connection=conn)

    # Verify memory NOT deleted (policy disabled)
    result = conn.execute(
        "SELECT COUNT(*) FROM st_epi WHERE event_id = ?", ("evt_test",)
    ).fetchone()
    assert result[0] == 1, "Memory should NOT be deleted (policy disabled)"
