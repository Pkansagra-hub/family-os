"""Subscriber offset storage."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from k0.uow.connection_pool import connection_scope


@dataclass(slots=True)
class Offset:
    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int
    updated_ts: str


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


class OffsetStore:
    """Persistence surface for subscriber offsets."""

    def __init__(self) -> None:
        # Gap 32: RLock protects concurrent offset read/write operations
        self._lock = threading.RLock()

    def upsert(self, record: Offset, *, connection: sqlite3.Connection | None = None) -> None:
        # Gap 32: Serialize concurrent offset updates with RLock
        with self._lock:
            with _resolve_connection(connection) as conn:
                conn.execute(
                    (
                        "INSERT INTO st_offsets (subscriber_id, topic, space_id, tenant_id, offset, updated_ts) "
                        "VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(subscriber_id, topic, space_id, tenant_id) DO UPDATE SET "
                        "offset=excluded.offset, updated_ts=excluded.updated_ts"
                    ),
                    (
                        record.subscriber_id,
                        record.topic,
                        record.space_id,
                        record.tenant_id,
                        record.offset,
                        record.updated_ts,
                    ),
                )

    def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Offset | None:
        # Gap 32: Serialize concurrent offset reads with RLock
        with self._lock:
            with _resolve_connection(connection) as conn:
                row = conn.execute(
                    (
                        "SELECT subscriber_id, topic, space_id, tenant_id, offset, updated_ts "
                        "FROM st_offsets WHERE subscriber_id=? AND topic=? AND space_id=? AND tenant_id=?"
                    ),
                    (subscriber_id, topic, space_id, tenant_id),
                ).fetchone()
                if row is None:
                    return None
                return Offset(
                    subscriber_id=row["subscriber_id"],
                    topic=row["topic"],
                    space_id=row["space_id"],
                    tenant_id=row["tenant_id"],
                    offset=row["offset"],
                    updated_ts=row["updated_ts"],
                )
