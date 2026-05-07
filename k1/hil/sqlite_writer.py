"""``k1.hil.sqlite_writer`` — durable event log for HIL lifecycle (M13.E2).

A small append-only sqlite store for the four HIL lifecycle events:

  * ``HILRequestedEvent``  — request opened.
  * ``HILResolvedEvent``   — request closed by user / system.
  * ``HILTimedOutEvent``   — watcher fired before resolution.
  * ``HILBlockedEvent``    — request rejected before reaching the user.

The writer is intentionally minimal — it gives the kernel a crash-safe
trail so an in-flight HIL request can be replayed (or audited) after a
restart. Higher-level HIL flow continues to live in
:class:`k1.hil.suspension.SuspensionManager`; this writer is the
``ledger=`` argument the manager already accepts.

Design constraints
------------------

* No external dependencies (stdlib ``sqlite3`` only).
* Single-file db; safe for concurrent reads thanks to WAL journal mode.
* All writes auto-commit (one row per call) so a crash mid-session
  loses at most the in-flight statement.
* Events are stored as JSON in the ``payload`` column to keep the
  schema stable across event-type evolutions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from k1.hil.types import (
    HILBlockedEvent,
    HILRequestedEvent,
    HILResolvedEvent,
    HILTimedOutEvent,
)

__all__ = ["SQLiteHILEventWriter"]

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS hil_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hil_request_id  TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    resolver_id     TEXT NOT NULL DEFAULT '',
    payload         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hil_events_request_id
    ON hil_events(hil_request_id);

CREATE INDEX IF NOT EXISTS idx_hil_events_event_type
    ON hil_events(event_type);
"""


_EventTypes = (
    HILRequestedEvent,
    HILResolvedEvent,
    HILTimedOutEvent,
    HILBlockedEvent,
)


class SQLiteHILEventWriter:
    """Append-only sqlite store for HIL lifecycle events.

    Use ``":memory:"`` for tests and an absolute file path for
    production. The ``WAL`` journal mode is enabled on real files so
    readers (e.g. an audit query) don't block writers.
    """

    __slots__ = ("_db_path", "_conn", "_lock")

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        # ``check_same_thread=False`` lets the manager invoke the
        # writer from its asyncio timeout watcher tasks. Concurrency
        # is serialised by ``_lock``.
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        if self._db_path != ":memory:":
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:  # pragma: no cover - defensive
                logger.debug(
                    "SQLiteHILEventWriter: WAL pragma rejected for %s",
                    self._db_path,
                )
        self._conn.commit()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def append(self, event: Any) -> None:
        """Persist a single HIL lifecycle event."""
        if not isinstance(event, _EventTypes):
            raise TypeError(
                f"SQLiteHILEventWriter.append: unsupported event type " f"{type(event).__name__}"
            )
        event_type = type(event).__name__
        timestamp_ms = int(getattr(event, "timestamp_ms", 0))
        resolver_id = str(getattr(event, "resolver_id", ""))
        payload_json = json.dumps(asdict(event), ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT INTO hil_events "
                "(hil_request_id, event_type, timestamp_ms, resolver_id, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    event.hil_request_id,
                    event_type,
                    timestamp_ms,
                    resolver_id,
                    payload_json,
                ),
            )
            self._conn.commit()

    # SuspensionManager already calls ``writer.append_sync(evt)`` for
    # the LedgerWriter shape — alias so we slot in cleanly.
    append_sync = append

    # ------------------------------------------------------------------
    def read_all(self, hil_request_id: str | None = None) -> list[dict[str, Any]]:
        """Return event rows as dicts, oldest first.

        Filters by ``hil_request_id`` when provided. Used by audit
        tools and the durability replay in
        :func:`k1.hil.suspension.replay_pending`.
        """
        with self._lock:
            if hil_request_id is None:
                cur = self._conn.execute(
                    "SELECT id, hil_request_id, event_type, timestamp_ms, "
                    "resolver_id, payload FROM hil_events ORDER BY id ASC"
                )
            else:
                cur = self._conn.execute(
                    "SELECT id, hil_request_id, event_type, timestamp_ms, "
                    "resolver_id, payload FROM hil_events "
                    "WHERE hil_request_id = ? ORDER BY id ASC",
                    (hil_request_id,),
                )
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "hil_request_id": row[1],
                    "event_type": row[2],
                    "timestamp_ms": row[3],
                    "resolver_id": row[4],
                    "payload": json.loads(row[5]),
                }
            )
        return result

    # ------------------------------------------------------------------
    def pending_request_ids(self) -> list[str]:
        """Return ``hil_request_id``s that have a Requested event but no
        terminal (Resolved / TimedOut / Blocked) event.

        Drives crash-recovery replay: anything still pending after a
        restart should be re-emitted on the bus or auto-cancelled.
        """
        terminal = {
            "HILResolvedEvent",
            "HILTimedOutEvent",
            "HILBlockedEvent",
        }
        seen_request: set[str] = set()
        seen_terminal: set[str] = set()
        for row in self.read_all():
            rid = row["hil_request_id"]
            if row["event_type"] == "HILRequestedEvent":
                seen_request.add(rid)
            elif row["event_type"] in terminal:
                seen_terminal.add(rid)
        return sorted(seen_request - seen_terminal)

    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:  # pragma: no cover
                logger.debug("SQLiteHILEventWriter.close: ignored", exc_info=True)

    # ------------------------------------------------------------------
    def __enter__(self) -> "SQLiteHILEventWriter":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def _materialize(events: Iterable[Any]) -> list[dict[str, Any]]:  # pragma: no cover
    """Helper used in tests: materialise an event iterable to dicts."""
    return [asdict(e) for e in events]
