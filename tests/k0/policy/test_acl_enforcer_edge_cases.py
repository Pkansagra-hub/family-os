"""Edge case tests for k0.policy.acl_enforcer module.

This test suite targets the ACL enforcer with 0% coverage, implementing
comprehensive testing for access control list enforcement including:
- Permission checking with various scenarios
- Permission granting and revocation
- ACL listing with filters
- Error handling for missing tables and database issues
- Edge cases with expired permissions, revoked permissions, etc.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from k0.policy.acl_enforcer import ACLEnforcer, ACLEnforcerError, ACLEntry


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database with st_acl table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create st_acl table (from Migration 0004)
    conn.execute(
        """
        CREATE TABLE st_acl (
            acl_id TEXT PRIMARY KEY,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            principal_type TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            permission TEXT NOT NULL,
            privacy_band TEXT,
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            expires_at TEXT,
            revoked_at TEXT
        )
    """
    )

    # Create indexes for performance
    conn.execute("CREATE INDEX idx_acl_resource ON st_acl(resource_type, resource_id)")
    conn.execute("CREATE INDEX idx_acl_principal ON st_acl(principal_type, principal_id)")
    conn.execute("CREATE INDEX idx_acl_permission ON st_acl(permission)")
    conn.execute("CREATE INDEX idx_acl_revoked ON st_acl(revoked_at)")
    conn.execute("CREATE INDEX idx_acl_expires ON st_acl(expires_at)")

    yield conn
    conn.close()


@pytest.fixture
def sample_acl_entries():
    """Sample ACL entries for testing."""
    now = datetime.now(timezone.utc).isoformat()
    future = datetime.now(timezone.utc).replace(year=2030).isoformat()
    past = datetime.now(timezone.utc).replace(year=2020).isoformat()

    return [
        {
            "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "resource_type": "st_epi",
            "resource_id": "evt_123",
            "principal_type": "user",
            "principal_id": "usr_alice",
            "permission": "read",
            "privacy_band": "GREEN",
            "granted_at": now,
            "granted_by": "usr_admin",
            "expires_at": None,
            "revoked_at": None,
        },
        {
            "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FBW",
            "resource_type": "st_epi",
            "resource_id": "evt_123",
            "principal_type": "user",
            "principal_id": "usr_bob",
            "permission": "write",
            "privacy_band": "AMBER",
            "granted_at": now,
            "granted_by": "usr_admin",
            "expires_at": future,
            "revoked_at": None,
        },
        {
            "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FCX",
            "resource_type": "st_sem",
            "resource_id": "fact_456",
            "principal_type": "device",
            "principal_id": "dev_mobile",
            "permission": "read",
            "privacy_band": None,
            "granted_at": past,
            "granted_by": "usr_admin",
            "expires_at": None,
            "revoked_at": past,  # Revoked
        },
        {
            "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FDY",
            "resource_type": "st_epi",
            "resource_id": "evt_789",
            "principal_type": "service",
            "principal_id": "svc_api",
            "permission": "delete",
            "privacy_band": "RED",
            "granted_at": past,
            "granted_by": "usr_admin",
            "expires_at": past,  # Expired
            "revoked_at": None,
        },
    ]


class TestACLEnforcerCheckPermission:
    """Test permission checking functionality."""

    def test_check_permission_granted_active(self, in_memory_db, sample_acl_entries):
        """Test checking permission that exists and is active."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        result = enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=in_memory_db
        )
        assert result is True

    def test_check_permission_denied_no_entry(self, in_memory_db):
        """Test checking permission that doesn't exist."""
        enforcer = ACLEnforcer()
        result = enforcer.check_permission(
            "st_epi", "evt_nonexistent", "usr_alice", "read", connection=in_memory_db
        )
        assert result is False

    def test_check_permission_denied_revoked(self, in_memory_db, sample_acl_entries):
        """Test checking permission that was revoked."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        # Try to check the revoked permission (fact_456 for dev_mobile)
        result = enforcer.check_permission(
            "st_sem", "fact_456", "dev_mobile", "read", connection=in_memory_db
        )
        assert result is False

    def test_check_permission_denied_expired(self, in_memory_db, sample_acl_entries):
        """Test checking permission that has expired."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        # Try to check the expired permission (evt_789 for svc_api)
        result = enforcer.check_permission(
            "st_epi", "evt_789", "svc_api", "delete", connection=in_memory_db
        )
        assert result is False

    def test_check_permission_with_principal_type(self, in_memory_db, sample_acl_entries):
        """Test checking permission with specific principal type."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        result = enforcer.check_permission(
            "st_sem",
            "fact_456",
            "dev_mobile",
            "read",
            principal_type="device",
            connection=in_memory_db,
        )
        assert result is False  # Revoked, so still false

    def test_check_permission_table_missing_fallback(self):
        """Test permission check when st_acl table doesn't exist (fallback to permissive)."""
        # Create connection to empty database (no st_acl table)
        conn = sqlite3.connect(":memory:")

        enforcer = ACLEnforcer()
        result = enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=conn
        )
        assert result is True  # Fallback permissive policy

        conn.close()

    def test_check_permission_database_error(self):
        """Test permission check with database error."""
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)
        mock_conn.execute.side_effect = sqlite3.OperationalError("Disk I/O error")

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="ACL check failed"):
            enforcer.check_permission(
                "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
            )


class TestACLEnforcerGrantPermission:
    """Test permission granting functionality."""

    def test_grant_permission_success(self, in_memory_db):
        """Test successfully granting a permission."""
        enforcer = ACLEnforcer()
        enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_admin",
            privacy_band="GREEN",
            connection=in_memory_db,
        )

        # Verify the permission was inserted
        row = in_memory_db.execute(
            "SELECT * FROM st_acl WHERE acl_id = ?", ("01ARZ3NDEKTSV4RRFFQ69G5FAV",)
        ).fetchone()

        assert row is not None
        assert row["resource_type"] == "st_epi"
        assert row["resource_id"] == "evt_123"
        assert row["principal_type"] == "user"
        assert row["principal_id"] == "usr_alice"
        assert row["permission"] == "read"
        assert row["privacy_band"] == "GREEN"
        assert row["granted_by"] == "usr_admin"
        assert row["revoked_at"] is None

    def test_grant_permission_with_expires_at(self, in_memory_db):
        """Test granting permission with expiration date."""
        expires_at = "2030-01-01T00:00:00Z"

        enforcer = ACLEnforcer()
        enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FBW",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="write",
            granted_by="usr_admin",
            expires_at=expires_at,
            connection=in_memory_db,
        )

        row = in_memory_db.execute(
            "SELECT expires_at FROM st_acl WHERE acl_id = ?", ("01ARZ3NDEKTSV4RRFFQ69G5FBW",)
        ).fetchone()

        assert row["expires_at"] == expires_at

    def test_grant_permission_table_missing_error(self):
        """Test granting permission when st_acl table doesn't exist."""
        conn = sqlite3.connect(":memory:")  # No st_acl table

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="st_acl table not found"):
            enforcer.grant_permission(
                acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                resource_type="st_epi",
                resource_id="evt_123",
                principal_type="user",
                principal_id="usr_alice",
                permission="read",
                granted_by="usr_admin",
                connection=conn,
            )

        conn.close()

    def test_grant_permission_uses_connection_pool(self, in_memory_db):
        """Test granting permission without explicit connection (uses connection pool)."""
        from unittest.mock import MagicMock, patch

        # Mock the connection and its commit method
        mock_conn = MagicMock()
        mock_conn.execute = in_memory_db.execute
        mock_conn.commit = MagicMock()

        # Create a mock context manager that yields our mocked connection
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_conn)
        mock_context.__exit__ = MagicMock(return_value=None)

        def mock_connection_scope():
            return mock_context

        with patch("k0.policy.acl_enforcer.connection_scope", mock_connection_scope):
            enforcer = ACLEnforcer()
            enforcer.grant_permission(
                acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                resource_type="st_epi",
                resource_id="evt_123",
                principal_type="user",
                principal_id="usr_alice",
                permission="read",
                granted_by="usr_admin",
                # No connection provided - should use connection pool and commit
            )

            # Verify commit was called (since connection=None triggers commit)
            mock_conn.commit.assert_called_once()

            # Verify the data was inserted
            row = in_memory_db.execute(
                "SELECT * FROM st_acl WHERE acl_id = ?", ("01ARZ3NDEKTSV4RRFFQ69G5FAV",)
            ).fetchone()
            assert row is not None


class TestACLEnforcerRevokePermission:
    """Test permission revocation functionality."""

    def test_revoke_permission_success(self, in_memory_db, sample_acl_entries):
        """Test successfully revoking a permission."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV", connection=in_memory_db)

        # Verify the permission was revoked
        row = in_memory_db.execute(
            "SELECT revoked_at FROM st_acl WHERE acl_id = ?", ("01ARZ3NDEKTSV4RRFFQ69G5FAV",)
        ).fetchone()

        assert row is not None
        assert row["revoked_at"] is not None

    def test_revoke_permission_nonexistent_acl(self, in_memory_db):
        """Test revoking a non-existent ACL entry (should not error)."""
        enforcer = ACLEnforcer()
        # This should not raise an error even if ACL doesn't exist
        enforcer.revoke_permission("nonexistent_acl_id", connection=in_memory_db)

    def test_revoke_permission_table_missing_error(self):
        """Test revoking permission when st_acl table doesn't exist."""
        conn = sqlite3.connect(":memory:")  # No st_acl table

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="st_acl table not found"):
            enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV", connection=conn)

        conn.close()

    def test_revoke_permission_uses_connection_pool(self, in_memory_db, sample_acl_entries):
        """Test revoking permission without explicit connection (uses connection pool)."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        from unittest.mock import MagicMock, patch

        # Mock the connection and its commit method
        mock_conn = MagicMock()
        mock_conn.execute = in_memory_db.execute
        mock_conn.commit = MagicMock()

        # Create a mock context manager that yields our mocked connection
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_conn)
        mock_context.__exit__ = MagicMock(return_value=None)

        def mock_connection_scope():
            return mock_context

        with patch("k0.policy.acl_enforcer.connection_scope", mock_connection_scope):
            enforcer = ACLEnforcer()
            enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV")  # No connection provided

            # Verify commit was called (since connection=None triggers commit)
            mock_conn.commit.assert_called_once()

            # Verify the permission was revoked
            row = in_memory_db.execute(
                "SELECT revoked_at FROM st_acl WHERE acl_id = ?", ("01ARZ3NDEKTSV4RRFFQ69G5FAV",)
            ).fetchone()
            assert row is not None
            assert row["revoked_at"] is not None


class TestACLEnforcerListPermissions:
    """Test permission listing functionality."""

    def test_list_permissions_all(self, in_memory_db, sample_acl_entries):
        """Test listing all permissions."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        entries = enforcer.list_permissions(connection=in_memory_db)

        # Should return 3 entries (excluding the revoked one)
        assert len(entries) == 3
        assert all(isinstance(entry, ACLEntry) for entry in entries)

        # Check that revoked entry is not included
        acl_ids = {entry.acl_id for entry in entries}
        assert "01ARZ3NDEKTSV4RRFFQ69G5FCX" not in acl_ids  # Revoked entry

    def test_list_permissions_with_filters(self, in_memory_db, sample_acl_entries):
        """Test listing permissions with various filters."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()

        # Filter by resource
        entries = enforcer.list_permissions(
            resource_type="st_epi", resource_id="evt_123", connection=in_memory_db
        )
        assert len(entries) == 2  # Two entries for evt_123
        assert all(entry.resource_id == "evt_123" for entry in entries)

        # Filter by principal
        entries = enforcer.list_permissions(principal_id="usr_alice", connection=in_memory_db)
        assert len(entries) == 1
        assert entries[0].principal_id == "usr_alice"

    def test_list_permissions_include_revoked(self, in_memory_db, sample_acl_entries):
        """Test listing permissions including revoked ones."""
        # Insert sample data
        in_memory_db.executemany(
            """
            INSERT INTO st_acl VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [tuple(entry.values()) for entry in sample_acl_entries],
        )
        in_memory_db.commit()

        enforcer = ACLEnforcer()
        entries = enforcer.list_permissions(include_revoked=True, connection=in_memory_db)

        # Should return all 4 entries including revoked
        assert len(entries) == 4

        # Check that revoked entry is included
        acl_ids = {entry.acl_id for entry in entries}
        assert "01ARZ3NDEKTSV4RRFFQ69G5FCX" in acl_ids  # Revoked entry

    def test_list_permissions_empty_database(self, in_memory_db):
        """Test listing permissions on empty database."""
        enforcer = ACLEnforcer()
        entries = enforcer.list_permissions(connection=in_memory_db)
        assert entries == []

    def test_list_permissions_table_missing(self):
        """Test listing permissions when st_acl table doesn't exist."""
        conn = sqlite3.connect(":memory:")  # No st_acl table

        enforcer = ACLEnforcer()
        entries = enforcer.list_permissions(connection=conn)
        assert entries == []  # Should return empty list

        conn.close()

    def test_list_permissions_database_error(self):
        """Test listing permissions with database error."""
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)
        mock_conn.execute.side_effect = sqlite3.OperationalError("Disk I/O error")

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="Failed to list permissions"):
            enforcer.list_permissions(connection=mock_conn)


class TestACLEnforcerIntegration:
    """Integration tests combining multiple operations."""

    def test_grant_check_revoke_workflow(self, in_memory_db):
        """Test complete workflow: grant -> check -> revoke -> check."""
        enforcer = ACLEnforcer()

        # Grant permission
        enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_admin",
            connection=in_memory_db,
        )

        # Check permission (should be granted)
        assert (
            enforcer.check_permission(
                "st_epi", "evt_123", "usr_alice", "read", connection=in_memory_db
            )
            is True
        )

        # Revoke permission
        enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV", connection=in_memory_db)

        # Check permission again (should be denied)
        assert (
            enforcer.check_permission(
                "st_epi", "evt_123", "usr_alice", "read", connection=in_memory_db
            )
            is False
        )

    def test_multiple_permissions_same_resource(self, in_memory_db):
        """Test multiple permissions on the same resource for different principals."""
        enforcer = ACLEnforcer()

        # Grant read to Alice
        enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_admin",
            connection=in_memory_db,
        )

        # Grant write to Bob
        enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FBW",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_bob",
            permission="write",
            granted_by="usr_admin",
            connection=in_memory_db,
        )

        # Check permissions
        assert (
            enforcer.check_permission(
                "st_epi", "evt_123", "usr_alice", "read", connection=in_memory_db
            )
            is True
        )
        assert (
            enforcer.check_permission(
                "st_epi", "evt_123", "usr_bob", "write", connection=in_memory_db
            )
            is True
        )
        assert (
            enforcer.check_permission(
                "st_epi", "evt_123", "usr_alice", "write", connection=in_memory_db
            )
            is False
        )  # Alice doesn't have write

        # List permissions for the resource
        entries = enforcer.list_permissions(
            resource_type="st_epi", resource_id="evt_123", connection=in_memory_db
        )
        assert len(entries) == 2
        permissions = {entry.principal_id: entry.permission for entry in entries}
        assert permissions == {"usr_alice": "read", "usr_bob": "write"}


class TestACLEnforcerACLEntry:
    """Test ACLEntry dataclass."""

    def test_acl_entry_creation(self):
        """Test creating ACLEntry instances."""
        entry = ACLEntry(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            privacy_band="GREEN",
            granted_at="2023-01-01T00:00:00Z",
            granted_by="usr_admin",
            expires_at="2024-01-01T00:00:00Z",
            revoked_at=None,
        )

        assert entry.acl_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert entry.resource_type == "st_epi"
        assert entry.principal_id == "usr_alice"
        assert entry.permission == "read"
        assert entry.privacy_band == "GREEN"
        assert entry.revoked_at is None

    def test_acl_entry_immutable(self):
        """Test that ACLEntry is immutable (frozen dataclass)."""
        entry = ACLEntry(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
        )

        with pytest.raises(AttributeError):
            entry.acl_id = "new_id"
