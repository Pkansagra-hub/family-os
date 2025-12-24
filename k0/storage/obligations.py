"""Persistence adapter for policy obligation log (ADR-0089) - Async PostgreSQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator, Iterable

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg


@dataclass(slots=True)
class ObligationRecord:
    """Materialised obligation emitted by the Policy Enforcement Module (PEM)."""

    wal_pos: int
    obligation: str
    commit_ts: str
    tenant_id: str
    space_id: str
    details_json: str | None = None
    id: int | None = None


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


class ObligationStore:
    """Storage helper for persisting and fetching obligation log entries - PostgreSQL."""

    async def save(
        self,
        record: ObligationRecord,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Save an obligation record.

        Args:
            record: ObligationRecord to persist
            connection: Optional existing connection

        Returns:
            The assigned obligation id
        """
        async with _resolve_connection(connection) as conn:
            inserted_id = await conn.fetchval(
                """
                INSERT INTO st_obligation_log (
                    wal_pos, obligation, details_json, commit_ts, tenant_id, space_id
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                record.wal_pos,
                record.obligation,
                record.details_json,
                record.commit_ts,
                record.tenant_id,
                record.space_id,
            )
        return int(inserted_id) if inserted_id is not None else -1

    async def bulk_save(
        self,
        records: Iterable[ObligationRecord],
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Bulk save multiple obligation records.

        Args:
            records: Iterable of ObligationRecord to persist
            connection: Optional existing connection
        """
        tuples = [
            (
                record.wal_pos,
                record.obligation,
                record.details_json,
                record.commit_ts,
                record.tenant_id,
                record.space_id,
            )
            for record in records
        ]
        if not tuples:
            return

        async with _resolve_connection(connection) as conn:
            await conn.executemany(
                """
                INSERT INTO st_obligation_log (
                    wal_pos, obligation, details_json, commit_ts, tenant_id, space_id
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                tuples,
            )

    async def fetch_by_wal_pos(
        self,
        wal_pos: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> list[ObligationRecord]:
        """Fetch obligation records by WAL position.

        Args:
            wal_pos: The WAL position to query
            connection: Optional existing connection

        Returns:
            List of ObligationRecord objects
        """
        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(
                """
                SELECT id, wal_pos, obligation, details_json, commit_ts, tenant_id, space_id
                FROM st_obligation_log
                WHERE wal_pos = $1
                ORDER BY id ASC
                """,
                wal_pos,
            )

        return [
            ObligationRecord(
                id=row["id"],
                wal_pos=row["wal_pos"],
                obligation=row["obligation"],
                details_json=row["details_json"],
                commit_ts=str(row["commit_ts"]) if row["commit_ts"] else "",
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
            )
            for row in rows
        ]

    async def fetch_recent(
        self,
        *,
        limit: int,
        connection: asyncpg.Connection | None = None,
    ) -> list[ObligationRecord]:
        """Fetch most recent obligation records.

        Args:
            limit: Maximum number of records to return
            connection: Optional existing connection

        Returns:
            List of ObligationRecord objects ordered by id DESC
        """
        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(
                """
                SELECT id, wal_pos, obligation, details_json, commit_ts, tenant_id, space_id
                FROM st_obligation_log
                ORDER BY id DESC
                LIMIT $1
                """,
                limit,
            )

        return [
            ObligationRecord(
                id=row["id"],
                wal_pos=row["wal_pos"],
                obligation=row["obligation"],
                details_json=row["details_json"],
                commit_ts=str(row["commit_ts"]) if row["commit_ts"] else "",
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
            )
            for row in rows
        ]


__all__ = ["ObligationRecord", "ObligationStore"]
