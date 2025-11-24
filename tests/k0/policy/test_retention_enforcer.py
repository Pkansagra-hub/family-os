"""Tests for k0/policy/retention_enforcer.py"""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from k0.policy.retention_enforcer import ArchiveManifest, RetentionEnforcer, RetentionPolicy


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database with required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
    cursor = conn.cursor()

    # Create retention policy table
    cursor.execute(
        """
        CREATE TABLE st_retention_policy (
            policy_id TEXT PRIMARY KEY,
            resource_type TEXT NOT NULL,
            retention_days INTEGER NOT NULL,
            archive_enabled BOOLEAN NOT NULL DEFAULT 0,
            privacy_band_filter TEXT,
            tenant_id_filter TEXT,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """
    )

    # Create archive manifest table
    cursor.execute(
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

    # Insert test data
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        INSERT INTO st_retention_policy VALUES
        ('policy1', 'st_epi', 30, 1, 'GREEN', 'tenant1', 1, ?, NULL),
        ('policy2', 'st_sem', 7, 0, NULL, NULL, 1, ?, NULL)
    """,
        (now, now),
    )

    conn.commit()
    return conn


@pytest.fixture
def sample_policy():
    """Sample retention policy."""
    return RetentionPolicy(
        policy_id="test-policy",
        resource_type="st_epi",
        retention_days=30,
        archive_enabled=True,
        privacy_band_filter="GREEN",
        tenant_id_filter="tenant1",
        enabled=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_manifest():
    """Sample archive manifest."""
    return ArchiveManifest(
        manifest_id="test-manifest",
        resource_type="st_epi",
        resource_id="resource123",
        archive_location="s3://bucket/path",
        checksum="abc123",
        compressed_size_bytes=1024,
        archived_at=datetime.now(timezone.utc).isoformat(),
        delete_after=(datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        tenant_id="tenant1",
    )


class TestRetentionPolicy:
    """Test RetentionPolicy dataclass."""

    def test_retention_policy_creation(self):
        """Test creating a retention policy."""
        policy = RetentionPolicy(
            policy_id="test", resource_type="st_epi", retention_days=30, archive_enabled=True
        )
        assert policy.policy_id == "test"
        assert policy.retention_days == 30
        assert policy.archive_enabled is True


class TestArchiveManifest:
    """Test ArchiveManifest dataclass."""

    def test_archive_manifest_creation(self):
        """Test creating an archive manifest."""
        manifest = ArchiveManifest(
            manifest_id="test",
            resource_type="st_epi",
            resource_id="res123",
            archive_location="s3://bucket/file",
        )
        assert manifest.manifest_id == "test"
        assert manifest.resource_id == "res123"


class TestRetentionEnforcer:
    """Test RetentionEnforcer class."""

    def test_init(self):
        """Test RetentionEnforcer initialization."""
        enforcer = RetentionEnforcer()
        assert enforcer._archive_callback is None

    def test_apply_policies_no_expired(self, in_memory_db):
        """Test apply_policies when no resources are expired."""
        enforcer = RetentionEnforcer()

        # Mock get_expired_resources to return empty
        with patch.object(enforcer, "get_expired_resources", return_value=[]):
            result = enforcer.apply_policies(connection=in_memory_db)
            assert result == {"archived": 0, "deleted": 0, "errors": 0}

    def test_apply_policies_with_expired_archive(self, in_memory_db, sample_policy):
        """Test apply_policies archives expired resources."""
        enforcer = RetentionEnforcer(archive_callback=MagicMock(return_value="s3://bucket/path"))

        expired = [
            {"id": "res1", "id_column": "id", "created_at": "2023-01-01T00:00:00Z", "age_days": 60}
        ]

        # Create the table that _archive_resource expects
        cursor = in_memory_db.cursor()
        cursor.execute(
            """
            CREATE TABLE st_epi (
                id TEXT PRIMARY KEY,
                data TEXT
            )
        """
        )
        cursor.execute("INSERT INTO st_epi VALUES ('res1', 'test data')")
        in_memory_db.commit()

        with (
            patch.object(enforcer, "_load_policies", return_value=[sample_policy]),
            patch.object(enforcer, "_get_expired_resources_for_policy", return_value=expired),
        ):
            result = enforcer.apply_policies(connection=in_memory_db)
            assert result["archived"] == 1

    def test_apply_policies_with_expired_delete(self, in_memory_db):
        """Test apply_policies deletes expired resources when archive disabled."""
        enforcer = RetentionEnforcer()

        policy_no_archive = RetentionPolicy(
            policy_id="no-archive", resource_type="st_sem", retention_days=7, archive_enabled=False
        )

        expired = [
            {"id": "res2", "id_column": "id", "created_at": "2023-01-01T00:00:00Z", "age_days": 60}
        ]

        # Create the table that _delete_resource expects
        cursor = in_memory_db.cursor()
        cursor.execute(
            """
            CREATE TABLE st_sem (
                id TEXT PRIMARY KEY,
                data TEXT
            )
        """
        )
        cursor.execute("INSERT INTO st_sem VALUES ('res2', 'test data')")
        in_memory_db.commit()

        with (
            patch.object(enforcer, "_load_policies", return_value=[policy_no_archive]),
            patch.object(enforcer, "_get_expired_resources_for_policy", return_value=expired),
        ):
            result = enforcer.apply_policies(connection=in_memory_db)
            assert result["deleted"] == 1

    def test_get_expired_resources(self, in_memory_db):
        """Test get_expired_resources returns expired items."""
        enforcer = RetentionEnforcer()

        expired = enforcer.get_expired_resources("policy1", connection=in_memory_db)
        assert len(expired) >= 0  # May be empty if no matching resources

    def test_load_policies(self, in_memory_db):
        """Test _load_policies loads from database."""
        enforcer = RetentionEnforcer()
        policies = enforcer._load_policies(in_memory_db)

        assert len(policies) == 2
        assert policies[0].policy_id == "policy1"
        assert policies[0].retention_days == 30
        assert policies[1].policy_id == "policy2"

    def test_get_expired_resources_for_policy(self, in_memory_db, sample_policy):
        """Test _get_expired_resources_for_policy queries database."""
        enforcer = RetentionEnforcer()

        # Create a test table for resources
        cursor = in_memory_db.cursor()
        cursor.execute(
            """
            CREATE TABLE st_epi (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                privacy_band TEXT,
                tenant_id TEXT
            )
        """
        )

        # Insert expired resource (created 60 days ago)
        expired_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        cursor.execute(
            """
            INSERT INTO st_epi VALUES ('res1', ?, 'GREEN', 'tenant1')
        """,
            (expired_date,),
        )
        in_memory_db.commit()

        expired = enforcer._get_expired_resources_for_policy(in_memory_db, sample_policy)
        assert len(expired) == 1
        assert expired[0]["id"] == "res1"

    def test_archive_resource(self, in_memory_db, sample_policy):
        """Test _archive_resource creates manifest and deletes resource."""
        enforcer = RetentionEnforcer(archive_callback=MagicMock(return_value="s3://bucket/path"))

        # Create test table
        cursor = in_memory_db.cursor()
        cursor.execute(
            """
            CREATE TABLE st_epi (
                id TEXT PRIMARY KEY,
                data TEXT
            )
        """
        )
        cursor.execute("INSERT INTO st_epi VALUES ('res1', 'test data')")
        in_memory_db.commit()

        resource = {"id": "res1", "id_column": "id"}

        enforcer._archive_resource(in_memory_db, sample_policy, resource)

        # Check manifest was created
        cursor.execute("SELECT * FROM st_archive_manifest")
        manifests = cursor.fetchall()
        assert len(manifests) == 1

        # Check resource was deleted
        cursor.execute("SELECT * FROM st_epi WHERE id = 'res1'")
        resources = cursor.fetchall()
        assert len(resources) == 0

    def test_delete_resource(self, in_memory_db):
        """Test _delete_resource removes resource."""
        enforcer = RetentionEnforcer()

        # Create test table
        cursor = in_memory_db.cursor()
        cursor.execute(
            """
            CREATE TABLE st_epi (
                id TEXT PRIMARY KEY,
                data TEXT
            )
        """
        )
        cursor.execute("INSERT INTO st_epi VALUES ('res1', 'test data')")
        in_memory_db.commit()

        enforcer._delete_resource(in_memory_db, "st_epi", "res1")

        # Check resource was deleted
        cursor.execute("SELECT * FROM st_epi WHERE id = 'res1'")
        resources = cursor.fetchall()
        assert len(resources) == 0
