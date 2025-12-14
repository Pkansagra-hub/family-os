"""Dead letter queue persistence primitives."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterator, List, Optional

from k0.obs.metrics import MetricsExporter
from k0.uow.connection_pool import connection_scope


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


@contextmanager
def _resolve_connection(
    connection: sqlite3.Connection | None,
) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
        return

    with connection_scope() as pooled_connection:
        yield pooled_connection
        pooled_connection.commit()


class DeadLetterQueue:
    """Store and replay dead-lettered outbox entries."""

    def __init__(self, *, metrics: MetricsExporter | None = None) -> None:
        """Gap 44: Initialize DLQ with optional metrics exporter."""
        self._metrics = metrics

    def record(self, letter: DeadLetter, *, connection: sqlite3.Connection | None = None) -> int:
        insert_letter = replace(letter)
        state_value = insert_letter.state.upper()
        insert_letter.state = state_value

        # Gap 44: Track DLQ entry creation
        requeue_start = time.perf_counter()

        with _resolve_connection(connection) as conn:
            cursor = conn.execute(
                (
                    "INSERT INTO st_dlq (wal_pos, tenant_id, space_id, driver, op_kind, fingerprint, payload, reason, "
                    "retries, requeue_seq, first_failure_ts, last_failure_ts, state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
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
                ),
            )
            row_id = cursor.lastrowid
            if row_id is None:  # pragma: no cover - SQLite always returns rowid
                msg = "Failed to determine dead-letter id"
                raise RuntimeError(msg)
            entry_id = int(row_id)
            insert_letter.id = entry_id
            letter.id = entry_id
            letter.state = state_value

            # Gap 44: Emit DLQ metrics
            if self._metrics is not None:
                # Track entries by state
                self._metrics.emit(
                    "dlq_entries_by_state",
                    1.0,
                    state=state_value,
                    driver=insert_letter.driver,
                )
                # Track retry attempts
                self._metrics.emit(
                    "dlq_retry_attempts_total",
                    float(insert_letter.retries),
                    driver=insert_letter.driver,
                )
                # Track requeue latency
                requeue_latency = time.perf_counter() - requeue_start
                self._metrics.observe(
                    "dlq_requeue_latency_seconds",
                    requeue_latency,
                    labels={"driver": insert_letter.driver, "state": state_value},
                )

            return entry_id

    def list_pending(
        self,
        limit: int = 100,
        *,
        state: str | None = "PENDING",
        tenant_id: str | None = None,
        space_id: str | None = None,
        driver: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> List[DeadLetter]:
        with _resolve_connection(connection) as conn:
            query = (
                "SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, fingerprint, payload, reason, "
                "retries, requeue_seq, first_failure_ts, last_failure_ts, state FROM st_dlq"
            )
            filters: list[str] = []
            parameters: list[object] = []
            if state and state.upper() != "ALL":
                filters.append("state = ?")
                parameters.append(state.upper())
            if tenant_id:
                filters.append("tenant_id = ?")
                parameters.append(tenant_id)
            if space_id:
                filters.append("space_id = ?")
                parameters.append(space_id)
            if driver:
                filters.append("driver = ?")
                parameters.append(driver)
            if filters:
                query += " WHERE " + " AND ".join(filters)
            query += " ORDER BY first_failure_ts ASC, id ASC LIMIT ?"
            parameters.append(limit)
            rows = conn.execute(query, parameters).fetchall()
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
                    first_failure_ts=row["first_failure_ts"],
                    last_failure_ts=row["last_failure_ts"],
                    state=row["state"],
                )
                for row in rows
            ]

    def get(
        self,
        letter_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Optional[DeadLetter]:
        with _resolve_connection(connection) as conn:
            row = conn.execute(
                (
                    "SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, fingerprint, payload, reason, "
                    "retries, requeue_seq, first_failure_ts, last_failure_ts, state FROM st_dlq WHERE id = ?"
                ),
                (letter_id,),
            ).fetchone()
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
                first_failure_ts=row["first_failure_ts"],
                last_failure_ts=row["last_failure_ts"],
                state=row["state"],
            )

    def mark_requeued(
        self,
        letter_id: int,
        *,
        requeue_seq: int | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        """Mark DLQ entry as requeued with safe requeue_seq.

        Gap 23: If requeue_seq not provided, compute next safe value
        by querying MAX(requeue_seq) from outbox to prevent collisions.
        """
        with _resolve_connection(connection) as conn:
            # Gap 23: Prevent requeue_seq collision with outbox
            if requeue_seq is None:
                requeue_seq = self._get_next_requeue_seq(conn)

            cursor = conn.execute(
                "UPDATE st_dlq SET state='REQUEUED', requeue_seq=? WHERE id=?",
                (requeue_seq, letter_id),
            )
            if cursor.rowcount == 0:
                msg = f"Dead-letter entry {letter_id} not found"
                raise KeyError(msg)

    def _get_next_requeue_seq(self, connection: sqlite3.Connection) -> int:
        """Gap 23: Get next safe requeue_seq value.

        Query MAX(requeue_seq) from st_outbox and increment by 1
        to ensure no collision with existing outbox entries.
        """
        row = connection.execute(
            "SELECT COALESCE(MAX(requeue_seq), 0) as max_seq FROM st_outbox"
        ).fetchone()
        max_seq = row["max_seq"] if row else 0
        return int(max_seq) + 1

    def purge(
        self,
        letter_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        with _resolve_connection(connection) as conn:
            cursor = conn.execute(
                "UPDATE st_dlq SET state='QUARANTINED' WHERE id=?",
                (letter_id,),
            )
            return cursor.rowcount > 0
