"""
K0 CRDT Merge Logger - Conflict Resolution Audit Trail

Logs all CRDT conflict resolution events to st_crdt_merge_log for debugging,
compliance, and analytics.

References:
- Migration 0004: st_crdt_merge_log table schema
- Contract: k0/contracts/jsonschema/crdt_merge_log.schema.json
- Research: Honda 2008 (Multiparty Session Types), Shapiro 2011 (CRDTs)
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from k0.uow.connection_pool import connection_scope


@dataclass(frozen=True)
class CRDTMergeLog:
    """Represents a CRDT conflict resolution log entry."""

    merge_id: str
    resource_type: str  # st_epi, st_sem, etc
    resource_id: str  # event_id, fact_id, etc
    merge_strategy: str  # last-write-wins, vector-clock, manual, semantic-merge
    winner_device_id: str
    loser_device_id: str
    winner_vector_clock: Optional[str] = None  # JSON-encoded
    loser_vector_clock: Optional[str] = None  # JSON-encoded
    conflict_reason: Optional[str] = None
    merged_at: str = ""
    tenant_id: Optional[str] = None


class CRDTMergeLoggerError(Exception):
    """Base exception for CRDT merge logger errors."""


class CRDTMergeLogger:
    """
    Log CRDT conflict resolution events for audit and debugging.

    Usage:
        logger = CRDTMergeLogger()

        # After resolving conflict
        logger.log_merge(
            merge_id="merge_123",
            resource_type="st_epi",
            resource_id="evt_abc123",
            merge_strategy="vector-clock",
            winner_device_id="device_001",
            loser_device_id="device_002",
            winner_vector_clock={"device_001": 5, "device_002": 3},
            loser_vector_clock={"device_001": 4, "device_002": 4},
            conflict_reason="Concurrent edits detected"
        )
    """

    def log_merge(
        self,
        merge_id: str,
        resource_type: str,
        resource_id: str,
        merge_strategy: str,
        winner_device_id: str,
        loser_device_id: str,
        *,
        winner_vector_clock: Optional[Dict] = None,
        loser_vector_clock: Optional[Dict] = None,
        conflict_reason: Optional[str] = None,
        tenant_id: Optional[str] = None,
        connection: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        Log a CRDT conflict resolution event.

        Parameters
        ----------
        merge_id : str
            Unique identifier for merge event (ULID or UUID)
        resource_type : str
            Type of resource with conflict (st_epi, st_sem, etc)
        resource_id : str
            ID of resource with conflict
        merge_strategy : str
            Strategy used (last-write-wins, vector-clock, manual, semantic-merge)
        winner_device_id : str
            Device ID of winning version
        loser_device_id : str
            Device ID of losing version
        winner_vector_clock : dict, optional
            Vector clock of winner (will be JSON-encoded)
        loser_vector_clock : dict, optional
            Vector clock of loser (will be JSON-encoded)
        conflict_reason : str, optional
            Human-readable explanation of conflict
        tenant_id : str, optional
            Tenant ID for multi-tenancy tracking
        connection : sqlite3.Connection, optional
            Database connection (uses connection pool if not provided)
        """
        merged_at = datetime.now(timezone.utc).isoformat()

        # JSON-encode vector clocks
        winner_vc_json = json.dumps(winner_vector_clock) if winner_vector_clock else None
        loser_vc_json = json.dumps(loser_vector_clock) if loser_vector_clock else None

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO st_crdt_merge_log (
                        merge_id, resource_type, resource_id,
                        merge_strategy, winner_device_id, loser_device_id,
                        winner_vector_clock, loser_vector_clock,
                        conflict_reason, merged_at, tenant_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        merge_id,
                        resource_type,
                        resource_id,
                        merge_strategy,
                        winner_device_id,
                        loser_device_id,
                        winner_vc_json,
                        loser_vc_json,
                        conflict_reason,
                        merged_at,
                        tenant_id,
                    ),
                )
                if connection is None:
                    conn.commit()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    # CRDT merge log table doesn't exist (Migration 0004 not applied)
                    # Log to stderr but don't fail the merge operation
                    print(
                        f"Warning: st_crdt_merge_log table not found - "
                        f"merge {merge_id} not logged (apply Migration 0004)"
                    )
                    return
                raise CRDTMergeLoggerError(f"Failed to log merge: {e}") from e

    def get_merge_history(
        self,
        *,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 100,
        connection: Optional[sqlite3.Connection] = None,
    ) -> list[CRDTMergeLog]:
        """
        Retrieve merge history with optional filters.

        Parameters
        ----------
        resource_type : str, optional
            Filter by resource type
        resource_id : str, optional
            Filter by specific resource
        device_id : str, optional
            Filter by device ID (winner or loser)
        limit : int
            Maximum number of entries to return (default: 100)
        connection : sqlite3.Connection, optional
            Database connection

        Returns
        -------
        list[CRDTMergeLog]
            List of merge log entries, ordered by merged_at DESC
        """
        query = "SELECT * FROM st_crdt_merge_log WHERE 1=1"
        params = []

        if resource_type:
            query += " AND resource_type = ?"
            params.append(resource_type)
        if resource_id:
            query += " AND resource_id = ?"
            params.append(resource_id)
        if device_id:
            query += " AND (winner_device_id = ? OR loser_device_id = ?)"
            params.extend([device_id, device_id])

        query += " ORDER BY merged_at DESC LIMIT ?"
        params.append(limit)

        resolve = connection if connection else connection_scope()
        with resolve as conn:
            try:
                rows = conn.execute(query, params).fetchall()
                return [
                    CRDTMergeLog(
                        merge_id=row["merge_id"],
                        resource_type=row["resource_type"],
                        resource_id=row["resource_id"],
                        merge_strategy=row["merge_strategy"],
                        winner_device_id=row["winner_device_id"],
                        loser_device_id=row["loser_device_id"],
                        winner_vector_clock=row["winner_vector_clock"],
                        loser_vector_clock=row["loser_vector_clock"],
                        conflict_reason=row["conflict_reason"],
                        merged_at=row["merged_at"],
                        tenant_id=row["tenant_id"],
                    )
                    for row in rows
                ]
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    return []  # No merge log table = no entries
                raise CRDTMergeLoggerError(f"Failed to get merge history: {e}") from e


def resolve_conflict_with_logging(
    local_memory: Dict,
    remote_memory: Dict,
    resource_type: str,
    resource_id: str,
    logger: CRDTMergeLogger,
    *,
    merge_strategy: str = "vector-clock",
    connection: Optional[sqlite3.Connection] = None,
) -> Dict:
    """
    Resolve CRDT conflict and log the decision.

    Example integration for CRDT merge operations.

    Parameters
    ----------
    local_memory : dict
        Local version with vector_clock and device_id
    remote_memory : dict
        Remote version with vector_clock and device_id
    resource_type : str
        Type of resource (st_epi, st_sem, etc)
    resource_id : str
        ID of resource
    logger : CRDTMergeLogger
        Logger instance
    merge_strategy : str
        Strategy to use (default: "vector-clock")
    connection : sqlite3.Connection, optional
        Database connection

    Returns
    -------
    dict
        Winning memory version
    """
    # Determine winner based on strategy
    if merge_strategy == "vector-clock":
        # Compare vector clocks: local dominates if all its entries >= remote's
        local_vc = local_memory.get("vector_clock", {})
        remote_vc = remote_memory.get("vector_clock", {})

        # Get all device IDs
        all_devices = set(local_vc.keys()) | set(remote_vc.keys())

        local_dominates = True
        remote_dominates = True

        for device in all_devices:
            local_val = local_vc.get(device, 0)
            remote_val = remote_vc.get(device, 0)

            if local_val < remote_val:
                local_dominates = False
            if remote_val < local_val:
                remote_dominates = False

        # If local dominates, local wins; if remote dominates, remote wins
        # If concurrent (neither dominates), use device_id as tiebreaker
        if local_dominates and not remote_dominates:
            winner = local_memory
            loser = remote_memory
        elif remote_dominates and not local_dominates:
            winner = remote_memory
            loser = local_memory
        else:
            # Concurrent or equal: tie-break by preferring the memory from the originating device
            # Use the memory that comes from its own device (local.device_id appears in local.vector_clock with higher value)
            local_device = local_memory.get("device_id", "")
            remote_device = remote_memory.get("device_id", "")

            local_self_clock = local_vc.get(local_device, 0)
            remote_self_clock = remote_vc.get(remote_device, 0)

            # Prefer the one with higher self-clock (more recent local edits)
            if local_self_clock > remote_self_clock:
                winner = local_memory
                loser = remote_memory
            elif remote_self_clock > local_self_clock:
                winner = remote_memory
                loser = local_memory
            else:
                # Equal self-clocks: use device_id as final tiebreaker (lower device_id wins for determinism)
                if local_device < remote_device:
                    winner = local_memory
                    loser = remote_memory
                else:
                    winner = remote_memory
                    loser = local_memory
    elif merge_strategy == "last-write-wins":
        # Compare timestamps
        if local_memory.get("updated_at", "") > remote_memory.get("updated_at", ""):
            winner = local_memory
            loser = remote_memory
        else:
            winner = remote_memory
            loser = local_memory
    else:
        # Default to local
        winner = local_memory
        loser = remote_memory

    # Log the merge decision
    import uuid

    merge_id = str(uuid.uuid4())
    logger.log_merge(
        merge_id=merge_id,
        resource_type=resource_type,
        resource_id=resource_id,
        merge_strategy=merge_strategy,
        winner_device_id=winner.get("device_id", "unknown"),
        loser_device_id=loser.get("device_id", "unknown"),
        winner_vector_clock=winner.get("vector_clock"),
        loser_vector_clock=loser.get("vector_clock"),
        conflict_reason="Concurrent modifications detected during sync",
        tenant_id=winner.get("tenant_id"),
        connection=connection,
    )

    return winner
