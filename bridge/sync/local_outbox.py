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
from typing import TYPE_CHECKING

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
        self._conn.executescript(f"{_CREATE_TABLE_SQL}\n{_CREATE_INDEX_SQL}")
        self._conn.commit()

    # -- public API ----------------------------------------------------------

    def enqueue(
        self,
        envelope_json: str,
        topic: str,
        priority: int = 2,
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
            "INSERT INTO outbox_queue (topic, envelope_json, priority, created_at) VALUES (?, ?, ?, ?)",
            (topic, envelope_json, priority, now),
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
