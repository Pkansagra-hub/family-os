"""Outbox adapter responsible for async driver intents - Async PostgreSQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncIterator

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg

from k0.obs.metrics import MetricsExporter


@dataclass(slots=True)
class OutboxEntry:
    id: int | None
    wal_pos: int
    tenant_id: str
    space_id: str
    driver: str
    op_kind: str
    payload: bytes
    fingerprint: str
    requeue_seq: int
    retries: int
    last_error: str | None = None
    next_attempt_ts: str | None = None
    backoff_exp: int = 0
    status: str = "PENDING"


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


class OutboxStore:
    """Manage creation and consumption of outbox entries - PostgreSQL."""

    def __init__(self, *, metrics: MetricsExporter | None = None) -> None:
        self._metrics = metrics

    def attach_metrics(self, metrics: MetricsExporter | None) -> None:
        """Attach or replace the metrics exporter used for gauges."""
        self._metrics = metrics

    async def enqueue(
        self,
        entry: OutboxEntry,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Enqueue an entry to the outbox.

        Args:
            entry: OutboxEntry to persist
            connection: Optional existing connection

        Returns:
            The assigned outbox entry id
        """
        insert_entry = replace(entry)

        async with _resolve_connection(connection) as conn:
            entry_id = await conn.fetchval(
                """
                INSERT INTO st_outbox (
                    wal_pos, tenant_id, space_id, driver, op_kind, payload,
                    fingerprint, requeue_seq, retries, last_error,
                    next_attempt_ts, backoff_exp, status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id
                """,
                insert_entry.wal_pos,
                insert_entry.tenant_id,
                insert_entry.space_id,
                insert_entry.driver,
                insert_entry.op_kind,
                insert_entry.payload,
                insert_entry.fingerprint,
                insert_entry.requeue_seq,
                insert_entry.retries,
                insert_entry.last_error,
                insert_entry.next_attempt_ts,
                insert_entry.backoff_exp,
                insert_entry.status,
            )

        if entry_id is None:
            msg = "Failed to determine outbox entry id"
            raise RuntimeError(msg)

        insert_entry.id = int(entry_id)
        entry.id = int(entry_id)
        await self._update_pending_metrics(connection, insert_entry.driver)
        return int(entry_id)

    async def enqueue_async(
        self,
        entry: OutboxEntry,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Alias for enqueue() to support UoW async flush pattern."""
        return await self.enqueue(entry, connection=connection)

    async def dequeue_batch(
        self,
        driver: str,
        limit: int = 128,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> list[OutboxEntry]:
        """Dequeue batch of entries (legacy method - no backoff awareness).

        For new code, use dequeue_ready_batch() which respects next_attempt_ts.
        """
        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(
                """
                SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, payload, fingerprint,
                       requeue_seq, retries, last_error, next_attempt_ts, backoff_exp, status
                FROM st_outbox
                WHERE driver = $1
                ORDER BY requeue_seq ASC, id ASC
                LIMIT $2
                """,
                driver,
                limit,
            )

        return [
            OutboxEntry(
                id=row["id"],
                wal_pos=row["wal_pos"],
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
                driver=row["driver"],
                op_kind=row["op_kind"],
                payload=row["payload"],
                fingerprint=row["fingerprint"],
                requeue_seq=row["requeue_seq"],
                retries=row["retries"],
                last_error=row["last_error"],
                next_attempt_ts=str(row["next_attempt_ts"]) if row["next_attempt_ts"] else None,
                backoff_exp=row["backoff_exp"] if row["backoff_exp"] is not None else 0,
                status=row["status"] if row["status"] else "PENDING",
            )
            for row in rows
        ]

    async def dequeue_ready_batch(
        self,
        driver: str,
        limit: int = 128,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> list[OutboxEntry]:
        """Dequeue entries WHERE next_attempt_ts IS NULL OR next_attempt_ts <= NOW().

        This method respects exponential backoff by only returning entries that are
        ready to be retried based on their next_attempt_ts timestamp.

        Parameters
        ----------
        driver : str
            Driver alias to filter by
        limit : int
            Maximum number of entries to return (default: 128)
        connection : asyncpg.Connection, optional
            Database connection (uses connection pool if not provided)

        Returns
        -------
        list[OutboxEntry]
            Entries ready for processing (respects backoff timing)
        """
        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(
                """
                SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, payload, fingerprint,
                       requeue_seq, retries, last_error, next_attempt_ts, backoff_exp, status
                FROM st_outbox
                WHERE driver = $1
                  AND status = 'PENDING'
                  AND (next_attempt_ts IS NULL OR next_attempt_ts <= $2)
                ORDER BY id ASC
                LIMIT $3
                """,
                driver,
                now,
                limit,
            )

        return [
            OutboxEntry(
                id=row["id"],
                wal_pos=row["wal_pos"],
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
                driver=row["driver"],
                op_kind=row["op_kind"],
                payload=row["payload"],
                fingerprint=row["fingerprint"],
                requeue_seq=row["requeue_seq"],
                retries=row["retries"],
                last_error=row["last_error"],
                next_attempt_ts=str(row["next_attempt_ts"]) if row["next_attempt_ts"] else None,
                backoff_exp=row["backoff_exp"] if row["backoff_exp"] is not None else 0,
                status=row["status"] if row["status"] else "PENDING",
            )
            for row in rows
        ]

    async def mark_applied(
        self,
        entry_id: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Mark an entry as applied and remove from outbox."""
        driver: str | None = None

        async with _resolve_connection(connection) as conn:
            if self._metrics is not None:
                row = await conn.fetchrow(
                    "SELECT driver FROM st_outbox WHERE id = $1",
                    entry_id,
                )
                if row is not None:
                    driver = row["driver"]

            await conn.execute("DELETE FROM st_outbox WHERE id = $1", entry_id)

        await self._update_pending_metrics(connection, driver)

    async def record_failure(
        self,
        entry: OutboxEntry,
        *,
        retries: int,
        requeue_seq: int,
        last_error: str,
        next_attempt_ts: datetime | None = None,
        backoff_exp: int = 0,
        status: str = "PENDING",
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Record a failure for an outbox entry with backoff information."""
        if entry.id is None:
            msg = "outbox entry must be persisted before recording failure"
            raise ValueError(msg)

        # Convert datetime to ISO string for TEXT column
        next_attempt_ts_str = next_attempt_ts.isoformat() if next_attempt_ts else None

        async with _resolve_connection(connection) as conn:
            await conn.execute(
                """
                UPDATE st_outbox
                SET retries = $1, requeue_seq = $2, last_error = $3,
                    next_attempt_ts = $4, backoff_exp = $5, status = $6
                WHERE id = $7
                """,
                retries,
                requeue_seq,
                last_error,
                next_attempt_ts_str,
                backoff_exp,
                status,
                entry.id,
            )

        entry.retries = retries
        entry.requeue_seq = requeue_seq
        entry.last_error = last_error
        entry.next_attempt_ts = next_attempt_ts_str
        entry.backoff_exp = backoff_exp
        entry.status = status

    async def _update_pending_metrics(
        self,
        connection: asyncpg.Connection | None,
        driver: str | None,
    ) -> None:
        """Update pending metrics gauges."""
        metrics = self._metrics
        if metrics is None:
            return

        async with _resolve_connection(connection) as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM st_outbox")
            total_count = int(total) if total is not None else 0
            metrics.set_gauge(
                "outbox_pending_total",
                float(total_count),
                driver="*",
            )

            if not driver:
                return

            driver_count = await conn.fetchval(
                "SELECT COUNT(*) FROM st_outbox WHERE driver = $1",
                driver,
            )
            driver_total = int(driver_count) if driver_count is not None else 0
            metrics.set_gauge(
                "outbox_pending_total",
                float(driver_total),
                driver=driver,
            )
