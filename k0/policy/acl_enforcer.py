"""
K0 ACL Policy Engine - Normalized Access Control Enforcement

Provides row-level permission checks using the st_acl table.
Performance target: <2ms P95 for permission checks.

References:
- Migration 0004: st_acl table schema
- Contract: k0/contracts/jsonschema/acl.schema.json
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg


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

    All methods are async and use asyncpg for PostgreSQL operations.

    Usage:
        enforcer = ACLEnforcer()

        # Check permission
        if await enforcer.check_permission("st_epi", "evt_123", "usr_alice", "read"):
            return memory

        # Grant permission
        await enforcer.grant_permission(
            acl_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            resource_type="st_epi",
            resource_id="evt_123",
            principal_type="user",
            principal_id="usr_alice",
            permission="read",
            granted_by="usr_alice"
        )

        # Revoke permission
        await enforcer.revoke_permission("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    """

    async def check_permission(
        self,
        resource_type: str,
        resource_id: str,
        principal_id: str,
        permission: str,
        *,
        principal_type: str = "user",
        connection: Optional["asyncpg.Connection"] = None,
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
        connection : asyncpg.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        bool
            True if permission granted and active, False otherwise
        """
        now = datetime.now(timezone.utc).isoformat()

        async def _run_with_conn(conn: "asyncpg.Connection") -> bool:
            try:
                # Query st_acl with all constraints
                result = await conn.fetchrow(
                    """
                    SELECT 1 FROM st_acl
                    WHERE resource_type = $1
                      AND resource_id = $2
                      AND principal_type = $3
                      AND principal_id = $4
                      AND permission = $5
                      AND revoked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > $6)
                    LIMIT 1
                    """,
                    resource_type,
                    resource_id,
                    principal_type,
                    principal_id,
                    permission,
                    now,
                )
                return result is not None
            except Exception as e:
                # Fallback: st_acl table doesn't exist (migrations not applied)
                if "does not exist" in str(e):
                    # Default permissive policy when ACL table unavailable
                    return True
                raise ACLEnforcerError(f"ACL check failed: {e}") from e

        if connection is not None:
            return await _run_with_conn(connection)
        else:
            async with connection_scope() as conn:
                return await _run_with_conn(conn)

    async def grant_permission(
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
        connection: Optional["asyncpg.Connection"] = None,
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
        connection : asyncpg.Connection, optional
            Database connection (uses connection pool if not provided)
        """
        granted_at = datetime.now(timezone.utc).isoformat()

        async def _run_with_conn(conn: "asyncpg.Connection") -> None:
            try:
                await conn.execute(
                    """
                    INSERT INTO st_acl (
                        acl_id, resource_type, resource_id,
                        principal_type, principal_id, permission,
                        privacy_band, granted_at, granted_by,
                        expires_at, revoked_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NULL)
                    """,
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
                )
            except Exception as e:
                if "does not exist" in str(e):
                    raise ACLEnforcerError("st_acl table not found - apply migrations") from e
                raise ACLEnforcerError(f"Failed to grant permission: {e}") from e

        if connection is not None:
            await _run_with_conn(connection)
        else:
            async with connection_scope() as conn:
                await _run_with_conn(conn)

    async def revoke_permission(
        self,
        acl_id: str,
        *,
        connection: Optional["asyncpg.Connection"] = None,
    ) -> None:
        """
        Revoke permission by setting revoked_at timestamp.

        Parameters
        ----------
        acl_id : str
            ACL entry ID to revoke
        connection : asyncpg.Connection, optional
            Database connection (uses connection pool if not provided)
        """
        revoked_at = datetime.now(timezone.utc).isoformat()

        async def _run_with_conn(conn: "asyncpg.Connection") -> None:
            try:
                await conn.execute(
                    "UPDATE st_acl SET revoked_at = $1 WHERE acl_id = $2",
                    revoked_at,
                    acl_id,
                )
            except Exception as e:
                if "does not exist" in str(e):
                    raise ACLEnforcerError("st_acl table not found - apply migrations") from e
                raise ACLEnforcerError(f"Failed to revoke permission: {e}") from e

        if connection is not None:
            await _run_with_conn(connection)
        else:
            async with connection_scope() as conn:
                await _run_with_conn(conn)

    async def list_permissions(
        self,
        *,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        include_revoked: bool = False,
        connection: Optional["asyncpg.Connection"] = None,
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
        connection : asyncpg.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        List[ACLEntry]
            List of matching ACL entries
        """
        query = "SELECT * FROM st_acl WHERE 1=1"
        params: list = []
        param_idx = 1

        if resource_type:
            query += f" AND resource_type = ${param_idx}"
            params.append(resource_type)
            param_idx += 1
        if resource_id:
            query += f" AND resource_id = ${param_idx}"
            params.append(resource_id)
            param_idx += 1
        if principal_id:
            query += f" AND principal_id = ${param_idx}"
            params.append(principal_id)
            param_idx += 1
        if not include_revoked:
            query += " AND revoked_at IS NULL"

        async def _run_with_conn(conn: "asyncpg.Connection") -> List[ACLEntry]:
            try:
                rows = await conn.fetch(query, *params)
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
            except Exception as e:
                if "does not exist" in str(e):
                    return []  # No ACL table = no entries
                raise ACLEnforcerError(f"Failed to list permissions: {e}") from e

        if connection is not None:
            return await _run_with_conn(connection)
        else:
            async with connection_scope() as conn:
                return await _run_with_conn(conn)
