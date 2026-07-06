"""
k1.kernel.session_registry — Persistent session lifecycle backed by kernel.db.

Wraps KernelDB for CRUD on st_sessions.  Session IDs follow the format:
  web-{12 hex chars}   (web shell)
  kernel-{12 hex chars} (CLI/runner)

The prefix is the "origin"; the 12-char hex is os.urandom(6) for 48 bits
of entropy (collision probability < 1e-7 for 10k sessions).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class SessionRegistry:
    """Stable session identity backed by kernel.db.

    Owned by KernelService._session_registry.  Initialized during
    Tier 1 startup (S2.12 / S0.5) alongside KernelDB.  Closed during
    shutdown (set to None before KernelDB.close()).
    """

    def __init__(self, kernel_db: object) -> None:
        """Wrap a KernelDB instance.

        Args:
            kernel_db: An open KernelDB (is_open must be True).
        """
        # kernel_db is KernelDB but we avoid the import to keep this
        # module importable without pulling in sqlite3 at module level.
        self._db = kernel_db

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(self, title: str = "New Chat", origin: str = "web") -> str:
        """Create a new session row and return the session_id.

        Generates a 12-char hex ID from os.urandom(6).  The row is
        committed immediately — no batching needed.
        """
        hex_id = os.urandom(6).hex()  # 48 bits
        session_id = f"{origin}-{hex_id}"
        now_ms = int(time.time() * 1000)
        self._db.execute(
            "INSERT INTO st_sessions"
            "  (session_id, title, turn_count, last_active, created_at)"
            "  VALUES (?, ?, ?, ?, ?)",
            (session_id, title, 0, now_ms, now_ms),
        )
        logger.debug("SessionRegistry: created %s title=%r", session_id, title)
        return session_id

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        """Return all sessions, newest first."""
        rows = self._db.execute(
            "SELECT session_id, title, turn_count, last_active, created_at"
            "  FROM st_sessions"
            "  ORDER BY last_active DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Return a single session row or None."""
        row = self._db.execute(
            "SELECT session_id, title, turn_count, last_active, created_at"
            "  FROM st_sessions"
            "  WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_most_recent(self) -> dict[str, Any] | None:
        """Return the most-recently-active session, or None."""
        rows = self._db.execute(
            "SELECT session_id, title, turn_count, last_active, created_at"
            "  FROM st_sessions"
            "  ORDER BY last_active DESC LIMIT 1"
        ).fetchall()
        return dict(rows[0]) if rows else None

    def count(self) -> int:
        """Return the total number of sessions in the registry."""
        row = self._db.execute("SELECT COUNT(*) FROM st_sessions").fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update_title(self, session_id: str, title: str) -> bool:
        """Update the title.  Returns False if session not found."""
        cur = self._db.execute(
            "UPDATE st_sessions SET title = ? WHERE session_id = ?",
            (title, session_id),
        )
        return cur.rowcount > 0

    def touch(self, session_id: str) -> bool:
        """Update last_active to now.  Returns False if session not found."""
        now_ms = int(time.time() * 1000)
        cur = self._db.execute(
            "UPDATE st_sessions SET last_active = ? WHERE session_id = ?",
            (now_ms, session_id),
        )
        return cur.rowcount > 0

    def increment_turn(self, session_id: str) -> bool:
        """Increment turn_count AND update last_active.

        Returns False if session not found.
        """
        now_ms = int(time.time() * 1000)
        cur = self._db.execute(
            "UPDATE st_sessions"
            "   SET turn_count = turn_count + 1,"
            "       last_active = ?"
            " WHERE session_id = ?",
            (now_ms, session_id),
        )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(self, session_id: str) -> bool:
        """Delete session row AND cascade-delete its messages.

        Returns False if session not found.
        """
        self._db.execute(
            "DELETE FROM st_chat_messages WHERE session_id = ?",
            (session_id,),
        )
        cur = self._db.execute(
            "DELETE FROM st_sessions WHERE session_id = ?",
            (session_id,),
        )
        return cur.rowcount > 0
