"""
k1.bus.outbox.sqlite_outbox -- SQLite WAL-backed durable outbox (P6.13).

Stores envelopes for durable topics so that subscribers can replay any
un-acked envelope after a process restart.  The bus appends an envelope
to the outbox BEFORE dispatching to handlers; each durable subscription
acks its envelope_id after the handler returns successfully.  On bus
startup, ``replay_unacked()`` re-emits envelopes whose ``envelope_id``
is greater than the consumer's last_acked_envelope_id.

Schema::

    CREATE TABLE envelopes (
        envelope_id INTEGER PRIMARY KEY,
        topic       TEXT NOT NULL,
        payload     BLOB NOT NULL,
        priority    INTEGER NOT NULL DEFAULT 1,
        created_ns  INTEGER NOT NULL,
        request_id  TEXT NOT NULL DEFAULT '',
        session_id  TEXT NOT NULL DEFAULT '',
        deleted     INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX idx_envelopes_topic ON envelopes(topic, envelope_id);

    CREATE TABLE acks (
        consumer_id            TEXT NOT NULL,
        topic                  TEXT NOT NULL,
        last_acked_envelope_id INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (consumer_id, topic)
    );

Concurrency:
    SQLite is opened in WAL mode for concurrent readers.  A single
    ``threading.Lock`` serialises writes from the bus's publish path
    (the sqlite3 module's GIL release lets other threads read while
    one thread writes).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from k1.bus.envelope import Envelope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxRecord:
    """Outbox row hydrated back into an Envelope-friendly shape."""

    envelope_id: int
    topic: str
    payload: bytes
    priority: int
    created_ns: int
    request_id: str
    session_id: str

    def to_envelope(self) -> Envelope:
        """Rebuild an :class:`Envelope` (sequence is reset to 0 on replay)."""
        return Envelope(
            topic=self.topic,
            payload=self.payload,
            priority=self.priority,
            request_id=self.request_id,
            session_id=self.session_id,
            envelope_id=self.envelope_id,
            created_ns=self.created_ns,
        )


class BusOutbox:
    """
    SQLite WAL-backed envelope store for durable topics.

    Thread-safe via an internal lock around writes.  Reads use
    short-lived connections to avoid holding the lock across the
    handler dispatch path.
    """

    _SCHEMA = (
        """
        CREATE TABLE IF NOT EXISTS envelopes (
            envelope_id INTEGER PRIMARY KEY,
            topic       TEXT NOT NULL,
            payload     BLOB NOT NULL,
            priority    INTEGER NOT NULL DEFAULT 1,
            created_ns  INTEGER NOT NULL,
            request_id  TEXT NOT NULL DEFAULT '',
            session_id  TEXT NOT NULL DEFAULT '',
            deleted     INTEGER NOT NULL DEFAULT 0
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_envelopes_topic ON envelopes(topic, envelope_id)",
        """
        CREATE TABLE IF NOT EXISTS acks (
            consumer_id            TEXT NOT NULL,
            topic                  TEXT NOT NULL,
            last_acked_envelope_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (consumer_id, topic)
        )
        """,
    )

    def __init__(self, path: str | Path) -> None:
        self._path = str(Path(path))
        self._lock = threading.Lock()
        self._closed = False
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        # Ensure parent directory exists.
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                for stmt in self._SCHEMA:
                    conn.execute(stmt)
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Writes (bus.publish path)
    # ------------------------------------------------------------------

    def append(self, envelope: Envelope) -> None:
        """
        Append an envelope to the outbox.  Idempotent on envelope_id
        (INSERT OR IGNORE) so re-ingest of an already-stored envelope
        is a no-op.
        """
        if self._closed:
            raise RuntimeError("BusOutbox is closed")
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO envelopes "
                    "(envelope_id, topic, payload, priority, created_ns, request_id, session_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope.envelope_id,
                        envelope.topic,
                        bytes(envelope.payload),
                        envelope.priority,
                        envelope.created_ns,
                        envelope.request_id,
                        envelope.session_id,
                    ),
                )
            finally:
                conn.close()

    def ack(self, consumer_id: str, topic: str, envelope_id: int) -> None:
        """
        Record that ``consumer_id`` has fully processed ``envelope_id`` for ``topic``.
        last_acked is monotonically non-decreasing per (consumer_id, topic).
        """
        if self._closed:
            return
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO acks (consumer_id, topic, last_acked_envelope_id) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(consumer_id, topic) DO UPDATE SET "
                    "  last_acked_envelope_id = MAX(acks.last_acked_envelope_id, excluded.last_acked_envelope_id)",
                    (consumer_id, topic, int(envelope_id)),
                )
            finally:
                conn.close()

    def prune_acked(self, retain_below: int = 0) -> int:
        """
        Delete envelopes whose ``envelope_id`` is <= the smallest ``last_acked``
        across every consumer for that topic.  Use sparingly; typically
        called from a background maintenance task.

        Args:
            retain_below: Optional override.  If > 0, deletes envelopes with
                envelope_id <= retain_below regardless of acks (force prune).

        Returns:
            Number of envelope rows deleted.
        """
        with self._lock:
            conn = self._connect()
            try:
                if retain_below > 0:
                    cur = conn.execute(
                        "DELETE FROM envelopes WHERE envelope_id <= ?",
                        (int(retain_below),),
                    )
                    return cur.rowcount or 0

                # For each topic, find the min(last_acked) across consumers,
                # then delete envelopes <= that watermark.
                cur = conn.execute(
                    """
                    SELECT topic, MIN(last_acked_envelope_id)
                    FROM acks
                    GROUP BY topic
                    """
                )
                deleted = 0
                for topic, watermark in cur.fetchall():
                    d = conn.execute(
                        "DELETE FROM envelopes WHERE topic = ? AND envelope_id <= ?",
                        (topic, int(watermark)),
                    )
                    deleted += d.rowcount or 0
                return deleted
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Reads (replay path)
    # ------------------------------------------------------------------

    def unacked(self, consumer_id: str, topic: str) -> Iterator[OutboxRecord]:
        """
        Yield outbox records for ``topic`` that ``consumer_id`` has not yet
        acked, in envelope_id order.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT last_acked_envelope_id FROM acks WHERE consumer_id = ? AND topic = ?",
                (consumer_id, topic),
            ).fetchone()
            last_acked = int(row[0]) if row else 0
            cur = conn.execute(
                "SELECT envelope_id, topic, payload, priority, created_ns, request_id, session_id "
                "FROM envelopes "
                "WHERE topic = ? AND envelope_id > ? AND deleted = 0 "
                "ORDER BY envelope_id ASC",
                (topic, last_acked),
            )
            for r in cur.fetchall():
                yield OutboxRecord(
                    envelope_id=int(r[0]),
                    topic=str(r[1]),
                    payload=bytes(r[2]) if r[2] is not None else b"",
                    priority=int(r[3]),
                    created_ns=int(r[4]),
                    request_id=str(r[5]),
                    session_id=str(r[6]),
                )
        finally:
            conn.close()

    def last_envelope_id(self) -> int:
        """Largest envelope_id stored in the outbox (0 if empty)."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT MAX(envelope_id) FROM envelopes").fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()

    def count(self, topic: str | None = None) -> int:
        """Total stored envelopes, optionally filtered to ``topic``."""
        conn = self._connect()
        try:
            if topic is None:
                row = conn.execute("SELECT COUNT(*) FROM envelopes").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM envelopes WHERE topic = ?",
                    (topic,),
                ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def close(self) -> None:
        """Mark the outbox closed (subsequent appends raise)."""
        self._closed = True

    def __repr__(self) -> str:
        return f"BusOutbox(path={self._path!r}, closed={self._closed})"


__all__ = ["BusOutbox", "OutboxRecord"]
