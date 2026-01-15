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

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from k0.policy.acl_enforcer import ACLEnforcer, ACLEnforcerError, ACLEntry


@pytest.fixture
def mock_conn():
    """Mock asyncpg connection for testing."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return conn


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


@pytest.mark.asyncio
class TestACLEnforcerCheckPermission:
    """Test permission checking functionality."""

    async def test_check_permission_granted_active(self, mock_conn):
        """Test checking permission that exists and is active."""
        # Mock database returning an active permission row
        mock_conn.fetchrow.return_value = {
            "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "resource_type": "st_epi",
            "resource_id": "evt_123",
            "principal_id": "usr_alice",
            "permission": "read",
            "revoked_at": None,
            "expires_at": None,
        }

        enforcer = ACLEnforcer()
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
        )
        assert result is True

    async def test_check_permission_denied_no_entry(self, mock_conn):
        """Test checking permission that doesn't exist."""
        mock_conn.fetchrow.return_value = None

        enforcer = ACLEnforcer()
        result = await enforcer.check_permission(
            "st_epi", "evt_nonexistent", "usr_alice", "read", connection=mock_conn
        )
        assert result is False

    async def test_check_permission_denied_revoked(self, mock_conn):
        """Test checking permission that was revoked."""
        # Mock database returning a revoked entry (check_permission filters these)
        mock_conn.fetchrow.return_value = None  # Revoked entries are excluded by query

        enforcer = ACLEnforcer()
        result = await enforcer.check_permission(
            "st_sem", "fact_456", "dev_mobile", "read", connection=mock_conn
        )
        assert result is False

    async def test_check_permission_denied_expired(self, mock_conn):
        """Test checking permission that has expired."""
        # Mock database returning None (expired entries filtered by query)
        mock_conn.fetchrow.return_value = None

        enforcer = ACLEnforcer()
        result = await enforcer.check_permission(
            "st_epi", "evt_789", "svc_api", "delete", connection=mock_conn
        )
        assert result is False

    async def test_check_permission_with_principal_type(self, mock_conn):
        """Test checking permission with specific principal type."""
        # Mock returning None (revoked entry not found)
        mock_conn.fetchrow.return_value = None

        enforcer = ACLEnforcer()
        result = await enforcer.check_permission(
            "st_sem",
            "fact_456",
            "dev_mobile",
            "read",
            principal_type="device",
            connection=mock_conn,
        )
        assert result is False  # Revoked, so still false

    async def test_check_permission_table_missing_fallback(self, mock_conn):
        """Test permission check when st_acl table doesn't exist (fallback to permissive)."""
        # Mock asyncpg raising error with "does not exist" in message for fallback
        mock_conn.fetchrow.side_effect = Exception('relation "st_acl" does not exist')

        enforcer = ACLEnforcer()
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
        )
        assert result is True  # Fallback permissive policy

    async def test_check_permission_database_error(self, mock_conn):
        """Test permission check with database error."""
        import asyncpg

        mock_conn.fetchrow.side_effect = asyncpg.PostgresError("Disk I/O error")

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="ACL check failed"):
            await enforcer.check_permission(
                "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
            )


@pytest.mark.asyncio
class TestACLEnforcerGrantPermission:
    """Test permission granting functionality."""

    async def test_grant_permission_success(self, mock_conn):
        """Test successfully granting a permission."""
        enforcer = ACLEnforcer()
        await enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_admin",
            privacy_band="GREEN",
            connection=mock_conn,
        )

        # Verify execute was called for the insert
        mock_conn.execute.assert_called()

    async def test_grant_permission_with_expires_at(self, mock_conn):
        """Test granting permission with expiration date."""
        expires_at = "2030-01-01T00:00:00Z"

        enforcer = ACLEnforcer()
        await enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FBW",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="write",
            granted_by="usr_admin",
            expires_at=expires_at,
            connection=mock_conn,
        )

        # Verify execute was called
        mock_conn.execute.assert_called()

    async def test_grant_permission_table_missing_error(self, mock_conn):
        """Test granting permission when st_acl table doesn't exist."""
        import asyncpg

        mock_conn.execute.side_effect = asyncpg.UndefinedTableError("st_acl")

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="Failed to grant permission"):
            await enforcer.grant_permission(
                acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                resource_type="st_epi",
                resource_id="evt_123",
                principal_type="user",
                principal_id="usr_alice",
                permission="read",
                granted_by="usr_admin",
                connection=mock_conn,
            )

    async def test_grant_permission_uses_connection_pool(self):
        """Test granting permission without explicit connection (uses connection pool)."""
        # Mock the async connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        # Create async context manager mock
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("k0.policy.acl_enforcer.connection_scope", return_value=mock_cm):
            enforcer = ACLEnforcer()
            await enforcer.grant_permission(
                acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                resource_type="st_epi",
                resource_id="evt_123",
                principal_type="user",
                principal_id="usr_alice",
                permission="read",
                granted_by="usr_admin",
                # No connection provided - should use connection pool
            )

            # Verify execute was called
            mock_conn.execute.assert_called()


@pytest.mark.asyncio
class TestACLEnforcerRevokePermission:
    """Test permission revocation functionality."""

    async def test_revoke_permission_success(self, mock_conn):
        """Test successfully revoking a permission."""
        enforcer = ACLEnforcer()
        await enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV", connection=mock_conn)

        # Verify execute was called for the update
        mock_conn.execute.assert_called()

    async def test_revoke_permission_nonexistent_acl(self, mock_conn):
        """Test revoking a non-existent ACL entry (should not error)."""
        enforcer = ACLEnforcer()
        # This should not raise an error even if ACL doesn't exist
        await enforcer.revoke_permission("nonexistent_acl_id", connection=mock_conn)

    async def test_revoke_permission_table_missing_error(self, mock_conn):
        """Test revoking permission when st_acl table doesn't exist."""
        # Mock error with "does not exist" to trigger table not found handling
        mock_conn.execute.side_effect = Exception('relation "st_acl" does not exist')

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="st_acl table not found"):
            await enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV", connection=mock_conn)

    async def test_revoke_permission_uses_connection_pool(self):
        """Test revoking permission without explicit connection (uses connection pool)."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        # Create async context manager mock
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("k0.policy.acl_enforcer.connection_scope", return_value=mock_cm):
            enforcer = ACLEnforcer()
            await enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV")  # No connection provided

            # Verify execute was called
            mock_conn.execute.assert_called()


@pytest.mark.asyncio
class TestACLEnforcerListPermissions:
    """Test permission listing functionality."""

    async def test_list_permissions_all(self, mock_conn, sample_acl_entries):
        """Test listing all permissions."""
        # Mock database returning active entries (excluding revoked)
        active_entries = [e for e in sample_acl_entries if e["revoked_at"] is None]
        mock_conn.fetch.return_value = active_entries

        enforcer = ACLEnforcer()
        entries = await enforcer.list_permissions(connection=mock_conn)

        # Should return 3 entries (excluding the revoked one)
        assert len(entries) == 3
        assert all(isinstance(entry, ACLEntry) for entry in entries)

    async def test_list_permissions_with_filters(self, mock_conn):
        """Test listing permissions with various filters."""
        # Mock returning filtered entries for evt_123
        mock_conn.fetch.return_value = [
            {
                "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "resource_type": "st_epi",
                "resource_id": "evt_123",
                "principal_type": "user",
                "principal_id": "usr_alice",
                "permission": "read",
                "privacy_band": "GREEN",
                "granted_at": "2024-01-01T00:00:00Z",
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
                "granted_at": "2024-01-01T00:00:00Z",
                "granted_by": "usr_admin",
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked_at": None,
            },
        ]

        enforcer = ACLEnforcer()
        entries = await enforcer.list_permissions(
            resource_type="st_epi", resource_id="evt_123", connection=mock_conn
        )
        assert len(entries) == 2
        assert all(entry.resource_id == "evt_123" for entry in entries)

    async def test_list_permissions_include_revoked(self, mock_conn, sample_acl_entries):
        """Test listing permissions including revoked ones."""
        # Mock returning all entries including revoked
        mock_conn.fetch.return_value = sample_acl_entries

        enforcer = ACLEnforcer()
        entries = await enforcer.list_permissions(include_revoked=True, connection=mock_conn)

        # Should return all 4 entries including revoked
        assert len(entries) == 4

    async def test_list_permissions_empty_database(self, mock_conn):
        """Test listing permissions on empty database."""
        mock_conn.fetch.return_value = []

        enforcer = ACLEnforcer()
        entries = await enforcer.list_permissions(connection=mock_conn)
        assert entries == []

    async def test_list_permissions_table_missing(self, mock_conn):
        """Test listing permissions when st_acl table doesn't exist."""
        # Mock error with "does not exist" to trigger fallback to empty list
        mock_conn.fetch.side_effect = Exception('relation "st_acl" does not exist')

        enforcer = ACLEnforcer()
        entries = await enforcer.list_permissions(connection=mock_conn)
        assert entries == []  # Should return empty list

    async def test_list_permissions_database_error(self, mock_conn):
        """Test listing permissions with database error."""
        import asyncpg

        mock_conn.fetch.side_effect = asyncpg.PostgresError("Disk I/O error")

        enforcer = ACLEnforcer()
        with pytest.raises(ACLEnforcerError, match="Failed to list permissions"):
            await enforcer.list_permissions(connection=mock_conn)


@pytest.mark.asyncio
class TestACLEnforcerIntegration:
    """Integration tests combining multiple operations."""

    async def test_grant_check_revoke_workflow(self, mock_conn):
        """Test complete workflow: grant -> check -> revoke -> check."""
        enforcer = ACLEnforcer()

        # Grant permission
        await enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_admin",
            connection=mock_conn,
        )

        # Mock check_permission returning True after grant
        mock_conn.fetchrow.return_value = {"acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
        )
        assert result is True

        # Revoke permission
        await enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV", connection=mock_conn)

        # Mock check_permission returning False after revoke
        mock_conn.fetchrow.return_value = None
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
        )
        assert result is False

    async def test_multiple_permissions_same_resource(self, mock_conn):
        """Test multiple permissions on the same resource for different principals."""
        enforcer = ACLEnforcer()

        # Grant read to Alice
        await enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_admin",
            connection=mock_conn,
        )

        # Grant write to Bob
        await enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FBW",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_bob",
            permission="write",
            granted_by="usr_admin",
            connection=mock_conn,
        )

        # Mock check for Alice read - granted
        mock_conn.fetchrow.return_value = {"acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=mock_conn
        )
        assert result is True

        # Mock check for Bob write - granted
        mock_conn.fetchrow.return_value = {"acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FBW"}
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_bob", "write", connection=mock_conn
        )
        assert result is True

        # Mock check for Alice write - not granted
        mock_conn.fetchrow.return_value = None
        result = await enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "write", connection=mock_conn
        )
        assert result is False  # Alice doesn't have write

        # Mock list permissions
        mock_conn.fetch.return_value = [
            {
                "acl_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "resource_type": "st_epi",
                "resource_id": "evt_123",
                "principal_type": "user",
                "principal_id": "usr_alice",
                "permission": "read",
                "privacy_band": None,
                "granted_at": "2024-01-01T00:00:00Z",
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
                "privacy_band": None,
                "granted_at": "2024-01-01T00:00:00Z",
                "granted_by": "usr_admin",
                "expires_at": None,
                "revoked_at": None,
            },
        ]
        entries = await enforcer.list_permissions(
            resource_type="st_epi", resource_id="evt_123", connection=mock_conn
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
