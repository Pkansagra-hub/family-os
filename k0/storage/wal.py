"""Write-ahead log adapter - Async PostgreSQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, AsyncIterator

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg


def _format_timestamp(value: str | datetime | None) -> str | None:
    """Convert datetime to string for TEXT columns in PostgreSQL."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(slots=True)
class WalEntry:
    """Domain representation of a WAL row (V1 with full envelope integrity)."""

    tenant_id: str
    space_id: str
    topic: str
    envelope_json: str
    schema_uri: str
    schema_version: str
    device_id: str
    commit_ts: str
    body: bytes | None = None
    payload_sha256: str | None = None
    idem_key: str | None = None
    redacted_body_json: str | None = None
    position: int | None = None

    # V1 NEW: Envelope integrity tracking
    envelope_sha256: str | None = None

    # V1 NEW: Time tracking
    ingested_at: str | None = None
    clock_skew_ms: int | None = None

    # V1.3 NEW: Policy stamp (attached by PolicyEvaluator)
    policy_stamp_json: str | None = None

    # V1.3 NEW: Location privacy fields
    location_geohash: str | None = None
    location_precision_m: int | None = None


@dataclass(slots=True)
class WalBacklogStats:
    """Aggregate backlog information for a WAL topic scope."""

    pending_events: int
    latest_position: int | None
    latest_commit_ts: str | None


@asynccontextmanager
async def _resolve_connection(
    connection: asyncpg.Connection | None,
) -> AsyncIterator[asyncpg.Connection]:
    """Resolve connection from provided or pool."""
    if connection is not None:
        yield connection
        return

    async with connection_scope() as pooled_connection:
        yield pooled_connection


class WriteAheadLog:
    """Abstraction over the `st_wal` PostgreSQL table."""

    def __init__(self, *, metrics: Any | None = None) -> None:
        """Initialize with optional metrics exporter."""
        self._metrics = metrics

    async def append(
        self,
        entry: WalEntry,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Append entry to the write-ahead log.

        Args:
            entry: WalEntry to persist
            connection: Optional existing connection

        Returns:
            The assigned WAL position (pos)
        """
        insert_entry = replace(entry)

        # Convert datetime to string for TEXT columns
        commit_ts = _format_timestamp(insert_entry.commit_ts)
        ingested_at = _format_timestamp(insert_entry.ingested_at)

        async with _resolve_connection(connection) as conn:
            position = await conn.fetchval(
                """
                INSERT INTO st_wal (
                    tenant_id, space_id, topic, envelope_json, body,
                    redacted_body_json, payload_sha256, schema_uri, schema_version,
                    idem_key, device_id, commit_ts,
                    envelope_sha256, ingested_at, clock_skew_ms, policy_stamp_json,
                    location_geohash, location_precision_m
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18
                ) RETURNING pos
                """,
                insert_entry.tenant_id,
                insert_entry.space_id,
                insert_entry.topic,
                insert_entry.envelope_json,
                insert_entry.body,
                insert_entry.redacted_body_json,
                insert_entry.payload_sha256,
                insert_entry.schema_uri,
                insert_entry.schema_version,
                insert_entry.idem_key,
                insert_entry.device_id,
                commit_ts,
                insert_entry.envelope_sha256,
                ingested_at,
                insert_entry.clock_skew_ms,
                insert_entry.policy_stamp_json,
                insert_entry.location_geohash,
                insert_entry.location_precision_m,
            )

        if position is None:
            msg = "Failed to determine WAL position"
            raise RuntimeError(msg)

        insert_entry.position = position

        if self._metrics is not None:
            try:
                self._metrics.set_gauge("wal_current_position", float(position))
            except Exception:  # noqa: BLE001
                pass

        return position

    async def read_from(
        self,
        position: int,
        limit: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> list[WalEntry]:
        """Read WAL entries after a given position.

        Args:
            position: Read entries with pos > this value
            limit: Maximum number of entries to return
            connection: Optional existing connection

        Returns:
            List of WalEntry objects ordered by position
        """
        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(
                """
                SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256,
                       redacted_body_json, schema_uri, schema_version, idem_key, device_id, commit_ts,
                       envelope_sha256, ingested_at, clock_skew_ms, policy_stamp_json,
                       location_geohash, location_precision_m
                FROM st_wal
                WHERE pos > $1
                ORDER BY pos ASC
                LIMIT $2
                """,
                position,
                limit,
            )

        return [
            WalEntry(
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
                topic=row["topic"],
                envelope_json=row["envelope_json"],
                schema_uri=row["schema_uri"],
                schema_version=row["schema_version"],
                device_id=row["device_id"],
                commit_ts=str(row["commit_ts"]) if row["commit_ts"] else "",
                body=row["body"],
                redacted_body_json=row["redacted_body_json"],
                payload_sha256=row["payload_sha256"],
                idem_key=row["idem_key"],
                position=row["pos"],
                envelope_sha256=row["envelope_sha256"],
                ingested_at=str(row["ingested_at"]) if row["ingested_at"] else None,
                clock_skew_ms=row["clock_skew_ms"],
                policy_stamp_json=row["policy_stamp_json"],
                location_geohash=row["location_geohash"],
                location_precision_m=row["location_precision_m"],
            )
            for row in rows
        ]

    async def fsync(
        self,
        *,
        connection: asyncpg.Connection | None = None,
        mode: str | None = None,
        metrics_exporter: Any | None = None,
    ) -> int | None:
        """Ensure WAL durability by checking current WAL LSN.

        PostgreSQL handles durability through its own WAL mechanism.
        The mode and metrics_exporter parameters are accepted for API
        compatibility with UnitOfWork but are not used for PostgreSQL.

        Returns:
            Current WAL LSN as integer, or None if not available
        """
        # PostgreSQL doesn't need mode - it handles durability natively
        _ = mode
        _ = metrics_exporter
        async with _resolve_connection(connection) as conn:
            lsn = await conn.fetchval("SELECT pg_current_wal_lsn()")
            if lsn is not None:
                lsn_numeric = await conn.fetchval(
                    "SELECT pg_wal_lsn_diff($1, '0/0')",
                    lsn,
                )
                return int(lsn_numeric) if lsn_numeric else None
            return None

    async def backlog_stats(
        self,
        *,
        tenant_id: str,
        space_id: str,
        topic: str,
        offset: int,
        connection: asyncpg.Connection | None = None,
    ) -> WalBacklogStats:
        """Return backlog statistics beyond a subscriber's acknowledged offset."""
        async with _resolve_connection(connection) as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS pending,
                    MAX(pos) AS latest_pos,
                    MAX(commit_ts) AS latest_ts
                FROM st_wal
                WHERE tenant_id = $1
                  AND space_id = $2
                  AND topic = $3
                  AND pos > $4
                """,
                tenant_id,
                space_id,
                topic,
                offset,
            )

        pending = int(row["pending"]) if row and row["pending"] is not None else 0
        latest_pos = row["latest_pos"] if row else None
        latest_ts = str(row["latest_ts"]) if row and row["latest_ts"] else None

        return WalBacklogStats(
            pending_events=pending,
            latest_position=latest_pos,
            latest_commit_ts=latest_ts,
        )
