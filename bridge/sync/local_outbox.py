"""SQLite-backed offline queue for Bridge envelope persistence.

When K0 is unreachable (5xx, 429, timeout), envelopes are persisted here
and drained when connectivity is restored.  Guarantees MW-09: no envelope
loss through device restarts, network outages, or K0 downtime.

Per bridge/contracts/command_port.protocol.yaml offline section.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.transport import HttpTransport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_QUEUE_DEPTH = 10_000
MAX_ATTEMPTS = 10
DEFAULT_DRAIN_CONCURRENCY = 5
DEFAULT_POLL_INTERVAL_S = 10.0
MAX_POLL_INTERVAL_S = 60.0

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS outbox_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT    NOT NULL,
    envelope_json   TEXT    NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 2,
    created_at      TEXT    NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    status          TEXT    NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'FAILED'))
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox_queue (status, priority DESC, created_at ASC);
"""

# MS-3b epic 3b.3 \u2014 enriched dead-letter routing + per-row TTL.
_CREATE_DEAD_LETTER_SQL = """
CREATE TABLE IF NOT EXISTS dead_letter (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id     INTEGER NOT NULL,
    topic           TEXT    NOT NULL,
    envelope_json   TEXT    NOT NULL,
    enqueued_at     TEXT    NOT NULL,
    moved_at        TEXT    NOT NULL,
    reason          TEXT    NOT NULL,
    response_code   INTEGER,
    response_body   TEXT
);
"""


# ---------------------------------------------------------------------------
# Outbox entry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OutboxQueueEntry:
    """A single row in the local outbox queue."""

    id: int
    topic: str
    envelope_json: str
    priority: int
    created_at: str
    attempts: int
    last_attempt_at: str | None
    status: str


# ---------------------------------------------------------------------------
# LocalOutbox
# ---------------------------------------------------------------------------


class LocalOutbox:
    """SQLite-backed offline queue for Bridge envelopes.

    One database per device.  Thread-safe via SQLite's built-in locking.
    All public methods are synchronous (SQLite operations are fast, typically
    sub-millisecond).  The ``drain`` method is async because it performs
    HTTP calls.

    Parameters
    ----------
    db_path : str | Path
        Path to the SQLite database file (created if absent).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(
            f"{_CREATE_TABLE_SQL}\n{_CREATE_INDEX_SQL}\n{_CREATE_DEAD_LETTER_SQL}"
        )
        # MS-3b additive migration: add ``max_queue_age_s`` column for
        # per-row TTL. Use a defensive ALTER \u2014 SQLite has no IF NOT
        # EXISTS for columns, so we read the schema and skip when set.
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(outbox_queue)")}
        if "max_queue_age_s" not in cols:
            self._conn.execute("ALTER TABLE outbox_queue ADD COLUMN max_queue_age_s INTEGER")
        self._conn.commit()

    # -- public API ----------------------------------------------------------

    def enqueue(
        self,
        envelope_json: str,
        topic: str,
        priority: int = 2,
        *,
        max_queue_age_s: int | None = None,
    ) -> int:
        """Persist an envelope to the offline queue.

        Parameters
        ----------
        envelope_json : str
            Full serialised envelope JSON string.
        topic : str
            Command topic for logging/ordering.
        priority : int
            Numeric priority (1=HIGH, 2=NORMAL, 3=LOW).
        max_queue_age_s : int | None
            Per-row TTL in seconds. When set, :meth:`prune_expired`
            will remove rows whose ``created_at + max_queue_age_s`` lies
            in the past. ``None`` disables TTL for this row.

        Returns
        -------
        int
            Row ID of the inserted entry.

        Raises
        ------
        RuntimeError
            If the queue has reached ``MAX_QUEUE_DEPTH``.
        """
        count = self._count_pending()
        if count >= MAX_QUEUE_DEPTH:
            msg = f"LocalOutbox queue full ({count}/{MAX_QUEUE_DEPTH})"
            raise RuntimeError(msg)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cursor = self._conn.execute(
            "INSERT INTO outbox_queue "
            "(topic, envelope_json, priority, created_at, max_queue_age_s) "
            "VALUES (?, ?, ?, ?, ?)",
            (topic, envelope_json, priority, now, max_queue_age_s),
        )
        self._conn.commit()
        row_id = cursor.lastrowid
        logger.info("LocalOutbox enqueued: topic=%s priority=%d id=%d", topic, priority, row_id)
        return row_id or 0

    def pending_count(self) -> int:
        """Return the number of PENDING entries."""
        return self._count_pending()

    def list_pending(self, limit: int = 50) -> list[OutboxQueueEntry]:
        """Return PENDING entries ordered by priority DESC, created_at ASC."""
        rows = self._conn.execute(
            "SELECT id, topic, envelope_json, priority, created_at, attempts, last_attempt_at, status "
            "FROM outbox_queue WHERE status = 'PENDING' "
            "ORDER BY priority ASC, created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [OutboxQueueEntry(*row) for row in rows]

    async def drain(
        self, transport: HttpTransport, max_concurrent: int = DEFAULT_DRAIN_CONCURRENCY
    ) -> int:
        """Drain PENDING entries by sending them to K0.

        Parameters
        ----------
        transport : HttpTransport
            Open HTTP transport for K0 communication.
        max_concurrent : int
            Max simultaneous drain submissions.

        Returns
        -------
        int
            Number of successfully drained entries.
        """
        entries = self.list_pending(limit=100)
        if not entries:
            return 0

        semaphore = asyncio.Semaphore(max_concurrent)
        results = await asyncio.gather(
            *[self._drain_one(entry, transport, semaphore) for entry in entries],
            return_exceptions=True,
        )
        success_count = sum(1 for r in results if r is True)
        logger.info("LocalOutbox drain: %d/%d succeeded", success_count, len(entries))
        return success_count

    def mark_failed(self, entry_id: int) -> None:
        """Mark an entry as permanently FAILED (max attempts exceeded)."""
        self._conn.execute(
            "UPDATE outbox_queue SET status = 'FAILED' WHERE id = ?",
            (entry_id,),
        )
        self._conn.commit()

    def delete(self, entry_id: int) -> None:
        """Remove a successfully drained entry."""
        self._conn.execute("DELETE FROM outbox_queue WHERE id = ?", (entry_id,))
        self._conn.commit()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    # -- MS-3b epic 3b.3: dead-letter + TTL ---------------------------------

    def move_to_dead_letter(
        self,
        entry_id: int,
        *,
        reason: str,
        response_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        """Atomically move ``entry_id`` from ``outbox_queue`` to ``dead_letter``.

        Used by :class:`bridge.sync.drain_worker.DrainWorker` when a
        4xx contract-violation response is observed: the envelope is
        unrecoverable and must not retry, but operators must still see
        it for the dead-letter replay procedure.
        """
        row = self._conn.execute(
            "SELECT topic, envelope_json, created_at FROM outbox_queue WHERE id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            return
        topic, envelope_json, created_at = row
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._conn:
            self._conn.execute(
                "INSERT INTO dead_letter "
                "(original_id, topic, envelope_json, enqueued_at, moved_at, "
                " reason, response_code, response_body) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    topic,
                    envelope_json,
                    created_at,
                    now,
                    reason,
                    response_code,
                    response_body,
                ),
            )
            self._conn.execute("DELETE FROM outbox_queue WHERE id = ?", (entry_id,))
        logger.warning(
            "LocalOutbox: id=%d topic=%s \u2192 dead_letter (reason=%s code=%s)",
            entry_id,
            topic,
            reason,
            response_code,
        )

    def dead_letter_count(self) -> int:
        """Return the number of rows in the ``dead_letter`` table."""
        row = self._conn.execute("SELECT COUNT(*) FROM dead_letter").fetchone()
        return row[0] if row else 0

    def list_dead_letter(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return dead-letter rows for operator inspection / replay."""
        rows = self._conn.execute(
            "SELECT id, original_id, topic, envelope_json, enqueued_at, moved_at, "
            "reason, response_code, response_body "
            "FROM dead_letter ORDER BY moved_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        keys = (
            "id",
            "original_id",
            "topic",
            "envelope_json",
            "enqueued_at",
            "moved_at",
            "reason",
            "response_code",
            "response_body",
        )
        return [dict(zip(keys, r, strict=False)) for r in rows]

    def prune_expired(self, *, now_iso: str | None = None) -> int:
        """Remove pending rows whose ``created_at + max_queue_age_s`` lies
        in the past. Returns the number of rows pruned.

        Rows whose ``max_queue_age_s`` is NULL are exempt.
        """
        now_dt = (
            datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            if now_iso is not None
            else datetime.now(timezone.utc)
        )
        rows = self._conn.execute(
            "SELECT id, created_at, max_queue_age_s FROM outbox_queue "
            "WHERE max_queue_age_s IS NOT NULL AND status = 'PENDING'"
        ).fetchall()
        expired_ids: list[int] = []
        for row_id, created_at, ttl_s in rows:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            age_s = (now_dt - created_dt).total_seconds()
            if age_s >= ttl_s:
                expired_ids.append(row_id)
        if expired_ids:
            self._conn.executemany(
                "DELETE FROM outbox_queue WHERE id = ?",
                [(i,) for i in expired_ids],
            )
            self._conn.commit()
            logger.info("LocalOutbox: pruned %d expired row(s)", len(expired_ids))
        return len(expired_ids)

    # -- drain internals -----------------------------------------------------

    async def _drain_one(
        self,
        entry: OutboxQueueEntry,
        transport: HttpTransport,
        semaphore: asyncio.Semaphore,
    ) -> bool:
        """Attempt to send a single entry. Returns True on success."""
        async with semaphore:
            result = await transport.post_command(entry.envelope_json.encode("utf-8"))

            if result.status_code == 200:
                self.delete(entry.id)
                return True

            if result.status_code == 409:
                # Idempotent duplicate: safe to remove
                logger.info("LocalOutbox drain: duplicate (409) for id=%d", entry.id)
                self.delete(entry.id)
                return True

            # Failure: increment attempts
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            new_attempts = entry.attempts + 1

            if new_attempts >= MAX_ATTEMPTS:
                logger.error(
                    "LocalOutbox: max attempts reached for id=%d topic=%s",
                    entry.id,
                    entry.topic,
                )
                self.mark_failed(entry.id)
                return False

            self._conn.execute(
                "UPDATE outbox_queue SET attempts = ?, last_attempt_at = ? WHERE id = ?",
                (new_attempts, now, entry.id),
            )
            self._conn.commit()
            logger.warning(
                "LocalOutbox drain failed: id=%d status=%d attempts=%d/%d",
                entry.id,
                result.status_code,
                new_attempts,
                MAX_ATTEMPTS,
            )
            return False

    # -- helpers -------------------------------------------------------------

    def _count_pending(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM outbox_queue WHERE status = 'PENDING'"
        ).fetchone()
        return row[0] if row else 0
