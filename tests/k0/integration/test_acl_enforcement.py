"""
Integration tests for ACL Policy Engine

Tests the normalized access control enforcement using st_acl table from Migration 0004.
Performance target: <2ms P95 for permission checks.

Run with: python -m pytest tests/k0/integration/test_acl_enforcement.py -v
"""

import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from k0.policy.acl_enforcer import ACLEnforcer, ACLEnforcerError


@pytest.fixture
def temp_db_with_acl():
    """Create temporary database with Migration 0004 ACL schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_acl.db"
        conn = sqlite3.connect(str(db_path))
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
              revoked_at TEXT,
              CHECK(principal_type IN ('user', 'device', 'service')),
              CHECK(permission IN ('read', 'write', 'delete', 'share')),
              CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED'))
            )
        """
        )

        conn.execute("CREATE INDEX idx_acl_resource ON st_acl(resource_type, resource_id)")
        conn.execute("CREATE INDEX idx_acl_principal ON st_acl(principal_type, principal_id)")
        conn.execute("CREATE INDEX idx_acl_permission ON st_acl(permission, revoked_at)")
        conn.commit()

        yield conn, str(db_path)
        conn.close()


def test_check_permission_granted(temp_db_with_acl):
    """Test permission check when ACL entry exists."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Grant permission
    acl_id = str(uuid.uuid4())
    enforcer.grant_permission(
        acl_id=acl_id,
        resource_type="st_epi",
        resource_id="evt_123",
        principal_type="user",
        principal_id="usr_alice",
        permission="read",
        granted_by="usr_alice",
        connection=conn,
    )

    # Check permission
    has_permission = enforcer.check_permission(
        resource_type="st_epi",
        resource_id="evt_123",
        principal_id="usr_alice",
        permission="read",
        connection=conn,
    )

    assert has_permission is True


def test_check_permission_denied(temp_db_with_acl):
    """Test permission check when ACL entry does NOT exist."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # No ACL entry exists - should deny
    has_permission = enforcer.check_permission(
        resource_type="st_epi",
        resource_id="evt_123",
        principal_id="usr_bob",
        permission="read",
        connection=conn,
    )

    assert has_permission is False


def test_check_permission_revoked(temp_db_with_acl):
    """Test permission check after revocation."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Grant permission
    acl_id = str(uuid.uuid4())
    enforcer.grant_permission(
        acl_id=acl_id,
        resource_type="st_epi",
        resource_id="evt_123",
        principal_type="user",
        principal_id="usr_alice",
        permission="write",
        granted_by="usr_admin",
        connection=conn,
    )

    # Verify permission exists
    assert enforcer.check_permission("st_epi", "evt_123", "usr_alice", "write", connection=conn)

    # Revoke permission
    enforcer.revoke_permission(acl_id, connection=conn)

    # Verify permission revoked
    assert not enforcer.check_permission("st_epi", "evt_123", "usr_alice", "write", connection=conn)


def test_check_permission_expired(temp_db_with_acl):
    """Test permission check with expired timestamp."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Grant permission that expired 1 hour ago
    acl_id = str(uuid.uuid4())
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    enforcer.grant_permission(
        acl_id=acl_id,
        resource_type="st_epi",
        resource_id="evt_123",
        principal_type="user",
        principal_id="usr_alice",
        permission="read",
        granted_by="usr_admin",
        expires_at=expired_at,
        connection=conn,
    )

    # Permission should be denied (expired)
    has_permission = enforcer.check_permission(
        "st_epi", "evt_123", "usr_alice", "read", connection=conn
    )

    assert has_permission is False


def test_check_permission_privacy_band(temp_db_with_acl):
    """Test ACL with privacy band classification."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Grant READ permission on AMBER-classified resource
    acl_id = str(uuid.uuid4())
    enforcer.grant_permission(
        acl_id=acl_id,
        resource_type="st_epi",
        resource_id="evt_sensitive",
        principal_type="user",
        principal_id="usr_alice",
        permission="read",
        granted_by="usr_admin",
        privacy_band="AMBER",
        connection=conn,
    )

    # Check permission
    has_permission = enforcer.check_permission(
        "st_epi", "evt_sensitive", "usr_alice", "read", connection=conn
    )

    assert has_permission is True


def test_list_permissions_by_resource(temp_db_with_acl):
    """Test listing ACL entries filtered by resource."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Grant multiple permissions on same resource
    resource_id = "evt_collab"
    for user, perm in [("usr_alice", "read"), ("usr_bob", "write"), ("usr_charlie", "read")]:
        enforcer.grant_permission(
            acl_id=str(uuid.uuid4()),
            resource_type="st_epi",
            resource_id=resource_id,
            principal_type="user",
            principal_id=user,
            permission=perm,
            granted_by="usr_admin",
            connection=conn,
        )

    # List permissions for resource
    permissions = enforcer.list_permissions(
        resource_type="st_epi", resource_id=resource_id, connection=conn
    )

    assert len(permissions) == 3
    assert {p.principal_id for p in permissions} == {"usr_alice", "usr_bob", "usr_charlie"}


def test_list_permissions_by_principal(temp_db_with_acl):
    """Test listing ACL entries filtered by principal."""
    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Grant multiple permissions to same principal
    principal_id = "usr_alice"
    for resource, perm in [("evt_001", "read"), ("evt_002", "write"), ("evt_003", "read")]:
        enforcer.grant_permission(
            acl_id=str(uuid.uuid4()),
            resource_type="st_epi",
            resource_id=resource,
            principal_type="user",
            principal_id=principal_id,
            permission=perm,
            granted_by="usr_admin",
            connection=conn,
        )

    # List permissions for principal
    permissions = enforcer.list_permissions(principal_id=principal_id, connection=conn)

    assert len(permissions) == 3
    assert {p.resource_id for p in permissions} == {"evt_001", "evt_002", "evt_003"}


def test_check_permission_performance(temp_db_with_acl):
    """Test ACL check performance (<2ms P95 target)."""
    import time

    conn, _ = temp_db_with_acl
    enforcer = ACLEnforcer()

    # Create 100 ACL entries
    for i in range(100):
        enforcer.grant_permission(
            acl_id=str(uuid.uuid4()),
            resource_type="st_epi",
            resource_id=f"evt_{i}",
            principal_type="user",
            principal_id=f"usr_{i % 10}",  # 10 users
            permission="read",
            granted_by="usr_admin",
            connection=conn,
        )

    # Measure 100 permission checks
    times = []
    for i in range(100):
        start = time.perf_counter()
        enforcer.check_permission("st_epi", f"evt_{i}", f"usr_{i % 10}", "read", connection=conn)
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    # Calculate P95
    times.sort()
    p95_index = int(len(times) * 0.95)
    p95_latency = times[p95_index]

    print(f"P95 ACL check latency: {p95_latency:.2f}ms")
    assert p95_latency < 2.0, f"P95 latency {p95_latency:.2f}ms exceeds 2ms target"


def test_acl_enforcer_backward_compatible():
    """Test enforcer gracefully handles missing st_acl table."""
    # Create database WITHOUT st_acl table
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_baseline.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # No st_acl table created

        enforcer = ACLEnforcer()

        # Should return True (default permissive when table missing)
        has_permission = enforcer.check_permission(
            "st_epi", "evt_123", "usr_alice", "read", connection=conn
        )

        assert has_permission is True

        # Grant should raise error with helpful message
        with pytest.raises(ACLEnforcerError, match="st_acl table not found"):
            enforcer.grant_permission(
                acl_id="test_id",
                resource_type="st_epi",
                resource_id="evt_123",
                principal_type="user",
                principal_id="usr_alice",
                permission="read",
                granted_by="usr_admin",
                connection=conn,
            )

        conn.close()
