"""
K0 Retention Policy Enforcer - Data Lifecycle Management

Applies retention policies from st_retention_policy table.
Archives expired data to blob storage or performs hard deletes.

References:
- Migration 0004: st_retention_policy, st_archive_manifest tables
- Contracts: k0/contracts/jsonschema/retention_policy.schema.json
            k0/contracts/jsonschema/archive_manifest.schema.json
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from k0.uow.connection_pool import connection_scope


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
        stats = enforcer.apply_policies()
        # Returns: {"archived": 150, "deleted": 20, "errors": 0}

        # Get expired resources for specific policy
        expired = enforcer.get_expired_resources(policy_id="policy_001")
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
            Function to archive data to blob storage.
            Signature: (resource_type, resource_id, data) -> archive_location
        """
        self._archive_callback = archive_callback

    def apply_policies(
        self,
        *,
        dry_run: bool = False,
        connection: Optional[sqlite3.Connection] = None,
    ) -> dict:
        """
        Apply all enabled retention policies.

        This method should be run as a nightly background job.

        Parameters
        ----------
        dry_run : bool
            If True, only return stats without making changes
        connection : sqlite3.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        dict
            Statistics: {"archived": int, "deleted": int, "errors": int}
        """
        stats = {"archived": 0, "deleted": 0, "errors": 0}

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                # Get all enabled policies
                policies = self._load_policies(conn, enabled_only=True)

                for policy in policies:
                    try:
                        expired = self._get_expired_resources_for_policy(conn, policy)

                        if not dry_run:
                            if policy.archive_enabled and self._archive_callback:
                                # Archive to blob storage
                                for resource in expired:
                                    try:
                                        self._archive_resource(conn, policy, resource)
                                        stats["archived"] += 1
                                    except Exception as e:
                                        print(f"Archive error for {resource['id']}: {e}")
                                        stats["errors"] += 1
                            else:
                                # Hard delete
                                for resource in expired:
                                    try:
                                        id_column = resource.get("id_column", "id")
                                        self._delete_resource(
                                            conn, policy.resource_type, resource["id"], id_column
                                        )
                                        stats["deleted"] += 1
                                    except Exception as e:
                                        print(f"Delete error for {resource['id']}: {e}")
                                        stats["errors"] += 1

                        if connection is None:
                            conn.commit()

                    except Exception as e:
                        print(f"Policy error for {policy.policy_id}: {e}")
                        stats["errors"] += 1

                return stats

            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    # Retention tables don't exist (Migration 0004 not applied)
                    return stats
                raise RetentionEnforcerError(f"Failed to apply policies: {e}") from e

    def get_expired_resources(
        self,
        policy_id: str,
        *,
        connection: Optional[sqlite3.Connection] = None,
    ) -> List[dict]:
        """
        Get resources that have exceeded retention period for a policy.

        Parameters
        ----------
        policy_id : str
            Policy ID to check
        connection : sqlite3.Connection, optional
            Database connection

        Returns
        -------
        List[dict]
            List of expired resources with fields: id, created_at, age_days
        """
        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                # Load policy
                policy_row = conn.execute(
                    "SELECT * FROM st_retention_policy WHERE policy_id = ?",
                    (policy_id,),
                ).fetchone()

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

                return self._get_expired_resources_for_policy(conn, policy)

            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    return []
                raise RetentionEnforcerError(f"Failed to get expired resources: {e}") from e

    def _load_policies(
        self, conn: sqlite3.Connection, enabled_only: bool = False
    ) -> List[RetentionPolicy]:
        """Load retention policies from st_retention_policy."""
        query = "SELECT * FROM st_retention_policy"
        if enabled_only:
            query += " WHERE enabled = 1"

        rows = conn.execute(query).fetchall()
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

    def _get_expired_resources_for_policy(
        self, conn: sqlite3.Connection, policy: RetentionPolicy
    ) -> List[dict]:
        """Get resources that exceed retention period for a policy."""
        cutoff_date = (
            datetime.now(timezone.utc) - timedelta(days=policy.retention_days)
        ).isoformat()

        # Build dynamic query based on resource type
        # Assumes all memory tables have: id column (first column), created_at, tenant_id fields
        query = f"SELECT * FROM {policy.resource_type} WHERE created_at < ?"
        params = [cutoff_date]

        if policy.tenant_id_filter:
            query += " AND tenant_id = ?"
            params.append(policy.tenant_id_filter)

        if policy.privacy_band_filter:
            query += " AND privacy_band = ?"
            params.append(policy.privacy_band_filter)

        try:
            rows = conn.execute(query, params).fetchall()
            result = []
            for row in rows:
                # Get the primary key column name dynamically
                # SQLite row.keys() gives column names
                id_col = row.keys()[0] if row.keys() else "id"
                resource_id = row[id_col]

                result.append(
                    {
                        "id": resource_id,
                        "id_column": id_col,  # Store column name for deletion
                        "created_at": row["created_at"] if "created_at" in row.keys() else None,
                        "age_days": (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(
                                row["created_at"] if "created_at" in row.keys() else cutoff_date
                            )
                        ).days,
                    }
                )
            return result
        except Exception as e:
            print(f"Error getting expired resources: {e}")
            return []

    def _archive_resource(
        self, conn: sqlite3.Connection, policy: RetentionPolicy, resource: dict
    ) -> None:
        """Archive resource to blob storage and record in st_archive_manifest."""
        if not self._archive_callback:
            raise RetentionEnforcerError("Archive callback not configured")

        # Get the primary key column name from resource dict
        id_column = resource.get("id_column", "id")

        # Fetch full resource data
        row = conn.execute(
            f"SELECT * FROM {policy.resource_type} WHERE {id_column} = ?",
            (resource["id"],),
        ).fetchone()

        # Archive to blob storage (callback handles compression, upload, etc)
        archive_location = self._archive_callback(policy.resource_type, resource["id"], dict(row))

        # Record in manifest
        archived_at = datetime.now(timezone.utc).isoformat()
        manifest_id = f"archive_{resource['id']}"  # Simple ID generation

        conn.execute(
            """
            INSERT INTO st_archive_manifest (
                manifest_id, resource_type, resource_id,
                archive_location, archived_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (manifest_id, policy.resource_type, resource["id"], archive_location, archived_at),
        )

        # Delete from source table
        self._delete_resource(conn, policy.resource_type, resource["id"], id_column)

    def _delete_resource(
        self, conn: sqlite3.Connection, resource_type: str, resource_id: str, id_column: str = "id"
    ) -> None:
        """Hard delete resource from table."""
        conn.execute(
            f"DELETE FROM {resource_type} WHERE {id_column} = ?",
            (resource_id,),
        )
