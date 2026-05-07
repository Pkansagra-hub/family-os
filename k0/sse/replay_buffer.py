"""SQLite-backed per-topic SSE replay buffer (MS-3d Epic 3d.3).

Design references:
    docs/architecture/whiteboard_k1/bridge_system_design.md
    \u2022 D13: cursor protocol \u2014 ``Last-Event-ID`` header + 24h replay buffer.
            On stale cursor (older than the retention window or simply
            not present in the buffer) the server emits a synthetic
            ``event: replay-gap-detected`` frame so the K1 client can
            trigger a corrective resync rather than silently losing
            events.

Storage shape (one SQLite database file per K0 process; per-topic
isolation enforced via the ``topic`` column + composite indexes):

    CREATE TABLE sse_replay_buffer (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        envelope_id TEXT NOT NULL,
        payload TEXT NOT NULL,                 -- JSON body
        created_at REAL NOT NULL               -- unix epoch seconds
    );
    CREATE UNIQUE INDEX ux_topic_env ON sse_replay_buffer(topic, envelope_id);
    CREATE INDEX ix_topic_seq ON sse_replay_buffer(topic, seq);
    CREATE INDEX ix_created_at ON sse_replay_buffer(created_at);

The buffer is **append-only by writers** and **eviction-only by the
retention sweep**. Writes are point-in-time durable: each ``append``
issues a single ``INSERT`` under ``isolation_level=None`` (autocommit)
so a K0 crash mid-fanout never reorders or loses already-acked events.

Replay semantics:
    \u2022 ``replay_after(topic, cursor=None)`` \u2192 every row with
      ``topic = ? AND seq > <cursor_seq>`` ordered by ``seq ASC``.
      Caller-supplied ``cursor`` is the ``envelope_id`` of the last event
      the consumer acked; we resolve it to a ``seq`` here.
    \u2022 ``replay_after(topic, cursor=...)`` where ``cursor`` is **not in
      the buffer** \u2192 raises :class:`ReplayGapError`. The endpoint maps
      this to a synthetic ``replay-gap-detected`` SSE frame and closes
      the stream after sending it (consumer must re-subscribe with no
      cursor and treat the next stream as a fresh start).
    \u2022 ``replay_after(topic, cursor=None)`` \u2192 empty stream (we don't
      flood new subscribers with the entire 24h backlog by default).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sse_replay_buffer (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    envelope_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_topic_env
    ON sse_replay_buffer(topic, envelope_id);
CREATE INDEX IF NOT EXISTS ix_topic_seq
    ON sse_replay_buffer(topic, seq);
CREATE INDEX IF NOT EXISTS ix_created_at
    ON sse_replay_buffer(created_at);
"""


DEFAULT_RETENTION_S: float = 24 * 60 * 60  # PT24H per all 5 SSE manifests.


@dataclass(frozen=True)
class ReplayEvent:
    """One row of the replay buffer surfaced to the SSE endpoint."""

    seq: int
    topic: str
    envelope_id: str
    payload: dict[str, Any]
    created_at: float


class ReplayGapError(LookupError):
    """Raised when a caller-supplied cursor is not present in the buffer.

    The :mod:`k0.sse.endpoint` route catches this and emits a synthetic
    ``replay-gap-detected`` SSE frame before closing the connection.
    """

    def __init__(self, *, topic: str, cursor: str) -> None:
        self.topic = topic
        self.cursor = cursor
        super().__init__(
            f"SSE replay gap on topic={topic!r}: cursor={cursor!r} "
            "is not in the replay buffer (likely older than retention "
            "window or never persisted)."
        )


class SSEReplayBuffer:
    """Per-process, multi-topic SSE replay buffer.

    Thread-safe: each public method takes ``self._lock``. The underlying
    SQLite connection runs with ``check_same_thread=False`` because the
    K0 SSE endpoint serves requests from the asyncio event loop while
    eviction sweeps are run from a periodic background thread.

    Use :meth:`from_path` to construct one bound to a file (production)
    or pass ``":memory:"`` for tests.
    """

    def __init__(
        self, conn: sqlite3.Connection, *, retention_s: float = DEFAULT_RETENTION_S
    ) -> None:
        self._conn = conn
        self._retention_s = retention_s
        self._lock = threading.RLock()
        self._init_schema()

    @classmethod
    def from_path(
        cls, path: Path | str, *, retention_s: float = DEFAULT_RETENTION_S
    ) -> "SSEReplayBuffer":
        """Open (or create) a replay buffer at ``path``.

        Parent directories are created if missing. ``path`` may be the
        special string ``":memory:"`` for an in-memory store (test use).
        """
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(path),
            isolation_level=None,
            check_same_thread=False,
        )
        return cls(conn, retention_s=retention_s)

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # Tune for write concurrency / no fsync stalls on bursty
            # P06/P03 emit traffic. ``WAL`` mode + ``NORMAL`` sync gives
            # us crash-consistency without per-row fsync.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")

    # ------------------------------------------------------------------
    # Append / replay / eviction.
    # ------------------------------------------------------------------

    def append(
        self,
        *,
        topic: str,
        envelope_id: str,
        payload: dict[str, Any],
        created_at: float | None = None,
    ) -> tuple[int, bool]:
        """Append one event to the buffer.

        Returns ``(seq, was_new)`` \u2014 ``seq`` is the auto-assigned
        primary key, ``was_new`` is ``True`` if this call inserted a
        new row and ``False`` if a row with the same
        ``(topic, envelope_id)`` already existed (idempotent retry).

        ``envelope_id`` is the on-the-wire ``id:`` field; uniqueness per
        ``(topic, envelope_id)`` is enforced by a UNIQUE index so a
        retried emit (e.g. P06 retries on a dropped fanout) is idempotent.
        """
        ts = time.time() if created_at is None else float(created_at)
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO sse_replay_buffer(topic, envelope_id, payload, created_at) "
                    "VALUES(?, ?, ?, ?)",
                    (topic, envelope_id, body, ts),
                )
                seq = cur.lastrowid
                if seq is None:  # pragma: no cover - sqlite always assigns
                    raise RuntimeError("sqlite did not return lastrowid")
                return int(seq), True
            except sqlite3.IntegrityError:
                # Duplicate (topic, envelope_id): re-fetch the existing seq.
                row = self._conn.execute(
                    "SELECT seq FROM sse_replay_buffer " "WHERE topic = ? AND envelope_id = ?",
                    (topic, envelope_id),
                ).fetchone()
                if row is None:  # pragma: no cover - paranoia
                    raise
                return int(row[0]), False

    def replay_after(
        self,
        *,
        topic: str,
        cursor: str | None,
        limit: int | None = None,
    ) -> Iterator[ReplayEvent]:
        """Yield every event with ``seq > <cursor_seq>`` for ``topic``.

        ``cursor`` is an ``envelope_id`` (matches the SSE wire format).
        ``cursor=None`` yields nothing \u2014 fresh subscribers start live,
        not from history (mirrors the SSE spec's "no Last-Event-ID =
        start now" semantics). Pass ``cursor=""`` (empty string) to
        force-replay everything currently in the buffer (admin / test).

        Raises :class:`ReplayGapError` if ``cursor`` is non-empty and
        not present in the buffer.
        """
        with self._lock:
            if cursor is None:
                return iter(())
            if cursor == "":
                cursor_seq = 0
            else:
                row = self._conn.execute(
                    "SELECT seq FROM sse_replay_buffer " "WHERE topic = ? AND envelope_id = ?",
                    (topic, cursor),
                ).fetchone()
                if row is None:
                    raise ReplayGapError(topic=topic, cursor=cursor)
                cursor_seq = int(row[0])
            sql = (
                "SELECT seq, topic, envelope_id, payload, created_at "
                "FROM sse_replay_buffer "
                "WHERE topic = ? AND seq > ? ORDER BY seq ASC"
            )
            params: tuple[Any, ...] = (topic, cursor_seq)
            if limit is not None:
                sql += " LIMIT ?"
                params = (*params, int(limit))
            rows = self._conn.execute(sql, params).fetchall()
        return (
            ReplayEvent(
                seq=int(seq),
                topic=str(t),
                envelope_id=str(env),
                payload=json.loads(body),
                created_at=float(ts),
            )
            for seq, t, env, body, ts in rows
        )

    def evict_expired(self, *, now: float | None = None) -> int:
        """Delete every row older than the retention window. Returns count.

        Idempotent and safe to call from a background thread; the
        endpoint's read path takes the same lock so eviction never
        races with an in-flight replay.
        """
        cutoff = (time.time() if now is None else float(now)) - self._retention_s
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM sse_replay_buffer WHERE created_at < ?",
                (cutoff,),
            )
            return int(cur.rowcount or 0)

    # ------------------------------------------------------------------
    # Introspection (used by /k0/sse health endpoints + tests).
    # ------------------------------------------------------------------

    def depth(self, topic: str | None = None) -> int:
        """Row count for ``topic`` (or all topics when ``topic is None``)."""
        with self._lock:
            if topic is None:
                row = self._conn.execute("SELECT COUNT(*) FROM sse_replay_buffer").fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM sse_replay_buffer WHERE topic = ?",
                    (topic,),
                ).fetchone()
            return int(row[0])

    def latest_envelope_id(self, topic: str) -> str | None:
        """Return the highest-``seq`` envelope_id for ``topic``, or ``None``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT envelope_id FROM sse_replay_buffer "
                "WHERE topic = ? ORDER BY seq DESC LIMIT 1",
                (topic,),
            ).fetchone()
        return None if row is None else str(row[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()


__all__ = (
    "DEFAULT_RETENTION_S",
    "ReplayEvent",
    "ReplayGapError",
    "SSEReplayBuffer",
)
