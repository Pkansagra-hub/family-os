"""Outbox adapter responsible for async driver intents."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterator, List

from k0.obs.metrics import MetricsExporter
from k0.uow.connection_pool import connection_scope


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


class OutboxStore:
    """Manage creation and consumption of outbox entries."""

    def __init__(self, *, metrics: MetricsExporter | None = None) -> None:
        self._metrics = metrics

    def attach_metrics(self, metrics: MetricsExporter | None) -> None:
        """Attach or replace the metrics exporter used for gauges."""

        self._metrics = metrics

    def enqueue(
        self,
        entry: OutboxEntry,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        insert_entry = replace(entry)
        with _resolve_connection(connection) as conn:
            cursor = conn.execute(
                (
                    "INSERT INTO st_outbox (wal_pos, tenant_id, space_id, driver, op_kind, payload, "
                    "fingerprint, requeue_seq, retries, last_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
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
                ),
            )
            row_id = cursor.lastrowid
            if (
                row_id is None
            ):  # pragma: no cover - SQLite guarantees rowid, defensive guard
                msg = "Failed to determine outbox entry id"
                raise RuntimeError(msg)
            entry_id = int(row_id)
            insert_entry.id = entry_id
            entry.id = entry_id
            self._update_pending_metrics(conn, insert_entry.driver)
            return entry_id

    def dequeue_batch(
        self,
        driver: str,
        limit: int = 128,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> List[OutboxEntry]:
        with _resolve_connection(connection) as conn:
            rows = conn.execute(
                (
                    "SELECT id, wal_pos, tenant_id, space_id, driver, op_kind, payload, fingerprint, "
                    "requeue_seq, retries, last_error FROM st_outbox WHERE driver=? ORDER BY requeue_seq ASC, id ASC LIMIT ?"
                ),
                (driver, limit),
            ).fetchall()
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
                )
                for row in rows
            ]

    def mark_applied(
        self,
        entry_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        with _resolve_connection(connection) as conn:
            driver: str | None = None
            if self._metrics is not None:
                row = conn.execute(
                    "SELECT driver FROM st_outbox WHERE id=?",
                    (entry_id,),
                ).fetchone()
                if row is not None:
                    driver = row["driver"]

            conn.execute("DELETE FROM st_outbox WHERE id=?", (entry_id,))
            self._update_pending_metrics(conn, driver)

    def record_failure(
        self,
        entry: OutboxEntry,
        *,
        retries: int,
        requeue_seq: int,
        last_error: str,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if entry.id is None:
            msg = "outbox entry must be persisted before recording failure"
            raise ValueError(msg)

        with _resolve_connection(connection) as conn:
            conn.execute(
                (
                    "UPDATE st_outbox SET retries=?, requeue_seq=?, last_error=? "
                    "WHERE id=?"
                ),
                (retries, requeue_seq, last_error, entry.id),
            )

        entry.retries = retries
        entry.requeue_seq = requeue_seq
        entry.last_error = last_error

    def _update_pending_metrics(
        self,
        connection: sqlite3.Connection,
        driver: str | None,
    ) -> None:
        metrics = self._metrics
        if metrics is None:
            return

        total_row = connection.execute(
            "SELECT COUNT(*) AS pending FROM st_outbox"
        ).fetchone()
        total = (
            int(total_row["pending"])
            if total_row is not None and total_row["pending"] is not None
            else 0
        )
        metrics.set_gauge(
            "outbox_pending_total",
            float(total),
            driver="*",
        )

        if not driver:
            return

        driver_row = connection.execute(
            "SELECT COUNT(*) AS pending FROM st_outbox WHERE driver=?",
            (driver,),
        ).fetchone()
        driver_total = (
            int(driver_row["pending"])
            if driver_row is not None and driver_row["pending"] is not None
            else 0
        )
        metrics.set_gauge(
            "outbox_pending_total",
            float(driver_total),
            driver=driver,
        )
