"""
k1.kernel.adapters.kernel_db — Kernel-level SQLite database.

Pattern B: lazy open()/close() lifecycle (mirrors GlobalProjectionStore
/ IdempotencyStore).  Owns the schema for st_sessions, st_chat_messages,
and kernel_meta (schema versioning).

Created at S2.12 of KernelService._startup_tier1().  Closed during
shutdown() and _cleanup_tier1_partial().
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS st_sessions (
    session_id   TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT 'New Chat',
    created_at   INTEGER NOT NULL,
    last_active  INTEGER NOT NULL,
    turn_count   INTEGER NOT NULL DEFAULT 0,
    member_id    TEXT,
    device_id    TEXT
);

CREATE TABLE IF NOT EXISTS st_chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    turn_num     INTEGER NOT NULL,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    timestamp    INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES st_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON st_chat_messages(session_id, turn_num);

CREATE INDEX IF NOT EXISTS idx_sessions_last_active
    ON st_sessions(last_active DESC);

CREATE TABLE IF NOT EXISTS kernel_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO kernel_meta (key, value) VALUES ('schema_version', '1');
"""


class KernelDB:
    """Kernel-level SQLite database (kernel.db).

    Lazy open/close lifecycle — call ``open()`` before use, ``close()``
    during shutdown.  Both are idempotent.  The public ``execute()``
    method delegates to ``sqlite3.Connection.execute()`` so callers
    (e.g. ``SessionRegistry``) never touch ``_conn`` directly.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the database and ensure the schema exists (idempotent)."""
        if self._conn is not None:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit mode
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._ensure_schema()
        self._conn.commit()
        logger.info("KernelDB opened: %s", self._db_path)

    def close(self) -> None:
        """Close the database (idempotent)."""
        if self._conn is None:
            return
        self._conn.commit()
        self._conn.close()
        self._conn = None
        logger.info("KernelDB closed: %s", self._db_path)

    @property
    def is_open(self) -> bool:
        """True if the database connection is open and ready."""
        return self._conn is not None

    # ------------------------------------------------------------------
    # SQL execution (public API for SessionRegistry + other callers)
    # ------------------------------------------------------------------

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a SQL statement and return the cursor.

        Thin delegation to ``sqlite3.Connection.execute()``.
        Callers must call ``.fetchone()`` / ``.fetchall()`` on the
        returned cursor as needed.
        """
        if self._conn is None:
            raise RuntimeError("KernelDB is not open")
        return self._conn.execute(sql, parameters)

    # ------------------------------------------------------------------
    # Chat message persistence (Slice 2)
    # ------------------------------------------------------------------

    def insert_message(
        self,
        session_id: str,
        turn_num: int,
        role: str,
        content: str,
        timestamp: int,
    ) -> None:
        """Write a single chat message row (user or assistant).

        Called from the turn.completed.v1 bus handler — fire-and-forget,
        never raises to the bus (caller wraps in try/except).
        """
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO st_chat_messages"
            "  (session_id, turn_num, role, content, timestamp)"
            "  VALUES (?, ?, ?, ?, ?)",
            (session_id, turn_num, role, content, timestamp),
        )

    def get_messages(self, session_id: str) -> list[dict[str, object]]:
        """Return all messages for a session, ordered by turn_num then role.

        Returns a list of dicts with keys: turn_num, role, content, timestamp.
        """
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT turn_num, role, content, timestamp"
            "  FROM st_chat_messages"
            "  WHERE session_id = ?"
            "  ORDER BY turn_num, role",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Execute the schema DDL (idempotent — uses IF NOT EXISTS)."""
        assert self._conn is not None
        self._conn.executescript(_SCHEMA_SQL)
