"""Persistence adapter for policy obligation log (ADR-0089)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator

from k0.uow.connection_pool import connection_scope


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


class ObligationStore:
    """Storage helper for persisting and fetching obligation log entries."""

    def save(
        self,
        record: ObligationRecord,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        with _resolve_connection(connection) as conn:
            cursor = conn.execute(
                (
                    "INSERT INTO st_obligation_log (wal_pos, obligation, details_json, commit_ts, tenant_id, space_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)"
                ),
                (
                    record.wal_pos,
                    record.obligation,
                    record.details_json,
                    record.commit_ts,
                    record.tenant_id,
                    record.space_id,
                ),
            )
            inserted_id = cursor.lastrowid
            return int(inserted_id) if inserted_id is not None else -1

    def bulk_save(
        self,
        records: Iterable[ObligationRecord],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        with _resolve_connection(connection) as conn:
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
            if tuples:
                conn.executemany(
                    (
                        "INSERT INTO st_obligation_log (wal_pos, obligation, details_json, commit_ts, tenant_id, space_id) "
                        "VALUES (?, ?, ?, ?, ?, ?)"
                    ),
                    tuples,
                )

    def fetch_by_wal_pos(
        self,
        wal_pos: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[ObligationRecord]:
        with _resolve_connection(connection) as conn:
            rows = conn.execute(
                (
                    "SELECT id, wal_pos, obligation, details_json, commit_ts, tenant_id, space_id "
                    "FROM st_obligation_log WHERE wal_pos = ? ORDER BY id ASC"
                ),
                (wal_pos,),
            ).fetchall()
            return [
                ObligationRecord(
                    id=row["id"],
                    wal_pos=row["wal_pos"],
                    obligation=row["obligation"],
                    details_json=row["details_json"],
                    commit_ts=row["commit_ts"],
                    tenant_id=row["tenant_id"],
                    space_id=row["space_id"],
                )
                for row in rows
            ]

    def fetch_recent(
        self,
        *,
        limit: int,
        connection: sqlite3.Connection | None = None,
    ) -> list[ObligationRecord]:
        with _resolve_connection(connection) as conn:
            rows = conn.execute(
                (
                    "SELECT id, wal_pos, obligation, details_json, commit_ts, tenant_id, space_id "
                    "FROM st_obligation_log ORDER BY id DESC LIMIT ?"
                ),
                (limit,),
            ).fetchall()
            return [
                ObligationRecord(
                    id=row["id"],
                    wal_pos=row["wal_pos"],
                    obligation=row["obligation"],
                    details_json=row["details_json"],
                    commit_ts=row["commit_ts"],
                    tenant_id=row["tenant_id"],
                    space_id=row["space_id"],
                )
                for row in rows
            ]


__all__ = ["ObligationRecord", "ObligationStore"]
