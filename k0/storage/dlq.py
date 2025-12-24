"""Dead letter queue persistence primitives - Async PostgreSQL."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, AsyncIterator

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg

from k0.obs.metrics import MetricsExporter


@dataclass(slots=True)
class DeadLetter:
    id: int | None
    wal_pos: int | None
    tenant_id: str
    space_id: str
    driver: str
    op_kind: str
    fingerprint: str
    payload: bytes
    reason: str
    retries: int
    requeue_seq: int
    first_failure_ts: str
    last_failure_ts: str
    state: str = "PENDING"


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


class DeadLetterQueue:
    """Store and replay dead-lettered outbox entries - PostgreSQL."""

    def __init__(self, *, metrics: MetricsExporter | None = None) -> None:
        """Initialize DLQ with optional metrics exporter."""
        self._metrics = metrics

    async def record(
        self,
        letter: DeadLetter,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record a dead letter entry.

        Args:
            letter: DeadLetter to persist
            connection: Optional existing connection

        Returns:
            The assigned dead letter id
        """
        insert_letter = replace(letter)
        state_value = insert_letter.state.upper()
        insert_letter.state = state_value

        requeue_start = time.perf_counter()

        async with _resolve_connection(connection) as conn:
            entry_id = await conn.fetchval(
                """
                INSERT INTO st_dlq (
                    wal_pos, tenant_id, space_id, driver, op_kind, fingerprint,
                    payload, reason, retries, requeue_seq, first_failure_ts,
                    last_failure_ts, state
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id
                """,
                insert_letter.wal_pos,
                insert_letter.tenant_id,
                insert_letter.space_id,
                insert_letter.driver,
                insert_letter.op_kind,
                insert_letter.fingerprint,
                insert_letter.payload,
                insert_letter.reason,
                insert_letter.retries,
                insert_letter.requeue_seq,
                insert_letter.first_failure_ts,
                insert_letter.last_failure_ts,
                state_value,
            )

        if entry_id is None:
            msg = "Failed to determine dead-letter id"
            raise RuntimeError(msg)

        insert_letter.id = int(entry_id)
        letter.id = int(entry_id)
        letter.state = state_value

        if self._metrics is not None:
            self._metrics.emit(
                "dlq_entries_by_state",
                1.0,
                state=state_value,
                driver=insert_letter.driver,
            )
            self._metrics.emit(
                "dlq_retry_attempts_total",
                float(insert_letter.retries),
                driver=insert_letter.driver,
            )
            requeue_latency = time.perf_counter() - requeue_start
            self._metrics.observe(
                "dlq_requeue_latency_seconds",
                requeue_latency,
                labels={"driver": insert_letter.driver, "state": state_value},
            )

        return int(entry_id)

    async def list_pending(
        self,
        limit: int = 100,
        *,
        state: str | None = "PENDING",
        tenant_id: str | None = None,
        space_id: str | None = None,
        driver: str | None = None,
        connection: asyncpg.Connection | None = None,
    ) -> list[DeadLetter]:
        """List dead letters with optional filters.

        Args:
            limit: Maximum number of entries to return
            state: Filter by state (default: PENDING, use "ALL" for all states)
            tenant_id: Optional tenant filter
            space_id: Optional space filter
            driver: Optional driver filter
            connection: Optional existing connection

        Returns:
            List of DeadLetter objects
        """
        async with _resolve_connection(connection) as conn:
            query = """
                SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, fingerprint,
                       payload, reason, retries, requeue_seq, first_failure_ts,
                       last_failure_ts, state
                FROM st_dlq
            """
            filters: list[str] = []
            params: list[object] = []
            param_idx = 1

            if state and state.upper() != "ALL":
                filters.append(f"state = ${param_idx}")
                params.append(state.upper())
                param_idx += 1
            if tenant_id:
                filters.append(f"tenant_id = ${param_idx}")
                params.append(tenant_id)
                param_idx += 1
            if space_id:
                filters.append(f"space_id = ${param_idx}")
                params.append(space_id)
                param_idx += 1
            if driver:
                filters.append(f"driver = ${param_idx}")
                params.append(driver)
                param_idx += 1

            if filters:
                query += " WHERE " + " AND ".join(filters)

            query += f" ORDER BY first_failure_ts ASC, id ASC LIMIT ${param_idx}"
            params.append(limit)

            rows = await conn.fetch(query, *params)

        return [
            DeadLetter(
                id=row["id"],
                wal_pos=row["wal_pos"],
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
                driver=row["driver"],
                op_kind=row["op_kind"],
                fingerprint=row["fingerprint"],
                payload=row["payload"],
                reason=row["reason"],
                retries=row["retries"],
                requeue_seq=row["requeue_seq"],
                first_failure_ts=str(row["first_failure_ts"]) if row["first_failure_ts"] else "",
                last_failure_ts=str(row["last_failure_ts"]) if row["last_failure_ts"] else "",
                state=row["state"],
            )
            for row in rows
        ]

    async def get(
        self,
        letter_id: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> DeadLetter | None:
        """Get a dead letter by ID.

        Args:
            letter_id: The dead letter ID
            connection: Optional existing connection

        Returns:
            DeadLetter if found, None otherwise
        """
        async with _resolve_connection(connection) as conn:
            row = await conn.fetchrow(
                """
                SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, fingerprint,
                       payload, reason, retries, requeue_seq, first_failure_ts,
                       last_failure_ts, state
                FROM st_dlq
                WHERE id = $1
                """,
                letter_id,
            )

        if row is None:
            return None

        return DeadLetter(
            id=row["id"],
            wal_pos=row["wal_pos"],
            tenant_id=row["tenant_id"],
            space_id=row["space_id"],
            driver=row["driver"],
            op_kind=row["op_kind"],
            fingerprint=row["fingerprint"],
            payload=row["payload"],
            reason=row["reason"],
            retries=row["retries"],
            requeue_seq=row["requeue_seq"],
            first_failure_ts=str(row["first_failure_ts"]) if row["first_failure_ts"] else "",
            last_failure_ts=str(row["last_failure_ts"]) if row["last_failure_ts"] else "",
            state=row["state"],
        )

    async def mark_requeued(
        self,
        letter_id: int,
        *,
        requeue_seq: int | None = None,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Mark DLQ entry as requeued with safe requeue_seq.

        If requeue_seq not provided, compute next safe value
        by querying MAX(requeue_seq) from outbox to prevent collisions.
        """
        async with _resolve_connection(connection) as conn:
            if requeue_seq is None:
                requeue_seq = await self._get_next_requeue_seq(conn)

            result = await conn.execute(
                "UPDATE st_dlq SET state = 'REQUEUED', requeue_seq = $1 WHERE id = $2",
                requeue_seq,
                letter_id,
            )
            # asyncpg returns "UPDATE N" string
            if result == "UPDATE 0":
                msg = f"Dead-letter entry {letter_id} not found"
                raise KeyError(msg)

    async def _get_next_requeue_seq(
        self,
        connection: asyncpg.Connection,
    ) -> int:
        """Get next safe requeue_seq value.

        Query MAX(requeue_seq) from st_outbox and increment by 1
        to ensure no collision with existing outbox entries.
        """
        max_seq = await connection.fetchval("SELECT COALESCE(MAX(requeue_seq), 0) FROM st_outbox")
        return int(max_seq) + 1 if max_seq is not None else 1

    async def purge(
        self,
        letter_id: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> bool:
        """Mark a dead letter as quarantined.

        Args:
            letter_id: The dead letter ID to purge
            connection: Optional existing connection

        Returns:
            True if entry was found and updated, False otherwise
        """
        async with _resolve_connection(connection) as conn:
            result = await conn.execute(
                "UPDATE st_dlq SET state = 'QUARANTINED' WHERE id = $1",
                letter_id,
            )
            return result != "UPDATE 0"
