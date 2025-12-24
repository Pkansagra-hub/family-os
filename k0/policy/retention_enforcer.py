"""
K0 Retention Policy Enforcer - Data Lifecycle Management

Applies retention policies from st_retention_policy table.
Archives expired data to blob storage or performs hard deletes.

References:
- Migration 0004: st_retention_policy, st_archive_manifest tables
- Contracts: k0/contracts/jsonschema/retention_policy.schema.json
            k0/contracts/jsonschema/archive_manifest.schema.json
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Optional

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg


@dataclass(frozen=True)
class RetentionPolicy:
    """Represents a data retention policy."""

    policy_id: str
    resource_type: str  # st_epi, st_sem, etc
    retention_days: int
    archive_enabled: bool
    privacy_band_filter: Optional[str] = None
    tenant_id_filter: Optional[str] = None
    enabled: bool = True
    created_at: str = ""
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class ArchiveManifest:
    """Represents an archived data entry."""

    manifest_id: str
    resource_type: str
    resource_id: str
    archive_location: str
    checksum: Optional[str] = None
    compressed_size_bytes: Optional[int] = None
    archived_at: str = ""
    delete_after: Optional[str] = None
    tenant_id: Optional[str] = None


class RetentionEnforcerError(Exception):
    """Base exception for retention enforcer errors."""


class RetentionEnforcer:
    """
    Data retention policy enforcement and archival.

    Usage:
        enforcer = RetentionEnforcer()

        # Apply all enabled policies (nightly job)
        stats = await enforcer.apply_policies()
        # Returns: {"archived": 150, "deleted": 20, "errors": 0}

        # Get expired resources for specific policy
        expired = await enforcer.get_expired_resources(policy_id="policy_001")
    """

    def __init__(
        self,
        *,
        archive_callback=None,
    ):
        """
        Initialize retention enforcer.

        Parameters
        ----------
        archive_callback : callable, optional
            Async function to archive data to blob storage.
            Signature: async (resource_type, resource_id, data) -> archive_location
        """
        self._archive_callback = archive_callback

    async def apply_policies(
        self,
        *,
        dry_run: bool = False,
        connection: Optional["asyncpg.Connection"] = None,
    ) -> dict:
        """
        Apply all enabled retention policies.

        This method should be run as a nightly background job.

        Parameters
        ----------
        dry_run : bool
            If True, only return stats without making changes
        connection : asyncpg.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        dict
            Statistics: {"archived": int, "deleted": int, "errors": int}
        """
        stats = {"archived": 0, "deleted": 0, "errors": 0}

        async def _run_with_conn(conn: "asyncpg.Connection") -> dict:
            nonlocal stats
            try:
                # Get all enabled policies
                policies = await self._load_policies(conn, enabled_only=True)

                for policy in policies:
                    try:
                        expired = await self._get_expired_resources_for_policy(conn, policy)

                        if not dry_run:
                            if policy.archive_enabled and self._archive_callback:
                                # Archive to blob storage
                                for resource in expired:
                                    try:
                                        await self._archive_resource(conn, policy, resource)
                                        stats["archived"] += 1
                                    except Exception as e:
                                        print(f"Archive error for {resource['id']}: {e}")
                                        stats["errors"] += 1
                            else:
                                # Hard delete
                                for resource in expired:
                                    try:
                                        id_column = resource.get("id_column", "id")
                                        await self._delete_resource(
                                            conn, policy.resource_type, resource["id"], id_column
                                        )
                                        stats["deleted"] += 1
                                    except Exception as e:
                                        print(f"Delete error for {resource['id']}: {e}")
                                        stats["errors"] += 1

                    except Exception as e:
                        print(f"Policy error for {policy.policy_id}: {e}")
                        stats["errors"] += 1

                return stats

            except Exception as e:
                if "does not exist" in str(e):
                    # Retention tables don't exist (migrations not applied)
                    return stats
                raise RetentionEnforcerError(f"Failed to apply policies: {e}") from e

        if connection is not None:
            return await _run_with_conn(connection)
        else:
            async with connection_scope() as conn:
                return await _run_with_conn(conn)

    async def get_expired_resources(
        self,
        policy_id: str,
        *,
        connection: Optional["asyncpg.Connection"] = None,
    ) -> List[dict]:
        """
        Get resources that have exceeded retention period for a policy.

        Parameters
        ----------
        policy_id : str
            Policy ID to check
        connection : asyncpg.Connection, optional
            Database connection

        Returns
        -------
        List[dict]
            List of expired resources with fields: id, created_at, age_days
        """

        async def _run_with_conn(conn: "asyncpg.Connection") -> List[dict]:
            try:
                # Load policy
                policy_row = await conn.fetchrow(
                    "SELECT * FROM st_retention_policy WHERE policy_id = $1",
                    policy_id,
                )

                if not policy_row:
                    return []

                policy = RetentionPolicy(
                    policy_id=policy_row["policy_id"],
                    resource_type=policy_row["resource_type"],
                    retention_days=policy_row["retention_days"],
                    archive_enabled=bool(policy_row["archive_enabled"]),
                    privacy_band_filter=policy_row["privacy_band_filter"],
                    tenant_id_filter=policy_row["tenant_id_filter"],
                    enabled=bool(policy_row["enabled"]),
                    created_at=policy_row["created_at"],
                    updated_at=policy_row["updated_at"],
                )

                return await self._get_expired_resources_for_policy(conn, policy)

            except Exception as e:
                if "does not exist" in str(e):
                    return []
                raise RetentionEnforcerError(f"Failed to get expired resources: {e}") from e

        if connection is not None:
            return await _run_with_conn(connection)
        else:
            async with connection_scope() as conn:
                return await _run_with_conn(conn)

    async def _load_policies(
        self, conn: "asyncpg.Connection", enabled_only: bool = False
    ) -> List[RetentionPolicy]:
        """Load retention policies from st_retention_policy."""
        query = "SELECT * FROM st_retention_policy"
        if enabled_only:
            query += " WHERE enabled = true"

        rows = await conn.fetch(query)
        return [
            RetentionPolicy(
                policy_id=row["policy_id"],
                resource_type=row["resource_type"],
                retention_days=row["retention_days"],
                archive_enabled=bool(row["archive_enabled"]),
                privacy_band_filter=row["privacy_band_filter"],
                tenant_id_filter=row["tenant_id_filter"],
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def _get_expired_resources_for_policy(
        self, conn: "asyncpg.Connection", policy: RetentionPolicy
    ) -> List[dict]:
        """Get resources that exceed retention period for a policy."""
        cutoff_date = (
            datetime.now(timezone.utc) - timedelta(days=policy.retention_days)
        ).isoformat()

        # Build dynamic query based on resource type
        # Assumes all memory tables have: id column (first column), created_at, tenant_id fields
        query = f"SELECT * FROM {policy.resource_type} WHERE created_at < $1"
        params: list = [cutoff_date]
        param_idx = 2

        if policy.tenant_id_filter:
            query += f" AND tenant_id = ${param_idx}"
            params.append(policy.tenant_id_filter)
            param_idx += 1

        if policy.privacy_band_filter:
            query += f" AND privacy_band = ${param_idx}"
            params.append(policy.privacy_band_filter)

        try:
            rows = await conn.fetch(query, *params)
            result = []
            for row in rows:
                # Get the primary key column name dynamically
                # asyncpg Record.keys() gives column names
                row_keys = list(row.keys())
                id_col = row_keys[0] if row_keys else "id"
                resource_id = row[id_col]

                result.append(
                    {
                        "id": resource_id,
                        "id_column": id_col,  # Store column name for deletion
                        "created_at": row["created_at"] if "created_at" in row_keys else None,
                        "age_days": (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(
                                row["created_at"] if "created_at" in row_keys else cutoff_date
                            )
                        ).days,
                    }
                )
            return result
        except Exception as e:
            print(f"Error getting expired resources: {e}")
            return []

    async def _archive_resource(
        self, conn: "asyncpg.Connection", policy: RetentionPolicy, resource: dict
    ) -> None:
        """Archive resource to blob storage and record in st_archive_manifest."""
        if not self._archive_callback:
            raise RetentionEnforcerError("Archive callback not configured")

        # Get the primary key column name from resource dict
        id_column = resource.get("id_column", "id")

        # Fetch full resource data
        row = await conn.fetchrow(
            f"SELECT * FROM {policy.resource_type} WHERE {id_column} = $1",
            resource["id"],
        )

        # Archive to blob storage (callback handles compression, upload, etc)
        archive_location = await self._archive_callback(
            policy.resource_type, resource["id"], dict(row)
        )

        # Record in manifest
        archived_at = datetime.now(timezone.utc).isoformat()
        manifest_id = f"archive_{resource['id']}"  # Simple ID generation

        await conn.execute(
            """
            INSERT INTO st_archive_manifest (
                manifest_id, resource_type, resource_id,
                archive_location, archived_at
            ) VALUES ($1, $2, $3, $4, $5)
            """,
            manifest_id,
            policy.resource_type,
            resource["id"],
            archive_location,
            archived_at,
        )

        # Delete from source table
        await self._delete_resource(conn, policy.resource_type, resource["id"], id_column)

    async def _delete_resource(
        self,
        conn: "asyncpg.Connection",
        resource_type: str,
        resource_id: str,
        id_column: str = "id",
    ) -> None:
        """Hard delete resource from table."""
        await conn.execute(
            f"DELETE FROM {resource_type} WHERE {id_column} = $1",
            resource_id,
        )
