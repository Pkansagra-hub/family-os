"""
K0 ACL Policy Engine - Normalized Access Control Enforcement

Provides row-level permission checks using the st_acl table.
Performance target: <2ms P95 for permission checks.

References:
- Migration 0004: st_acl table schema
- Contract: k0/contracts/jsonschema/acl.schema.json
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from k0.uow.connection_pool import connection_scope


@dataclass(frozen=True)
class ACLEntry:
    """Represents an access control list entry."""

    acl_id: str
    resource_type: str  # st_epi, st_sem, etc
    resource_id: str  # event_id, fact_id, etc
    principal_type: str  # user, device, service
    principal_id: str  # Neo4j Person ID, device_id, service name
    permission: str  # read, write, delete, share
    privacy_band: Optional[str] = None  # GREEN, AMBER, RED
    granted_at: str = ""
    granted_by: str = ""
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None


class ACLEnforcerError(Exception):
    """Base exception for ACL enforcer errors."""


class ACLEnforcer:
    """
    Normalized access control enforcement using st_acl table.

    Usage:
        enforcer = ACLEnforcer()

        # Check permission
        if enforcer.check_permission("st_epi", "evt_123", "usr_alice", "read"):
            return memory

        # Grant permission
        enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_alice"
        )

        # Revoke permission
        enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    """

    def check_permission(
        self,
        resource_type: str,
        resource_id: str,
        principal_id: str,
        permission: str,
        *,
        principal_type: str = "user",
        connection: Optional[sqlite3.Connection] = None,
    ) -> bool:
        """
        Check if principal has permission on resource.

        Performance: <2ms P95 (indexed query on st_acl)

        Parameters
        ----------
        resource_type : str
            Type of resource (st_epi, st_sem, etc)
        resource_id : str
            ID of specific resource (event_id, fact_id, etc)
        principal_id : str
            ID of entity requesting access
        permission : str
            Permission type (read, write, delete, share)
        principal_type : str
            Type of principal (default: "user")
        connection : sqlite3.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        bool
            True if permission granted and active, False otherwise
        """
        now = datetime.now(timezone.utc).isoformat()

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                # Query st_acl with all constraints
                result = conn.execute(
                    """
                    SELECT 1 FROM st_acl
                    WHERE resource_type = ?
                      AND resource_id = ?
                      AND principal_type = ?
                      AND principal_id = ?
                      AND permission = ?
                      AND revoked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > ?)
                    LIMIT 1
                    """,
                    (
                        resource_type,
                        resource_id,
                        principal_type,
                        principal_id,
                        permission,
                        now,
                    ),
                ).fetchone()
                return result is not None
            except sqlite3.OperationalError as e:
                # Fallback: st_acl table doesn't exist (Migration 0004 not applied)
                if "no such table" in str(e):
                    # Default permissive policy when ACL table unavailable
                    return True
                raise ACLEnforcerError(f"ACL check failed: {e}") from e

    def grant_permission(
        self,
        acl_id: str,
        resource_type: str,
        resource_id: str,
        principal_type: str,
        principal_id: str,
        permission: str,
        granted_by: str,
        *,
        privacy_band: Optional[str] = None,
        expires_at: Optional[str] = None,
        connection: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        Grant permission by inserting into st_acl.

        Parameters
        ----------
        acl_id : str
            Unique ACL entry ID (ULID or UUID)
        resource_type : str
            Type of resource (st_epi, st_sem, etc)
        resource_id : str
            ID of specific resource
        principal_type : str
            Type of principal (user, device, service)
        principal_id : str
            ID of entity being granted permission
        permission : str
            Permission type (read, write, delete, share)
        granted_by : str
            ID of entity granting permission
        privacy_band : str, optional
            Privacy classification (GREEN, AMBER, RED)
        expires_at : str, optional
            ISO8601 timestamp when permission expires
        connection : sqlite3.Connection, optional
            Database connection (uses connection pool if not provided)
        """
        granted_at = datetime.now(timezone.utc).isoformat()

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO st_acl (
                        acl_id, resource_type, resource_id,
                        principal_type, principal_id, permission,
                        privacy_band, granted_at, granted_by,
                        expires_at, revoked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        acl_id,
                        resource_type,
                        resource_id,
                        principal_type,
                        principal_id,
                        permission,
                        privacy_band,
                        granted_at,
                        granted_by,
                        expires_at,
                    ),
                )
                if connection is None:
                    conn.commit()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    raise ACLEnforcerError("st_acl table not found - apply Migration 0004") from e
                raise ACLEnforcerError(f"Failed to grant permission: {e}") from e

    def revoke_permission(
        self,
        acl_id: str,
        *,
        connection: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        Revoke permission by setting revoked_at timestamp.

        Parameters
        ----------
        acl_id : str
            ACL entry ID to revoke
        connection : sqlite3.Connection, optional
            Database connection (uses connection pool if not provided)
        """
        revoked_at = datetime.now(timezone.utc).isoformat()

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                conn.execute(
                    "UPDATE st_acl SET revoked_at = ? WHERE acl_id = ?",
                    (revoked_at, acl_id),
                )
                if connection is None:
                    conn.commit()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    raise ACLEnforcerError("st_acl table not found - apply Migration 0004") from e
                raise ACLEnforcerError(f"Failed to revoke permission: {e}") from e

    def list_permissions(
        self,
        *,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        include_revoked: bool = False,
        connection: Optional[sqlite3.Connection] = None,
    ) -> List[ACLEntry]:
        """
        List ACL entries matching filters.

        Parameters
        ----------
        resource_type : str, optional
            Filter by resource type
        resource_id : str, optional
            Filter by resource ID
        principal_id : str, optional
            Filter by principal ID
        include_revoked : bool
            Include revoked permissions (default: False)
        connection : sqlite3.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        List[ACLEntry]
            List of matching ACL entries
        """
        query = "SELECT * FROM st_acl WHERE 1=1"
        params = []

        if resource_type:
            query += " AND resource_type = ?"
            params.append(resource_type)
        if resource_id:
            query += " AND resource_id = ?"
            params.append(resource_id)
        if principal_id:
            query += " AND principal_id = ?"
            params.append(principal_id)
        if not include_revoked:
            query += " AND revoked_at IS NULL"

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                rows = conn.execute(query, params).fetchall()
                return [
                    ACLEntry(
                        acl_id=row["acl_id"],
                        resource_type=row["resource_type"],
                        resource_id=row["resource_id"],
                        principal_type=row["principal_type"],
                        principal_id=row["principal_id"],
                        permission=row["permission"],
                        privacy_band=row["privacy_band"],
                        granted_at=row["granted_at"],
                        granted_by=row["granted_by"],
                        expires_at=row["expires_at"],
                        revoked_at=row["revoked_at"],
                    )
                    for row in rows
                ]
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    return []  # No ACL table = no entries
                raise ACLEnforcerError(f"Failed to list permissions: {e}") from e
